"""Dates and times in the viewer's own time zone.

The domain stores every moment in UTC. People type and read times in their own zone: a
small script (`static/js/local-time.js`) puts the browser's IANA zone in the `pv_tz`
cookie, and this module converts on the way in and on the way out. Without the cookie
(first request, no JavaScript) times are in UTC and say so.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, tzinfo
from functools import lru_cache
from urllib.parse import unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jinja2 import pass_context
from jinja2.runtime import Context
from starlette.requests import Request

ZONE_COOKIE = "pv_tz"
DEFAULT_DUE_TIME = time(16, 0)  # reviews are due at 16:00 unless the organizer says otherwise


class BadTime(ValueError):
    """A date or time a person typed that cannot be read."""


@lru_cache(maxsize=256)
def _zone(name: str) -> tzinfo | None:
    if not name or len(name) > 64 or name.startswith(("/", ".")) or ".." in name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def viewer_zone(request: Request | None) -> tzinfo:
    """The browser's zone from the cookie, or UTC."""
    if request is None:
        return UTC
    return _zone(unquote(request.cookies.get(ZONE_COOKIE, ""))) or UTC


def zone_name(zone: tzinfo) -> str:
    return getattr(zone, "key", None) or "UTC"


def today(zone: tzinfo, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(zone).date()


def parse_local(value: str, zone: tzinfo) -> datetime | None:
    """A `datetime-local` value (2026-12-31T16:00) in `zone`, as UTC. Empty is None."""
    value = value.strip()
    if not value:
        return None
    try:
        naive = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise BadTime("Use a date and time like 2026-12-31 16:00.") from None
    return naive.replace(tzinfo=zone).astimezone(UTC)


def parse_day_time(
    day: str, at: str, zone: tzinfo, default_time: time = DEFAULT_DUE_TIME
) -> datetime | None:
    """A `date` input plus an optional `time` input in `zone`, as UTC. No day is None."""
    day, at = day.strip(), at.strip()
    if not day:
        return None
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        raise BadTime("Write the date like 2026-12-31.") from None
    try:
        t = datetime.strptime(at, "%H:%M").time() if at else default_time
    except ValueError:
        raise BadTime("Write the time like 16:00.") from None
    return datetime.combine(d, t, zone).astimezone(UTC)


# -- template helpers ---------------------------------------------------------------------


def _ctx_zone(ctx: Context) -> tzinfo:
    request = ctx.get("request")
    return viewer_zone(request if isinstance(request, Request) else None)


@pass_context
def when(ctx: Context, moment: datetime | None) -> str:
    """`2026-12-31 16:00 EET` in the viewer's zone."""
    if moment is None:
        return ""
    local = moment.astimezone(_ctx_zone(ctx))
    return f"{local:%Y-%m-%d %H:%M} {local.tzname() or 'UTC'}"


@pass_context
def day_of(ctx: Context, moment: datetime | None) -> str:
    """`2026-12-31` in the viewer's zone."""
    return "" if moment is None else f"{moment.astimezone(_ctx_zone(ctx)):%Y-%m-%d}"


@pass_context
def local_input(ctx: Context, moment: datetime | None) -> str:
    """Value for a `datetime-local` input."""
    return "" if moment is None else f"{moment.astimezone(_ctx_zone(ctx)):%Y-%m-%dT%H:%M}"


@pass_context
def time_of(ctx: Context, moment: datetime | None) -> str:
    """Value for a `time` input; 16:00 when there is no moment yet."""
    if moment is None:
        return DEFAULT_DUE_TIME.strftime("%H:%M")
    return f"{moment.astimezone(_ctx_zone(ctx)):%H:%M}"


@pass_context
def your_zone(ctx: Context) -> str:
    return zone_name(_ctx_zone(ctx))


@pass_context
def min_day(ctx: Context, current: datetime | None = None) -> str:
    """`min` for a date picker: today, or an earlier saved value so the form still saves."""
    first = today(_ctx_zone(ctx))
    if current is not None:
        first = min(first, current.astimezone(_ctx_zone(ctx)).date())
    return first.isoformat()


def install(env: object) -> None:
    """Register the helpers on a Jinja environment."""
    filters = env.filters  # type: ignore[attr-defined]
    globals_ = env.globals  # type: ignore[attr-defined]
    filters["when"] = when
    filters["day"] = day_of
    filters["local_input"] = local_input
    filters["time_of"] = time_of
    globals_["your_zone"] = your_zone
    globals_["min_day"] = min_day
