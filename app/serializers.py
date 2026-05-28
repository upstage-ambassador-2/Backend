from datetime import datetime, timezone

from app import models
from app.config import GOOGLE_SCOPES
from app.generation_options import generation_length_label, generation_tone_label
from app.schemas import (
    HistoryOut,
    IntegrationStatus,
    MailFormatOut,
    PersonaOut,
    ReplyContextOut,
    UserOut,
    normalize_mbti_value,
)
from app.services.people import display_name_from_address, normalize_email


def split_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line for line in value.split("\n") if line]


def join_lines(value: list[str] | None) -> str:
    return "\n".join(value or [])


def human_when(value: datetime) -> str:
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = now - value
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "방금 전"
    if seconds < 3600:
        return f"{seconds // 60}분 전"
    if seconds < 86400:
        return f"오늘 {value.astimezone().strftime('%H:%M')}"
    if seconds < 172800:
        return f"어제 {value.astimezone().strftime('%H:%M')}"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def tone_label(value: int) -> str:
    return generation_tone_label(value)


def length_label(value: int) -> str:
    return generation_length_label(value)


def persona_mbti_value(value: str | None) -> str:
    try:
        return normalize_mbti_value(value) or ""
    except ValueError:
        return ""


def user_out(user: models.User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        pictureUrl=user.picture_url,
        createdAt=user.created_at,
    )


def integration_status(token: models.OAuthToken | None) -> IntegrationStatus:
    scopes = set((token.scope if token else "").split())
    return IntegrationStatus(
        gmail={
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
        }.issubset(scopes),
        contacts="https://www.googleapis.com/auth/contacts.readonly" in scopes,
    )


def persona_out(persona: models.Persona) -> PersonaOut:
    initials = "".join(part[0] for part in persona.name.split()[:2]).upper()
    return PersonaOut(
        id=persona.id,
        name=persona.name,
        relation=persona.relation,
        tone=persona.tone,
        notes=persona.notes,
        email=persona.email,
        source=persona.source,
        role=persona.role,
        mbti=persona_mbti_value(persona.mbti),
        avatar=persona.avatar or initials[:2],
        color=persona.color,
        keywords=split_lines(persona.keywords),
        avoid=split_lines(persona.avoid),
        prefer=persona.prefer,
        channel=persona.channel,
        tagColor=persona.tag_color,
        lastUsed=human_when(persona.last_used_at) if persona.last_used_at else "없음",
        createdAt=persona.created_at,
        updatedAt=persona.updated_at,
    )


def mail_format_out(mail_format: models.MailFormat) -> MailFormatOut:
    return MailFormatOut(
        signature=mail_format.signature,
        greeting=mail_format.greeting,
        closing=mail_format.closing,
        structure=mail_format.structure,
        bulletStyle=mail_format.bullet_style,
        language=mail_format.language,
        updatedAt=mail_format.updated_at,
    )


def reply_context_out(reply_context: models.ReplyContext, persona: models.Persona | None = None) -> ReplyContextOut:
    return ReplyContextOut(
        id=reply_context.id,
        gmailMessageId=reply_context.gmail_message_id,
        fromAddr=reply_context.from_addr,
        senderEmail=normalize_email(reply_context.from_addr),
        senderName=display_name_from_address(reply_context.from_addr),
        personaId=persona.id if persona else None,
        persona=persona_out(persona) if persona else None,
        subject=reply_context.subject,
        snippet=reply_context.snippet,
        rawBody=reply_context.raw_body,
        threadId=reply_context.thread_id,
        messageId=reply_context.message_id,
        references=reply_context.references,
        date=reply_context.date,
        createdAt=reply_context.created_at,
        updatedAt=reply_context.updated_at,
    )


def history_out(history: models.HistoryItem) -> HistoryOut:
    preview = history.body.replace("\n", " ")[:120]
    persona = history.persona
    reply_context = history.reply_context
    reply_context_payload = reply_context_out(reply_context, persona) if reply_context else None
    persona_name = persona.name if persona else history.persona_name
    persona_email = persona.email if persona else history.persona_email
    reply_email = normalize_email(reply_context.from_addr if reply_context else None)
    reply_name = display_name_from_address(reply_context.from_addr if reply_context else None)
    if persona:
        counterparty_email = persona.email or history.counterparty_email or reply_email
        counterparty_name = persona.name
    else:
        counterparty_email = history.counterparty_email or persona_email or reply_email
        counterparty_name = history.counterparty_name or persona_name or reply_name
    return HistoryOut(
        id=history.id,
        personaId=history.persona_id,
        replyContextId=history.reply_context_id,
        persona=persona_out(persona) if persona else None,
        replyContext=reply_context_payload,
        personaName=persona_name,
        personaEmail=persona_email,
        counterpartyName=counterparty_name,
        counterpartyEmail=counterparty_email,
        brief=history.brief,
        subject=history.subject,
        body=history.body,
        status=history.status,
        tone=tone_label(history.tone),
        toneValue=history.tone,
        length=length_label(history.length),
        lengthValue=history.length,
        when=human_when(history.created_at),
        createdAt=history.created_at,
        sentAt=history.sent_at,
        subj=history.subject,
        prev=preview,
    )


def required_google_scope_string() -> str:
    return " ".join(GOOGLE_SCOPES)
