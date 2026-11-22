import pytest

from peerview.domain.identity import Email, User, UserId
from peerview.domain.policy import DEFAULT_POLICY, Action, VerificationPolicy, parse_actions


def _user(*, verified: bool, email: bool = True) -> User:
    return User(UserId("u"), "A", Email("a@x.fi") if email else None, verified, frozenset(), False)


def test_by_default_nothing_needs_a_verified_email():
    # decided (ADR 0020): an invitation link is enough to review, even without an account
    assert DEFAULT_POLICY.required_for == frozenset()
    unverified = _user(verified=False)
    assert all(DEFAULT_POLICY.allows(unverified, a) for a in Action)


def test_a_user_without_an_email_counts_as_unverified():
    reviewers_verified = VerificationPolicy(frozenset({Action.REVIEW}))
    assert not reviewers_verified.allows(_user(verified=False, email=False), Action.REVIEW)
    assert reviewers_verified.allows(_user(verified=False, email=False), Action.SUBMIT)


def test_policies_can_require_more_or_nothing():
    strict = VerificationPolicy(frozenset(Action))
    lax = VerificationPolicy(frozenset())
    unverified = _user(verified=False)
    assert not any(strict.allows(unverified, a) for a in Action)
    assert all(lax.allows(unverified, a) for a in Action)


def test_parse_actions():
    assert parse_actions(["review", "submit"]) == {Action.REVIEW, Action.SUBMIT}
    assert parse_actions([]) == frozenset()
    with pytest.raises(ValueError, match="reveiw"):
        parse_actions(["reveiw"])  # a typo must not silently weaken the policy
