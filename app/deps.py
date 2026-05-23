from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import SessionToken, User, as_utc, utcnow
from app.security import hash_token


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _delete_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        domain=settings.session_cookie_domain,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def get_current_user(
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> User:
    session_cookie = request.cookies.get(settings.session_cookie_name)
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")

    token_hash = hash_token(session_cookie)
    session = db.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash))
    if not session or as_utc(session.expires_at) <= utcnow():
        if session:
            db.delete(session)
            db.commit()
        _delete_session_cookie(response, settings)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="세션이 만료되었습니다.")

    user = db.get(User, session.user_id)
    if not user:
        db.delete(session)
        db.commit()
        _delete_session_cookie(response, settings)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
