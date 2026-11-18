"""Prepared review requests (ADR 0023): an AI assistant fills in Request a review, the person
checks it and sends it. Nothing is sent by preparing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from previewit.adapters.persistence.memory_prepared import InMemoryPreparedRequestRepository
from previewit.application.prepared_requests import (
    MAX_PENDING,
    InvalidPreparedRequest,
    PreparedRequestsService,
)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


class World:
    def __init__(self, repo=None) -> None:
        self.now = NOW
        self.repo = repo or InMemoryPreparedRequestRepository()
        ids = count(1)
        self.s = PreparedRequestsService(self.repo, lambda: f"token-{next(ids)}", lambda: self.now)


@pytest.fixture
def w() -> World:
    return World()


def test_a_web_page_and_reviewers_are_kept_for_the_person_to_check(w: World):
    token, prepared = w.s.prepare(
        title="  My portfolio ",
        web_address="example.org/portfolio",
        reviewers=["ana@x.fi", " Bo@X.fi ", "ana@x.fi"],
        message="Be honest.",
        due="2026-12-01",
    )
    assert token == "token-1"
    assert (
        prepared.title == "My portfolio" and prepared.web_address == "https://example.org/portfolio"
    )
    assert prepared.reviewers == ("ana@x.fi", "bo@x.fi")
    assert prepared.expires_at == NOW + timedelta(days=7)
    assert w.s.open(token) == prepared
    assert w.repo.raw_keys() != ["token-1"]  # only a hash of the token is kept


def test_text_can_be_prepared_instead_of_a_page(w: World):
    token, prepared = w.s.prepare(text="My essay.\n\nIt is short.")
    assert prepared.text == "My essay.\n\nIt is short." and prepared.reviewers == ()
    assert w.s.open(token) is not None


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({}, "Give either web_address (a public web page) or text"),
        ({"web_address": "example.org", "text": "x"}, "not both"),
        ({"web_address": "http://10.0.0.1/"}, "not on the public internet"),
        ({"text": "x" * 100_001}, "text is too long"),
        ({"text": "x", "title": "t" * 201}, "title is too long"),
        ({"text": "x", "reviewers": ["ana@x.fi", "not an address"]}, "not an address"),
        ({"text": "x", "reviewers": [f"r{i}@x.fi" for i in range(101)]}, "at most 100"),
        ({"text": "x", "message": "m" * 2001}, "message is too long"),
        ({"text": "x", "due": "1.12.2026"}, "YYYY-MM-DD"),
        ({"text": "x", "due": "2026-11-01"}, "has passed"),
        ({"text": "x", "due": "2028-01-01"}, "within the next year"),
    ],
)
def test_what_cannot_become_a_request_is_explained(w: World, fields, reason):
    with pytest.raises(InvalidPreparedRequest) as refused:
        w.s.prepare(**fields)
    assert reason in str(refused.value)
    assert w.repo.count() == 0


def test_a_prepared_request_expires_and_is_forgotten(w: World):
    token, _ = w.s.prepare(text="x")
    w.now = NOW + timedelta(days=7, seconds=1)
    assert w.s.open(token) is None
    w.s.prepare(text="y")  # preparing another clears the expired ones
    assert w.repo.count() == 1


def test_a_sent_request_is_forgotten(w: World):
    token, _ = w.s.prepare(text="x")
    w.s.used(token)
    assert w.s.open(token) is None and w.repo.count() == 0
    w.s.used(token)  # twice is harmless
    assert w.s.open("never-made") is None


def test_previewit_refuses_when_too_many_are_waiting(w: World):
    w.repo.pretend_count = MAX_PENDING
    with pytest.raises(InvalidPreparedRequest, match="too many"):
        w.s.prepare(text="x")
