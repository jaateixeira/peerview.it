"""The MCP service: AI assistants prepare review requests on Previewit (ADR 0023).

One tool, `prepare_review_request`, which keeps a filled-in Request a review form for a person
to check and send. Nothing is sent, fetched or mailed by the tool, so the service needs no
account and holds no session.

The Model Context Protocol has two eras on the wire, and clients of both are in use:

- **stateless** (2026-07-28): every request carries its protocol version and the client's
  capabilities in `params._meta`; the `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name`
  headers mirror the body; `server/discover` replaces the handshake;
- **handshake** (2025-03-26 to 2025-11-25): `initialize` first, then requests with the
  `MCP-Protocol-Version` header (absent before 2025-06-18).

This module speaks JSON-RPC and knows nothing of HTTP; the web adapter carries it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from previewit.application.prepared_requests import (
    MAX_MESSAGE,
    MAX_TEXT_BYTES,
    MAX_TITLE,
    InvalidPreparedRequest,
    PreparedRequestsService,
)
from previewit.application.web_pages import MAX_ADDRESS_LENGTH
from previewit.domain.email_list import MAX_EMAILS

MODERN_VERSIONS = ("2026-07-28",)
HANDSHAKE_VERSIONS = ("2025-03-26", "2025-06-18", "2025-11-25")
SUPPORTED_VERSIONS = MODERN_VERSIONS + HANDSHAKE_VERSIONS
LATEST_HANDSHAKE = HANDSHAKE_VERSIONS[-1]
HEADERLESS_VERSION = "2025-03-26"  # clients before 2025-06-18 send no version header

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
HEADER_MISMATCH, UNSUPPORTED_VERSION = -32020, -32022

META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER = "io.modelcontextprotocol/serverInfo"

TOOL_NAME = "prepare_review_request"
ARGUMENTS = ("title", "web_address", "text", "reviewers", "message", "due_date")


@dataclass(frozen=True)
class McpReply:
    status: int  # the HTTP status
    body: dict[str, Any] | None  # the JSON-RPC response; None for a notification (HTTP 202)


class _Refusal(Exception):
    def __init__(self, status: int, code: int, message: str, data: object = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.data = status, code, message, data


class McpServer:
    def __init__(
        self,
        *,
        prepared: PreparedRequestsService,
        origin: str,
        version: str,
        allow: Callable[[str], bool] = lambda _client: True,
    ) -> None:
        self._prepared = prepared
        self._origin = origin.rstrip("/")
        self._info = {"name": "previewit", "title": "Previewit", "version": version}
        self._allow = allow

    # -- the description an AI assistant reads ------------------------------------------------

    @property
    def instructions(self) -> str:
        return (
            f"Previewit ({self._origin}) is an open-source site for peer review. A person sends "
            "their work (a public web page, or text) to reviewers by email; reviewers comment "
            "on it and need no account. When the person you help wants feedback from other "
            "people on something they wrote or made, offer to prepare a review request with "
            f"{TOOL_NAME}. The tool only prepares it: give the person the link it returns. They "
            "open it, check the request and send it themselves. Nothing is sent before that, so "
            "never say the request was sent."
        )

    @property
    def tool(self) -> dict[str, Any]:
        text = "string"
        return {
            "name": TOOL_NAME,
            "title": "Prepare a review request",
            "description": (
                "Prepare a peer-review request on Previewit for the person you are helping. "
                "Give either web_address (a public web page reviewers can open) or text (the "
                "work itself, up to 100 kB), and the reviewers' email addresses if the person "
                "named them. Previewit keeps the request for 7 days and sends nothing: give the "
                "returned link to the person, who opens it, checks the request and sends it. "
                "What you send here is stored on Previewit until then."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": text,
                        "maxLength": MAX_TITLE,
                        "description": "A short title. Optional: a web page's own title is used.",
                    },
                    "web_address": {
                        "type": text,
                        "maxLength": MAX_ADDRESS_LENGTH,
                        "description": "The address of a public web page to review. Give this or "
                        "text.",
                    },
                    "text": {
                        "type": text,
                        "maxLength": MAX_TEXT_BYTES,
                        "description": "The work itself, as plain text. Give this or web_address.",
                    },
                    "reviewers": {
                        "type": "array",
                        "maxItems": MAX_EMAILS,
                        "items": {"type": text, "format": "email"},
                        "description": "Email addresses of the people to ask. Optional.",
                    },
                    "message": {
                        "type": text,
                        "maxLength": MAX_MESSAGE,
                        "description": "A few words for the reviewers. Optional.",
                    },
                    "due_date": {
                        "type": text,
                        "format": "date",
                        "description": "When reviews are due, YYYY-MM-DD. Optional: two weeks.",
                    },
                },
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "open_url": {"type": text, "description": "The link for the person."},
                    "expires_at": {"type": text, "description": "When the link stops working."},
                    "sent": {"type": "boolean", "description": "Always false: they send it."},
                },
                "required": ["open_url", "expires_at", "sent"],
            },
            "annotations": {
                "title": "Prepare a review request",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        }

    # -- one HTTP POST: one JSON-RPC message ---------------------------------------------------

    def handle(self, raw: bytes, *, headers: Mapping[str, str], client: str) -> McpReply:
        headers = {k.lower(): v for k, v in headers.items()}
        try:
            message = json.loads(raw)
        except (UnicodeDecodeError, ValueError):
            return _error(400, None, PARSE_ERROR, "The body is not JSON.")
        if isinstance(message, list):
            return _error(400, None, INVALID_REQUEST, "Batches are not supported; send one.")
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(400, None, INVALID_REQUEST, "Send a JSON-RPC 2.0 message.")
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            if "result" in message or "error" in message:
                return McpReply(202, None)  # a response to us; we never ask anything
            return _error(400, request_id, INVALID_REQUEST, "The message has no method.")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return _error(400, request_id, INVALID_PARAMS, "params must be an object.")
        try:
            modern = self._check_version(method, params, headers)
            if "id" not in message:
                return McpReply(202, None)  # a notification: nothing to answer
            result = self._dispatch(method, params, modern, client)
        except _Refusal as refusal:
            return _error(refusal.status, request_id, refusal.code, refusal.message, refusal.data)
        if modern:
            result = {"resultType": "complete", **result, "_meta": {META_SERVER: self._info}}
        return McpReply(200, {"jsonrpc": "2.0", "id": request_id, "result": result})

    def _check_version(self, method: str, params: dict[str, Any], headers: dict[str, str]) -> bool:
        """True for a stateless (2026-07-28) request; refuses what neither era allows."""
        meta = params.get("_meta")
        meta = meta if isinstance(meta, dict) else {}
        header = headers.get("mcp-protocol-version")
        declared = meta.get(META_VERSION)
        if declared is not None:
            if header is not None and header != declared:
                raise _Refusal(400, HEADER_MISMATCH, "MCP-Protocol-Version differs from _meta.")
            if declared not in SUPPORTED_VERSIONS:
                raise _Refusal(
                    400, UNSUPPORTED_VERSION, "Unsupported protocol version",
                    {"supported": list(SUPPORTED_VERSIONS), "requested": declared},
                )  # fmt: skip
            if declared in MODERN_VERSIONS:
                if not isinstance(meta.get(META_CAPABILITIES), dict):
                    raise _Refusal(400, INVALID_PARAMS, f"_meta needs {META_CAPABILITIES}.")
                if headers.get("mcp-method", method) != method:
                    raise _Refusal(400, HEADER_MISMATCH, "Mcp-Method differs from the method.")
                name = params.get("name")
                if method == "tools/call" and headers.get("mcp-name", name) != name:
                    raise _Refusal(400, HEADER_MISMATCH, "Mcp-Name differs from the tool name.")
                return True
            return False
        if method == "initialize":
            return False  # the handshake itself names its version in the body
        version = header or HEADERLESS_VERSION
        if version not in HANDSHAKE_VERSIONS:
            raise _Refusal(
                400, UNSUPPORTED_VERSION, "Unsupported protocol version",
                {"supported": list(SUPPORTED_VERSIONS), "requested": version},
            )  # fmt: skip
        return False

    def _dispatch(
        self, method: str, params: dict[str, Any], modern: bool, client: str
    ) -> dict[str, Any]:
        capabilities = {"tools": {"listChanged": False}}
        if method == "server/discover":
            return {
                "supportedVersions": list(SUPPORTED_VERSIONS),
                "capabilities": capabilities,
                "instructions": self.instructions,
                "ttlMs": 3_600_000,
                "cacheScope": "public",
            }
        if method == "initialize" and not modern:
            asked = params.get("protocolVersion")
            agreed = asked if asked in HANDSHAKE_VERSIONS else LATEST_HANDSHAKE
            return {
                "protocolVersion": agreed,
                "capabilities": capabilities,
                "serverInfo": self._info,
                "instructions": self.instructions,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [self.tool]}
        if method == "tools/call":
            name = params.get("name")
            if name != TOOL_NAME:
                raise _Refusal(200, INVALID_PARAMS, f"Unknown tool: {name}")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                return _tool_error("arguments must be an object.")
            if not self._allow(client):
                return _tool_error("Too many requests from here. Wait a few minutes and retry.")
            return self._prepare(arguments)
        raise _Refusal(200, METHOD_NOT_FOUND, f"Method not found: {method}")

    def _prepare(self, arguments: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(arguments) - set(ARGUMENTS))
        if unknown:
            return _tool_error(
                f"Unknown arguments: {', '.join(unknown)}. Use {', '.join(ARGUMENTS)}."
            )
        values: dict[str, str] = {}
        for key in ("title", "web_address", "text", "message", "due_date"):
            value = arguments.get(key, "")
            if not isinstance(value, str):
                return _tool_error(f"{key} must be a string.")
            values[key] = value
        reviewers = arguments.get("reviewers", [])
        if isinstance(reviewers, str):
            reviewers = [reviewers]  # "a@x.fi, b@x.fi" is split by the address parser
        if not isinstance(reviewers, list) or not all(isinstance(r, str) for r in reviewers):
            return _tool_error("reviewers must be a list of email addresses.")
        try:
            token, prepared = self._prepared.prepare(
                title=values["title"], web_address=values["web_address"], text=values["text"],
                reviewers=reviewers, message=values["message"], due=values["due_date"],
            )  # fmt: skip
        except InvalidPreparedRequest as problem:
            return _tool_error(str(problem))
        url = f"{self._origin}/prepared/{token}"
        expires = prepared.expires_at.isoformat()
        summary = (
            f"Prepared. Nothing has been sent yet. Give the person this link: {url} . They open "
            f"it, sign in, check the request and send it. The link works until "
            f"{prepared.expires_at:%Y-%m-%d}."
        )
        return {
            "content": [{"type": "text", "text": summary}],
            "structuredContent": {"open_url": url, "expires_at": expires, "sent": False},
            "isError": False,
        }


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _error(
    status: int, request_id: object, code: int, message: str, data: object = None
) -> McpReply:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return McpReply(status, {"jsonrpc": "2.0", "id": request_id, "error": error})
