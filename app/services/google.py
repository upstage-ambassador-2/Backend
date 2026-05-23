import base64
from datetime import timedelta
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import GOOGLE_SCOPES, Settings
from app.schemas import GmailMessageOut, ReplyContextInline
from app.security import decrypt_token, encrypt_token


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
PEOPLE_API = "https://people.googleapis.com/v1/people/me/connections"


def build_google_auth_url(settings: Settings, state: str) -> str:
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID가 설정되지 않았습니다.")
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}"


async def exchange_code_for_token(settings: Settings, code: str) -> dict[str, Any]:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth 환경변수가 설정되지 않았습니다.")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri,
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Google OAuth 토큰 교환에 실패했습니다.")
    return response.json()


async def fetch_userinfo(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Google 사용자 정보를 가져오지 못했습니다.")
    return response.json()


def upsert_oauth_user(db: Session, settings: Settings, token_payload: dict[str, Any], userinfo: dict[str, Any]) -> models.User:
    google_sub = str(userinfo.get("sub") or "")
    email = str(userinfo.get("email") or "")
    if not google_sub or not email:
        raise HTTPException(status_code=502, detail="Google 사용자 정보가 올바르지 않습니다.")

    user = db.scalar(select(models.User).where(models.User.google_sub == google_sub))
    if not user:
        user = models.User(google_sub=google_sub, email=email)
        db.add(user)

    user.email = email
    user.name = str(userinfo.get("name") or email.split("@")[0])
    user.picture_url = userinfo.get("picture")

    expires_in = int(token_payload.get("expires_in") or 3600)
    access_token = str(token_payload["access_token"])
    refresh_token = token_payload.get("refresh_token")
    scope = str(token_payload.get("scope") or " ".join(GOOGLE_SCOPES))

    existing_token = user.oauth_token or db.get(models.OAuthToken, user.id)
    if existing_token:
        oauth_token = existing_token
    else:
        oauth_token = models.OAuthToken(user=user)
        db.add(oauth_token)
    oauth_token.access_token_enc = encrypt_token(access_token, settings)
    if refresh_token:
        oauth_token.refresh_token_enc = encrypt_token(str(refresh_token), settings)
    oauth_token.scope = scope
    oauth_token.expires_at = models.utcnow() + timedelta(seconds=expires_in)

    if not user.mail_format:
        db.add(default_mail_format(user))

    db.commit()
    db.refresh(user)
    return user


def default_mail_format(user: models.User) -> models.MailFormat:
    return models.MailFormat(
        user=user,
        greeting="안녕하세요.",
        closing="감사합니다.",
        structure="인사 → 본문 → 요청 → 마무리",
        bullet_style="· (가운뎃점)",
        language="한국어 · 존댓말 기본",
        signature=f"{user.name}\n{user.email}",
    )


async def refresh_access_token(db: Session, settings: Settings, token: models.OAuthToken) -> str:
    refresh_token = decrypt_token(token.refresh_token_enc, settings)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google 재인증이 필요합니다. 다시 로그인해주세요.",
        )
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth 환경변수가 설정되지 않았습니다.")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google 토큰 갱신에 실패했습니다. 다시 로그인해주세요.",
        )
    payload = response.json()
    token.access_token_enc = encrypt_token(str(payload["access_token"]), settings)
    if payload.get("refresh_token"):
        token.refresh_token_enc = encrypt_token(str(payload["refresh_token"]), settings)
    token.scope = str(payload.get("scope") or token.scope)
    token.expires_at = models.utcnow() + timedelta(seconds=int(payload.get("expires_in") or 3600))
    db.commit()
    return str(payload["access_token"])


async def google_access_token(db: Session, settings: Settings, user: models.User) -> str:
    token = db.get(models.OAuthToken, user.id)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google 연결이 필요합니다.")
    if token.expires_at and models.as_utc(token.expires_at) <= models.utcnow() + timedelta(seconds=60):
        return await refresh_access_token(db, settings, token)
    access_token = decrypt_token(token.access_token_enc, settings)
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google 연결이 필요합니다.")
    return access_token


async def google_get_json(url: str, access_token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="Gmail 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Google API 요청에 실패했습니다.")
    return response.json()


async def google_post_json(url: str, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="Gmail 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Gmail 발송에 실패했습니다.")
    return response.json()


def _headers_map(message: dict[str, Any]) -> dict[str, str]:
    headers = message.get("payload", {}).get("headers", [])
    return {str(h.get("name", "")).lower(): str(h.get("value", "")) for h in headers}


def _decode_body(data: str | None) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")


