"""Feedback received on the web, and the leak tests for anonymous review (ADR 0028)."""

from __future__ import annotations

import pytest

from tests.integration.test_invitations_web import confirm_email
from tests.integration.test_reviews_web import Setup, find
from tests.integration.test_tenancy_web import post


def main(html: str) -> str:
    """The page without the site's header and footer."""
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def hand_in(s: Setup, clarity: str = "4", comment: str = "Strong opening") -> None:
    r = s.save(intent="submit", **{s.clarity: clarity, s.comment: comment})
    assert r.status_code == 303, r.text


def feedback_path(s: Setup) -> str:
    return f"{s.sub}/feedback"


def test_the_author_reads_the_review_under_a_pseudonym_and_hears_by_mail():
    s = Setup()
    confirm_email(s.c, s.sam, "sam@x.fi")
    waiting = s.sam.get(feedback_path(s))
    assert waiting.status_code == 200 and "0 of 1 review handed in" in waiting.text
    hand_in(s)
    page = main(s.sam.get(feedback_path(s)).text)
    assert "Reviewer A" in page and "Strong opening" in page and "4 (1 to 5)" in page
    assert "Sue" not in page
    [mail] = [m for m in s.c.h.outbox.sent if m[0] == "sam@x.fi" and "Reviews of" in m[1]]
    assert feedback_path(s) in mail[2] and "Sue" not in mail[1] + mail[2]
    listing = s.sam.get(f"{s.c.space}/feedback").text
    assert "On foxes" in listing and "1 of 1 to read" in listing


def test_double_anonymous_names_nobody_anywhere():
    """Plan scenario 3, on the pages: under double-anonymous no page, file or mail tells the
    reviewer who wrote the work, or the author who reviewed it."""
    s = Setup(group=True, anonymity="double_anonymous")
    confirm_email(s.c, s.sam, "sam@x.fi")
    for reviewer in (s.sue, s.pat):  # both members of the reviewing group
        for path in (s.task, f"{s.c.space}/reviews"):
            assert "Sam" not in main(reviewer.get(path).text), path
        work = reviewer.get(f"{s.task}/raw")
        assert work.headers["content-disposition"] == 'inline; filename="work"'
    assert "Anonymous author" in s.page
    hand_in(s)
    page = main(s.sam.get(feedback_path(s)).text)
    assert "Reviewer A" in page
    for name in ("Sue", "Pat", "Reviewers"):  # the people and their group's name
        assert name not in page
    for _to, subject, body in s.c.h.outbox.sent:
        if "Reviews of" in subject:
            assert "Sue" not in body and "Pat" not in body and "Reviewers" not in body


def test_the_organizer_sees_names_and_releases_a_manual_round():
    s = Setup(release="manual")
    hand_in(s)
    assert "Strong opening" not in s.sam.get(feedback_path(s)).text
    staff = main(s.c.teacher.get(feedback_path(s)).text)
    assert "Sue" in staff and "Strong opening" in staff
    rounds = s.c.teacher.get(f"{s.call}/rounds").text
    assert "When an organizer releases them" in rounds and "Show authors the reviews now" in rounds
    r = post(s.c.teacher, f"/rounds/{s.round}/release", page=f"{s.call}/rounds")
    assert r.status_code == 200 and "Authors can now read" in r.text
    assert "Strong opening" in s.sam.get(feedback_path(s)).text
    assert "Show authors the reviews now" not in s.c.teacher.get(f"{s.call}/rounds").text


@pytest.mark.parametrize("who", ["sue", "pat"])
def test_people_who_are_not_authors_get_nothing(who: str):
    s = Setup()
    hand_in(s)
    assert getattr(s, who).get(feedback_path(s)).status_code == 404
    r = post(getattr(s, who), f"/rounds/{s.round}/release", page="/spaces")
    assert r.status_code in (403, 404)


def test_the_submission_page_links_to_its_reviews_for_the_author_only():
    s = Setup()
    assert f'href="{feedback_path(s)}"' in s.sam.get(s.sub).text
    assert f'href="{feedback_path(s)}"' in s.c.teacher.get(s.sub).text


def test_the_round_form_keeps_its_release_rule():
    s = Setup(release="each")
    page = s.c.teacher.get(f"{s.call}/rounds").text
    assert find(r'<option value="(each)" selected', page) == "each"
