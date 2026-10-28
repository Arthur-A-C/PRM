"""Design system: navegação agrupada por cargo, cabeçalho, abas do módulo e folha central de estilos."""
from html.parser import HTMLParser
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.routers.pages import NAV_ITEMS
from app.services.access import visible_navigation
from app.services.current_analysis import summarize_current

ROOT = Path(__file__).resolve().parents[1]


class Nodes(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))


def render(title, path, role="gestor"):
    env = Environment(loader=FileSystemLoader(str(ROOT / "app/templates")), autoescape=select_autoescape(["html"]))
    return env.get_template("shell.html").render(
        title=title, active_path=path, nav_items=visible_navigation(role, NAV_ITEMS),
        user={"name": "Ana", "role": role}, csrf_token="t", refined_analysis=None, current_analysis=summarize_current(None),
        url_for=lambda endpoint, path: "/static" + path)


def nav_hrefs(html):
    sidebar = html.split('<aside class="sidebar">')[1].split("</aside>")[0]
    return [attrs["href"] for tag, attrs in Nodes(sidebar).nodes if tag == "a" and attrs.get("href", "").startswith("/") and "data-nav-label" in attrs]


def test_every_allowed_page_stays_in_the_grouped_menu_for_each_role():
    for role in ("gestor", "desenvolvedor", "vendedor"):
        html = render("Planner", "/planner", role)
        hrefs = nav_hrefs(html)
        assert {href for _, href in visible_navigation(role, NAV_ITEMS)} <= set(hrefs), role
        assert len([h for h in hrefs if h == "/planner"]) == 1
        assert "/cards" not in hrefs and "/reunioes" not in hrefs  # o Planner concentra cards e reuniões


def test_sellers_never_see_manager_subpages_and_groups_are_labelled():
    seller = render("Cards", "/cards", "vendedor")
    assert "/digitalizacao/cadastro-api" not in seller and "/reunioes/pauta-semanal" not in seller
    assert "/digitalizacao" not in nav_hrefs(seller) and "/gestao" not in nav_hrefs(seller)
    manager = render("Cadastro via API", "/digitalizacao/cadastro-api")
    for group in ("Operação", "Relacionamento", "Gestão", "Dados", "Administração"):
        assert f'<p class="sidebar-caption">{group}</p>' in manager
    # Inside the module the parent is marked and the child is the current page.
    nodes = Nodes(manager.split('<aside class="sidebar">')[1].split("</aside>")[0]).nodes
    assert any(a.get("href") == "/digitalizacao" and a.get("class") == "is-within" for _, a in nodes)
    assert any(a.get("href") == "/digitalizacao/cadastro-api" and a.get("aria-current") == "page" for _, a in nodes)


def test_header_has_breadcrumb_real_subtitle_and_no_duplicated_logos():
    html = render("Remoção de Arquivos", "/digitalizacao/remocao-arquivos")
    header = html.split('<header class="page-header')[1].split("</header>")[0]
    assert 'aria-label="Você está em"' in header and 'href="/digitalizacao">Digitalização</a>' in header
    assert "Dry Run, aprovação e restauração" in header
    assert "brand-trio-header" not in header and "Nova digitalização" not in header
    assert "data-workspace-clock" in header  # relógio operacional preservado (compacto)


@pytest.mark.parametrize("title,path", [("Digitalização", "/digitalizacao"), ("Cadastro via API", "/digitalizacao/cadastro-api"),
                                        ("Remoção de Arquivos", "/digitalizacao/remocao-arquivos"), ("Resolução de Imagens", "/digitalizacao/resolucao-imagens")])
def test_digitalization_pages_share_module_tabs_and_unique_ids(title, path):
    html = render(title, path)
    tabs = html.split('class="prm-tabs"')[1].split("</nav>")[0]
    assert f'href="{path}" aria-current="page"' in tabs and tabs.count("<a ") == 6
    ids = [attrs["id"] for _, attrs in Nodes(html).nodes if "id" in attrs]
    assert len(ids) == len(set(ids))
    assert 'class="prm-tabs"' not in render(title, path, "vendedor")


def test_overview_has_empty_states_and_keeps_snapshot_notice():
    html = render("Dashboard", "/")
    assert "data-overview" in html and "Nenhum catálogo importado" in html and "data-cc-heatmap" in html
    assert html.count('data-overview-block="') == 6 and "/static/js/overview.js" in html


def test_design_system_is_loaded_last_and_defines_the_tokens():
    base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    head = base.split("</head>")[0]
    assert head.rstrip().splitlines()[-1].strip().startswith('<link rel="stylesheet" href="{{ url_for(\'static\', path=\'/css/prm-system.css\')')
    css = (ROOT / "app/static/css/prm-system.css").read_text(encoding="utf-8")
    for token in ("--cc-bg", "--cc-surface", "--cc-ink", "--cc-primary", "--cc-ok", "--cc-warn", "--cc-alert", "--ui-text-base", "--ds-text-title"):
        assert token + ":" in css
    assert ":root[data-theme=\"dark\"]" in css and "prefers-reduced-motion" in css
