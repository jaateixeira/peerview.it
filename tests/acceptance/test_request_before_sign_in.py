"""Fill in Request a review before signing in (ADR 0024): the form and its file wait while the
visitor creates an account, then go out."""

import pytest
from playwright.sync_api import Page, expect
from tests.acceptance.test_calls import PASSWORD
from tests.acceptance.test_request_a_review import PDF, RequestReviewPage, unique

pytestmark = pytest.mark.acceptance


def test_a_visitor_fills_it_in_signs_up_and_sends_it(page: Page, base_url: str):
    page.goto(base_url)
    page.get_by_role("link", name="Request a review").first.click()
    expect(page.get_by_role("heading", name="Get your work reviewed")).to_be_visible()
    expect(page.get_by_text("Fill it in now and sign in when you send it.")).to_be_visible()

    request = RequestReviewPage(page, base_url)
    request.title("My thesis chapter")
    request.attach("chapter.pdf", PDF, "application/pdf")
    reviewer = unique("ana")
    request.type_reviewers(reviewer)
    expect(page.get_by_text("1 reviewer ready")).to_be_visible()  # checked without an account
    page.get_by_label("A few words for the reviewers").fill("Is chapter 2 clear?")
    request.send()

    # the request is saved; she creates her account
    expect(page.get_by_text("Your review request is saved.")).to_be_visible()
    page.get_by_role("link", name="Create an account").click()
    expect(page.get_by_role("heading", name="Create your account")).to_be_visible()
    expect(page.get_by_text("Your review request is saved.")).to_be_visible()
    page.get_by_label("Name").fill("Maya Maker")
    page.get_by_label("Email").fill(unique("maya"))
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign up").click()

    # ...and finds it as she left it, file included
    expect(page.get_by_text("Here is your request as you left it.")).to_be_visible()
    expect(page.get_by_label("Title")).to_have_value("My thesis chapter")
    expect(page.get_by_text("Your file chapter.pdf is kept for you.")).to_be_visible()
    expect(page.get_by_label("Email addresses")).to_have_value(reviewer)
    expect(page.get_by_label("A few words for the reviewers")).to_have_value("Is chapter 2 clear?")
    request.send()
    expect(page.get_by_text("“My thesis chapter” is up for review")).to_be_visible()
    expect(page.locator("ul.reviewers li").filter(has_text=reviewer)).to_have_count(1)
