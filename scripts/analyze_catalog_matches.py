import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Brand, CatalogMatch, CatalogMatchRun, Company, Offer
from app.services.catalog_matching import ALGORITHM_VERSION, MatchOffer, match_catalogs


def load_offers(
    db: Session,
    *,
    organization_id,
    own: bool,
    competitor_code: str | None = None,
) -> list[MatchOffer]:
    statement = (
        select(
            Offer.id,
            Offer.company_id,
            Company.code,
            Company.name,
            Offer.external_code,
            Offer.name_raw,
            Brand.canonical_name.label("brand_name"),
            Offer.manufacturer_code,
            Offer.reference,
            Offer.description_display,
            Offer.category_raw,
        )
        .join(Company, Company.id == Offer.company_id)
        .outerjoin(Brand, Brand.id == Offer.brand_id)
        .where(
            Offer.active.is_(True),
            Offer.excluded_from_analytics.is_(False),
            Offer.organization_id == organization_id,
            Company.active.is_(True),
            Company.company_type == ("nossa" if own else "concorrente"),
        )
        .order_by(Company.name, Offer.external_code)
    )
    if competitor_code:
        statement = statement.where(Company.code == competitor_code)
    return [
        MatchOffer(
            id=row.id,
            company_id=row.company_id,
            company_code=row.code,
            company_name=row.name,
            external_code=row.external_code,
            name=row.name_raw,
            brand=row.brand_name,
            manufacturer_code=row.manufacturer_code,
            reference=row.reference,
            description=row.description_display,
            category=row.category_raw,
        )
        for row in db.execute(statement)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia correspondências sem alterar o banco.")
    parser.add_argument("--company", default="eco-automacao")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--minimum-score", type=float, default=0.38)
    parser.add_argument("--suggested-score", type=float, default=0.68)
    parser.add_argument(
        "--commit", action="store_true", help="Persiste uma nova execução e seus candidatos."
    )
    args = parser.parse_args()

    with Session(get_engine()) as db:
        competitor_company = db.scalar(
            select(Company).where(
                Company.code == args.company,
                Company.company_type == "concorrente",
                Company.active.is_(True),
            )
        )
        if competitor_company is None:
            raise SystemExit("Empresa concorrente não encontrada.")
        organization_id = competitor_company.organization_id
        own = load_offers(db, organization_id=organization_id, own=True)
        competitors = load_offers(
            db,
            organization_id=organization_id,
            own=False,
            competitor_code=args.company,
        )
    if args.limit:
        competitors = competitors[: args.limit]
    own_by_id = {offer.id: offer for offer in own}
    competitor_by_id = {offer.id: offer for offer in competitors}
    matches = match_catalogs(
        competitors,
        own,
        minimum_score=args.minimum_score,
        suggested_score=args.suggested_score,
    )
    top_matches = [match for match in matches if match.rank == 1]
    suggested = [match for match in top_matches if match.suggested]
    distribution = Counter(int(match.score * 10) / 10 for match in top_matches)
    print(f"own_offers={len(own)} competitor_offers={len(competitors)}")
    print(f"candidate_top1={len(top_matches)} suggested={len(suggested)}")
    print(
        f"suggested_coverage={len(suggested) * 100 / len(competitors):.2f}%"
        if competitors
        else "suggested_coverage=0.00%"
    )
    print(f"score_distribution={dict(sorted(distribution.items()))}")
    for match in sorted(top_matches, key=lambda item: item.score, reverse=True)[:30]:
        competitor = competitor_by_id[match.competitor_offer_id]
        own_offer = own_by_id[match.own_offer_id]
        print(
            f"{match.score:.3f} | {competitor.external_code} {competitor.name[:65]}"
            f" -> {own_offer.company_name} {own_offer.external_code} {own_offer.name[:65]}"
            f" | {match.reasons}"
        )
    if args.commit:
        if args.limit:
            raise SystemExit("Não é permitido persistir uma execução parcial com --limit.")
        now = datetime.now(timezone.utc)
        run = CatalogMatchRun(
            organization_id=organization_id,
            competitor_company_id=competitor_company.id,
            algorithm_version=ALGORITHM_VERSION,
            status="completed",
            parameters={
                "minimum_score": args.minimum_score,
                "suggested_score": args.suggested_score,
                "candidate_limit": 3,
            },
            competitor_total=len(competitors),
            candidate_count=len(top_matches),
            suggested_count=len(suggested),
            started_at=now,
            completed_at=now,
        )
        with Session(get_engine()) as db, db.begin():
            db.add(run)
            db.flush()
            db.add_all(
                [
                    CatalogMatch(
                        run_id=run.id,
                        competitor_offer_id=match.competitor_offer_id,
                        own_offer_id=match.own_offer_id,
                        rank=match.rank,
                        score=Decimal(str(match.score)),
                        status="sugerido" if match.suggested else "candidato",
                        reasons=match.reasons,
                    )
                    for match in matches
                ]
            )
            run_id = run.id
        print(f"run_id={run_id} persisted_matches={len(matches)}")


if __name__ == "__main__":
    main()
