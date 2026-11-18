"""Reviewing a web page through the web layer (ADR 0022): the live check, Request a review,
calls that take web pages, and comments on the whole work."""

from __future__ import annotations

import re

from previewit.application.web_pages import PageCheck
from tests.integration.test_calls_web import create_call
from tests.integration.test_quick_review_web import NEW, mails_to, organizer, send
from tests.integration.test_reviews_web import Setup
from tests.integration.test_tenancy_web import Course, post
from tests.integration.web_fakes import csrf_token, make_harness
from tests.unit.test_webpage_plugin import ESSAY


def check(client, address: str):
    return post(client, "/pages/check", {"web_address": address}, page=NEW)


# -- the live check --------------------------------------------------------------------------


def test_the_form_checks_the_page_while_it_is_typed():
    h, client = organizer()
    form = client.get(NEW).text
    assert 'name="web_address"' in form and 'hx-post="/pages/check"' in form
    found = check(client, "example.org/essay")
    assert found.status_code == 200 and "Previewit can reach this page." in found.text
    assert "On testing &amp; &#34;trust&#34;" in found.text and "Sam&#39;s notes" in found.text
    h.pages.pages["https://example.org/private"] = "The page asks for a login."
    refused = check(client, "https://example.org/private")
    assert refused.status_code == 200 and 'role="alert">The page asks for a login.' in refused.text
    inside = check(client, "http://192.168.0.1/admin")
    assert "not on the public internet" in inside.text
    assert check(client, "   ").text.strip() == ""


def test_a_note_from_the_check_is_shown():
    h, client = organizer()
    shy = PageCheck("https://shy.example/", "https://shy.example/", "", "", "shy.example", "",
                    note="The site did not let Previewit look at the page.")  # fmt: skip
    h.pages.pages[shy.address] = shy
    assert "did not let Previewit look" in check(client, "shy.example").text


def test_only_people_signed_in_make_previewit_fetch_pages():
    h = make_harness()
    stranger = h.new_client()
    token = csrf_token(stranger, "/login")
    r = stranger.post("/pages/check", data={"csrf": token, "web_address": ESSAY.address})
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert h.pages.checked == []


def test_checking_many_pages_quickly_is_slowed_down():
    h, client = organizer()
    for _ in range(30):
        check(client, ESSAY.address)
    assert "Wait a minute" in check(client, ESSAY.address).text
    assert len(h.pages.checked) == 30


# -- Request a review of a web page -----------------------------------------------------------


def test_a_web_page_goes_to_reviewers_and_they_comment_on_the_whole_page():
    h, client = organizer()
    r = send(client, {"title": "", "text": "", "web_address": "example.org/essay",
                      "emails": "rita@x.fi", "send_emails": "on"})  # fmt: skip
    assert r.status_code == 200 and "On testing &amp; &#34;trust&#34;" in r.text

    link = re.search(r"/i/[A-Za-z0-9_-]+", mails_to(h, "rita@x.fi")[0][2]).group(0)  # type: ignore[union-attr]
    reviewer = h.new_client()
    start = post(reviewer, f"{link}/guest", {"name": "Rita"}, page=link)
    assert start.status_code == 303
    mine = reviewer.get(start.headers["location"]).text
    task = re.search(r'href="(/tasks/\w+)"', mine).group(1)  # type: ignore[union-attr]
    page = reviewer.get(task).text
    assert 'href="https://example.org/essay" target="_blank"' in page
    assert "Your comment is about the whole work." in page and "data-annotatable" not in page

    said = post(reviewer, f"{task}/annotations", {"body": "Convincing."}, page=task)
    assert said.status_code == 303
    page = reviewer.get(task).text
    assert "About the whole work" in page and "Convincing." in page
    assert "Thank you for reviewing" in page  # a guest is invited to join once they commented


def test_one_thing_to_review_at_a_time():
    _, client = organizer()
    both = send(client, {"web_address": ESSAY.address, "text": "Also this", "emails": "a@x.fi"})
    assert both.status_code == 400 and "Give one thing to review" in both.text
    assert 'value="https://example.org/essay"' in both.text  # what was typed stays


def test_a_page_reviewers_could_not_open_is_explained_on_the_form():
    h, client = organizer()
    h.pages.pages["https://example.org/private"] = "The page asks for a login."
    r = send(client, {"text": "", "web_address": "https://example.org/private", "emails": "a@x.fi"})
    assert r.status_code == 400 and "The page asks for a login." in r.text


# -- calls that take web pages, and comments on any work --------------------------------------


def test_a_call_can_take_web_pages():
    c = Course()
    sam = c.join_student()
    call = create_call(c, "Portfolio", kind="webpage")
    form = sam.get(call).text
    assert 'name="web_address"' in form and 'name="text"' not in form
    refused = post(sam, f"{call}/submissions", {"title": "Mine", "web_address": "10.0.0.1"},
                   page="/spaces")  # fmt: skip
    assert refused.status_code == 400 and "not on the public internet" in refused.text
    r = post(sam, f"{call}/submissions", {"title": "Mine", "web_address": ESSAY.address},
             page="/spaces")  # fmt: skip
    assert r.status_code == 303
    assert "Open the page" in sam.get(r.headers["location"]).text


def test_text_takes_pinned_comments_and_comments_on_the_whole_work():
    s = Setup()
    assert "data-annotatable" in s.page and "About the whole work instead" in s.page
    data = {"quote": "", "start": "", "end": "", "body": "Good overall"}
    assert post(s.sue, f"{s.task}/annotations", data, page=s.task).status_code == 303
    page = s.sue.get(s.task).text
    assert "About the whole work</small>" in page and "Good overall" in page
