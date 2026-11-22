"""An author asks for reviews and hides her name from the reviewers too (ADR 0029): the
invitation, the reviewer's pages and the work itself never name her."""

import pytest
from playwright.sync_api import Browser, Page, expect
from tests.acceptance.test_request_a_review import RequestReviewPage, invitation_link, unique

pytestmark = pytest.mark.acceptance


def test_an_author_hides_her_name_and_the_reviewer_never_sees_it(
    page: Page, browser: Browser, base_url: str, outbox
):
    maya, ana = unique("maya"), unique("ana")
    request = RequestReviewPage(page, base_url)
    request.sign_up_from_the_home_page("Maya Maker", maya)
    request.confirm_email(outbox, maya)

    request.title("My thesis chapter")
    page.get_by_label("or paste the text").fill("A chapter about kale.")
    request.type_reviewers(ana)
    expect(page.get_by_label("Reviewers see my name")).to_be_checked()
    page.get_by_label("Hide my name from the reviewers too").check()
    request.send()
    expect(page.get_by_role("heading", name="Sent!")).to_be_visible()

    link = invitation_link(outbox, ana)
    mail = next(b for to, _, b in reversed(outbox.sent) if to == ana)
    assert "Maya" not in mail and "An author invited you" in mail

    reviewer_ctx = browser.new_context()
    try:
        reviewer = reviewer_ctx.new_page()
        reviewer.goto(link)
        expect(reviewer.get_by_text("An author invited you to review")).to_be_visible()
        expect(reviewer.locator("main")).not_to_contain_text("Maya")
        reviewer.get_by_label("Your name").fill("Ana Reader")
        reviewer.get_by_role("button", name="Start reviewing").click()
        reviewer.locator("li.card a").first.click()
        expect(reviewer.locator(".artifact")).to_contain_text("A chapter about kale.")
        expect(reviewer.locator("main")).to_contain_text("By Anonymous author")
        expect(reviewer.locator("main")).not_to_contain_text("Maya")
        reviewer.get_by_role("link", name="Spaces").first.click()
        expect(reviewer.locator("main")).to_contain_text("My thesis chapter")
        expect(reviewer.locator("main")).not_to_contain_text("Maya")
    finally:
        reviewer_ctx.close()
