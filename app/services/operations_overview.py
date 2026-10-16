"""Read-only view of persisted digitalization runs for the dashboard.

Only facts written by `digitalization_storage` are reported: draft creation
(technical analysis + datasheet), approval and validated package. CSV and
WooCommerce steps have no persisted record, so they are reported as untracked
instead of being inferred. Paths and analysis contents are never exposed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.digitalization_storage import COMPANIES, RUN_ID_RE, storage_root

STATUSES = {"draft", "approved", "validated"}
MAX_RUNS = 2000


def _timestamp(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _item(record: dict) -> dict | None:
    run_id = record.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        return None
    status = record.get("status")
    created = _timestamp(record.get("created_at"))
    if status not in STATUSES or record.get("company") not in COMPANIES or created is None:
        return None
    manifest = record.get("manifest") if isinstance(record.get("manifest"), dict) else {}
    return {
        "run_id": run_id,
        "company": record["company"],
        "sku": str(record.get("sku", "")),
        "name": str(record.get("name", "")),
        "status": status,
        "created_at": created,
        "approved_at": _timestamp(record.get("approved_at")),
        "validated_at": _timestamp(manifest.get("generated_at")) if status == "validated" else None,
        "image_count": int(record.get("image_count") or 0),
        "warnings": len(record.get("warnings") or []),
        "pending": len(record.get("pending") or []),
        "pending_acknowledged": bool(record.get("pending_acknowledged")),
        "package_version": record.get("package_version") if status == "validated" else None,
    }


def operations_overview(root: Path | None = None) -> dict:
    base = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "tracked_stages": ["draft", "approved", "validated"], "untracked_stages": ["csv", "woocommerce"],
            "failures_tracked": False, "items": [], "unreadable": 0, "truncated": False}
    try:
        runs = (root or storage_root()) / "_runs"
    except ValueError:
        return {**base, "status": "storage_misconfigured"}
    if not runs.is_dir():
        return {**base, "status": "no_runs"}
    folders = sorted((p for p in runs.iterdir() if p.is_dir() and RUN_ID_RE.fullmatch(p.name)),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    items, unreadable = [], 0
    for folder in folders[:MAX_RUNS]:
        try:
            item = _item(json.loads((folder / "record.json").read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            item = None
        if item is None or item["run_id"] != folder.name:
            unreadable += 1
            continue
        items.append(item)
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {**base, "status": "ok" if items else "no_runs", "items": items,
            "unreadable": unreadable, "truncated": len(folders) > MAX_RUNS}
