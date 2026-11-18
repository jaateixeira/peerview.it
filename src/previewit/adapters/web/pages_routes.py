"""The live check of a web page's address while someone types it (ADR 0022)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from previewit.adapters.web.kit import WebKit
from previewit.adapters.web.limits import RateLimiter
from previewit.adapters.web.tenancy_routes import current_user
from previewit.application.web_pages import PageCheck, PageChecker, PageUnreachable

TOO_MANY = "You checked many pages in a short time. Wait a minute and try again."


async def check_page(pages: PageChecker, address: str) -> tuple[PageCheck | None, str | None]:
    """(what Previewit found, None) or (None, why it cannot go to reviewers)."""
    try:
        return await run_in_threadpool(pages.check, address), None
    except PageUnreachable as problem:
        return None, str(problem)


def build_pages_router(*, pages: PageChecker, kit: WebKit, limiter: RateLimiter) -> APIRouter:
    router = APIRouter()

    @router.post("/pages/check", response_class=HTMLResponse)
    async def check(request: Request) -> Response:
        user = current_user(request)  # only people with an account make Previewit fetch pages
        form = await kit.checked_form(request)
        if form is None:
            return kit.forbidden()
        address = kit.text(form, "web_address").strip()
        page: PageCheck | None = None
        problem: str | None = None
        if address:
            if limiter.allow(user.id):
                page, problem = await check_page(pages, address)
            else:
                problem = TOO_MANY
        # Always 200: HTMX shows the fragment either way.
        return kit.render(request, "_page_check.html", {"page": page, "problem": problem})

    return router
