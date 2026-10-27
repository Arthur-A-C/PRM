import uuid
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import inspect

from app.dependencies import CurrentAuth, DbSession
from app.repositories.catalog import (
    CatalogFilters,
    comparison_preview,
    filter_options,
    get_offer_detail,
    list_offers,
)
from app.repositories.comparisons import get_saved_comparison, save_comparison
from app.repositories.matching import catalog_gap_report, catalog_match_report
from app.schemas.comparison import ComparisonCreate
from app.services.comparable_snapshot import load_snapshot, snapshot_view
from app.services.security import secrets_match
from app.services.current_analysis import summarize_current
from app.services.refined_catalog_database import database_manifest
from app.services.access import MANAGERS, public_product_data


router = APIRouter(prefix="/api/v1", tags=["catálogos"])


@router.get("/dashboard/summary")
def summary(auth: CurrentAuth, db: DbSession) -> dict:
    manifest = database_manifest(db, auth.user.organization_id) if inspect(db.get_bind()).has_table("refined_catalog_runs") else None
    return summarize_current(manifest)


@router.get("/filters/options")
def options(auth: CurrentAuth, db: DbSession) -> dict:
    return filter_options(db, auth.user.organization_id)


@router.get("/products")
def products(
    auth: CurrentAuth,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    source_group: str | None = Query(default=None, pattern="^(internal|competitor)$"),
    company: list[str] = Query(default=[]),
    brand: list[str] = Query(default=[]),
    availability: list[str] = Query(default=[]),
    family_group: str | None = Query(default=None, max_length=255),
    modality: str | None = Query(default=None, pattern="^(pix|cartao|venda)$"),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    include_excluded: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
) -> dict:
    if q and len(q.split()) > 8:
        raise HTTPException(status_code=422, detail="Use no máximo oito termos na pesquisa.")
    if page_size not in {24, 48, 100, 200}:
        raise HTTPException(status_code=422, detail="page_size deve ser 24, 48, 100 ou 200.")
    if price_min is not None and price_max is not None and price_min > price_max:
        raise HTTPException(status_code=422, detail="price_min não pode ser maior que price_max.")
    if include_excluded and auth.user.role not in {"gestor", "desenvolvedor"}:
        raise HTTPException(status_code=403, detail="Somente gestores podem incluir exclusões analíticas.")
    filters = CatalogFilters(
        source_group=source_group,
        search=q,
        companies=tuple(value for value in company if value),
        brands=tuple(value for value in brand if value),
        availability=tuple(value for value in availability if value),
        family_group=family_group,
        modality=modality,
        price_min=price_min,
        price_max=price_max,
        include_excluded=include_excluded,
    )
    return list_offers(
        db, auth.user.organization_id, filters, page=page, page_size=page_size
    )


@router.get("/products/{offer_id}")
def product(offer_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> dict:
    detail = get_offer_detail(db, auth.user.organization_id, offer_id)
    if detail is None or (
        detail["excluded_from_analytics"] and auth.user.role not in {"gestor", "desenvolvedor"}
    ):
        raise HTTPException(status_code=404, detail="Oferta não encontrada.")
    return detail if auth.user.role in MANAGERS else public_product_data(detail)


@router.get("/comparisons/preview")
def compare_preview(
    auth: CurrentAuth,
    db: DbSession,
    offer: list[uuid.UUID] = Query(default=[]),
    reference: uuid.UUID | None = Query(default=None),
) -> dict:
    try:
        comparison = comparison_preview(
            db, auth.user.organization_id, offer, reference_offer_id=reference
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if auth.user.role not in {"gestor", "desenvolvedor"} and any(
        item["excluded_from_analytics"] for item in comparison["items"]
    ):
        raise HTTPException(status_code=404, detail="Uma oferta não foi encontrada.")
    return comparison if auth.user.role in MANAGERS else public_product_data(comparison)


@router.get("/catalog-matches")
def catalog_matches(
    auth: CurrentAuth,
    db: DbSession,
    company: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return catalog_match_report(
        db,
        auth.user.organization_id,
        competitor_code=company,
        limit=limit,
    )


@router.get("/catalog-gaps")
def catalog_gaps(
    auth: CurrentAuth,
    db: DbSession,
    company: str | None = Query(default=None, max_length=50),
    gap_type: str | None = Query(default=None, pattern="^(brand|family)$"),
    gap_key: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
) -> dict:
    matching = catalog_match_report(
        db, auth.user.organization_id, competitor_code=company, limit=1
    )
    return catalog_gap_report(
        db, auth.user.organization_id, matching,
        gap_type=gap_type, gap_key=gap_key, page=page,
    )


@router.get("/comparable-portfolio")
def comparable_portfolio(
    auth: CurrentAuth,
    db: DbSession,
    macro: str = Query(default="", max_length=255),
    signal: str = Query(default="", max_length=40),
    page: int = Query(default=1, ge=1),
) -> dict:
    snapshot = load_snapshot(db, auth.user.organization_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Retrato comparável ainda não publicado.")
    return snapshot_view(snapshot, macro, signal, page)


@router.post("/comparisons", status_code=201)
def create_comparison(
    payload: ComparisonCreate,
    auth: CurrentAuth,
    db: DbSession,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    if not csrf_token or not secrets_match(auth.login_session.csrf_hash, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")
    try:
        comparison = save_comparison(
            db,
            organization_id=auth.user.organization_id,
            creator_id=auth.user.id,
            title=payload.title,
            offer_ids=payload.offer_ids,
            reference_offer_id=payload.reference_offer_id,
            allow_excluded=auth.user.role in {"gestor", "desenvolvedor"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    saved = get_saved_comparison(
        db,
        organization_id=auth.user.organization_id,
        comparison_id=comparison.id,
    )
    return saved if auth.user.role in MANAGERS else public_product_data(saved)


@router.get("/comparisons/{comparison_id}")
def saved_comparison(
    comparison_id: uuid.UUID,
    auth: CurrentAuth,
    db: DbSession,
) -> dict:
    comparison = get_saved_comparison(
        db,
        organization_id=auth.user.organization_id,
        comparison_id=comparison_id,
    )
    if comparison is None or (
        auth.user.role not in {"gestor", "desenvolvedor"} and comparison["creator_id"] != auth.user.id
    ):
        raise HTTPException(status_code=404, detail="Comparação não encontrada.")
    return comparison if auth.user.role in MANAGERS else public_product_data(comparison)
