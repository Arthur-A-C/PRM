"""Read the locally staged, company-specific WooCommerce reference exports."""

from __future__ import annotations

import os
from pathlib import Path
from zipfile import BadZipFile, ZipFile


EXPORT_NAMES = {
    "choice": "export_woocommerce_choice.csv",
    "sag": "export_woocommerce_sag.csv",
    "portwell": "export_woocommerce_portwell.csv",
}
DEFAULT_ZIP = Path(__file__).resolve().parents[2] / "data" / "imports" / "exports_woocommerce_choice_sag_portwell.zip"


def load_company_export(company: str) -> bytes:
    entry = EXPORT_NAMES.get(company)
    if entry is None:
        raise ValueError("Empresa sem export WooCommerce configurado.")
    archive = Path(os.environ.get("PRM_WOO_EXPORTS_ZIP", str(DEFAULT_ZIP)))
    if not archive.is_file():
        raise ValueError("ZIP de exports WooCommerce não encontrado; selecione o export da empresa.")
    try:
        with ZipFile(archive) as package:
            info = package.getinfo(entry)
            if info.file_size > 25 * 1024 * 1024:
                raise ValueError("Export WooCommerce acima de 25 MiB.")
            return package.read(info)
    except (BadZipFile, KeyError) as exc:
        raise ValueError("ZIP de exports WooCommerce inválido ou incompleto.") from exc
