# 0020. Review without an account

Status: accepted (amends ADR 0017)

## Context
ADR 0017 required an account with a verified email before an invitation could be opened. A reviewer who got a link had to sign up, wait for a mail, confirm the address, open the link again and only then see the work. Every step before the first review loses people, and a reviewer gets nothing out of an account until they have reviewed. The product owner decided: **reviewers do not need an account to review. peerview.it invites them to join after the review is done.**

The invitation link is already a personal secret: at least 128 bits, bound to one address, mailed to that address by peerview.it or handed over by the organizer who trusts the person, revocable and expiring. Holding it is as much proof as the organizer asked for.

## Decision
- **A guest reviewer.** Opening an invitation without being signed in offers **Start reviewing** with an optional name. peerview.it creates a *guest*: a `User` with no email, no password and no external identity (`User.is_guest`). The guest is admitted as a Reviewer member, gets the invitation's review tasks and a session. Nothing else changes: the review workspace, autosave, comments and anonymity work as for anyone.
- **One guest per invitation.** The invitation records the guest that accepted it (`accepted_by`). Claiming it is atomic (`claim_invitation`: `UPDATE ... WHERE accepted_by IS NULL`), so a double click or two browsers make one guest. Opening the same link again later, on any device, continues as that guest; that is how a guest who lost the session gets back to the work. The link remains the guest's key until the guest joins.
- **An address that already has an account logs in.** If the invited address belongs to an account, or an account already accepted the invitation, the link never opens it as a guest. The page asks to log in.
- **Accounts no longer need a verified email to review.** Signed-in people still open only invitations for their own address. The operator's verification policy decides the rest: its default is now empty.
- **The operator can turn it off.** Listing `review` or `join` in `[policy] require_verified_email_for` brings back the ADR 0017 behaviour: no guests, and an account with a confirmed address is required to review.
- **Invited to join after reviewing.** When the guest has submitted the review (or, with no rubric to submit, has commented on the work), the workspace thanks them and offers **Join peerview.it**. Joining (`/account/new`) takes a password and optionally a name; the email is the invited address, set but unverified, and peerview.it mails a confirmation link. The guest's id does not change, so every review, comment and membership stays theirs. If the address meanwhile got an account, joining is refused and the guest's reviews stay with the invitation.
- **What a guest cannot do.** A guest cannot create an organization, request a review or reach the account page; those lead to **Join peerview.it**. The navigation shows *Your reviews* and *Join peerview.it*, and the join page has a log-out button for shared computers.

## Consequences
- The first review needs one click after the link, with no mail round trip. This serves the hosted-first goal of a first review round within minutes (ADR 0005).
- The organizer sees the guest's name, or the part of the address before `@` when no name was given, as today.
- A link forwarded by the reviewer gives the receiver that reviewer's tasks. That was already true of the account flow for anyone who could read the mailbox; the organizer can revoke the invitation. A guest's work is never shown to another invitation's guest: a guest session opening another link is treated as signed out.
- Guests who never join remain as users without an email. They hold no personal data beyond an optional name. Cleaning them up belongs to the data-retention work.
- Glossary: **Guest reviewer**. ADR 0017's rule "the email must match the invitation and be verified, whatever the operator's verification policy says" is replaced by this ADR.
