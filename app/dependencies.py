from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db_session
from app.services.auth import AuthContext, find_auth_context


DbSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_current_auth(
    request: Request,
    db: DbSession,
    settings: AppSettings,
) -> AuthContext:
    context = find_auth_context(db, request.cookies.get(settings.session_cookie_name))
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
        )
    return context


CurrentAuth = Annotated[AuthContext, Depends(get_current_auth)]

