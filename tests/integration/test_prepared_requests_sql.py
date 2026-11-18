"""The prepared-requests suite again on SQL storage (ADR 0023)."""

import pytest

from previewit.adapters.persistence.sql_prepared import SqlPreparedRequestRepository
from previewit.adapters.persistence.tables import prepared_requests
from tests.integration.test_tenancy_sql import engine as engine  # fixture
from tests.unit import test_prepared_requests as base


class SqlRepo(SqlPreparedRequestRepository):
    """The SQL store, with the two test hooks the suite uses."""

    pretend_count: int | None = None

    def count(self) -> int:
        return self.pretend_count if self.pretend_count is not None else super().count()

    def raw_keys(self) -> list[str]:
        from sqlalchemy import select

        with self._engine.connect() as conn:
            return [r[0] for r in conn.execute(select(prepared_requests.c.token_hash))]


@pytest.fixture
def w(engine) -> base.World:
    return base.World(repo=SqlRepo(engine))


for _name in dir(base):
    if _name.startswith("test_"):
        globals()[_name] = getattr(base, _name)
