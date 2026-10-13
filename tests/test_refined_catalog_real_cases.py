"""Integração opcional com os arquivos locais recebidos, nunca com produção."""

from pathlib import Path

import pytest

from app.services.refined_catalog import ARCHIVE, iter_records, load_policy, normalize_record


def archived(name):
    candidates = list(ARCHIVE.glob("*/" + name))
    if not candidates:
        pytest.skip("Arquivo de referência local não disponível")
    return candidates[0]


def test_real_choice_identifiers_variants_and_power():
    wanted = {"codmaterialaqui", "113004000109", "113004000119", "113004000121", "112011000174", "112011000214"}
    records = {r["raw"]["SKU"]: r for r in iter_records(archived("produtos-choice.csv"), "choice") if r["raw"].get("SKU") in wanted}
    assert set(records) == wanted
    items = {}
    for sku, row in records.items():
        item, attrs = normalize_record(row, "choice", load_policy(), "real-case")
        items[sku] = item
        if sku.startswith("113004"):
            assert any(a["knowledge_state"] == "conflicting" and a.get("resolution_proposal") for a in attrs)
    assert items["codmaterialaqui"]["record_key"] == "6260"
    assert items["112011000174"]["item_id"] != items["112011000214"]["item_id"]
    assert items["112011000174"]["title_original"] == items["112011000214"]["title_original"]


def test_real_portwell_network_and_usb_conflicts():
    ethernet, usb_exact, usb_other = 0, 0, 0
    for row in iter_records(archived("produtos-portwell.csv"), "portwell"):
        _, attrs = normalize_record(row, "portwell", load_policy(), "real-case")
        ethernet += any("ethernet_speed_conflict" in a["issues"] for a in attrs)
        for attr in attrs:
            if "ambiguous_usb_quantities" in attr["issues"]:
                if attr["raw_value"] == "2x USB 2.0, 2x USB 3.0, 4x USB 2.0, 4x USB 3.0":
                    usb_exact += 1
                else:
                    usb_other += 1
    assert ethernet == 29 and usb_exact == 39
    # Outros dois cadastros também repetem versões com contagens ambíguas.
    assert usb_other == 2


def test_real_eco_model_truncation_preserved():
    row = next(r for r in iter_records(archived("Produtos_ECO_Tratados_PRM.xlsx"), "eco") if r["raw"]["Codigo_ECO"] == "P002212")
    item, _ = normalize_record(row, "eco", load_policy(), "real-case")
    assert item["model_claimed"] == "DILM38-10(RDC24"
    assert "model_unbalanced_parentheses" in item["quality_issues"]
    assert item["technical_match_status"] == "not_assessed"
