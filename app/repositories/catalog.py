import math
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import and_, case, distinct, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AttributeDefinition,
    Brand,
    CatalogImport,
    Category,
    Company,
    ImportRow,
    Offer,
    OfferAttribute,
    OfferEnrichment,
    OfferObservation,
    OfferPrice,
)
from app.services.catalog_treatment import plain
from app.services.catalog_origin import GROUP_TYPES, source_group


@dataclass(frozen=True)
class CatalogFilters:
    source_group: str | None = None
    search: str | None = None
    companies: tuple[str, ...] = field(default_factory=tuple)
    brands: tuple[str, ...] = field(default_factory=tuple)
    availability: tuple[str, ...] = field(default_factory=tuple)
    family_group: str | None = None
    modality: str | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    include_excluded: bool = False


def company_focus_order() -> tuple:
    """Empresas próprias sempre precedem as demais; nome desempata."""
    return (
        case((Company.company_type == "nossa", 0), else_=1),
        Company.name,
    )


def latest_price(modality: str):
    return (
        select(OfferPrice.amount)
        .join(OfferObservation, OfferObservation.id == OfferPrice.observation_id)
        .where(
            OfferObservation.offer_id == Offer.id,
            OfferPrice.modality == modality,
            OfferPrice.state == "valido",
        )
        .order_by(OfferObservation.imported_at.desc())
        .limit(1)
        .correlate(Offer)
        .scalar_subquery()
    )


def price_range_condition(amount, minimum: Decimal | None, maximum: Decimal | None):
    if minimum is not None and maximum is not None:
        return amount.between(minimum, maximum)
    if minimum is not None:
        return amount >= minimum
    if maximum is not None:
        return amount <= maximum
    return amount.is_not(None)


def filter_conditions(organization_id: uuid.UUID, filters: CatalogFilters) -> list:
    conditions = [Offer.organization_id == organization_id, Offer.active.is_(True)]
    if filters.source_group:
        if filters.source_group not in GROUP_TYPES:
            raise ValueError("Origem inválida")
        conditions.append(Offer.company_id.in_(select(Company.id).where(
            Company.organization_id == organization_id,
            Company.company_type == GROUP_TYPES[filters.source_group],
        ).correlate(None)))
    if not filters.include_excluded:
        conditions.append(Offer.excluded_from_analytics.is_(False))
    if filters.companies:
        conditions.append(
            Offer.company_id.in_(
                select(Company.id)
                .where(Company.organization_id == organization_id, Company.code.in_(filters.companies))
                .correlate(None)
            )
        )
    if filters.brands:
        selected_brand_ids = (
            select(Brand.id)
            .where(Brand.canonical_name.in_(filters.brands))
            .correlate(None)
        )
        conditions.append(
            or_(
                Offer.brand_id.in_(selected_brand_ids),
                and_(Offer.brand_id.is_(None), "Não informada" in filters.brands),
            )
        )
    if filters.availability:
        conditions.append(Offer.availability_state.in_(filters.availability))
    if filters.family_group:
        conditions.append(
            select(OfferEnrichment.id)
            .where(
                OfferEnrichment.offer_id == Offer.id,
                OfferEnrichment.family_group == filters.family_group,
            )
            .correlate(Offer)
            .exists()
        )
    if filters.search:
        for term in filters.search.strip().split()[:8]:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            normalized = plain(term) if not any(character in term for character in "%_\\") else ""
            conditions.append(
                or_(
                    Offer.external_code.ilike(pattern, escape="\\"),
                    Offer.name_raw.ilike(pattern, escape="\\"),
                    Offer.brand_raw.ilike(pattern, escape="\\"),
                    Offer.manufacturer_code.ilike(pattern, escape="\\"),
                    Offer.reference.ilike(pattern, escape="\\"),
                    Offer.description_display.ilike(pattern, escape="\\"),
                    Offer.application_raw.ilike(pattern, escape="\\"),
                    Offer.category_raw.ilike(pattern, escape="\\"),
                    select(Brand.id).where(
                        Brand.id == Offer.brand_id,
                        Brand.canonical_name.ilike(pattern, escape="\\"),
                    ).correlate(Offer).exists(),
                    select(OfferEnrichment.id).where(
                        OfferEnrichment.offer_id == Offer.id,
                        or_(
                            OfferEnrichment.family.ilike(pattern, escape="\\"),
                            OfferEnrichment.family_group.ilike(pattern, escape="\\"),
                            OfferEnrichment.model_reference.ilike(pattern, escape="\\"),
                            OfferEnrichment.normalized_title.ilike(
                                f"%{normalized}%", escape="\\"
                            ) if normalized else False,
                        ),
                    ).correlate(Offer).exists(),
                )
            )
    if filters.modality:
        amount = latest_price(filters.modality)
        conditions.append(price_range_condition(amount, filters.price_min, filters.price_max))
    elif filters.price_min is not None or filters.price_max is not None:
        conditions.append(or_(*[
            price_range_condition(latest_price(modality), filters.price_min, filters.price_max)
            for modality in ("venda", "pix", "cartao")
        ]))
    return conditions


