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


def render(title="Visão geral", published=True):
    counts = {code: dict(received=0, accepted=0, public_catalog=0, with_attributes=0,
                        unknown_family=0, conflicting_attributes=0)
              for code in ["portwell", "choice", "eco", "dimensional"]}
    manifest = dict(run_id="a" * 24, counts=counts, families={}, created_at="2026-10-15",
                    matching_status="not_assessed", ai_calls=0, rule_version="fixture", elapsed_seconds=0)
    env = Environment(loader=FileSystemLoader("app/templates"), autoescape=select_autoescape(["html"]))
    return env.get_template("shell.html").render(
        title=title, user={"name": "<script>unsafe</script>", "role": "gestor"},
        nav_items=[("Visão geral", "/"), ("Digitalização", "/digitalizacao")], active_path="/",
        refined_analysis=manifest if published else None, current_analysis=summarize_current(manifest if published else None),
        url_for=lambda endpoint, path: "/static" + path, csrf_token="test-token",
    )


@pytest.mark.parametrize("title,initial", [("Visão geral", "overview"), ("Comparador", "attributes"),
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


def test_no_snapshot_never_renders_dashboard_or_legacy_data():
    html = render(published=False)
    assert "Base atual indisponível" in html
    assert 'data-operations' not in html and 'id="ops-data"' not in html


def test_digitalization_keeps_workflow_ids_scripts_and_inspector_target():
    html = render("Digitalização")
    nodes = Elements(html).nodes
    ids = [attrs["id"] for _, attrs in nodes if "id" in attrs]
    assert len(ids) == len(set(ids))
    for identifier in ["digitalizacao-empresa", "digitalizacao-codigo", "digitalizacao-produto",
                       "digitalizacao-imagens", "digitalizacao-analisar", "digitalizacao-review",
                       "digitalizacao-gerar-datasheet", "digitalizacao-aprovar", "digitalizacao-gerar",
                       "digitalizacao-baixar-pacote", "cadastro-automatizado", "cadastro-woo-previa",
                       "context-product-name", "digitalizacao-image-dialog", "workspace-product-context"]:
        assert identifier in ids
    inspector = next(attrs for _, attrs in nodes if "data-workspace-inspector" in attrs)
    assert inspector["aria-controls"] in ids and inspector["aria-expanded"] == "true"
    scripts = [attrs["src"] for tag, attrs in nodes if tag == "script" and "src" in attrs]
    assert [src.split("?")[0] for src in scripts] == ["/static/js/" + name + ".js" for name in
                                                       ["ui", "workspace", "digitalizacao", "registration"]]
    assert 'name="csrf_token" value="test-token"' in html
