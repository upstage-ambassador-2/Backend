import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test-mello.db"
os.environ["SECRET_KEY"] = "test-secret-key-with-enough-length"
os.environ["SOLAR_API_KEY"] = "test-solar-key"

from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_token, session_expiry  # noqa: E402


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


def test_persona_crud():
    client, _ = authed_client()

    created = client.post(
        "/personas",
        json={
            "name": "김지훈 팀장",
            "relation": "회사 · 직속 상사",
            "tone": "결론 우선",
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

    patched = client.patch(f"/personas/{persona_id}", json={"tone": "정중", "tagColor": "green"})
    assert patched.status_code == 200
    assert patched.json()["tone"] == "정중"
    assert patched.json()["tagColor"] == "green"

    deleted = client.delete(f"/personas/{persona_id}")
    assert deleted.status_code == 204
    assert client.get("/personas").json() == []


def test_history_endpoint_returns_frontend_compatible_shape():
    client, user = authed_client()
    with SessionLocal() as db:
        history = models.HistoryItem(
            user_id=user.id,
            brief="회의 일정 변경",
            tone=20,
            length=70,
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


def test_generate_stream_persists_history(monkeypatch):
    async def fake_stream(_settings, _messages):
        yield "Subject: 테스트 제목\n"
        yield "Body:\n테스트 본문입니다."

    monkeypatch.setattr("app.routers.ai.stream_solar_text", fake_stream)
    client, _ = authed_client()

    response = client.post("/ai/generate", json={"brief": "테스트 메일 작성", "tone": 50, "length": 50})
    assert response.status_code == 200
    body = response.text
    assert "event: delta" in body
    assert "event: done" in body
    assert "테스트 제목" in body

    history = client.get("/history").json()
    assert len(history) == 1
    assert history[0]["subject"] == "테스트 제목"
    assert history[0]["body"] == "테스트 본문입니다."


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
            "tone": 50,
            "length": 50,
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
