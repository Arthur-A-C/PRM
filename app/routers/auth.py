from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.dependencies import AppSettings, CurrentAuth, DbSession
from app.schemas.auth import LoginRequest, UserResponse
from app.services.auth import authenticate, create_login_session
from app.services.security import secrets_match


router = APIRouter(prefix="/api/v1/auth", tags=["autenticação"])


def set_auth_cookies(response: Response, token: str, csrf: str, settings: AppSettings) -> None:
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response, settings: AppSettings) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> UserResponse:
    user = authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )
    created = create_login_session(db, user, settings)
    db.commit()
    set_auth_cookies(response, created.raw_token, created.raw_csrf, settings)
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
def me(auth: CurrentAuth) -> UserResponse:
    return UserResponse.model_validate(auth.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    auth: CurrentAuth,
    db: DbSession,
    settings: AppSettings,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    if not csrf_token or not secrets_match(auth.login_session.csrf_hash, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")
    auth.login_session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    clear_auth_cookies(response, settings)
