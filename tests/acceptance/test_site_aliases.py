"""One site, two addresses (ADR 0021): the second name leads to the first."""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.acceptance


def test_a_visitor_at_the_other_address_lands_on_the_main_one_and_can_sign_up(
    page: Page, base_url: str
):
    other = base_url.replace("127.0.0.1", "localhost")
    assert other != base_url
    page.goto(f"{other}/signup?next=/review/new")
    expect(page).to_have_url(f"{base_url}/signup?next=/review/new")
    expect(page.locator("footer")).to_contain_text(base_url.removeprefix("http://"))
    # Forms work, because the page now lives at the main address.
    page.get_by_label("Name").fill("Vera Visitor")
    page.get_by_label("Email").fill("vera.alias@example.org")
    page.get_by_label("Password").fill("correct horse battery staple")
    page.get_by_role("button", name="Sign up").click()
    expect(page.get_by_role("heading", name="Get your work reviewed")).to_be_visible()
