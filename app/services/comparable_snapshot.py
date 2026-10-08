"""Read-only, auditable portfolio-breadth snapshot from normalized exports.

Family overlap is a taxonomy signal, never proof of product equivalence.
"""

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session


SOURCE_CODES = {"CHOICE": "choice-tech", "PORTWELL": "portwell", "ECO": "eco-automacao"}
REQUIRED_BASE = {"Chave_Unica", "Fonte", "ID_Origem", "Macro_Categoria", "Familia_Comparavel"}
REQUIRED_ATTRIBUTES = {"Chave_Unica", "Fonte", "Atributo", "Origem_Valor", "Relevante_Familia"}
SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "data" / "analysis" / "comparable_snapshot.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rows(path: Path, required: set[str]):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter=";")
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path.name}: colunas ausentes: {', '.join(sorted(missing))}")
        yield from reader


def build_snapshot(base_path: Path, attributes_path: Path, published_codes: dict[str, set[str]]) -> dict:
    """Reconcile external rows to published offers; leave operational data untouched."""
    source_rows = Counter()
    duplicate_keys = Counter()
    not_published = Counter()
    seen: dict[str, dict] = {}
    families: dict[tuple[str, str], dict] = {}
    for row in _rows(base_path, REQUIRED_BASE):
        source = row["Fonte"]
        if source not in SOURCE_CODES:
            raise ValueError(f"Fonte desconhecida: {source!r}")
        source_rows[source] += 1
        key = row["Chave_Unica"]
        if key != f"{source}:{row['ID_Origem']}":
            raise ValueError(f"Chave inconsistente: {key!r}")
        if key in seen:
            duplicate_keys[source] += 1
            if row != seen[key]:
                raise ValueError(f"Chave duplicada com dados divergentes: {key}")
            continue
        seen[key] = row
        if row["ID_Origem"] not in published_codes.get(source, set()):
            not_published[source] += 1
            continue
        macro = row["Macro_Categoria"].strip()
        family = row["Familia_Comparavel"].strip()
        if not macro or not family:
            raise ValueError(f"Classificação vazia: {key}")
        slot = families.setdefault((macro, family), {
            "macro": macro, "family": family,
            "counts": {name: 0 for name in SOURCE_CODES},
            "with_attributes": {name: 0 for name in SOURCE_CODES},
        })
        slot["counts"][source] += 1

    accepted = {key for key, row in seen.items()
                if row["ID_Origem"] in published_codes.get(row["Fonte"], set())}
    attribute_rows = Counter()
    attribute_keys: set[str] = set()
    inferred_keys: set[str] = set()
    orphan_attributes = 0
    attribute_pairs: set[tuple[str, str]] = set()
    duplicate_attribute_rows = 0
    for row in _rows(attributes_path, REQUIRED_ATTRIBUTES):
        key = row["Chave_Unica"]
        if row["Fonte"] not in SOURCE_CODES or not key.startswith(f"{row['Fonte']}:"):
            raise ValueError(f"Atributo com fonte/chave inconsistente: {key!r}")
        if key not in accepted:
            orphan_attributes += 1
            continue
        pair = (key, row["Atributo"])
        if pair in attribute_pairs:
            duplicate_attribute_rows += 1
            continue
        attribute_pairs.add(pair)
        attribute_rows[row["Fonte"]] += 1
        attribute_keys.add(key)
        if row["Origem_Valor"].startswith("texto"):
            inferred_keys.add(key)
    for key in attribute_keys:
        row = seen[key]
        families[(row["Macro_Categoria"].strip(), row["Familia_Comparavel"].strip())]["with_attributes"][row["Fonte"]] += 1

    ordered = sorted(families.values(), key=lambda item: (
        -(item["counts"]["ECO"] if item["counts"]["CHOICE"] + item["counts"]["PORTWELL"] == 0 else 0),
        -item["counts"]["ECO"], item["macro"], item["family"],
    ))
    totals = {source: sum(item["counts"][source] for item in ordered) for source in SOURCE_CODES}
    return {
        "schema_version": 1,
        "sources": {"base_sha256": sha256(base_path), "attributes_sha256": sha256(attributes_path)},
        "quality": {
            "source_rows": dict(source_rows), "duplicate_keys": dict(duplicate_keys),
            "not_published": dict(not_published), "orphan_attribute_rows": orphan_attributes,
            "duplicate_attribute_rows": duplicate_attribute_rows,
            "attribute_rows": dict(attribute_rows), "products_with_attributes": len(attribute_keys),
            "products_with_inferred_attributes": len(inferred_keys),
        },
        "totals": totals,
        "published_counts": {source: len(published_codes.get(source, ())) for source in SOURCE_CODES},
        "macro_count": len({item["macro"] for item in ordered}),
        "family_count": len(ordered),
        "families": ordered,
    }


