"""Candidate WCDA contract: append-only planning, GET verification, mock-only PUT.

There is deliberately no production executor or configuration switch in this module.
Plans contain private immutable snapshots; only preview() is safe for reports.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.services.store_config import COMPANIES, secure_url
from app.services.store_http import StoreAPIError, read_json

KEY = "_wcda_arquivos"
DOCUMENT_KEYS = {"label", "url", "filename", "filesize"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return sha256(_json(value).encode("utf-8")).hexdigest()


def metadata_field(product, *, allow_empty=False):
    """Exactly one existing list field. allow_empty permits first inclusion: rollback restores []."""
    metadata = product.get("meta_data")
    if not isinstance(metadata, list) or any(not isinstance(m, dict) for m in metadata):
        raise ValueError("Metadados inválidos; não converter nem sobrescrever.")
    matches = [m for m in metadata if m.get("key") == KEY]
    if len(matches) != 1:
        raise ValueError("Exige exatamente um _wcda_arquivos existente; criação/duplicidade requer revisão.")
    item = matches[0]
    if type(item.get("id")) is not int or item["id"] <= 0:
        raise ValueError("ID do metadado ausente ou inválido.")
    if not isinstance(item.get("value"), list) or any(not isinstance(d, dict) for d in item["value"]):
        raise ValueError("Valor de _wcda_arquivos não é lista de documentos; não converter.")
    if not item["value"] and not allow_empty:
        raise ValueError("Homologação inicial exige documentos existentes e rollback não vazio.")
    return deepcopy(item)


def _url(value):
    if not isinstance(value, str) or not value.strip() or any(c.isspace() for c in value):
        raise ValueError("URL do documento inválida.")
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError()
        parsed.port
    except ValueError:
        raise ValueError("URL do documento inválida.") from None
    # Queries are identity-bearing: never silently drop/normalize signed URLs for equality.
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _new_document(value):
    if not isinstance(value, dict) or set(value) != DOCUMENT_KEYS:
        raise ValueError("Novo documento exige somente label, url, filename e filesize observados no plugin.")
    if any(not isinstance(v, str) or not v.strip() for v in value.values()):
        raise ValueError("Novo documento deve ter valores reais não vazios em todos os campos.")
    if len(value["label"]) > 500 or len(value["filename"]) > 255 or len(value["url"]) > 2048:
        raise ValueError("Documento excede limites de tamanho da prévia.")
    if any(c in value["filename"] for c in '/\\') or value["filename"] in {".", ".."}:
        raise ValueError("filename deve ser apenas o nome do arquivo.")
    _url(value["url"])
    parsed = urlsplit(value["url"])
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        raise ValueError("Novo documento exige URL HTTPS pública estável, sem query ou fragmento.")
    if not re.fullmatch(r"\d+(?:[.,]\d+)?\s*(?:B|KB|MB|GB)", value["filesize"], re.I):
        raise ValueError("filesize deve ser informado no formato observado, sem inferir unidade/tamanho.")
    return deepcopy(value)


@dataclass(frozen=True)
class DocumentPlan:
    company: str
    origin: str
    product_id: int
    sku: str = field(repr=False)
    before_json: str = field(repr=False)
    payload_json: str = field(repr=False)
    added: int
    duplicates: int
    first_inclusion: bool = False

    @property
    def before(self):
        return json.loads(self.before_json)

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def fingerprint(self):
        return _hash([self.company, self.origin, self.product_id, self.sku, self.before, self.payload])


def prepare_document_update(company, origin, product, sku, additions, *, allow_empty=False):
    if company not in COMPANIES:
        raise ValueError("Loja inválida.")
    origin = secure_url(origin)
    if not isinstance(sku, str) or not sku.strip() or product.get("sku") != sku:
        raise ValueError("SKU exato não corresponde ao produto.")
    if type(product.get("id")) is not int or product["id"] <= 0:
        raise ValueError("Produto inválido.")
    current = metadata_field(product, allow_empty=allow_empty)
    if not isinstance(additions, list) or len(additions) > 50:
        raise ValueError("Informe uma lista de até 50 documentos.")
    desired = deepcopy(current["value"])
    added = duplicates = 0
    for entry in additions:
        candidate = _new_document(entry)
        for previous in desired:
            try:
                previous_url = _url(previous.get("url"))
            except ValueError:
                previous_url = None  # Preserve legacy content; never fetch or silently repair it.
            # Same URL with conflicting label/filename/size is ambiguous, not a silent replacement.
            if previous_url == _url(candidate["url"]):
                if all(previous.get(k) == candidate[k] for k in DOCUMENT_KEYS):
                    duplicates += 1
                    break
                raise ValueError("URL já cadastrada com informações divergentes; reconciliação manual necessária.")
            if any(isinstance(previous.get(k), str) and previous[k].casefold() == candidate[k].casefold()
                   for k in ("label", "filename")):
                raise ValueError("Nome/label já cadastrado em outra URL; conteúdo igual não foi comprovado.")
        else:
            desired.append(candidate)
            added += 1
    payload = {"meta_data": [{"id": current["id"], "key": KEY, "value": desired}]}
    return DocumentPlan(company, origin, product["id"], sku, _json(product), _json(payload), added, duplicates,
                        not current["value"])


def known_media_document(label, filename, filesize, media):
    """Use a confirmed WP media ID/source_url; media ID is not part of the WCDA entry."""
    if not isinstance(media, dict) or type(media.get("id")) is not int or media["id"] <= 0:
        raise ValueError("Mídia WordPress sem ID confirmado.")
    return _new_document({"label": label, "url": media.get("source_url"), "filename": filename, "filesize": filesize})


def _redacted_payload(payload):
    redactions = []
    def redact(value, path):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                here = path + "/" + key
                if key not in {"meta_data", "id", "key", "value", *DOCUMENT_KEYS}:
                    result[key] = "[campo adicional preservado; oculto]"
                    redactions.append(here)
                else:
                    result[key] = redact(item, here)
            return result
        if isinstance(value, list):
            return [redact(v, path + "/" + str(i)) for i, v in enumerate(value)]
        if isinstance(value, str) and value.startswith(("https://", "http://")):
            try:
                parsed = urlsplit(value)
                if parsed.query or parsed.fragment or parsed.username or parsed.password:
                    redactions.append(path)
                    return "[URL privada preservada; oculta]"
            except ValueError:
                redactions.append(path)
                return "[URL inválida preservada; oculta]"
        return value
    return redact(payload, ""), redactions


def preview(plan):
    payload, redactions = _redacted_payload(plan.payload)
    return {"mode": "dry_run", "writes_allowed": False, "company": plan.company,
            "method": "PUT", "endpoint": f"{plan.origin}/wp-json/wc/v3/products/{plan.product_id}",
            "action": "append" if plan.added else "no_op", "added": plan.added, "duplicates": plan.duplicates,
            "existing_count": len(metadata_field(plan.before, allow_empty=plan.first_inclusion)["value"]),
            "first_inclusion": plan.first_inclusion,
            "payload": payload, "payload_sha256": _hash(plan.payload), "plan_sha256": plan.fingerprint,
            "redacted_paths": redactions, "payload_is_exact": not redactions,
            "authorization": "not_granted", "plugin_recognition": "not_verified"}


def _protected(product):
    # Ignore Woo-generated timestamps, links and derived properties. Observe known writable fields.
    fields = ("name", "slug", "type", "status", "featured", "catalog_visibility", "description",
              "short_description", "regular_price", "sale_price", "date_on_sale_from", "date_on_sale_to",
              "virtual", "downloadable", "downloads", "download_limit", "download_expiry", "tax_status",
              "tax_class", "manage_stock", "stock_quantity", "stock_status", "backorders", "sold_individually",
              "weight", "dimensions", "shipping_class", "reviews_allowed", "upsell_ids", "cross_sell_ids",
              "parent_id", "purchase_note", "categories", "tags", "images", "attributes", "default_attributes",
              "grouped_products", "menu_order", "brands", "external_url", "button_text",
              "global_unique_id", "date_on_sale_from_gmt", "date_on_sale_to_gmt")
    other_metadata = [m for m in product.get("meta_data", []) if m.get("key") != KEY]
    return {**{k: product.get(k) for k in fields},
            "other_meta_data": sorted(other_metadata, key=lambda m: _json(m))}


def verify_document_update(plan, observed):
    identity = observed.get("id") == plan.product_id and observed.get("sku") == plan.sku
    try:
        field = metadata_field(observed)
        expected = plan.payload["meta_data"][0]
        persisted = field["id"] == expected["id"] and field["value"] == expected["value"]
        old = metadata_field(plan.before, allow_empty=plan.first_inclusion)["value"]
        preserved = field["value"][:len(old)] == old
    except ValueError:
        persisted = preserved = False
    unchanged = _protected(observed) == _protected(plan.before)
    return {"verified": identity and persisted and preserved and unchanged,
            "identity_matches": identity, "metadata_persisted": persisted,
            "previous_documents_preserved": preserved, "other_fields_unchanged": unchanged,
            "frontend_verified": False, "plugin_recognition": "not_verified"}


def rollback_payload(plan, current):
    """Plan only, no write. Never overwrite edits that occurred after the candidate PUT."""
    if not verify_document_update(plan, current)["verified"]:
        raise ValueError("Rollback automático bloqueado: estado divergente; reconciliar alterações antes de restaurar.")
    original = metadata_field(plan.before, allow_empty=plan.first_inclusion)
    return {"meta_data": [{"id": original["id"], "key": KEY, "value": original["value"]}]}


def simulate_update(plan, *, transport=None):
    """Exercise GET / PUT(meta_data only) / GET with mocks. No real HTTP transport allowed."""
    if type(transport) is not httpx.MockTransport:
        raise ValueError("Escrita real bloqueada. Exige autorização específica de loja/SKU e executor homologado.")
    # Use the store URL for fidelity, but MockTransport cannot access its network.
    with httpx.Client(base_url=plan.origin + "/wp-json/wc/v3/", transport=transport,
                      follow_redirects=False, trust_env=False, timeout=20) as client:
        path = f"products/{plan.product_id}"
        current = read_json(client, path, {"context": "edit"})
        baseline = plan.before
        if (current.get("id") != plan.product_id or current.get("sku") != plan.sku
                or metadata_field(current, allow_empty=plan.first_inclusion) != metadata_field(baseline, allow_empty=plan.first_inclusion) or _protected(current) != _protected(baseline)):
            raise ValueError("Produto alterado após a prévia; refaça a consulta. Nenhum PUT enviado.")
        if not plan.added:
            return {"status": "no_op", "put_sent": False, "verification": verify_document_update(plan, current)}
        status = None
        try:
            # Exactly one request; HTTP 200 alone is not proof of persistence.
            result = client.put(path, json=plan.payload)
            status = result.status_code
        except httpx.RequestError:
            pass
        try:
            observed = read_json(client, path, {"context": "edit"})
            verification = verify_document_update(plan, observed)
        except (StoreAPIError, ValueError):
            verification = {"verified": False, "metadata_persisted": False,
                            "frontend_verified": False, "plugin_recognition": "not_verified"}
        return {"status": "rest_verified" if status == 200 and verification["verified"] else "reconciliation_required",
                "put_sent": True, "http_status": status, "verification": verification, "automatic_retry": False}
