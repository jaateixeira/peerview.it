"""Process 2 and 3 (ADR 0017): the call for reviewers, one personal invitation per reviewer."""

from datetime import timedelta
from itertools import count

import pytest

from peerview.application.artifacts import Upload
from peerview.application.auth import AuthService, EmailTaken, NotAGuest, WeakPassword
from peerview.application.calls import ShareLimitReached
from peerview.application.invitations import (
    AccountExists,
    InvalidInvitationLink,
    InvitationsService,
    WrongEmail,
)
from peerview.application.ports import MailError
from peerview.application.tenancy import Forbidden, NotFound, VerificationRequired
from peerview.domain.identity import Email, User, UserId
from peerview.domain.invitations import InvalidInvitation
from peerview.domain.policy import DEFAULT_POLICY, Action, VerificationPolicy
from peerview.domain.tenancy import Role
from tests.unit.test_auth_service import FakeHasher as PlainHasher
from tests.unit.test_calls_service import PAT, SAM, SUE, TINA
from tests.unit.test_rounds_service import RoundsWorld
from tests.unit.test_tenancy_service import AVA, BOB, ZED

LARS = UserId("lars")  # an outsider whose email is not verified
RITA = UserId("rita")  # an outsider: no membership anywhere, a verified email


class Outbox:
    """Records the mails the service sends."""

    def __init__(self, broken: bool = False) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.broken = broken

    def send(self, to: str, subject: str, body: str) -> None:
        if self.broken:
            raise MailError("smtp is down")
        self.sent.append((to, subject, body))


class InviteWorld(RoundsWorld):
    def __init__(self, *args, entitlements=None, mail=None, verified_organizer=True, **kw):
        super().__init__(*args, **kw)
        self.mail = mail or Outbox()
        if verified_organizer:
            self.users.mark_email_verified(TINA, Email(f"{TINA}@x.fi"))
        for uid, verified in ((RITA, True), (UserId("lars"), False)):
            self.users.add_user(
                User(uid, uid.title(), Email(f"{uid}@x.fi"), verified, frozenset(), False), None
            )
        self._ids = count(1)
        self._entitlements_for_invites = entitlements or self.c._entitlements
        self.iv = self.invitations()
        self.work_by = self.work(SAM, SUE)  # two essays to review
        self.r = self.round()

    def invitations(self, policy: VerificationPolicy = DEFAULT_POLICY) -> InvitationsService:
        return InvitationsService(
            self.rr._repo,
            self.c._repo,
            self.t,
            self.t._repo,
            self.users,
            self._entitlements_for_invites,
            lambda: f"v{next(self._ids)}",
            self.clock,
            mailer=self.mail,
            base_url="https://peerview.test/",
            policy=policy,
        )

    def titles(self, user, space=None):
        return sorted(
            t.submission_title for t in self.rr.my_tasks(user, space or self.call.space_id)
        )


@pytest.fixture
def w() -> InviteWorld:
    return InviteWorld()


# --- the organizer sends the call for reviewers -------------------------------------------------


def test_an_organizer_invites_a_reviewer_and_gets_a_link_token_once(w: InviteWorld):
    inv, token = w.iv.invite(TINA, w.r.id, " Rita@X.fi ", [w.work_by[SAM].id])
    assert token and token not in inv.id  # only the hash is stored
    assert inv.email == Email("rita@x.fi")
    assert inv.submission_ids == (w.work_by[SAM].id,)
    [view] = w.iv.invitations(TINA, w.r.id)
    assert (view.email, view.status, view.work) == ("rita@x.fi", "waiting", ["sam essay"])


def test_only_organizers_invite_reviewers(w: InviteWorld):
    for user in (SAM, AVA):
        with pytest.raises(Forbidden):
            w.iv.invite(user, w.r.id, "rita@x.fi")
        with pytest.raises(Forbidden):
            w.iv.invitations(user, w.r.id)
    with pytest.raises(NotFound):
        w.iv.invite(BOB, w.r.id, "rita@x.fi")
    with pytest.raises(NotFound):
        w.iv.invite(ZED, w.r.id, "rita@x.fi")


