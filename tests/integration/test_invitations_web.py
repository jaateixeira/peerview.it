"""Processes 2 and 3 (ADR 0017) through the web layer: invite a reviewer, open the link."""

import re

from fastapi.testclient import TestClient

from peerview.domain.policy import DEFAULT_POLICY, Action, VerificationPolicy
from tests.integration.test_calls_web import create_call, submit_text
from tests.integration.test_rounds_web import new_round, page_of, round_id
from tests.integration.test_tenancy_web import PASSWORD, Course, post, signup
from tests.integration.web_fakes import csrf_token

EMAIL = "rita@x.fi"
REVIEWERS_VERIFIED = VerificationPolicy(frozenset({Action.REVIEW}))


def invite(c: Course, call: str, email=EMAIL, work: tuple[str, ...] = ()):
    rid = round_id(c, call)
    data = {"email": email, "submission_id": list(work)}
    return post(c.teacher, f"/rounds/{rid}/invitations", data, page=page_of(c, call)), rid


def link_in(text: str) -> str:
    match = re.search(r"/i/[A-Za-z0-9_-]+", text)
    assert match, text
    return match.group(0)


def confirm_email(c: Course, client: TestClient, email: str) -> None:
    mail = [m for m in c.h.outbox.sent if m[0] == email][-1]
    path = "/verify?token=" + re.search(r"/verify\?token=(\S+)", mail[2]).group(1)  # type: ignore[union-attr]
    token = csrf_token(client, path)
    done = client.post("/verify", data={"csrf": token, "token": path.split("token=")[1]})
    assert done.status_code == 200


def verified_visitor(c: Course, email=EMAIL, name="Rita Reviewer", next_="/spaces") -> TestClient:
    visitor = c.h.new_client()
    signup(visitor, email, name, next_=next_)
    confirm_email(c, visitor, email)
    return visitor


def course_with_round(policy: VerificationPolicy = DEFAULT_POLICY):
    c = Course(policy)
    sam = c.join_student("sam@x.fi", "Sam Student")
    call = create_call(c, "Essay")
    sub = submit_text(sam, call, "Essay by Sam", "Please review me").headers["location"]
    new_round(c, call)
    return c, call, sub.rsplit("/", 1)[1]


def test_the_organizer_invites_a_reviewer_and_the_link_is_shown_once():
    c, call, sub = course_with_round()
    r, _ = invite(c, call, work=(sub,))
    assert r.status_code == 200 and "shown only once" in r.text
    link = link_in(r.text)
    again = c.teacher.get(page_of(c, call)).text
    assert link not in again and "rita@x.fi: waiting, 1 to review" in again


def test_someone_with_an_account_logs_in_opens_the_link_and_reviews():
    c, call, sub = course_with_round()
    link = link_in(invite(c, call, work=(sub,))[0].text)
    visitor = c.h.new_client()
    page = visitor.get(link)
    assert page.status_code == 200 and "Tina Teacher invited you to review" in page.text
    assert "r***@x.fi" in page.text and "Sam" not in page.text  # no author names, no work
    assert "No account needed" in page.text and "Create an account" not in page.text
    visitor = verified_visitor(c, next_=link)
    r = post(visitor, link, page=link)
    assert r.status_code == 303 and r.headers["location"] == f"{c.space}/reviews"
    mine = visitor.get(f"{c.space}/reviews").text
    assert "Essay by Sam" in mine
    assert "rita@x.fi: accepted (Rita Reviewer)" in c.teacher.get(page_of(c, call)).text


def test_the_link_works_for_its_own_email_only():
    c, call, sub = course_with_round()
    link = link_in(invite(c, call, work=(sub,))[0].text)
    other = verified_visitor(c, email="mallory@x.fi", name="Mallory")
    assert "signed in with another address" in other.get(link).text
    r = post(other, link, page="/account")
    assert r.status_code == 403 and "r***@x.fi" in r.text
    assert other.get(f"{c.space}/reviews").status_code == 404  # not admitted


def test_when_the_operator_asks_reviewers_confirm_their_email_first():
    c, call, sub = course_with_round(REVIEWERS_VERIFIED)
    link = link_in(invite(c, call, work=(sub,))[0].text)
    visitor = c.h.new_client()
    page = visitor.get(link).text
    assert "Create an account" in page and "No account needed" not in page
    r = post(visitor, f"{link}/guest", {"name": "Rita"}, page="/login")
    assert r.status_code == 403 and "asks reviewers for an account" in r.text
    signup(visitor, EMAIL, "Rita Reviewer", next_=link)
    page = visitor.get(link).text
    assert "Confirm your email address first" in page and "Start reviewing" not in page
    r = post(visitor, link, page="/account")
    assert r.status_code == 403 and "Verify your email" in r.text


