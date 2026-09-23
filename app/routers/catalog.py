import uuid
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import CurrentAuth, DbSession
from app.repositories.catalog import (
    CatalogFilters,
    comparison_preview,
    dashboard_summary,
    filter_options,
    get_offer_detail,
    list_offers,
)
from app.repositories.comparisons import get_saved_comparison, save_comparison
from app.repositories.matching import catalog_match_report
from app.schemas.comparison import ComparisonCreate
from app.services.security import secrets_match


router = APIRouter(prefix="/api/v1", tags=["catálogos"])


@router.get("/dashboard/summary")
def summary(auth: CurrentAuth, db: DbSession) -> dict:
    return dashboard_summary(db, auth.user.organization_id)


@router.get("/filters/options")
def options(auth: CurrentAuth, db: DbSession) -> dict:
    return filter_options(db, auth.user.organization_id)


@router.get("/products")
def products(
    auth: CurrentAuth,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    company: list[str] = Query(default=[]),
    brand: list[str] = Query(default=[]),
    availability: list[str] = Query(default=[]),
    modality: str | None = Query(default=None, pattern="^(pix|cartao|venda)$"),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    include_excluded: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24),
) -> dict:
    if price_min is not None and price_max is not None and price_min > price_max:
        raise HTTPException(status_code=422, detail="price_min não pode ser maior que price_max.")
    if include_excluded and auth.user.role != "gestor":
        raise HTTPException(status_code=403, detail="Somente gestores podem incluir exclusões analíticas.")
    filters = CatalogFilters(
        search=q,
        companies=tuple(company),
        brands=tuple(brand),
        availability=tuple(availability),
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
        detail["excluded_from_analytics"] and auth.user.role != "gestor"
    ):
        raise HTTPException(status_code=404, detail="Oferta não encontrada.")
    return detail


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
    if auth.user.role != "gestor" and any(
        item["excluded_from_analytics"] for item in comparison["items"]
    ):
        raise HTTPException(status_code=404, detail="Uma oferta não foi encontrada.")
    return comparison


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
            allow_excluded=auth.user.role == "gestor",
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
    return saved


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
        auth.user.role != "gestor" and comparison["creator_id"] != auth.user.id
    ):
        raise HTTPException(status_code=404, detail="Comparação não encontrada.")
    return comparison
