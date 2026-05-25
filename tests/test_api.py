import asyncio
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

os.environ["DATABASE_URL"] = "sqlite:///./test-mello.db"
os.environ["SECRET_KEY"] = "test-secret-key-with-enough-length"
os.environ["SOLAR_API_KEY"] = "test-solar-key"
os.environ["GOOGLE_CLIENT_ID"] = "test-google-client"
os.environ["GOOGLE_REDIRECT_URI"] = "http://localhost:8000/auth/google/callback"
os.environ["FRONTEND_URL"] = "http://localhost:3000"

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_token, load_oauth_state, session_expiry  # noqa: E402
from app.services import google as google_service  # noqa: E402


def setup_function():
    Base.metadata.drop_all(bind=engine)
    init_db()


def teardown_module():
    Path("test-mello.db").unlink(missing_ok=True)


def authed_client() -> tuple[TestClient, models.User]:
    token = "test-session-token"
    settings = get_settings()
    with SessionLocal() as db:
        user = models.User(google_sub="google-sub-1", email="user@example.com", name="Tester")
        db.add(user)
        db.flush()
        db.add(models.SessionToken(token_hash=hash_token(token), user_id=user.id, expires_at=session_expiry(settings)))
        db.add(models.MailFormat(user_id=user.id, signature="Tester\nuser@example.com"))
        db.commit()
        db.refresh(user)

    client = TestClient(app)
    client.cookies.set("mello_session", token)
    return client, user


def _oauth_start_next(client: TestClient, next_url: str | None) -> str:
    response = client.post("/auth/google/start", json={"next": next_url})
    assert response.status_code == 200
    state = parse_qs(urlparse(response.json()["url"]).query)["state"][0]
    return load_oauth_state(state, get_settings())["next"]


def test_google_start_constrains_redirect_to_frontend_origin():
    client = TestClient(app)

    assert (
        _oauth_start_next(client, "/compose?reply=1")
        == "http://localhost:3000/compose?reply=1"
    )
    assert _oauth_start_next(client, "http://localhost:3000/inbox") == "http://localhost:3000/inbox"
    assert _oauth_start_next(client, "https://evil.example/phishing") == "http://localhost:3000"
    assert _oauth_start_next(client, "//evil.example/phishing") == "http://localhost:3000"


