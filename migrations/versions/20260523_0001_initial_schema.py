"""initial schema

Revision ID: 20260523_0001
Revises:
Create Date: 2026-05-23 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260523_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("picture_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.create_index(op.f("ix_users_google_sub"), "users", ["google_sub"], unique=True)

    op.create_table(
        "mail_formats",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("greeting", sa.Text(), nullable=False),
        sa.Column("closing", sa.Text(), nullable=False),
        sa.Column("structure", sa.Text(), nullable=False),
        sa.Column("bullet_style", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "oauth_tokens",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "personas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("relation", sa.String(length=255), nullable=False),
        sa.Column("tone", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("role", sa.String(length=255), nullable=False),
        sa.Column("mbti", sa.String(length=32), nullable=False),
        sa.Column("avatar", sa.String(length=32), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=False),
        sa.Column("avoid", sa.Text(), nullable=False),
        sa.Column("prefer", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(length=255), nullable=False),
        sa.Column("tag_color", sa.String(length=32), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "email", name="uq_personas_user_email"),
    )
    op.create_index(op.f("ix_personas_email"), "personas", ["email"], unique=False)
    op.create_index(op.f("ix_personas_user_id"), "personas", ["user_id"], unique=False)
    op.create_index("ix_personas_user_created", "personas", ["user_id", "created_at"], unique=False)

    op.create_table(
        "reply_contexts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=False),
        sa.Column("from_addr", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("raw_body", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("references", sa.Text(), nullable=True),
        sa.Column("date", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "gmail_message_id", name="uq_reply_context_user_gmail"),
    )
    op.create_index(op.f("ix_reply_contexts_gmail_message_id"), "reply_contexts", ["gmail_message_id"], unique=False)
    op.create_index(op.f("ix_reply_contexts_thread_id"), "reply_contexts", ["thread_id"], unique=False)
    op.create_index(op.f("ix_reply_contexts_user_id"), "reply_contexts", ["user_id"], unique=False)
    op.create_index("ix_reply_context_user_created", "reply_contexts", ["user_id", "created_at"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_sessions_token_hash"), "sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)

    op.create_table(
        "history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("tone", sa.Integer(), nullable=False),
        sa.Column("length", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.String(length=36), nullable=True),
        sa.Column("reply_context_id", sa.String(length=36), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reply_context_id"], ["reply_contexts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_history_user_id"), "history", ["user_id"], unique=False)
    op.create_index("ix_history_user_created", "history", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_history_user_created", table_name="history")
    op.drop_index(op.f("ix_history_user_id"), table_name="history")
    op.drop_table("history")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_token_hash"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_reply_context_user_created", table_name="reply_contexts")
    op.drop_index(op.f("ix_reply_contexts_user_id"), table_name="reply_contexts")
    op.drop_index(op.f("ix_reply_contexts_thread_id"), table_name="reply_contexts")
    op.drop_index(op.f("ix_reply_contexts_gmail_message_id"), table_name="reply_contexts")
    op.drop_table("reply_contexts")
    op.drop_index("ix_personas_user_created", table_name="personas")
    op.drop_index(op.f("ix_personas_user_id"), table_name="personas")
    op.drop_index(op.f("ix_personas_email"), table_name="personas")
    op.drop_table("personas")
    op.drop_table("oauth_tokens")
    op.drop_table("mail_formats")
    op.drop_index(op.f("ix_users_google_sub"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
