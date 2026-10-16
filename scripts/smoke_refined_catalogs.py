"""Valida o snapshot SQL e renderiza páginas sem criar usuário/sessão."""

import argparse
import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.main import app
from app.db import get_db_session
from app.dependencies import get_current_auth
from app.models import Organization, RefinedCatalogRun
from app.services.refined_catalog_database import _verify_counts, database_manifest, list_refined_items
from app.services.current_analysis import summarize_current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["staging", "production"], required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    settings = get_settings()
    url = make_url(settings.database_url)
    engine = create_engine(url.set(database="prm_pipeline_staging" if args.target == "staging" else "prm_mvp"))
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        organization = conn.execute(select(Organization.id).where(Organization.name == settings.organization_name)).scalar_one()
        manifest = conn.execute(select(RefinedCatalogRun.manifest).where(RefinedCatalogRun.id == args.run_id)).scalar_one()
        _verify_counts(conn, args.run_id, 89693, 89693)
        attribute_count = conn.scalar(text("SELECT sum(jsonb_array_length(payload->'attribute_observations')) FROM refined_catalog_items WHERE run_id=:run"), {"run": args.run_id})
        assert attribute_count == sum(c["attributes"] for c in manifest["counts"].values())
        if manifest['rule_version'] in {'refined-base-v2', 'refined-base-v3'}:
            aliases = conn.scalars(text("""SELECT a FROM refined_catalog_items i
                CROSS JOIN LATERAL jsonb_array_elements(i.payload->'attribute_observations') a
                WHERE i.run_id=:run AND i.source_id='eco'
                AND a->>'raw_name' IN ('ATR_USB','ATR_COM')"""), {'run': args.run_id}).all()
            assert len(aliases) == 19
            for attr in aliases:
                expected = ('ports.usb', 'Portas USB') if attr['raw_name'] == 'ATR_USB' else ('ports.serial', 'Portas Seriais COM')
                assert (attr['attribute_code'], attr['canonical_label']) == expected
                assert attr['raw_value'] and attr['evidence']
        if manifest.get('attribute_analysis'):
            from app.services.catalog_attribute_analysis import AttributeAnalysis
            audit = AttributeAnalysis()
            records = conn.scalars(text("""SELECT payload FROM refined_catalog_items i WHERE run_id=:run
                AND EXISTS (SELECT 1 FROM jsonb_array_elements(i.payload->'attribute_observations') a
                            WHERE a->>'attribute_code'='compute.os')"""), {'run': args.run_id})
            for item in records:
                audit.observe(item, item['attribute_observations'])
            for source, counts in manifest['counts'].items():
                audit.counts[source]['total'] = counts['accepted']
            assert audit.summary()['competitors'] == manifest['attribute_analysis']['competitors']
            for report in manifest['attribute_analysis']['competitors']:
                assert sum(report[k] for k in ['equivalent', 'different', 'inconclusive', 'missing_os']) == report['total']
        for source in ["portwell", "choice", "eco", "dimensional"]:
            actual = conn.scalar(text("SELECT count(*) FROM refined_catalog_items WHERE run_id=:run AND source_id=:source"), {"run": args.run_id, "source": source})
            assert actual == manifest["counts"][source]["accepted"]
        assert database_manifest(conn, organization)["run_id"] == args.run_id
        catalog = list_refined_items(conn, organization)
        assert catalog["total"] == 89651 and len(catalog["items"]) == 100
        assert {item["source_id"] for item in catalog["items"]} == {"portwell"}
        assert list_refined_items(conn, organization, source="choice")["total"] == 2750
        assert list_refined_items(conn, organization, source="portwell", internal=True)["total"] == 1033
        assert list_refined_items(conn, organization, source="dimensional", search="xyznevermatch123")["total"] == 0
        for competitor in summarize_current(manifest)["competitors"]:
            for group, key in [("shared", "shared_family"), ("not_found", "family_not_found"), ("review", "family_pending")]:
                listed = list_refined_items(conn, organization, source=competitor["source"], group=group)
                assert listed["total"] == competitor[key]
        reference = list_refined_items(conn, organization, source="eco", group="shared")["items"][0]
        candidate = list_refined_items(conn, organization, source="own", family=reference["classification"]["family_id"])["items"][0]
        reference_url = f"/catalogos?source=own&family={reference['classification']['family_id']}&reference={reference['item_id']}&run_id={args.run_id}"
        comparison_url = f"/comparacao-atual?run_id={args.run_id}&item={reference['item_id']}&item={candidate['item_id']}"
        import uuid
        assert database_manifest(conn, uuid.uuid4()) is None
        legacy = conn.execute(text("SELECT c.code,count(o.id) FROM companies c LEFT JOIN offers o ON o.company_id=c.id GROUP BY c.code ORDER BY c.code")).all()
    # Authentication is replaced only in this local diagnostic process. No
    # server auth bypass, credentials, cookies or writes are persisted.
    auth = SimpleNamespace(user=SimpleNamespace(name="Smoke local", role="gestor", organization_id=organization))
    with patch("app.routers.pages.get_engine", return_value=engine), patch("app.routers.pages.find_auth_context", return_value=auth):
        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, "local-diagnostic-not-a-real-token")
            for path in ["/", "/catalogos", "/catalogos?source=choice", "/catalogos?source=dimensional&page=2", "/catalogos?view=legacy", "/comparador", "/importacoes", "/catalogos?source=eco&group=shared", "/catalogos?source=eco&group=not_found", "/catalogos?source=dimensional&group=review", "/catalogos?group=quality_review", reference_url, comparison_url]:
                response = client.get(path)
                assert response.status_code == 200, (path, response.status_code)
                if "view=legacy" not in path and not path.startswith("/comparacao-atual"):
                    assert "Nova base" in response.text or "Nova base de referência" in response.text
                if path in ["/", "/comparador", "/importacoes"]:
                    assert "Dados atuais do e-commerce" in response.text
                    assert "lexical-v1.3" not in response.text
                    assert "Histórico operacional abaixo" not in response.text
                    assert "Banco de staging:" not in response.text
                print(f"HTTP 200 {path}")
            assert client.get(f"/comparacao-atual?item={reference['item_id']}").status_code == 422
            assert client.get(comparison_url.replace(args.run_id, "outdated")).status_code == 422
            assert client.get(f"/comparacao-atual?item={reference['item_id']}&item=00000000-0000-0000-0000-000000000000").status_code == 404
    previous_overrides = app.dependency_overrides.copy()
    def diagnostic_db():
        with Session(engine) as db:
            yield db
    try:
        app.dependency_overrides[get_current_auth] = lambda: auth
        app.dependency_overrides[get_db_session] = diagnostic_db
        with TestClient(app) as client:
            response = client.get("/api/v1/dashboard/summary")
            assert response.status_code == 200
            payload = response.json()
            assert payload["schema_version"] == 2 and payload["run_id"] == args.run_id
            assert payload["accepted"] == 89693 and payload["own_public"] == 3741
            assert payload["strict_coverage_percent"] is None
            assert payload.get('attribute_analysis') == manifest.get('attribute_analysis')
            print("HTTP 200 /api/v1/dashboard/summary (snapshot atual)")
            print(json.dumps({"current_family_comparison": payload["competitors"]}))
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
    engine.dispose()
    print(json.dumps({"target": args.target, "run_id": args.run_id, "items": 89693, "attributes": attribute_count, "legacy_company_counts": dict(legacy), "tenant_isolation": True}))


if __name__ == "__main__":
    main()
