"""A visualização de staging é separada do catálogo publicado."""

from jinja2 import Environment, FileSystemLoader

from app.services.dimensional_dashboard import load_dimensional_staging
from app.services.pipeline_staging import load_staging_audit


def render(role: str, dimensional: dict | None):
    environment = Environment(loader=FileSystemLoader("app/templates"), autoescape=True)
    return environment.get_template("shell.html").render(
        title="Importações e qualidade", user={"name": "Teste", "role": role},
        nav_items=[], active_path="/importacoes", csrf_token="",
        pipeline_audit=load_staging_audit() if role == "gestor" else None,
        dimensional_staging=dimensional,
        url_for=lambda *args, **kwargs: "/static/css/app.css",
    )


def test_staging_panel_is_labeled_and_not_shown_as_published():
    report = load_dimensional_staging()
    assert report is not None
    assert report["audit"]["metrics"]["records"] == 77_965
    assert report["simulation"]["published_offers"] == 0
    manager_html = render("gestor", report)
    assert "Dimensional — auditoria do CSV" in manager_html
    assert "77.965" in manager_html
    assert "ainda não integra o catálogo publicado" in manager_html
    seller_html = render("vendedor", None)
    assert "Dimensional — auditoria do CSV" not in seller_html


def test_overview_separates_audited_source_from_live_database():
    report = load_dimensional_staging()
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
    assert "Situação atual do novo catálogo" in html
    assert "77.965" in html
    assert "Ofertas Dimensional no banco oficial: 0" in html
    assert "Banco de staging: 77.965 ofertas" in html
    assert "Lote reconciliado com a auditoria" in html
    assert "não representam cobertura do nosso portfólio" in html
