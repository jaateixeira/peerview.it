# 0024. Fill in Request a review before signing in

Status: accepted

## Context
*Request a review* asked a newcomer to sign up before showing the form, so the first thing they met was an account to create, before they had seen what Previewit does. The target is a first review round in under ten minutes (ADR 0005), and reviewers already need no account (ADR 0020). The founder decided that people may fill in the form first; a file they chose is kept for one hour, then deleted.

The obstacle is the sign-in itself. Logging in, signing up, and Google, Apple or HAKA all leave the page, and a browser forgets a chosen file when the page changes. So the form must be kept on the server while the person signs in.

## Decision
- **Open the form.** `GET /review/new` shows the form to everyone, with links to log in or create an account that come back to it. Checking and importing email addresses needs no account: it is parsing, with no network and no storage.
- **Send it out keeps the form.** For a visitor, *Send it out* checks what is cheap to check (the addresses, that there is one thing to review, the kind and size of a file) and keeps the form as a **Prepared request** of the visitor kind (ADR 0023's store): title, address or text, reviewers, message, due date and time, and the file. Then it sends the visitor to log in, with the prepared request's link as the page to come back to. The login and sign-up pages say the request is saved. All sign-in routes return there (Google, Apple and HAKA keep the page in the session).
- **One hour, then deleted.** A visitor's form, file included, expires after one hour, and its link stops working. A loop in the running site deletes expired prepared requests every five minutes, so the file is gone soon after its hour even if nobody asks for it. Sending the request deletes it at once.
- **Back on the form, filled in.** After signing in, the person sees *Request a review* as they left it ("Here is your request as you left it") with the kept file named. Sending without choosing another file sends the kept one; a new file replaces it. Nothing is created or sent before this, and the usual checks, limits and the verified-email rule for mailing apply.
- **No fetching for visitors.** A web page's address is checked only after signing in (ADR 0022 keeps fetching for accounts): the field says so, and the check runs when the kept form opens.
- **Bounded.** At most 10 kept forms per client address every 10 minutes (in each worker), at most 200 files waiting site-wide (2 GB at the very most, for an hour), and the existing limits on size and on prepared requests waiting.
- **Guests join first.** A guest reviewer (ADR 0020) is still sent to *Join Previewit* before requesting reviews.

## Consequences
- Strangers can make Previewit hold a file for up to an hour. The limits above cap it; nginx can add a site-wide limit on `POST /review`.
- A person who never signs in leaves nothing behind after the hour.
- Glossary: **Prepared request** now has two kinds: from an AI assistant (7 days) and from a visitor (1 hour, with a file).
