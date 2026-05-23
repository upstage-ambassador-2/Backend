import base64
import hashlib
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import Settings
from app.models import utcnow


def _fernet_key(settings: Settings) -> bytes:
    if settings.token_encryption_key:
        return settings.token_encryption_key.encode("utf-8")
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_token(value: str, settings: Settings) -> str:
    return Fernet(_fernet_key(settings)).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_token(value: str | None, settings: Settings) -> str | None:
    if not value:
        return None
    try:
        return Fernet(_fernet_key(settings)).decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("stored OAuth token cannot be decrypted") from exc


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(settings: Settings):
    return utcnow() + timedelta(days=settings.session_ttl_days)


def state_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="mello-google-oauth-state")


def sign_oauth_state(payload: dict[str, str], settings: Settings) -> str:
    return state_serializer(settings).dumps(payload)


def load_oauth_state(value: str, settings: Settings, max_age: int = 600) -> dict[str, str]:
    try:
        data = state_serializer(settings).loads(value, max_age=max_age)
    except BadSignature as exc:
        raise ValueError("invalid OAuth state") from exc
    if not isinstance(data, dict):
        raise ValueError("invalid OAuth state")
    return {str(k): str(v) for k, v in data.items()}
