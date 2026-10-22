import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import DatabaseNotConfigured, get_engine
from app.dependencies import AppSettings, DbSession
from app.models import Company, Offer
from app.repositories.catalog import (
    CatalogFilters,
    company_focus_order,
    comparison_preview,
    filter_options,
    list_offers,
)
from app.repositories.comparisons import save_comparison
from app.routers.auth import clear_auth_cookies, set_auth_cookies
from app.services.auth import authenticate, create_login_session, find_auth_context
from app.services.catalog_import import parse_decimal
from app.services.refined_catalog_database import database_manifest, list_refined_items, current_items, current_comparison
from app.services.current_analysis import summarize_current
from app.services.operations_overview import operations_overview
from app.services.security import secrets_match
from app.services.access import MANAGERS, SELLER_PAGES, visible_navigation


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


NAV_ITEMS = (
    ("Visão geral", "/"),
    ("Catálogos", "/catalogos"),
    ("Digitalização", "/digitalizacao"),
    ("Integrações WooCommerce", "/integracoes-woocommerce"),
    ("Comparador", "/comparador"),
    ("Aplicações e regiões", "/aplicacoes-regioes"),
    ("Cards", "/cards"),
    ("Reuniões", "/reunioes"),
    ("Planner", "/planner"),
    ("Meus alertas", "/alertas"),
    ("Gestão", "/gestao"),
    ("Importações e qualidade", "/importacoes"),
)


def require_page_auth(request: Request, db: DbSession, settings: AppSettings):
    context = find_auth_context(db, request.cookies.get(settings.session_cookie_name))
    if context is None:
        return None
    return context


def render_shell(request: Request, settings: AppSettings, title: str, extra_context=None):
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
        if auth.user.role not in MANAGERS:
            if auth.user.role == "vendedor" and request.url.path in {"/", "/comparador"}:
                return RedirectResponse("/catalogos", status_code=303)
            if auth.user.role != "vendedor" or request.url.path not in SELLER_PAGES:
                raise HTTPException(403, "Seu nível de acesso não permite esta página.")
            if request.query_params.get("internal") == "1" or request.query_params.get("group") == "quality_review":
                raise HTTPException(403, "Detalhes internos de importação são restritos.")
        if title in {"Integrações WooCommerce", "Cadastro via API", "Publicação em Lote", "Resolução de Imagens"} and auth.user.role not in {"gestor", "desenvolvedor"}:
            raise HTTPException(403, "Somente gestores podem consultar integrações.")
        companies = db.scalars(
            select(Company)
            .where(Company.organization_id == auth.user.organization_id, Company.active.is_(True))
            .order_by(*company_focus_order())
        ).all()
        page_context = {
            "title": title,
            "user": auth.user,
            "nav_items": visible_navigation(auth.user.role, NAV_ITEMS),
            "companies": companies,
            "active_path": request.url.path,
            "csrf_token": request.cookies.get(settings.csrf_cookie_name, ""),
        }
        page_context.update(extra_context or {})
        refined_manifest = database_manifest(db, auth.user.organization_id) if inspect(engine).has_table("refined_catalog_runs") else None
        page_context["refined_analysis"] = refined_manifest if title in {"Visão geral", "Comparador", "Importações e qualidade"} else None
        if title in {"Visão geral", "Comparador", "Importações e qualidade"}:
            page_context["current_analysis"] = summarize_current(refined_manifest)
            page_context["operations"] = operations_overview() if auth.user.role in {"gestor", "desenvolvedor"} else {"status": "restricted", "items": []}
            return templates.TemplateResponse(request=request, name="shell.html", context=page_context)
        if title == "Comparação atual":
            try:
                ids = [uuid.UUID(value) for value in request.query_params.getlist("item")]
                if not 2 <= len(set(ids)) <= 8 or len(ids) != len(set(ids)):
                    raise ValueError("Selecione entre 2 e 8 produtos distintos.")
                items = current_items(db, auth.user.organization_id, ids,
                                      run_id=request.query_params.get("run_id"), internal=auth.user.role in {"gestor", "desenvolvedor"})
                page_context["current_comparison"] = current_comparison(items)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return templates.TemplateResponse(request=request, name="shell.html", context=page_context)
        if title == "Catálogos":
            query = request.query_params
            if refined_manifest and query.get("view") != "legacy":
                try:
                    refined_page = int(query.get("page", "1"))
                except ValueError:
                    refined_page = 1
                page_context["refined_catalog"] = list_refined_items(
                    db, auth.user.organization_id, source=query.get("source", ""),
                    family=query.get("family", ""), search=query.get("q", ""), page=refined_page,
                    internal=query.get("internal") == "1" and auth.user.role in {"gestor", "desenvolvedor"},
                    group=query.get("group", ""),
                )
                if query.get("reference"):
                    try:
                        reference = current_items(db, auth.user.organization_id, [uuid.UUID(query["reference"])],
                                                  run_id=query.get("run_id"), internal=auth.user.role in {"gestor", "desenvolvedor"})
                        page_context["catalog_reference"] = reference[0]
                    except ValueError as exc:
                        raise HTTPException(status_code=422, detail=str(exc)) from exc
                    except LookupError as exc:
                        raise HTTPException(status_code=404, detail=str(exc)) from exc
                page_context["refined_pagination"] = urlencode([(k, v) for k, v in query.multi_items() if k != "page"])
                return templates.TemplateResponse(request=request, name="shell.html", context=page_context)
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
                if auth.user.role not in {"gestor", "desenvolvedor"}:
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


@router.get("/comparacao-atual", response_class=HTMLResponse)
def current_comparison_page(request: Request, settings: AppSettings):
    return render_shell(request, settings, "Comparação atual")


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
            allow_excluded=auth.user.role in {"gestor", "desenvolvedor"},
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
    route_titles["digitalizacao/lotes"] = "Geração em Lote"
    route_titles["digitalizacao/cadastro-api"] = "Cadastro via API"
    route_titles["digitalizacao/publicacao-lote"] = "Publicação em Lote"
    route_titles["digitalizacao/resolucao-imagens"] = "Resolução de Imagens"
    if page not in route_titles:
        raise HTTPException(status_code=404, detail="Página não encontrada.")
    return render_shell(request, settings, route_titles[page])
