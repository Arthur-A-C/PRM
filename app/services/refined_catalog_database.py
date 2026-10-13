"""Persistência de snapshots, isolada das ofertas legadas e transacional."""

import json
import uuid
from datetime import datetime, timezone
from itertools import groupby

from sqlalchemy import case, func, insert, select, update

from app.models.refined_catalog import RefinedCatalogItem, RefinedCatalogRaw, RefinedCatalogRun
from app.services.refined_catalog import ORDER, STAGING, plain, verify_run


def json_lines(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def database_manifest(conn, organization_id):
    return conn.execute(select(RefinedCatalogRun.manifest).where(
        RefinedCatalogRun.organization_id == organization_id, RefinedCatalogRun.status == "published"
    )).scalar_one_or_none()


def persist_run(engine, organization_id, run_id, *, output_root=STAGING):
    directory = output_root / run_id
    manifest = verify_run(directory)
    expected = sum(c["accepted"] for c in manifest["counts"].values())
    received = sum(c["received"] for c in manifest["counts"].values())
    with engine.begin() as conn:
        # Serialize writers for this organization; keeps prior published state intact.
        from sqlalchemy import text
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "refined:" + str(organization_id)})
        existing = conn.execute(select(RefinedCatalogRun.organization_id, RefinedCatalogRun.manifest).where(RefinedCatalogRun.id == run_id)).first()
        if existing:
            if existing.organization_id != organization_id or existing.manifest["output_files"] != manifest["output_files"]:
                raise ValueError("Execução existente pertence a outro escopo ou conteúdo")
            _verify_counts(conn, run_id, expected, received)
            return {"idempotent": True, "items": expected, "raw_records": received}
        conn.execute(insert(RefinedCatalogRun), [{"id": run_id, "organization_id": organization_id,
                                                  "status": "validated", "manifest": manifest}])
        batch = []
        for row in json_lines(directory / "raw_records.jsonl"):
            batch.append({"run_id": run_id, "source_id": row["source_id"], "position": row["position"], "payload": row})
            if len(batch) == 250:
                conn.execute(insert(RefinedCatalogRaw), batch)
                batch.clear()
        if batch:
            conn.execute(insert(RefinedCatalogRaw), batch)
        batch = []
        groups = iter(groupby(json_lines(directory / "attribute_observations.jsonl"), lambda a: a["item_id"]))
        current_id, group = next(groups, (None, iter(())))
        for filename in ["own_items.jsonl", "competitor_items.jsonl"]:
            for item in json_lines(directory / filename):
                attrs = []
                if current_id == item["item_id"]:
                    attrs = list(group)
                    current_id, group = next(groups, (None, iter(())))
                payload = {**item, "attribute_observations": attrs}
                if len(attrs) != item["attribute_count"]:
                    raise ValueError("Atributos não reconciliados com cadastro")
                batch.append({"run_id": run_id, "item_id": uuid.UUID(item["item_id"]), "source_id": item["source_id"],
                              "record_key": item["record_key"], "title_search": item["title_search"],
                              "family_id": item["classification"]["family_id"], "public_catalog": item["public_catalog"], "payload": payload})
                if len(batch) == 250:
                    conn.execute(insert(RefinedCatalogItem), batch)
                    batch.clear()
        if batch:
            conn.execute(insert(RefinedCatalogItem), batch)
        if current_id is not None:
            raise ValueError("Atributos sem cadastro correspondente")
        _verify_counts(conn, run_id, expected, received)
    return {"idempotent": False, "items": expected, "raw_records": received}


def _verify_counts(conn, run_id, expected, received):
    items = conn.scalar(select(func.count()).select_from(RefinedCatalogItem).where(RefinedCatalogItem.run_id == run_id))
    raw = conn.scalar(select(func.count()).select_from(RefinedCatalogRaw).where(RefinedCatalogRaw.run_id == run_id))
    if items != expected or raw != received:
        raise ValueError("Contagem SQL não reconciliada")


def publish_database(engine, organization_id, run_id):
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "refined:" + str(organization_id)})
        row = conn.execute(select(RefinedCatalogRun).where(RefinedCatalogRun.id == run_id, RefinedCatalogRun.organization_id == organization_id)).first()
        if not row:
            raise ValueError("Execução não pertence à organização")
        if any(c.get("quarantine", 0) for c in row.manifest["counts"].values()):
            raise ValueError("Quarentena pendente")
        _verify_counts(conn, run_id, sum(c["accepted"] for c in row.manifest["counts"].values()), sum(c["received"] for c in row.manifest["counts"].values()))
        conn.execute(update(RefinedCatalogRun).where(RefinedCatalogRun.organization_id == organization_id, RefinedCatalogRun.status == "published").values(status="archived"))
        conn.execute(update(RefinedCatalogRun).where(RefinedCatalogRun.id == run_id).values(status="published", published_at=datetime.now(timezone.utc)))


