"""Verified ZIP package with processed images and unchanged original files."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile

from PIL import Image, ImageOps

from app.schemas.registration import RegistrationProduct


def safe_component(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    if not result or result in {".", ".."}:
        raise ValueError("Código ou nome de arquivo inseguro.")
    return result[:120]


def process_image(content: bytes, *, rotation: int = 0, size: int | None = 1200, quality: int = 90) -> bytes:
    if rotation not in {0, 90, 180, 270} or size not in {None, 1200, 1600} or quality not in {90, 95, 100}:
        raise ValueError("Configuração de imagem inválida.")
    if len(content) > 25 * 1024 * 1024:
        raise ValueError("Imagem acima de 25 MiB.")
    with Image.open(io.BytesIO(content)) as source:
        source.verify()
    with Image.open(io.BytesIO(content)) as source:
        image = ImageOps.exif_transpose(source)
        image = image.rotate(-rotation, expand=True)
        if size:
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()


def build_package(
    product: RegistrationProduct,
    images: list[tuple[str, bytes, int]],
    files: list[tuple[str, str, bytes]],
    *, size: int | None = 1200, quality: int = 90,
) -> tuple[bytes, dict]:
    if sum(len(content) for _, content, _ in images) + sum(len(content) for _, _, content in files) > 100 * 1024 * 1024:
        raise ValueError("Pacote acima de 100 MiB.")
    folder = safe_component(product.sku)
    manifest = {
        "company": product.company, "sku": product.sku,
        "product": product.model_dump(mode="json"),
        "files": [],
    }
    output = io.BytesIO()
    used = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (_, content, rotation) in enumerate(images, 1):
            processed = process_image(content, rotation=rotation, size=size, quality=quality)
            name = f"{index}.jpg"
            archive.writestr(f"{folder}/{name}", processed)
            manifest["files"].append({
                "role": "main_image" if index == 1 else "gallery",
                "name": name, "sha256": hashlib.sha256(processed).hexdigest(),
            })
            used.add(name.casefold())
        for role, filename, content in files:
            if role not in {"source_datasheet", "generated_datasheet", "drawing_3d", "manual", "certificate", "other"}:
                raise ValueError(f"Tipo de arquivo não permitido: {role}.")
            if len(content) > 50 * 1024 * 1024:
                raise ValueError(f"Arquivo acima de 50 MiB: {filename}.")
            name = safe_component(filename)
            if name.casefold() in used:
                raise ValueError(f"Nome de arquivo duplicado no pacote: {name}.")
            used.add(name.casefold())
            archive.writestr(f"{folder}/{name}", content)
            manifest["files"].append({
                "role": role, "name": name, "sha256": hashlib.sha256(content).hexdigest(),
            })
        archive.writestr(
            f"{folder}/manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return output.getvalue(), manifest
