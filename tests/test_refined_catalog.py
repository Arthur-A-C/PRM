import csv
import json
from copy import deepcopy
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.dimensional_csv import HEADERS
from app.services.refined_catalog import (
    classify, iter_records, load_analysis, load_policy, normalize_attribute,
    normalize_record, parse_price, profile_inputs, publish_analysis, run_pipeline,
    split_pairs, spreadsheet_safe, verify_run,
)


def record(raw):
    return {"position": 1, "raw": raw, "issues": [], "error": None}


def woo_raw(**changes):
    raw = {"ID": "6260", "Tipo": "simple", "SKU": "", "Nome": "Chave de segurança KL3-SS-Z-RR",
           "Publicado": "1", "Visibilidade no catálogo": "visible", "Categorias": "Instrumentar",
           "Preço": "1758,64", "Estoque": "0", "Em estoque?": "0"}
    raw.update(changes)
    return raw


def test_source_namespace_and_empty_sku_are_not_merged():
    policy = load_policy()
    a, _ = normalize_record(record(woo_raw()), "choice", policy, "batch")
    b, _ = normalize_record(record(woo_raw()), "portwell", policy, "batch")
    assert a["item_id"] != b["item_id"]
    assert a["record_key"] == "6260" and a["sku"] is None
    assert "empty_sku_preserved" in a["quality_issues"]
    assert a["public_catalog"]  # estoque zero não remove catálogo
    assert a["commercial"]["prices"][0]["amount"] == "1758.64"
    a, _ = normalize_record(record(woo_raw(SKU="codmaterialaqui")), "choice", policy, "batch")
    assert "placeholder_sku" in a["quality_issues"]


def test_legacy_eco_crossing_cannot_change_normalization():
    raw = {"Codigo_ECO": "P002212", "Nome_Original": "Contator DILM38-10(RDC24)",
           "Modelo_Referencia": "DILM38-10(RDC24", "ATR_Tensao": "24V",
           "Atributos_PRM": "Tensao=24V", "Marca_Padronizada": "Elfin",
           "Resultado_Cruzamento": "MESMO CÓDIGO NA CHOICE", "Score_Cruzamento": 100,
           "Cod_Material_Choice_Mais_Proximo": "999999"}
    a, attrs = normalize_record(record(raw), "eco", load_policy(), "batch")
    clean = {k: v for k, v in raw.items() if k not in {"Resultado_Cruzamento", "Score_Cruzamento", "Cod_Material_Choice_Mais_Proximo"}}
    b, _ = normalize_record(record(clean), "eco", load_policy(), "batch")
    assert a == b and a["technical_match_status"] == "not_assessed"
    assert a["brand_search"] == "new elfin srl"
    assert "model_unbalanced_parentheses" in a["quality_issues"]
    assert len(attrs) == 1 and len(attrs[0]["evidence"]) == 2
    assert attrs[0]["correlated_representations"]


@pytest.mark.parametrize("stock", ["99999", "100", "10", "1"])
def test_dimensional_variant_and_stock_are_conservative(stock):
    base = {"sku": "197090", "product_id": "197090", "nome": "Fita 20 m",
            "referencia": "BSEM - 39", "estoque": stock, "ean": "4,03E12", "preco": "0"}
    a, _ = normalize_record(record(base), "dimensional", load_policy(), "batch")
    b, _ = normalize_record(record({**base, "sku": "197354", "nome": "Fita 10 m"}), "dimensional", load_policy(), "batch")
    assert a["item_id"] != b["item_id"]
    assert not a["gtin_valid"] and a["gtin_raw"] == "4,03E12"
    assert a["commercial"]["quantity"] is None
    assert a["commercial"]["quantity_reliability"] == "unverified_source_semantics"
    assert a["commercial"]["prices"][0]["state"] == "zero_not_free"


def test_attribute_conflicts_do_not_invent_measurements():
    ethernet = normalize_attribute("Ethernet", "1x RJ45 (10/100 Mbps Gigabit)", "box_pc")
    usb = normalize_attribute("USB", "2x USB 2.0, 2x USB 3.0, 4x USB 2.0, 4x USB 3.0", "box_pc")
    assert ethernet["knowledge_state"] == usb["knowledge_state"] == "conflicting"
    assert ethernet["normalized_value"] is usb["normalized_value"] is None
    protocol = normalize_attribute("Protocolos de Comunicação", "RJ45", "plc")
    assert protocol["knowledge_state"] == "unknown" and protocol["qualifiers"]["connector_observed"] == "RJ45"
    assert normalize_attribute("Temperatura", "'-70°C a +380°C", "sensor")["normalized_value"].startswith("-70")
    diameter = normalize_attribute("Diâmetro", r"20\,8mm", "sensor")
    assert diameter["normalized_value"] == "20.8" and diameter["unit"] == "mm"
    power = normalize_attribute("Potência", "2, 5W", "power_supply", "Fonte 2,5 W")
    assert power["knowledge_state"] == "conflicting" and power["resolution_proposal"]["value"] == "2,5 W"
    assert normalize_attribute("Socket", "LGA 1700", "box_pc")["normalized_value"] == "LGA1700"
    assert normalize_attribute("Memória", "8 GB", "plc")["attribute_code"] != normalize_attribute("Memória", "8 GB", "box_pc")["attribute_code"]
    assert normalize_attribute("Alcance", "0-600 μg/m³", "sensor")["attribute_code"] != normalize_attribute("Alcance", "10 km", "sensor")["attribute_code"]
    assert normalize_attribute("Bitola", "8 mm", "cabling")["knowledge_state"] == "conflicting"


