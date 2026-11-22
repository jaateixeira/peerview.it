"""When authors see the reviews of their work (ADR 0028).

A round's release rule decides, for each Submission, when its handed-in reviews reach the
authors. Seeing them all at once also hides who reviewed when. An organizer may release a
round early, whatever its rule. Drafts never reach anyone.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum


class ReleaseRule(StrEnum):
    COMPLETE_OR_DUE = "complete_or_due"  # when every review is in, or at the due time
    EACH = "each"  # as each review is handed in
    MANUAL = "manual"  # when an organizer releases them


RELEASE_OPTIONS: dict[str, str] = {
    ReleaseRule.COMPLETE_OR_DUE.value: "When every review is in, or at the due time",
    ReleaseRule.EACH.value: "As each review is handed in",
    ReleaseRule.MANUAL.value: "When an organizer releases them",
}
DEFAULT_RELEASE = ReleaseRule.COMPLETE_OR_DUE


def feedback_released(
    rule: ReleaseRule,
    *,
    now: datetime,
    closes_at: datetime | None,
    released_at: datetime | None,
    handed_in: int,
    expected: int,
) -> bool:
    """Whether the authors of one Submission may read its handed-in reviews."""
    if released_at is not None and now >= released_at:
        return True
    if rule is ReleaseRule.MANUAL:
        return False
    if rule is ReleaseRule.EACH:
        return handed_in > 0
    all_in = expected > 0 and handed_in >= expected
    return all_in or (closes_at is not None and now >= closes_at)
