from email.utils import parseaddr

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    parsed = parseaddr(value)[1] or value
    email = parsed.strip().lower()
    if "@" not in email:
        return None
    return email


def display_name_from_address(value: str | None) -> str | None:
    if not value:
        return None
    name, parsed = parseaddr(value)
    clean_name = name.strip().strip('"')
    if clean_name:
        return clean_name
    email = normalize_email(parsed or value)
    if email:
        return email.split("@", 1)[0]
    return value.strip() or None


def find_persona_by_email(db: Session, user_id: str, value: str | None) -> models.Persona | None:
    email = normalize_email(value)
    if not email:
        return None
    return db.scalar(
        select(models.Persona).where(
            models.Persona.user_id == user_id,
            models.Persona.email.is_not(None),
            func.lower(models.Persona.email) == email,
        )
    )


def assign_persona_email_if_empty(db: Session, user_id: str, persona: models.Persona, value: str | None) -> bool:
    email = normalize_email(value)
    if not email or persona.email:
        return False
    existing = find_persona_by_email(db, user_id, email)
    if existing and existing.id != persona.id:
        return False
    persona.email = email
    return True
