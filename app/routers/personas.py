from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app import models
from app.deps import AppSettings, CurrentUser, DbSession
from app.schemas import ContactImportIn, ContactImportOut, PersonaCreate, PersonaOut, PersonaPatch
from app.serializers import join_lines, persona_out
from app.services.google import import_contacts


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
            value = str(value)
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
    if payload.email:
        existing = db.scalar(
            select(models.Persona).where(models.Persona.user_id == user.id, models.Persona.email == str(payload.email))
        )
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
    if payload.email:
        existing = db.scalar(
            select(models.Persona).where(
                models.Persona.user_id == user.id,
                models.Persona.email == str(payload.email),
                models.Persona.id != persona_id,
            )
        )
        if existing:
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
