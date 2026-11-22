"""The reviewer's side of the call for reviewers: open a personal invitation link.

No account is needed (ADR 0020). A visitor reviews as a guest made for that one invitation
and is invited to join peerview.it after the review: joining keeps the reviews."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from loguru import logger
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from peerview.adapters.web.kit import WebKit
from peerview.adapters.web.session import SessionCodec, set_session_cookie
from peerview.adapters.web.tenancy_routes import current_user
from peerview.application.auth import AuthService, EmailTaken, NotAGuest, WeakPassword
from peerview.application.invitations import (
    AccountExists,
    InvalidInvitationLink,
    InvitationsService,
)
from peerview.application.ports import MailError
from peerview.application.tenancy import VerificationRequired
from peerview.application.verification import VerificationService
from peerview.domain.identity import User

JOIN = "/account/new"


def build_invitations_router(
    *,
    invitations: InvitationsService,
    kit: WebKit,
    auth: AuthService,
    verification: VerificationService,
    codec: SessionCodec,
) -> APIRouter:
    router = APIRouter()
    run = run_in_threadpool

    async def invitation_page(
        request: Request, token: str, *, problem: str | None = None, status: int = 200
    ) -> Response:
        preview = await run(invitations.preview, token)
        if preview is None:
            raise InvalidInvitationLink
        user: User | None = getattr(request.state, "user", None)
        state = await run(invitations.readiness, user.id, token) if user else None
        return kit.render(
            request,
            "invitation.html",
            {
                "page_title": f"Review: {preview.call_title}",
                "preview": preview,
                "token": token,
                "state": None if state == "anonymous" else state,
                "guests_allowed": invitations.guests_allowed(),
                "problem": problem,
            },
            status,
        )

    @router.get("/i/{token}", response_class=HTMLResponse)
    async def open_page(request: Request, token: str) -> Response:
        return await invitation_page(request, token)

    @router.post("/i/{token}")
    async def open_invitation(request: Request, token: str) -> Response:
        form = await kit.checked_form(request)
        if form is None:
            return kit.forbidden()
        user = current_user(request)
        accepted = await run(invitations.accept, user.id, token)
        return RedirectResponse(f"/spaces/{accepted.space_id}/reviews", status_code=303)

    @router.post("/i/{token}/guest")
    async def review_as_guest(request: Request, token: str) -> Response:
        form = await kit.checked_form(request)
        if form is None:
            return kit.forbidden()
        try:
            guest_id, accepted = await run(
                invitations.start_as_guest, token, kit.text(form, "name")
            )
        except AccountExists:
            return await invitation_page(request, token, problem="account_exists", status=409)
        except VerificationRequired:
            return await invitation_page(request, token, problem="account_needed", status=403)
        response = RedirectResponse(f"/spaces/{accepted.space_id}/reviews", status_code=303)
        set_session_cookie(response, codec.dumps(guest_id), secure=kit.settings.https)
        return response

    # -- joining after the review ------------------------------------------------------------

    def join_page(
        request: Request, user: User, *, error: str | None = None, status: int = 200
    ) -> Response:
        invitation = invitations.invitation_of_guest(user.id)
        return kit.render(
            request,
            "account_new.html",
            {
                "page_title": "Join peerview.it",
                "email": invitation.email.value if invitation else None,
                "name": user.display_name,
                "error": error,
            },
            status,
        )

    @router.get(JOIN, response_class=HTMLResponse)
    async def join(request: Request) -> Response:
        user = current_user(request)
        if not user.is_guest:
            return RedirectResponse("/account", status_code=303)
        return await run(join_page, request, user)

    @router.post(JOIN)
    async def join_now(request: Request) -> Response:
        form = await kit.checked_form(request)
        if form is None:
            return kit.forbidden()
        user = current_user(request)
        if not user.is_guest:
            return RedirectResponse("/account", status_code=303)
        invitation = await run(invitations.invitation_of_guest, user.id)
        if invitation is None:
            return await run(
                join_page, request, user, error="Open your invitation link again.", status=400
            )
        try:
            joined = await run(
                auth.join_as_guest,
                user.id,
                invitation.email,
                kit.text(form, "password"),
                kit.text(form, "name"),
            )
        except WeakPassword as weak:
            error = (
                "Use at least 10 characters."
                if weak.problem == "too_short"
                else "That password is too long (128 characters at most)."
            )
            return await run(join_page, request, user, error=error, status=400)
        except EmailTaken:
            error = (
                f"{invitation.email.value} already has an account. Log in with it to request "
                "reviews; the reviews you wrote as a guest stay with this invitation."
            )
            return await run(join_page, request, user, error=error, status=409)
        except NotAGuest:
            return RedirectResponse("/account", status_code=303)
        try:
            await run(verification.send, joined)
        except (MailError, OSError):
            logger.opt(exception=True).warning("could not send verification mail")
        return RedirectResponse("/account", status_code=303)

    return router
