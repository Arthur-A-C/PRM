"""Leitura do último relatório de auditoria em staging; nunca publica dados."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


AUDIT_REPORT = Path("data/analysis/staging/audit_20260925.json")


def load_staging_audit(path: Path = AUDIT_REPORT) -> dict[str, Any] | None:
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if report.get("audit_version") != "1" or report.get("mode") != "read_only_staging":
        return None
    if not isinstance(report.get("sources"), dict) or not isinstance(report.get("reconciliation"), dict):
        return None
    return report
