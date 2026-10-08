from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.services.datasheet_core import Theme, build_datasheet

BASE_DIR = Path(__file__).resolve().parent

SAG_THEME = Theme(
    brand="SAG",
    primary="#005ED3",
    accent="#005ED3",
    dark="#2E4259",
    text="#151B22",
    muted="#56616D",
    light="#F4F7FC",
    line="#D7E1EC",
    cover_bg="#F1F2F6",
    cover_text="#005ED3",
    cover_muted="#2E4259",
    header_bg="#FFFFFF",
    header_text="#16202A",
    footer_bg="#2E4259",
    footer_text="#FFFFFF",
    section_bg="#E7F0FB",
    section_text="#16202A",
    logo_path=str(BASE_DIR / "assets" / "sag_logo.png"),
    cover_logo_bg="#FFFFFF",
    footer_lines=("SAG",),
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


def generate_sag_datasheet(
    data: dict[str, Any],
    images: list[bytes] | None = None,
    codigo: str | None = None,
) -> bytes:
    images = images or []
    safe_code = (codigo or data.get("model") or "PRODUTO").strip()

    with tempfile.TemporaryDirectory(prefix="prm_sag_") as tmp_dir:
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
            SAG_THEME,
            output_dir=tmp_path,
        )

        return Path(output_path).read_bytes()
