from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.generation_options import GENERATION_LENGTH_LABELS, GENERATION_TONE_LABELS, normalize_generation_scale


PersonaTone = Literal["매우 격식", "격식", "중립", "친근", "매우 친근"]


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    pictureUrl: str | None = None
    createdAt: datetime


class IntegrationStatus(BaseModel):
    gmail: bool
    contacts: bool
    slack: Literal["planned"] = "planned"
    notion: Literal["planned"] = "planned"


class MeOut(BaseModel):
    user: UserOut
    integrations: IntegrationStatus


class AuthStartIn(BaseModel):
    next: str | None = None


class AuthStartOut(BaseModel):
    url: str


class PersonaBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    relation: str = ""
    tone: PersonaTone = "중립"
    notes: str = ""
    email: EmailStr | None = None
    role: str = ""
    mbti: str = ""
    avatar: str = ""
    color: str = "#dfe3da"
    keywords: list[str] = []
    avoid: list[str] = []
    prefer: str = ""
    channel: str = "이메일"
    tagColor: str = "gray"


class PersonaCreate(PersonaBase):
    pass


class PersonaPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    relation: str | None = None
    tone: PersonaTone | None = None
    notes: str | None = None
    email: EmailStr | None = None
    role: str | None = None
    mbti: str | None = None
    avatar: str | None = None
    color: str | None = None
    keywords: list[str] | None = None
    avoid: list[str] | None = None
    prefer: str | None = None
    channel: str | None = None
    tagColor: str | None = None


class PersonaOut(PersonaBase):
    id: str
    source: str
    lastUsed: str
    createdAt: datetime
    updatedAt: datetime


class ContactImportIn(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class ContactImportOut(BaseModel):
    imported: int
    skipped: int
    personas: list[PersonaOut]


class MailFormatIn(BaseModel):
    signature: str | None = None
    greeting: str | None = None
    closing: str | None = None
    structure: str | None = None
    bulletStyle: str | None = None
    language: str | None = None


class MailFormatOut(BaseModel):
    signature: str
    greeting: str
    closing: str
    structure: str
    bulletStyle: str
    language: str
    updatedAt: datetime


class ReplyContextInline(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    gmailMessageId: str
    fromAddr: str = ""
    from_: str | None = Field(default=None, alias="from")
    subject: str = ""
    snippet: str = ""
    rawBody: str = ""
    threadId: str | None = None
    messageId: str | None = None
    references: str | None = None
    date: str | None = None

    @model_validator(mode="after")
    def sync_from_fields(self):
        if self.from_ and not self.fromAddr:
            self.fromAddr = self.from_
        if self.fromAddr and not self.from_:
            self.from_ = self.fromAddr
        return self


class ReplyContextOut(ReplyContextInline):
    id: str
    senderEmail: str | None = None
    senderName: str | None = None
    personaId: str | None = None
    persona: PersonaOut | None = None
    createdAt: datetime
    updatedAt: datetime


class GenerateIn(BaseModel):
    brief: str = ""
    tone: int = 3
    length: int = 3
    personaId: str | None = None
    persona_id: str | None = None
    replyContextId: str | None = None
    reply_context_id: str | None = None
    replyContext: ReplyContextInline | None = None

    @field_validator("tone", mode="before")
    @classmethod
    def normalize_tone(cls, value):
        return normalize_generation_scale(value, labels=GENERATION_TONE_LABELS, option_name="tone")

    @field_validator("length", mode="before")
    @classmethod
    def normalize_length(cls, value):
        return normalize_generation_scale(value, labels=GENERATION_LENGTH_LABELS, option_name="length")

    @property
    def persona_id_value(self) -> str | None:
        return self.personaId or self.persona_id

    @property
    def reply_context_id_value(self) -> str | None:
        return self.replyContextId or self.reply_context_id


class GeneratedDraft(BaseModel):
    subject: str
    body: str


class HistoryOut(BaseModel):
    id: str
    personaId: str | None
    replyContextId: str | None
    persona: PersonaOut | None = None
    replyContext: ReplyContextOut | None = None
    personaName: str | None = None
    personaEmail: str | None = None
    counterpartyName: str | None = None
    counterpartyEmail: str | None = None
    brief: str
    subject: str
    body: str
    status: str
    tone: str
    toneValue: int
    length: str
    lengthValue: int
    when: str
    createdAt: datetime
    sentAt: datetime | None = None
    subj: str
    prev: str


class GmailMessageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    threadId: str | None = None
    fromAddr: str
    from_: str | None = Field(default=None, alias="from")
    senderEmail: str | None = None
    senderName: str | None = None
    personaId: str | None = None
    persona: PersonaOut | None = None
    subject: str
    snippet: str
    date: str | None = None
    messageId: str | None = None
    references: str | None = None

    @model_validator(mode="after")
    def sync_from_fields(self):
        if self.from_ and not self.fromAddr:
            self.fromAddr = self.from_
        if self.fromAddr and not self.from_:
            self.from_ = self.fromAddr
        return self


class GmailMessagesPageOut(BaseModel):
    messages: list[GmailMessageOut]
    nextPageToken: str | None = None
    resultSizeEstimate: int | None = None
    limit: int
    hasMore: bool


class GmailMessageDetailOut(GmailMessageOut):
    rawBody: str
    replyContext: ReplyContextOut


class GmailSendIn(BaseModel):
    to: EmailStr | None = None
    cc: list[EmailStr] = []
    bcc: list[EmailStr] = []
    subject: str
    body: str
    historyId: str | None = None
    history_id: str | None = None
    replyContextId: str | None = None
    reply_context_id: str | None = None

    @property
    def history_id_value(self) -> str | None:
        return self.historyId or self.history_id

    @property
    def reply_context_id_value(self) -> str | None:
        return self.replyContextId or self.reply_context_id

    @field_validator("subject", "body")
    @classmethod
    def require_non_blank_content(cls, value: str, info):
        if not value.strip():
            label = "제목" if info.field_name == "subject" else "본문"
            raise ValueError(f"{label}은 비워둘 수 없습니다.")
        return value


class GmailSendOut(BaseModel):
    id: str
    threadId: str | None = None
    status: Literal["sent"] = "sent"
    history: HistoryOut | None = None
    raw: dict[str, Any] | None = None


class PlannedIntegrationOut(BaseModel):
    provider: str
    status: Literal["planned"] = "planned"
    message: str
