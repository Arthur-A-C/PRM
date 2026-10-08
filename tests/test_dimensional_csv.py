"""Auditoria e identidade da Dimensional ancoradas no lote recebido."""

from pathlib import Path

import pytest

from app.services.dimensional_csv import (
    DimensionalCsvAdapter,
    DimensionalLayoutError,
    SourceRecord,
    audit_dimensional,
    parse_announced_price,
    specification_pairs,
    valid_gtin,
)


CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "imports" / "produtos_dimensional.csv"


@pytest.fixture(scope="module")
def audit():
    if not CSV_PATH.is_file():
        pytest.skip("CSV Dimensional local indisponível")
    return audit_dimensional(CSV_PATH)


@pytest.fixture(scope="module")
def cases():
    if not CSV_PATH.is_file():
        pytest.skip("CSV Dimensional local indisponível")
    wanted = {"1053625", "1053629", "1053630", "1053631", "1053632", "1053633", "1053634", "197090", "197354", "238950", "238948", "1401334", "1440301", "1440302", "1414941", "1272256", "1197342", "1290038", "243665", "84600", "172167", "1290750", "198183", "1298390", "878767", "1302674", "1302675", "435197", "1267587", "1405472", "1184211"}
    return {source.raw["sku"]: source for source in DimensionalCsvAdapter().iter_source_records(CSV_PATH) if source.raw["sku"] in wanted}


def test_physical_csv_audit_reconciles_all_records(audit):
    assert audit["sha256"] == "8ad7e0e63e265aa6ebfd34b06a530dc000177c11602c2a6920e80add3e211528"
    assert (audit["size_bytes"], audit["physical_lines"], audit["header_fields"]) == (140_518_094, 261_622, 20)
    assert (audit["metrics"]["records"], audit["distinct_skus"], audit["distinct_product_ids"]) == (77_965, 77_965, 77_957)
    assert audit["duplicate_skus"] == {}
    assert audit["repeated_product_ids"] == {"1053625": 7, "197090": 2, "238948": 2}
    assert audit["metrics"]["product_id_differs_from_sku"] == 15
    assert audit["metrics"]["whole_record_duplicates"] == 0
    assert (audit["distinct_brands"], audit["distinct_categories"], len(audit["domains"])) == (210, 117, 9)
    assert audit["distinct_specification_labels"] == 284


def test_quality_counts_are_not_silently_reinterpreted(audit):
    m = audit["metrics"]
    expected = {
        "specifications_empty": 40527, "specifications_media_only": 2454,
        "no_specification_or_descriptions": 1717, "short_description_empty": 22062,
        "full_description_empty": 2349, "ean_empty": 12448, "ean_invalid": 112,
        "ncm_empty": 13631, "ncm_invalid": 126, "ncm_url": 122,
        "reference_scientific": 320, "reference_equals_sku": 9703,
        "reference_placeholder": 55, "formula_in_specifications": 6,
        "datasheet_empty": 33115, "local_images_empty": 77965,
        "price_zero_or_invalid": 31, "reference_price_zero_or_invalid": 31,
        "positive_announced_price": 77934, "prices_equal_raw": 75171,
        "price_below_reference": 2794,
    }
    assert {key: m[key] for key in expected} == expected
    assert audit["ean_shared_groups"] == 777
    assert audit["ean_example_7909492067382"] == 108
    assert audit["stock"] == {"99999": 65600, "100": 5213, "10": 5007, "1": 2113, "0": 32}
    assert sum(audit["availability"].values()) == 77965


def test_variant_identity_is_sku_not_product_id_url_or_title(cases):
    shoes = [cases[sku] for sku in ("1053625", "1053629", "1053630", "1053631", "1053632", "1053633", "1053634")]
    assert len({item.raw["sku"] for item in shoes}) == 7
    assert len({item.raw["product_id"] for item in shoes}) == 1
    assert len({item.raw["url"] for item in shoes}) == 1
    assert cases["197090"].raw["product_id"] == cases["197354"].raw["product_id"]
    assert cases["238950"].raw["nome"] == cases["238948"].raw["nome"]
    assert cases["238950"].raw["sku"] != cases["238948"].raw["sku"]


def test_original_multiline_and_commercial_semantics(cases):
    source = cases["1401334"]
    assert source.number == 2575
    assert source.last_physical_line > source.first_physical_line
    mapped = DimensionalCsvAdapter().map_record(source)
    assert mapped.external_code == "1401334" and mapped.seller_code == "dimensional"
    assert mapped.trusted_stock_quantity is None
    assert {"ean_invalido", "formula_textual_invalida"}.issubset(mapped.warnings)
    assert mapped.price == mapped.reference_price
    unavailable = DimensionalCsvAdapter().map_record(cases["1184211"])
    assert unavailable.availability_raw != "Em estoque" and unavailable.price == parse_announced_price("231.1")
    assert unavailable.reference_price != unavailable.price


def test_identifiers_and_specification_parser_preserve_evidence(cases):
    assert not valid_gtin("4,03E12")
    assert valid_gtin("7909492067382")  # checksum não prova identidade do produto
    assert "referencia_cientifica_suspeita" in DimensionalCsvAdapter().map_record(cases["1290038"]).warnings
    assert "ncm_invalido" in DimensionalCsvAdapter().map_record(cases["243665"]).warnings
    pairs = specification_pairs("Acessórios de:: Controlador Lógico | Modelo: X | Modelo: Y | imagem-360: https://example.test/a:b")
    assert pairs == [("Acessórios de", ": Controlador Lógico"), ("Modelo", "X"), ("Modelo", "Y"), ("imagem-360", "https://example.test/a:b")]


def test_all_six_formula_cells_remain_invalid_text(cases):
    adapter = DimensionalCsvAdapter()
    for sku in ("1401334", "1440301", "1440302", "1414941", "1272256", "1197342"):
        assert "formula_textual_invalida" in adapter.map_record(cases[sku]).warnings
        assert "_xlfn." in cases[sku].raw["especificacoes"]


def test_layout_missing_field_blocks_and_new_field_is_preserved():
    adapter = DimensionalCsvAdapter()
    with pytest.raises(DimensionalLayoutError):
        adapter.validate_layout(["sku", "nome"])
    assert adapter.validate_layout(list(adapter_headers()) + ["campo_novo"])["extra"] == ["campo_novo"]


def adapter_headers():
    from app.services.dimensional_csv import HEADERS
    return HEADERS
