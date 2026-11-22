"""The MCP endpoint over Streamable HTTP (ADR 0023): POST carries JSON-RPC, a browser gets a page
that explains how to connect, and nothing else is offered (no event stream, no sessions)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from peerview.adapters.mcp import INVALID_REQUEST, McpServer
from peerview.adapters.web.kit import WebKit

MAX_BODY = 256_000  # a 100 kB text, escaped, fits with room to spare


def _refused(status: int, message: str) -> JSONResponse:
    body = {"jsonrpc": "2.0", "id": None, "error": {"code": INVALID_REQUEST, "message": message}}
    return JSONResponse(body, status_code=status)


async def _body(request: Request) -> bytes | None:
    """The body, or None when it is larger than MAX_BODY (announced or not)."""
    try:
        if int(request.headers.get("content-length", "0")) > MAX_BODY:
            return None
    except ValueError:
        return None
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BODY:
            return None
    return bytes(data)


def build_mcp_router(*, server: McpServer, kit: WebKit) -> APIRouter:
    router = APIRouter()
    origin = kit.settings.origin

    @router.post("/mcp")
    async def mcp(request: Request) -> Response:
        sender = request.headers.get("origin")
        if sender is not None and sender.rstrip("/") != origin:  # against DNS rebinding
            return _refused(403, "Requests from other web sites are not allowed.")
        body = await _body(request)
        if body is None:
            return _refused(413, "The message is too large.")
        client = request.client.host if request.client else "unknown"
        reply = await run_in_threadpool(
            lambda: server.handle(body, headers=dict(request.headers), client=client)
        )
        if reply.body is None:
            return Response(status_code=202)
        return JSONResponse(reply.body, status_code=reply.status)

    @router.get("/mcp", response_model=None)
    async def mcp_page(request: Request) -> Response:
        accept = request.headers.get("accept", "")
        if "text/event-stream" in accept and "text/html" not in accept:
            return Response(status_code=405, headers={"Allow": "POST"})  # no event stream
        return kit.render(
            request,
            "mcp.html",
            {"page_title": "peerview.it for AI assistants", "endpoint": f"{origin}/mcp",
             "tool": server.tool},
        )  # fmt: skip

    @router.delete("/mcp")
    async def mcp_delete() -> Response:
        return Response(status_code=405, headers={"Allow": "POST"})  # there are no sessions

    return router
