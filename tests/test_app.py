from fastapi.testclient import TestClient

from app.main import app
from app.db import DatabaseNotConfigured
from app.routers import health
from app.routers.pages import templates


client = TestClient(app)


def test_liveness_does_not_require_database() -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_missing_database_configuration(monkeypatch) -> None:
    def missing_engine():
        raise DatabaseNotConfigured("Banco não configurado.")

    monkeypatch.setattr(health, "get_engine", missing_engine)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "not_configured"}


def test_login_page_is_accessible_and_localized() -> None:
    response = client.get("/login")
    assert response.status_code == 200
    assert "Acesse o painel" in response.text
    assert "lang=\"pt-BR\"" in response.text
    assert "login-brand-lockup" in response.text
    assert "/css/design-system.css" in response.text


def test_visual_assets_are_served() -> None:
    for path, expected_type in (
        ("/static/css/design-system.css", "text/css"),
        ("/static/js/ui.js", "javascript"),
        ("/static/brand-lockup.png", "image/png"),
        ("/static/favicon.svg", "image/svg+xml"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert expected_type in response.headers["content-type"]
        assert response.content


def test_unknown_page_is_not_silently_accepted() -> None:
    response = client.get("/pagina-inexistente")
    assert response.status_code == 404


def test_templates_compile() -> None:
    assert templates.get_template("shell.html") is not None


def test_company_logos_use_individual_crops_of_original_asset() -> None:
    html = templates.get_template("digitalizacao.html").render()
    for company, crop in (
        ("portwell", "54 355 550 178"),
        ("choice", "657 355 532 178"),
        ("sag", "1256 355 370 178"),
    ):
        assert f'class="company-card-logo logo-{company}"' in html
        assert f'viewBox="{crop}"' in html
    assert html.count('href="/static/brand-lockup.png"') == 3
    assert html.count('preserveAspectRatio="xMidYMid slice"') == 3


def test_login_lockup_uses_cropped_original_asset() -> None:
    response = client.get("/login")
    assert 'viewBox="48 348 1576 190"' in response.text
    assert 'href="/static/brand-lockup.png"' in response.text
