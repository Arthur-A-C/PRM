from pathlib import Path

from openpyxl import Workbook

from app.services.catalog_treatment import attribute_key, iter_treated_xlsx, treat_raw


def test_raw_import_extracts_only_explicit_model_family_and_specs() -> None:
    result = treat_raw(
        name="Sensor indutivo M12 IP67 24 Vcc",
        manufacturer_code="SI-12345",
        reference=None,
        description="Invólucro para automação industrial",
        application=None,
    )

    assert result.family_group == "Sensores"
    assert result.model_reference == "SI-12345"
    assert result.attributes == {"protecao_ip": "IP67", "tensao": "24 Vcc"}


def test_pipeline_sheet_uses_sparse_attributes_and_ignores_precomputed_match(tmp_path: Path) -> None:
    file = tmp_path / "Produtos-ECO.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Base_ECO"
    sheet.append([
        "Codigo_ECO", "Familia_Produto", "Grupo_Familia_PRM", "Modelo_Referencia",
        "Codigos_Busca", "Titulo_Normalizado_PRM", "Confianca_Tratamento",
        "Atributos_PRM", "ATR_Grau_de_Protecao_IP", "Resultado_Cruzamento",
    ])
    sheet.append([
        "A-01", "Sensor", "Sensores", "SI-12345", "SI12345 | SI-12345",
        "sensor indutivo", 0.9, "cor=Azul | protecao_ip=IP54", "IP67", "MESMO CÓDIGO NA CHOICE",
    ])
    workbook.save(file)

    rows = list(iter_treated_xlsx(file, "eco-automacao"))

    assert len(rows) == 1
    assert rows[0].treatment.model_reference == "SI-12345"
    assert rows[0].treatment.attributes == {"cor": "Azul", "protecao_ip": "IP67"}
    assert attribute_key("ATR_Grau_de_Protecao_IP") == "protecao_ip"
