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
    assert "brand-trio-login" in response.text
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


def test_company_selectors_use_individual_transparent_logos() -> None:
    html = templates.get_template("digitalizacao.html").render()
    for company in ("portwell", "choice", "sag"):
        assert f'class="brand-logo brand-logo-{company} company-logo"' in html
        assert f'src="/static/brand/{company}.png?v=' in html
    assert "brand-lockup.png" not in html


def test_brand_logo_files_have_real_transparency() -> None:
    from PIL import Image
    for company in ("portwell", "choice", "sag"):
        response = client.get(f"/static/brand/{company}.png")
        assert response.status_code == 200 and "image/png" in response.headers["content-type"]
        image = Image.open(__import__("io").BytesIO(response.content))
        assert image.mode == "RGBA"
        alpha = image.getchannel("A")
        assert alpha.getpixel((0, 0)) == 0 and alpha.getextrema() == (0, 255)
        assert image.convert("RGB").getextrema() == ((0, 0), (0, 0), (0, 0))  # tinta preta; o tema define a cor
    assert ".brand-logo-portwell" in client.get("/static/brand/brand.css").text


def test_login_uses_three_individual_logos() -> None:
    response = client.get("/login")
    assert 'aria-label="Portwell, Choice e SAG"' in response.text
    for company in ("portwell", "choice", "sag"):
        assert f"/static/brand/{company}.png" in response.text
    assert "brand-lockup.png" not in response.text


def test_dark_theme_layer_is_loaded_after_light_design() -> None:
    response = client.get("/login")
    assert response.status_code == 200
    html = response.text
    assert html.index("localStorage.getItem('prm-theme')") < html.index("/css/app.css")
    assert html.index("/css/app.css") < html.index("/css/prm-v2.css") < html.index("/css/prm-dark.css")
    stylesheet = client.get("/static/css/prm-dark.css")
    assert stylesheet.status_code == 200
    assert ":root[data-theme=\"dark\"]" in stylesheet.text
    assert "--prm-input: #111923" in stylesheet.text
