from email.utils import parseaddr

from fastapi import APIRouter, HTTPException, Query

from app import models
from app.deps import AppSettings, CurrentUser, DbSession
from app.routers.format import get_or_create_format
from app.schemas import (
    GeneratedDraft,
    GmailMessageDetailOut,
    GmailMessagesPageOut,
    GmailSendIn,
    GmailSendOut,
    ReplyContextInline,
)
from app.serializers import history_out, persona_out, reply_context_out
from app.services.google import get_gmail_message_detail, list_gmail_messages, send_gmail_message, upsert_reply_context
from app.services.people import (
    assign_persona_email_if_empty,
    display_name_from_address,
    find_persona_by_email,
    normalize_email,
)
from app.services.solar import apply_generation_guardrails


router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.get("/messages", response_model=GmailMessagesPageOut)
async def messages(
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    limit: int = Query(default=30, ge=1, le=100),
    page_token: str | None = Query(default=None, alias="pageToken"),
) -> GmailMessagesPageOut:
    return await list_gmail_messages(db, settings, user, limit, page_token)


@router.get("/messages/{message_id}", response_model=GmailMessageDetailOut)
async def message_detail(message_id: str, user: CurrentUser, db: DbSession, settings: AppSettings) -> GmailMessageDetailOut:
    message, body = await get_gmail_message_detail(db, settings, user, message_id)
    reply_context = upsert_reply_context(
        db,
        user,
        ReplyContextInline(
            gmailMessageId=message.id,
            fromAddr=message.fromAddr,
            subject=message.subject,
            snippet=message.snippet,
            rawBody=body,
            threadId=message.threadId,
            messageId=message.messageId,
            references=message.references,
            date=message.date,
        ),
    )
    persona = find_persona_by_email(db, user.id, message.senderEmail or message.fromAddr)
    if persona and not message.personaId:
        message.personaId = persona.id
        message.persona = persona_out(persona)
    return GmailMessageDetailOut(
        **message.model_dump(),
        rawBody=body,
        replyContext=reply_context_out(reply_context, persona),
    )


@router.post("/send", response_model=GmailSendOut)
async def send(payload: GmailSendIn, user: CurrentUser, db: DbSession, settings: AppSettings) -> GmailSendOut:
    history = db.get(models.HistoryItem, payload.history_id_value) if payload.history_id_value else None
    if payload.history_id_value and (not history or history.user_id != user.id):
        raise HTTPException(status_code=404, detail="히스토리를 찾을 수 없습니다.")
    if history and history.status == "sent" and history.gmail_message_id:
        return GmailSendOut(
            id=history.gmail_message_id,
            threadId=None,
            history=history_out(history),
            raw={"id": history.gmail_message_id, "deduplicated": True},
        )

    reply_context = None
    if payload.reply_context_id_value:
        reply_context = db.get(models.ReplyContext, payload.reply_context_id_value)
        if not reply_context or reply_context.user_id != user.id:
            raise HTTPException(status_code=404, detail="답장 컨텍스트를 찾을 수 없습니다.")
    elif history and history.reply_context_id:
        reply_context = db.get(models.ReplyContext, history.reply_context_id)

    history_persona = history.persona if history and history.persona_id else None

    to_addr = normalize_email(str(payload.to)) if payload.to else None
    if not to_addr and history_persona and history_persona.email:
        to_addr = normalize_email(history_persona.email)
    if not to_addr and reply_context:
        to_addr = normalize_email(parseaddr(reply_context.from_addr)[1] or reply_context.from_addr)
    if not to_addr:
        raise HTTPException(status_code=422, detail="받는 사람 이메일이 필요합니다.")

    recipient_persona = history_persona or find_persona_by_email(db, user.id, to_addr)
    if history and not history.persona_id and recipient_persona:
        history.persona_id = recipient_persona.id
    if history_persona:
        assign_persona_email_if_empty(db, user.id, history_persona, to_addr)
    mail_format = get_or_create_format(user, db)
    guarded_draft = apply_generation_guardrails(
        GeneratedDraft(subject=payload.subject, body=payload.body),
        persona=recipient_persona,
        mail_format=mail_format,
        forbidden_status_code=422,
        forbidden_target="발송하려는 내용",
        forbidden_action="수정 후 다시 보내주세요.",
    )

    result = await send_gmail_message(
        db,
        settings,
        user,
        to=to_addr,
        subject=guarded_draft.subject,
        body=guarded_draft.body,
        cc=[str(item) for item in payload.cc],
        bcc=[str(item) for item in payload.bcc],
        reply_context=reply_context,
    )
    if recipient_persona:
        recipient_persona.last_used_at = models.utcnow()
    if history:
        history.subject = guarded_draft.subject
        history.body = guarded_draft.body
        history.status = "sent"
        history.gmail_message_id = str(result.get("id") or "")
        history.sent_at = models.utcnow()
        if recipient_persona:
            history.persona_name = recipient_persona.name
            history.persona_email = recipient_persona.email
            history.counterparty_name = recipient_persona.name
            history.counterparty_email = recipient_persona.email or to_addr
        else:
            if reply_context:
                history.counterparty_name = display_name_from_address(reply_context.from_addr)
            history.counterparty_email = to_addr or history.counterparty_email
    if history or recipient_persona:
        db.commit()
    if history:
        db.refresh(history)
    return GmailSendOut(id=str(result.get("id") or ""), threadId=result.get("threadId"), history=history_out(history) if history else None, raw=result)
