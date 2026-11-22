"""The feedback suite again, on SQL storage (SQLite, and PostgreSQL if available), plus what
only the database can promise: one release record, and so one notice, per Submission."""

from dataclasses import replace
from datetime import timedelta

import pytest

from peerview.adapters.persistence.sql import SqlTenancyRepository, SqlUserRepository
from peerview.adapters.persistence.sql_calls import SqlCallRepository
from peerview.adapters.persistence.sql_reviews import SqlReviewRepository
from peerview.adapters.persistence.sql_rounds import SqlRoundRepository
from peerview.adapters.persistence.sql_rubrics import SqlRubricRepository
from tests.integration.test_tenancy_sql import engine as engine  # fixture
from tests.unit import test_feedback_service as base
from tests.unit.test_calls_service import SAM
from tests.unit.test_feedback_service import FeedbackWorld


@pytest.fixture
def w(engine) -> FeedbackWorld:
    return FeedbackWorld(
        users=SqlUserRepository(engine),
        repo=SqlTenancyRepository(engine),
        calls_repo=SqlCallRepository(engine),
        rounds_repo=SqlRoundRepository(engine),
        reviews_repo=SqlReviewRepository(engine),
        rubrics_repo=SqlRubricRepository(engine),
    )


for _name in dir(base):
    if _name.startswith("test_"):
        globals()[_name] = getattr(base, _name)


def test_a_release_is_recorded_once(w: FeedbackWorld):
    r = w.new_round()
    sub = w.subs[SAM].id
    at = w.clock.now
    assert w.rr._repo.record_release(r, sub, at)
    assert not w.rr._repo.record_release(r, sub, at + timedelta(hours=1))
    assert w.rr._repo.releases_of_round(r.id) == {sub: at}


def test_marking_a_round_released_keeps_the_first_time_and_the_settings(w: FeedbackWorld):
    r = w.new_round(closes_at=w.clock.now + timedelta(days=1))
    w.rr._repo.mark_released(r.id, w.clock.now)
    w.rr._repo.mark_released(r.id, w.clock.now + timedelta(days=3))
    stored = w.rr._repo.get_round(r.id)
    assert stored is not None and stored.released_at == w.clock.now
    assert stored.release_key == r.release_key and stored.closes_at == r.closes_at
    w.rr._repo.update_round(replace(stored, released_at=None))
    again = w.rr._repo.get_round(r.id)
    assert again is not None and again.released_at == w.clock.now  # updates never undo it


def test_the_sweep_finds_only_due_rounds_with_the_default_rule(w: FeedbackWorld):
    due = w.new_round(closes_at=w.clock.now + timedelta(hours=1))
    w.new_round(closes_at=w.clock.now + timedelta(hours=1), release_key="manual")
    w.new_round(closes_at=w.clock.now + timedelta(days=9))
    w.new_round()  # no due time
    later = w.clock.now + timedelta(hours=2)
    assert [r.id for r in w.rr._repo.rounds_due_unreleased(later)] == [due.id]
    w.rr._repo.mark_released(due.id, later)
    assert w.rr._repo.rounds_due_unreleased(later) == []
