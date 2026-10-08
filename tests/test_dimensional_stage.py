"""A simulação completa não publica e só emite afirmações com trecho literal."""

from pathlib import Path

import pytest

from app.services.dimensional_stage import simulate_dimensional


CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "imports" / "produtos_dimensional.csv"


@pytest.mark.skipif(not CSV_PATH.is_file(), reason="CSV Dimensional local indisponível")
def test_full_dry_run_preserves_all_skus_and_has_no_unproven_evidence():
    report = simulate_dimensional(CSV_PATH)
    assert report["mode"] == "dry_run_staging"
    assert report["source_sha256"] == "8ad7e0e63e265aa6ebfd34b06a530dc000177c11602c2a6920e80add3e211528"
    assert report["metrics"]["records"] == report["metrics"]["distinct_skus"] == 77_965
    assert report["metrics"]["trusted_stock_unknown"] == 77_965
    assert report["warnings"].get("evidence_not_literal", 0) == 0
    assert report["warnings"].get("duplicate_sku", 0) == 0
    assert report["published_offers"] == report["automatic_equivalences"] == 0
    assert report["cases"]["435197"]["blocked_fields"] == ["coil.voltage"]
    assert report["cases"]["1298390"]["form_factor"] == "panel_pc"