def test_invitations_are_validated(w: InviteWorld):
    with pytest.raises(InvalidInvitation):
        w.iv.invite(TINA, w.r.id, "not an email")
    other_call = w.c.create_call(
        TINA, w.call.space_id, title="Other", artifact_type="text", published=True
    )
    foreign = w.c.submit(PAT, other_call.id, title="elsewhere", upload=Upload(text="x"))
    with pytest.raises(NotFound):
        w.iv.invite(TINA, w.r.id, "rita@x.fi", [foreign.id])
    w.iv.invite(TINA, w.r.id, "rita@x.fi")
    with pytest.raises(InvalidInvitation):  # one live invitation per person and round
        w.iv.invite(TINA, w.r.id, "RITA@x.fi")


def test_a_closed_round_cannot_be_invited_to(w: InviteWorld):
    closed = w.round(opens_at=w.clock.now - timedelta(days=2), closes_at=w.clock.now - timedelta(1))
    with pytest.raises(InvalidInvitation):
        w.iv.invite(TINA, closed.id, "rita@x.fi")


def test_invitations_count_toward_the_share_limit(w: InviteWorld):
    class Limited:
        def may_create_share(self, user_id, shares_so_far):
            return shares_so_far < 2

    limited = InviteWorld(entitlements=Limited())
    limited.iv.invite(TINA, limited.r.id, "a@x.fi")
    limited.iv.invite(TINA, limited.r.id, "b@x.fi")
    with pytest.raises(ShareLimitReached):
        limited.iv.invite(TINA, limited.r.id, "c@x.fi")


def test_the_organizer_revokes_an_invitation(w: InviteWorld):
    inv, token = w.iv.invite(TINA, w.r.id, "rita@x.fi", [w.work_by[SAM].id])
    w.iv.revoke(TINA, w.r.id, inv.id)
    assert w.iv.invitations(TINA, w.r.id)[0].status == "revoked"
    assert w.iv.preview(token) is None
    with pytest.raises(InvalidInvitationLink):
        w.iv.accept(RITA, token)
    with pytest.raises(Forbidden):
        w.iv.revoke(SAM, w.r.id, inv.id)


# --- the reviewer opens it (process 3) ------------------------------------------------------------


