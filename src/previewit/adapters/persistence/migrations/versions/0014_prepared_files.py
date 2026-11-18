"""a visitor's file, kept an hour while they sign in (ADR 0024)

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prepared_requests") as batch:
        batch.add_column(sa.Column("file_name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("file_content", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prepared_requests") as batch:
        batch.drop_column("file_content")
        batch.drop_column("file_name")