def test_me_and_format_roundtrip():
    client, _ = authed_client()

    me = client.get("/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "user@example.com"

    updated = client.put("/format", json={"greeting": "안녕하세요, Tester입니다.", "signature": "Tester"})
    assert updated.status_code == 200
    assert updated.json()["greeting"] == "안녕하세요, Tester입니다."

    fetched = client.get("/format")
    assert fetched.json()["signature"] == "Tester"


def test_integration_toggle_allows_known_providers_only():
    client, _ = authed_client()

    gmail = client.post("/integrations/gmail/toggle")
    assert gmail.status_code == 200
    assert gmail.json()["provider"] == "gmail"
    assert gmail.json()["message"] == "Gmail/Contacts는 Google OAuth 동의 시점에 연결됩니다."

    contacts_alias = client.post("/integrations/google_contacts/toggle")
    assert contacts_alias.status_code == 200
    assert contacts_alias.json()["provider"] == "contacts"

    slack = client.post("/integrations/slack/toggle")
    assert slack.status_code == 200
    assert slack.json() == {
        "provider": "slack",
        "status": "planned",
        "message": "지원 예정입니다.",
    }

    unknown = client.post("/integrations/dropbox/toggle")
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "지원하지 않는 연동 제공자입니다."


def test_persona_crud():
    client, _ = authed_client()

    created = client.post(
        "/personas",
        json={
            "name": "김지훈 팀장",
            "relation": "회사 · 직속 상사",
            "tone": "격식",
            "keywords": ["결과 중심", "직설적"],
            "avoid": ["모호한 시작"],
            "prefer": "결론 → 일정 → 근거",
            "email": "lead@example.com",
        },
    )
    assert created.status_code == 201
    persona_id = created.json()["id"]

    listed = client.get("/personas")
    assert listed.status_code == 200
    assert listed.json()[0]["keywords"] == ["결과 중심", "직설적"]

    patched = client.patch(f"/personas/{persona_id}", json={"tone": "친근", "tagColor": "green"})
    assert patched.status_code == 200
    assert patched.json()["tone"] == "친근"
    assert patched.json()["tagColor"] == "green"

    invalid = client.patch(f"/personas/{persona_id}", json={"tone": "정중"})
    assert invalid.status_code == 422

    deleted = client.delete(f"/personas/{persona_id}")
    assert deleted.status_code == 204
    assert client.get("/personas").json() == []


def test_persona_delete_rejects_history_linked_persona():
    client, user = authed_client()
    with SessionLocal() as db:
        persona = models.Persona(user_id=user.id, name="김지훈 팀장", email="lead@example.com")
        db.add(persona)
        db.flush()
        db.add(
            models.HistoryItem(
                user_id=user.id,
                persona_id=persona.id,
                brief="연결된 히스토리",
                subject="연결된 히스토리",
                body="삭제 보호 확인",
            )
        )
        db.commit()
        persona_id = persona.id

    deleted = client.delete(f"/personas/{persona_id}")

    assert deleted.status_code == 409
    assert deleted.json()["detail"] == "히스토리와 연결된 페르소나는 삭제할 수 없습니다."
    assert client.get("/history").json()[0]["personaId"] == persona_id


def test_history_endpoint_returns_frontend_compatible_shape():
    client, user = authed_client()
    with SessionLocal() as db:
        history = models.HistoryItem(
            user_id=user.id,
            brief="회의 일정 변경",
            tone=2,
            length=4,
            subject="[Mello] 회의 일정 변경 요청",
            body="안녕하세요.\n회의 일정 변경 가능하실까요?",
            status="draft",
        )
        db.add(history)
        db.commit()

    response = client.get("/history")
    assert response.status_code == 200
    item = response.json()[0]
    assert item["subj"] == "[Mello] 회의 일정 변경 요청"
    assert item["prev"].startswith("안녕하세요.")
    assert item["status"] == "draft"
    assert item["tone"] == "격식"
    assert item["toneValue"] == 2
    assert item["length"] == "길게"
    assert item["lengthValue"] == 4


def test_generate_stream_persists_history(monkeypatch):
    async def fake_stream(_settings, _messages):
        yield "Subject: 테스트 제목\n"
        yield "Body:\n테스트 본문입니다."

    monkeypatch.setattr("app.routers.ai.stream_solar_text", fake_stream)
    client, _ = authed_client()

    response = client.post("/ai/generate", json={"brief": "테스트 메일 작성", "tone": 3, "length": 3})
    assert response.status_code == 200
    body = response.text
    assert "event: delta" in body
    assert "event: done" in body
    assert "테스트 제목" in body

    history = client.get("/history").json()
    assert len(history) == 1
    assert history[0]["subject"] == "테스트 제목"
    assert history[0]["body"] == "테스트 본문입니다."
    assert history[0]["tone"] == "중립"
    assert history[0]["toneValue"] == 3
    assert history[0]["length"] == "보통"
    assert history[0]["lengthValue"] == 3


def test_generate_accepts_legacy_percentage_scale(monkeypatch):
    async def fake_stream(_settings, _messages):
        yield "Subject: 레거시 제목\n"
        yield "Body:\n레거시 본문입니다."

    monkeypatch.setattr("app.routers.ai.stream_solar_text", fake_stream)
    client, _ = authed_client()

    response = client.post("/ai/generate", json={"brief": "레거시 스케일", "tone": 75, "length": 100})
    assert response.status_code == 200

    history = client.get("/history").json()
    assert history[0]["tone"] == "친근"
    assert history[0]["toneValue"] == 4
    assert history[0]["length"] == "매우 길게"
    assert history[0]["lengthValue"] == 5

    invalid = client.post("/ai/generate", json={"brief": "잘못된 스케일", "tone": 101, "length": 3})
    assert invalid.status_code == 422


def test_generate_links_reply_sender_to_existing_persona(monkeypatch):
    async def fake_stream(_settings, _messages):
        yield "Subject: 답장 제목\n"
        yield "Body:\n답장 본문입니다."

    monkeypatch.setattr("app.routers.ai.stream_solar_text", fake_stream)
    client, user = authed_client()
    with SessionLocal() as db:
        persona = models.Persona(user_id=user.id, name="김지훈 팀장", email="lead@example.com")
        db.add(persona)
        db.commit()
        db.refresh(persona)
        persona_id = persona.id

    response = client.post(
        "/ai/generate",
        json={
            "brief": "",
            "tone": 3,
            "length": 3,
            "replyContext": {
                "gmailMessageId": "gmail-in-1",
                "fromAddr": "김지훈 팀장 <LEAD@example.com>",
                "subject": "일정 확인",
                "snippet": "내일 일정 가능할까요?",
                "rawBody": "내일 일정 가능할까요?",
                "threadId": "thread-1",
                "messageId": "<message-1@example.com>",
            },
        },
    )
    assert response.status_code == 200
    assert f'"personaId": "{persona_id}"' in response.text

    history = client.get("/history", params={"personaEmail": "lead@example.com"}).json()
    assert len(history) == 1
    assert history[0]["personaId"] == persona_id
    assert history[0]["personaEmail"] == "lead@example.com"
    assert history[0]["counterpartyEmail"] == "lead@example.com"
    assert history[0]["replyContext"]["senderEmail"] == "lead@example.com"


def test_gmail_send_uses_history_persona_email_and_updates_history(monkeypatch):
    sent = {}

    async def fake_send_gmail_message(_db, _settings, _user, *, to, subject, body, cc, bcc, reply_context):
        sent.update({"to": to, "subject": subject, "body": body, "cc": cc, "bcc": bcc, "reply_context": reply_context})
        return {"id": "gmail-out-1", "threadId": "thread-out-1"}

    monkeypatch.setattr("app.routers.gmail.send_gmail_message", fake_send_gmail_message)
    client, user = authed_client()
    with SessionLocal() as db:
        persona = models.Persona(user_id=user.id, name="김지훈 팀장", email="lead@example.com")
        db.add(persona)
        db.flush()
        history = models.HistoryItem(
            user_id=user.id,
            persona_id=persona.id,
            brief="일정 안내",
            subject="일정 안내",
            body="내일 뵙겠습니다.",
            status="draft",
        )
        db.add(history)
        db.commit()
        history_id = history.id

    response = client.post(
        "/gmail/send",
        json={"historyId": history_id, "subject": "일정 안내", "body": "내일 뵙겠습니다."},
    )
    assert response.status_code == 200
    assert sent["to"] == "lead@example.com"
    payload = response.json()
    assert payload["history"]["status"] == "sent"
    assert payload["history"]["personaEmail"] == "lead@example.com"


def test_gmail_send_rejects_blank_subject_or_body(monkeypatch):
    async def fake_send_gmail_message(*_args, **_kwargs):
        raise AssertionError("Gmail send should not be called for invalid content")

    monkeypatch.setattr("app.routers.gmail.send_gmail_message", fake_send_gmail_message)
    client, _ = authed_client()

    blank_subject = client.post(
        "/gmail/send",
        json={"to": "lead@example.com", "subject": "   ", "body": "본문입니다."},
    )
    blank_body = client.post(
        "/gmail/send",
        json={"to": "lead@example.com", "subject": "제목입니다.", "body": "\n\t"},
    )

    assert blank_subject.status_code == 422
    assert "제목은 비워둘 수 없습니다." in blank_subject.text
    assert blank_body.status_code == 422
    assert "본문은 비워둘 수 없습니다." in blank_body.text


def test_google_post_json_maps_auth_and_retry_errors(monkeypatch):
    original_async_client = google_service.httpx.AsyncClient

    def call_with_status(status_code: int) -> tuple[int, str]:
        transport = httpx.MockTransport(lambda _request: httpx.Response(status_code, json={}))
        monkeypatch.setattr(
            google_service.httpx,
            "AsyncClient",
            lambda *args, **kwargs: original_async_client(transport=transport),
        )
        try:
            asyncio.run(
                google_service.google_post_json("https://gmail.test/send", "token", {"raw": "x"})
            )
        except HTTPException as exc:
            return exc.status_code, str(exc.detail)
        raise AssertionError("Google API error was not raised")

    assert call_with_status(401) == (401, "Google 재인증이 필요합니다. 다시 로그인해주세요.")
    assert call_with_status(403) == (
        403,
        "Gmail 권한이 부족합니다. Google 권한을 다시 동의해주세요.",
    )
    assert call_with_status(429) == (
        429,
        "Gmail 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
    )
    assert call_with_status(500) == (502, "Gmail 발송에 실패했습니다.")


def test_gmail_message_detail_marks_matching_persona(monkeypatch):
    async def fake_detail(_db, _settings, _user, _message_id):
        from app.schemas import GmailMessageOut

        return (
            GmailMessageOut(
                id="gmail-in-1",
                threadId="thread-1",
                fromAddr="김지훈 팀장 <LEAD@example.com>",
                senderEmail="lead@example.com",
                subject="일정 확인",
                snippet="내일 일정 가능할까요?",
                messageId="<message-1@example.com>",
            ),
            "내일 일정 가능할까요?",
        )

    monkeypatch.setattr("app.routers.gmail.get_gmail_message_detail", fake_detail)
    client, user = authed_client()
    with SessionLocal() as db:
        persona = models.Persona(user_id=user.id, name="김지훈 팀장", email="lead@example.com")
        db.add(persona)
        db.commit()
        db.refresh(persona)
        persona_id = persona.id

    response = client.get("/gmail/messages/gmail-in-1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["personaId"] == persona_id
    assert payload["replyContext"]["personaId"] == persona_id
    assert payload["replyContext"]["senderEmail"] == "lead@example.com"


def _gmail_metadata(message_id: str, subject: str | None = None, from_addr: str | None = None) -> dict:
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "snippet": f"snippet-{message_id}",
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr or f"Sender {message_id} <sender-{message_id}@example.com>"},
                {"name": "Subject", "value": subject or f"subject-{message_id}"},
                {"name": "Date", "value": "Sat, 23 May 2026 12:00:00 +0000"},
                {"name": "Message-ID", "value": f"<{message_id}@example.com>"},
                {"name": "References", "value": "<root@example.com>"},
            ]
        },
    }


