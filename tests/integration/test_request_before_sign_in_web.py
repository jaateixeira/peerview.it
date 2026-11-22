"""Fill in Request a review before signing in (ADR 0024): the form waits, with its file, for an
hour while the visitor signs in or creates an account, then it is deleted."""

from __future__ import annotations

import time
from datetime import timedelta
from urllib.parse import unquote

from fastapi.testclient import TestClient

import peerview.adapters.web.app as web_app
from peerview.application.prepared_requests import token_hash
from tests.integration.test_quick_review_web import NEW, PDF
from tests.integration.test_tenancy_web import post, signup
from tests.integration.web_fakes import csrf_token, make_harness
from tests.unit.test_webpage_plugin import ESSAY


def send(client: TestClient, data: dict[str, str], files=None):
    return client.post("/review", data={"csrf": csrf_token(client, NEW), **data}, files=files)


def saved_link(response) -> str:
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    assert location.startswith("/login?next=%2Fprepared%2F"), location
    return unquote(location.split("next=", 1)[1])


def test_a_visitor_gets_the_form_with_a_way_to_sign_in():
    h = make_harness()
    visitor = h.new_client()
    page = visitor.get(NEW)
    assert page.status_code == 200 and "Get your work reviewed" in page.text
    assert 'href="/signup?next=%2Freview%2Fnew">Create an account' in page.text
    assert 'href="/login?next=%2Freview%2Fnew">Log in' in page.text
    assert 'hx-post="/pages/check"' not in page.text  # only accounts make peerview.it fetch pages
    assert "peerview.it checks it when you send it" in page.text
    checked = post(visitor, "/review/emails/check", {"emails": "ana@x.fi, nope"}, page=NEW)
    assert checked.status_code == 200 and "does not look like an email address" in checked.text


def test_a_visitors_form_and_file_wait_while_they_sign_up_and_then_go_out():
    h = make_harness()
    visitor = h.new_client()
    sent = send(
        visitor,
        {"title": "Chapter 2", "emails": "rita@x.fi", "cover_letter": "Be frank."},
        files={"file": ("chapter.pdf", PDF, "application/pdf")},
    )
    link = saved_link(sent)
    assert "Your review request is saved" in visitor.get(sent.headers["location"]).text

    signup(visitor, "vera@x.fi", "Vera Visitor", next_=link)
    form = visitor.get(link)
    assert form.status_code == 200 and "Here is your request as you left it" in form.text
    assert 'value="Chapter 2"' in form.text and "rita@x.fi" in form.text
    assert "Be frank." in form.text and "<strong>chapter.pdf</strong> is kept for you" in form.text

    token = link.rsplit("/", 1)[1]
    data = {"title": "Chapter 2", "emails": "rita@x.fi", "cover_letter": "Be frank.",
            "prepared": token}  # fmt: skip
    done = post(visitor, "/review", data, page=link)  # no new file: the kept one goes out
    assert done.status_code == 200 and "“Chapter 2” is up for review by 1" in done.text
    assert visitor.get(link).status_code == 404  # sent: gone, file and all
    assert h.prepared_repo.count() == 0


def test_a_new_file_replaces_the_kept_one():
    h = make_harness()
    visitor = h.new_client()
    link = saved_link(send(visitor, {"title": "Draft", "emails": "rita@x.fi"},
                           files={"file": ("old.pdf", PDF, "application/pdf")}))  # fmt: skip
    signup(visitor, "vera@x.fi", "Vera Visitor", next_=link)
    token = link.rsplit("/", 1)[1]
    r = visitor.post(
        "/review",
        data={"csrf": csrf_token(visitor, link), "title": "", "emails": "rita@x.fi",
              "prepared": token},
        files={"file": ("notes.txt", b"Plain notes", "text/plain")},
    )  # fmt: skip
    assert r.status_code == 200 and "“notes” is up for review" in r.text


def test_a_web_page_is_checked_once_the_visitor_has_signed_in():
    h = make_harness()
    visitor = h.new_client()
    link = saved_link(send(visitor, {"web_address": "example.org/essay", "emails": "a@x.fi"}))
    assert h.pages.checked == []  # nothing fetched for someone without an account
    signup(visitor, "vera@x.fi", "Vera Visitor", next_=link)
    form = visitor.get(link).text
    assert "peerview.it can reach this page." in form and ESSAY.address in h.pages.checked


