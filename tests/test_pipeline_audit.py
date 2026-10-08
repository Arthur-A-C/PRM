"""Regressões da auditoria dos catálogos; nenhuma importação é publicada."""

from pathlib import Path

import pytest


CATALOG_DIR = Path(__file__).resolve().parents[1] / "data" / "imports"


@pytest.mark.skipif(not CATALOG_DIR.exists(), reason="catálogos locais indisponíveis")
def test_audit_fixtures_are_present() -> None:
    expected = (
        "produtos-choice.xlsx",
        "produtos-portwell.xlsx",
        "produtos_ecoautomacao.xlsx",
        "treated/Produtos-Choice.xlsx",
        "treated/Produtos-Portwell.xlsx",
        "treated/Produtos-ECO.xlsx",
    )
    assert all((CATALOG_DIR / name).is_file() for name in expected)
