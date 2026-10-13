"""Migra/ingere staging antes da promoção explícita para prm_mvp."""

import argparse
import json

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.models import Organization
from app.services.refined_catalog_database import persist_run, publish_database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=["staging", "production"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not args.commit:
        parser.error("Escrita exige --commit explícito")
    if args.target == "production" and not args.publish:
        parser.error("Promoção de produção exige --publish explícito")
    settings = get_settings()
    url = make_url(settings.database_url)
    if url.database != "prm_mvp":
        raise ValueError("A URL configurada deve apontar para prm_mvp")
    if args.target == "production":
        # Gate: lote precisa ter sido carregado/reconciliado no staging separado.
        staging = create_engine(url.set(database="prm_pipeline_staging"))
        from app.models import RefinedCatalogRun
        with staging.connect() as conn:
            staged = conn.execute(select(RefinedCatalogRun.manifest).where(RefinedCatalogRun.id == args.run_id)).scalar_one_or_none()
            if not staged:
                raise ValueError("Execute/reconcilie staging antes de promover")
        staging.dispose()
    engine = create_engine(url.set(database="prm_pipeline_staging" if args.target == "staging" else "prm_mvp"))
    with engine.begin() as conn:
        cfg = Config("alembic.ini")
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "20261009_0008")
    with engine.connect() as conn:
        organization_id = conn.execute(select(Organization.id).where(Organization.name == settings.organization_name)).scalar_one()
    result = persist_run(engine, organization_id, args.run_id)
    if args.publish:
        publish_database(engine, organization_id, args.run_id)
    with engine.connect() as conn:
        legacy = conn.scalar(text("SELECT count(*) FROM offers"))
    engine.dispose()
    print(json.dumps({"target": args.target, "run_id": args.run_id, "published": args.publish,
                      "legacy_offers_preserved": legacy, **result}))


if __name__ == "__main__":
    main()
