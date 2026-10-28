from types import SimpleNamespace

import pytest

from app.routers.pages import templates
from app.services.current_analysis import summarize_current


def manifest():
    counts = {s: {"received": 10, "accepted": 10, "public_catalog": 10, "with_attributes": 5,
                  "unknown_family": 2, "conflicting_attributes": 1} for s in ["portwell", "choice", "eco", "dimensional"]}
    return {"run_id": "f" * 24, "created_at": "2026-10-09", "counts": counts, "matching_status": "not_assessed",
            "rule_version": "test", "elapsed_seconds": 1, "ai_calls": 0, "inputs": [], "families": {
                "shared": {"label": "Compartilhada", "proximity": "core", "counts": {"eco": 4, "dimensional": 6}, "public_counts": {"choice": 1}},
                "absent": {"label": "Não localizada", "proximity": "adjacent", "counts": {"eco": 4, "dimensional": 2}, "public_counts": {"portwell": 0}},
                "unknown": {"label": "Pendente", "proximity": "undecided", "counts": {"eco": 2, "dimensional": 2}, "public_counts": {"choice": 9}},
            }}


def test_current_family_comparison_keeps_pending_in_denominator():
    summary = summarize_current(manifest())
    assert summary["run_id"] == "f" * 24 and summary["accepted"] == 40
    assert summary["competitors"][0]["shared_percent"] == 40.0
    assert summary["competitors"][0]["family_pending"] == 2
    assert summary["competitors"][1]["shared_percent"] == 60.0
    assert summary["strict_coverage_percent"] is None
    assert [s["code"] for s in summary["sources"]] == ["portwell", "choice", "eco", "dimensional"]


def test_no_snapshot_does_not_fall_back_and_bad_totals_are_rejected():
    assert summarize_current(None)["status"] == "no_current_snapshot"
    source = manifest()
    source["families"]["shared"]["counts"]["eco"] = 99
    with pytest.raises(ValueError, match="reconciliada"):
        summarize_current(source)


def test_dashboard_api_returns_only_published_snapshot(monkeypatch):
    from app.routers import catalog
    auth = SimpleNamespace(user=SimpleNamespace(organization_id="org-atual"))
    db = SimpleNamespace(get_bind=lambda: object())
    monkeypatch.setattr(catalog, "inspect", lambda bind: SimpleNamespace(has_table=lambda name: True))
    seen = []
    def current(db, organization):
        seen.append(organization)
        return manifest()
    monkeypatch.setattr(catalog, "database_manifest", current)
    result = catalog.summary(auth, db)
    assert seen == ["org-atual"] and result["schema_version"] == 2
    assert result["run_id"] == "f" * 24 and "offers" not in result


@pytest.mark.parametrize("title", ["Dashboard", "Comparador", "Importações e qualidade"])
def test_analysis_pages_render_only_current_data_even_with_stale_context(title):
    current = manifest()
    html = templates.get_template("shell.html").render(
        title=title, user=SimpleNamespace(name="Teste", role="gestor"), nav_items=[],
        active_path="/", csrf_token="", refined_analysis=current, current_analysis=summarize_current(current),
        summary={"offers": 999999}, comparable={"stale": "OBSOLETO"},
        matching={"summary": {"total": 888888}, "run": {"algorithm_version": "lexical-v1.3"}},
        dimensional_staging={"audit": "AUDITORIA ANTIGA"}, pipeline_audit={"audit": "AUDITORIA ANTIGA"},
        url_for=lambda *args, **kwargs: "/static/test",
    )
    assert "Dados atuais do e-commerce" in html and "Família" in html
    assert "999.999" not in html and "888888" not in html
    assert "lexical-v1.3" not in html and "AUDITORIA ANTIGA" not in html
    assert "Histórico operacional abaixo" not in html
