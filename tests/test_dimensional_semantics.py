"""Regressões técnicas da Dimensional: propostas rastreáveis, sem equivalência automática."""

from pathlib import Path

import pytest

from app.services.dimensional_csv import DimensionalCsvAdapter
from app.services.dimensional_semantics import analyze_dimensional


CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "imports" / "produtos_dimensional.csv"
WANTED = {"1053625", "1053629", "197090", "197354", "1401334", "1298390", "878767", "1302674", "1302675", "435197", "1267587", "1405472", "355604", "302805", "243665", "84600", "172167", "1290750", "198183"}


@pytest.fixture(scope="module")
def analyses():
    if not CSV_PATH.is_file():
        pytest.skip("CSV local indisponível")
    return {source.raw["sku"]: analyze_dimensional(source) for source in DimensionalCsvAdapter().iter_source_records(CSV_PATH) if source.raw["sku"] in WANTED}


def test_shoe_and_tape_page_level_values_do_not_override_variant(analyses):
    assert set(analyses["1053625"].values("shoe.size")) == {35}
    assert set(analyses["1053629"].values("shoe.size")) == {35, 39}
    assert "shoe.size" in analyses["1053629"].blocked_fields
    assert set(analyses["197090"].values("tape.length_m")) == {20}
    assert set(analyses["197354"].values("tape.length_m")) == {10, 20}
    assert set(analyses["197354"].values("tape.rating_v")) == {600, 750}
    assert {"tape.length_m", "tape.rating_v", "manufacturer_part_candidate"}.issubset(analyses["197354"].blocked_fields)


def test_formula_is_invalid_but_description_can_propose_input(analyses):
    result = analyses["1401334"]
    assert result.family == "power_supply"
    assert [100, 240] in result.values("power.input_range_vac")
    assert any(item.state == "invalid" and "_xlfn." in item.evidence for item in result.assertions)
    assert not result.values("ups.function")
    assert any(item.state == "invalid" and item.attribute == "ean" for item in result.assertions)


def test_pc_inside_ihm_has_panel_evidence_without_converting_operator_panel(analyses):
    pc = analyses["1298390"]
    assert (pc.family, pc.form_factor) == ("industrial_computer", "panel_pc")
    assert pc.values("memory.installed_gb") == [4]
    assert pc.values("display.diagonal_in") == [15]
    assert pc.values("power.input_vdc") == [24]
    assert pc.values("os.included") == [False]
    assert pc.values("manufacturer_part_candidate") == ["6AV72411BA302AA0"]
    assert analyses["878767"].family != "industrial_computer"


def test_contactor_accessories_and_coil_conflict(analyses):
    for sku in ("1302674", "1302675"):
        assert (analyses[sku].family, analyses[sku].role) == ("contact_auxiliary", "accessory")
    contactor = analyses["435197"]
    assert contactor.family == "contactor"
    assert "coil.voltage" in contactor.blocked_fields
    assert {value["value"] for value in contactor.values("coil.voltage")} == {125, 220}


def test_switch_variants_and_negation(analyses):
    conflict = analyses["1267587"]
    assert conflict.family == "network_switch"
    assert "switch.platform_model" in conflict.blocked_fields
    assert "switch.rj45_declared" in conflict.blocked_fields
    assert analyses["1405472"].values("switch.managed") == [False]
    assert 5 in analyses["1405472"].values("switch.rj45_declared")
    assert [10, 100] in analyses["1405472"].values("switch.ethernet_speeds_mbps")


def test_cable_dimensions_and_wrong_column_document(analyses):
    copper = analyses["355604"]
    assert copper.family == "industrial_cable"
    assert "cable.cross_section" in copper.blocked_fields
    assert not copper.values("cable.cross_section")
    optical = analyses["302805"]
    assert "optical_fiber" in optical.values("cable.medium")
    assert not optical.values("cable.cross_section")
    wrong_column = analyses["243665"]
    assert any(item["source_column"] == "ncm" and item["kind"] == "document_candidate" for item in wrong_column.resources)
    assert analyses["84600"].values("ncm_declared") == ["85044090"]
    assert analyses["172167"].values("ncm_declared") == ["85381000"]
    assert analyses["1290750"].values("ncm_declared") == ["85364900"]
    assert analyses["198183"].values("ncm_declared") == ["85389090"]
