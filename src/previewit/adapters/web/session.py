"""Signed session cookie, CSRF tokens and safe redirects."""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from typing import Literal

from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.requests import Request
from starlette.responses import Response

SESSION_COOKIE = "pv_session"
CSRF_COOKIE = "pv_csrf"
SESSION_MAX_AGE = 14 * 24 * 3600
CSRF_MAX_AGE = 365 * 24 * 3600  # outlives the browser session: a restored tab still matches


class SessionCodec:
    def __init__(self, secret_key: str, max_age: int = SESSION_MAX_AGE) -> None:
        self._serializer = URLSafeTimedSerializer(secret_key, salt="previewit-session")
        self._max_age = max_age

    def dumps(self, user_id: str) -> str:
        return self._serializer.dumps(user_id)

    def loads(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            value = self._serializer.loads(token, max_age=self._max_age)
        except BadSignature:
            return None
        return value if isinstance(value, str) else None


def set_session_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def csrf_token_for(request: Request) -> tuple[str, bool]:
    """The request's CSRF token, and whether it is new (cookie must then be set)."""
    existing = request.cookies.get(CSRF_COOKIE)
    if existing:
        return existing, False
    return secrets.token_urlsafe(32), True


def set_csrf_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=CSRF_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


@dataclass(frozen=True)
class FormRefusal:
    """Why a form failed the double-submit and Origin checks."""

    kind: Literal["no_cookie", "stale_page", "other_address"]
    log: str  # for the server log
    opened_at: str = ""  # the Origin the browser sent, for "other_address"


def csrf_refusal(request: Request, submitted: str | None, origin: str) -> FormRefusal | None:
    cookie = request.cookies.get(CSRF_COOKIE)
    if not cookie:
        return FormRefusal(
            "no_cookie",
            "no form-token cookie (cookies blocked, or an https base URL served over http)",
        )
    if not submitted or not hmac.compare_digest(cookie, submitted):
        return FormRefusal(
            "stale_page",
            "the form token does not match the cookie (page opened before the cookie changed)",
        )
    sent_origin = request.headers.get("origin")
    if sent_origin is not None and sent_origin != origin:
        return FormRefusal(
            "other_address",
            f"page opened at {sent_origin}, but the base URL is {origin}",
            sent_origin,
        )
    return None


def csrf_problem(request: Request, submitted: str | None, origin: str) -> str | None:
    """Why a form fails the double-submit and Origin checks, or None when it passes."""
    refusal = csrf_refusal(request, submitted, origin)
    return refusal.log if refusal else None


def csrf_ok(request: Request, submitted: str | None, origin: str) -> bool:
    """Double-submit check plus an Origin check when the browser sends one."""
    return csrf_problem(request, submitted, origin) is None


def safe_next(value: str | None) -> str:
    """Only local absolute paths: never another site, never protocol-relative."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value
