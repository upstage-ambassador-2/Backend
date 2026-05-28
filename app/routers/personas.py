from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app import models
from app.deps import AppSettings, CurrentUser, DbSession
from app.schemas import (
    ContactImportIn,
    ContactImportOut,
    PersonaCreate,
    PersonaMbtiInferIn,
    PersonaMbtiInferOut,
    PersonaOut,
    PersonaPatch,
    PersonaStructureIn,
    PersonaStructureOut,
)
from app.serializers import join_lines, persona_out
from app.services.google import import_contacts
from app.services.people import find_persona_by_email, normalize_email
from app.services.solar import infer_persona_mbti, structure_persona_text


router = APIRouter(prefix="/personas", tags=["personas"])


def _apply_persona(persona: models.Persona, payload: PersonaCreate | PersonaPatch) -> None:
    data = payload.model_dump(exclude_unset=True)
    field_map = {"tagColor": "tag_color"}
    list_fields = {"keywords", "avoid"}
    for key, value in data.items():
        column = field_map.get(key, key)
        if key in list_fields:
            value = join_lines(value)
        elif key == "email" and value is not None:
            value = normalize_email(str(value))
        setattr(persona, column, value)
    if not persona.avatar and persona.name:
        persona.avatar = "".join(part[0] for part in persona.name.split()[:2]).upper()[:2]


@router.get("", response_model=list[PersonaOut])
def list_personas(user: CurrentUser, db: DbSession) -> list[PersonaOut]:
    personas = db.scalars(
        select(models.Persona).where(models.Persona.user_id == user.id).order_by(models.Persona.created_at.desc())
    ).all()
    return [persona_out(item) for item in personas]


@router.post("", response_model=PersonaOut, status_code=201)
def create_persona(payload: PersonaCreate, user: CurrentUser, db: DbSession) -> PersonaOut:
    email = normalize_email(str(payload.email)) if payload.email else None
    if email:
        existing = find_persona_by_email(db, user.id, email)
        if existing:
            raise HTTPException(status_code=409, detail="이미 등록된 이메일입니다.")
    persona = models.Persona(user_id=user.id, name=payload.name)
    _apply_persona(persona, payload)
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona_out(persona)


@router.patch("/{persona_id}", response_model=PersonaOut)
def update_persona(persona_id: str, payload: PersonaPatch, user: CurrentUser, db: DbSession) -> PersonaOut:
    persona = db.get(models.Persona, persona_id)
    if not persona or persona.user_id != user.id:
        raise HTTPException(status_code=404, detail="페르소나를 찾을 수 없습니다.")
    email = normalize_email(str(payload.email)) if payload.email else None
    if email:
        existing = find_persona_by_email(db, user.id, email)
        if existing and existing.id != persona_id:
            raise HTTPException(status_code=409, detail="이미 등록된 이메일입니다.")
    _apply_persona(persona, payload)
    db.commit()
    db.refresh(persona)
    return persona_out(persona)


@router.delete("/{persona_id}", status_code=204)
def delete_persona(persona_id: str, user: CurrentUser, db: DbSession) -> None:
    persona = db.get(models.Persona, persona_id)
    if not persona or persona.user_id != user.id:
        raise HTTPException(status_code=404, detail="페르소나를 찾을 수 없습니다.")
    linked_history = db.scalars(
        select(models.HistoryItem).where(
            models.HistoryItem.user_id == user.id,
            models.HistoryItem.persona_id == persona_id,
        )
    ).all()
    for history in linked_history:
        history.persona_name = history.persona_name or persona.name
        history.persona_email = history.persona_email or persona.email
        history.counterparty_name = history.counterparty_name or persona.name
        history.counterparty_email = history.counterparty_email or persona.email
        history.persona_id = None
    db.delete(persona)
    db.commit()


@router.post("/import-contacts", response_model=ContactImportOut)
async def import_google_contacts(
    payload: ContactImportIn,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> ContactImportOut:
    imported, skipped = await import_contacts(db, settings, user, payload.limit)
    personas = db.scalars(
        select(models.Persona).where(models.Persona.user_id == user.id).order_by(models.Persona.created_at.desc())
    ).all()
    return ContactImportOut(imported=len(imported), skipped=skipped, personas=[persona_out(item) for item in personas])


@router.post("/structure", response_model=PersonaStructureOut)
async def structure_persona(
    payload: PersonaStructureIn,
    user: CurrentUser,
    settings: AppSettings,
) -> PersonaStructureOut:
    del user
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="분석할 페르소나 메모가 필요합니다.")
    return await structure_persona_text(settings, text)


@router.post("/infer-mbti", response_model=PersonaMbtiInferOut)
async def infer_mbti(
    payload: PersonaMbtiInferIn,
    user: CurrentUser,
    settings: AppSettings,
) -> PersonaMbtiInferOut:
    del user
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="MBTI 분석에 사용할 설명이 필요합니다.")
    return await infer_persona_mbti(settings, text)
