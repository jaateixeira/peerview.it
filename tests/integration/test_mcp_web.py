"""The MCP service (ADR 0023): AI assistants prepare a review request; the person sends it.

Both protocol eras are covered: the stateless one (2026-07-28: every request carries its
version and capabilities in _meta, server/discover instead of a handshake) and the earlier one
(initialize, then requests with the MCP-Protocol-Version header).
"""

from __future__ import annotations

import json
import re

import pytest

from peerview.adapters.mcp import TOOL_NAME
from tests.integration.test_quick_review_web import NEW, mails_to, organizer
from tests.integration.test_tenancy_web import post
from tests.integration.web_fakes import Harness, make_harness

MODERN = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": MODERN,
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "test-client", "version": "1"},
}


def rpc(
    h: Harness,
    method: str,
    params: dict | None = None,
    *,
    id_: int | None = 1,
    version: str | None = MODERN,
    headers: dict | None = None,
    modern: bool = True,
):
    message: dict = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        message["id"] = id_
    body = dict(params or {})
    if modern:
        body["_meta"] = {**META, **body.get("_meta", {})}
    if body:
        message["params"] = body
    sent = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if version:
        sent["MCP-Protocol-Version"] = version
    if modern:
        sent["Mcp-Method"] = method
        if method == "tools/call":
            sent["Mcp-Name"] = str(body.get("name", ""))
    sent.update(headers or {})
    return h.client.post("/mcp", content=json.dumps(message), headers=sent)


def call(h: Harness, arguments: dict, **kw):
    return rpc(h, "tools/call", {"name": TOOL_NAME, "arguments": arguments}, **kw)


@pytest.fixture
def h() -> Harness:
    return make_harness()


# -- the stateless era ---------------------------------------------------------------------------


def test_discover_says_what_peerview_is_and_how_to_use_it(h):
    r = rpc(h, "server/discover")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    result = r.json()["result"]
    assert result["resultType"] == "complete" and MODERN in result["supportedVersions"]
    assert "2025-06-18" in result["supportedVersions"]
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert "peer review" in result["instructions"] and "never say" in result["instructions"]
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "peerview"


def test_the_one_tool_is_described_with_its_inputs(h):
    [tool] = rpc(h, "tools/list").json()["result"]["tools"]
    assert tool["name"] == TOOL_NAME
    properties = tool["inputSchema"]["properties"]
    assert set(properties) == {"title", "web_address", "text", "reviewers", "message", "due_date"}
    assert tool["inputSchema"]["additionalProperties"] is False
    assert tool["annotations"]["destructiveHint"] is False
    assert "sends nothing" in tool["description"]
    assert set(tool["outputSchema"]["required"]) == {"open_url", "expires_at", "sent"}


def test_preparing_a_request_returns_a_link_and_sends_nothing(h):
    r = call(h, {"web_address": "example.org/essay", "reviewers": ["rita@x.fi"],
                 "message": "Please be frank.", "due_date": "2026-12-01"})  # fmt: skip
    result = r.json()["result"]
    assert r.status_code == 200 and result["isError"] is False
    found = result["structuredContent"]
    assert found["sent"] is False
    assert re.fullmatch(r"http://testserver/prepared/[A-Za-z0-9_-]{30,}", found["open_url"])
    assert found["open_url"] in result["content"][0]["text"]
    assert "Nothing has been sent" in result["content"][0]["text"]
    assert mails_to(h, "rita@x.fi") == [] and h.pages.checked == []  # no fetching, no mail


def test_a_request_that_cannot_be_prepared_comes_back_as_a_tool_error(h):
    for arguments, reason in (
        ({}, "Give either web_address"),
        ({"text": "x", "reviewers": ["nope"]}, "not an address"),
        ({"text": "x", "colour": "red"}, "Unknown arguments: colour"),
        ({"text": 5}, "text must be a string"),
        ({"text": "x", "reviewers": "rita@x.fi, bo@x.fi"}, None),  # a string list is accepted
    ):
        result = call(h, arguments).json()["result"]
        if reason is None:
            assert result["isError"] is False
        else:
            assert result["isError"] is True and reason in result["content"][0]["text"]


def test_an_unknown_tool_or_method_is_a_protocol_error(h):
    r = rpc(h, "tools/call", {"name": "delete_everything", "arguments": {}},
            headers={"Mcp-Name": "delete_everything"})  # fmt: skip
    assert r.json()["error"]["code"] == -32602 and "Unknown tool" in r.json()["error"]["message"]
    assert rpc(h, "resources/list").json()["error"]["code"] == -32601


def test_headers_must_agree_with_the_body(h):
    r = rpc(h, "tools/list", version="2025-06-18")
    assert r.status_code == 400 and r.json()["error"]["code"] == -32020
    r = rpc(h, "tools/list", headers={"Mcp-Method": "tools/call"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32020


def test_an_unknown_version_or_missing_capabilities_are_refused(h):
    r = rpc(h, "tools/list", {"_meta": {"io.modelcontextprotocol/protocolVersion": "2099-01-01"}},
            version="2099-01-01")  # fmt: skip
    error = r.json()["error"]
    assert r.status_code == 400 and error["code"] == -32022
    assert error["data"]["requested"] == "2099-01-01" and MODERN in error["data"]["supported"]
    meta = {"io.modelcontextprotocol/protocolVersion": MODERN}
    message = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {"_meta": meta}}
    r = h.client.post("/mcp", json=message, headers={"MCP-Protocol-Version": MODERN})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32602


# -- the earlier era: a handshake, then the version header --------------------------------------


def test_an_older_client_shakes_hands_and_then_works(h):
    hello = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "old"}}
    init = rpc(h, "initialize", hello, version=None, modern=False)
    result = init.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "peerview" and "tools" in result["capabilities"]
    assert "instructions" in result and "mcp-session-id" not in init.headers
    done = rpc(h, "notifications/initialized", id_=None, version="2025-06-18", modern=False)
    assert done.status_code == 202 and done.content == b""
    tools = rpc(h, "tools/list", version="2025-06-18", modern=False).json()["result"]["tools"]
    assert [t["name"] for t in tools] == [TOOL_NAME]
    r = call(h, {"text": "My essay."}, version="2025-06-18", modern=False)
    assert r.json()["result"]["isError"] is False
    assert rpc(h, "ping", version="2025-06-18", modern=False).json()["result"] == {}


