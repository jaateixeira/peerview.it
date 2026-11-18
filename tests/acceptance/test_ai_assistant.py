"""An AI assistant prepares a review request through the MCP service (ADR 0023); the person
opens the link, checks the filled-in form and sends it."""

import pytest
from playwright.sync_api import Page, expect
from tests.acceptance.test_calls import PASSWORD
from tests.acceptance.test_request_a_review import unique

pytestmark = pytest.mark.acceptance

META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "acceptance", "version": "1"},
}


class Assistant:
    """What an AI assistant does on the wire: one tool call to the MCP endpoint."""

    def __init__(self, page: Page, base_url: str) -> None:
        self.request, self.endpoint = page.request, f"{base_url}/mcp"

    def prepare(self, **arguments) -> dict:
        response = self.request.post(
            self.endpoint,
            data={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "prepare_review_request", "arguments": arguments, "_meta": META},
            },
            headers={
                "MCP-Protocol-Version": "2026-07-28",
                "Mcp-Method": "tools/call",
                "Mcp-Name": "prepare_review_request",
            },
        )
        assert response.status == 200
        return response.json()["result"]


def test_an_assistant_prepares_and_the_person_checks_and_sends(page: Page, base_url: str):
    reviewer = unique("bo")
    result = Assistant(page, base_url).prepare(
        web_address="https://example.org/portfolio",
        reviewers=[reviewer],
        message="Which project should go first?",
    )
    assert result["isError"] is False and result["structuredContent"]["sent"] is False
    link = result["structuredContent"]["open_url"]

    # the person opens the link, signs up, and lands on the filled-in form
    page.goto(link)
    page.get_by_role("link", name="Create an account").click()
    page.get_by_label("Name").fill("Maya Maker")
    page.get_by_label("Email").fill(unique("maya"))
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign up").click()
    expect(page.get_by_text("An AI assistant prepared this request for you.")).to_be_visible()
    expect(page.get_by_label("or the address of a web page")).to_have_value(
        "https://example.org/portfolio"
    )
    expect(page.locator("#page-check")).to_contain_text("Maya's design portfolio")
    expect(page.get_by_label("Email addresses")).to_have_value(reviewer)
    expect(page.get_by_label("A few words for the reviewers")).to_have_value(
        "Which project should go first?"
    )

    # nothing went out until she sends it
    page.get_by_label("Email the invitations for me").uncheck()
    page.get_by_role("button", name="Send it out").click()
    expect(page.get_by_text("“Maya's design portfolio” is up for review")).to_be_visible()

    # the link has done its job
    page.goto(link)
    expect(page.get_by_role("heading", name="This request is no longer here")).to_be_visible()


def test_a_person_can_read_how_to_connect_an_assistant(page: Page, base_url: str):
    page.goto(base_url)
    page.get_by_role("link", name="For AI assistants").click()
    expect(page.get_by_role("heading", name="Previewit for AI assistants")).to_be_visible()
    expect(
        page.get_by_text(f"claude mcp add --transport http previewit {base_url}/mcp")
    ).to_be_visible()
