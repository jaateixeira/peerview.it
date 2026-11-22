"""Review rounds for a call, allocation, manual pairing and "my reviews to do"."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData
from starlette.responses import Response

from peerview.adapters.web.kit import WebKit
from peerview.adapters.web.local_time import (
    BadTime,
    parse_day_time,
    parse_local,
    viewer_zone,
)
from peerview.adapters.web.tenancy_routes import current_user
from peerview.application.allocation import UnknownStrategy
from peerview.application.calls import CallsService, ShareLimitReached
from peerview.application.feedback import FeedbackService
from peerview.application.invitations import InvitationsService
from peerview.application.ports import MailError
from peerview.application.rounds import RoundsService
from peerview.application.tenancy import NotFound
from peerview.domain.calls import CallId, SubmissionId
from peerview.domain.identity import User
from peerview.domain.invitations import InvalidInvitation
from peerview.domain.party import GroupParty, Party, UserParty
from peerview.domain.release import DEFAULT_RELEASE
from peerview.domain.rounds import DEFAULT_ANONYMITY, InvalidRound, RoundId, TaskId
from peerview.domain.tenancy import SpaceId


def parse_when(value: str, zone: tzinfo = UTC) -> datetime | None:
    """`datetime-local` input in the viewer's zone, as UTC."""
    try:
        return parse_local(value, zone)
    except BadTime as e:
        raise InvalidRound(str(e)) from None


def parse_due(day: str, at: str, zone: tzinfo = UTC) -> datetime | None:
    """The reviews-due day and time (16:00 if no time) in the viewer's zone, as UTC."""
    try:
        return parse_day_time(day, at, zone)
    except BadTime as e:
        raise InvalidRound(str(e)) from None


def refuse_past_due(closes_at: datetime | None, before: datetime | None = None) -> None:
    """A due time typed in the form must still be ahead; an unchanged saved one may not be."""
    if closes_at is not None and closes_at != before and closes_at <= datetime.now(UTC):
        raise InvalidRound("That due time has passed. Choose today or a later day.")


def whole(value: str, default: int) -> int:
    value = value.strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise InvalidRound("The number of reviews must be a whole number.") from None


def parse_party(value: str) -> Party:
    """`user:<id>` or `group:<id>`, as the manual-pairing form sends it."""
    kind, _, ident = value.partition(":")
    if kind == "user" and ident:
        return UserParty(ident)
    if kind == "group" and ident:
        return GroupParty(ident)
    raise InvalidRound("Choose who should review.")


@dataclass(frozen=True)
class FreshInvitation:
    """An invitation just created: its link and token are shown to the organizer once."""

    round_id: str
    link: str
    token: str
    email: str


