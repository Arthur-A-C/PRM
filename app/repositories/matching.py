import uuid
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.models import Brand, CatalogMatch, CatalogMatchRun, Company, Offer, OfferObservation, OfferPrice


def _latest_prices(db: Session, offer_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    prices: dict[uuid.UUID, dict] = {offer_id: {} for offer_id in offer_ids}
    rows = db.execute(
        select(
            OfferObservation.offer_id,
            OfferPrice.modality,
            OfferPrice.amount,
            OfferPrice.state,
            OfferObservation.imported_at,
        )
        .join(OfferPrice, OfferPrice.observation_id == OfferObservation.id)
        .where(OfferObservation.offer_id.in_(offer_ids))
        .order_by(
            OfferObservation.offer_id,
            OfferPrice.modality,
            OfferObservation.imported_at.desc(),
        )
    )
    for row in rows:
        if row.modality not in prices[row.offer_id]:
            prices[row.offer_id][row.modality] = (
                row.amount if row.state == "valido" else None
            )
    return prices


def _preferred_price(prices: dict, priorities: tuple[str, ...]) -> tuple[str | None, Decimal | None]:
    for modality in priorities:
        amount = prices.get(modality)
        if amount is not None and amount > 0:
            return modality, amount
    return None, None


def _price_analysis(own_prices: dict, competitor_prices: dict) -> dict:
    own_modality, own_amount = _preferred_price(own_prices, ("venda", "pix", "cartao"))
    competitor_modality, competitor_amount = _preferred_price(
        competitor_prices, ("venda", "pix", "cartao")
    )
    result = {
        "own": {"modality": own_modality, "amount": own_amount},
        "competitor": {"modality": competitor_modality, "amount": competitor_amount},
        "difference_percent": None,
        "our_position": "nao_comparavel",
        "same_modality": own_modality == competitor_modality and own_modality is not None,
    }
    if own_amount is None or competitor_amount is None:
        return result
    difference = (
        (competitor_amount - own_amount) / own_amount * Decimal("100")
    ).quantize(Decimal("0.1"))
    result["difference_percent"] = difference
    result["our_position"] = (
        "igual" if difference == 0 else "abaixo" if difference > 0 else "acima"
    )
    return result


def catalog_match_report(
    db: Session,
    organization_id: uuid.UUID,
    *,
    competitor_code: str | None = None,
    limit: int = 50,
) -> dict:
    competitors = list(
        db.scalars(
            select(Company)
            .where(
                Company.organization_id == organization_id,
                Company.company_type == "concorrente",
                Company.active.is_(True),
            )
            .order_by(Company.name)
        )
    )
    if not competitors:
        return {"companies": [], "selected_company": None, "run": None, "summary": None, "items": []}
    selected = next(
        (company for company in competitors if company.code == competitor_code), competitors[0]
    )
    run = db.scalar(
        select(CatalogMatchRun)
        .where(
            CatalogMatchRun.organization_id == organization_id,
            CatalogMatchRun.competitor_company_id == selected.id,
            CatalogMatchRun.status == "completed",
        )
        .order_by(CatalogMatchRun.completed_at.desc())
        .limit(1)
    )
    base = {
        "companies": [
            {"code": company.code, "name": company.name} for company in competitors
        ],
        "selected_company": {"code": selected.code, "name": selected.name},
        "run": None,
        "summary": None,
        "items": [],
    }
    if run is None:
        return base

    status_counts = dict(
        db.execute(
            select(CatalogMatch.status, func.count())
            .where(CatalogMatch.run_id == run.id, CatalogMatch.rank == 1)
            .group_by(CatalogMatch.status)
        ).all()
    )
    confirmed = status_counts.get("confirmado", 0)
    suggested = status_counts.get("sugerido", 0)
    candidates = status_counts.get("candidato", 0)
    covered = confirmed + suggested
    no_candidate = max(run.competitor_total - confirmed - suggested - candidates, 0)
    base["run"] = {
        "id": run.id,
        "algorithm_version": run.algorithm_version,
        "completed_at": run.completed_at,
        "parameters": run.parameters,
    }
    base["summary"] = {
        "total": run.competitor_total,
        "confirmed": confirmed,
        "suggested": suggested,
        "candidates": candidates,
        "no_candidate": no_candidate,
        "coverage_count": covered,
        "coverage_percent": round(covered * 100 / run.competitor_total, 2)
        if run.competitor_total
        else 0,
        "candidate_percent": round(
            (covered + candidates) * 100 / run.competitor_total, 2
        )
        if run.competitor_total
        else 0,
    }

    competitor_offer = aliased(Offer)
    own_offer = aliased(Offer)
    own_company = aliased(Company)
    competitor_brand = aliased(Brand)
    own_brand = aliased(Brand)
    rows = db.execute(
        select(
            CatalogMatch,
            competitor_offer,
            own_offer,
            own_company,
            competitor_brand.canonical_name.label("competitor_brand_name"),
            own_brand.canonical_name.label("own_brand_name"),
        )
        .join(competitor_offer, competitor_offer.id == CatalogMatch.competitor_offer_id)
        .join(own_offer, own_offer.id == CatalogMatch.own_offer_id)
        .join(own_company, own_company.id == own_offer.company_id)
        .outerjoin(competitor_brand, competitor_brand.id == competitor_offer.brand_id)
        .outerjoin(own_brand, own_brand.id == own_offer.brand_id)
        .where(CatalogMatch.run_id == run.id, CatalogMatch.rank == 1)
        .order_by(
            case(
                (CatalogMatch.status == "confirmado", 0),
                (CatalogMatch.status == "sugerido", 1),
                else_=2,
            ),
            CatalogMatch.score.desc(),
            own_company.name,
        )
        .limit(max(1, min(limit, 200)))
    ).all()
    offer_ids = [identifier for row in rows for identifier in (row[1].id, row[2].id)]
    prices = _latest_prices(db, offer_ids) if offer_ids else {}
    base["items"] = [
        {
            "id": match.id,
            "status": match.status,
            "score": match.score,
            "confidence_percent": round(float(match.score) * 100, 1),
            "reasons": match.reasons,
            "competitor": {
                "id": competitor.id,
                "code": competitor.external_code,
                "name": competitor.name_raw,
                "brand": competitor_brand_name or competitor.brand_raw,
                "brand_raw": competitor.brand_raw,
            },
            "own": {
                "id": own.id,
                "company": own_company.name,
                "company_code": own_company.code,
                "code": own.external_code,
                "name": own.name_raw,
                "brand": own_brand_name or own.brand_raw,
                "brand_raw": own.brand_raw,
            },
            "price": _price_analysis(prices.get(own.id, {}), prices.get(competitor.id, {})),
        }
        for match, competitor, own, own_company, competitor_brand_name, own_brand_name in rows
    ]
    return base
