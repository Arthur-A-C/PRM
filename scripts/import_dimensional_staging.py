"""Atomic, idempotent import of the audited Dimensional CSV into staging only."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, insert, select
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.models import CatalogImport, Company, ImportRow, Offer, OfferObservation, OfferPrice, Organization
from app.services.dimensional_csv import DimensionalCsvAdapter, sha256_file


EXPECTED_SHA256 = "8ad7e0e63e265aa6ebfd34b06a530dc000177c11602c2a6920e80add3e211528"
EXPECTED_RECORDS = 77_965
STAGING_DATABASE = "prm_pipeline_staging"


def staging_url():
    url = make_url(get_settings().database_url)
    if url.database != "prm_mvp":
        raise ValueError("Configured database must be prm_mvp; never import to another target.")
    return url.set(database=STAGING_DATABASE)


def build_record_values(source, mapped, company_id, organization_id, import_id):
    raw = source.raw
    if len(mapped.external_code) > 255:
        raise ValueError(f"SKU too long at record {source.number}")
    fingerprint = hashlib.sha256(
        json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    offer_id = uuid.uuid4()
    observation_id = uuid.uuid4()
    offer = {
        "id": offer_id, "organization_id": organization_id, "company_id": company_id,
        "external_code": mapped.external_code, "manufacturer_code": None,
        "reference": raw["referencia"][:500] or None,
        "name_raw": raw["nome"] or mapped.external_code,
        "description_raw": raw["descricao_completa"] or None,
        "description_display": raw["descricao_curta"] or None,
        "application_raw": None, "brand_raw": raw["marca"][:500] or None,
        "category_raw": raw["categoria"][:500] or None, "subcategory_raw": None,
        "source_url": raw["url"] or None, "unit_raw": None,
        "supplier_raw": None, "country_raw": None,
        "availability_raw": raw["disponibilidade"][:500] or None,
        "availability_state": "nao_informado", "stock_quantity": None,
        "source_fingerprint": fingerprint, "active": True,
        "excluded_from_analytics": False, "exclusion_reason": None,
    }
    line = {
        "id": uuid.uuid4(), "catalog_import_id": import_id, "offer_id": offer_id,
        "sheet_name": "CSV", "row_number": source.number,
        "raw_row": {**raw, "_physical_line_start": source.first_physical_line,
                    "_physical_line_end": source.last_physical_line},
        "warnings": list(mapped.warnings), "errors": [], "published": True,
    }
    observation = {
        "id": observation_id, "offer_id": offer_id, "catalog_import_id": import_id,
        "source_fingerprint": fingerprint,
        "availability_raw": raw["disponibilidade"][:500] or None,
        "availability_state": "nao_informado", "stock_quantity": None,
        "currency": "XXX", "observed_at": None,
    }
    prices = []
    for modality, value, amount in (
        ("anunciado", raw["preco"], mapped.price),
        ("referencia_anunciada", raw["preco_de"], mapped.reference_price),
    ):
        prices.append({
            "id": uuid.uuid4(), "observation_id": observation_id,
            "modality": modality, "amount": amount,
            "raw_value": value or None,
            "state": "valido" if amount is not None else "nao_informado",
        })
    return offer, line, observation, prices


def import_staging(path: Path, *, expected_sha256: str = EXPECTED_SHA256) -> dict:
    path = path.resolve()
    if path.parent != Path("data/imports").resolve():
        raise ValueError("CSV must be directly under data/imports.")
    digest = sha256_file(path)
    if digest != expected_sha256:
        raise ValueError("Source SHA-256 differs from the audited lot.")
    adapter = DimensionalCsvAdapter()
    engine = create_engine(staging_url(), pool_pre_ping=True)
    import_id = uuid.uuid4()
    counts = {"offers": 0, "warnings": 0, "announced_prices": 0}
    seen: set[str] = set()
    with engine.begin() as connection:
        organization_id = connection.execute(
            select(Organization.id).where(Organization.name == get_settings().organization_name)
        ).scalar_one()
        company = connection.execute(
            select(Company.id).where(
                Company.organization_id == organization_id, Company.code == "dimensional"
            )
        ).scalar_one_or_none()
        if company is not None:
            existing = connection.execute(
                select(CatalogImport.id, CatalogImport.file_sha256).where(
                    CatalogImport.company_id == company
                )
            ).all()
            if any(row.file_sha256 == digest for row in existing):
                return {"idempotent": True, "offers": connection.execute(
                    select(CatalogImport.inserted_count).where(
                        CatalogImport.company_id == company, CatalogImport.file_sha256 == digest
                    )
                ).scalar_one()}
            if existing:
                raise ValueError("Another Dimensional revision exists; use a reviewed update workflow.")
            raise ValueError("Dimensional company already exists without this lot; manual review required.")
        company = uuid.uuid4()
        connection.execute(insert(Company), [{
            "id": company, "organization_id": organization_id, "code": "dimensional",
            "name": "Dimensional", "domain": None,
            "company_type": "concorrente", "active": True,
        }])
        connection.execute(insert(CatalogImport), [{
            "id": import_id, "organization_id": organization_id, "company_id": company,
            "created_by_id": None, "original_filename": path.name,
            "source_path": path.as_posix(), "file_sha256": digest,
            "file_size": path.stat().st_size, "sheet_name": "CSV",
            "header_row": 1, "mapping": {
                "source_id": adapter.source_id, "adapter_version": adapter.version,
                "identity": "company+source+sku", "currency_status": "unknown",
                "price_modalities": ["anunciado", "referencia_anunciada"],
                "stock_status": "untrusted", "technical_review": "pending",
            },
            "currency": "XXX", "observed_at": None, "status": "processing",
            "total_rows": 0, "inserted_count": 0, "updated_count": 0,
            "unchanged_count": 0, "warning_count": 0, "rejected_count": 0,
        }])
        batch = {"offers": [], "lines": [], "observations": [], "prices": []}

        def flush() -> None:
            if not batch["offers"]:
                return
            connection.execute(insert(Offer), batch["offers"])
            connection.execute(insert(ImportRow), batch["lines"])
            connection.execute(insert(OfferObservation), batch["observations"])
            connection.execute(insert(OfferPrice), batch["prices"])
            for values in batch.values():
                values.clear()

        for source in adapter.iter_source_records(path):
            mapped = adapter.map_record(source)
            if mapped.external_code in seen:
                raise ValueError(f"Duplicate SKU {mapped.external_code}; transaction rolled back.")
            seen.add(mapped.external_code)
            offer, line, observation, prices = build_record_values(
                source, mapped, company, organization_id, import_id
            )
            batch["offers"].append(offer)
            batch["lines"].append(line)
            batch["observations"].append(observation)
            batch["prices"].extend(prices)
            counts["offers"] += 1
            counts["warnings"] += bool(mapped.warnings)
            counts["announced_prices"] += mapped.price is not None
            if len(batch["offers"]) >= 500:
                flush()
                if counts["offers"] % 10_000 == 0:
                    print(f"staging rows prepared: {counts['offers']}", flush=True)
        flush()
        if counts["offers"] != EXPECTED_RECORDS:
            raise ValueError(f"Expected {EXPECTED_RECORDS} records, got {counts['offers']}; rolled back.")
        connection.execute(
            CatalogImport.__table__.update().where(CatalogImport.id == import_id).values(
                status="published", total_rows=counts["offers"],
                inserted_count=counts["offers"], warning_count=counts["warnings"],
                published_at=datetime.now(timezone.utc),
            )
        )
    engine.dispose()
    return {"idempotent": False, "import_id": str(import_id), "sha256": digest, **counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("data/imports/produtos_dimensional.csv"))
    parser.add_argument("--commit", action="store_true", help="Write only to prm_pipeline_staging.")
    args = parser.parse_args()
    if not args.commit:
        print(f"Target={STAGING_DATABASE}; source={args.csv}; use --commit to import.")
        return
    print(json.dumps(import_staging(args.csv), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
