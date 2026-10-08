"""Reconcile normalized CSV exports to current PRM offers without DB writes.

The externally supplied normalizar_catalogos.py is not executed here.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_engine
from app.services.comparable_snapshot import (
    SNAPSHOT_PATH,
    build_snapshot,
    published_offer_codes,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path, help="base_comparavel.csv")
    parser.add_argument("attributes", type=Path, help="atributos_normalizados_long.csv")
    parser.add_argument("--output", type=Path, default=SNAPSHOT_PATH)
    args = parser.parse_args()
    with Session(get_engine()) as db:
        organizations = db.execute(text("SELECT id FROM organizations ORDER BY id")).scalars().all()
        if len(organizations) != 1:
            raise SystemExit("Este retrato exige exatamente uma organização; selecione a organização antes de publicar.")
        snapshot = build_snapshot(args.base, args.attributes, published_offer_codes(db))
        snapshot["organization_id"] = str(organizations[0])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=args.output.parent, prefix=".comparable-",
                                         suffix=".json", delete=False) as target:
            temporary = Path(target.name)
            target.write(payload)
        os.replace(temporary, args.output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(json.dumps({"output": str(args.output), "totals": snapshot["totals"],
                      "quality": snapshot["quality"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