def test_by_default_an_unconfirmed_account_reviews_too():
    c, call, sub = course_with_round()
    link = link_in(invite(c, call, work=(sub,))[0].text)
    visitor = c.h.new_client()
    signup(visitor, EMAIL, "Rita Reviewer", next_=link)
    assert "Start reviewing" in visitor.get(link).text
    r = post(visitor, link, page=link)
    assert r.status_code == 303 and "Essay by Sam" in visitor.get(f"{c.space}/reviews").text


# -- reviewing without an account (ADR 0020) ---------------------------------------------------


def start_as_guest(c: Course, link: str, name: str = "Rita Reviewer"):
    guest = c.h.new_client()
    r = post(guest, f"{link}/guest", {"name": name}, page=link)
    return guest, r


def test_a_visitor_reviews_without_an_account_and_is_then_invited_to_join():
    c, call, sub = course_with_round()
    link = link_in(invite(c, call, work=(sub,))[0].text)
    guest, r = start_as_guest(c, link)
    assert r.status_code == 303 and r.headers["location"] == f"{c.space}/reviews"
    mine = guest.get(f"{c.space}/reviews").text
    assert "Essay by Sam" in mine and 'href="/account/new">Join peerview.it' in mine
    assert "rita@x.fi: accepted (Rita Reviewer)" in c.teacher.get(page_of(c, call)).text

    task = re.search(r'href="(/tasks/\w+)"', mine).group(1)  # type: ignore[union-attr]
    page = guest.get(task).text
    assert "Please review me" in page and "Thank you for reviewing" not in page
    start = "Please review me".index("review")
    data = {"quote": "review", "start": str(start), "end": str(start + 6), "body": "Clear ask"}
    assert post(guest, f"{task}/annotations", data, page=task).status_code == 303
    page = guest.get(task).text
    assert "Clear ask" in page and "Thank you for reviewing" in page  # done: invite to join

    join = guest.get("/account/new").text
    assert 'value="rita@x.fi"' in join and "readonly" in join
    weak = post(guest, "/account/new", {"name": "Rita", "password": "short"}, page="/account/new")
    assert weak.status_code == 400 and "at least 10 characters" in weak.text
    data = {"name": "Rita R", "password": PASSWORD}
    joined = post(guest, "/account/new", data, page="/account/new")
    assert joined.status_code == 303 and joined.headers["location"] == "/account"
    assert c.h.outbox.sent[-1][0] == "rita@x.fi"  # a link to confirm the address
    assert guest.get("/account/new").headers["location"] == "/account"
    assert "Clear ask" in guest.get(task).text  # the review stayed with her

    later = c.h.new_client()
    login = {"email": EMAIL, "password": PASSWORD, "next": "/spaces"}
    assert post(later, "/login", login, page="/login").status_code == 303
    assert "Essay by Sam" in later.get(f"{c.space}/reviews").text


def test_the_link_continues_the_same_guest_review():
    c, call, sub = course_with_round()
    link = link_in(invite(c, call, work=(sub,))[0].text)
    start_as_guest(c, link)
    other, again = start_as_guest(c, link, name="Someone")  # another device, later
    assert again.status_code == 303
    assert "Essay by Sam" in other.get(f"{c.space}/reviews").text
    assert "rita@x.fi: accepted (Rita Reviewer)" in c.teacher.get(page_of(c, call)).text


def test_an_address_with_an_account_is_asked_to_log_in():
    c, call, sub = course_with_round()
    verified_visitor(c)
    link = link_in(invite(c, call, work=(sub,))[0].text)
    _, r = start_as_guest(c, link)
    assert r.status_code == 409 and "already has a peerview.it account" in r.text
    assert "/login?next=" in r.text and "set-cookie" not in r.headers


def test_a_guest_joins_before_making_an_organization_or_requesting_reviews():
    c, call, sub = course_with_round()
    link = link_in(invite(c, call, work=(sub,))[0].text)
    guest, _ = start_as_guest(c, link)
    assert "You are reviewing as a guest" in guest.get("/spaces").text
    assert guest.get("/review/new").headers["location"] == "/account/new"
    assert guest.get("/account").headers["location"] == "/account/new"
    r = post(guest, "/orgs", {"name": "Rita's club", "preset": "general"}, page="/account/new")
    assert r.status_code == 403
    out = post(guest, "/logout", page="/account/new")  # a guest on a shared computer
    assert out.status_code == 303 and guest.get("/account/new").status_code in (303, 401)
    _, back = start_as_guest(c, link)  # the link brings the reviews back
    assert back.status_code == 303


