"""When authors see the reviews of their work (ADR 0028)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from peerview.domain.release import (
    DEFAULT_RELEASE,
    RELEASE_OPTIONS,
    ReleaseRule,
    feedback_released,
)
from peerview.domain.rounds import InvalidRound, release_rule

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
DUE = NOW + timedelta(days=7)


def released(rule: ReleaseRule, **kw: object) -> bool:
    options: dict = {
        "now": NOW,
        "closes_at": DUE,
        "released_at": None,
        "handed_in": 0,
        "expected": 3,
    }
    return feedback_released(rule, **{**options, **kw})


def test_by_default_authors_see_them_when_all_are_in_or_at_the_due_time() -> None:
    rule = DEFAULT_RELEASE
    assert rule is ReleaseRule.COMPLETE_OR_DUE
    assert not released(rule, handed_in=2)
    assert released(rule, handed_in=3)  # every review is in
    assert released(rule, handed_in=1, now=DUE)  # the due time came
    assert not released(rule, handed_in=0, closes_at=None)  # no due time: wait for all


def test_as_each_is_handed_in() -> None:
    assert not released(ReleaseRule.EACH, handed_in=0)
    assert released(ReleaseRule.EACH, handed_in=1)


def test_an_organizer_releases_them_whatever_the_rule() -> None:
    assert not released(ReleaseRule.MANUAL, handed_in=3, now=DUE)  # never by itself
    for rule in ReleaseRule:
        assert released(rule, handed_in=1, released_at=NOW)


def test_the_rules_have_words_and_keys() -> None:
    assert set(RELEASE_OPTIONS) == {r.value for r in ReleaseRule}
    assert release_rule("manual") is ReleaseRule.MANUAL
    with pytest.raises(InvalidRound):
        release_rule("whenever")


@given(
    st.sampled_from(list(ReleaseRule)),
    st.integers(0, 10),
    st.integers(0, 10),
    st.integers(0, 20),
    st.integers(0, 20),
    st.booleans(),
)
def test_once_released_feedback_stays_released(
    rule: ReleaseRule, handed_in: int, more: int, hours: int, later: int, organizer: bool
) -> None:
    """More reviews or more time never take feedback back (ADR 0028)."""
    at = NOW + timedelta(hours=hours)
    released_at = NOW if organizer else None
    expected = 5
    before = released(rule, now=at, handed_in=handed_in, expected=expected, released_at=released_at)
    after = released(
        rule,
        now=at + timedelta(hours=later),
        handed_in=min(handed_in + more, expected),
        expected=expected,
        released_at=released_at,
    )
    assert not before or after