def test_mistakes_are_shown_on_the_form_and_nothing_is_kept():
    h = make_harness()
    visitor = h.new_client()
    nothing = send(visitor, {"title": "x", "emails": "rita@x.fi"})
    assert nothing.status_code == 400 and "Choose a file, give the address" in nothing.text
    bad = send(visitor, {"text": "My essay", "emails": "rita@, bo@x.fi"})
    assert bad.status_code == 400 and "Fix or remove the addresses" in bad.text
    assert "My essay" in bad.text  # what was typed stays
    assert h.prepared_repo.count() == 0


def test_the_kept_form_is_gone_after_an_hour():
    h = make_harness()
    visitor = h.new_client()
    link = saved_link(send(visitor, {"text": "My essay", "emails": "rita@x.fi"},
                           files={"file": ("a.pdf", PDF, "application/pdf")}))  # fmt: skip
    h.clock.now += timedelta(hours=1)
    signup(visitor, "vera@x.fi", "Vera Visitor", next_=link)
    gone = visitor.get(link)
    assert gone.status_code == 404 and "no longer here" in gone.text


def test_expired_forms_and_files_are_deleted_while_the_site_runs(monkeypatch):
    monkeypatch.setattr(web_app, "CLEANUP_SECONDS", 0.05)
    h = make_harness()
    with TestClient(h.app, base_url=h.base_url, follow_redirects=False) as running:
        link = saved_link(send(running, {"text": "Mine", "emails": "rita@x.fi"},
                               files={"file": ("a.pdf", PDF, "application/pdf")}))  # fmt: skip
        token = link.rsplit("/", 1)[1]
        assert h.prepared_repo.get(token_hash(token)) is not None
        h.clock.now += timedelta(hours=1, seconds=1)
        for _ in range(100):
            if h.prepared_repo.count() == 0:
                break
            time.sleep(0.02)
        assert h.prepared_repo.count() == 0


def test_many_saved_forms_from_one_place_are_slowed_down():
    h = make_harness()
    visitor = h.new_client()
    for _ in range(10):
        assert send(visitor, {"text": "x", "emails": "rita@x.fi"}).status_code == 303
    slowed = send(visitor, {"text": "x", "emails": "rita@x.fi"})
    assert slowed.status_code == 429 and "Wait a few minutes" in slowed.text


def test_a_guest_reviewer_still_joins_first():
    from tests.integration.test_invitations_web import course_with_round, invite, link_in

    c, call, sub = course_with_round()
    link = link_in(invite(c, call, work=(sub,))[0].text)
    guest = c.h.new_client()
    post(guest, f"{link}/guest", {"name": "G"}, page=link)
    assert guest.get(NEW).headers["location"] == "/account/new"


def test_the_whole_visitor_round_trip_works_on_an_https_site():
    """As on peerview.it: https, secure cookies, and the browser's Origin on every form."""
    h = make_harness(base_url="https://peerview.it")
    visitor = h.new_client()
    browser = {"Origin": "https://peerview.it"}
    token = csrf_token(visitor, NEW)
    checked = visitor.post("/review/emails/check", data={"csrf": token, "emails": "rita@x.fi"},
                           headers=browser)  # fmt: skip
    assert checked.status_code == 200
    sent = visitor.post(
        "/review",
        data={"csrf": token, "title": "Chapter 2", "emails": "rita@x.fi"},
        files={"file": ("chapter.pdf", PDF, "application/pdf")},
        headers=browser,
    )
    link = saved_link(sent)
    signup_page = visitor.get(f"/signup?next={link}")
    assert "Your review request is saved" in signup_page.text
    joined = visitor.post(
        "/signup",
        data={"csrf": csrf_token(visitor, "/signup"), "email": "vera@x.fi", "name": "Vera",
              "password": "correct horse battery", "next": link},
        headers=browser,
    )  # fmt: skip
    assert joined.status_code == 303 and joined.headers["location"] == link
    form = visitor.get(link)
    assert "Here is your request as you left it" in form.text
    done = visitor.post(
        "/review",
        data={"csrf": csrf_token(visitor, link), "title": "Chapter 2", "emails": "rita@x.fi",
              "prepared": link.rsplit("/", 1)[1]},
        headers=browser,
    )  # fmt: skip
    assert done.status_code == 200 and "“Chapter 2” is up for review" in done.text
