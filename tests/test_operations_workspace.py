"""Presentation contracts: real aggregates, accessible tabs and preserved hooks."""
import json
from html.parser import HTMLParser

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.current_analysis import summarize_current


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))


def render(title="Dashboard", published=True):
    counts = {code: dict(received=0, accepted=0, public_catalog=0, with_attributes=0,
                        unknown_family=0, conflicting_attributes=0)
              for code in ["portwell", "choice", "eco", "dimensional"]}
    manifest = dict(run_id="a" * 24, counts=counts, families={}, created_at="2026-10-15",
                    matching_status="not_assessed", ai_calls=0, rule_version="fixture", elapsed_seconds=0)
    env = Environment(loader=FileSystemLoader("app/templates"), autoescape=select_autoescape(["html"]))
    return env.get_template("shell.html").render(
        title=title, user={"name": "<script>unsafe</script>", "role": "gestor"},
        nav_items=[("Dashboard", "/"), ("Digitalização", "/digitalizacao")], active_path="/",
        refined_analysis=manifest if published else None, current_analysis=summarize_current(manifest if published else None),
        url_for=lambda endpoint, path: "/static" + path, csrf_token="test-token",
    )


@pytest.mark.parametrize("title,initial", [("Dashboard", "overview"), ("Comparador", "attributes"),
                                          ("Importações e qualidade", "quality")])
def test_workspace_tabs_and_snapshot_data(title, initial):
    html = render(title)
    nodes = Elements(html).nodes
    ids = [attrs["id"] for _, attrs in nodes if "id" in attrs]
    assert len(ids) == len(set(ids))
    root = next(attrs for _, attrs in nodes if "data-operations" in attrs)
    assert root["data-initial-view"] == initial
    for _, attrs in nodes:
        if attrs.get("role") == "tab":
            assert attrs["aria-controls"] in ids
        if attrs.get("role") == "tabpanel":
            assert attrs["aria-labelledby"] in ids
    data = json.loads(html.split('id="ops-data">')[1].split('</script>')[0])
    assert data["accepted"] == 0 and data["own_public"] == 0
    assert data["strict_coverage_percent"] is None
    cards = [attrs["data-ops-company-card"] for _, attrs in nodes if "data-ops-company-card" in attrs]
    assert cards == ["portwell", "choice", "sag"]
    assert "Sem catálogo nesta fotografia" in html
    assert "Sem telemetria" in html and "Análise de atributos ainda não disponível" in html
    assert "<script>unsafe</script>" not in html
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in html
    for source in ["eco", "dimensional"]:
        for group in ["shared", "not_found", "review"]:
            assert f'href="/catalogos?source={source}&group={group}"' in html


def test_no_snapshot_keeps_activity_map_but_never_renders_catalog_data():
    # Dashboard: digitalization activity (heatmap, feed) does not depend on a catalog snapshot.
    html = render(published=False)
    assert 'data-operations' in html and 'data-cc-heatmap' in html and 'data-cc-feed' in html
    assert 'Base de catálogo não publicada' in html and 'data-catalog-unpublished' in html
    assert 'cc-coverage-row' not in html and 'Base publicada' not in html and 'id="ops-families"' in html
    families = json.loads(html.split('id="ops-families">')[1].split('</script>')[0])
    assert families == {'families': {}, 'totals': {'group': 0}, 'sources': {}, 'own': [], 'rivals': []}
    # Analysis pages still refuse to show anything without the official snapshot.
    for title in ("Comparador", "Importações e qualidade"):
        page = render(title, published=False)
        assert "Base atual indisponível" in page and 'data-operations' not in page


def test_cards_visual_style_is_scoped_and_preserves_action_hooks():
    html = render('Cards')
    assert '/css/cards-page.css' in html and 'cards-workspace' in html
    nodes = Elements(html).nodes
    for hook in ['data-cards-filters', 'data-cards-list', 'data-export', 'data-review-selected',
                 'data-assign-selected', 'data-publish-selected']:
        assert any(hook in attrs for _, attrs in nodes)
    assert 'data-demo-cards' not in html and '/js/meeting-demo.js' not in html
    ids = [attrs['id'] for _, attrs in nodes if 'id' in attrs]
    assert len(ids) == len(set(ids))


