# 0028. Feedback received: release rules and the IdentityMask

Status: accepted (M6 step 1; step 2 adds author responses and the later-round view)

## Context
Until now authors could not read the reviews people wrote about their work, and each page turned people into names its own way. M6 asks for directional anonymity applied everywhere through one service, rules for when authors see reviews, a "feedback received" page, notifications and leak tests (plan scenario 3). The founder chose the release rule: authors see the reviews when every review is in, or at the due time, whichever comes first, and an organizer can release them earlier. M6 comes in two steps; this is the first.

## Decision
- **One IdentityMask.** `application/identity_mask.py` is the only code that reads a person's or a group's name for display. Given a round's `AnonymityPolicy` and the viewer's place (organizer, author, reviewer), it gives the real name or a pseudonym: **Anonymous author**, or **Reviewer A**, **Reviewer B**, ... (then AA, AB). The calls, rounds, reviews and feedback services use it; organizers always see real names.
- **Pseudonyms are stable for one Submission within a round**: its reviewers are lettered in the order of their task ids, which carry no meaning. A group that reviews is one reviewer and gets one letter.
- **Release rules per round** (`ReviewRound.release_key`):
  - *When every review is in, or at the due time* (default, `complete_or_due`). Seeing them all at once also hides who reviewed when.
  - *As each review is handed in* (`each`).
  - *When an organizer releases them* (`manual`).
  An organizer can **show authors the reviews now** whatever the rule (`released_at`). Drafts never reach authors.
- **Released feedback stays released.** The first time a Submission's handed-in reviews reach its authors, peerview.it records it (`feedback_releases`, migration 0017). Adding a reviewer later, or moving the due time, does not take feedback back. At the due time a sweep (every five minutes, with the existing clean-up) marks default rounds released.
- **One email per Submission per round**, when its feedback is first released with at least one review in it, to every author with a confirmed address (all members of an author group). It names the work and links to its page; it never names reviewers. A failing mail server never stops a reviewer from handing in.
- **Feedback received.** `/spaces/{id}/feedback` lists my work that reviewers were given; `/submissions/{id}/feedback` shows each round's released reviews: the answers in words (a new optional `ShowsAnswers` protocol for criterion plugins, which all four built-ins implement) and the comments with the passage they are pinned to. Organizers see every handed-in review, released or not, with names. Nobody else sees the page.
- **Reviewers see the author only when the policy allows** ("By Anonymous author" otherwise), on the review page and nowhere else.
- **Files carry no names.** The work is served as `work`, never its uploaded file name. When the round hides authors, reviewers get a PDF without its document properties, XMP metadata or the names on its comments (an optional `HidesAuthors` protocol for artifact plugins). If a PDF cannot be cleaned it is not shown, rather than shown with the names.
- **Leak tests**: unit tests of the mask and the cleaned PDF; web tests that no page, file or mail under double-anonymous review names the other side; acceptance scenario 3 (a member reviews a group's work, and the group reads the review).

## Consequences
- Authors finally read their reviews, and organizers decide when.
- Names that authors type into the work itself (a title page, a URL of their own web page) still show. Help text should say so; detecting them is out of scope.
- Office files are not accepted yet (ADR 0022), so only PDFs need cleaning. The cleaning runs on each request for the file; cache it if large PDFs make the review page slow.
- With *as each is handed in*, the email goes once; later reviews appear on the page without another email.
- Organizers who add a reviewer by hand before release may shift the letters of that Submission's reviewers; after release, letters can still move if a reviewer is added. Step 2 may store the letters.
- Step 2: author responses with a revision, and the round-2 view (scenario 5).
