"""Isolated WooCommerce v3 adapter. No automatic writes or media uploads."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.schemas.registration import RegistrationProduct
from app.services.registration_core import fold


@dataclass(frozen=True)
class WooCredentials:
    base_url: str
    key: str
    secret: str


def credentials_for(company: str) -> WooCredentials:
    if company not in {"choice", "sag", "portwell"}:
        raise ValueError("Empresa WooCommerce inválida.")
    prefix = "PRM_WOO_" + company.upper() + "_"
    base_url = os.environ.get(prefix + "URL", "").rstrip("/")
    key = os.environ.get(prefix + "KEY", "")
    secret = os.environ.get(prefix + "SECRET", "")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"}:
        raise ValueError(f"URL HTTPS da loja {company} não configurada corretamente.")
    if not key or not secret:
        raise ValueError(f"Credenciais da loja {company} não configuradas.")
    return WooCredentials(base_url, key, secret)


class WooClient:
    def __init__(self, credentials: WooCredentials, *, transport: httpx.BaseTransport | None = None):
        self.credentials = credentials
        self.client = httpx.Client(
            base_url=credentials.base_url + "/wp-json/wc/v3/",
            auth=(credentials.key, credentials.secret),
            timeout=20,
            follow_redirects=False,
            transport=transport,
        )

    def close(self):
        self.client.close()

    def _get(self, path: str, **params):
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def find_by_sku(self, sku: str) -> dict | None:
        rows = self._get("products", sku=sku, per_page=100)
        exact = [item for item in rows if item.get("sku") == sku]
        if len(exact) > 1:
            raise ValueError(f"SKU duplicado na loja: {sku}.")
        return exact[0] if exact else None

    def categories(self) -> list[dict]:
        results = []
        for page in range(1, 51):
            rows = self._get("products/categories", per_page=100, page=page)
            results.extend(rows)
            if len(rows) < 100:
                return results
        raise ValueError("Categorias excedem o limite seguro de paginação.")

    def attributes(self) -> list[dict]:
        return self._get("products/attributes", per_page=100)

    def resolve_category_ids(self, paths: list[str], categories: list[dict]) -> list[int]:
        by_parent: dict[tuple[int, str], list[int]] = {}
        for category in categories:
            key = (int(category.get("parent") or 0), fold(category["name"]))
            by_parent.setdefault(key, []).append(int(category["id"]))
        ids = []
        for path in paths:
            parent = 0
            for name in (part.strip() for part in path.split(">")):
                matches = by_parent.get((parent, fold(name)), [])
                if len(matches) != 1:
                    raise ValueError(f"Categoria ausente ou ambígua na loja: {path}.")
                parent = matches[0]
                if parent not in ids:
                    ids.append(parent)
        return ids

    def preview(self, product: RegistrationProduct) -> dict:
        previous = self.find_by_sku(product.sku)
        category_ids = self.resolve_category_ids(product.category_paths, self.categories())
        global_attributes = self.attributes()
        globals_by_name = {}
        for attribute in global_attributes:
            globals_by_name.setdefault(fold(attribute["name"]), []).append(attribute)
        requested_attributes = []
        for position, attribute in enumerate(product.attributes):
            matches = globals_by_name.get(fold(attribute.name), [])
            if len(matches) > 1:
                raise ValueError(f"Atributo global ambíguo: {attribute.name}.")
            data = {
                "name": attribute.name,
                "position": position,
                "visible": attribute.visible,
                "variation": False,
                "options": attribute.values,
            }
            if matches:
                data["id"] = int(matches[0]["id"])
                data["name"] = matches[0]["name"]
            requested_attributes.append(data)
        if previous:
            previous_categories = [int(item["id"]) for item in previous.get("categories", [])]
            category_ids = list(dict.fromkeys(previous_categories + category_ids))
            previous_attributes = previous.get("attributes", [])
            keys = {fold(item.get("name", "")) for item in requested_attributes}
            requested_attributes = [item for item in previous_attributes if fold(item.get("name", "")) not in keys] + requested_attributes
            if len(requested_attributes) > max(15, len(previous_attributes)):
                raise ValueError("Atualização excederia 15 atributos; revisão necessária.")
        payload = {
            "name": product.commercial_title,
            "categories": [{"id": identifier} for identifier in category_ids],
            "attributes": requested_attributes,
        }
        if product.full_description is not None:
            payload["description"] = product.full_description
        if product.short_description is not None:
            payload["short_description"] = product.short_description
        if previous is None:
            payload.update({"type": "simple", "sku": product.sku, "status": "draft"})
        return {
            "action": "update" if previous else "create_draft",
            "product_id": previous.get("id") if previous else None,
            "before": {
                "name": previous.get("name"),
                "status": previous.get("status"),
                "categories": previous.get("categories"),
                "attributes": previous.get("attributes"),
            } if previous else None,
            "payload": payload,
        }


def preview_live_product(product: RegistrationProduct, *, transport: httpx.BaseTransport | None = None) -> dict:
    client = WooClient(credentials_for(product.company), transport=transport)
    try:
        return client.preview(product)
    finally:
        client.close()
