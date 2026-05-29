from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import models
from app.deps import AppSettings, CurrentUser, DbSession
from app.routers.format import get_or_create_format
from app.schemas import DraftRevisionIn, DraftRevisionMessageOut, DraftRevisionOut, HistoryDraftPatchIn, HistoryOut
from app.serializers import draft_revision_message_out, history_out
from app.services.people import normalize_email
from app.services.solar import (
    apply_generation_guardrails,
    build_revision_messages,
    parse_generated_draft,
    stream_solar_text,
)


router = APIRouter(prefix="/history", tags=["history"])


def _history_matches_email(item: models.HistoryItem, email: str) -> bool:
    candidates = [
        item.persona.email if item.persona else None,
        item.persona_email,
        item.counterparty_email,
        item.reply_context.from_addr if item.reply_context else None,
    ]
    return any(normalize_email(candidate) == email for candidate in candidates)


@router.get("", response_model=list[HistoryOut])
def list_history(
    user: CurrentUser,
    db: DbSession,
    personaId: str | None = Query(default=None),
    persona_id: str | None = Query(default=None),
    persona_email: str | None = Query(default=None, alias="personaEmail"),
    email: str | None = Query(default=None),
) -> list[HistoryOut]:
    persona_id_value = personaId or persona_id
    stmt = (
        select(models.HistoryItem)
        .options(selectinload(models.HistoryItem.persona), selectinload(models.HistoryItem.reply_context))
        .where(models.HistoryItem.user_id == user.id)
        .order_by(models.HistoryItem.created_at.desc())
    )
    if persona_id_value:
        persona = db.get(models.Persona, persona_id_value)
        if not persona or persona.user_id != user.id:
            raise HTTPException(status_code=404, detail="페르소나를 찾을 수 없습니다.")
        stmt = stmt.where(models.HistoryItem.persona_id == persona_id_value)
    items = db.scalars(stmt).all()
    email_value = normalize_email(persona_email or email)
    if email_value:
        items = [item for item in items if _history_matches_email(item, email_value)]
    return [history_out(item) for item in items]


@router.get("/{history_id}", response_model=HistoryOut)
def get_history(history_id: str, user: CurrentUser, db: DbSession) -> HistoryOut:
    item = db.get(models.HistoryItem, history_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="히스토리를 찾을 수 없습니다.")
    return history_out(item)


@router.delete("/{history_id}", status_code=204)
def delete_history(history_id: str, user: CurrentUser, db: DbSession) -> Response:
    item = db.get(models.HistoryItem, history_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="히스토리를 찾을 수 없습니다.")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


def _editable_history(history_id: str, user: CurrentUser, db: DbSession) -> models.HistoryItem:
    item = db.get(models.HistoryItem, history_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="히스토리를 찾을 수 없습니다.")
    if item.status == "sent":
        raise HTTPException(status_code=409, detail="발송 완료된 히스토리는 수정할 수 없습니다.")
    return item


def _history_messages(history_id: str, user: CurrentUser, db: DbSession) -> list[models.DraftRevisionMessage]:
    return db.scalars(
        select(models.DraftRevisionMessage)
        .where(
            models.DraftRevisionMessage.user_id == user.id,
            models.DraftRevisionMessage.history_id == history_id,
        )
        .order_by(models.DraftRevisionMessage.created_at.asc())
    ).all()


@router.patch("/{history_id}/draft", response_model=HistoryOut)
def update_history_draft(
    history_id: str,
    payload: HistoryDraftPatchIn,
    user: CurrentUser,
    db: DbSession,
) -> HistoryOut:
    item = _editable_history(history_id, user, db)
    if payload.subject is not None:
        item.subject = payload.subject
    if payload.body is not None:
        item.body = payload.body
    db.commit()
    db.refresh(item)
    return history_out(item)


@router.get("/{history_id}/draft/messages", response_model=list[DraftRevisionMessageOut])
def list_history_draft_messages(
    history_id: str,
    user: CurrentUser,
    db: DbSession,
) -> list[DraftRevisionMessageOut]:
    item = db.get(models.HistoryItem, history_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="히스토리를 찾을 수 없습니다.")
    return [draft_revision_message_out(message) for message in _history_messages(history_id, user, db)]


@router.post("/{history_id}/draft/revise", response_model=DraftRevisionOut)
async def revise_history_draft(
    history_id: str,
    payload: DraftRevisionIn,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> DraftRevisionOut:
    item = _editable_history(history_id, user, db)
    previous_messages = _history_messages(history_id, user, db)
    user_message = models.DraftRevisionMessage(
        user_id=user.id,
        history_id=item.id,
        role="user",
        content=payload.message,
    )
    db.add(user_message)
    db.flush()

    mail_format = get_or_create_format(user, db)
    messages = build_revision_messages(
        history=item,
        revision_request=payload.message,
        recent_messages=[*previous_messages, user_message],
        persona=item.persona,
        mail_format=mail_format,
        reply_context=item.reply_context,
    )

    raw_parts: list[str] = []
    async for token in stream_solar_text(settings, messages):
        raw_parts.append(token)

    draft = parse_generated_draft("".join(raw_parts))
    if not draft.subject.strip() or not draft.body.strip():
        raise HTTPException(status_code=502, detail="Solar 수정 결과가 비어 있습니다. 다시 요청해주세요.")

    draft = apply_generation_guardrails(
        draft,
        persona=item.persona,
        mail_format=mail_format,
        forbidden_status_code=422,
        forbidden_target="수정 결과",
        forbidden_action="다른 방식으로 요청해주세요.",
    )
    item.subject = draft.subject
    item.body = draft.body
    assistant_message = models.DraftRevisionMessage(
        user_id=user.id,
        history_id=item.id,
        role="assistant",
        content="초안을 수정했습니다.",
        subject=draft.subject,
        body=draft.body,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(item)

    return DraftRevisionOut(
        history=history_out(item),
        messages=[draft_revision_message_out(message) for message in _history_messages(history_id, user, db)],
    )


@router.post("/{history_id}/draft/reset", response_model=HistoryOut)
def reset_history_draft(history_id: str, user: CurrentUser, db: DbSession) -> HistoryOut:
    item = _editable_history(history_id, user, db)
    item.subject = ""
    item.body = ""
    db.commit()
    db.refresh(item)
    return history_out(item)
