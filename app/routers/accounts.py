"""Administrative account creation links, never public privilege selection."""
import re
from typing import Literal

from fastapi import APIRouter, Form, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from app.dependencies import AppSettings, CurrentAuth, DbSession
from app.models import User
from app.routers.pages import render_shell
from app.services.access import require_management
from app.services.security import hash_password, normalize_email, secrets_match

router = APIRouter(tags=["contas"])
Role = Literal["desenvolvedor", "gestor", "vendedor"]


@router.get("/contas/criar/{role}", include_in_schema=False)
def account_page(role: Role, request: Request, settings: AppSettings):
    return render_shell(request, settings, "Criar conta", {"account_role": role})


@router.post("/contas/criar/{role}", include_in_schema=False)
def account_create(role: Role, request: Request, settings: AppSettings,
                   auth: CurrentAuth, db: DbSession,
                   name: str = Form(min_length=1, max_length=200),
                   email: str = Form(min_length=3, max_length=320),
                   password: str = Form(default=""),
                   csrf_token: str = Form(default="")):
    require_management(auth.user)
    if not csrf_token or not secrets_match(auth.login_session.csrf_hash, csrf_token):
        raise HTTPException(403, "Token CSRF inválido.")
    name, email = name.strip(), normalize_email(email)
    if not 6 <= len(password) <= 1024:
        raise HTTPException(422, "A senha deve ter entre 6 e 1024 caracteres.")
    if not name or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "Informe nome e e-mail válidos.")
    user = User(name=name, email=email, password_hash=hash_password(password),
                organization_id=auth.user.organization_id, role=role, active=True)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Não foi possível cadastrar: e-mail já utilizado ou vínculo inválido.") from None
    # Never log or return the submitted password/hash. No automatic login as the new user.
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/contas/criar/{role}?criada=1", status_code=303)
