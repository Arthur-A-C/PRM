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


def _verified(content: bytes, limit_mib: int) -> None:
    if len(content) > limit_mib * 1024 * 1024:
        raise ValueError(f"Imagem acima de {limit_mib} MiB.")
    with Image.open(io.BytesIO(content)) as source:
        source.verify()


def _on_white(image: Image.Image, *, palette: bool = False) -> Image.Image:
    """Flatten transparency onto white; every other mode becomes RGB (palette transparency only on request)."""
    if palette and image.mode == "P" and "transparency" in image.info:
        image = image.convert("RGBA")
    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        return background
    return image.convert("RGB")


def process_image(content: bytes, *, rotation: int = 0, size: int | None = 1200, quality: int = 90) -> bytes:
    if rotation not in {0, 90, 180, 270} or size not in {None, 1200, 1600} or quality not in {90, 95, 100}:
        raise ValueError("Configuração de imagem inválida.")
    _verified(content, 25)
    with Image.open(io.BytesIO(content)) as source:
        image = ImageOps.exif_transpose(source)
        image = image.rotate(-rotation, expand=True)
        if size:
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
        image = _on_white(image)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()


SQUARE_FORMATS = {"JPEG", "PNG", "WEBP"}


def fit_square(content: bytes, *, size: int = 1500, image_format: str = "JPEG", quality: int = 90) -> bytes:
    """Exact size x size canvas: proportional fit (up or down, never stretched), centred on white.

    Same verification, EXIF orientation and white flattening as process_image; keeps the
    requested format (JPEG/PNG/WEBP) and the ICC profile when present.
    """
    if image_format not in SQUARE_FORMATS or not 200 <= size <= 4000 or quality not in {85, 90, 95, 100}:
        raise ValueError("Configuração de imagem inválida.")
    _verified(content, 60)
    with Image.open(io.BytesIO(content)) as source:
        if source.width * source.height > 60_000_000:
            raise ValueError("Imagem acima de 60 megapixels.")
        icc = source.info.get("icc_profile")
        image = _on_white(ImageOps.exif_transpose(source), palette=True)
        image = ImageOps.contain(image, (size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (size, size), "white")
        canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
        options = {"icc_profile": icc} if icc else {}
        if image_format == "JPEG":
            options.update(quality=quality, optimize=True, subsampling=0 if quality >= 95 else 2)
        elif image_format == "WEBP":
            options.update(quality=quality, method=4)
        else:
            options.update(optimize=True)
        output = io.BytesIO()
        canvas.save(output, format=image_format, **options)
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
            # The supplier datasheet is only a generation source; the export carries the PRM datasheet.
            if role == "source_datasheet":
                continue
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
