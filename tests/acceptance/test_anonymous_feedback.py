"""Plan scenario 3: a member reviews a group's work under double-anonymous review, and no
identity shows on either side; the authors read the review once it is in (ADR 0028)."""

import uuid

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect
from tests.acceptance.test_calls import PASSWORD, TeacherPage
from tests.acceptance.test_rubrics import RubricsPage

pytestmark = pytest.mark.acceptance


def join(browser: Browser, link: str, name: str) -> tuple[BrowserContext, Page]:
    ctx = browser.new_context()
    student = ctx.new_page()
    student.goto(link)
    student.get_by_role("link", name="Create an account").click()
    student.get_by_label("Name").fill(name)
    student.get_by_label("Email").fill(f"{uuid.uuid4().hex[:8]}@example.org")
    student.get_by_label("Password").fill(PASSWORD)
    student.get_by_role("button", name="Sign up").click()
    student.get_by_role("button", name="Join").click()
    expect(student.get_by_role("heading", name="Software Engineering", level=1)).to_be_visible()
    return ctx, student


class SpacePage:
    """The organizer's course page: groups."""

    def __init__(self, page: Page) -> None:
        self.page = page

    def open(self) -> None:
        self.page.get_by_role("link", name="Spaces").first.click()
        self.page.get_by_role("link", name="Software Engineering").click()
        expect(self.page.get_by_role("heading", name="Create group")).to_be_visible()

    def make_group(self, name: str, *members: str) -> None:
        form = self.page.locator("form", has=self.page.get_by_role("heading", name="Create group"))
        form.get_by_label("Name").fill(name)
        form.get_by_role("button", name="Create group").click()
        expect(self.page.locator(".group")).to_contain_text(name)
        for member in members:
            self.page.get_by_label(f"Add to {name}").select_option(label=member)
            self.page.get_by_role("button", name="Add", exact=True).click()
            expect(self.page.locator(".group")).to_contain_text(member)


class AnonymousRoundPage:
    """The organizer's round setup with both sides hidden, and one reviewer added by hand."""

    def __init__(self, page: Page) -> None:
        self.page = page

    def create_double_anonymous(self) -> None:
        self.page.get_by_role("link", name="Review rounds").click()
        form = self.page.locator("form", has=self.page.get_by_role("heading", name="Add round 1"))
        form.get_by_label("Reviews each submission gets").fill("1")
        form.get_by_label("Allocation").select_option(value="manual")
        form.get_by_label("Identities").select_option(value="double_anonymous")
        form.get_by_label("Authors see the reviews").select_option(value="complete_or_due")
        form.get_by_role("button", name="Create round").click()
        expect(self.page.get_by_role("heading", name="Round 1")).to_be_visible()
        expect(self.page.locator("#round-1 > p").first).to_contain_text("Neither side sees")

    def add_reviewer(self, name: str) -> None:
        self.page.get_by_text("Add a reviewer by hand").click()
        self.page.locator("select[name=reviewer]").select_option(label=name)
        self.page.get_by_role("button", name="Add reviewer to round 1").click()
        expect(self.page.locator("table tbody tr")).to_have_count(1)


class FeedbackPage:
    """An author's Feedback received page and the reviews of one work."""

    def __init__(self, page: Page) -> None:
        self.page = page

    def open_work(self, title: str) -> None:
        self.page.get_by_role("link", name="Spaces").first.click()
        self.page.get_by_role("link", name="Software Engineering").click()
        self.page.get_by_role("link", name="Feedback received").click()
        self.page.get_by_role("link", name=title).click()
        expect(self.page.get_by_role("heading", name=f"Reviews of {title}")).to_be_visible()


def test_a_member_reviews_a_groups_work_and_no_name_shows_on_either_side(
    page: Page, browser: Browser, base_url: str
):
    teacher = TeacherPage(page, base_url)
    link = teacher.create_course()

    contexts: list[BrowserContext] = []
    try:
        for name in ("Sam", "Sue", "Pat"):
            ctx, _ = join(browser, link, name)
            contexts.append(ctx)
        sam, sue, pat = (ctx.pages[0] for ctx in contexts)

        space = SpacePage(page)
        space.open()
        space.make_group("Team Kale", "Sam", "Sue")

        # A group assignment with a rubric
        page.get_by_role("link", name="Assignments").click()
        page.get_by_label("Title").fill("Project plan")
        page.get_by_label("Kind of work").select_option("Text")
        page.get_by_label("Groups submit together").check()
        page.get_by_role("button", name="Create assignment").click()
        expect(page.get_by_role("heading", name="Project plan", level=1)).to_be_visible()
        rubrics = RubricsPage(page)
        rubrics.open_from_space()
        rubrics.create_from_template("Quick rubric", "quick-check")
        page.get_by_role("link", name="Software Engineering").click()
        page.get_by_role("link", name="Assignments").click()
        page.get_by_role("link", name="Project plan").click()
        page.get_by_label("Review rubric").select_option(label="Quick rubric")
        page.get_by_role("button", name="Use this rubric").click()

        # Sam hands in the group's work
        sam.get_by_role("link", name="Spaces").first.click()
        sam.get_by_role("link", name="Software Engineering").click()
        sam.get_by_role("link", name="Assignments").click()
        sam.get_by_role("link", name="Project plan").click()
        sam.get_by_label("Title").fill("Kale plan")
        sam.get_by_label("Your text").fill("We plan to grow kale.")
        sam.get_by_role("button", name="Submit").click()
        expect(sam.get_by_role("heading", name="Kale plan", level=1)).to_be_visible()

        page.reload()
        rounds = AnonymousRoundPage(page)
        rounds.create_double_anonymous()
        rounds.add_reviewer("Pat")

        # Pat reviews without learning who wrote it
        pat.get_by_role("link", name="Spaces").first.click()
        pat.get_by_role("link", name="Software Engineering").click()
        pat.get_by_role("link", name="My reviews").click()
        for name in ("Sam", "Sue", "Team Kale"):
            expect(pat.locator("main")).not_to_contain_text(name)
        pat.locator("li.card a").first.click()
        expect(pat.locator(".artifact")).to_contain_text("We plan to grow kale.")
        expect(pat.locator("main")).to_contain_text("By Anonymous author")
        for name in ("Sam", "Sue", "Team Kale"):
            expect(pat.locator("main")).not_to_contain_text(name)
        pat.get_by_label("Yes").check()
        pat.locator("fieldset", has_text="Overall score").locator("input").fill("4")
        pat.locator("fieldset", has_text="One thing").locator("textarea").fill("Well argued")
        pat.get_by_role("button", name="Submit review").click()
        expect(pat.get_by_text("Review submitted")).to_be_visible()

        # Sue, the other group member, reads it without learning who wrote it
        feedback = FeedbackPage(sue)
        feedback.open_work("Kale plan")
        expect(sue.locator("main")).to_contain_text("Reviewer A")
        expect(sue.locator("main")).to_contain_text("Well argued")
        expect(sue.locator("main")).not_to_contain_text("Pat")

        # The organizer sees who reviewed whom
        page.goto(sue.url)
        expect(page.locator("main")).to_contain_text("Pat")
    finally:
        for ctx in contexts:
            ctx.close()