def test_a_revoked_or_unknown_link_is_not_valid():
    c, call, sub = course_with_round()
    r, rid = invite(c, call, work=(sub,))
    link = link_in(r.text)
    iid = re.search(rf"/rounds/{rid}/invitations/(\w+)/revoke", r.text).group(1)  # type: ignore[union-attr]
    done = post(c.teacher, f"/rounds/{rid}/invitations/{iid}/revoke", page=page_of(c, call))
    assert done.status_code == 303
    anon = c.h.new_client()
    assert anon.get(link).status_code == 404
    assert anon.get("/i/nonsense").status_code == 404
    assert "revoked" in c.teacher.get(page_of(c, call)).text


def test_students_cannot_invite_and_bad_input_is_reported():
    c, call, _ = course_with_round()
    sam = c.join_student("sue@x.fi", "Sue Student")
    rid = round_id(c, call)
    forbidden = post(sam, f"/rounds/{rid}/invitations", {"email": EMAIL})
    assert forbidden.status_code in (403, 404)
    bad = invite(c, call, email="not an email")[0]
    assert bad.status_code == 400 and "email address" in bad.text
    assert invite(c, call)[0].status_code == 200
    twice = invite(c, call)[0]
    assert twice.status_code == 400 and "already has an invitation" in twice.text


def test_invitation_pages_keep_the_token_out_of_referrers():
    c, call, _ = course_with_round()
    link = link_in(invite(c, call)[0].text)
    assert c.h.new_client().get(link).headers["referrer-policy"] == "same-origin"


# --- peerview.it sends the invitation: generate the link, ask, then ask for a cover letter -------


def send(c: Course, rid: str, fresh_page: str, letter: str = "Please be kind."):
    token = re.search(r"/i/([A-Za-z0-9_-]+)", fresh_page).group(1)  # type: ignore[union-attr]
    data = {"token": token, "email": EMAIL, "cover_letter": letter}
    return post(c.teacher, f"/rounds/{rid}/invitations/send", data, page="/spaces"), token


def test_the_organizer_is_asked_whether_peerview_should_send_it_and_for_a_cover_letter():
    c, call, sub = course_with_round()
    created, _ = invite(c, call, work=(sub,))
    assert "Have peerview.it email it to rita@x.fi" in created.text
    assert 'name="cover_letter"' in created.text and "send it yourself" in created.text
    assert c.h.outbox.sent[-1][0] != EMAIL  # nothing was sent yet


def test_peerview_mails_the_invitation_with_the_cover_letter():
    c, call, sub = course_with_round()
    confirm_email(c, c.teacher, "tina@x.fi")
    created, rid = invite(c, call, work=(sub,))
    r, token = send(c, rid, created.text, "Dear Rita, your eyes would help.")
    assert r.status_code == 200 and "Invitation sent to rita@x.fi." in r.text
    to, subject, body = c.h.outbox.sent[-1]
    assert to == EMAIL and "Essay" in subject
    assert "Dear Rita, your eyes would help." in body and f"/i/{token}" in body
    assert "rita@x.fi: waiting, 1 to review, emailed" in r.text
    assert token not in r.text  # the link is not shown again


def test_an_invitation_cannot_be_mailed_twice():
    c, call, _ = course_with_round()
    confirm_email(c, c.teacher, "tina@x.fi")
    created, rid = invite(c, call)
    send(c, rid, created.text)
    again, _ = send(c, rid, created.text)
    assert again.status_code == 400 and "already sent" in again.text
    assert len([m for m in c.h.outbox.sent if m[0] == EMAIL]) == 1


def test_the_organizer_must_have_a_verified_email_to_send():
    c, call, _ = course_with_round()
    created, rid = invite(c, call)
    r, _ = send(c, rid, created.text)
    assert r.status_code == 403 and not [m for m in c.h.outbox.sent if m[0] == EMAIL]


def test_when_the_mail_fails_the_link_is_still_there_to_copy():
    c, call, _ = course_with_round()
    confirm_email(c, c.teacher, "tina@x.fi")
    created, rid = invite(c, call)
    link = link_in(created.text)
    c.h.outbox.failing = True
    r, _ = send(c, rid, created.text)
    assert r.status_code == 502 and "could not be sent" in r.text and link in r.text
    c.h.outbox.failing = False
    assert send(c, rid, created.text)[0].status_code == 200
