"""Isolated WooCommerce v3 adapter. No automatic writes or media uploads."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.schemas.registration import RegistrationProduct
from app.services.registration_core import fold
from app.services.store_config import StoreSettings
from app.services.store_http import http_client, read_json


@dataclass(frozen=True)
class WooCredentials:
    base_url: str
    key: str = field(repr=False)
    secret: str = field(repr=False)


def credentials_for(company: str, settings=None) -> WooCredentials:
    value = (settings or StoreSettings()).credentials(company, "wc")
    return WooCredentials(value.base_url, value.username, value.password)


class WooClient:
    def __init__(self, credentials: WooCredentials, *, transport: httpx.BaseTransport | None = None, timeout=20):
        self.credentials = credentials
        self.client = http_client(credentials.base_url, "wc/v3", auth=(credentials.key, credentials.secret),
                                  timeout=timeout, transport=transport)

    def close(self):
        self.client.close()

    def _get(self, path: str, **params):
        return read_json(self.client, path, params)

    def products(self, page=1, per_page=20, **params):
        if not 1 <= page <= 1000 or not 1 <= per_page <= 100:
            raise ValueError("Paginação inválida.")
        rows = self._get("products", page=page, per_page=per_page, context="edit", **params)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Resposta de produtos inválida.")
        return rows

    def product(self, identifier: int):
        if type(identifier) is not int or identifier <= 0:
            raise ValueError("Identificador de produto inválido.")
        result = self._get(f"products/{identifier}", context="edit")
        if not isinstance(result, dict) or result.get("id") != identifier:
            raise ValueError("Resposta de produto inválida.")
        return result

    def find_by_sku(self, sku: str) -> dict | None:
        rows = self.products(sku=sku, per_page=100)
        if len(rows) == 100:
            raise ValueError("Busca de SKU excedeu o limite seguro; revisão necessária.")
        exact = [item for item in rows if item.get("sku") == sku]
        if len(exact) > 1:
            raise ValueError(f"SKU duplicado na loja: {sku}.")
        return exact[0] if exact else None

    def upload_limit(self) -> int | None:
        """Largest upload the store's WordPress/PHP accepts (wp_max_upload_size), read-only. None = not exposed."""
        try:
            status = self._get("system_status", _fields="environment")
        except ValueError:
            return None  # needs manage_woocommerce; absence is reported, never guessed
        size = (status.get("environment") or {}).get("max_upload_size") if isinstance(status, dict) else None
        return size if type(size) is int and size > 0 else None

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

    def preview(self, product: RegistrationProduct, *, existing_only=False, existing=None) -> dict:
        previous = existing if existing is not None else self.find_by_sku(product.sku)
        if existing_only and not previous:
            raise ValueError("SKU não existe na loja; criação automática proibida.")
        if previous and previous.get("sku") != product.sku:
            raise ValueError("SKU da resposta não corresponde ao produto solicitado.")
        category_ids = self.resolve_category_ids(product.category_paths, self.categories()) if product.category_paths else []
        global_attributes = self.attributes() if product.attributes else []
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
            if any(item.get("variation") and fold(item.get("name", "")) in keys for item in previous_attributes):
                raise ValueError("Atributo de variação exige revisão; não substituir automaticamente.")
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
