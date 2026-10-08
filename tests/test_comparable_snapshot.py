import csv

import pytest

from app.services.comparable_snapshot import build_snapshot, snapshot_view


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def test_reconciles_duplicates_unpublished_and_attribute_provenance(tmp_path):
    base = tmp_path / "base.csv"
    attrs = tmp_path / "attrs.csv"
    fields = ["Chave_Unica", "Fonte", "ID_Origem", "Macro_Categoria", "Familia_Comparavel"]
    rows = [
        dict(zip(fields, ["CHOICE:C1", "CHOICE", "C1", "Comando", "Botão"])),
        dict(zip(fields, ["ECO:E1", "ECO", "E1", "Comando", "Botão"])),
        dict(zip(fields, ["ECO:E2", "ECO", "E2", "Proteção", "Fusível"])),
        dict(zip(fields, ["PORTWELL:P1", "PORTWELL", "P1", "Computação", "Painel PC"])),
        dict(zip(fields, ["PORTWELL:P1", "PORTWELL", "P1", "Computação", "Painel PC"])),
        dict(zip(fields, ["CHOICE:MISSING", "CHOICE", "MISSING", "Comando", "Botão"])),
    ]
    write_csv(base, fields, rows)
    attr_fields = ["Chave_Unica", "Fonte", "Atributo", "Origem_Valor", "Relevante_Familia"]
    write_csv(attrs, attr_fields, [
        dict(zip(attr_fields, ["CHOICE:C1", "CHOICE", "tensao", "atributo", "Sim"])),
        dict(zip(attr_fields, ["ECO:E1", "ECO", "tensao", "texto (título)", "Sim"])),
        dict(zip(attr_fields, ["CHOICE:MISSING", "CHOICE", "tensao", "atributo", "Sim"])),
    ])
    snapshot = build_snapshot(base, attrs, {
        "CHOICE": {"C1"}, "PORTWELL": {"P1"}, "ECO": {"E1", "E2"},
    })
    assert snapshot["totals"] == {"CHOICE": 1, "PORTWELL": 1, "ECO": 2}
    assert snapshot["quality"]["duplicate_keys"] == {"PORTWELL": 1}
    assert snapshot["quality"]["not_published"] == {"CHOICE": 1}
    assert snapshot["quality"]["orphan_attribute_rows"] == 1
    assert snapshot["quality"]["products_with_inferred_attributes"] == 1
    view = snapshot_view(snapshot, signal="sem_familia_propria")
    assert view["metrics"]["family_overlap_percent"] == 50.0
    assert view["metrics"]["competitor_only"] == 1
    assert [item["family"] for item in view["items"]] == ["Fusível"]


def test_rejects_conflicting_duplicate_keys(tmp_path):
    base = tmp_path / "base.csv"
    attrs = tmp_path / "attrs.csv"
    fields = ["Chave_Unica", "Fonte", "ID_Origem", "Macro_Categoria", "Familia_Comparavel"]
    write_csv(base, fields, [
        dict(zip(fields, ["ECO:E1", "ECO", "E1", "Proteção", "Fusível"])),
        dict(zip(fields, ["ECO:E1", "ECO", "E1", "Proteção", "Disjuntor"])),
    ])
    write_csv(attrs, ["Chave_Unica", "Fonte", "Atributo", "Origem_Valor", "Relevante_Familia"], [])
    with pytest.raises(ValueError, match="dados divergentes"):
        build_snapshot(base, attrs, {"ECO": {"E1"}})
