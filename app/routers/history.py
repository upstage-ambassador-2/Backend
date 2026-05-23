from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app import models
from app.deps import CurrentUser, DbSession
from app.schemas import HistoryOut
from app.serializers import history_out


router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryOut])
def list_history(user: CurrentUser, db: DbSession) -> list[HistoryOut]:
    items = db.scalars(
        select(models.HistoryItem).where(models.HistoryItem.user_id == user.id).order_by(models.HistoryItem.created_at.desc())
    ).all()
    return [history_out(item) for item in items]


@router.get("/{history_id}", response_model=HistoryOut)
def get_history(history_id: str, user: CurrentUser, db: DbSession) -> HistoryOut:
    item = db.get(models.HistoryItem, history_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="히스토리를 찾을 수 없습니다.")
    return history_out(item)
