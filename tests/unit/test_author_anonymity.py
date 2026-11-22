"""Authors choose anonymity when they ask for reviews themselves (ADR 0029).

Who organizes a request is often its author. Then peerview.it treats them as the author for
their own work (conflict of interest) and, when the request hides authors, never names them
to the reviewers it invites."""

from __future__ import annotations

import pytest

from peerview.application.artifacts import Upload
from peerview.application.quick_review import AUTHOR_ANONYMITY, InvalidReviewRequest
from peerview.application.tenancy import NotFound
from peerview.domain.identity import UserId
from peerview.domain.rounds import DEFAULT_ANONYMITY
from tests.unit.test_calls_service import SAM, SUE, TINA
from tests.unit.test_feedback_service import FeedbackWorld
from tests.unit.test_quick_review_service import ANA, QUINN, QuickWorld

# -- choosing it in Request a review ----------------------------------------------------------


def test_the_author_chooses_one_side_or_both_sides_hidden() -> None:
    assert AUTHOR_ANONYMITY == ("reviewers_hidden", "double_anonymous")
    w = QuickWorld()
    usual = w.q.request_review(QUINN, w.request(send_emails=False))
    both = w.q.request_review(QUINN, w.request(send_emails=False, anonymity_key="double_anonymous"))
    keys = [w.rr.rounds(QUINN, done.call_id)[0].round.anonymity_key for done in (usual, both)]
    assert keys == [DEFAULT_ANONYMITY, "double_anonymous"]
    for other in ("open", "authors_hidden", "nonsense"):
        with pytest.raises(InvalidReviewRequest):
            w.q.request_review(QUINN, w.request(send_emails=False, anonymity_key=other))


def test_when_both_sides_are_hidden_the_invitation_does_not_name_the_author() -> None:
    w = QuickWorld()
    done = w.q.request_review(
        QUINN,
        w.request(anonymity_key="double_anonymous", reviewers=(ANA,), cover_letter="Thanks!"),
    )
    [(to, subject, body)] = w.mail.sent
    assert to == "ana@x.fi" and "My thesis" in subject
    assert "Quinn" not in subject + body and "An author" in body and "Thanks!" in body
    preview = w.iv.preview(done.invites[0].token)
    assert preview is not None
    assert preview.invited_by == "An author" and preview.organization_name == ""


def test_when_only_reviewers_are_hidden_the_invitation_names_the_author() -> None:
    w = QuickWorld()
    done = w.q.request_review(QUINN, w.request(reviewers=(ANA,)))
    [(_to, _subject, body)] = w.mail.sent
    assert "Quinn invited you" in body
    preview = w.iv.preview(done.invites[0].token)
    assert preview is not None and preview.invited_by == "Quinn"


def test_an_organizer_who_is_not_an_author_is_named_even_when_authors_are_hidden() -> None:
    """A teacher's double-anonymous round: reviewers may know who invites them."""
    w = QuickWorld()
    r = w.round(anonymity_key="double_anonymous")
    _, token = w.iv.invite(TINA, r.id, "rita@x.fi", [w.work_by[SAM].id])
    w.iv.send(TINA, r.id, token, "")
    assert "Tina invited you" in w.mail.sent[-1][2]


# -- the author of the work, even when they organize ------------------------------------------


@pytest.fixture
def fw() -> FeedbackWorld:
    """Tina organizes and also submits work of her own; Sue reviews it."""
    w = FeedbackWorld()
    w.subs[TINA] = w.c.submit(TINA, w.call.id, title="Tina essay", upload=Upload(text="Mine"))
    return w


def test_an_organizer_reads_reviews_of_her_own_work_as_its_author(fw: FeedbackWorld) -> None:
    r = fw.new_round()  # reviewers hidden from authors
    sue_task, pat_task = fw.assign(r, TINA, SUE, UserId("pat"))
    fw.hand_in(SUE, sue_task, "3", "Good")
    mine = fw.fb.feedback(TINA, fw.subs[TINA].id)
    assert not mine.organizer  # no early look at reviews of her own work
    assert mine.rounds[0].reviews == []
    fw.hand_in(UserId("pat"), pat_task)
    labels = [rv.reviewer_label for rv in fw.fb.feedback(TINA, fw.subs[TINA].id).rounds[0].reviews]
    assert labels == ["Reviewer A", "Reviewer B"]


def test_an_organizer_cannot_open_the_reviews_of_her_own_work(fw: FeedbackWorld) -> None:
    r = fw.new_round()
    (task,) = fw.assign(r, TINA, SUE)
    with pytest.raises(NotFound):
        fw.rv.workspace(TINA, task.id)
    (other,) = fw.assign(r, UserId("sam"), SUE)
    assert fw.rv.workspace(TINA, other.id).task.id == other.id  # other people's work: yes


def test_the_round_page_hides_who_reviews_the_organizers_own_work(fw: FeedbackWorld) -> None:
    r = fw.new_round()
    fw.assign(r, TINA, SUE)
    fw.assign(r, UserId("sam"), SUE)
    rows = {t.submission_title: t for t in fw.rr.round_view(TINA, r.id).tasks}
    assert rows["Tina essay"].reviewer_label == "Reviewer A" and rows["Tina essay"].own_work
    assert rows["sam essay"].reviewer_label == "Sue" and not rows["sam essay"].own_work


def test_an_open_round_shows_the_organizer_who_reviews_her_work(fw: FeedbackWorld) -> None:
    r = fw.new_round(anonymity_key="open")
    fw.assign(r, TINA, SUE)
    [row] = [t for t in fw.rr.round_view(TINA, r.id).tasks if t.own_work]
    assert row.reviewer_label == "Sue"


# -- spaces whose rounds hide people ----------------------------------------------------------


def test_spaces_with_a_round_that_hides_people_are_anonymous(fw: FeedbackWorld) -> None:
    assert fw.rr.anonymous_spaces([fw.s.id]) == set()
    fw.new_round()  # reviewers hidden from authors only: members may still be listed
    assert fw.rr.anonymous_spaces([fw.s.id]) == set()
    fw.new_round(anonymity_key="double_anonymous")
    assert fw.rr.anonymous_spaces([fw.s.id]) == {fw.s.id}


def test_a_reviewer_of_an_author_run_request_is_in_an_anonymous_space() -> None:
    w = QuickWorld()
    done = w.q.request_review(
        QUINN,
        w.request(send_emails=False, anonymity_key="double_anonymous", reviewers=(ANA,)),
    )
    assert w.rr.anonymous_spaces([done.space_id]) == {done.space_id}
