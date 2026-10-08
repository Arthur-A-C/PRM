"""The staging importer preserves source meaning and commercial uncertainty."""

from app.services.dimensional_csv import HEADERS, DimensionalCsvAdapter, SourceRecord
from scripts.import_dimensional_staging import build_record_values


def test_staging_values_preserve_sku_variant_and_unknown_commercial_terms():
    raw = dict.fromkeys(HEADERS, "")
    raw.update({
        "sku": "1053629", "product_id": "1053625",
        "nome": "Sapato de segurança tamanho 39", "marca": "Exemplo",
        "categoria": "EPI > Calçados", "preco": "123.45", "preco_de": "140.00",
        "estoque": "99999", "disponibilidade": "Em estoque",
        "referencia": "REF-39", "descricao_curta": "Descrição",
    })
    source = SourceRecord(1, 2, 4, raw)
    mapped = DimensionalCsvAdapter().map_record(source)
    offer, line, observation, prices = build_record_values(
        source, mapped, "company", "organization", "import"
    )
    assert offer["external_code"] == "1053629"
    assert line["raw_row"]["product_id"] == "1053625"
    assert line["raw_row"]["_physical_line_end"] == 4
    assert offer["stock_quantity"] is None
    assert offer["availability_state"] == "nao_informado"
    assert observation["currency"] == "XXX"
    assert observation["observed_at"] is None
    assert [price["modality"] for price in prices] == ["anunciado", "referencia_anunciada"]
    assert [str(price["amount"]) for price in prices] == ["123.45", "140.00"]