def test_gmail_messages_returns_paginated_envelope(monkeypatch):
    async def fake_access_token(_db, _settings, _user):
        return "gmail-access-token"

    calls = []

    async def fake_google_get(_client, url, access_token, params=None):
        calls.append({"url": url, "access_token": access_token, "params": params})
        if url.endswith("/messages"):
            return {
                "messages": [{"id": "msg-1"}, {"id": "msg-2"}],
                "nextPageToken": "next-token",
                "resultSizeEstimate": 42,
            }
        return _gmail_metadata(url.rsplit("/", 1)[-1])

    monkeypatch.setattr("app.services.google.google_access_token", fake_access_token)
    monkeypatch.setattr("app.services.google._google_get_json_with_client", fake_google_get)
    client, _ = authed_client()

    response = client.get("/gmail/messages?limit=2")

    assert response.status_code == 200
    body = response.json()
    assert body["nextPageToken"] == "next-token"
    assert body["resultSizeEstimate"] == 42
    assert body["limit"] == 2
    assert body["hasMore"] is True
    assert [message["id"] for message in body["messages"]] == ["msg-1", "msg-2"]
    assert body["messages"][0]["from"] == "Sender msg-1 <sender-msg-1@example.com>"
    assert calls[0]["access_token"] == "gmail-access-token"
    assert calls[0]["params"] == {"maxResults": 2, "q": 'in:inbox -from:"user@example.com"', "includeSpamTrash": "false"}


