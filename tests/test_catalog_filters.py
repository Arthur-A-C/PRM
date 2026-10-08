import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import Offer
from app.repositories.catalog import CatalogFilters, filter_conditions


def test_search_uses_all_terms_and_escapes_like_wildcards() -> None:
    filters = CatalogFilters(search="sensor 100%", family_group="Sensores")
    conditions = filter_conditions(uuid.uuid4(), filters)
    statement = select(Offer.id).where(*conditions)
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert len(conditions) == 6  # organização, ativa, exclusão, família, dois termos
    assert "offer_enrichments.family_group = 'Sensores'" in sql
    assert "sensor" in sql
    assert r"100\\%" in sql
    assert "offer_enrichments.normalized_title" in sql


def test_all_modalities_price_range_keeps_bounds_on_same_price() -> None:
    filters = CatalogFilters(price_min=Decimal("100"), price_max=Decimal("500"))
    conditions = filter_conditions(uuid.uuid4(), filters)
    statement = select(Offer.id).where(*conditions)
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert len(conditions) == 4
    for modality in ("venda", "pix", "cartao"):
        assert sql.count(f"offer_prices.modality = '{modality}'") == 1
    assert sql.count(" BETWEEN 100 AND 500") == 3
