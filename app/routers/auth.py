from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app import models
from app.config import Settings
from app.deps import AppSettings, DbSession
from app.security import hash_token, load_oauth_state, new_session_token, session_expiry, sign_oauth_state
from app.services.google import build_google_auth_url, exchange_code_for_token, fetch_userinfo, upsert_oauth_user
from app.schemas import AuthStartIn, AuthStartOut


router = APIRouter(prefix="/auth", tags=["auth"])


def _safe_frontend_redirect(next_url: str | None, settings: Settings) -> str:
    frontend = urlsplit(settings.frontend_url)
    fallback = settings.frontend_url
    candidate = (next_url or "").strip()
    if not candidate:
        return fallback

    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        same_origin = (
            parsed.scheme.lower() == frontend.scheme.lower()
            and parsed.netloc.lower() == frontend.netloc.lower()
        )
        return urlunsplit(parsed) if same_origin else fallback

    path = parsed.path if parsed.path.startswith("/") else f"/{parsed.path}"
    return urlunsplit((frontend.scheme, frontend.netloc, path or "/", parsed.query, parsed.fragment))


def _login_error_redirect(reason: str, settings: Settings) -> RedirectResponse:
    frontend = urlsplit(settings.frontend_url)
    query = urlencode({"auth_error": reason})
    return RedirectResponse(
        urlunsplit((frontend.scheme, frontend.netloc, "/login", query, "")),
        status_code=303,
    )


@router.post("/google/start", response_model=AuthStartOut)
def google_start(payload: AuthStartIn, settings: AppSettings) -> AuthStartOut:
    state = sign_oauth_state({"next": _safe_frontend_redirect(payload.next, settings)}, settings)
    return AuthStartOut(url=build_google_auth_url(settings, state))


@router.get("/google/callback")
async def google_callback(
    db: DbSession,
    settings: AppSettings,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    if error:
        reason = "access_denied" if error == "access_denied" else "oauth_failed"
        return _login_error_redirect(reason, settings)
    if not state:
        return _login_error_redirect("invalid_state", settings)
    try:
        state_payload = load_oauth_state(state, settings)
    except ValueError:
        return _login_error_redirect("invalid_state", settings)
    if not code:
        return _login_error_redirect("missing_code", settings)

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
