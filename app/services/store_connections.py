"""Read-only connection diagnostics. Only sanitized summaries are persisted."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.services.store_config import COMPANIES, ROOT
from app.services.store_http import StoreAPIError, http_client, read_json
from app.services.registration_woo_api import WooClient, credentials_for
from app.services.wordpress_api import WordPressClient


def failure(exc, attempted=True):
    if isinstance(exc, StoreAPIError):
        return {"status": exc.code, "message": str(exc), "http_status": exc.status,
                "attempted": attempted, "authenticated": False}
    return {"status": "invalid_response" if attempted else "not_configured",
            "message": "Resposta inválida; autenticação não confirmada." if attempted else
                       "Credenciais ausentes ou URL inválida. Confira o .env do backend.",
            "attempted": attempted, "authenticated": False}


def check_woo(company, settings, transport=None):
    try:
        credentials = credentials_for(company, settings)
    except ValueError as exc:
        return failure(exc, False)
    client = WooClient(credentials, timeout=settings.timeout, transport=transport)
    try:
        rows = client.products(per_page=1, _fields="id,meta_data")
        # Protected endpoint, plus anonymous negative control. Public responses alone
        # must never be presented as proof that a key has authenticated.
        with http_client(credentials.base_url, "wc/v3", timeout=settings.timeout, transport=transport) as anonymous:
            try:
                read_json(anonymous, "products", {"context":"edit", "per_page":1, "_fields":"id"})
            except StoreAPIError as exc:
                if exc.status not in {401, 403}:
                    return {"status":"unconfirmed", "authenticated":False, "attempted":True,
                            "message":"Consulta autenticada respondeu, mas o controle anônimo foi inconclusivo."}
            else:
                return {"status":"public_endpoint", "authenticated":False, "attempted":True,
                        "message":"O endpoint também respondeu sem credenciais; autenticação não comprovada."}
        fields = []
        for row in rows:
            metadata = row.get("meta_data", [])
            if isinstance(metadata, list):
                for item in metadata:
                    if isinstance(item, dict) and item.get("key") in {"wcda_arquivos", "_wcda_arquivos"}:
                        fields.append({"key":item["key"], "value_type":type(item.get("value")).__name__})
        return {"status":"ok", "authenticated":True, "attempted":True, "http_status":200,
                "message":"Leitura autenticada de produtos confirmada. Escrita não foi testada.",
                "permissions":{"read_products":True, "write_products":None},
                "wcda":{"sample_fields":fields, "scope":"amostra de até um produto",
                        "write_support":"não verificado", "storage":"não determinado pela API"}}
    except (StoreAPIError, ValueError) as exc:
        return failure(exc)
    finally:
        client.close()


def check_wordpress(company, settings, transport=None):
    try:
        credentials = settings.credentials(company, "wp")
    except ValueError as exc:
        return failure(exc, False)
    client = WordPressClient(credentials, timeout=settings.timeout, transport=transport)
    try:
        identity = client.identity()
        caps = identity.get("capabilities")
        permissions = {name: (caps.get(name) is True if isinstance(caps, dict) else None)
                       for name in ("read", "upload_files", "edit_products", "manage_woocommerce")}
        try:
            client.media()
            media = {"status":"ok", "message":"Leitura de mídia em contexto edit permitida."}
        except (StoreAPIError, ValueError) as exc:
            media = failure(exc)
        return {"status":"ok" if media["status"] == "ok" else "limited", "authenticated":True,
                "attempted":True, "http_status":200, "permissions":permissions, "media":media,
                "message":"Conta autenticada; permissões declaradas abaixo. Nenhum upload realizado.",
                "allowed_upload_formats":None,
                "formats_note":"PNG/JPG/WebP/PDF/ZIP não foram enviados. Restrições MIME/plugins ainda não homologadas."}
    except (StoreAPIError, ValueError) as exc:
        return failure(exc)
    finally:
        client.close()


def check_company(company, settings, transport=None):
    if company not in COMPANIES:
        raise ValueError("Empresa inválida.")
    return {"company":company, "checked_at":datetime.now(timezone.utc).isoformat(),
            "woocommerce":check_woo(company, settings, transport),
            "wordpress":check_wordpress(company, settings, transport),
            "read_only":True}


class ConnectionHistory:
    def __init__(self, settings):
        root = Path(settings.status_dir)
        if not root.is_absolute():
            root = ROOT / root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "connections.sqlite3"

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("CREATE TABLE IF NOT EXISTS checks(org TEXT, company TEXT, result TEXT, PRIMARY KEY(org,company))")
        return db

    def save(self, org, result):
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO checks VALUES(?,?,?)",
                       (str(org), result["company"], json.dumps(result, ensure_ascii=False)))
        db.close()

    def list(self, org):
        with self._connect() as db:
            result = {row[0]:json.loads(row[1]) for row in db.execute("SELECT company,result FROM checks WHERE org=?", (str(org),))}
        db.close()
        return [result.get(company, {"company":company, "checked_at":None, "woocommerce":{"status":"not_tested"},
                                    "wordpress":{"status":"not_tested"}, "read_only":True}) for company in COMPANIES]