def test_pairs_preserve_duplicates_urls_and_residuals():
    pairs, residuals = split_pairs("CA: 123 | CA: 456|PDF: https://host/a:b|fragmento")
    assert pairs == [("CA", "123"), ("CA", "456"), ("PDF", "https://host/a:b")]
    assert residuals == ["fragmento"]
    assert normalize_attribute("CA", "123", "ppe")["attribute_code"] == "unmapped.ca"
    assert spreadsheet_safe("=1+2") == "'=1+2"


def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def fixture_inputs(tmp_path):
    headers = list(woo_raw()) + ["Nome do atributo 25", "Valores do atributo 25", "Metadado extra"]
    entries = []
    for source in ["portwell", "choice"]:
        path = tmp_path / (source + ".csv")
        raw = woo_raw(**{"Nome do atributo 25": "Socket", "Valores do atributo 25": "LGA 1700", "Metadado extra": ""})
        write_csv(path, headers, [[raw.get(h, "") for h in headers]])
        entries.append({"source_id": source, "path": path})
    path = tmp_path / "eco.xlsx"
    book = Workbook()
    book.active.title = "Base_ECO"
    book.active.append(["Codigo_ECO", "Nome_Original", "ATR_Tensao", "Outro"])
    book.active.append(["P002212", "Contator DILM38-10(RDC24)", "24V", "=1+2"])
    book.save(path)
    book.close()
    entries.append({"source_id": "eco", "path": path})
    path = tmp_path / "dimensional.csv"
    write_csv(path, list(HEADERS), [[{"sku": "197090", "product_id": "197090", "nome": "Fita 20 m", "preco": "13.32"}.get(h, "") for h in HEADERS]])
    entries.append({"source_id": "dimensional", "path": path})
    return entries


def test_csv_alignment_tail_multiline_and_dynamic_attributes(tmp_path):
    entries = fixture_inputs(tmp_path)
    path = entries[0]["path"]
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    good = rows[1][:-1]
    good[3] = "Título\ncom vírgula, preservada"
    bad = list(rows[1])
    bad[1] = "DESLOCADO"
    write_csv(path, rows[0], [good, bad, rows[1] + ["extra"]])
    records = list(iter_records(path, "portwell"))
    assert records[0]["error"] is None and records[0]["raw"]["Metadado extra"] is None
    assert records[0]["raw"]["Nome"] == "Título\ncom vírgula, preservada"
    assert records[1]["error"] and records[2]["error"]
    item, attrs = normalize_record(records[0], "portwell", load_policy(), "batch")
    assert attrs[0]["raw_name"] == "Socket" and item["attribute_count"] == 1
    profile = profile_inputs(entries, load_policy())
    assert profile["sources"]["portwell"]["counts"]["received"] == 3
    assert profile["sources"]["portwell"]["counts"]["quarantine"] == 2


def test_publication_idempotency_atomicity_and_tamper(tmp_path):
    entries = fixture_inputs(tmp_path)
    output, archive = tmp_path / "outputs", tmp_path / "archive"
    result = run_pipeline(entries, load_policy(), output_root=output, archive_root=archive)
    run_id = result["run_id"]
    assert result["counts"]["eco"]["accepted"] == 1
    assert result["quality"]["eco"]["excel_formula_not_evaluated"] == 1
    assert load_analysis(output_root=output) is None
    publish_analysis(run_id, output)
    assert load_analysis(output_root=output)["matching_status"] == "not_assessed"
    again = run_pipeline(entries, load_policy(), output_root=output, archive_root=archive)
    assert again["idempotent"] and again["run_id"] == run_id
    coverage = list(csv.DictReader((output / run_id / "competitor_coverage.csv").open(encoding="utf-8")))
    assert len(coverage) == 12 and {r["coverage_status"] for r in coverage} == {"not_assessed"}
    prior_pointer = (output / "published.json").read_bytes()
    broken = deepcopy(entries)
    broken[0]["path"] = tmp_path / "broken.csv"
    write_csv(broken[0]["path"], ["bad"], [["content"]])
    with pytest.raises(ValueError):
        run_pipeline(broken, load_policy(), output_root=output, archive_root=archive)
    assert (output / "published.json").read_bytes() == prior_pointer
    (output / run_id / "own_items.jsonl").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError):
        verify_run(output / run_id)
    with pytest.raises(ValueError):
        publish_analysis(run_id, output)
    assert (output / "published.json").read_bytes() == prior_pointer


def test_no_safety_equivalence_or_definitive_gap_from_family():
    policy = load_policy()
    assert classify("Bobina para contator", "", policy)["item_form"] == "accessory"
    assert classify("Contator", "", policy)["family_id"] != classify("Relé de segurança", "", policy)["family_id"]
    item, _ = normalize_record(record(woo_raw(Nome="Contator", SKU="A1")), "choice", policy, "batch")
    assert item["catalog_completeness"] == "partial"
    assert item["technical_match_status"] == "not_assessed" and item["substitution_approval"] == "not_reviewed"


@pytest.mark.parametrize("value,locale,expected", [("1758,64", "pt_BR", "1758.64"), ("13.32", "decimal_dot", "13.32"), ("0", "excel", None), ("", "pt_BR", None)])
def test_price_locale(value, locale, expected):
    assert parse_price(value, locale)[0] == expected
