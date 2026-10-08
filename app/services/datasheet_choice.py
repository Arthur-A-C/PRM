from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.services.datasheet_core import Theme, build_datasheet

BASE_DIR = Path(__file__).resolve().parent

CHOICE_THEME = Theme(
    brand="CHOICE",
    primary="#3A3A3A",
    accent="#35A9D6",
    dark="#252525",
    text="#1D1D1D",
    muted="#666666",
    light="#F5F5F5",
    line="#DADDE1",
    cover_bg="#303030",
    cover_text="#FFFFFF",
    cover_muted="#C9CDD1",
    header_bg="#F1F2F6",
    header_text="#252525",
    footer_bg="#303030",
    footer_text="#FFFFFF",
    section_bg="#ECEDEF",
    section_text="#252525",
    logo_path=str(BASE_DIR / "assets" / "choice_logo.png"),
    cover_logo_bg=None,
    footer_lines=("CHOICE",),
)


def _flatten_specs(specs: list[dict[str, Any]] | None) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []

    for section in specs or []:
        if not isinstance(section, dict):
            continue

        section_name = str(section.get("secao") or section.get("section") or "").strip()
        if section_name:
            rows.append((section_name,))

        for item in section.get("itens") or []:
            if not isinstance(item, dict):
                continue

            key = str(item.get("campo") or item.get("key") or "").strip()
            value = str(item.get("valor") or item.get("value") or "").strip()

            if key and value:
                rows.append((key, value))

    return rows


def _prepare_product(data: dict[str, Any], codigo: str) -> dict[str, Any]:
    product = dict(data)
    product["codigo"] = codigo
    product["model"] = str(data.get("model") or codigo).strip()
    product["specs"] = _flatten_specs(data.get("specs"))
    return product


def generate_choice_datasheet(
    data: dict[str, Any],
    images: list[bytes] | None = None,
    codigo: str | None = None,
) -> bytes:
    images = images or []
    safe_code = (codigo or data.get("model") or "PRODUTO").strip()

    with tempfile.TemporaryDirectory(prefix="prm_choice_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        product = _prepare_product(data, safe_code)

        image_paths: list[str] = []

        for index, image_bytes in enumerate(images, start=1):
            path = tmp_path / f"{index}.jpg"
            path.write_bytes(image_bytes)
            image_paths.append(str(path))

        if image_paths:
            product["main_image"] = image_paths[0]
            product["gallery"] = image_paths[1:]

        output_path = build_datasheet(
            product,
            CHOICE_THEME,
            output_dir=tmp_path,
        )

        return Path(output_path).read_bytes()
