import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import DatabaseNotConfigured, get_engine
from app.dependencies import AppSettings, DbSession
from app.models import Company, Offer
from app.repositories.catalog import (
    CatalogFilters,
    company_focus_order,
    comparison_preview,
    dashboard_summary,
    filter_options,
    list_offers,
)
from app.repositories.comparisons import save_comparison
from app.repositories.matching import catalog_gap_report, catalog_match_report
from app.routers.auth import clear_auth_cookies, set_auth_cookies
from app.services.auth import authenticate, create_login_session, find_auth_context
from app.services.catalog_import import parse_decimal
from app.services.comparable_snapshot import load_snapshot, snapshot_view
from app.services.dimensional_dashboard import load_dimensional_database_status, load_dimensional_staging
from app.services.pipeline_staging import load_staging_audit
from app.services.security import secrets_match


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


NAV_ITEMS = (
    ("Visão geral", "/"),
    ("Catálogos", "/catalogos"),
    ("Digitalização", "/digitalizacao"),
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
            page_context["dimensional_staging"] = load_dimensional_staging()
            page_context["dimensional_database"] = load_dimensional_database_status(auth.user.organization_id)
            page_context["dimensional_published_count"] = next(
                (
                    item["count"]
                    for item in page_context["summary"]["company_counts"]
                    if item["code"] == "dimensional"
                ),
                0,
            )
            comparable = load_snapshot(db, auth.user.organization_id)
            page_context["comparable"] = snapshot_view(comparable) if comparable else None
            matching = catalog_match_report(db, auth.user.organization_id, limit=3)
            matching["price_highlights"] = [
                item for item in matching["items"]
                if item["status"] in ("confirmado", "sugerido")
            ]
            page_context["matching"] = matching
        elif title == "Importações e qualidade":
            page_context["pipeline_audit"] = load_staging_audit() if auth.user.role == "gestor" else None
            page_context["dimensional_staging"] = load_dimensional_staging() if auth.user.role == "gestor" else None
            page_context["dimensional_database"] = load_dimensional_database_status(auth.user.organization_id) if auth.user.role == "gestor" else None
        elif title == "Catálogos":
            query = request.query_params
            try:
                page = max(1, int(query.get("page", "1")))
            except ValueError:
                page = 1
            page_size = int(query.get("page_size")) if query.get("page_size") in {"24", "48", "100", "200"} else 100
            filter_error = None
            prices: dict[str, Decimal | None] = {"price_min": None, "price_max": None}
            for key in prices:
                if query.get(key):
                    try:
                        parsed = parse_decimal(query[key])
                        if parsed is None or not parsed.is_finite() or parsed < 0:
                            raise InvalidOperation
                        prices[key] = parsed
                    except (InvalidOperation, ValueError):
                        filter_error = "Informe preços válidos e não negativos."
                        prices = {"price_min": None, "price_max": None}
                        break
            modality = query.get("modality") if query.get("modality") in {"venda", "pix", "cartao"} else None
            if prices["price_min"] is not None and prices["price_max"] is not None and prices["price_min"] > prices["price_max"]:
                filter_error = "O preço mínimo não pode superar o máximo."
                prices = {"price_min": None, "price_max": None}
            search = (query.get("q") or "")[:200]
            if len(search.split()) > 8:
                filter_error = "Use no máximo oito termos na pesquisa."
                search = ""
            catalog_filters = CatalogFilters(
                search=search or None,
                companies=tuple(value for value in query.getlist("company") if value),
                brands=tuple(value for value in query.getlist("brand") if value),
                availability=tuple(value for value in query.getlist("availability") if value),
                family_group=(query.get("family_group") or "")[:255] or None,
                modality=modality,
                price_min=prices["price_min"],
                price_max=prices["price_max"],
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
            page_context["filter_error"] = filter_error
            page_context["search_input"] = (query.get("q") or "")[:200]
            page_context["price_inputs"] = {
                "min": query.get("price_min", ""),
                "max": query.get("price_max", ""),
            }
            page_context["pagination_query"] = urlencode(
                [(key, value) for key, value in query.multi_items() if key != "page"]
            )
        elif title == "Comparador":
            comparable = load_snapshot(db, auth.user.organization_id)
            query = request.query_params
            try:
                comparable_page = int(query.get("comparable_page", "1"))
            except ValueError:
                comparable_page = 1
            page_context["comparable"] = snapshot_view(
                comparable, (query.get("macro") or "")[:255],
                (query.get("signal") or "")[:40], comparable_page,
            ) if comparable else None
            matching = catalog_match_report(
                db,
                auth.user.organization_id,
                competitor_code=request.query_params.get("company"),
            )
            gap_type = query.get("gap_type") if query.get("gap_type") in {"brand", "family"} else None
            gap_key = (query.get("gap_key") or "")[:255]
            try:
                gap_page = max(1, int(query.get("gap_page", "1")))
            except ValueError:
                gap_page = 1
            page_context["matching"] = matching
            page_context["gaps"] = catalog_gap_report(
                db, auth.user.organization_id, matching,
                gap_type=gap_type, gap_key=gap_key, page=gap_page,
            )
            page_context["gap_query"] = urlencode({
                "company": matching["selected_company"]["code"] if matching["selected_company"] else "",
                "gap_type": gap_type or "",
                "gap_key": gap_key,
            })
            page_context["comparable_query"] = urlencode({
                "company": matching["selected_company"]["code"] if matching["selected_company"] else "",
                "macro": page_context["comparable"]["macro"] if comparable else "",
                "signal": page_context["comparable"]["signal"] if comparable else "",
            })
        elif title == "Comparação direta":
            try:
                offer_ids = [uuid.UUID(value) for value in request.query_params.getlist("offer")]
                reference_raw = request.query_params.get("reference")
                reference_id = uuid.UUID(reference_raw) if reference_raw else None
                if not 2 <= len(set(offer_ids)) <= 8:
                    raise ValueError("Selecione entre 2 e 8 produtos distintos.")
                conditions = [
                    Offer.organization_id == auth.user.organization_id,
                    Offer.id.in_(offer_ids),
                    Offer.active.is_(True),
                ]
                if auth.user.role != "gestor":
                    conditions.append(Offer.excluded_from_analytics.is_(False))
                allowed = set(db.scalars(select(Offer.id).where(*conditions)))
                if allowed != set(offer_ids):
                    raise LookupError("Um dos produtos selecionados não está disponível para comparação.")
                page_context["direct"] = comparison_preview(
                    db, auth.user.organization_id, offer_ids, reference_offer_id=reference_id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@router.get("/comparacao-direta", response_class=HTMLResponse)
def direct_comparison(request: Request, settings: AppSettings):
    return render_shell(request, settings, "Comparação direta")


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
