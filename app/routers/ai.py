import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import models
from app.database import SessionLocal
from app.deps import AppSettings, CurrentUser, DbSession
from app.routers.format import get_or_create_format
from app.schemas import GenerateIn, ReplyContextInline
from app.serializers import history_out
from app.services.google import upsert_reply_context
from app.services.people import assign_persona_email_if_empty, find_persona_by_email
from app.services.solar import build_generation_messages, parse_generated_draft, stream_solar_text


router = APIRouter(prefix="/ai", tags=["ai"])


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/generate")
async def generate(payload: GenerateIn, user: CurrentUser, db: DbSession, settings: AppSettings):
    if not payload.brief.strip() and not payload.reply_context_id_value and not payload.replyContext:
        raise HTTPException(status_code=422, detail="brief 또는 reply_context가 필요합니다.")

    persona = None
    if payload.persona_id_value:
        persona = db.get(models.Persona, payload.persona_id_value)
        if not persona or persona.user_id != user.id:
            raise HTTPException(status_code=404, detail="페르소나를 찾을 수 없습니다.")

    reply_context = None
    if payload.reply_context_id_value:
        reply_context = db.get(models.ReplyContext, payload.reply_context_id_value)
        if not reply_context or reply_context.user_id != user.id:
            raise HTTPException(status_code=404, detail="답장 컨텍스트를 찾을 수 없습니다.")
    elif payload.replyContext:
        reply_context = upsert_reply_context(db, user, payload.replyContext)

    if not persona and reply_context:
        persona = find_persona_by_email(db, user.id, reply_context.from_addr)
    if persona and reply_context and assign_persona_email_if_empty(db, user.id, persona, reply_context.from_addr):
        db.commit()
        db.refresh(persona)

    mail_format = get_or_create_format(user, db)
    messages = build_generation_messages(
        brief=payload.brief,
        tone=payload.tone,
        length=payload.length,
        persona=persona,
        mail_format=mail_format,
        reply_context=reply_context,
    )

    user_id = user.id
    persona_id = persona.id if persona else None
    reply_context_id = reply_context.id if reply_context else None

    async def event_stream():
        raw_parts: list[str] = []
        try:
            async for token in stream_solar_text(settings, messages):
                raw_parts.append(token)
                yield sse("delta", {"text": token})

            draft = parse_generated_draft("".join(raw_parts))
            with SessionLocal() as session:
                history = models.HistoryItem(
                    user_id=user_id,
                    brief=payload.brief,
                    tone=payload.tone,
                    length=payload.length,
                    persona_id=persona_id,
                    reply_context_id=reply_context_id,
                    subject=draft.subject,
                    body=draft.body,
                    status="draft",
                )
                session.add(history)
                if persona_id:
                    saved_persona = session.get(models.Persona, persona_id)
                    if saved_persona:
                        saved_persona.last_used_at = models.utcnow()
                session.commit()
                session.refresh(history)
                history_payload = history_out(history).model_dump(mode="json")
            yield sse("done", {"subject": draft.subject, "body": draft.body, "history": history_payload})
        except HTTPException as exc:
            yield sse("error", {"detail": exc.detail, "status": exc.status_code})
        except Exception:
            yield sse("error", {"detail": "초안 생성 중 알 수 없는 오류가 발생했습니다.", "status": 500})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
