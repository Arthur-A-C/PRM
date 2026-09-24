"""Associa as saídas tratadas do PRM_Pipeline às ofertas originais."""

import argparse
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import Company, Offer, OfferEnrichment
from app.services.catalog_import import file_sha256
from app.services.catalog_treatment import iter_treated_xlsx, product_content_sha256


DEFAULT_FILES = {
    "choice-tech": "Produtos-Choice.xlsx",
    "portwell": "Produtos-Portwell.xlsx",
    "eco-automacao": "Produtos-ECO.xlsx",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prévia ou publicação do enriquecimento técnico de um catálogo.")
    parser.add_argument("--company", required=True, choices=sorted(DEFAULT_FILES))
    parser.add_argument("--file", type=Path, help="XLSX tratado; padrão: data/imports/treated/<empresa>.")
    parser.add_argument("--commit", action="store_true", help="Grava o enriquecimento e atualiza a análise.")
    parser.add_argument("--skip-matching", action="store_true", help="Adia o recálculo para publicar vários arquivos em sequência.")
    args = parser.parse_args()
    path = args.file or Path("data/imports/treated") / DEFAULT_FILES[args.company]
    path = path.resolve()
    if not path.is_file():
        raise SystemExit(f"Arquivo tratado não encontrado: {path}")
    settings = get_settings()
    if path.stat().st_size > settings.max_upload_mib * 1024 * 1024:
        raise SystemExit("Arquivo tratado excede o limite configurado.")
    rows = list(iter_treated_xlsx(path, args.company, max_rows=settings.max_import_rows))
    digest = file_sha256(path)
    with Session(get_engine()) as db:
        company = db.scalar(select(Company).where(Company.code == args.company, Company.active.is_(True)))
        if company is None:
            raise SystemExit("Empresa não cadastrada.")
        organization_id = company.organization_id
        offers = {offer.external_code: offer for offer in db.scalars(select(Offer).where(Offer.company_id == company.id))}
        existing = {
            entry.offer_id: entry for entry in db.scalars(
                select(OfferEnrichment)
                .join(Offer, Offer.id == OfferEnrichment.offer_id)
                .where(Offer.company_id == company.id)
            )
        }
        known = {row.code for row in rows if row.code in offers}
        duplicate_codes = len(rows) - len({row.code for row in rows})
        unknown = len({row.code for row in rows if row.code not in offers})
        print(f"company={args.company} source={path.name} sha256={digest}")
        print(f"rows={len(rows)} matched_offers={len(known)} unknown_codes={unknown} duplicate_codes={duplicate_codes}")
        if not rows or len(known) / len({row.code for row in rows}) < 0.90:
            raise SystemExit("Correspondência de códigos abaixo de 90%; confira empresa e arquivo.")
        if not args.commit:
            print("Prévia concluída; banco não alterado.")
            return
        created = updated = unchanged = 0
        seen = set()
        for row in rows:
            if row.code in seen or row.code not in offers:
                continue
            seen.add(row.code)
            offer = offers[row.code]
            content_digest = product_content_sha256(
                name=offer.name_raw, manufacturer_code=offer.manufacturer_code,
                reference=offer.reference, description=offer.description_raw,
                application=offer.application_raw, brand=offer.brand_raw,
                category=offer.category_raw,
            )
            enrichment = existing.get(offer.id)
            if enrichment and enrichment.source == "pipeline" and enrichment.source_sha256 == digest and enrichment.content_sha256 == content_digest:
                unchanged += 1
                continue
            if enrichment is None:
                enrichment = OfferEnrichment(id=uuid.uuid4(), offer_id=offer.id)
                db.add(enrichment)
                created += 1
            else:
                updated += 1
            treatment = row.treatment
            enrichment.source = "pipeline"
            enrichment.source_filename = path.name[:255]
            enrichment.source_sha256 = digest
            enrichment.source_row = row.row_number
            enrichment.content_sha256 = content_digest
            enrichment.family = treatment.family
            enrichment.family_group = treatment.family_group
            enrichment.model_reference = treatment.model_reference
            enrichment.normalized_title = treatment.normalized_title
            enrichment.search_codes = treatment.search_codes
            enrichment.attributes = treatment.attributes
            enrichment.confidence = treatment.confidence
        db.commit()
    print(f"created={created} updated={updated} unchanged={unchanged}")
    if not args.skip_matching and (created or updated):
        with Session(get_engine()) as db:
            competitor_codes = list(db.scalars(
                select(Company.code).where(
                    Company.organization_id == organization_id,
                    Company.company_type == "concorrente", Company.active.is_(True),
                )
            ))
        for competitor_code in competitor_codes:
            subprocess.run(
                [sys.executable, "-m", "scripts.analyze_catalog_matches", "--company", competitor_code, "--commit"],
                check=True,
            )


if __name__ == "__main__":
    main()