def group_families(manifest, group):
    """Os três grupos seguem exatamente o denominador dos gráficos públicos."""
    own = {key for key, value in manifest["families"].items()
           if key != "unknown" and value["public_counts"].get("portwell", 0) + value["public_counts"].get("choice", 0)}
    if group == "shared":
        return sorted(own)
    if group == "not_found":
        return sorted(set(manifest["families"]) - own - {"unknown"})
    if group == "review":
        return ["unknown"]
    return None


def list_refined_items(conn, organization_id, *, source="", family="", search="", page=1, internal=False, group=""):
    manifest = database_manifest(conn, organization_id)
    if not manifest:
        return None
    conditions = [RefinedCatalogItem.run_id == manifest["run_id"]]
    if source in ORDER:
        conditions.append(RefinedCatalogItem.source_id == source)
    elif source == "own":
        conditions.append(RefinedCatalogItem.source_id.in_(["portwell", "choice"]))
    families = group_families(manifest, group)
    if families is not None:
        conditions.append(RefinedCatalogItem.family_id.in_(families))
        conditions.append(RefinedCatalogItem.source_id.in_(["eco", "dimensional"]))
    if group == "quality_review":
        conditions.append(func.jsonb_array_length(RefinedCatalogItem.payload["quality_issues"]) > 0)
    if family:
        conditions.append(RefinedCatalogItem.family_id == family)
    if not internal:
        conditions.append(RefinedCatalogItem.public_catalog.is_(True))
    for token in plain(search[:200]).split()[:8]:
        conditions.append(RefinedCatalogItem.title_search.contains(token, autoescape=True))
    total = conn.scalar(select(func.count()).select_from(RefinedCatalogItem).where(*conditions))
    pages = max(1, (total + 99) // 100)
    page = max(1, min(page, pages))
    order = case({source: index for index, source in enumerate(ORDER)}, value=RefinedCatalogItem.source_id, else_=99)
    items = conn.scalars(select(RefinedCatalogItem.payload).where(*conditions).order_by(order, RefinedCatalogItem.title_search, RefinedCatalogItem.item_id).limit(100).offset((page - 1) * 100)).all()
    return {"items": items, "manifest": manifest, "total": total, "pages": pages, "page": page,
            "source": source, "family": family, "search": search[:200], "internal": internal, "group": group}


def current_items(conn, organization_id, ids, *, run_id=None, internal=False):
    manifest = database_manifest(conn, organization_id)
    if not manifest:
        raise LookupError("Não há base atual publicada.")
    if run_id and manifest["run_id"] != run_id:
        raise ValueError("A base publicada mudou. Volte ao catálogo e selecione os produtos novamente.")
    conditions = [RefinedCatalogItem.run_id == manifest["run_id"], RefinedCatalogItem.item_id.in_(ids)]
    if not internal:
        conditions.append(RefinedCatalogItem.public_catalog.is_(True))
    items = conn.scalars(select(RefinedCatalogItem.payload).where(*conditions)).all()
    if {i["item_id"] for i in items} != {str(i) for i in ids}:
        raise LookupError("Um dos produtos não está disponível na base atual desta organização.")
    return sorted(items, key=lambda i: (ORDER.index(i["source_id"]), i["title_search"], i["item_id"]))


def current_comparison(items):
    """Matriz exploratória: preserva repetidos, escopos, unidades e conflitos."""
    rows = {}
    for item in items:
        for attr in item["attribute_observations"]:
            discriminator = plain(attr["raw_name"]) if attr["attribute_code"].startswith("unmapped.") else ""
            key = (attr["attribute_code"], attr["configuration_scope"], attr.get("unit") or "", discriminator)
            row = rows.setdefault(key, {"label": attr.get("canonical_label", attr["raw_name"]), "scope": key[1], "unit": key[2], "values": {}})
            row["values"].setdefault(item["item_id"], []).append({"raw": attr["raw_value"], "name": attr["raw_name"], "normalized": attr.get("normalized_value"), "state": attr["knowledge_state"]})
    return {"items": items, "rows": [rows[k] for k in sorted(rows)]}
