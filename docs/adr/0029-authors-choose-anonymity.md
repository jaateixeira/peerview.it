# 0029. Authors choose anonymity when they ask for reviews

Status: accepted (follows ADR 0028)

## Context
The founder asked that both the editor (the Organizer) and the author can choose single-anonymous review (authors do not know the reviewers) or double-anonymous review (reviewers do not know the author either). Organizers already chose anonymity for each round. In *Request a review* (ADR 0018) the author chose nothing: the round got the default, and three things defeated anonymity:
- the author organizes her own request, and organizers see every name;
- the invitation is sent in the author's name;
- the space's organization is named after her, and reviewers who join a space see its member list.

## Decision
- **Request a review offers two choices** under *Names*: *Reviewers see my name* (reviewers hidden, the default) and *Hide my name from the reviewers too* (double-anonymous). Either way the author does not see which reviewer wrote which review. The MCP tool takes the same choice as `hide_author` (ADR 0023), and a form kept for a visitor keeps it (ADR 0024).
- **Conflict of interest: an organizer is the author of her own work.** For reviews of work she wrote (alone or in her group), peerview.it treats her as its author, not as an organizer:
  - the Reviews received page shows only released reviews, under pseudonyms;
  - she cannot open those review tasks;
  - on the round page those reviewers appear as Reviewer A, B (open rounds still name them).
  This applies in every space, not only to requests.
- **An author who invites is not named when the round hides authors.**
  - The invitation email says *An author invited you* and *The author writes*, and explains that the review is anonymous both ways.
  - The invitation page shows neither her name nor her organization's.
  - An organizer who is not an author is still named, as in a teacher's double-anonymous round.
- **Anonymous spaces.** A space is anonymous if a round in it hides authors from reviewers or reviewers from one another. People who do not manage its members see there:
  - no member list (only themselves);
  - only their own group;
  - no organization name, on the space page, in the list of spaces, or in the list of organizations they are a member of.

## Consequences
- The author still knows whom she invited, because she typed their addresses; she does not learn who wrote what. Single-anonymous review means more with two or more reviewers.
- Students in a class with a double-anonymous round no longer see their classmates listed on the space page.
- An author can still reveal herself in the work or in the few words to reviewers; the form says so. peerview.it removes her name from a PDF's properties (ADR 0028).
- An invitation that names nobody could be misused to send unwanted mail. The sender still needs a confirmed address, the sharing limit applies, and the operator can see who sent it.
