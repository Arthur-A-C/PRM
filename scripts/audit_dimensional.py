"""Auditoria read-only da Dimensional: python -m scripts.audit_dimensional --csv CAMINHO."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from app.services.dimensional_csv import audit_dimensional


def main() -> None:
    parser = argparse.ArgumentParser(description="Audita CSV Dimensional sem banco, rede ou publicação")
    parser.add_argument("--csv", type=Path, required=True, help="Arquivo CSV original, não modificado")
    parser.add_argument("--json", type=Path, default=Path("data/analysis/staging/dimensional_audit.json"))
    args = parser.parse_args()
    started = perf_counter()
    report = audit_dimensional(args.csv)
    report["elapsed_seconds"] = round(perf_counter() - started, 3)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.json.with_suffix(args.json.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.json)
    print(f"Dimensional auditada em staging: {report['metrics']['records']} registros; relatório em {args.json}")


if __name__ == "__main__":
    main()
