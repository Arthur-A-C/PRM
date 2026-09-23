import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Comparison, ComparisonItem
from app.repositories.catalog import comparison_preview


def save_comparison(
    db: Session,
    *,
    organization_id: uuid.UUID,
    creator_id: uuid.UUID,
    title: str,
    offer_ids: list[uuid.UUID],
    reference_offer_id: uuid.UUID | None = None,
    allow_excluded: bool = False,
) -> Comparison:
    preview = comparison_preview(
        db, organization_id, offer_ids, reference_offer_id=reference_offer_id
    )
    if not allow_excluded and any(
        item["excluded_from_analytics"] for item in preview["items"]
    ):
        raise LookupError("Uma oferta não foi encontrada.")
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Informe um título para a comparação.")
    if len(clean_title) > 255:
        raise ValueError("O título deve ter no máximo 255 caracteres.")
    comparison = Comparison(
        id=uuid.uuid4(),
        organization_id=organization_id,
        creator_id=creator_id,
        reference_offer_id=reference_offer_id,
        title=clean_title,
        mode="exploratoria",
        equivalence_status="nao_avaliado",
        filters_snapshot={},
    )
    db.add(comparison)
    for position, item in enumerate(preview["items"], start=1):
        db.add(
            ComparisonItem(
                id=uuid.uuid4(),
                comparison_id=comparison.id,
                offer_id=item["id"],
                position=position,
            )
        )
    return comparison


def get_saved_comparison(
    db: Session,
    *,
    organization_id: uuid.UUID,
    comparison_id: uuid.UUID,
) -> dict | None:
    comparison = db.scalar(
        select(Comparison).where(
            Comparison.id == comparison_id,
            Comparison.organization_id == organization_id,
        )
    )
    if comparison is None:
        return None
    item_ids = list(
        db.scalars(
            select(ComparisonItem.offer_id)
            .where(ComparisonItem.comparison_id == comparison.id)
            .order_by(ComparisonItem.position)
        )
    )
    preview = comparison_preview(
        db,
        organization_id,
        item_ids,
        reference_offer_id=comparison.reference_offer_id,
    )
    return {
        **preview,
        "id": comparison.id,
        "title": comparison.title,
        "creator_id": comparison.creator_id,
        "mode": comparison.mode,
        "equivalence_status": comparison.equivalence_status,
        "conclusion": comparison.conclusion,
        "created_at": comparison.created_at,
        "updated_at": comparison.updated_at,
    }
