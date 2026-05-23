from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app import models
from app.deps import AppSettings, DbSession
from app.security import hash_token, load_oauth_state, new_session_token, session_expiry, sign_oauth_state
from app.services.google import build_google_auth_url, exchange_code_for_token, fetch_userinfo, upsert_oauth_user
from app.schemas import AuthStartIn, AuthStartOut


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google/start", response_model=AuthStartOut)
def google_start(payload: AuthStartIn, settings: AppSettings) -> AuthStartOut:
    state = sign_oauth_state({"next": payload.next or settings.frontend_url}, settings)
    return AuthStartOut(url=build_google_auth_url(settings, state))


@router.get("/google/callback")
async def google_callback(
    db: DbSession,
    settings: AppSettings,
    code: str = Query(...),
    state: str = Query(...),
):
    try:
        state_payload = load_oauth_state(state, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="OAuth state가 올바르지 않습니다.") from exc

    token_payload = await exchange_code_for_token(settings, code)
    userinfo = await fetch_userinfo(str(token_payload["access_token"]))
    user = upsert_oauth_user(db, settings, token_payload, userinfo)

    raw_token = new_session_token()
    session = models.SessionToken(
        token_hash=hash_token(raw_token),
        user_id=user.id,
        expires_at=session_expiry(settings),
    )
    db.add(session)
    db.commit()

    redirect_to = state_payload.get("next") or settings.frontend_url
    response = RedirectResponse(redirect_to, status_code=303)
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
    )
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DbSession, settings: AppSettings):
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token:
        existing = db.scalar(select(models.SessionToken).where(models.SessionToken.token_hash == hash_token(session_token)))
        if existing:
            db.delete(existing)
            db.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        domain=settings.session_cookie_domain,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
