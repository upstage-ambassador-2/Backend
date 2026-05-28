"""add history persona snapshots

Revision ID: 20260528_0003
Revises: 20260523_0002
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260528_0003"
down_revision: str | None = "20260523_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("history") as batch_op:
        batch_op.add_column(sa.Column("persona_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("persona_email", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("counterparty_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("counterparty_email", sa.String(length=320), nullable=True))

    op.execute(
        """
        UPDATE history
        SET persona_name = (
                SELECT personas.name FROM personas WHERE personas.id = history.persona_id
            ),
            persona_email = (
                SELECT personas.email FROM personas WHERE personas.id = history.persona_id
            ),
            counterparty_name = (
                SELECT personas.name FROM personas WHERE personas.id = history.persona_id
            ),
            counterparty_email = (
                SELECT personas.email FROM personas WHERE personas.id = history.persona_id
            )
        WHERE persona_id IS NOT NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("history") as batch_op:
        batch_op.drop_column("counterparty_email")
        batch_op.drop_column("counterparty_name")
        batch_op.drop_column("persona_email")
        batch_op.drop_column("persona_name")
