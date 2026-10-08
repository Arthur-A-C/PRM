"""Aceite do lote auditado em 25/09/2026; alterações exigem nova auditoria."""

from pathlib import Path

import pytest

from app.services.catalog_audit import audit_six_files


IMPORTS = Path(__file__).resolve().parents[1] / "data" / "imports"


@pytest.fixture(scope="module")
def report():
    if not (IMPORTS / "produtos-choice.xlsx").is_file():
        pytest.skip("Lote de integração não disponível")
    return audit_six_files(IMPORTS)


def test_reconciliation_and_non_products(report):
    sources = report["sources"]
    assert report["product_rows_per_layer"] == 35_799
    assert all(value["same_code_multiplicity"] for value in report["reconciliation"].values())
    assert (sources["choice_raw"]["header_row"], sources["choice_raw"]["columns"], sources["choice_raw"]["coded_rows"]) == (3, 32, 16_894)
    assert (sources["choice_treated"]["columns"], sources["choice_treated"]["coded_rows"]) == (281, 16_894)
    assert (sources["portwell_raw"]["columns"], sources["portwell_raw"]["coded_rows"], sources["portwell_raw"]["physical_rows"]) == (26, 10_960, 10_961)
    assert (sources["portwell_treated"]["columns"], sources["portwell_treated"]["coded_rows"]) == (121, 10_960)
    assert (sources["eco_raw"]["columns"], sources["eco_raw"]["coded_rows"]) == (8, 7_945)
    assert (sources["eco_treated"]["columns"], sources["eco_treated"]["coded_rows"]) == (256, 7_945)
    assert sources["portwell_raw"]["non_product_rows"] == [{"line": 10963, "first_cell": "Nenhum filtro aplicado"}]
    assert sources["portwell_raw"]["duplicate_codes"] == {"311006000015": 2, "312001000032": 2, "317010000010": 2}
    assert sources["choice_treated"]["case_lines"]["111001000409"] == [2866]
    assert sources["eco_raw"]["case_lines"]["P024190"] == [7939]


def test_fixture_hashes(report):
    expected = {
        "choice_raw": "e5a2eb368f6d40749fd63a6988c48f05552d608f6aed39918146c70036b2eab3",
        "choice_treated": "43c77a20f1aa556ac4f2641c020fec587921ef69359dc5ee2512d816f1392c82",
        "portwell_raw": "083f0f2b290f0316feb2410ab5b471b784c96b961bf6dfab49e828b6a69b74b9",
        "portwell_treated": "cd52a69ed6b1cb9462a13e747cb8a41fa2d3a9ec3024fdce38a09dda0a1b0b63",
        "eco_raw": "1dbb6be1da1f7f89746638ff3214070e2ad9f6ff949321623a8b4cb393ccca5d",
        "eco_treated": "9b4f2b4edd0c83870c8bc8ae7e4712cac1b0b9d0551b1db05f7ca98b5e4d179d",
    }
    assert {key: value["sha256"] for key, value in report["sources"].items()} == expected


def test_commercial_conflicts_and_eco_states(report):
    portwell = report["sources"]["portwell_raw"]
    assert {key: item["lines"] for key, item in portwell["commercial_conflicts"].items()} == {
        "311006000015": [7498, 7499],
        "312001000032": [10430, 10431],
        "317010000010": [10868, 10869],
    }
    assert all(set(item["different_fields"]) == {"indice_mk", "preco_compra"} for item in portwell["commercial_conflicts"].values())
    eco = report["sources"]["eco_raw"]
    assert eco["zero_prices"] == {"pix": 612, "cartao": 612}
    assert eco["availability_counts"] == {
        "Em estoque": 1670, "Fora de estoque": 6221, "https://schema.org/BackOrder": 54,
    }