def test_a_stranger_with_the_invited_verified_email_becomes_a_reviewer_with_tasks(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi", [w.work_by[SAM].id, w.work_by[SUE].id])
    assert w.iv.preview(token).call_title == w.call.title  # type: ignore[union-attr]
    accepted = w.iv.accept(RITA, token)
    assert (accepted.created, accepted.skipped) == (2, 0)
    assert accepted.space_id == w.call.space_id
    assert w.t.space_view(RITA, w.call.space_id).roles == frozenset({Role.REVIEWER})
    assert w.titles(RITA) == ["sam essay", "sue essay"]
    assert w.iv.invitations(TINA, w.r.id)[0].status == "accepted"


def test_opening_it_twice_is_harmless(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi", [w.work_by[SAM].id])
    w.iv.accept(RITA, token)
    again = w.iv.accept(RITA, token)
    assert (again.created, again.skipped) == (0, 0)
    assert w.titles(RITA) == ["sam essay"]


def test_the_invitation_belongs_to_its_email(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi", [w.work_by[SAM].id])
    with pytest.raises(WrongEmail) as caught:
        w.iv.accept(ZED, token)  # zed's address is another one
    assert caught.value.hint == "r***@x.fi"
    assert not w.t.my_spaces(ZED)


def test_an_unverified_email_must_be_confirmed_first_when_the_operator_asks(w: InviteWorld):
    strict = w.invitations(VerificationPolicy(frozenset({Action.REVIEW})))
    _, token = strict.invite(TINA, w.r.id, "lars@x.fi", [w.work_by[SAM].id])
    assert strict.readiness(LARS, token) == "confirm_email"
    with pytest.raises(VerificationRequired):
        strict.accept(LARS, token)
    assert not w.t.my_spaces(LARS)
    assert not strict.guests_allowed()
    with pytest.raises(VerificationRequired):
        strict.start_as_guest(token)


def test_by_default_an_unverified_account_with_that_address_reviews(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "lars@x.fi", [w.work_by[SAM].id])
    assert w.iv.readiness(LARS, token) == "ready"
    w.iv.accept(LARS, token)
    assert w.titles(LARS) == ["sam essay"]


# -- reviewing without an account (ADR 0020) ---------------------------------------------------


def test_a_visitor_without_an_account_reviews_as_a_guest(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "nina@x.fi", [w.work_by[SAM].id])
    guest_id, accepted = w.iv.start_as_guest(token, "  Nina   Newcomer ")
    guest = w.users.get(guest_id)
    assert guest is not None and guest.is_guest and guest.display_name == "Nina Newcomer"
    assert accepted.created == 1 and w.titles(guest_id) == ["sam essay"]
    assert w.t.space_view(guest_id, w.call.space_id).roles == frozenset({Role.REVIEWER})
    [view] = w.iv.invitations(TINA, w.r.id)
    assert view.status == "accepted" and view.accepted_by == "Nina Newcomer"
    assert w.iv.readiness(guest_id, token) == "ready"
    w.iv.accept(guest_id, token)  # opening it again as the guest changes nothing
    assert w.titles(guest_id) == ["sam essay"]


def test_a_guest_without_a_name_is_named_after_the_address(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "nina@x.fi", [w.work_by[SAM].id])
    guest_id, _ = w.iv.start_as_guest(token)
    assert w.users.get(guest_id).display_name == "nina"  # type: ignore[union-attr]


def test_the_same_link_continues_as_the_same_guest(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "nina@x.fi", [w.work_by[SAM].id])
    first, _ = w.iv.start_as_guest(token, "Nina")
    again, accepted = w.iv.start_as_guest(token, "Someone else")  # another browser, later
    assert again == first and accepted.created == 0
    assert w.titles(first) == ["sam essay"]


def test_each_invitation_has_its_own_guest(w: InviteWorld):
    _, one = w.iv.invite(TINA, w.r.id, "nina@x.fi", [w.work_by[SAM].id])
    _, two = w.iv.invite(TINA, w.round().id, "nina@x.fi", [w.work_by[SUE].id])  # round 2
    first, _ = w.iv.start_as_guest(one)
    second, _ = w.iv.start_as_guest(two)
    assert first != second
    assert w.titles(first) == ["sam essay"] and w.titles(second) == ["sue essay"]
    assert w.iv.readiness(first, two) == "anonymous"  # another invitation's guest: signed out
    with pytest.raises(InvalidInvitationLink):
        w.iv.accept(first, two)


def test_an_address_with_an_account_logs_in_instead(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi", [w.work_by[SAM].id])
    with pytest.raises(AccountExists) as caught:
        w.iv.start_as_guest(token)
    assert caught.value.hint == "r***@x.fi"
    w.iv.accept(RITA, token)  # rita logs in and opens it
    with pytest.raises(AccountExists):
        w.iv.start_as_guest(token)  # the link never opens her account


def test_an_invitation_is_claimed_once(w: InviteWorld):
    inv, token = w.iv.invite(TINA, w.r.id, "nina@x.fi", [w.work_by[SAM].id])
    guest_id, _ = w.iv.start_as_guest(token)
    assert not w.rr._repo.claim_invitation(inv.id, UserId("someone-else"))
    assert [i.id for i in w.rr._repo.invitations_accepted_by(guest_id)] == [inv.id]
    assert w.iv.invitation_of_guest(guest_id).email.value == "nina@x.fi"  # type: ignore[union-attr]
    assert w.iv.invitation_of_guest(RITA) is None  # not a guest


def test_a_guest_joins_with_a_password_and_keeps_the_reviews(w: InviteWorld):
    auth = AuthService(w.users, PlainHasher(), lambda: "u-new")
    _, token = w.iv.invite(TINA, w.r.id, "nina@x.fi", [w.work_by[SAM].id])
    guest_id, _ = w.iv.start_as_guest(token, "Nina")
    with pytest.raises(WeakPassword):
        auth.join_as_guest(guest_id, Email("nina@x.fi"), "short", "Nina")
    joined = auth.join_as_guest(guest_id, Email("nina@x.fi"), "long enough password", " Nina N ")
    assert not joined.is_guest and joined.display_name == "Nina N"
    assert joined.email == Email("nina@x.fi") and not joined.email_verified
    assert auth.login_with_password("nina@x.fi", "long enough password").id == guest_id
    assert w.titles(guest_id) == ["sam essay"]
    with pytest.raises(NotAGuest):
        auth.join_as_guest(guest_id, Email("nina@x.fi"), "long enough password", "Nina")
    with pytest.raises(AccountExists):
        w.iv.start_as_guest(token)  # she has an account now: she logs in


def test_a_guest_cannot_take_an_address_that_has_an_account(w: InviteWorld):
    auth = AuthService(w.users, PlainHasher(), lambda: "u-new")
    _, token = w.iv.invite(TINA, w.r.id, "nina@x.fi", [w.work_by[SAM].id])
    guest_id, _ = w.iv.start_as_guest(token)
    auth.register_with_password("nina@x.fi", "long enough password", "The real Nina")
    with pytest.raises(EmailTaken):
        auth.join_as_guest(guest_id, Email("nina@x.fi"), "another long password", "Nina")
    assert w.users.get(guest_id).is_guest  # type: ignore[union-attr]


def test_a_guest_must_join_before_making_an_organization(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "nina@x.fi", [w.work_by[SAM].id])
    guest_id, _ = w.iv.start_as_guest(token)
    with pytest.raises(Forbidden):
        w.t.create_organization(guest_id, "Nina's club", "general")


def test_an_existing_author_gains_the_reviewer_role_and_keeps_theirs(w: InviteWorld):
    w.t.admit(RITA, w.call.space_id, {Role.AUTHOR})
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi", [w.work_by[SAM].id])
    w.iv.accept(RITA, token)
    assert w.t.space_view(RITA, w.call.space_id).roles == frozenset({Role.AUTHOR, Role.REVIEWER})


def test_nobody_reviews_their_own_work_through_an_invitation(w: InviteWorld):
    w.t.admit(RITA, w.call.space_id, {Role.AUTHOR})  # rita is a member and an author
    mine = w.essay(RITA, title="rita essay")
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi", [mine.id, w.work_by[SAM].id])
    accepted = w.iv.accept(RITA, token)
    assert (accepted.created, accepted.skipped) == (1, 1)
    assert w.titles(RITA) == ["sam essay"]


def test_an_invitation_without_work_only_admits(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi")
    assert w.iv.accept(RITA, token).created == 0
    assert w.t.space_view(RITA, w.call.space_id).roles == frozenset({Role.REVIEWER})


def test_expired_unknown_and_foreign_tokens_are_refused(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi", ttl=timedelta(days=1))
    w.clock.now += timedelta(days=2)
    assert w.iv.preview(token) is None
    for bad in (token, "nonsense", ""):
        with pytest.raises(InvalidInvitationLink):
            w.iv.accept(RITA, bad)
    assert w.iv.invitations(TINA, w.r.id)[0].status == "expired"


def test_an_invitation_to_a_round_that_has_closed_is_refused(w: InviteWorld):
    soon = w.round(closes_at=w.clock.now + timedelta(days=1))
    _, token = w.iv.invite(TINA, soon.id, "rita@x.fi", [w.work_by[SAM].id])
    w.clock.now += timedelta(days=2)
    with pytest.raises(InvalidInvitationLink):
        w.iv.accept(RITA, token)


def test_deleting_a_round_deletes_its_invitations(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi")
    w.rr.delete_round(TINA, w.r.id)
    assert w.iv.preview(token) is None


# --- peerview.it sends the invitation, with the organizer's cover letter -----------------------


def test_peerview_mails_the_invitation_with_the_cover_letter(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi", [w.work_by[SAM].id])
    w.iv.send(TINA, w.r.id, token, "  Dear Rita,\nyour view on my course matters.  ")
    [(to, subject, body)] = w.mail.sent
    assert to == "rita@x.fi" and w.call.title in subject
    assert "Dear Rita,\nyour view on my course matters." in body
    assert f"https://peerview.test/i/{token}" in body
    assert "Tina" in body and "rita@x.fi" in body  # who asked, and which address works
    assert w.iv.invitations(TINA, w.r.id)[0].sent


def test_the_cover_letter_is_optional_but_not_unlimited(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi")
    with pytest.raises(InvalidInvitation):
        w.iv.send(TINA, w.r.id, token, "x" * 2001)
    assert w.mail.sent == [] and not w.iv.invitations(TINA, w.r.id)[0].sent
    w.iv.send(TINA, w.r.id, token, "")
    assert f"/i/{token}" in w.mail.sent[0][2]


def test_an_invitation_is_mailed_once(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi")
    w.iv.send(TINA, w.r.id, token, "Hello")
    with pytest.raises(InvalidInvitation):
        w.iv.send(TINA, w.r.id, token, "Hello again")
    assert len(w.mail.sent) == 1


def test_only_a_verified_organizer_of_that_round_can_send(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi")
    for user in (SAM, AVA):
        with pytest.raises(Forbidden):
            w.iv.send(user, w.r.id, token, "")
    with pytest.raises(NotFound):
        w.iv.send(ZED, w.r.id, token, "")
    other = w.round()
    with pytest.raises(InvalidInvitationLink):  # a token belongs to its own round
        w.iv.send(TINA, other.id, token, "")
    with pytest.raises(InvalidInvitationLink):
        w.iv.send(TINA, w.r.id, "nonsense", "")
    assert w.mail.sent == []
    unverified = InviteWorld(verified_organizer=False)
    _, t2 = unverified.iv.invite(TINA, unverified.r.id, "rita@x.fi")
    with pytest.raises(VerificationRequired):  # the mail goes out in their name
        unverified.iv.send(TINA, unverified.r.id, t2, "")
    assert unverified.mail.sent == []


def test_a_revoked_or_used_invitation_is_not_mailed(w: InviteWorld):
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi")
    w.iv.accept(RITA, token)
    with pytest.raises(InvalidInvitation):
        w.iv.send(TINA, w.r.id, token, "")
    inv2, token2 = w.iv.invite(TINA, w.r.id, "pat@x.fi")
    w.iv.revoke(TINA, w.r.id, inv2.id)
    with pytest.raises(InvalidInvitationLink):
        w.iv.send(TINA, w.r.id, token2, "")
    assert w.mail.sent == []


def test_a_mail_that_fails_leaves_the_invitation_usable_and_unsent():
    w = InviteWorld(mail=Outbox(broken=True))
    _, token = w.iv.invite(TINA, w.r.id, "rita@x.fi")
    with pytest.raises(MailError):
        w.iv.send(TINA, w.r.id, token, "Hello")
    assert not w.iv.invitations(TINA, w.r.id)[0].sent
    w.mail.broken = False
    w.iv.send(TINA, w.r.id, token, "Hello")  # trying again is allowed
    assert w.iv.accept(RITA, token).created == 0
