import secrets
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.main import app
from app.models import LoginSession, Organization, User
from app.services.auth import create_login_session
from app.services.security import hash_password


def main() -> None:
    settings = get_settings()
    user_id = uuid.uuid4()
    raw_token = raw_csrf = None
    try:
        with Session(get_engine()) as db, db.begin():
            organization = db.scalar(select(Organization))
            if organization is None:
                raise RuntimeError("Organização não cadastrada.")
            user = User(
                id=user_id,
                organization_id=organization.id,
                name="Teste temporário",
                email=f"smoke-{user_id}@localhost.invalid",
                password_hash=hash_password(secrets.token_urlsafe(24)),
                role="gestor",
                active=True,
            )
            db.add(user)
            created = create_login_session(db, user, settings)
            raw_token, raw_csrf = created.raw_token, created.raw_csrf

        client = TestClient(app)
        client.cookies.set(settings.session_cookie_name, raw_token)
        client.cookies.set(settings.csrf_cookie_name, raw_csrf)
        checks = {
            "dashboard": client.get("/"),
            "catalog": client.get("/catalogos?company=eco-automacao&availability=sob_encomenda"),
            "summary_api": client.get("/api/v1/dashboard/summary"),
            "products_api": client.get("/api/v1/products?company=portwell&page_size=24"),
            "me": client.get("/api/v1/auth/me"),
        }
        for name, response in checks.items():
            if response.status_code != 200:
                raise RuntimeError(f"{name} retornou HTTP {response.status_code}")
            print(f"{name}: HTTP 200 ({len(response.content)} bytes)")
        summary = checks["summary_api"].json()
        own_types = [item["type"] for item in summary["company_counts"]]
        if own_types[:2] != ["nossa", "nossa"] or own_types[-1:] != ["concorrente"]:
            raise RuntimeError("Empresas próprias não aparecem primeiro no dashboard.")
        if summary["treated_offers"] != sum(item["treated_count"] for item in summary["company_counts"]):
            raise RuntimeError("Total de ofertas tratadas diverge do detalhamento por empresa.")
        if summary["pipeline_offers"] != sum(item["pipeline_count"] for item in summary["company_counts"]):
            raise RuntimeError("Total do pipeline diverge do detalhamento por empresa.")
        dashboard_html = checks["dashboard"].text
        if "Catálogo tratado" not in dashboard_html or dashboard_html.find("Nossas empresas") > dashboard_html.find("Outras empresas"):
            raise RuntimeError("Dashboard não apresenta tratamento ou prioridade das nossas empresas.")

        comparison_page = client.get("/comparador?company=eco-automacao")
        comparison_api = client.get(
            "/api/v1/catalog-matches?company=eco-automacao&limit=50"
        )
        if comparison_page.status_code != 200 or comparison_api.status_code != 200:
            raise RuntimeError("Análise automática não respondeu com HTTP 200.")
        matching = comparison_api.json()
        if matching["summary"]["total"] != 7944 or not matching["items"]:
            raise RuntimeError("Análise automática não retornou a cobertura esperada.")
        if sum(item["strong_count"] for item in matching["own_portfolio"]) != matching["summary"]["coverage_count"]:
            raise RuntimeError("Sugestões fortes por empresa divergem da cobertura.")
        if "Sugestões fortes por empresa própria" not in dashboard_html:
            raise RuntimeError("Nova análise não aparece no dashboard.")
        if matching["summary"]["coverage_count"] and "Preços em até três sugestões fortes" not in dashboard_html:
            raise RuntimeError("Destaques de preço não aparecem no dashboard.")
        if any(item["own"]["company_code"] == "eco-automacao" for item in matching["items"]):
            raise RuntimeError("Concorrente apareceu como oferta do nosso portfólio.")
        elfin_match = next(
            (
                item
                for item in matching["items"]
                if item["competitor"]["brand"] == "ELFIN"
                and item["own"]["brand"] == "ELFIN"
                and item["own"]["brand_raw"] == "NEW ELFIN SRL"
            ),
            None,
        )
        if elfin_match is None or not elfin_match["reasons"]["brand_equal"]:
            raise RuntimeError("Alias NEW ELFIN SRL não foi reconhecido como ELFIN.")
        print(f"comparison_page: HTTP 200 ({len(comparison_page.content)} bytes)")
        print(
            "catalog_matching_api: cobertura global, empresas próprias e preços validados"
        )
        logout = client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": raw_csrf}
        )
        if logout.status_code != 204:
            raise RuntimeError(f"logout retornou HTTP {logout.status_code}")
        print("logout: HTTP 204")
    finally:
        with Session(get_engine()) as db, db.begin():
            db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
            db.execute(delete(User).where(User.id == user_id))


if __name__ == "__main__":
    main()
