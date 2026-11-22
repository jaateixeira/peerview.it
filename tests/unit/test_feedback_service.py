"""Authors read the reviews of their work once the round's rule releases them (ADR 0028)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from peerview.application.artifacts import Upload
from peerview.application.feedback import FeedbackService
from peerview.application.tenancy import Forbidden, NotFound
from peerview.domain.anonymity import ANONYMOUS_AUTHOR
from peerview.domain.identity import Email
from peerview.domain.party import GroupParty, UserParty
from tests.unit.test_calls_service import PAT, SAM, SUE, TINA
from tests.unit.test_invitations_service import Outbox
from tests.unit.test_reviews_service import ReviewWorld
from tests.unit.test_tenancy_service import AVA, BOB, ZED

BASE = "https://peerview.it"


class FeedbackWorld(ReviewWorld):
    """The review world plus the feedback service, wired as the app wires it."""

    def __init__(self, *args, broken_mail: bool = False, **kw):
        super().__init__(*args, **kw)
        for uid in (SAM, SUE, PAT):
            self.users.mark_email_verified(uid, Email(f"{uid}@x.fi"))
        self.outbox = Outbox(broken=broken_mail)
        self.fb = FeedbackService(
            self.rr._repo,
            self.review_repo,
            self.c._repo,
            self.rub._repo,
            self.t,
            self.t._repo,
            self.users,
            self.rv._criteria,
            self.outbox,
            BASE,
            self.clock,
        )
        self.rv.when_handed_in(self.fb.handed_in)

    def new_round(self, **kw):
        kw.setdefault("strategy_key", "manual")
        return self.round(**kw)

    def assign(self, round_, author, *reviewers):
        return [
            self.rr.add_task(TINA, round_.id, self.subs[author].id, UserParty(r)) for r in reviewers
        ]

    def hand_in(self, reviewer, task, clarity="4", note="Clear"):
        return self.rv.save(reviewer, task.id, self.answers(clarity, note), 0, submit=True)

    def sam_feedback(self, viewer=SAM):
        return self.fb.feedback(viewer, self.subs[SAM].id).rounds[0]

    def mails_to(self, address: str) -> list[tuple[str, str, str]]:
        return [m for m in self.outbox.sent if m[0] == address]


@pytest.fixture
def w() -> FeedbackWorld:
    return FeedbackWorld()


def test_by_default_authors_read_the_reviews_once_every_one_is_in(w: FeedbackWorld):
    r = w.new_round()
    sue_task, pat_task = w.assign(r, SAM, SUE, PAT)
    w.hand_in(SUE, sue_task, "2", "Too short")
    waiting = w.sam_feedback()
    assert (waiting.released, waiting.handed_in, waiting.expected) == (False, 1, 2)
    assert waiting.reviews == [] and not w.outbox.sent
    w.hand_in(PAT, pat_task, "5", "Lovely")
    ready = w.sam_feedback()
    assert ready.released and [rv.reviewer_label for rv in ready.reviews] == [
        "Reviewer A",
        "Reviewer B",
    ]
    answers = {(a.title, a.text) for rv in ready.reviews for a in rv.answers}
    assert {("Clarity", "2 (1 to 5)"), ("Comment", "Too short"), ("Comment", "Lovely")} <= answers
    [(_, subject, body)] = w.mails_to("sam@x.fi")
    assert '"sam essay"' in subject and f"{BASE}/submissions/{w.subs[SAM].id}/feedback" in body
    assert "Sue" not in body + subject and "Pat" not in body + subject


def test_the_due_time_releases_them_and_the_sweep_sends_one_notice(w: FeedbackWorld):
    r = w.new_round(closes_at=w.clock.now + timedelta(days=1))
    sue_task, _ = w.assign(r, SAM, SUE, PAT)
    w.hand_in(SUE, sue_task)
    assert not w.sam_feedback().released
    w.clock.now += timedelta(days=1)
    assert w.sam_feedback().released  # seen at once, before any sweep
    assert w.fb.send_due_notices() == 1 and w.fb.send_due_notices() == 0
    assert len(w.mails_to("sam@x.fi")) == 1
    stored = w.rr._repo.get_round(r.id)
    assert stored is not None and stored.released_at == r.closes_at


def test_a_submission_without_reviews_gets_no_notice_until_one_comes(w: FeedbackWorld):
    due = w.clock.now + timedelta(days=1)
    r = w.new_round(closes_at=due)
    (sue_task,) = w.assign(r, SAM, SUE)
    w.clock.now += timedelta(days=2)
    assert w.fb.send_due_notices() == 0  # the round is released, but there is nothing to read
    w.rr.update_round(
        TINA, r.id, per_submission=1, strategy_key="manual", anonymity_key=r.anonymity_key,
        opens_at=None, closes_at=w.clock.now + timedelta(days=1),
    )  # fmt: skip
    w.hand_in(SUE, sue_task)  # a late review, after the organizer moved the due time
    assert w.sam_feedback().released and len(w.mails_to("sam@x.fi")) == 1


def test_as_each_review_is_handed_in(w: FeedbackWorld):
    r = w.new_round(release_key="each")
    sue_task, _ = w.assign(r, SAM, SUE, PAT)
    w.hand_in(SUE, sue_task)
    shown = w.sam_feedback()
    assert shown.released and len(shown.reviews) == 1
    assert len(w.mails_to("sam@x.fi")) == 1


def test_only_an_organizer_releases_a_manual_round(w: FeedbackWorld):
    r = w.new_round(release_key="manual", closes_at=w.clock.now + timedelta(days=1))
    (sue_task,) = w.assign(r, SAM, SUE)
    w.hand_in(SUE, sue_task)
    w.clock.now += timedelta(days=2)
    assert w.fb.send_due_notices() == 0 and not w.sam_feedback().released
    for outsider in (SAM, AVA, BOB):
        with pytest.raises((Forbidden, NotFound)):
            w.fb.release(outsider, r.id)
    w.fb.release(TINA, r.id)
    assert w.sam_feedback().released and len(w.mails_to("sam@x.fi")) == 1
    w.fb.release(TINA, r.id)  # again: nothing new
    assert len(w.mails_to("sam@x.fi")) == 1


def test_drafts_never_reach_authors(w: FeedbackWorld):
    r = w.new_round(release_key="each")
    (sue_task,) = w.assign(r, SAM, SUE)
    w.rv.save(SUE, sue_task.id, w.answers(), 0)  # a draft
    w.fb.release(TINA, r.id)
    shown = w.sam_feedback()
    assert shown.released and shown.reviews == [] and shown.handed_in == 0
    assert not w.outbox.sent


def test_feedback_stays_released_when_an_organizer_adds_a_reviewer(w: FeedbackWorld):
    r = w.new_round()
    (sue_task,) = w.assign(r, SAM, SUE)
    w.hand_in(SUE, sue_task)
    w.assign(r, SAM, PAT)
    shown = w.sam_feedback()
    assert shown.released and (shown.handed_in, shown.expected) == (1, 2)


def test_only_authors_and_organizers_open_the_feedback(w: FeedbackWorld):
    r = w.new_round(release_key="each")
    (sue_task,) = w.assign(r, SAM, SUE)
    w.hand_in(SUE, sue_task)
    for outsider in (SUE, PAT, AVA, BOB, ZED):
        with pytest.raises(NotFound):
            w.fb.feedback(outsider, w.subs[SAM].id)
    staff = w.fb.feedback(TINA, w.subs[SAM].id)
    assert staff.organizer and staff.rounds[0].reviews[0].reviewer_label == "Sue"
    assert staff.author_name == "Sam"


def test_an_open_round_names_the_reviewers_to_authors(w: FeedbackWorld):
    r = w.new_round(release_key="each", anonymity_key="open")
    (sue_task,) = w.assign(r, SAM, SUE)
    w.hand_in(SUE, sue_task)
    assert w.sam_feedback().reviews[0].reviewer_label == "Sue"


def test_organizers_see_reviews_before_authors_do(w: FeedbackWorld):
    r = w.new_round()
    sue_task, _ = w.assign(r, SAM, SUE, PAT)
    w.hand_in(SUE, sue_task)
    staff = w.sam_feedback(viewer=TINA)
    assert not staff.released and [rv.reviewer_label for rv in staff.reviews] == ["Sue"]


def test_pinned_comments_come_with_the_review(w: FeedbackWorld):
    r = w.new_round(release_key="each")
    (sue_task,) = w.assign(r, SAM, SUE)
    w.rv.add_annotation(SUE, sue_task.id, {"quote": "ell", "start": "1", "end": "4"}, "Why?")
    w.rv.add_annotation(SUE, sue_task.id, {}, "Nice overall")
    w.rv.save(SUE, sue_task.id, w.answers(), 1, submit=True)
    notes = w.sam_feedback().reviews[0].notes
    assert [(n.quote, n.body) for n in notes] == [("ell", "Why?"), ("", "Nice overall")]


def test_every_member_of_an_author_group_reads_and_hears(w: FeedbackWorld):
    call, group = w.group_call()
    work = w.c.submit(SAM, call.id, title="Our project", upload=w_upload(), group_id=group.id)
    r = w.rr.create_round(
        TINA, call.id, per_submission=1, strategy_key="manual", release_key="each"
    )
    task = w.rr.add_task(TINA, r.id, work.id, UserParty(PAT))
    w.rv.save(PAT, task.id, {}, 0, submit=True)
    for member in (SAM, SUE):
        assert w.fb.feedback(member, work.id).rounds[0].released
    assert {m[0] for m in w.outbox.sent} == {"sam@x.fi", "sue@x.fi"}


def test_a_hand_in_works_when_mail_is_down(w: FeedbackWorld):
    broken = FeedbackWorld(broken_mail=True)
    r = broken.new_round(release_key="each")
    (sue_task,) = broken.assign(r, SAM, SUE)
    assert broken.hand_in(SUE, sue_task).submitted
    assert broken.sam_feedback().released


def test_the_list_of_feedback_received(w: FeedbackWorld):
    r = w.new_round(release_key="each")
    sue_task, _ = w.assign(r, SAM, SUE, PAT)
    w.hand_in(SUE, sue_task)
    [item] = w.fb.received(SAM, w.s.id)
    assert item.submission.id == w.subs[SAM].id and (item.shown, item.expected) == (1, 2)
    assert w.fb.received(PAT, w.s.id) == []  # Pat's work has no reviewers yet
    with pytest.raises(NotFound):
        w.fb.received(BOB, w.s.id)


def test_the_workspace_names_the_author_only_when_the_policy_allows(w: FeedbackWorld):
    hidden = w.new_round(anonymity_key="double_anonymous")
    (sue_task,) = w.assign(hidden, SAM, SUE)
    assert w.rv.workspace(SUE, sue_task.id).author_label == ANONYMOUS_AUTHOR
    assert w.rv.workspace(TINA, sue_task.id).author_label == "Sam"
    usual = w.new_round()  # reviewers hidden from authors; reviewers see who wrote it
    (pat_task,) = w.assign(usual, SAM, PAT)
    assert w.rv.workspace(PAT, pat_task.id).author_label == "Sam"


def w_upload() -> Upload:
    return Upload(text="Group work")


def test_groups_review_under_pseudonyms_too(w: FeedbackWorld):
    group = w.t.create_group(TINA, w.s.id, "Reviewers", [SUE, PAT])
    r = w.new_round(release_key="each")
    task = w.rr.add_task(TINA, r.id, w.subs[SAM].id, GroupParty(group.id))
    w.rv.save(PAT, task.id, w.answers(), 0, submit=True)
    assert w.sam_feedback().reviews[0].reviewer_label == "Reviewer A"