def list_offers(
    db: Session,
    organization_id: uuid.UUID,
    filters: CatalogFilters,
    *,
    page: int = 1,
    page_size: int = 100,
) -> dict:
    page = max(page, 1)
    page_size = page_size if page_size in {24, 48, 100, 200} else 100
    conditions = filter_conditions(organization_id, filters)
    total = db.scalar(select(func.count()).select_from(Offer).where(*conditions)) or 0
    pages = max(1, math.ceil(total / page_size))
    page = min(page, pages)
    pix = latest_price("pix").label("price_pix")
    card = latest_price("cartao").label("price_card")
    sale = latest_price("venda").label("price_sale")
    statement = (
        select(
            Offer,
            Company.code.label("company_code"),
            Company.name.label("company_name"),
            Company.company_type.label("company_type"),
            Brand.canonical_name.label("brand_name"),
            Category.name.label("category_name"),
            pix,
            card,
            sale,
        )
        .join(Company, Company.id == Offer.company_id)
        .outerjoin(Brand, Brand.id == Offer.brand_id)
        .outerjoin(Category, Category.id == Offer.category_id)
        .where(*conditions)
        .order_by(*company_focus_order(), Offer.name_raw, Offer.external_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for row in db.execute(statement):
        offer = row.Offer
        items.append(
            {
                "id": offer.id,
                "company_code": row.company_code,
                "company_name": row.company_name,
                "company_type": row.company_type,
                "source_group": source_group(row.company_type),
                "external_code": offer.external_code,
                "name": offer.name_raw,
                "brand": row.brand_name or offer.brand_raw,
                "category": row.category_name or offer.category_raw,
                "availability": offer.availability_state,
                "stock_quantity": offer.stock_quantity,
                "excluded_from_analytics": offer.excluded_from_analytics,
                "prices": {"pix": row.price_pix, "cartao": row.price_card, "venda": row.price_sale},
            }
        )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
    }


def get_offer_detail(db: Session, organization_id: uuid.UUID, offer_id: uuid.UUID) -> dict | None:
    statement = (
        select(Offer, Company, Brand, Category)
        .join(Company, Company.id == Offer.company_id)
        .outerjoin(Brand, Brand.id == Offer.brand_id)
        .outerjoin(Category, Category.id == Offer.category_id)
        .where(Offer.id == offer_id, Offer.organization_id == organization_id)
    )
    row = db.execute(statement).one_or_none()
    if row is None:
        return None
    offer, company, brand, category = row
    prices = db.execute(
        select(OfferPrice.modality, OfferPrice.amount, OfferPrice.state, OfferPrice.raw_value)
        .join(OfferObservation, OfferObservation.id == OfferPrice.observation_id)
        .where(OfferObservation.offer_id == offer.id)
        .order_by(OfferObservation.imported_at.desc(), OfferPrice.modality)
    ).all()
    source = db.execute(
        select(
            CatalogImport.original_filename,
            CatalogImport.sheet_name,
            ImportRow.row_number,
            CatalogImport.file_sha256,
        )
        .join(ImportRow, ImportRow.catalog_import_id == CatalogImport.id)
        .where(ImportRow.offer_id == offer.id, ImportRow.published.is_(True))
        .order_by(CatalogImport.published_at.desc())
        .limit(1)
    ).one_or_none()
    return {
        "id": offer.id,
        "company": {
            "code": company.code,
            "name": company.name,
            "type": company.company_type,
            "source_group": source_group(company.company_type),
        },
        "external_code": offer.external_code,
        "manufacturer_code": offer.manufacturer_code,
        "reference": offer.reference,
        "name": offer.name_raw,
        "brand": brand.canonical_name if brand else offer.brand_raw,
        "category": category.name if category else offer.category_raw,
        "subcategory": offer.subcategory_raw,
        "description": offer.description_display,
        "application": offer.application_raw,
        "unit": offer.unit_raw,
        "supplier": offer.supplier_raw,
        "country": offer.country_raw,
        "availability": offer.availability_state,
        "availability_raw": offer.availability_raw,
        "stock_quantity": offer.stock_quantity,
        "source_url": offer.source_url,
        "excluded_from_analytics": offer.excluded_from_analytics,
        "exclusion_reason": offer.exclusion_reason,
        "prices": [
            {"modality": item.modality, "amount": item.amount, "state": item.state, "raw_value": item.raw_value}
            for item in prices
        ],
        "source": (
            {
                "filename": source.original_filename,
                "sheet": source.sheet_name,
                "row_number": source.row_number,
                "sha256": source.file_sha256,
            }
            if source
            else None
        ),
    }


def dashboard_summary(db: Session, organization_id: uuid.UUID) -> dict:
    base = [
        Offer.organization_id == organization_id,
        Offer.active.is_(True),
        Offer.excluded_from_analytics.is_(False),
    ]
    any_valid_price = exists().where(
        OfferObservation.offer_id == Offer.id,
        OfferPrice.observation_id == OfferObservation.id,
        OfferPrice.state == "valido",
    )
    totals = db.execute(
        select(
            func.count(Offer.id).label("offers"),
            func.count(distinct(Offer.company_id)).label("companies"),
            func.count(distinct(Offer.brand_id)).label("brands"),
            func.count(Offer.id).filter(any_valid_price).label("with_price"),
        ).where(*base)
    ).one()
    company_counts = [
        {
            "code": row.code,
            "name": row.name,
            "type": row.company_type,
            "count": row.count,
            "treated_count": row.treated_count,
            "pipeline_count": row.pipeline_count,
            "treatment_percent": round(row.treated_count * 100 / row.count, 1) if row.count else 0,
        }
        for row in db.execute(
            select(
                Company.code,
                Company.name,
                Company.company_type,
                func.count(Offer.id).label("count"),
                func.count(OfferEnrichment.id).label("treated_count"),
                func.count(OfferEnrichment.id).filter(OfferEnrichment.source == "pipeline").label("pipeline_count"),
            )
            .outerjoin(Offer, and_(Offer.company_id == Company.id, *base))
            .outerjoin(OfferEnrichment, OfferEnrichment.offer_id == Offer.id)
            .where(Company.organization_id == organization_id, Company.active.is_(True))
            .group_by(Company.id)
            .order_by(*company_focus_order())
        )
    ]
    availability = [
        {"state": row.availability_state, "count": row.count}
        for row in db.execute(
            select(Offer.availability_state, func.count().label("count"))
            .where(*base)
            .group_by(Offer.availability_state)
            .order_by(Offer.availability_state)
        )
    ]
    top_brands = [
        {"name": row.name, "count": row.count}
        for row in db.execute(
            select(Brand.canonical_name.label("name"), func.count(Offer.id).label("count"))
            .join(Offer, Offer.brand_id == Brand.id)
            .where(*base)
            .group_by(Brand.id)
            .order_by(func.count(Offer.id).desc(), Brand.canonical_name)
            .limit(10)
        )
    ]
    missing_brand = db.scalar(select(func.count()).select_from(Offer).where(*base, Offer.brand_id.is_(None))) or 0
    no_valid_price = (totals.offers or 0) - (totals.with_price or 0)
    treated_offers = sum(company["treated_count"] for company in company_counts)
    pipeline_offers = sum(company["pipeline_count"] for company in company_counts)
    return {
        "offers": totals.offers or 0,
        "companies": totals.companies or 0,
        "brands": totals.brands or 0,
        "with_price": totals.with_price or 0,
        "price_coverage": round((totals.with_price or 0) * 100 / totals.offers, 1) if totals.offers else 0,
        "missing_brand": missing_brand,
        "no_valid_price": no_valid_price,
        "treated_offers": treated_offers,
        "pipeline_offers": pipeline_offers,
        "treatment_percent": round(treated_offers * 100 / totals.offers, 1) if totals.offers else 0,
        "company_counts": company_counts,
        "availability": availability,
        "top_brands": top_brands,
    }


def filter_options(db: Session, organization_id: uuid.UUID) -> dict:
    companies = [
        {"code": row.code, "name": row.name, "type": row.company_type,
         "source_group": source_group(row.company_type)}
        for row in db.execute(
            select(Company.code, Company.name, Company.company_type)
            .where(Company.organization_id == organization_id, Company.active.is_(True))
            .order_by(*company_focus_order())
        )
    ]
    brands = list(
        db.scalars(
            select(Brand.canonical_name)
            .where(Brand.organization_id == organization_id)
            .order_by(Brand.canonical_name)
        )
    )
    family_groups = list(
        db.scalars(
            select(OfferEnrichment.family_group)
            .join(Offer, Offer.id == OfferEnrichment.offer_id)
            .where(
                Offer.organization_id == organization_id,
                Offer.active.is_(True),
                Offer.excluded_from_analytics.is_(False),
                OfferEnrichment.family_group.is_not(None),
            )
            .distinct()
            .order_by(OfferEnrichment.family_group)
        )
    )
    return {
        "companies": companies,
        "brands": brands,
        "family_groups": family_groups,
        "availability": ["em_estoque", "fora_estoque", "sob_encomenda", "nao_informado"],
        "modalities": ["pix", "cartao", "venda"],
    }


def comparison_preview(
    db: Session,
    organization_id: uuid.UUID,
    offer_ids: list[uuid.UUID],
    reference_offer_id: uuid.UUID | None = None,
) -> dict:
    unique_ids = list(dict.fromkeys(offer_ids))
    if not 2 <= len(unique_ids) <= 8:
        raise ValueError("Selecione entre 2 e 8 ofertas distintas.")
    if reference_offer_id is not None and reference_offer_id not in unique_ids:
        raise ValueError("A oferta de referência precisa fazer parte da comparação.")
    items = []
    for offer_id in unique_ids:
        detail = get_offer_detail(db, organization_id, offer_id)
        if detail is None:
            raise LookupError(f"Oferta não encontrada: {offer_id}")
        latest_prices: dict[str, Decimal | None] = {
            "venda": None,
            "pix": None,
            "cartao": None,
        }
        seen_modalities: set[str] = set()
        for price in detail["prices"]:
            if price["modality"] not in seen_modalities:
                latest_prices[price["modality"]] = (
                    price["amount"] if price["state"] == "valido" else None
                )
                seen_modalities.add(price["modality"])
        detail["latest_prices"] = latest_prices
        items.append(detail)
    items.sort(
        key=lambda item: (
            0 if item["company"]["type"] == "nossa" else 1,
            item["company"]["name"].casefold(),
            item["name"].casefold(),
        )
    )
    reference = next(
        (item for item in items if item["id"] == reference_offer_id), None
    )
    maximum_prices = {
        modality: max(
            (
                item["latest_prices"][modality]
                for item in items
                if item["latest_prices"][modality] is not None
            ),
            default=None,
        )
        for modality in ("venda", "pix", "cartao")
    }
    for item in items:
        item["is_reference"] = item["id"] == reference_offer_id
        item["price_analysis"] = {}
        for modality in ("venda", "pix", "cartao"):
            amount = item["latest_prices"][modality]
            maximum = maximum_prices[modality]
            analysis = {
                "bar_percent": (
                    (amount / maximum * Decimal("100")).quantize(Decimal("0.1"))
                    if amount is not None and maximum is not None and maximum > 0
                    else None
                ),
                "difference_percent": None,
                "status": "sem_referencia" if reference is None else "nao_informado",
            }
            if reference is not None:
                reference_amount = reference["latest_prices"][modality]
                if reference_amount is None or reference_amount <= 0:
                    analysis["status"] = "referencia_nao_informada"
                elif amount is not None:
                    difference = (
                        (amount - reference_amount) / reference_amount * Decimal("100")
                    ).quantize(Decimal("0.1"))
                    analysis["difference_percent"] = difference
                    analysis["status"] = "igual" if difference == 0 else "diferente"
            item["price_analysis"][modality] = analysis
    comparable_modalities = []
    for modality in ("venda", "pix", "cartao"):
        available = sum(item["latest_prices"].get(modality) is not None for item in items)
        if available >= 2:
            comparable_modalities.append({"modality": modality, "offers_with_price": available})
    return {
        "mode": "exploratoria",
        "equivalence_status": "nao_avaliado",
        "warning": "Comparação exploratória; não confirma equivalência ou substituição comercial.",
        "reference": (
            {
                "id": reference["id"],
                "company": reference["company"],
                "name": reference["name"],
            }
            if reference is not None
            else None
        ),
        "items": items,
        "comparable_modalities": comparable_modalities,
        "technical_matrix": _technical_matrix(db, organization_id, items),
    }


def _matrix_status(values: list[str | None], *, incompatible: bool = False) -> str:
    if incompatible:
        return "incompativel"
    if any(value is None for value in values):
        return "nao_informado"
    normalized = {value.strip().casefold() for value in values if value is not None}
    return "igual" if len(normalized) == 1 else "diferente"


def _technical_matrix(
    db: Session, organization_id: uuid.UUID, items: list[dict]
) -> list[dict]:
    basic_fields = (
        ("brand", "Marca/fabricante"),
        ("manufacturer_code", "Código do fabricante"),
        ("reference", "Referência/modelo"),
        ("category", "Categoria"),
        ("subcategory", "Subcategoria"),
        ("unit", "Unidade comercial"),
    )
    matrix = []
    for key, name in basic_fields:
        raw_values = [item.get(key) for item in items]
        matrix.append(
            {
                "key": key,
                "name": name,
                "unit": None,
                "origin": "catalogo",
                "status": _matrix_status(raw_values),
                "values": [
                    {
                        "offer_id": item["id"],
                        "value": item.get(key),
                        "review_status": None,
                        "method": "importado",
                    }
                    for item in items
                ],
            }
        )

    attribute_rows = db.execute(
        select(AttributeDefinition, OfferAttribute)
        .join(OfferAttribute, OfferAttribute.definition_id == AttributeDefinition.id)
        .where(
            AttributeDefinition.organization_id == organization_id,
            AttributeDefinition.active.is_(True),
            AttributeDefinition.comparable.is_(True),
            OfferAttribute.offer_id.in_([item["id"] for item in items]),
            OfferAttribute.review_status != "rejeitado",
        )
        .order_by(AttributeDefinition.name)
    ).all()
    by_definition: dict[uuid.UUID, dict] = {}
    for definition, attribute in attribute_rows:
        entry = by_definition.setdefault(
            definition.id,
            {"definition": definition, "attributes": {}},
        )
        entry["attributes"][attribute.offer_id] = attribute

    for entry in by_definition.values():
        definition = entry["definition"]
        cells = []
        comparison_values = []
        units = set()
        for item in items:
            attribute = entry["attributes"].get(item["id"])
            value = None
            if attribute is not None:
                if definition.data_type == "numero" and attribute.value_numeric is not None:
                    value = str(attribute.value_numeric.normalize())
                elif definition.data_type == "booleano" and attribute.value_boolean is not None:
                    value = "Sim" if attribute.value_boolean else "Não"
                else:
                    value = attribute.value_text
                unit = attribute.unit or definition.canonical_unit
                if value is not None and unit:
                    units.add(unit.strip().casefold())
                    value = f"{value} {unit}"
            comparison_values.append(value)
            cells.append(
                {
                    "offer_id": item["id"],
                    "value": value,
                    "review_status": attribute.review_status if attribute else None,
                    "method": attribute.method if attribute else None,
                }
            )
        matrix.append(
            {
                "key": definition.key,
                "name": definition.name,
                "unit": definition.canonical_unit,
                "origin": "atributo_normalizado",
                "status": _matrix_status(
                    comparison_values,
                    incompatible=definition.data_type == "numero" and len(units) > 1,
                ),
                "values": cells,
            }
        )
    enrichments = {
        item.offer_id: item
        for item in db.scalars(
            select(OfferEnrichment).where(OfferEnrichment.offer_id.in_([offer["id"] for offer in items]))
        )
    }
    for key, name in (
        ("family", "Família tratada"),
        ("family_group", "Grupo tratado"),
        ("model_reference", "Modelo tratado"),
    ):
        values = [getattr(enrichments.get(item["id"]), key, None) for item in items]
        if any(value is not None for value in values):
            matrix.append({
                "key": key, "name": name, "unit": None, "origin": "enriquecimento",
                "status": _matrix_status(values),
                "values": [
                    {"offer_id": item["id"], "value": value, "review_status": None,
                     "method": enrichments[item["id"]].source if item["id"] in enrichments else None}
                    for item, value in zip(items, values)
                ],
            })
    defined_keys = {entry["definition"].key for entry in by_definition.values()}
    enrichment_keys = sorted({key for enrichment in enrichments.values()
                              for key in (enrichment.attributes or {})} - defined_keys)
    for key in enrichment_keys:
        values = [(enrichments.get(item["id"]).attributes or {}).get(key)
                  if item["id"] in enrichments else None for item in items]
        matrix.append({
            "key": key, "name": key.replace("_", " ").capitalize(), "unit": None,
            "origin": "enriquecimento", "status": _matrix_status(values),
            "values": [
                {"offer_id": item["id"], "value": str(value) if value is not None else None,
                 "review_status": None,
                 "method": enrichments[item["id"]].source if item["id"] in enrichments else None}
                for item, value in zip(items, values)
            ],
        })
    return matrix
