"""add draft revision messages

Revision ID: 20260529_0004
Revises: 20260528_0003
Create Date: 2026-05-29 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260529_0004"
down_revision: str | None = "20260528_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "draft_revision_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("history_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["history_id"], ["history.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_draft_revision_messages_history_id", "draft_revision_messages", ["history_id"])
    op.create_index("ix_draft_revision_messages_user_id", "draft_revision_messages", ["user_id"])
    op.create_index("ix_draft_revision_history_created", "draft_revision_messages", ["history_id", "created_at"])
    op.create_index("ix_draft_revision_user_created", "draft_revision_messages", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_draft_revision_user_created", table_name="draft_revision_messages")
    op.drop_index("ix_draft_revision_history_created", table_name="draft_revision_messages")
    op.drop_index("ix_draft_revision_messages_user_id", table_name="draft_revision_messages")
    op.drop_index("ix_draft_revision_messages_history_id", table_name="draft_revision_messages")
    op.drop_table("draft_revision_messages")
