"""when authors see the reviews of their work (ADR 0028)

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("review_rounds") as batch:
        batch.add_column(
            sa.Column(
                "release_key", sa.String(32), nullable=False, server_default="complete_or_due"
            )
        )
        batch.add_column(sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "feedback_releases",
        sa.Column("round_id", sa.String(64), primary_key=True),
        sa.Column("submission_id", sa.String(64), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["round_id", "org_id"],
            ["review_rounds.id", "review_rounds.org_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id", "org_id"],
            ["submissions.id", "submissions.org_id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("feedback_releases")
    with op.batch_alter_table("review_rounds") as batch:
        batch.drop_column("released_at")
        batch.drop_column("release_key")
