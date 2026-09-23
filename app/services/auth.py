from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import LoginSession, User
from app.services.security import (
    hash_secret,
    new_secret,
    normalize_email,
    verify_password,
)


@dataclass(frozen=True)
class CreatedSession:
    user: User
    login_session: LoginSession
    raw_token: str
    raw_csrf: str


@dataclass(frozen=True)
class AuthContext:
    user: User
    login_session: LoginSession


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if not user or not user.active or not verify_password(user.password_hash, password):
        return None
    return user


def create_login_session(db: Session, user: User, settings: Settings) -> CreatedSession:
    raw_token = new_secret()
    raw_csrf = new_secret()
    login_session = LoginSession(
        user_id=user.id,
        token_hash=hash_secret(raw_token),
        csrf_hash=hash_secret(raw_csrf),
        expires_at=datetime.now(timezone.utc)
        + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(login_session)
    db.flush()
    return CreatedSession(user, login_session, raw_token, raw_csrf)


def find_auth_context(db: Session, raw_token: str | None) -> AuthContext | None:
    if not raw_token:
        return None
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(User, LoginSession)
        .join(LoginSession, LoginSession.user_id == User.id)
        .where(
            LoginSession.token_hash == hash_secret(raw_token),
            LoginSession.revoked_at.is_(None),
            LoginSession.expires_at > now,
            User.active.is_(True),
        )
    ).one_or_none()
    return AuthContext(*row) if row else None

