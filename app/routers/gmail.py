from email.utils import parseaddr

from fastapi import APIRouter, HTTPException, Query

from app import models
from app.deps import AppSettings, CurrentUser, DbSession
from app.schemas import GmailMessageDetailOut, GmailMessageOut, GmailSendIn, GmailSendOut, ReplyContextInline
from app.serializers import history_out, reply_context_out
from app.services.google import get_gmail_message_detail, list_gmail_messages, send_gmail_message, upsert_reply_context


router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.get("/messages", response_model=list[GmailMessageOut])
async def messages(
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[GmailMessageOut]:
    return await list_gmail_messages(db, settings, user, limit)


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
    return GmailMessageDetailOut(**message.model_dump(), rawBody=body, replyContext=reply_context_out(reply_context))


@router.post("/send", response_model=GmailSendOut)
async def send(payload: GmailSendIn, user: CurrentUser, db: DbSession, settings: AppSettings) -> GmailSendOut:
    history = db.get(models.HistoryItem, payload.history_id_value) if payload.history_id_value else None
    if history and history.user_id != user.id:
        raise HTTPException(status_code=404, detail="히스토리를 찾을 수 없습니다.")

    reply_context = None
    if payload.reply_context_id_value:
        reply_context = db.get(models.ReplyContext, payload.reply_context_id_value)
        if not reply_context or reply_context.user_id != user.id:
            raise HTTPException(status_code=404, detail="답장 컨텍스트를 찾을 수 없습니다.")
    elif history and history.reply_context_id:
        reply_context = db.get(models.ReplyContext, history.reply_context_id)

    to_addr = str(payload.to) if payload.to else None
    if not to_addr and reply_context:
        to_addr = parseaddr(reply_context.from_addr)[1]
    if not to_addr:
        raise HTTPException(status_code=422, detail="받는 사람 이메일이 필요합니다.")

    result = await send_gmail_message(
        db,
        settings,
        user,
        to=to_addr,
        subject=payload.subject,
        body=payload.body,
        cc=[str(item) for item in payload.cc],
        bcc=[str(item) for item in payload.bcc],
        reply_context=reply_context,
    )
    if history:
        history.status = "sent"
        history.gmail_message_id = str(result.get("id") or "")
        history.sent_at = models.utcnow()
        db.commit()
        db.refresh(history)
    return GmailSendOut(id=str(result.get("id") or ""), threadId=result.get("threadId"), history=history_out(history) if history else None, raw=result)
