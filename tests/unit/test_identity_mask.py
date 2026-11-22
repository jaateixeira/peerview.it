"""The IdentityMask: the one way a Party becomes a name on a page (ADR 0028)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from peerview.adapters.persistence.memory import InMemoryTenancyRepository, InMemoryUserRepository
from peerview.application.identity_mask import IdentityMask
from peerview.domain.anonymity import (
    ANONYMOUS_AUTHOR,
    AnonymityPolicy,
    Viewer,
    reviewer_pseudonym,
)
from peerview.domain.identity import User, UserId
from peerview.domain.party import GroupParty, UserParty
from peerview.domain.tenancy import Group, GroupId, OrgId, SpaceId

ANA, BEN, CY = UserId("ana"), UserId("ben"), UserId("cy")


def mask() -> IdentityMask:
    users = InMemoryUserRepository()
    for uid, name in [(ANA, "Ana"), (BEN, "Ben"), (CY, "Cy")]:
        users.add_user(User(uid, name, None, True, frozenset(), False), None)
    groups = InMemoryTenancyRepository()
    groups.add_group(Group(GroupId("g1"), OrgId("o"), SpaceId("s"), "Team Kale", frozenset({BEN})))
    return IdentityMask(users, groups)


def test_real_names_of_people_and_groups() -> None:
    m = mask()
    assert m.name(UserParty(ANA)) == "Ana"
    assert m.name(GroupParty(GroupId("g1"))) == "Team Kale"
    assert m.name(UserParty(UserId("gone"))) == "Unknown"
    assert m.people([ANA, BEN, ANA]) == {ANA: "Ana", BEN: "Ben"}


def test_reviewers_are_letters_for_authors_when_reviewers_are_hidden() -> None:
    m = mask()
    reviewers = [UserParty(ANA), GroupParty(GroupId("g1"))]
    hidden = AnonymityPolicy.reviewers_hidden()
    assert m.reviewers(reviewers, hidden, Viewer.AUTHOR) == ["Reviewer A", "Reviewer B"]
    assert m.reviewers(reviewers, hidden, Viewer.ORGANIZER) == ["Ana", "Team Kale"]
    assert m.reviewers(reviewers, AnonymityPolicy.open(), Viewer.AUTHOR) == ["Ana", "Team Kale"]
    assert m.reviewers(reviewers, hidden, Viewer.AUTHOR, revealed=True) == ["Ana", "Team Kale"]


def test_authors_are_anonymous_to_reviewers_when_authors_are_hidden() -> None:
    m = mask()
    author = GroupParty(GroupId("g1"))
    policy = AnonymityPolicy.double_anonymous()
    assert m.author(author, policy, Viewer.REVIEWER) == ANONYMOUS_AUTHOR
    assert m.author(author, policy, Viewer.ORGANIZER) == "Team Kale"
    assert m.author(author, policy, Viewer.AUTHOR) == "Team Kale"
    assert m.author(author, AnonymityPolicy.reviewers_hidden(), Viewer.REVIEWER) == "Team Kale"


@given(st.integers(0, 2_000), st.integers(0, 2_000))
def test_pseudonyms_differ_for_different_places(i: int, j: int) -> None:
    assert (reviewer_pseudonym(i) == reviewer_pseudonym(j)) == (i == j)


def test_pseudonyms_run_past_z() -> None:
    assert [reviewer_pseudonym(i) for i in (0, 1, 25, 26, 27)] == [
        "Reviewer A",
        "Reviewer B",
        "Reviewer Z",
        "Reviewer AA",
        "Reviewer AB",
    ]