def _plain_text_from_payload(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType")
    body_data = payload.get("body", {}).get("data")
    if mime_type == "text/plain" and body_data:
        return _decode_body(body_data)
    for part in payload.get("parts", []) or []:
        text = _plain_text_from_payload(part)
        if text:
            return text
    if body_data:
        return _decode_body(body_data)
    return ""


def gmail_message_out(message: dict[str, Any]) -> GmailMessageOut:
    headers = _headers_map(message)
    return GmailMessageOut(
        id=str(message.get("id", "")),
        threadId=message.get("threadId"),
        fromAddr=headers.get("from", ""),
        subject=headers.get("subject", ""),
        snippet=str(message.get("snippet") or ""),
        date=headers.get("date"),
        messageId=headers.get("message-id"),
        references=headers.get("references"),
    )


async def list_gmail_messages(db: Session, settings: Settings, user: models.User, limit: int) -> list[GmailMessageOut]:
    access_token = await google_access_token(db, settings, user)
    listing = await google_get_json(
        f"{GMAIL_API}/messages",
        access_token,
        params={"maxResults": limit, "q": "in:inbox", "includeSpamTrash": "false"},
    )
    messages = listing.get("messages", [])[:limit]
    result: list[GmailMessageOut] = []
    for item in messages:
        detail = await google_get_json(
            f"{GMAIL_API}/messages/{item['id']}",
            access_token,
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date", "Message-ID", "References"]},
        )
        result.append(gmail_message_out(detail))
    return result


async def get_gmail_message_detail(db: Session, settings: Settings, user: models.User, message_id: str) -> tuple[GmailMessageOut, str]:
    access_token = await google_access_token(db, settings, user)
    detail = await google_get_json(f"{GMAIL_API}/messages/{message_id}", access_token, params={"format": "full"})
    message = gmail_message_out(detail)
    body = _plain_text_from_payload(detail.get("payload", {}))
    return message, body


def upsert_reply_context(db: Session, user: models.User, inline: ReplyContextInline) -> models.ReplyContext:
    reply_context = db.scalar(
        select(models.ReplyContext).where(
            models.ReplyContext.user_id == user.id,
            models.ReplyContext.gmail_message_id == inline.gmailMessageId,
        )
    )
    if not reply_context:
        reply_context = models.ReplyContext(user_id=user.id, gmail_message_id=inline.gmailMessageId)
        db.add(reply_context)
    reply_context.from_addr = inline.fromAddr
    reply_context.subject = inline.subject
    reply_context.snippet = inline.snippet
    reply_context.raw_body = inline.rawBody
    reply_context.thread_id = inline.threadId
    reply_context.message_id = inline.messageId
    reply_context.references = inline.references
    reply_context.date = inline.date
    db.commit()
    db.refresh(reply_context)
    return reply_context


async def import_contacts(db: Session, settings: Settings, user: models.User, limit: int) -> tuple[list[models.Persona], int]:
    access_token = await google_access_token(db, settings, user)
    payload = await google_get_json(
        PEOPLE_API,
        access_token,
        params={
            "pageSize": limit,
            "personFields": "names,emailAddresses,metadata",
            "sortOrder": "LAST_MODIFIED_DESCENDING",
        },
    )
    imported: list[models.Persona] = []
    skipped = 0
    for person in payload.get("connections", [])[:limit]:
        names = person.get("names") or []
        emails = person.get("emailAddresses") or []
        name = (names[0].get("displayName") if names else "") or ""
        email = (emails[0].get("value") if emails else "") or None
        if not name or not email:
            skipped += 1
            continue
        exists = db.scalar(select(models.Persona).where(models.Persona.user_id == user.id, models.Persona.email == email))
        if exists:
            skipped += 1
            continue
        persona = models.Persona(
            user_id=user.id,
            name=name,
            email=email,
            relation="Google Contacts",
            tone="중립",
            notes=f"Google Contacts에서 가져옴: {email}",
            source="contacts",
            avatar="".join(part[0] for part in name.split()[:2]).upper()[:2],
            keywords="이메일\n연락처",
            channel="이메일",
            tag_color="green",
        )
        db.add(persona)
        imported.append(persona)
    db.commit()
    for persona in imported:
        db.refresh(persona)
    return imported, skipped


def build_email_raw(
    *,
    sender: str,
    to: str,
    subject: str,
    body: str,
    cc: list[str],
    bcc: list[str],
    reply_context: models.ReplyContext | None,
) -> str:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    if reply_context and reply_context.message_id:
        msg["In-Reply-To"] = reply_context.message_id
        refs = " ".join(part for part in [reply_context.references, reply_context.message_id] if part)
        if refs:
            msg["References"] = refs
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")


async def send_gmail_message(
    db: Session,
    settings: Settings,
    user: models.User,
    *,
    to: str,
    subject: str,
    body: str,
    cc: list[str],
    bcc: list[str],
    reply_context: models.ReplyContext | None,
) -> dict[str, Any]:
    access_token = await google_access_token(db, settings, user)
    payload: dict[str, Any] = {
        "raw": build_email_raw(
            sender=user.email,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            reply_context=reply_context,
        )
    }
    if reply_context and reply_context.thread_id:
        payload["threadId"] = reply_context.thread_id
    return await google_post_json(f"{GMAIL_API}/messages/send", access_token, payload)
