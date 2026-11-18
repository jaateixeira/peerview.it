"""review requests prepared by AI assistants (ADR 0023)

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prepared_requests",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prepared_requests_expires_at", "prepared_requests", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_prepared_requests_expires_at", table_name="prepared_requests")
    op.drop_table("prepared_requests")
