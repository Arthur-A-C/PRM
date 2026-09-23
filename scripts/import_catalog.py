import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.services.bootstrap import ensure_reference_data
from app.services.catalog_import import parse_catalog, publish_catalog
from app.models import Company


DEFAULT_FILES = {
    "eco-automacao": "produtos_ecoautomacao.xlsx",
    "portwell": "produtos-portwell.xlsx",
    "choice-tech": "produtos-choice.xlsx",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pré-visualiza ou publica um catálogo com rastreabilidade."
    )
    parser.add_argument("--company", choices=sorted(DEFAULT_FILES), required=True)
    parser.add_argument("--file", help="Nome do XLSX dentro de data/imports")
    parser.add_argument("--currency", default="BRL")
    parser.add_argument("--observed-at", help="Data/hora ISO conhecida da observação")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Publica transacionalmente; sem esta opção apenas exibe a prévia.",
    )
    parser.add_argument(
        "--skip-matching",
        action="store_true",
        help="Não recalcula correspondências após uma publicação nova.",
    )
    return parser.parse_args()


def import_path(filename: str) -> Path:
    imports_root = (Path.cwd() / "data" / "imports").resolve()
    path = (imports_root / filename).resolve()
    if path.parent != imports_root:
        raise SystemExit("O arquivo deve estar diretamente em data/imports.")
    return path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    arguments = parse_arguments()
    settings = get_settings()
    path = import_path(arguments.file or DEFAULT_FILES[arguments.company])
    preview = parse_catalog(path, arguments.company, settings)
    summary = preview.summary()
    if arguments.commit:
        summary.pop("sample", None)
        summary.pop("headers", None)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    if not arguments.commit:
        print("Prévia concluída; nenhum dado foi gravado.")
        return

    observed_at = datetime.fromisoformat(arguments.observed_at) if arguments.observed_at else None
    with Session(get_engine()) as db, db.begin():
        _, companies = ensure_reference_data(db, settings)
        result = publish_catalog(
            db,
            preview,
            companies[arguments.company],
            currency=arguments.currency,
            observed_at=observed_at,
        )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str))
    if result.idempotent or arguments.skip_matching:
        return
    with Session(get_engine()) as db:
        competitor_codes = list(
            db.scalars(
                select(Company.code).where(
                    Company.company_type == "concorrente", Company.active.is_(True)
                )
            )
        )
    for competitor_code in competitor_codes:
        print(f"Atualizando correspondências automáticas de {competitor_code}...")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.analyze_catalog_matches",
                "--company",
                competitor_code,
                "--commit",
            ],
            cwd=Path.cwd(),
            check=True,
        )


if __name__ == "__main__":
    main()
