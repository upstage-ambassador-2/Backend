import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    picture_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    oauth_token: Mapped["OAuthToken | None"] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["SessionToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    personas: Mapped[list["Persona"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reply_contexts: Mapped[list["ReplyContext"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    history_items: Mapped[list["HistoryItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    draft_revision_messages: Mapped[list["DraftRevisionMessage"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    mail_format: Mapped["MailFormat | None"] = relationship(back_populates="user", cascade="all, delete-orphan")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="oauth_token")


class SessionToken(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class Persona(Base):
    __tablename__ = "personas"
    __table_args__ = (
        Index("ix_personas_user_created", "user_id", "created_at"),
        UniqueConstraint("user_id", "email", name="uq_personas_user_email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    relation: Mapped[str] = mapped_column(String(255), default="")
    tone: Mapped[str] = mapped_column(String(255), default="중립")
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(50), default="manual")
    email: Mapped[str | None] = mapped_column(String(320), index=True)

    role: Mapped[str] = mapped_column(String(255), default="")
    mbti: Mapped[str] = mapped_column(String(32), default="")
    avatar: Mapped[str] = mapped_column(String(32), default="")
    color: Mapped[str] = mapped_column(String(32), default="#dfe3da")
    keywords: Mapped[str] = mapped_column(Text, default="")
    avoid: Mapped[str] = mapped_column(Text, default="")
    prefer: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(255), default="이메일")
    tag_color: Mapped[str] = mapped_column(String(32), default="gray")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="personas")
    history_items: Mapped[list["HistoryItem"]] = relationship(back_populates="persona")


class MailFormat(Base):
    __tablename__ = "mail_formats"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    signature: Mapped[str] = mapped_column(Text, default="")
    greeting: Mapped[str] = mapped_column(Text, default="안녕하세요.")
    closing: Mapped[str] = mapped_column(Text, default="감사합니다.")
    structure: Mapped[str] = mapped_column(Text, default="인사 → 본문 → 요청 → 마무리")
    bullet_style: Mapped[str] = mapped_column(String(255), default="문단형 기본 · 목록 요청 시에만 사용")
    language: Mapped[str] = mapped_column(String(255), default="한국어 · 존댓말 기본")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="mail_format")


class ReplyContext(Base):
    __tablename__ = "reply_contexts"
    __table_args__ = (
        UniqueConstraint("user_id", "gmail_message_id", name="uq_reply_context_user_gmail"),
        Index("ix_reply_context_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(255), index=True)
    from_addr: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    raw_body: Mapped[str] = mapped_column(Text, default="")
    thread_id: Mapped[str | None] = mapped_column(String(255), index=True)
    message_id: Mapped[str | None] = mapped_column(Text)
    references: Mapped[str | None] = mapped_column(Text)
    date: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="reply_contexts")
    history_items: Mapped[list["HistoryItem"]] = relationship(back_populates="reply_context")


class HistoryItem(Base):
    __tablename__ = "history"
    __table_args__ = (Index("ix_history_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    brief: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[int] = mapped_column(Integer, default=3)
    length: Mapped[int] = mapped_column(Integer, default=3)
    persona_id: Mapped[str | None] = mapped_column(ForeignKey("personas.id", ondelete="SET NULL"), nullable=True)
    reply_context_id: Mapped[str | None] = mapped_column(ForeignKey("reply_contexts.id", ondelete="SET NULL"), nullable=True)
    persona_name: Mapped[str | None] = mapped_column(String(255))
    persona_email: Mapped[str | None] = mapped_column(String(320))
    counterparty_name: Mapped[str | None] = mapped_column(String(255))
    counterparty_email: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    gmail_message_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="history_items")
    persona: Mapped[Persona | None] = relationship(back_populates="history_items")
    reply_context: Mapped[ReplyContext | None] = relationship(back_populates="history_items")
    revision_messages: Mapped[list["DraftRevisionMessage"]] = relationship(
        back_populates="history",
        cascade="all, delete-orphan",
    )


class DraftRevisionMessage(Base):
    __tablename__ = "draft_revision_messages"
    __table_args__ = (
        Index("ix_draft_revision_history_created", "history_id", "created_at"),
        Index("ix_draft_revision_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    history_id: Mapped[str] = mapped_column(ForeignKey("history.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="draft_revision_messages")
    history: Mapped[HistoryItem] = relationship(back_populates="revision_messages")