def published_offer_codes(db: Session) -> dict[str, set[str]]:
    codes = defaultdict(set)
    for company_code, external_code in db.execute(text("""
        SELECT c.code, o.external_code FROM offers o
        JOIN companies c ON c.id = o.company_id
        WHERE o.active = true AND o.excluded_from_analytics = false
    """)):
        for source, code in SOURCE_CODES.items():
            if company_code == code:
                codes[source].add(external_code)
                break
    return dict(codes)


def load_snapshot(db: Session, organization_id, path: Path = SNAPSHOT_PATH) -> dict | None:
    if not path.is_file():
        return None
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if snapshot.get("schema_version") != 1 or snapshot.get("organization_id") != str(organization_id):
        return None
    counts = dict(db.execute(text("""
        SELECT c.code, count(o.id) FROM companies c JOIN offers o ON o.company_id = c.id
        WHERE o.active = true AND o.excluded_from_analytics = false
          AND o.organization_id = :organization_id GROUP BY c.code
    """), {"organization_id": organization_id}).all())
    snapshot["stale"] = any(counts.get(SOURCE_CODES[source], 0) != snapshot["published_counts"][source]
                            for source in SOURCE_CODES)
    return snapshot


def snapshot_view(snapshot: dict, macro: str = "", signal: str = "", page: int = 1) -> dict:
    """Aggregate breadth signals without implying individual equivalence."""
    families = snapshot["families"]
    competitor_total = snapshot["totals"]["ECO"]
    competitor_in_own_families = sum(item["counts"]["ECO"] for item in families
                                     if item["counts"]["CHOICE"] + item["counts"]["PORTWELL"])
    competitor_only = competitor_total - competitor_in_own_families
    own_only_families = sum(1 for item in families if item["counts"]["ECO"] == 0
                            and item["counts"]["CHOICE"] + item["counts"]["PORTWELL"] > 0)
    macros = sorted({item["macro"] for item in families})
    if macro not in macros:
        macro = ""
    if signal not in {"sem_familia_propria", "familia_compartilhada", "so_nossas"}:
        signal = ""
    selected = []
    for item in families:
        own = item["counts"]["CHOICE"] + item["counts"]["PORTWELL"]
        eco = item["counts"]["ECO"]
        state = "sem_familia_propria" if eco and not own else (
            "familia_compartilhada" if eco and own else "so_nossas")
        if (not macro or item["macro"] == macro) and (not signal or state == signal):
            selected.append({**item, "own": own, "signal": state})
    page_size = 25
    pages = max(1, math.ceil(len(selected) / page_size))
    page = min(max(1, page), pages)
    return {
        "snapshot": {key: value for key, value in snapshot.items() if key != "families"},
        "metrics": {
            "competitor_total": competitor_total,
            "competitor_in_own_families": competitor_in_own_families,
            "competitor_only": competitor_only,
            "family_overlap_percent": round(100 * competitor_in_own_families / competitor_total, 1)
            if competitor_total else 0,
            "own_only_families": own_only_families,
        },
        "macros": macros, "macro": macro, "signal": signal,
        "items": selected[(page - 1) * page_size:page * page_size],
        "total": len(selected), "page": page, "pages": pages,
    }
