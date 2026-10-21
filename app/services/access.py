"""Explicit module allowlists; unknown roles are denied, never promoted."""
import re
from copy import deepcopy
from fastapi import HTTPException

ROLES = ("desenvolvedor", "gestor", "vendedor")
MANAGERS = frozenset({"desenvolvedor", "gestor"})
SELLER_PAGES = frozenset({"/catalogos", "/comparacao-atual", "/comparacao-direta",
                         "/cards", "/reunioes", "/planner", "/alertas"})


def require_management(user):
    if user.role not in MANAGERS:
        raise HTTPException(403, "Acesso restrito a desenvolvedores e gestores.")


def api_allowed(role, path):
    if role in MANAGERS:
        return True
    if role != "vendedor":
        return False
    return bool(re.fullmatch(
        r"/api/v1/(?:auth/(?:me|logout)|filters/options|products(?:/[\w-]+)?|"
        r"comparisons(?:/[\w-]+)?|planner(?:/.*)?)", path.rstrip("/")))


def visible_navigation(role, items):
    return tuple((label, path) for label, path in items
                 if role in MANAGERS or (role == "vendedor" and path in SELLER_PAGES))


def public_product_data(value):
    """Remove import provenance from legacy product/comparison responses for sellers."""
    hidden = {"source", "raw_payload", "import_run_id", "source_record_id", "file_sha256",
              "row_number", "sheet_name", "original_filename", "exclusion_reason", "method"}
    if isinstance(value, dict):
        return {k: public_product_data(v) for k, v in value.items() if k not in hidden}
    if isinstance(value, list):
        return [public_product_data(v) for v in value]
    return deepcopy(value)
