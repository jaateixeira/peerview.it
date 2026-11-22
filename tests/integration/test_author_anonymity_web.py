"""An author asks for reviews and chooses who sees whom (ADR 0029), through the web layer:
leak tests for the pages a reviewer and the author see."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from tests.integration.test_feedback_web import main
from tests.integration.test_invitations_web import link_in
from tests.integration.test_mcp_web import prepared_link
from tests.integration.test_quick_review_web import NEW, mails_to, organizer, send
from tests.integration.test_tenancy_web import post
from tests.integration.web_fakes import Harness

AUTHOR = ("Olga", "Organizer")  # the author's name, in two parts


def as_guest(h: Harness, link: str) -> TestClient:
    guest = h.new_client()
    r = post(guest, f"{link}/guest", {"name": "Rita Reviewer"}, page=link)
    assert r.status_code == 303, r.text
    return guest


def ask(anonymity: str) -> tuple[Harness, TestClient, str, str]:
    """Olga asks Rita for a review; returns the harness, Olga, the space and the invite link."""
    h, olga = organizer()
    r = send(olga, {"emails": "rita@x.fi", "send_emails": "on", "anonymity": anonymity})
    assert r.status_code == 200 and "Review requested" in r.text
    space = re.search(r'href="(/spaces/\w+)"', main(r.text)).group(1)  # type: ignore[union-attr]
    [(_to, _subject, body)] = mails_to(h, "rita@x.fi")
    return h, olga, space, link_in(body)


def task_of(reviewer: TestClient, space: str) -> str:
    mine = reviewer.get(f"{space}/reviews").text
    return re.search(r'href="(/tasks/\w+)"', mine).group(1)  # type: ignore[union-attr]


def test_the_form_offers_one_side_or_both_sides_hidden():
    _h, olga = organizer()
    page = olga.get(NEW).text
    assert 'value="reviewers_hidden" checked' in page and 'value="double_anonymous"' in page


def test_hiding_both_sides_keeps_the_author_out_of_everything_the_reviewer_sees():
    h, _olga, space, link = ask("double_anonymous")
    [(_to, subject, body)] = mails_to(h, "rita@x.fi")
    for part in AUTHOR:
        assert part not in subject + body
    invitation = main(h.new_client().get(link).text)
    assert "An author invited you" in invitation
    rita = as_guest(h, link)
    task = task_of(rita, space)
    paths = (space, "/spaces", f"{space}/reviews", task)
    pages = {path: main(rita.get(path).text) for path in paths}
    for path, page in pages.items():
        for part in AUTHOR:
            assert part not in page, path
    assert "By Anonymous author" in pages[task]
    assert "other members are not listed" in pages[space]


def test_by_default_the_reviewer_knows_whose_work_it_is():
    h, _olga, space, link = ask("reviewers_hidden")
    assert "Olga Organizer invited you" in mails_to(h, "rita@x.fi")[0][2]
    rita = as_guest(h, link)
    assert "By Olga Organizer" in rita.get(task_of(rita, space)).text
    assert "Olga Organizer" in main(rita.get(space).text)  # members are listed


def test_the_author_never_learns_which_reviewer_wrote_which_review():
    h, olga, space, link = ask("reviewers_hidden")
    rita = as_guest(h, link)
    task = task_of(rita, space)
    assert olga.get(task).status_code == 404  # her own work: she reads it as its author
    calls_page = olga.get(f"{space}/calls").text
    call = re.search(r'href="(/calls/\w+)"', calls_page).group(1)  # type: ignore[union-attr]
    table = main(olga.get(f"{call}/rounds").text)
    assert "Reviewer A" in table and f'href="{task}"' not in table


def test_an_assistant_can_prepare_a_double_anonymous_request():
    h, olga = organizer()
    link = prepared_link(h, text="My essay", reviewers=["rita@x.fi"], hide_author=True)
    form = olga.get(link).text
    assert 'value="double_anonymous" checked' in form
