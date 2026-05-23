from fastapi import APIRouter

from app import models
from app.deps import CurrentUser, DbSession
from app.schemas import MailFormatIn, MailFormatOut
from app.serializers import mail_format_out
from app.services.google import default_mail_format


router = APIRouter(prefix="/format", tags=["format"])


def get_or_create_format(user: models.User, db: DbSession) -> models.MailFormat:
    mail_format = db.get(models.MailFormat, user.id)
    if mail_format:
        return mail_format
    mail_format = default_mail_format(user)
    db.add(mail_format)
    db.commit()
    db.refresh(mail_format)
    return mail_format


@router.get("", response_model=MailFormatOut)
def get_format(user: CurrentUser, db: DbSession) -> MailFormatOut:
    return mail_format_out(get_or_create_format(user, db))


@router.put("", response_model=MailFormatOut)
def update_format(payload: MailFormatIn, user: CurrentUser, db: DbSession) -> MailFormatOut:
    mail_format = get_or_create_format(user, db)
    data = payload.model_dump(exclude_unset=True)
    field_map = {"bulletStyle": "bullet_style"}
    for key, value in data.items():
        if value is not None:
            setattr(mail_format, field_map.get(key, key), value)
    db.commit()
    db.refresh(mail_format)
    return mail_format_out(mail_format)
