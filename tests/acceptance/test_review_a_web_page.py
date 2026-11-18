"""Review a web page (ADR 0022): give its address instead of a file; Previewit checks it can
reach the page, and reviewers open it and comment on the whole page."""

import pytest
from playwright.sync_api import Browser, Page, expect
from tests.acceptance.test_request_a_review import RequestReviewPage, unique

pytestmark = pytest.mark.acceptance


class WebAddress:
    """The address field of Request a review, with its live check."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.field = page.get_by_label("or the address of a web page")
        self.result = page.locator("#page-check")

    def type(self, address: str) -> None:
        self.field.fill(address)


def test_a_web_page_is_checked_sent_out_and_commented_on(page: Page, browser: Browser, base_url):
    request = RequestReviewPage(page, base_url)
    request.sign_up_from_the_home_page("Maya Maker", unique("maya"))
    address = WebAddress(page)

    # a page reviewers could not open is caught while typing
    address.type("https://example.org/private")
    expect(address.result).to_contain_text("The page asks for a login")
    address.type("192.168.1.10/admin")
    expect(address.result).to_contain_text("not on the public internet")

    # a public page is reached and previewed; its title becomes the review's title
    address.type("example.org/portfolio")
    expect(address.result).to_contain_text("Previewit can reach this page.")
    expect(address.result).to_contain_text("Maya's design portfolio")
    reviewer_email = unique("rita")
    request.type_reviewers(reviewer_email)
    page.get_by_label("Email the invitations for me").uncheck()
    request.send()
    expect(page.get_by_text("“Maya's design portfolio” is up for review")).to_be_visible()
    link = page.locator("input.link-box").first.input_value()

    # the reviewer opens the page from Previewit and comments on the whole of it
    context = browser.new_context()
    try:
        reviewer = context.new_page()
        reviewer.goto(link)
        reviewer.get_by_label("Your name").fill("Rita Reviewer")
        reviewer.get_by_role("button", name="Start reviewing").click()
        reviewer.locator("li.card a").first.click()
        expect(reviewer.get_by_role("heading", name="The work", exact=True)).to_be_visible()
        opener = reviewer.get_by_role("link", name="Open the page")
        expect(opener).to_have_attribute("href", "https://example.org/portfolio")
        expect(opener).to_have_attribute("target", "_blank")
        expect(reviewer.get_by_text("Your comment is about the whole work.")).to_be_visible()
        reviewer.get_by_label("Comment", exact=True).fill("Lead with the strongest project.")
        reviewer.get_by_role("button", name="Add comment").click()
        comments = reviewer.locator("#comments")
        expect(comments).to_contain_text("About the whole work")
        expect(comments).to_contain_text("Lead with the strongest project.")
        expect(reviewer.locator(".join-card")).to_contain_text("Thank you for reviewing")
    finally:
        context.close()
