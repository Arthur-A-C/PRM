import os
import secrets
import uuid

import httpx

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
    temp_password = secrets.token_urlsafe(24)
    temp_email = f"smoke-{user_id}@localhost.invalid"
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
                email=temp_email,
                password_hash=hash_password(temp_password),
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
                raise RuntimeError(f"{name} retornou HTTP {response.status_code}: {response.text[:500]}")
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
        catalog_first = client.get("/api/v1/products")
        catalog_second = client.get("/api/v1/products?page=2")
        if catalog_first.status_code != 200 or catalog_second.status_code != 200:
            raise RuntimeError("Paginação padrão do catálogo não respondeu.")
        first_items = catalog_first.json()["items"]
        second_items = catalog_second.json()["items"]
        if catalog_first.json()["page_size"] != 100 or len(first_items) != 100 or len(second_items) != 100:
            raise RuntimeError("Catálogo não exibe 100 produtos por página por padrão.")
        if {item["id"] for item in first_items} & {item["id"] for item in second_items}:
            raise RuntimeError("Produtos se repetem nas duas primeiras páginas.")
        if any(item["company_type"] != "nossa" for item in first_items):
            raise RuntimeError("Empresas próprias não aparecem primeiro no catálogo.")
        search_response = client.get("/api/v1/products", params={"q": "sensor 24V", "page_size": 100})
        family_option = client.get("/api/v1/filters/options").json()["family_groups"][0]
        family_response = client.get("/api/v1/products", params={"family_group": family_option})
        if search_response.status_code != 200 or search_response.json()["total"] == 0:
            raise RuntimeError("Busca por múltiplos termos não encontrou produtos.")
        if family_response.status_code != 200 or family_response.json()["total"] == 0:
            raise RuntimeError("Filtro por família tratada não encontrou produtos.")
        price_response = client.get(
            "/api/v1/products",
            params={"company": "choice-tech", "modality": "venda", "price_min": "100", "price_max": "500"},
        )
        if price_response.status_code != 200 or not price_response.json()["items"]:
            raise RuntimeError("Filtro de faixa de preço não encontrou produtos.")
        if any(not 100 <= float(item["prices"]["venda"]) <= 500 for item in price_response.json()["items"]):
            raise RuntimeError("Filtro de preço retornou produto fora da faixa.")
        modality_response = client.get("/api/v1/products?modality=pix")
        if modality_response.status_code != 200 or any(item["prices"]["pix"] is None for item in modality_response.json()["items"]):
            raise RuntimeError("Filtro apenas por modalidade retornou preço ausente.")
        any_price_response = client.get("/api/v1/products?price_min=100&price_max=500")
        if any_price_response.status_code != 200 or not any_price_response.json()["items"]:
            raise RuntimeError("Faixa de preço com todas as modalidades não retornou produtos.")
        if any(not any(amount is not None and 100 <= float(amount) <= 500
                       for amount in item["prices"].values())
               for item in any_price_response.json()["items"]):
            raise RuntimeError("Filtro de todas as modalidades retornou preço fora da faixa.")
        if client.get("/api/v1/products?page_size=75").status_code != 422:
            raise RuntimeError("API aceitou tamanho de página não suportado.")
        if client.get("/api/v1/products?q=um+dois+tres+quatro+cinco+seis+sete+oito+nove").status_code != 422:
            raise RuntimeError("API aceitou pesquisa com mais de oito termos.")
        blank_filter = client.get("/api/v1/products?company=choice-tech&brand=&availability=")
        if blank_filter.status_code != 200 or blank_filter.json()["total"] == 0:
            raise RuntimeError("Filtro em branco removeu ofertas do catálogo.")
        filtered_page = client.get("/catalogos?company=choice-tech&modality=venda&price_min=100&price_max=500")
        expected_count = f"{price_response.json()['total']:,}".replace(",", ".")
        if filtered_page.status_code != 200 or f"{expected_count}</strong> ofertas encontradas" not in filtered_page.text:
            raise RuntimeError("Filtros da interface não refletem o catálogo real.")
        all_price_page = client.get("/catalogos?price_min=100&price_max=500")
        if all_price_page.status_code != 200 or "Todas as modalidades" not in all_price_page.text:
            raise RuntimeError("Interface não aceitou faixa com todas as modalidades.")
        if "data-compare-offer" not in all_price_page.text or "data-compare-bar" not in all_price_page.text:
            raise RuntimeError("Seleção de produtos não aparece no catálogo.")
        if "/static/direct-comparison.html" not in all_price_page.text:
            raise RuntimeError("Botão de comparação não aponta para a página compatível com o servidor em execução.")
        fallback_page = client.get("/static/direct-comparison.html")
        fallback_script = client.get("/static/js/direct-comparison-fallback.js")
        if fallback_page.status_code != 200 or fallback_script.status_code != 200:
            raise RuntimeError("Página de comparação compatível não está disponível como arquivo estático.")
        direct_page = client.get("/comparacao-direta", params=[
            ("offer", str(first_items[0]["id"])), ("offer", str(first_items[1]["id"])),
        ])
        if direct_page.status_code != 200 or "Matriz técnica" not in direct_page.text:
            raise RuntimeError("Comparação direta não mostra preços e características.")
        if "Dado tratado" not in direct_page.text:
            raise RuntimeError("Comparação direta não mostra características do pipeline.")
        selected = [("offer", str(price_response.json()["items"][0]["id"])),
                    ("offer", str(price_response.json()["items"][1]["id"]))]
        direct_api = client.get("/api/v1/comparisons/preview", params=selected)
        if direct_api.status_code != 200 or not any(
            row["origin"] == "enriquecimento" and any(cell["value"] for cell in row["values"])
            for row in direct_api.json()["technical_matrix"]
        ):
            raise RuntimeError("Matriz direta não inclui características tratadas com valores.")
        referenced = client.get("/comparacao-direta", params=[*selected, ("reference", selected[0][1])])
        if referenced.status_code != 200 or "frente à referência" not in referenced.text:
            raise RuntimeError("Comparação direta não aplicou a referência de preços.")

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
        comparable_api = client.get("/api/v1/comparable-portfolio?signal=sem_familia_propria")
        if comparable_api.status_code != 200 or "Cobertura por família comparável" not in comparison_page.text:
            raise RuntimeError("Nova comparação normalizada não aparece no comparador.")
        comparable = comparable_api.json()
        if comparable["snapshot"]["stale"] or comparable["metrics"]["competitor_total"] != 7944:
            raise RuntimeError("Retrato comparável não concilia com o catálogo Eco publicado.")
        if any(item["own"] for item in comparable["items"]):
            raise RuntimeError("Filtro de famílias sem oferta própria retornou família compartilhada.")
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
        gaps_response = client.get("/api/v1/catalog-gaps?company=eco-automacao")
        if gaps_response.status_code != 200:
            raise RuntimeError("API de possíveis lacunas não respondeu com HTTP 200.")
        gaps = gaps_response.json()
        if gaps["summary"]["unmatched_total"] != matching["summary"]["no_candidate"]:
            raise RuntimeError("Total de possíveis lacunas diverge dos produtos sem candidato.")
        if gaps["summary"]["stale"]:
            raise RuntimeError("Análise de lacunas está desatualizada em relação às importações.")
        if not gaps["brands"] or not gaps["families"]:
            raise RuntimeError("Marcas e famílias sem candidato não foram agrupadas.")
        if "Possíveis lacunas no nosso catálogo" not in comparison_page.text:
            raise RuntimeError("Visualização de lacunas não aparece no comparador.")
        selected_response = client.get(
            "/api/v1/catalog-gaps",
            params={
                "company": "eco-automacao",
                "gap_type": "family",
                "gap_key": gaps["families"][0]["key"],
                "page": 1,
            },
        )
        selected = selected_response.json()["selected"]
        if selected_response.status_code != 200 or not selected or not selected["items"]:
            raise RuntimeError("Detalhe paginado da família sem candidato não funciona.")
        selected_page = client.get(
            "/comparador",
            params={
                "company": "eco-automacao",
                "gap_type": "family",
                "gap_key": gaps["families"][0]["key"],
            },
        )
        if selected_page.status_code != 200 or "lacuna-selecionada" not in selected_page.text:
            raise RuntimeError("Produtos da família não aparecem na página do comparador.")
        brand_response = client.get(
            "/api/v1/catalog-gaps",
            params={
                "company": "eco-automacao",
                "gap_type": "brand",
                "gap_key": gaps["brand_options"][-1]["key"],
            },
        )
        if brand_response.status_code != 200 or not brand_response.json()["selected"]:
            raise RuntimeError("Seleção de marca fora do grupo principal não funciona.")
        print(f"comparison_page: HTTP 200 ({len(comparison_page.content)} bytes)")
        print(
            "catalog_matching_api: cobertura, empresas próprias, preços e lacunas validados"
        )
        live_url = os.environ.get("PRM_LIVE_URL")
        if live_url:
            with httpx.Client(base_url=live_url, cookies={settings.session_cookie_name: raw_token}, timeout=10) as live:
                static_page = live.get("/static/direct-comparison.html")
                static_script = live.get("/static/js/direct-comparison-fallback.js")
                live_catalog = live.get("/catalogos")
                product = live.get(f"/api/v1/products/{first_items[0]['id']}")
                active_route = live.get("/comparacao-direta")
                if static_page.status_code != 200 or static_script.status_code != 200 or product.status_code != 200:
                    raise RuntimeError("A instância ativa não serve a página compatível ou os dados autenticados.")
                if live_catalog.status_code != 200 or "/static/direct-comparison.html" not in live_catalog.text:
                    raise RuntimeError("A instância ativa ainda não mostra o novo destino do botão no catálogo.")
                print(f"live_comparison: página estática HTTP 200, produto HTTP 200; rota Python HTTP {active_route.status_code}")
        public_url = os.environ.get("PRM_PUBLIC_PREVIEW_URL")
        preview_password = os.environ.get("PRM_PREVIEW_BASIC_PASSWORD")
        if public_url and preview_password:
            unauthenticated = httpx.get(f"{public_url}/api/v1/health/live", timeout=15)
            if unauthenticated.status_code != 401:
                raise RuntimeError("A prévia pública não exige a senha adicional.")
            with httpx.Client(
                base_url=public_url, auth=("prm-preview", preview_password), timeout=15,
                follow_redirects=False,
            ) as public:
                remote_login = public.post("/api/v1/auth/login", json={"email": temp_email, "password": temp_password})
                if remote_login.status_code != 200:
                    raise RuntimeError(f"Login remoto retornou HTTP {remote_login.status_code}.")
                cookies = remote_login.headers.get_list("set-cookie")
                if not cookies or any("secure" not in cookie.lower() for cookie in cookies):
                    raise RuntimeError("Cookie remoto sem atributo Secure.")
                if public.get("/api/v1/auth/me").status_code != 200 or public.get("/catalogos").status_code != 200:
                    raise RuntimeError("Sessão remota não acessou API e catálogo.")
                print("public_preview: Basic auth, login PRM, cookies Secure e catálogo validados")
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
