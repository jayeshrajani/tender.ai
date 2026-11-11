"""Password hashing, opaque session tokens and invitation tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthSession, User
from app.services.timeutil import utcnow

_hasher = PasswordHasher()
# Equalises timing for unknown emails.
_DUMMY_HASH = _hasher.hash("tenderos-dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(user: User | None, password: str) -> bool:
    try:
        return _hasher.verify(user.password_hash if user else _DUMMY_HASH, password) and user is not None
    except (VerificationError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def create_session(db: Session, user: User, organization_id: uuid.UUID | None) -> str:
    token = new_token()
    now = utcnow()
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at < now))
    db.add(
        AuthSession(
            token_hash=token_hash(token),
            user_id=user.id,
            organization_id=organization_id,
            expires_at=now + timedelta(hours=get_settings().session_ttl_hours),
            created_at=now,
            last_seen_at=now,
        )
    )
    user.last_login_at = now
    db.flush()
    return token