def build_rounds_router(
    *,
    rounds: RoundsService,
    calls: CallsService,
    invitations: InvitationsService,
    kit: WebKit,
    feedback: FeedbackService | None = None,
) -> APIRouter:
    router = APIRouter()
    run = run_in_threadpool

    def page(
        request: Request,
        user: User,
        call_id: str,
        *,
        error: str | None = None,
        notice: str | None = None,
        fresh: FreshInvitation | None = None,
        status: int = 200,
    ) -> Response:
        call_view = calls.call_view(user.id, CallId(call_id))
        call = call_view.call
        views = rounds.rounds(user.id, CallId(call_id))
        options = {v.round.id: rounds.reviewer_options(user.id, v.round.id) for v in views}
        invited = {v.round.id: invitations.invitations(user.id, v.round.id) for v in views}
        return kit.render(
            request,
            "rounds.html",
            {
                "page_title": f"Rounds: {call.title}",
                "call": call,
                "views": views,
                "strategies": rounds.strategies(),
                "anonymity_options": rounds.anonymity_options(),
                "default_anonymity": DEFAULT_ANONYMITY,
                "release_options": rounds.release_options(),
                "default_release": DEFAULT_RELEASE.value,
                "can_release": feedback is not None,
                "options": options,
                "invited": invited,
                "fresh": fresh,
                "submissions": call_view.everyone or [],
                "next_number": len(views) + 1,
                "error": error,
                "notice": notice,
            },
            status,
        )

    def reviews_page(request: Request, user: User, space_id: str) -> Response:
        sid = SpaceId(space_id)
        tasks = rounds.my_tasks(user.id, sid)
        return kit.render(
            request,
            "my_reviews.html",
            {"page_title": "My reviews", "space_id": space_id, "tasks": tasks},
        )

    @router.get("/calls/{call_id}/rounds", response_class=HTMLResponse)
    async def rounds_page(request: Request, call_id: str) -> Response:
        return await run(page, request, current_user(request), call_id)

    @router.get("/spaces/{space_id}/reviews", response_class=HTMLResponse)
    async def my_reviews(request: Request, space_id: str) -> Response:
        return await run(reviews_page, request, current_user(request), space_id)

    async def act(
        request: Request,
        call_id: str,
        action: Callable[[User, FormData], str | None],
    ) -> Response:
        """CSRF, run `action(user, form)`, then show the call's rounds again."""
        form = await kit.checked_form(request)
        if form is None:
            return kit.forbidden()
        user = current_user(request)
        try:
            notice = await run(action, user, form)
        except (InvalidRound, UnknownStrategy) as e:
            message = "Choose an allocation method." if isinstance(e, UnknownStrategy) else str(e)
            return await run(page, request, user, call_id, error=message, status=400)
        if notice:
            return await run(page, request, user, call_id, notice=notice)
        return RedirectResponse(f"/calls/{call_id}/rounds", status_code=303)

    def settings(f: FormData, zone: tzinfo) -> dict[str, Any]:
        return {
            "per_submission": whole(kit.text(f, "per_submission"), 1),
            "strategy_key": kit.text(f, "strategy"),
            "anonymity_key": kit.text(f, "anonymity") or DEFAULT_ANONYMITY,
            "release_key": kit.text(f, "release") or DEFAULT_RELEASE.value,
            "opens_at": parse_when(kit.text(f, "opens_at"), zone),
            "closes_at": parse_due(kit.text(f, "closes_on"), kit.text(f, "closes_time"), zone),
        }

    @router.post("/calls/{call_id}/rounds")
    async def create_round(request: Request, call_id: str) -> Response:
        zone = viewer_zone(request)

        def action(user: User, f: FormData) -> None:
            values = settings(f, zone)
            refuse_past_due(values["closes_at"])
            rounds.create_round(user.id, CallId(call_id), **values)

        return await act(request, call_id, action)

    @router.post("/rounds/{round_id}/edit")
    async def edit_round(request: Request, round_id: str) -> Response:
        user = current_user(request)
        call_id = await run(call_of_sync, user, round_id)

        zone = viewer_zone(request)

        def action(u: User, f: FormData) -> None:
            values = settings(f, zone)
            saved = rounds.round_view(u.id, RoundId(round_id)).round.closes_at
            refuse_past_due(values["closes_at"], saved)
            rounds.update_round(u.id, RoundId(round_id), **values)

        return await act(request, call_id, action)

    def call_of_sync(user: User, round_id: str) -> str:
        return str(rounds.round_view(user.id, RoundId(round_id)).round.call_id)

    @router.post("/rounds/{round_id}/delete")
    async def delete_round(request: Request, round_id: str) -> Response:
        call_id = await run(call_of_sync, current_user(request), round_id)
        return await act(
            request, call_id, lambda u, _f: rounds.delete_round(u.id, RoundId(round_id))
        )

    @router.post("/rounds/{round_id}/release")
    async def release(request: Request, round_id: str) -> Response:
        """An organizer shows authors the reviews handed in so far (ADR 0028)."""
        if feedback is None:
            raise NotFound
        service = feedback
        call_id = await run(call_of_sync, current_user(request), round_id)

        def action(u: User, _f: FormData) -> str:
            service.release(u.id, RoundId(round_id))
            return "Authors can now read the reviews handed in so far. peerview.it emailed them."

        return await act(request, call_id, action)

    @router.post("/rounds/{round_id}/allocate")
    async def allocate(request: Request, round_id: str) -> Response:
        call_id = await run(call_of_sync, current_user(request), round_id)

        def action(u: User, _f: FormData) -> str:
            report = rounds.allocate(u.id, RoundId(round_id))
            note = f"Allocated {report.created} review{'' if report.created == 1 else 's'}."
            if report.gaps:
                note += f" {len(report.gaps)} submission(s) have fewer reviewers than asked for."
            return note

        return await act(request, call_id, action)

    @router.post("/rounds/{round_id}/tasks")
    async def add_task(request: Request, round_id: str) -> Response:
        call_id = await run(call_of_sync, current_user(request), round_id)

        def action(u: User, f: FormData) -> None:
            rounds.add_task(
                u.id,
                RoundId(round_id),
                SubmissionId(kit.text(f, "submission_id")),
                parse_party(kit.text(f, "reviewer")),
            )

        return await act(request, call_id, action)

    @router.post("/rounds/{round_id}/tasks/{task_id}/delete")
    async def remove_task(request: Request, round_id: str, task_id: str) -> Response:
        call_id = await run(call_of_sync, current_user(request), round_id)
        return await act(request, call_id, lambda u, _f: rounds.remove_task(u.id, TaskId(task_id)))

    @router.post("/rounds/{round_id}/invitations")
    async def invite_reviewer(request: Request, round_id: str) -> Response:
        """The call for reviewers: one personal link per reviewer, shown once."""
        form = await kit.checked_form(request)
        if form is None:
            return kit.forbidden()
        user = current_user(request)
        call_id = await run(call_of_sync, user, round_id)
        work = [SubmissionId(v) for v in form.getlist("submission_id") if isinstance(v, str)]
        email = kit.text(form, "email")
        try:
            _, token = await run(invitations.invite, user.id, RoundId(round_id), email, work)
        except InvalidInvitation as e:
            return await run(page, request, user, call_id, error=str(e), status=400)
        except ShareLimitReached:
            message = "You have reached the sharing limit of your plan."
            return await run(page, request, user, call_id, error=message, status=403)
        link = f"{kit.settings.origin}/i/{token}"
        fresh = FreshInvitation(round_id, link, token, email.strip().lower())
        return await run(page, request, user, call_id, fresh=fresh)

    @router.post("/rounds/{round_id}/invitations/send")
    async def send_invitation(request: Request, round_id: str) -> Response:
        """peerview.it mails the invitation that was just created, with a cover letter."""
        form = await kit.checked_form(request)
        if form is None:
            return kit.forbidden()
        user = current_user(request)
        call_id = await run(call_of_sync, user, round_id)
        token, email = kit.text(form, "token"), kit.text(form, "email")
        link = f"{kit.settings.origin}/i/{token}"
        fresh = FreshInvitation(round_id, link, token, email)
        try:
            sent_to = await run(
                invitations.send, user.id, RoundId(round_id), token, kit.text(form, "cover_letter")
            )
        except InvalidInvitation as e:
            return await run(page, request, user, call_id, error=str(e), fresh=fresh, status=400)
        except (MailError, OSError):
            message = "The email could not be sent. Copy the link and send it yourself."
            return await run(page, request, user, call_id, error=message, fresh=fresh, status=502)
        return await run(page, request, user, call_id, notice=f"Invitation sent to {sent_to}.")

    @router.post("/rounds/{round_id}/invitations/{invitation_id}/revoke")
    async def revoke_invitation(request: Request, round_id: str, invitation_id: str) -> Response:
        call_id = await run(call_of_sync, current_user(request), round_id)
        return await act(
            request,
            call_id,
            lambda u, _f: invitations.revoke(u.id, RoundId(round_id), invitation_id),
        )

    return router
