"""Small helpers shared by the route modules: rendering, CSRF-checked forms."""

from __future__ import annotations

from contextvars import ContextVar
from html import escape

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import Response

from previewit.adapters.settings import Settings
from previewit.adapters.web.session import (
    FormRefusal,
    csrf_refusal,
    csrf_token_for,
    set_csrf_cookie,
)

# Why this request's form was refused, so forbidden() can say it (one value per request task).
_refusal: ContextVar[FormRefusal | None] = ContextVar("form_refusal", default=None)


class WebKit:
    def __init__(self, templates: Jinja2Templates, settings: Settings) -> None:
        self.templates = templates
        self.settings = settings

    def render(
        self, request: Request, name: str, context: dict[str, object], status: int = 200
    ) -> Response:
        token, new = csrf_token_for(request)
        response = self.templates.TemplateResponse(
            request, name, {"csrf_token": token, **context}, status_code=status
        )
        if new:
            set_csrf_cookie(response, token, secure=self.settings.https)
        # The page carries this browser's form token: no shared cache may keep it for others.
        response.headers.setdefault("Cache-Control", "private, no-cache")
        return response

    async def checked_form(self, request: Request) -> FormData | None:
        form = await request.form()
        submitted = form.get("csrf")
        refusal = csrf_refusal(
            request, submitted if isinstance(submitted, str) else None, self.settings.origin
        )
        _refusal.set(refusal)
        if refusal is None:
            return form
        logger.warning("Form refused on {}: {}", request.url.path, refusal.log)
        return None

    def forbidden(self) -> Response:
        """The page for a refused form: what went wrong, in words, and what to do."""
        origin = escape(self.settings.origin)
        refusal = _refusal.get()
        if refusal is None or refusal.kind == "stale_page":
            message = (
                "This page was out of date: it was opened before your browser's form cookie "
                "was renewed. Reload the page and send it again."
            )
        elif refusal.kind == "no_cookie":
            secure = " and that you opened it with https://" if self.settings.https else ""
            message = (
                "Your browser did not send Previewit's form cookie, so the form could not be "
                "checked. Reload the page and send it again. If it happens again, check that "
                f"cookies are allowed for {escape(self.settings.host)}{secure}."
            )
        else:
            message = (
                f"This page was opened at {escape(refusal.opened_at)}, but Previewit's address "
                f"is {origin}. Forms only work there: open it at that address and try again."
            )
        return HTMLResponse(
            f"<!doctype html><title>Form refused</title><p>{message}</p>"
            f'<p><a href="{origin}/">Open Previewit at {origin}</a></p>',
            403,
        )

    @staticmethod
    def text(form: FormData, key: str) -> str:
        value = form.get(key)
        return value if isinstance(value, str) else ""

    @staticmethod
    def texts(form: FormData, key: str) -> list[str]:
        """Every text value sent under one name (a group of checkboxes)."""
        return [v for v in form.getlist(key) if isinstance(v, str)]
