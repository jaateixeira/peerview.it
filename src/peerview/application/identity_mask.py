"""The IdentityMask: the one way a Party becomes a name on a page (ADR 0028).

Services never read a person's or a group's name themselves; they ask the mask. With a
round's AnonymityPolicy and the viewer's place, the mask gives the real name or a
pseudonym: "Anonymous author", or "Reviewer A", "Reviewer B", ... in an order that stays
the same for one Submission within a round.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from peerview.application.ports import TenancyRepository, UserRepository
from peerview.domain.anonymity import (
    ANONYMOUS_AUTHOR,
    AnonymityPolicy,
    Viewer,
    reviewer_pseudonym,
)
from peerview.domain.identity import UserId
from peerview.domain.party import GroupParty, Party, UserParty
from peerview.domain.tenancy import GroupId

UNKNOWN_PERSON = "Unknown"
UNKNOWN_GROUP = "Unknown group"


class IdentityMask:
    def __init__(self, users: UserRepository, groups: TenancyRepository) -> None:
        self._users = users
        self._groups = groups

    # -- real names: for viewers who may see them --------------------------------------------

    def name(self, party: Party) -> str:
        if isinstance(party, UserParty):
            user = self._users.get(UserId(party.user_id))
            return user.display_name if user else UNKNOWN_PERSON
        assert isinstance(party, GroupParty)
        group = self._groups.get_group(GroupId(party.group_id))
        return group.name if group else UNKNOWN_GROUP

    def names(self, parties: Iterable[Party]) -> dict[Party, str]:
        wanted = list(dict.fromkeys(parties))
        people = self.people([UserId(p.user_id) for p in wanted if isinstance(p, UserParty)])
        result: dict[Party, str] = {}
        for party in wanted:
            if isinstance(party, UserParty):
                result[party] = people.get(UserId(party.user_id), UNKNOWN_PERSON)
            else:
                result[party] = self.name(party)
        return result

    def people(self, user_ids: Iterable[UserId]) -> dict[UserId, str]:
        """Names of people who act together (group mates in an edit trail)."""
        found = self._users.get_many(list(dict.fromkeys(user_ids)))
        return {uid: user.display_name for uid, user in found.items()}

    # -- names under an anonymity policy ------------------------------------------------------

    def author(
        self, party: Party, policy: AnonymityPolicy, viewer: Viewer, *, revealed: bool = False
    ) -> str:
        if policy.may_see_author(viewer, revealed=revealed):
            return self.name(party)
        return ANONYMOUS_AUTHOR

    def reviewers(
        self,
        parties: Sequence[Party],
        policy: AnonymityPolicy,
        viewer: Viewer,
        *,
        revealed: bool = False,
    ) -> list[str]:
        """Labels for the reviewers of one Submission in one round, in the order given (the
        caller keeps that order stable)."""
        if policy.may_see_reviewer(viewer, revealed=revealed):
            names = self.names(parties)
            return [names[p] for p in parties]
        return [reviewer_pseudonym(i) for i in range(len(parties))]
