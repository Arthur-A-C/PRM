"""Shared HTTP layer: no write methods, redirects, query-string credentials or raw errors."""
import json
import re
import ssl
import time

import httpx

from app.services.store_config import secure_url


class StoreAPIError(ValueError):
    def __init__(self, code, message, status=None):
        super().__init__(message)
        self.code, self.status = code, status


def http_client(base_url, namespace, auth=None, timeout=20, transport=None):
    return httpx.Client(base_url=secure_url(base_url) + "/wp-json/" + (namespace.strip("/") + "/" if namespace else ""),
                        auth=auth, timeout=httpx.Timeout(timeout, connect=min(timeout, 10)),
                        follow_redirects=False, verify=True, trust_env=False, transport=transport,
                        headers={"Accept": "application/json", "User-Agent": "PRM-ReadOnly-Integration/1"})


def read_json(client, path, params=None):
    # product/<id> is the WordPress REST view of a product (featured_media), read-only like the rest.
    if not re.fullmatch(r"(?:products(?:/\d+|/categories|/attributes)?|product/\d+|users/me|media(?:/\d+)?|system_status|)", path):
        raise ValueError("Endpoint de leitura não permitido.")
    started = time.monotonic()
    try:
        with client.stream("GET", path, params=params or {}) as response:
            status = response.status_code
            if status != 200:
                code, message = {
                    401: ("unauthorized", "Autenticação recusada (401). Confira credenciais e encaminhamento do header Authorization."),
                    403: ("forbidden", "Acesso negado (403): permissões insuficientes ou bloqueio de segurança."),
                    404: ("not_found", "Endpoint não encontrado (404). Confira URL, REST API e plugin WooCommerce."),
                    429: ("rate_limited", "Limite de requisições atingido (429). Aguarde antes de testar novamente."),
                }.get(status, ("redirect" if 300 <= status < 400 else "http_error",
                              "Redirecionamento recusado; configure a URL canônica." if 300 <= status < 400 else "A loja retornou erro HTTP."))
                raise StoreAPIError(code, message, status)
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 4 * 1024**2:
                    raise StoreAPIError("invalid_response", "Resposta excede o limite de segurança.", status)
                if time.monotonic() - started > client.timeout.read:
                    raise StoreAPIError("timeout", "A loja excedeu o tempo limite.")
            try:
                return json.loads(raw)
            except (ValueError, UnicodeError):
                raise StoreAPIError("invalid_response", "Resposta não é JSON válido; possível login, proxy ou bloqueio.", status) from None
    except StoreAPIError:
        raise
    except httpx.TimeoutException:
        raise StoreAPIError("timeout", "Tempo limite excedido ao consultar a loja.") from None
    except httpx.RequestError as exc:
        cause = exc
        tls = False
        while cause is not None:
            tls = tls or isinstance(cause, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(cause)
            cause = cause.__cause__
        raise StoreAPIError("tls_error" if tls else "connection_error",
                            "Falha SSL/TLS; certificado não foi ignorado." if tls else "Falha de comunicação/DNS com a loja.") from None
