"""Prepared review requests kept in memory, for tests (ADR 0023)."""

from __future__ import annotations

from datetime import datetime

from previewit.application.prepared_requests import PreparedRequest


class InMemoryPreparedRequestRepository:
    def __init__(self) -> None:
        self._rows: dict[str, PreparedRequest] = {}
        self.pretend_count: int | None = None  # tests: act as if this many were waiting
        self.pretend_files: int | None = None

    def add(self, token_hash: str, prepared: PreparedRequest) -> None:
        self._rows[token_hash] = prepared

    def get(self, token_hash: str) -> PreparedRequest | None:
        return self._rows.get(token_hash)

    def delete(self, token_hash: str) -> None:
        self._rows.pop(token_hash, None)

    def delete_expired(self, now: datetime) -> None:
        for key in [k for k, p in self._rows.items() if p.expires_at <= now]:
            del self._rows[key]

    def count(self) -> int:
        return self.pretend_count if self.pretend_count is not None else len(self._rows)

    def count_files(self) -> int:
        if self.pretend_files is not None:
            return self.pretend_files
        return sum(1 for p in self._rows.values() if p.file_content is not None)

    def raw_keys(self) -> list[str]:
        return list(self._rows)
