import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import DatabaseNotConfigured, get_engine
from app.dependencies import AppSettings, DbSession
from app.models import Company
from app.repositories.catalog import (
    CatalogFilters,
    company_focus_order,
    comparison_preview,
    dashboard_summary,
    filter_options,
    list_offers,
)
from app.repositories.comparisons import save_comparison
from app.repositories.matching import catalog_match_report
from app.routers.auth import clear_auth_cookies, set_auth_cookies
from app.services.auth import authenticate, create_login_session, find_auth_context
from app.services.security import secrets_match


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


NAV_ITEMS = (
    ("Visão geral", "/"),
    ("Catálogos", "/catalogos"),
    ("Comparador", "/comparador"),
    ("Aplicações e regiões", "/aplicacoes-regioes"),
    ("Cards", "/cards"),
    ("Meus alertas", "/alertas"),
    ("Gestão", "/gestao"),
    ("Importações e qualidade", "/importacoes"),
)


def require_page_auth(request: Request, db: DbSession, settings: AppSettings):
    context = find_auth_context(db, request.cookies.get(settings.session_cookie_name))
    if context is None:
        return None
    return context


def render_shell(request: Request, settings: AppSettings, title: str):
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return RedirectResponse("/login", status_code=303)
    try:
        engine = get_engine()
    except DatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    with Session(engine) as db:
        auth = find_auth_context(db, raw_token)
        if auth is None:
            return RedirectResponse("/login", status_code=303)
        companies = db.scalars(
            select(Company)
            .where(Company.organization_id == auth.user.organization_id, Company.active.is_(True))
            .order_by(*company_focus_order())
        ).all()
        page_context = {
            "title": title,
            "user": auth.user,
            "nav_items": NAV_ITEMS,
            "companies": companies,
            "active_path": request.url.path,
            "csrf_token": request.cookies.get(settings.csrf_cookie_name, ""),
        }
        if title == "Visão geral":
            page_context["summary"] = dashboard_summary(db, auth.user.organization_id)
            matching = catalog_match_report(db, auth.user.organization_id, limit=3)
            matching["price_highlights"] = [
                item for item in matching["items"]
                if item["status"] in ("confirmado", "sugerido")
            ]
            page_context["matching"] = matching
        elif title == "Catálogos":
            query = request.query_params
            try:
                page = max(1, int(query.get("page", "1")))
            except ValueError:
                page = 1
            page_size = 48 if query.get("page_size") == "48" else 24
            catalog_filters = CatalogFilters(
                search=query.get("q") or None,
                companies=tuple(query.getlist("company")),
                brands=tuple(query.getlist("brand")),
                availability=tuple(query.getlist("availability")),
            )
            page_context["catalog"] = list_offers(
                db,
                auth.user.organization_id,
                catalog_filters,
                page=page,
                page_size=page_size,
            )
            page_context["filter_options"] = filter_options(db, auth.user.organization_id)
            page_context["selected_filters"] = catalog_filters
            page_context["pagination_query"] = urlencode(
                [(key, value) for key, value in query.multi_items() if key != "page"]
            )
        elif title == "Comparador":
            page_context["matching"] = catalog_match_report(
                db,
                auth.user.organization_id,
                competitor_code=request.query_params.get("company"),
            )
    return templates.TemplateResponse(
        request,
        "shell.html",
        page_context,
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request, "login.html", {"title": "Entrar", "error": None}
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    email: str = Form(...),
    password: str = Form(...),
):
    user = authenticate(db, email, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"title": "Entrar", "error": "E-mail ou senha inválidos."},
            status_code=401,
        )
    created = create_login_session(db, user, settings)
    db.commit()
    response = RedirectResponse("/", status_code=303)
    set_auth_cookies(response, created.raw_token, created.raw_csrf, settings)
    return response


@router.post("/logout")
def logout_page(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    csrf_token: str = Form(...),
):
    auth = require_page_auth(request, db, settings)
    if auth is None:
        return RedirectResponse("/login", status_code=303)
    if not secrets_match(auth.login_session.csrf_hash, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")
    auth.login_session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    response = RedirectResponse("/login", status_code=303)
    clear_auth_cookies(response, settings)
    return response


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, settings: AppSettings):
    return render_shell(request, settings, "Visão geral")


@router.post("/comparador/salvar")
def save_comparison_page(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    title: str = Form(...),
    offer: list[str] = Form(...),
    reference: str | None = Form(default=None),
    csrf_token: str = Form(...),
):
    auth = require_page_auth(request, db, settings)
    if auth is None:
        return RedirectResponse("/login", status_code=303)
    if not secrets_match(auth.login_session.csrf_hash, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")
    try:
        offer_ids = [uuid.UUID(value) for value in offer]
        reference_offer_id = uuid.UUID(reference) if reference else None
        comparison = save_comparison(
            db,
            organization_id=auth.user.organization_id,
            creator_id=auth.user.id,
            title=title,
            offer_ids=offer_ids,
            reference_offer_id=reference_offer_id,
            allow_excluded=auth.user.role == "gestor",
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    parameters = [("offer", str(offer_id)) for offer_id in offer_ids]
    if reference_offer_id is not None:
        parameters.append(("reference", str(reference_offer_id)))
    parameters.append(("saved", str(comparison.id)))
    return RedirectResponse(f"/comparador?{urlencode(parameters)}", status_code=303)


@router.get("/{page:path}", response_class=HTMLResponse)
def feature_page(page: str, request: Request, settings: AppSettings):
    route_titles = {path.strip("/"): label for label, path in NAV_ITEMS if path != "/"}
    if page not in route_titles:
        raise HTTPException(status_code=404, detail="Página não encontrada.")
    return render_shell(request, settings, route_titles[page])
