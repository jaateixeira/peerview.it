"""Prepared review requests (ADR 0023).

An AI assistant, through the MCP service, fills in Request a review for a person: the work (a
web page's address or some text), the reviewers, a message and a due date. Previewit keeps it
for a week under a secret link and sends nothing. The person opens the link, signs in, checks
the form and sends it; only then are reviewers invited. Nobody needs an account to prepare one,
so the rules here are strict about size and the store is bounded.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Protocol

from previewit.application.web_pages import PageUnreachable, normalise_address
from previewit.domain.email_list import MAX_EMAILS, parse_typed

PREPARED_DAYS = 7
MAX_TEXT_BYTES = 100_000
MAX_TITLE = 200
MAX_MESSAGE = 2000
MAX_PENDING = 10_000  # waiting prepared requests, site-wide


class InvalidPreparedRequest(ValueError):
    """The request cannot be prepared. The message is for the AI assistant to fix it."""


@dataclass(frozen=True)
class PreparedRequest:
    title: str
    web_address: str  # tidied; "" when the work is text
    text: str  # "" when the work is a web page
    reviewers: tuple[str, ...]  # email addresses, each once
    message: str  # a few words for the reviewers
    due: str  # "YYYY-MM-DD", or "" for the usual two weeks
    created_at: datetime
    expires_at: datetime


class PreparedRequestRepository(Protocol):
    def add(self, token_hash: str, prepared: PreparedRequest) -> None: ...
    def get(self, token_hash: str) -> PreparedRequest | None: ...
    def delete(self, token_hash: str) -> None: ...
    def delete_expired(self, now: datetime) -> None: ...
    def count(self) -> int: ...


def token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


class PreparedRequestsService:
    def __init__(
        self,
        repo: PreparedRequestRepository,
        new_token: Callable[[], str],
        now: Callable[[], datetime],
    ) -> None:
        self._repo = repo
        self._new_token = new_token
        self._now = now

    def prepare(
        self,
        *,
        title: str = "",
        web_address: str = "",
        text: str = "",
        reviewers: Sequence[str] = (),
        message: str = "",
        due: str = "",
    ) -> tuple[str, PreparedRequest]:
        """Keep a request for the person to check. Returns the secret token for its link."""
        now = self._now()
        title = " ".join(title.split())
        if len(title) > MAX_TITLE:
            raise InvalidPreparedRequest(f"The title is too long (at most {MAX_TITLE} characters).")
        address, text = web_address.strip(), text.strip()
        either = "Give either web_address (a public web page) or text (the work itself)"
        if address and text:
            raise InvalidPreparedRequest(either + ", not both.")
        if not address and not text:
            raise InvalidPreparedRequest(either + ".")
        if address:
            try:
                address = normalise_address(address)
            except PageUnreachable as problem:
                raise InvalidPreparedRequest(str(problem)) from None
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise InvalidPreparedRequest(
                "The text is too long (at most 100 kB). Put it on a public web page and give its "
                "address instead."
            )
        found = parse_typed("\n".join(reviewers))
        if found.invalid:
            raise InvalidPreparedRequest(
                "These reviewers are not an address Previewit can use: "
                + ", ".join(found.invalid) + "."
            )  # fmt: skip
        if found.over_limit or len(found.emails) > MAX_EMAILS:
            raise InvalidPreparedRequest(f"Ask at most {MAX_EMAILS} reviewers at a time.")
        message = message.strip()
        if len(message) > MAX_MESSAGE:
            raise InvalidPreparedRequest(
                f"The message is too long (at most {MAX_MESSAGE} characters)."
            )
        due = self._check_due(due.strip(), now)

        self._repo.delete_expired(now)
        if self._repo.count() >= MAX_PENDING:
            raise InvalidPreparedRequest(
                "Previewit has too many prepared requests waiting. Try again later."
            )
        prepared = PreparedRequest(
            title, address, text, tuple(e.value for e in found.emails), message, due, now,
            now + timedelta(days=PREPARED_DAYS),
        )  # fmt: skip
        token = self._new_token()
        self._repo.add(token_hash(token), prepared)
        return token, prepared

    def open(self, token: str) -> PreparedRequest | None:
        """The request behind a link, or None if it expired, was sent or never existed."""
        prepared = self._repo.get(token_hash(token))
        if prepared is None or prepared.expires_at <= self._now():
            return None
        return prepared

    def used(self, token: str) -> None:
        """The person sent it: forget it."""
        self._repo.delete(token_hash(token))

    @staticmethod
    def _check_due(due: str, now: datetime) -> str:
        if not due:
            return ""
        try:
            day = date.fromisoformat(due)
        except ValueError:
            raise InvalidPreparedRequest("Write the due date as YYYY-MM-DD.") from None
        if day < now.date() - timedelta(days=1):  # a day of slack for time zones
            raise InvalidPreparedRequest("That due date has passed.")
        if day > now.date() + timedelta(days=365):
            raise InvalidPreparedRequest("Choose a due date within the next year.")
        return day.isoformat()
