from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from app.config import Settings
from app.services.catalog_import import (
    availability_from_stock,
    normalized_brand_name,
    parse_catalog,
    parse_decimal,
)


def settings() -> Settings:
    return Settings(_env_file=None, max_upload_mib=20, max_import_rows=100)


def test_eco_parser_preserves_code_and_normalizes_business_rules() -> None:
    path = Path("tests/.generated-eco.xlsx")
    path.unlink(missing_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Produtos"
    sheet.append(
        ["Codigo", "Nome", "link", "Marca", "Preco_pix", "Preco_cartao", "Estoque", "Descricao"]
    )
    sheet.append(
        ["001", "Produto A", "https://example.test/a", "Marca A", 0, "1.234,56", "https://schema.org/BackOrder", "Texto_x000D_\n&amp;nbsp; detalhe"]
    )
    workbook.save(path)

    try:
        preview = parse_catalog(path, "eco-automacao", settings())

        assert preview.header_row == 1
        assert preview.valid_rows == 1
        row = preview.rows[0]
        assert row.external_code == "001"
        assert row.availability_state == "sob_encomenda"
        assert row.description_display == "Texto\n\n detalhe"
        assert [(price.modality, price.amount, price.state) for price in row.prices] == [
            ("pix", None, "nao_informado"),
            ("cartao", Decimal("1234.56"), "valido"),
        ]
    finally:
        path.unlink(missing_ok=True)


def test_erp_parser_finds_third_row_header_and_rejects_duplicate_code() -> None:
    path = Path("tests/.generated-choice.xlsx")
    path.unlink(missing_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["Filtros aplicados"])
    sheet.append([])
    sheet.append(
        [
            "Cód. Material", "Descrição Material", "Fabricante", "Aplicação Material",
            "Preço Venda", "Estoque Atual", "Desc. Grupo", "Desc. Subgrupo",
        ]
    )
    sheet.append(["ABC", "Produto", "Fabricante", "Aplicação", "2.345,67", 2, "Controle", "IHM"])
    sheet.append(["ABC", "Produto repetido", "Fabricante", "Aplicação", 10, 0, "Controle", "IHM"])
    workbook.save(path)

    try:
        preview = parse_catalog(path, "choice-tech", settings())

        assert preview.header_row == 3
        assert preview.valid_rows == 1
        assert preview.rejected_rows == 1
        assert "duplicado" in preview.rows[1].errors[0]
        assert preview.rows[0].stock_quantity == Decimal("2")
        assert preview.rows[0].availability_state == "em_estoque"
        assert preview.rows[0].prices[0].amount == Decimal("2345.67")
    finally:
        path.unlink(missing_ok=True)


def test_decimal_and_stock_parsing_are_explicit() -> None:
    assert parse_decimal("1.234,56") == Decimal("1234.56")
    assert parse_decimal("1,234.56") == Decimal("1234.56")
    assert availability_from_stock(0)[1:3] == ("fora_estoque", Decimal("0"))
    assert availability_from_stock(None)[1:3] == ("nao_informado", None)


def test_brand_normalization_ignores_punctuation_in_legal_suffix() -> None:
    assert normalized_brand_name("New Elfin S.R.L.") == "new elfin srl"
    assert normalized_brand_name("NEW ELFIN SRL") == "new elfin srl"
