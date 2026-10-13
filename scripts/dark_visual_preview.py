"""Read-only localhost preview of existing Jinja pages with synthetic UI data.

This does not start the PRM application or connect to its database/API.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
env = Environment(
    loader=FileSystemLoader(ROOT / "app" / "templates"),
    autoescape=select_autoescape(["html"]),
)
env.globals["url_for"] = lambda endpoint, path: "/static" + path

NAV = (
    ("Visão geral", "/"), ("Catálogos", "/catalogos"),
    ("Digitalização", "/digitalizacao"), ("Comparador", "/comparador"),
    ("Aplicações e regiões", "/aplicacoes-regioes"), ("Cards", "/cards"),
    ("Meus alertas", "/alertas"), ("Gestão", "/gestao"),
    ("Importações e qualidade", "/importacoes"),
)

SUMMARY = {
    "offers": 35785, "companies": 4, "brands": 419,
    "price_coverage": 92, "treatment_percent": 100, "pipeline_offers": 35785,
    "missing_brand": 168, "no_valid_price": 2859,
    "company_counts": [
        {"code": "portwell", "name": "Portwell", "type": "nossa", "count": 10955,
         "treated_count": 10955, "treatment_percent": 100, "pipeline_count": 10955},
        {"code": "choice-tech", "name": "Choice Tech", "type": "nossa", "count": 16886,
         "treated_count": 16886, "treatment_percent": 100, "pipeline_count": 16886},
        {"code": "eco-automacao", "name": "Eco Automação", "type": "concorrente", "count": 7944,
         "treated_count": 7944, "treatment_percent": 100, "pipeline_count": 7944},
    ],
    "availability": [{"state": "disponivel", "count": 28900}, {"state": "indisponivel", "count": 6885}],
    "top_brands": [{"name": "ELFIN", "count": 461}, {"name": "Siemens", "count": 329}],
}


def render_page(title: str) -> bytes:
    context = dict(
        title=title, user={"name": "Usuário de demonstração", "role": "gestor"},
        nav_items=NAV, active_path={"Visão geral": "/", "Digitalização": "/digitalizacao", "Catálogos": "/catalogos"}.get(title, "/"),
        csrf_token="", summary=SUMMARY, matching={"summary": None, "selected_company": None},
        comparable=None, dimensional_staging=None, dimensional_database=None,
    )
    if title == "Catálogos":
        context.update(
            filter_error=None, search_input="", price_inputs={"min": "", "max": ""},
            pagination_query="", selected_filters={"companies": [], "brands": [], "availability": [], "family_group": "", "modality": ""},
            filter_options={"companies": SUMMARY["company_counts"], "brands": ["ELFIN", "Siemens"],
                            "availability": ["disponivel", "indisponivel"], "family_groups": ["Automação"],
                            "modalities": ["venda", "pix"]},
            catalog={"total": 3, "page": 1, "pages": 1, "page_size": 100, "items": [
                {"id": "visual-1", "company_code": "portwell", "company_name": "Portwell", "company_type": "nossa",
                 "name": "Controlador industrial de teste", "external_code": "P-100", "brand": "ELFIN",
                 "availability": "disponivel", "prices": {"venda": 1250.0, "pix": None, "cartao": None}},
                {"id": "visual-2", "company_code": "choice-tech", "company_name": "Choice Tech", "company_type": "nossa",
                 "name": "Módulo de controle de teste", "external_code": "C-200", "brand": "Siemens",
                 "availability": "disponivel", "prices": {"venda": 980.0, "pix": None, "cartao": None}},
                {"id": "visual-3", "company_code": "eco-automacao", "company_name": "Eco Automação", "company_type": "concorrente",
                 "name": "Interface de teste", "external_code": "E-300", "brand": "ELFIN",
                 "availability": "indisponivel", "prices": {"venda": None, "pix": 899.0, "cartao": None}},
            ]},
        )
    html = env.get_template("shell.html").render(**context)
    # Preview is intentionally static: no API calls, product changes or credentials.
    html = html.replace('<script src="/static/js/ui.js?v=20261008-2" defer></script>', "")
    html = html.replace('<script src="/static/js/digitalizacao.js?v=20261008-claude-4" defer></script>', "")
    html = html.replace('<script src="/static/js/registration.js?v=20261008-1" defer></script>', "")
    html = html.replace('<script src="/static/js/catalog-selection.js?v=20260924-2" defer></script>', "")
    if title == "Catálogos":
        html = html.replace(
            '<div class="compare-bar"',
            '<section class="panel technical-matrix-panel" id="visual-table"><h2>Tabela técnica de prévia sintética</h2><div class="table-scroll"><table class="technical-matrix"><thead><tr><th>Característica</th><th>Portwell</th><th>Choice</th><th>Eco</th></tr></thead><tbody><tr><th>Tensão</th><td>24 V</td><td>24 V</td><td>Não informado</td></tr><tr><th>Aplicação</th><td>Industrial</td><td>Industrial</td><td>Comercial</td></tr></tbody></table></div></section><div class="compare-bar"',
        )
    if title == "Digitalização":
        html = html.replace(
            "</body>",
            """<script>
            const state = new URLSearchParams(location.search).get('state');
            const page = document.querySelector('.digitalizacao-page');
            if (page) page.dataset.company = 'choice';
            const choice = document.querySelector('[data-company-select="choice"]');
            if (choice) choice.setAttribute('aria-pressed', 'true');
            if (state === 'review' || state === 'pdf') {
              const review = document.getElementById('digitalizacao-review');
              if (review) review.hidden = false;
              const content = document.getElementById('digitalizacao-review-content');
              if (content) content.innerHTML = '<div class="digitalizacao-review-field"><strong>Nome técnico</strong><p>Controlador industrial — prévia sintética para inspeção visual</p></div><div class="digitalizacao-review-field"><strong>Características</strong><p>Entradas digitais: 16 · Saídas digitais: 8</p></div>';
            }
            if (state === 'pdf') {
              const pages = document.getElementById('digitalizacao-preview-pages');
              if (pages) pages.innerHTML = '<div class="datasheet-viewer"><div class="datasheet-viewer-toolbar"><button type="button">Anterior</button><strong>Página 1 de 2</strong><button type="button">Próxima</button><button type="button">Ampliar</button></div><div class="datasheet-viewer-canvas"><div style="width:min(100%,36rem);aspect-ratio:1/1.4;background:white;color:#111;padding:3rem"><h2>Prévia de datasheet</h2><p>Documento sintético de teste visual. O PDF real nunca é invertido.</p></div></div></div>';
            }
            if (state === 'modal') {
              const dialog = document.getElementById('digitalizacao-image-dialog');
              const preview = document.getElementById('digitalizacao-image-dialog-preview');
              if (preview) preview.src = '/static/brand-lockup.png';
              if (dialog) dialog.showModal();
            }
            </script></body>""",
        )
    return html.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/preview/dashboard":
            data, kind = render_page("Visão geral"), "text/html; charset=utf-8"
        elif path == "/preview/catalogos":
            data, kind = render_page("Catálogos"), "text/html; charset=utf-8"
        elif path == "/preview/digitalizacao":
            data, kind = render_page("Digitalização"), "text/html; charset=utf-8"
        elif path.startswith("/static/"):
            target = (STATIC / path.removeprefix("/static/")).resolve()
            if not target.is_relative_to(STATIC) or not target.is_file():
                self.send_error(404)
                return
            data, kind = target.read_bytes(), guess_type(target.name)[0] or "application/octet-stream"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print("Synthetic, read-only preview: http://127.0.0.1:8770/preview/dashboard", flush=True)
    HTTPServer(("127.0.0.1", 8770), Handler).serve_forever()
