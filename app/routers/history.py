from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import models
from app.deps import CurrentUser, DbSession
from app.schemas import HistoryDraftPatchIn, HistoryOut
from app.serializers import history_out
from app.services.people import normalize_email


router = APIRouter(prefix="/history", tags=["history"])


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
        items = [
            item
            for item in items
            if normalize_email(item.persona.email if item.persona else None) == email_value
            or normalize_email(item.reply_context.from_addr if item.reply_context else None) == email_value
        ]
    return [history_out(item) for item in items]


@router.get("/{history_id}", response_model=HistoryOut)
def get_history(history_id: str, user: CurrentUser, db: DbSession) -> HistoryOut:
    item = db.get(models.HistoryItem, history_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="히스토리를 찾을 수 없습니다.")
    return history_out(item)


def _editable_history(history_id: str, user: CurrentUser, db: DbSession) -> models.HistoryItem:
    item = db.get(models.HistoryItem, history_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="히스토리를 찾을 수 없습니다.")
    if item.status == "sent":
        raise HTTPException(status_code=409, detail="발송 완료된 히스토리는 수정할 수 없습니다.")
    return item


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


@router.post("/{history_id}/draft/reset", response_model=HistoryOut)
def reset_history_draft(history_id: str, user: CurrentUser, db: DbSession) -> HistoryOut:
    item = _editable_history(history_id, user, db)
    item.subject = ""
    item.body = ""
    db.commit()
    db.refresh(item)
    return history_out(item)
