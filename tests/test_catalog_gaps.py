import uuid

from app.services.catalog_gaps import GapOffer, summarize_gap_offers


def test_gap_signals_keep_brand_and_family_counts_separate() -> None:
    absent_brand = uuid.uuid4()
    present_brand = uuid.uuid4()
    offers = [
        GapOffer(uuid.uuid4(), "B-02", "Disjuntor dois", absent_brand, "Marca B", "Disjuntor"),
        GapOffer(uuid.uuid4(), "B-01", "Disjuntor um", absent_brand, "Marca B", "Disjuntor"),
        GapOffer(uuid.uuid4(), "P-01", "Sensor", present_brand, "Marca P", "Sensor"),
        GapOffer(uuid.uuid4(), "N-01", "Sem marca", None, None, None),
    ]

    result = summarize_gap_offers(
        offers, {present_brand: 10}, {"Sensor": 3}, example_limit=1
    )

    assert result["summary"] == {
        "unmatched_total": 4,
        "absent_brand_total": 2,
        "absent_brand_groups": 1,
        "family_absent_total": 2,
        "unknown_brand": 1,
        "unknown_family": 1,
    }
    assert result["brands"][0]["name"] == "Marca B"
    assert result["brands"][0]["examples"][0]["code"] == "B-01"
    assert result["families"][0]["name"] == "Disjuntor"
    assert result["families"][0]["own_count"] == 0
    assert result["families"][1]["own_count"] == 3


def test_empty_gap_report_does_not_divide_or_invent_groups() -> None:
    result = summarize_gap_offers([], {}, {})

    assert result["summary"]["unmatched_total"] == 0
    assert result["brands"] == []
    assert result["families"] == []
