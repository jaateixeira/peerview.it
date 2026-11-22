"""In-memory round repository: a fast fake that follows the same contract as the SQL one."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from peerview.application.ports import DuplicateRound, DuplicateTask
from peerview.domain.calls import CallId, SubmissionId
from peerview.domain.identity import UserId
from peerview.domain.invitations import Invitation
from peerview.domain.party import Party
from peerview.domain.release import ReleaseRule
from peerview.domain.rounds import ReviewRound, ReviewTask, RoundId, TaskId
from peerview.domain.tenancy import SpaceId


class InMemoryRoundRepository:
    def __init__(self) -> None:
        self._rounds: dict[RoundId, ReviewRound] = {}
        self._tasks: dict[TaskId, ReviewTask] = {}
        self._invitations: dict[str, Invitation] = {}
        self._releases: dict[tuple[RoundId, SubmissionId], datetime] = {}

    def add_round(self, round_: ReviewRound) -> None:
        if any(
            r.call_id == round_.call_id and r.number == round_.number for r in self._rounds.values()
        ):
            raise DuplicateRound
        self._rounds[round_.id] = round_

    def get_round(self, round_id: RoundId) -> ReviewRound | None:
        return self._rounds.get(round_id)

    def update_round(self, round_: ReviewRound) -> None:
        stored = self._rounds.get(round_.id)
        if stored is not None:
            self._rounds[round_.id] = replace(round_, released_at=stored.released_at)

    def delete_round(self, round_id: RoundId) -> None:
        self._rounds.pop(round_id, None)
        for key in [k for k in self._releases if k[0] == round_id]:
            del self._releases[key]
        for iid in [i.id for i in self._invitations.values() if i.round_id == round_id]:
            del self._invitations[iid]
        for tid in [t.id for t in self._tasks.values() if t.round_id == round_id]:
            del self._tasks[tid]

    def rounds_of_call(self, call_id: CallId) -> list[ReviewRound]:
        return sorted((r for r in self._rounds.values() if r.call_id == call_id), key=_number)

    def record_release(
        self, round_: ReviewRound, submission_id: SubmissionId, at: datetime
    ) -> bool:
        key = (round_.id, submission_id)
        if key in self._releases or round_.id not in self._rounds:
            return False
        self._releases[key] = at
        return True

    def releases_of_round(self, round_id: RoundId) -> dict[SubmissionId, datetime]:
        return {sid: at for (rid, sid), at in self._releases.items() if rid == round_id}

    def mark_released(self, round_id: RoundId, at: datetime) -> None:
        found = self._rounds.get(round_id)
        if found is not None and found.released_at is None:
            self._rounds[round_id] = replace(found, released_at=at)

    def rounds_due_unreleased(self, now: datetime) -> list[ReviewRound]:
        return [
            r
            for r in self._rounds.values()
            if r.release_key == ReleaseRule.COMPLETE_OR_DUE.value
            and r.released_at is None
            and r.closes_at is not None
            and r.closes_at <= now
        ]

    def add_tasks(self, tasks: Sequence[ReviewTask]) -> None:
        for task in tasks:
            if any(
                t.round_id == task.round_id
                and t.reviewer == task.reviewer
                and t.submission_id == task.submission_id
                for t in self._tasks.values()
            ):
                raise DuplicateTask
            self._tasks[task.id] = task

    def replace_tasks(self, round_id: RoundId, tasks: Sequence[ReviewTask]) -> None:
        for tid in [t.id for t in self._tasks.values() if t.round_id == round_id]:
            del self._tasks[tid]
        self.add_tasks(tasks)

    def get_task(self, task_id: TaskId) -> ReviewTask | None:
        return self._tasks.get(task_id)

    def delete_task(self, task_id: TaskId) -> None:
        self._tasks.pop(task_id, None)

    def tasks_of_round(self, round_id: RoundId) -> list[ReviewTask]:
        return [t for t in self._tasks.values() if t.round_id == round_id]

    def tasks_for_parties(self, space_id: SpaceId, parties: Sequence[Party]) -> list[ReviewTask]:
        wanted = set(parties)
        return [t for t in self._tasks.values() if t.space_id == space_id and t.reviewer in wanted]

    def add_invitation(self, invitation: Invitation) -> None:
        self._invitations[invitation.id] = invitation

    def get_invitation(self, invitation_id: str) -> Invitation | None:
        return self._invitations.get(invitation_id)

    def update_invitation(self, invitation: Invitation) -> None:
        current = self._invitations.get(invitation.id)
        if current is not None:  # only these two ever change
            self._invitations[invitation.id] = replace(
                current,
                revoked=invitation.revoked,
                accepted_by=invitation.accepted_by,
                sent_at=invitation.sent_at,
            )

    def invitations_of_round(self, round_id: RoundId) -> list[Invitation]:
        return [i for i in self._invitations.values() if i.round_id == round_id]

    def count_invitations(self, created_by: UserId) -> int:
        return sum(1 for i in self._invitations.values() if i.created_by == created_by)

    def invitations_accepted_by(self, user_id: UserId) -> list[Invitation]:
        return [i for i in self._invitations.values() if i.accepted_by == user_id]

    def claim_invitation(self, invitation_id: str, user_id: UserId) -> bool:
        current = self._invitations.get(invitation_id)
        if current is None or current.accepted_by is not None:
            return False
        self._invitations[invitation_id] = replace(current, accepted_by=user_id)
        return True


def _number(round_: ReviewRound) -> int:
    return round_.number
