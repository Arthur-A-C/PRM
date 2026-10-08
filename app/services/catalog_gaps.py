"""Sinais de lacuna: ausência de candidato não prova ausência de equivalente."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class GapOffer:
    id: uuid.UUID
    code: str
    name: str
    brand_id: uuid.UUID | None
    brand_name: str | None
    family: str | None


def summarize_gap_offers(
    offers: Sequence[GapOffer],
    own_brand_counts: Mapping[uuid.UUID, int],
    own_family_counts: Mapping[str, int],
    *,
    group_limit: int = 8,
    example_limit: int = 3,
) -> dict:
    """Agrupa ofertas sem candidato por marca ausente e família tratada.

    Uma oferta pode aparecer nos dois grupos; os totais nunca são somados.
    """
    brand_groups: dict[uuid.UUID, list[GapOffer]] = defaultdict(list)
    family_groups: dict[str, list[GapOffer]] = defaultdict(list)
    unknown_brand = unknown_family = 0
    family_absent_total = 0
    for offer in offers:
        if offer.brand_id is None or not offer.brand_name:
            unknown_brand += 1
        elif own_brand_counts.get(offer.brand_id, 0) == 0:
            brand_groups[offer.brand_id].append(offer)
        if offer.family and offer.family.strip():
            family = offer.family.strip()
            family_groups[family].append(offer)
            if own_family_counts.get(family, 0) == 0:
                family_absent_total += 1
        else:
            unknown_family += 1

    def examples(members: list[GapOffer]) -> list[dict]:
        return [
            {"id": item.id, "code": item.code, "name": item.name}
            for item in sorted(members, key=lambda item: (item.code, item.name))[:example_limit]
        ]

    brands = [
        {
            "key": str(brand_id),
            "name": members[0].brand_name,
            "unmatched_count": len(members),
            "own_count": 0,
            "examples": examples(members),
        }
        for brand_id, members in brand_groups.items()
    ]
    brands.sort(key=lambda item: (-item["unmatched_count"], item["name"].casefold()))
    families = [
        {
            "key": family,
            "name": family,
            "unmatched_count": len(members),
            "own_count": own_family_counts.get(family, 0),
            "examples": examples(members),
        }
        for family, members in family_groups.items()
    ]
    families.sort(key=lambda item: (-item["unmatched_count"], item["name"].casefold()))
    return {
        "summary": {
            "unmatched_total": len(offers),
            "absent_brand_total": sum(len(members) for members in brand_groups.values()),
            "absent_brand_groups": len(brand_groups),
            "family_absent_total": family_absent_total,
            "unknown_brand": unknown_brand,
            "unknown_family": unknown_family,
        },
        "brands": brands[:group_limit],
        "families": families[:group_limit],
        "brand_options": [
            {"key": item["key"], "name": item["name"], "count": item["unmatched_count"]}
            for item in brands
        ],
        "family_options": [
            {"key": item["key"], "name": item["name"], "count": item["unmatched_count"]}
            for item in families
        ],
        "brand_group_total": len(brands),
        "family_group_total": len(families),
    }
