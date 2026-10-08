"""Simula a Dimensional: python -m scripts.stage_dimensional --csv data/imports/produtos_dimensional.csv."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from app.services.dimensional_stage import simulate_dimensional


def main() -> None:
    parser = argparse.ArgumentParser(description="Simula regras Dimensional sem publicar ofertas")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=Path("data/analysis/staging/dimensional_simulation.json"))
    args = parser.parse_args()
    started = perf_counter()
    report = simulate_dimensional(args.csv)
    report["elapsed_seconds"] = round(perf_counter() - started, 3)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.json.with_suffix(args.json.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.json)
    print(f"Simulação concluída: {report['metrics']['records']} registros; {report['published_offers']} publicados")


if __name__ == "__main__":
    main()