def test_an_older_client_asking_for_an_unknown_version_gets_the_latest_we_know(h):
    hello = {"protocolVersion": "2024-01-01", "capabilities": {}, "clientInfo": {"name": "old"}}
    init = rpc(h, "initialize", hello, version=None, modern=False)
    assert init.json()["result"]["protocolVersion"] == "2025-11-25"
    r = rpc(h, "tools/list", version="2024-01-01", modern=False)
    assert r.status_code == 400


# -- HTTP manners ------------------------------------------------------------------------------


def test_bad_json_batches_and_strangers_are_turned_away(h):
    r = h.client.post("/mcp", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700
    r = h.client.post("/mcp", json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
    assert r.status_code == 400 and r.json()["error"]["code"] == -32600
    r = rpc(h, "tools/list", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403  # a web page elsewhere cannot drive the service
    assert rpc(h, "tools/list", headers={"Origin": "http://testserver"}).status_code == 200
    big = h.client.post(
        "/mcp", content=b"x" * 300_000, headers={"Content-Type": "application/json"}
    )
    assert big.status_code == 413


def test_a_browser_gets_a_page_and_other_clients_no_stream(h):
    page = h.client.get("/mcp", headers={"Accept": "text/html"})
    assert page.status_code == 200 and "http://testserver/mcp" in page.text
    assert "claude mcp add --transport http peerview http://testserver/mcp" in page.text
    stream = h.client.get("/mcp", headers={"Accept": "text/event-stream"})
    assert stream.status_code == 405 and stream.headers["allow"] == "POST"
    assert h.client.delete("/mcp").status_code == 405
    assert 'href="/mcp"' in h.client.get("/").text  # the footer points AI users to it


def test_preparing_many_requests_quickly_is_slowed_down(h):
    for _ in range(20):
        assert call(h, {"text": "x"}).json()["result"]["isError"] is False
    result = call(h, {"text": "x"}).json()["result"]
    assert result["isError"] is True and "Too many" in result["content"][0]["text"]


# -- the person opens the link, checks and sends ------------------------------------------------


def prepared_link(h: Harness, **arguments) -> str:
    result = call(h, arguments).json()["result"]
    return result["structuredContent"]["open_url"].removeprefix("http://testserver")


def test_the_person_signs_in_checks_the_prepared_request_and_sends_it():
    h, client = organizer()
    link = prepared_link(h, web_address="example.org/essay", reviewers=["rita@x.fi", "bo@x.fi"],
                         message="Please be frank.", due_date="2026-12-01")  # fmt: skip

    stranger = h.new_client()
    r = stranger.get(link)
    assert (
        r.status_code == 303 and r.headers["location"] == f"/login?next={link.replace('/', '%2F')}"
    )

    form = client.get(link)
    assert form.status_code == 200 and "An AI assistant prepared this request" in form.text
    assert 'value="https://example.org/essay"' in form.text
    assert "rita@x.fi\nbo@x.fi" in form.text and "Please be frank." in form.text
    assert 'value="2026-12-01"' in form.text
    assert "peerview.it can reach this page." in form.text  # checked when the page opened
    token = link.rsplit("/", 1)[1]
    assert f'name="prepared" value="{token}"' in form.text

    sent = post(client, "/review", {"title": "", "text": "", "web_address": "example.org/essay",
                "emails": "rita@x.fi\nbo@x.fi", "cover_letter": "Please be frank.",
                "send_emails": "on", "prepared": token}, page=link)  # fmt: skip
    assert sent.status_code == 200 and len(mails_to(h, "rita@x.fi")) == 1
    gone = client.get(link)
    assert gone.status_code == 404 and "no longer here" in gone.text


def test_a_mistake_on_the_form_keeps_the_prepared_link():
    h, client = organizer()
    link = prepared_link(h, text="My essay.")
    token = link.rsplit("/", 1)[1]
    r = post(client, "/review", {"title": "Essay", "text": "My essay.", "emails": "nope",
             "prepared": token}, page=link)  # fmt: skip
    assert r.status_code == 400 and f'name="prepared" value="{token}"' in r.text
    assert client.get(link).status_code == 200  # still there


def test_a_guest_reviewer_joins_before_sending_a_prepared_request():
    h, client = organizer()
    assert client.get(NEW).status_code == 200
    link = prepared_link(h, text="x")
    from tests.integration.test_invitations_web import course_with_round, invite, link_in

    c, round_call, sub = course_with_round()
    invite_link = link_in(invite(c, round_call, work=(sub,))[0].text)
    guest = c.h.new_client()
    post(guest, f"{invite_link}/guest", {"name": "G"}, page=invite_link)
    assert guest.get(link).headers["location"] == "/account/new"
