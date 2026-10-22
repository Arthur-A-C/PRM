"""A visualização de staging é separada do catálogo publicado."""

from jinja2 import Environment, FileSystemLoader
import json
import pytest

from app.services.dimensional_dashboard import load_dimensional_staging
from app.services.pipeline_staging import load_staging_audit


@pytest.fixture
def staging_report(tmp_path):
    """Synthetic audit: UI regression must not depend on private data/analysis."""
    (tmp_path / "dimensional_audit.json").write_text(json.dumps({
        "mode": "read_only_staging", "sha256": "synthetic", "metrics": {"records": 77965},
    }), encoding="utf-8")
    (tmp_path / "dimensional_simulation.json").write_text(json.dumps({
        "mode": "dry_run_staging", "source_sha256": "synthetic",
        "metrics": {"records": 77965}, "published_offers": 0,
    }), encoding="utf-8")
    return load_dimensional_staging(tmp_path)


def render(role: str, dimensional: dict | None):
    environment = Environment(loader=FileSystemLoader("app/templates"), autoescape=True)
    return environment.get_template("shell.html").render(
        title="Importações e qualidade", user={"name": "Teste", "role": role},
        nav_items=[], active_path="/importacoes", csrf_token="",
        pipeline_audit=load_staging_audit() if role == "gestor" else None,
        dimensional_staging=dimensional,
        url_for=lambda *args, **kwargs: "/static/css/app.css",
    )


def test_staging_panel_is_labeled_and_not_shown_as_published(staging_report):
    report = staging_report
    assert report is not None
    assert report["audit"]["metrics"]["records"] == 77_965
    assert report["simulation"]["published_offers"] == 0
    manager_html = render("gestor", report)
    assert "Base atual indisponível" in manager_html
    assert "Dimensional — auditoria do CSV" not in manager_html
    assert "ainda não integra o catálogo publicado" not in manager_html
    seller_html = render("vendedor", None)
    assert "Dimensional — auditoria do CSV" not in seller_html


def test_overview_separates_audited_source_from_live_database(staging_report):
    report = staging_report
    assert report is not None
    environment = Environment(loader=FileSystemLoader("app/templates"), autoescape=True)
    html = environment.get_template("shell.html").render(
        title="Visão geral",
        user={"name": "Teste", "role": "gestor"},
        nav_items=[],
        active_path="/",
        csrf_token="",
        summary={
            "offers": 35_785, "companies": 3, "brands": 419,
            "price_coverage": 92.0, "treatment_percent": 100.0,
            "pipeline_offers": 35_785, "company_counts": [],
            "missing_brand": 168, "no_valid_price": 2859,
            "availability": [], "top_brands": [],
        },
        dimensional_staging=report,
        dimensional_published_count=0,
        dimensional_database={
            "available": True, "offers": 77_965, "rows": 77_965,
            "observations": 77_965, "prices": 155_930,
            "source_sha256": report["audit"]["sha256"],
        },
        matching={"summary": None, "selected_company": None},
        comparable=None,
        url_for=lambda *args, **kwargs: "/static/css/app.css",
    )
    assert "Base atual indisponível" in html
    assert "Situação atual do novo catálogo" not in html
    assert "35.785" not in html
    assert "Ofertas Dimensional no banco oficial: 0" not in html
    assert "Banco de staging" not in html