def test_gmail_messages_excludes_current_user_sender(monkeypatch):
    async def fake_access_token(_db, _settings, _user):
        return "gmail-access-token"

    async def fake_google_get(_client, url, _access_token, params=None):
        if url.endswith("/messages"):
            return {
                "messages": [{"id": "self-sent"}, {"id": "external"}],
                "resultSizeEstimate": 2,
            }
        message_id = url.rsplit("/", 1)[-1]
        if message_id == "self-sent":
            return _gmail_metadata(message_id, from_addr="Tester <USER@example.com>")
        return _gmail_metadata(message_id, from_addr="External Sender <external@example.com>")

    monkeypatch.setattr("app.services.google.google_access_token", fake_access_token)
    monkeypatch.setattr("app.services.google._google_get_json_with_client", fake_google_get)
    client, _ = authed_client()

    response = client.get("/gmail/messages?limit=2")

    assert response.status_code == 200
    assert [message["id"] for message in response.json()["messages"]] == ["external"]


def test_gmail_messages_forwards_page_token_and_marks_final_page(monkeypatch):
    async def fake_access_token(_db, _settings, _user):
        return "gmail-access-token"

    list_params = []

    async def fake_google_get(_client, url, _access_token, params=None):
        if url.endswith("/messages"):
            list_params.append(params)
            return {"messages": [{"id": "msg-3"}], "resultSizeEstimate": 3}
        return _gmail_metadata(url.rsplit("/", 1)[-1], subject="final page")

    monkeypatch.setattr("app.services.google.google_access_token", fake_access_token)
    monkeypatch.setattr("app.services.google._google_get_json_with_client", fake_google_get)
    client, _ = authed_client()

    response = client.get("/gmail/messages?limit=30&pageToken=opaque-token")

    assert response.status_code == 200
    assert list_params == [
        {"maxResults": 30, "q": 'in:inbox -from:"user@example.com"', "includeSpamTrash": "false", "pageToken": "opaque-token"}
    ]
    body = response.json()
    assert body["nextPageToken"] is None
    assert body["hasMore"] is False
    assert body["messages"][0]["subject"] == "final page"


def test_gmail_messages_handles_empty_page(monkeypatch):
    async def fake_access_token(_db, _settings, _user):
        return "gmail-access-token"

    async def fake_google_get(_client, url, _access_token, params=None):
        assert url.endswith("/messages")
        assert params == {"maxResults": 10, "q": 'in:inbox -from:"user@example.com"', "includeSpamTrash": "false"}
        return {"messages": [], "resultSizeEstimate": 0}

    monkeypatch.setattr("app.services.google.google_access_token", fake_access_token)
    monkeypatch.setattr("app.services.google._google_get_json_with_client", fake_google_get)
    client, _ = authed_client()

    response = client.get("/gmail/messages?limit=10")

    assert response.status_code == 200
    assert response.json() == {
        "messages": [],
        "nextPageToken": None,
        "resultSizeEstimate": 0,
        "limit": 10,
        "hasMore": False,
    }


def test_gmail_messages_validates_limit_bounds():
    client, _ = authed_client()

    too_small = client.get("/gmail/messages?limit=0")
    too_large = client.get("/gmail/messages?limit=101")

    assert too_small.status_code == 422
    assert too_large.status_code == 422
