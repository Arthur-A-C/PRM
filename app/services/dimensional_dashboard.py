"""Resumo Dimensional de staging para gestores; nunca substitui dados publicados."""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CatalogImport, Company, ImportRow, Offer, OfferObservation, OfferPrice


STAGING_DIR = Path("data/analysis/staging")


def _read_report(path: Path, expected_mode: str) -> dict | None:
    try:
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            return None
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(report, dict) or report.get("mode") != expected_mode:
        return None
    return report


def load_dimensional_staging(directory: Path = STAGING_DIR) -> dict | None:
    audit = _read_report(directory / "dimensional_audit.json", "read_only_staging")
    simulation = _read_report(directory / "dimensional_simulation.json", "dry_run_staging")
    if not audit or not simulation:
        return None
    if audit.get("sha256") != simulation.get("source_sha256"):
        return None
    if audit.get("metrics", {}).get("records") != simulation.get("metrics", {}).get("records"):
        return None
    return {"audit": audit, "simulation": simulation}


@lru_cache
def _staging_engine():
    url = make_url(get_settings().database_url)
    if url.database != "prm_mvp":
        raise ValueError("The configured production database must be prm_mvp.")
    return create_engine(url.set(database="prm_pipeline_staging"), pool_pre_ping=True)


def load_dimensional_database_status(organization_id: uuid.UUID) -> dict:
    """Read the isolated staging DB; never infer publication in production."""
    unavailable = {"available": False, "offers": 0, "rows": 0, "observations": 0,
                   "prices": 0, "source_sha256": None, "import_status": None}
    try:
        with Session(_staging_engine()) as db:
            company_id = db.scalar(
                select(Company.id).where(
                    Company.organization_id == organization_id,
                    Company.code == "dimensional",
                )
            )
            if company_id is None:
                return {**unavailable, "available": True}
            batch = db.scalar(
                select(CatalogImport).where(
                    CatalogImport.company_id == company_id
                ).order_by(CatalogImport.published_at.desc()).limit(1)
            )
            if batch is None:
                return {**unavailable, "available": True}
            return {
                "available": True,
                "offers": db.scalar(select(func.count()).select_from(Offer).where(Offer.company_id == company_id)),
                "rows": db.scalar(select(func.count()).select_from(ImportRow).where(ImportRow.catalog_import_id == batch.id)),
                "observations": db.scalar(select(func.count()).select_from(OfferObservation).where(OfferObservation.catalog_import_id == batch.id)),
                "prices": db.scalar(
                    select(func.count()).select_from(OfferPrice)
                    .join(OfferObservation, OfferObservation.id == OfferPrice.observation_id)
                    .where(OfferObservation.catalog_import_id == batch.id)
                ),
                "source_sha256": batch.file_sha256,
                "import_status": batch.status,
            }
    except (SQLAlchemyError, OSError, ValueError):
        return unavailable
