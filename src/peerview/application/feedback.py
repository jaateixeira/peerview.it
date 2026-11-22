"""Feedback received: authors read the reviews of their work (ADR 0028).

A round's release rule decides when the handed-in reviews of each Submission reach its
authors. The first time they do, peerview.it records it (so feedback never disappears again,
even if a reviewer is added later) and sends the authors one email. Names go through the
IdentityMask: authors see "Reviewer A", "Reviewer B", ... unless the round's anonymity
policy shows reviewers. Organizers see everything, released or not.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from peerview.application.criteria import CriterionRegistry, UnknownCriterionType, answer_text
from peerview.application.identity_mask import IdentityMask
from peerview.application.ports import (
    CallRepository,
    Mailer,
    MailError,
    ReviewRepository,
    RoundRepository,
    RubricRepository,
    TenancyRepository,
    UserRepository,
)
from peerview.application.tenancy import Forbidden, NotFound, TenancyService
from peerview.domain.anonymity import Viewer, is_revealed
from peerview.domain.calls import Call, Submission, SubmissionId
from peerview.domain.identity import UserId
from peerview.domain.party import GroupParty, Party, UserParty
from peerview.domain.release import RELEASE_OPTIONS
from peerview.domain.reviews import WHOLE_WORK, Review
from peerview.domain.rounds import ReviewRound, ReviewTask, RoundId, RoundStatus, TaskId
from peerview.domain.rubrics import Criterion
from peerview.domain.tenancy import GroupId, Permission, SpaceId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnswerView:
    title: str
    text: str  # the answer in words (the criterion plugin puts it so)
    score: int | None
    max_score: int | None


@dataclass(frozen=True)
class NoteView:
    """A comment from the review: pinned to a passage (`quote`) or about the whole work."""

    quote: str
    body: str


@dataclass(frozen=True)
class ReceivedReview:
    reviewer_label: str  # through the IdentityMask
    answers: list[AnswerView]
    notes: list[NoteView]


@dataclass(frozen=True)
class RoundFeedback:
    round: ReviewRound
    released: bool  # authors may read the handed-in reviews
    handed_in: int
    expected: int
    reviews: list[ReceivedReview]  # for authors, only once released
    rule_label: str


@dataclass(frozen=True)
class FeedbackView:
    submission: Submission
    call: Call
    author_name: str
    organizer: bool  # sees every handed-in review and may release a round early
    rounds: list[RoundFeedback]


@dataclass(frozen=True)
class ReceivedItem:
    """One of my Submissions with reviews, for the Feedback received page."""

    submission: Submission
    call: Call
    shown: int  # reviews I may read now
    expected: int


@dataclass(frozen=True)
class _Standing:
    """Where one Submission stands in one round."""

    tasks: list[ReviewTask]  # ordered by id, so pseudonyms stay put
    reviews: dict[TaskId, Review]  # handed-in reviews by task
    released: bool


class FeedbackService:
    def __init__(
        self,
        rounds_repo: RoundRepository,
        reviews_repo: ReviewRepository,
        calls_repo: CallRepository,
        rubrics_repo: RubricRepository,
        tenancy: TenancyService,
        tenancy_repo: TenancyRepository,
        users: UserRepository,
        criteria: CriterionRegistry,
        mailer: Mailer,
        base_url: str,
        clock: Callable[[], datetime],
    ) -> None:
        self._rounds = rounds_repo
        self._reviews = reviews_repo
        self._calls = calls_repo
        self._rubrics = rubrics_repo
        self._tenancy = tenancy
        self._tenancy_repo = tenancy_repo
        self._users = users
        self._criteria = criteria
        self._mailer = mailer
        self._base_url = base_url.rstrip("/")
        self._now = clock
        self._mask = IdentityMask(users, tenancy_repo)

    # -- reading ----------------------------------------------------------

    def feedback(self, actor: UserId, submission_id: SubmissionId) -> FeedbackView:
        """The reviews of one Submission, round by round. Its authors and the space's
        organizers only; anyone else gets NotFound."""
        submission = self._calls.get_submission(submission_id)
        call = self._calls.get_call(submission.call_id) if submission else None
        if submission is None or call is None:
            raise NotFound
        view = self._tenancy.space_view(actor, submission.space_id)  # NotFound for outsiders
        organizer = Permission.ROUNDS_MANAGE in view.permissions
        if not organizer and not self._is_author(actor, submission):
            raise NotFound
        viewer = Viewer.ORGANIZER if organizer else Viewer.AUTHOR
        rounds: list[RoundFeedback] = []
        for round_ in self._rounds.rounds_of_call(call.id):
            standing = self._standing(round_, submission.id)
            if not standing.tasks:
                continue
            shown = organizer or standing.released
            rounds.append(
                RoundFeedback(
                    round_,
                    standing.released,
                    len(standing.reviews),
                    len(standing.tasks),
                    self._received(round_, call, standing, viewer) if shown else [],
                    RELEASE_OPTIONS[round_.release_key],
                )
            )
        return FeedbackView(submission, call, self._mask.name(submission.author), organizer, rounds)

    def received(self, actor: UserId, space_id: SpaceId) -> list[ReceivedItem]:
        """My Submissions in this space that reviewers were given, newest first."""
        self._tenancy.space_view(actor, space_id)  # NotFound for outsiders
        parties = self._my_parties(actor, space_id)
        items: list[ReceivedItem] = []
        for call in self._calls.calls_in_space(space_id):
            for submission in self._calls.submissions_of_parties(call.id, parties):
                shown = expected = 0
                for round_ in self._rounds.rounds_of_call(call.id):
                    standing = self._standing(round_, submission.id)
                    expected += len(standing.tasks)
                    shown += len(standing.reviews) if standing.released else 0
                if expected:
                    items.append(ReceivedItem(submission, call, shown, expected))
        return sorted(items, key=lambda i: i.submission.created_at, reverse=True)

    # -- releasing --------------------------------------------------------

    def release(self, actor: UserId, round_id: RoundId) -> ReviewRound:
        """An organizer shows authors the reviews handed in so far, whatever the rule."""
        round_ = self._rounds.get_round(round_id)
        if round_ is None:
            raise NotFound
        view = self._tenancy.space_view(actor, round_.space_id)
        if Permission.ROUNDS_MANAGE not in view.permissions:
            raise Forbidden
        self._rounds.mark_released(round_.id, self._now())
        round_ = self._rounds.get_round(round_id) or round_
        self._settle_round(round_)
        return round_

    def handed_in(self, task: ReviewTask) -> None:
        """A review was handed in: release its Submission's feedback if the rule says so."""
        round_ = self._rounds.get_round(task.round_id)
        if round_ is not None:
            self._settle(round_, task.submission_id)

    def send_due_notices(self) -> int:
        """At the due time, release rounds with the default rule and tell the authors. Run
        every few minutes; returns how many Submissions' authors were told."""
        told = 0
        for round_ in self._rounds.rounds_due_unreleased(self._now()):
            self._rounds.mark_released(round_.id, round_.closes_at or self._now())
            told += self._settle_round(replace(round_, released_at=round_.closes_at))
        return told

    # -- helpers ----------------------------------------------------------

    def _settle_round(self, round_: ReviewRound) -> int:
        tasks = self._rounds.tasks_of_round(round_.id)
        submission_ids = dict.fromkeys(t.submission_id for t in tasks)
        return sum(self._settle(round_, sid) for sid in submission_ids)

    def _settle(self, round_: ReviewRound, submission_id: SubmissionId) -> bool:
        """Record the release and notify the authors, once, when there is something to read."""
        standing = self._standing(round_, submission_id)
        if not standing.released or not standing.reviews:
            return False
        if not self._rounds.record_release(round_, submission_id, self._now()):
            return False  # already released and announced
        submission = self._calls.get_submission(submission_id)
        call = self._calls.get_call(round_.call_id)
        if submission is not None and call is not None:
            self._notify(submission, call, round_)
        return True

    def _standing(self, round_: ReviewRound, submission_id: SubmissionId) -> _Standing:
        tasks = sorted(
            (t for t in self._rounds.tasks_of_round(round_.id) if t.submission_id == submission_id),
            key=lambda t: t.id,
        )
        ids = {t.id for t in tasks}
        reviews = {
            rv.task_id: rv
            for rv in self._reviews.reviews_in_round(round_.id)
            if rv.task_id in ids and rv.submitted
        }
        recorded = self._rounds.releases_of_round(round_.id).get(submission_id)
        released = recorded is not None or round_.feedback_released(
            self._now(), handed_in=len(reviews), expected=len(tasks)
        )
        return _Standing(tasks, reviews, released)

    def _received(
        self, round_: ReviewRound, call: Call, standing: _Standing, viewer: Viewer
    ) -> list[ReceivedReview]:
        policy = round_.anonymity
        revealed = is_revealed(
            policy.reveal_at,
            round_closed=round_.status(self._now()) is RoundStatus.CLOSED,
            decided=False,
        )
        labels = self._mask.reviewers(
            [t.reviewer for t in standing.tasks], policy, viewer, revealed=revealed
        )
        criteria = self._rubrics.criteria_of(call.rubric_id) if call.rubric_id else []
        result: list[ReceivedReview] = []
        for task, label in zip(standing.tasks, labels, strict=True):
            review = standing.reviews.get(task.id)
            if review is None:
                continue
            result.append(
                ReceivedReview(label, self._answers(criteria, review), self._notes(review))
            )
        return result

    def _answers(self, criteria: list[Criterion], review: Review) -> list[AnswerView]:
        shown: list[AnswerView] = []
        for c in criteria:
            value = review.answers.get(c.id, "")
            if not value:
                continue
            try:
                kind = self._criteria.get(c.type_key)
            except UnknownCriterionType:
                shown.append(AnswerView(c.title, value, None, None))
                continue
            shown.append(
                AnswerView(
                    c.title,
                    answer_text(kind, c.config, value),
                    kind.score(c.config, value),
                    kind.max_score(c.config),
                )
            )
        return shown

    def _notes(self, review: Review) -> list[NoteView]:
        return [
            NoteView("" if a.kind == WHOLE_WORK else a.selector.get("quote", ""), a.body)
            for a in self._reviews.annotations_of(review.id)
        ]

    def _notify(self, submission: Submission, call: Call, round_: ReviewRound) -> None:
        link = f"{self._base_url}/submissions/{submission.id}/feedback"
        for user in self._users.get_many(self._author_people(submission.author)).values():
            if user.email is None or not user.email_verified:
                continue  # never mail an address nobody has confirmed
            try:
                self._mailer.send(
                    user.email.value,
                    f'Reviews of "{submission.title}" are ready',
                    f"Hello {user.display_name},\n\n"
                    f'The reviews of "{submission.title}" ({call.title}, round '
                    f"{round_.number}) are ready to read:\n{link}\n\n"
                    "You received this because you are an author of this work on "
                    "peerview.it.\n",
                )
            except MailError:
                logger.exception("Could not tell an author that feedback is ready")

    def _author_people(self, author: Party) -> list[UserId]:
        if isinstance(author, UserParty):
            return [UserId(author.user_id)]
        group = self._tenancy_repo.get_group(GroupId(author.group_id))
        return sorted(group.members) if group else []

    def _is_author(self, actor: UserId, submission: Submission) -> bool:
        return actor in self._author_people(submission.author)

    def _my_parties(self, actor: UserId, space_id: SpaceId) -> list[Party]:
        parties: list[Party] = [UserParty(actor)]
        parties += [
            GroupParty(g.id)
            for g in self._tenancy_repo.groups_in_space(space_id)
            if actor in g.members
        ]
        return parties
