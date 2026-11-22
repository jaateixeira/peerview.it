"""Feedback received: the reviews of a Submission, for its authors and organizers (ADR 0028)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from peerview.adapters.web.kit import WebKit
from peerview.adapters.web.tenancy_routes import current_user
from peerview.application.feedback import FeedbackService
from peerview.domain.calls import SubmissionId
from peerview.domain.identity import User
from peerview.domain.tenancy import SpaceId


def build_feedback_router(*, feedback: FeedbackService, kit: WebKit) -> APIRouter:
    router = APIRouter()
    run = run_in_threadpool

    def submission_page(request: Request, user: User, submission_id: str) -> Response:
        view = feedback.feedback(user.id, SubmissionId(submission_id))
        return kit.render(
            request,
            "feedback.html",
            {"page_title": f"Reviews: {view.submission.title}", "view": view},
        )

    def received_page(request: Request, user: User, space_id: str) -> Response:
        items = feedback.received(user.id, SpaceId(space_id))
        return kit.render(
            request,
            "feedback_received.html",
            {"page_title": "Feedback received", "space_id": space_id, "items": items},
        )

    @router.get("/submissions/{submission_id}/feedback", response_class=HTMLResponse)
    async def submission_feedback(request: Request, submission_id: str) -> Response:
        return await run(submission_page, request, current_user(request), submission_id)

    @router.get("/spaces/{space_id}/feedback", response_class=HTMLResponse)
    async def received(request: Request, space_id: str) -> Response:
        return await run(received_page, request, current_user(request), space_id)

    return router
