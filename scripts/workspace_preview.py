"""Local read-only UI preview using a real snapshot, never the application API.

Run with: python -m scripts.workspace_preview --manifest PATH
Only binds to loopback. GET pages/assets only; no database, sessions or writes.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.current_analysis import summarize_current
from app.services.operations_overview import operations_overview
from app.routers.pages import NAV_ITEMS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
PAGES = {"/": "Visão geral", "/digitalizacao": "Digitalização",
         "/comparador": "Comparador", "/importacoes": "Importações e qualidade"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8871)
    parser.add_argument("--operations-root", type=Path, help="Pasta de produtos (com _runs/) lida pelo serviço real; padrão: armazenamento configurado")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    current = summarize_current(manifest)
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"),
                      autoescape=select_autoescape(["html"]))
    env.globals["url_for"] = lambda endpoint, path: "/static" + path

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            if path in PAGES:
                html = env.get_template("shell.html").render(
                    title=PAGES[path], active_path=path, nav_items=NAV_ITEMS,
                    user={"name": "Prévia local · somente leitura", "role": "gestor"}, csrf_token="",
                    refined_analysis=manifest, current_analysis=current,
                    operations=operations_overview(args.operations_root),
                )
                data, kind = html.encode("utf-8"), "text/html; charset=utf-8"
            elif path == "/login":
                html = env.get_template("login.html").render(title="Entrar", error=None)
                data, kind = html.encode("utf-8"), "text/html; charset=utf-8"
            elif path == "/api/v1/operations/overview":
                data, kind = json.dumps(operations_overview(args.operations_root)).encode("utf-8"), "application/json"
            elif path.startswith("/static/"):
                target = (STATIC / path.removeprefix("/static/")).resolve()
                if not target.is_relative_to(STATIC) or not target.is_file():
                    self.send_error(404)
                    return
                data, kind = target.read_bytes(), guess_type(target.name)[0] or "application/octet-stream"
            else:
                self.send_error(404, "Preview only: application/API not mounted")
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    print(f"Read-only preview: http://127.0.0.1:{args.port} / snapshot {manifest['run_id']}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
