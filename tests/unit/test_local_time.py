"""Times typed and shown in the viewer's zone, stored in UTC."""

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from starlette.requests import Request

from previewit.adapters.web.local_time import (
    BadTime,
    parse_day_time,
    parse_local,
    viewer_zone,
    zone_name,
)

HELSINKI = "Europe/Helsinki"


def http_request(cookies: dict[str, str], headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        raw.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw})


def request_with(cookie: str | None) -> Request:
    return http_request({} if cookie is None else {"pv_tz": cookie})


def test_the_zone_comes_from_the_cookie_and_falls_back_to_utc():
    assert zone_name(viewer_zone(request_with(HELSINKI))) == HELSINKI
    assert zone_name(viewer_zone(request_with("Europe%2FHelsinki"))) == HELSINKI  # encoded
    for bad in (None, "Mars/Olympus", "../../etc/passwd", "/etc/localtime", "x" * 200):
        assert viewer_zone(request_with(bad)) is UTC, bad


def test_a_due_day_without_a_time_is_four_in_the_afternoon_local():
    zone = viewer_zone(request_with(HELSINKI))
    assert parse_day_time("2027-01-15", "", zone) == datetime(2027, 1, 15, 14, 0, tzinfo=UTC)
    assert parse_day_time("2027-07-15", "", zone) == datetime(2027, 7, 15, 13, 0, tzinfo=UTC)
    assert parse_day_time("2027-07-15", "09:30", UTC) == datetime(2027, 7, 15, 9, 30, tzinfo=UTC)
    assert parse_day_time("", "09:30", UTC) is None


def test_typing_mistakes_are_explained():
    with pytest.raises(BadTime, match="date like"):
        parse_day_time("next week", "", UTC)
    with pytest.raises(BadTime, match="time like"):
        parse_day_time("2027-01-15", "teatime", UTC)
    with pytest.raises(BadTime, match="date and time"):
        parse_local("tomorrow", UTC)
    assert parse_local("  ", UTC) is None


@given(st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2099, 12, 31)))
def test_a_local_time_round_trips_through_utc(naive):
    zone = viewer_zone(request_with(HELSINKI))
    typed = naive.replace(second=0, microsecond=0)
    stored = parse_local(typed.strftime("%Y-%m-%dT%H:%M"), zone)
    assert stored is not None and stored.tzinfo is UTC
    shown = stored.astimezone(zone).replace(tzinfo=None)
    # A time skipped by the spring change moves an hour; every other time comes back as typed.
    assert shown == typed or abs((shown - typed).total_seconds()) == 3600


def test_a_refused_form_says_why():
    from previewit.adapters.web.session import csrf_problem

    def req(cookie: str | None, origin: str | None = None) -> Request:
        return http_request(
            {} if cookie is None else {"pv_csrf": cookie},
            {} if origin is None else {"origin": origin},
        )

    base = "http://localhost:8000"
    assert "cookie" in (csrf_problem(req(None), "t", base) or "")
    assert "does not match" in (csrf_problem(req("t"), "other", base) or "")
    assert "127.0.0.1" in (csrf_problem(req("t", "http://127.0.0.1:8000"), "t", base) or "")
    assert csrf_problem(req("t", base), "t", base) is None
    assert csrf_problem(req("t"), "t", base) is None  # no Origin header: the token decides