def test_batch_page_has_isolated_assets_and_controls():
    html = render("Geração em Lote")
    nodes = Elements(html).nodes
    ids = [attrs["id"] for _, attrs in nodes if "id" in attrs]
    assert len(ids) == len(set(ids))
    assert {"batch-upload", "batch-start", "batch-retry", "batch-progress", "batch-products", "batch-history"} <= set(ids)
    assert "/css/datasheet-batches.css" in html and "/js/datasheet-batches.js" in html
    assert "/js/digitalizacao.js" not in html
    assert "/css/datasheet-batches.css" not in render("Digitalização")


def test_integration_page_separate_cards_without_credentials():
    html = render("Integrações WooCommerce")
    assert html.count("data-test-store=") == 3
    assert html.count("data-wc-status") == html.count("data-wp-status") == 3
    assert "/js/store-integrations.js" in html
    assert "WC_SECRET" not in html and "WP_APP_PASSWORD" not in html
    assert "/js/store-integrations.js" not in render("Digitalização")


def test_registration_api_page_controls_and_scoped_assets():
    html=render("Cadastro via API")
    for name in ["api-registration-upload","api-registration-confirm","api-registration-progress",
                 "api-registration-items","api-registration-history","api-registration-report"]:
        assert f'id="{name}"' in html
    assert "/js/store-registration.js" in html
    assert "/css/store-registration.css" in html
    assert "/js/store-registration.js" not in render("Digitalização")


@pytest.mark.parametrize('title',['Dashboard','Planner','Reuniões','Digitalização'])
def test_cards_redesign_not_loaded_on_other_pages(title):
    html = render(title)
    assert '/css/cards-page.css' not in html
    assert 'cards-showcase' not in html and 'cards-metrics' not in html


def test_digitalization_keeps_workflow_ids_scripts_and_inspector_target():
    html = render("Digitalização")
    assert 'href="/digitalizacao/lotes"' in html
    nodes = Elements(html).nodes
    ids = [attrs["id"] for _, attrs in nodes if "id" in attrs]
    assert len(ids) == len(set(ids))
    for identifier in ["digitalizacao-empresa", "digitalizacao-codigo", "digitalizacao-produto",
                       "digitalizacao-imagens", "digitalizacao-analisar", "digitalizacao-review",
                       "digitalizacao-gerar-datasheet", "digitalizacao-aprovar", "digitalizacao-gerar",
                       "digitalizacao-baixar-pacote", "digitalizacao-pacote-status", "digitalizacao-recuperar",
                       "context-product-name", "digitalizacao-image-dialog", "workspace-product-context"]:
        assert identifier in ids
    assert "Cadastro automatizado" not in html and not any(i.startswith("cadastro-") for i in ids)
    assert "#cadastro-automatizado" not in html
    inspector = next(attrs for _, attrs in nodes if "data-workspace-inspector" in attrs)
    assert inspector["aria-controls"] in ids and inspector["aria-expanded"] == "true"
    scripts = [attrs["src"] for tag, attrs in nodes if tag == "script" and "src" in attrs]
    assert [src.split("?")[0] for src in scripts] == ["/static/js/" + name + ".js" for name in
                                                       ["ui", "workspace", "digitalizacao", "registration"]]
    assert 'name="csrf_token" value="test-token"' in html


def test_home_is_labelled_dashboard_in_menu_title_and_breadcrumb():
    from app.routers.pages import NAV_ITEMS
    assert ("Dashboard", "/") in NAV_ITEMS and all(label != "Visão geral" for label, _ in NAV_ITEMS)
    html = render("Dashboard")
    assert "<title>Dashboard · PRM</title>" in html and "<h1>Dashboard</h1>" in html
    assert '<span aria-current="page">Dashboard</span>' in html and "Visão geral" not in html
