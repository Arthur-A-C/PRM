"""Auditoria read-only: python -m scripts.audit_catalog_pipeline [--json CAMINHO]."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.catalog_audit import audit_six_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Audita os seis XLSX sem importar ou publicar")
    parser.add_argument("--imports", type=Path, default=Path("data/imports"))
    parser.add_argument("--json", type=Path, help="Saída JSON em staging; não altera o banco")
    args = parser.parse_args()
    report = audit_six_files(args.imports)
    formatted = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.json.with_suffix(args.json.suffix + ".tmp")
        temporary.write_text(formatted + "\n", encoding="utf-8")
        temporary.replace(args.json)
        print(f"Auditoria de staging salva em {args.json}")
    else:
        print(formatted)


if __name__ == "__main__":
    main()
