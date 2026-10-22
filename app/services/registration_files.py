"""Read-only file discovery adapted from cadastro_dashboardd.py's naming rules."""

from __future__ import annotations

import os
import json
import re
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf", ".zip", ".rar", ".7z", ".step", ".stp", ".dwg", ".dxf"}
DOCUMENT_ROLES = (
    ("source_datasheet", re.compile(r"datasheet|ficha.t[eé]cnica", re.I)),
    ("drawing_3d", re.compile(r"desenho|(?:^|[_ -])3d(?:$|[_ .-])", re.I)),
    ("manual", re.compile(r"manual|manuais", re.I)),
    ("certificate", re.compile(r"certificad", re.I)),
)


def configured_root(company: str) -> Path:
    if company not in {"choice", "sag", "portwell"}:
        raise ValueError("Empresa inválida.")
    raw = os.environ.get(f"PRM_REGISTRATION_{company.upper()}_ROOT", "")
    if not raw:
        raise ValueError(f"Pasta de produtos de {company} não configurada.")
    root = Path(raw).resolve()
    if not root.is_dir():
        raise ValueError(f"Pasta de produtos de {company} indisponível.")
    return root


def find_product_folder(root: Path, sku: str) -> Path | None:
    if not sku or "/" in sku or "\\" in sku or sku in {".", ".."}:
        raise ValueError("SKU inválido para busca de pasta.")
    resolved_root = root.resolve()
    found = []
    for path in resolved_root.rglob("*"):
        if path.is_dir() and path.name.casefold() == sku.casefold():
            resolved = path.resolve()
            if not resolved.is_relative_to(resolved_root):
                continue
            found.append(resolved)
            if len(found) > 1:
                raise ValueError(f"Mais de uma pasta encontrada para SKU {sku}; revisão necessária.")
    return found[0] if found else None


def classify_files(folder: Path, *, portable=False, sku=None, company=None) -> dict:
    """Classify only; never upload or infer that a document matches the product."""
    manifest_path = folder / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("status") != "validated" or (not portable and manifest.get("folder_path") != str(folder)):
                raise ValueError("Manifesto não corresponde à pasta validada.")
            if portable and (manifest.get("sku")!=sku or manifest.get("cigam_code")!=sku or manifest.get("company")!=company):
                raise ValueError("SKU/empresa do manifesto diverge da pasta/loja.")
            def existing(relative: str) -> str:
                from app.services.datasheet_batches import relative_name
                relative_name(relative)
                path = (folder / relative).resolve()
                if not path.is_relative_to(folder.resolve()) or not path.is_file() or path.is_symlink():
                    raise ValueError(f"Arquivo do manifesto ausente ou fora da pasta: {relative}.")
                return str(path)
            if portable:
                import hashlib
                declared={}
                for item in manifest["files"]:
                    relative=item["path"]
                    if relative.casefold() in declared: raise ValueError("Arquivo duplicado no manifesto.")
                    declared[relative.casefold()]=item
                    path=Path(existing(relative))
                    if hashlib.sha256(path.read_bytes()).hexdigest()!=item.get("sha256"):
                        raise ValueError("Hash do arquivo diverge do manifesto.")
                if any(r.casefold() not in declared for r in manifest["ordered_images"]):
                    raise ValueError("Imagem não declarada no manifesto.")
                if len(set(manifest["ordered_images"]))!=len(manifest["ordered_images"]):
                    raise ValueError("Imagem duplicada no manifesto.")
            ordered = [existing(relative) for relative in manifest["ordered_images"]]
            # A portable package may carry only documents (files-only publishing); local folders keep requiring a photo.
            if (not ordered and not portable) or (not portable and ordered[0] != manifest["main_image_path"]):
                raise ValueError("Imagem principal diverge da ordem do manifesto.")
            documents = [
                {"role": item["role"], "path": existing(item["path"])}
                for item in manifest["files"] if item["role"] not in {"main_image", "gallery", "technical_analysis"}
            ]
            return {"main_image": ordered[0] if ordered else None, "gallery": ordered[1:], "documents": documents, "warnings": []}
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Manifesto do produto inválido.") from exc
    images = []
    documents = []
    folders = [folder]
    photos = folder / "Fotos"
    if photos.is_dir():
        folders.append(photos)
    for directory in folders:
        for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            if not path.is_file() or path.is_symlink():
                continue
            extension = path.suffix.casefold()
            if extension in IMAGE_EXTENSIONS:
                images.append(path)
            elif extension in DOCUMENT_EXTENSIONS:
                role = next((role for role, pattern in DOCUMENT_ROLES if pattern.search(path.stem)), "other")
                documents.append({"role": role, "path": path})
    def image_order(path: Path):
        name = path.stem
        if re.search(r"(?:_variante?|_principal)$", name, re.I):
            return (0, 0, name.casefold())
        numbered = re.search(r"(?:_foto_?|[ _-])(\d+)$", name, re.I)
        return (1, int(numbered.group(1)), name.casefold()) if numbered else (2, 0, name.casefold())
    images.sort(key=image_order)
    return {
        "main_image": str(images[0]) if images else None,
        "gallery": [str(path) for path in images[1:]],
        "documents": [{"role": item["role"], "path": str(item["path"])} for item in documents],
        "warnings": [
            "Nenhum datasheet identificado por nome; confirmar manualmente."
        ] if not any(item["role"] == "source_datasheet" for item in documents) else [],
    }
