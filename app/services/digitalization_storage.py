"""Durable, review-first product folders. No WooCommerce operations live here."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.registration import RegistrationProduct


COMPANIES = {"choice", "sag", "portwell"}
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
ROOT_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "products"
RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def storage_root() -> Path:
    raw = os.environ.get("PRM_PRODUCT_STORAGE_ROOT")
    path = Path(raw) if raw else ROOT_DEFAULT
    if not path.is_absolute():
        raise ValueError("PRM_PRODUCT_STORAGE_ROOT deve ser um caminho absoluto.")
    return path.resolve()


def validate_sku(sku: str) -> str:
    if not isinstance(sku, str) or not sku or sku != sku.strip():
        raise ValueError("Código CIGAM vazio ou com espaços nas extremidades; corrija sem alterar o código automaticamente.")
    if len(sku) > 120 or re.search(r'[<>:"/\\|?*\x00-\x1f]', sku) or sku.endswith((".", " ")):
        raise ValueError("Código CIGAM contém caracteres proibidos em caminhos do Windows.")
    if sku.split(".", 1)[0].upper() in WINDOWS_RESERVED or sku in {".", ".."}:
        raise ValueError("Código CIGAM é um nome reservado do Windows.")
    return sku


def _run_dir(run_id: str, root: Path) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("Identificador de digitalização inválido.")
    return root / "_runs" / run_id


def _write_json(path: Path, value: dict) -> None:
    data = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_draft(
    company: str, sku: str, name: str, analysis: dict,
    processed_images: list[bytes], pdf: bytes,
    *, image_processing: dict | None = None, previews: list[bytes] | None = None,
    warnings: list[str] | None = None, pending: list[str] | None = None,
    source_check: str = "",
) -> dict:
    if company not in COMPANIES:
        raise ValueError("Empresa inválida.")
    validate_sku(sku)
    if not name.strip() or not isinstance(analysis, dict) or not analysis:
        raise ValueError("Nome e análise técnica são obrigatórios.")
    if not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-1024:]:
        raise ValueError("O gerador não retornou um PDF válido.")
    if not processed_images:
        raise ValueError("Adicione pelo menos uma foto antes de gerar o datasheet.")
    if len(processed_images) > 20 or len(pdf) > 30 * 1024 * 1024 or sum(map(len, processed_images)) + len(pdf) > 100 * 1024 * 1024:
        raise ValueError("Rascunho excede o limite de 20 fotos ou 100 MiB.")
    root = storage_root()
    runs = root / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    run_dir = _run_dir(run_id, root)
    run_dir.mkdir(exist_ok=False)
    record = {
        "run_id": run_id, "status": "draft", "company": company, "sku": sku,
        "name": name.strip(), "analysis": analysis,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "image_count": len(processed_images), "pdf_sha256": _sha(pdf),
        "image_processing": image_processing or {},
        "warnings": warnings or [], "pending": pending or [],
        "source_check": source_check, "preview_count": len(previews or []),
    }
    try:
        for index, content in enumerate(processed_images, 1):
            run_dir.joinpath(f"image_{index}.jpg").write_bytes(content)
        run_dir.joinpath("datasheet.pdf").write_bytes(pdf)
        for index, content in enumerate(previews or [], 1):
            run_dir.joinpath(f"preview_{index}.png").write_bytes(content)
        _write_json(run_dir / "record.json", record)
    except OSError:
        if run_dir.exists() and run_dir.resolve().is_relative_to(root):
            shutil.rmtree(run_dir)
        raise
    return record


def load_run(run_id: str) -> dict:
    path = _run_dir(run_id, storage_root()) / "record.json"
    if not path.is_file():
        raise ValueError("Digitalização não encontrada.")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("run_id") != run_id:
        raise ValueError("Registro de digitalização inconsistente.")
    return record


def approve_draft(run_id: str, *, acknowledge_pending: bool = False) -> dict:
    record = load_run(run_id)
    if record["status"] not in {"draft", "approved"}:
        raise ValueError("Somente rascunhos podem ser aprovados.")
    if record.get("pending") and not acknowledge_pending:
        raise ValueError("Há pendências técnicas; confirme explicitamente para aprovar.")
    record["status"] = "approved"
    record["approved_at"] = datetime.now(timezone.utc).isoformat()
    record["pending_acknowledged"] = bool(acknowledge_pending)
    _write_json(_run_dir(run_id, storage_root()) / "record.json", record)
    return record


def run_file(run_id: str, kind: str) -> Path:
    record = load_run(run_id)
    root = storage_root()
    if kind == "datasheet":
        path = _run_dir(run_id, root) / "datasheet.pdf"
    elif kind == "package" and record.get("status") == "validated":
        path = Path(record["folder_path"]) / f"{record['sku']}.zip"
    else:
        raise ValueError("Arquivo indisponível para esta digitalização.")
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError("Arquivo de digitalização não encontrado no armazenamento configurado.")
    return path


def verify_package(run_id: str) -> dict:
    record = load_run(run_id)
    if record.get("status") != "validated":
        raise ValueError("Digitalização ainda não validada.")
    folder = Path(record["folder_path"])
    root = storage_root()
    if not folder.resolve().is_relative_to(root) or not folder.is_dir():
        raise ValueError("Pasta final do produto indisponível.")
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("package_id") != run_id or manifest.get("status") != "validated":
            raise ValueError("Manifesto final inconsistente.")
        for item in manifest["files"]:
            path = (folder / item["path"]).resolve()
            if not path.is_relative_to(folder.resolve()) or _sha(path.read_bytes()) != item["sha256"]:
                raise ValueError(f"Arquivo final divergente: {item['path']}.")
        package = run_file(run_id, "package")
        with zipfile.ZipFile(package) as archive:
            if archive.testzip() is not None or f"{record['sku']}/manifest.json" not in archive.namelist():
                raise ValueError("ZIP final corrompido.")
            if _sha(archive.read(f"{record['sku']}/manifest.json")) != _sha((folder / "manifest.json").read_bytes()):
                raise ValueError("Manifesto no ZIP diverge da pasta final.")
            for item in manifest["files"]:
                if _sha(archive.read(f"{record['sku']}/{item['path']}")) != item["sha256"]:
                    raise ValueError(f"ZIP diverge do manifesto: {item['path']}.")
        return record
    except (FileNotFoundError, KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise ValueError("Pacote final incompleto ou corrompido.") from exc


def _document_name(sku: str, role: str, filename: str, ordinal: int) -> str:
    extension = Path(filename).suffix.lower()
    allowed = {
        "source_datasheet": {".pdf"},
        "drawing_3d": {".zip", ".step", ".stp", ".dwg", ".dxf", ".rar", ".7z"},
        "manual": {".pdf"}, "certificate": {".pdf"},
        "other": {".pdf", ".zip", ".step", ".stp", ".dwg", ".dxf"},
    }
    if extension not in allowed.get(role, set()):
        raise ValueError(f"Formato não permitido para {role}: {filename}.")
    names = {
        "source_datasheet": "Datasheet_Original", "drawing_3d": "Desenho_3D",
        "manual": "Manual", "certificate": "Certificado", "other": "Documento",
    }
    suffix = f"_{ordinal}" if ordinal > 1 else ""
    return f"{sku}_{names[role]}{suffix}{extension}"


def finalize_draft(
    run_id: str, product: RegistrationProduct,
    documents: list[tuple[str, str, bytes]], *, new_version: bool = False,
) -> dict:
    record = load_run(run_id)
    if record["status"] == "validated":
        raise ValueError("Esta execução já foi finalizada; use o pacote existente ou crie novo rascunho.")
    if record["status"] != "approved":
        raise ValueError("Aprove o datasheet antes de criar a pasta final do produto.")
    if product.company != record["company"] or product.sku != record["sku"] or product.technical_name != record["name"]:
        raise ValueError("Empresa, SKU ou nome divergem do datasheet revisado; gere novo datasheet.")
    sku = validate_sku(product.sku)
    root = storage_root()
    company_root = root / product.company
    company_root.mkdir(parents=True, exist_ok=True)
    canonical = company_root / sku
    if canonical.exists() and not new_version:
        raise FileExistsError("A pasta do produto já existe. Revise-a ou escolha criar uma nova versão.")
    if new_version and not canonical.exists():
        raise ValueError("Não há versão original; finalize primeiro na pasta principal do SKU.")
    if new_version:
        versions = company_root / "_versions" / sku
        version = len([item for item in versions.iterdir() if item.is_dir()]) + 2 if versions.is_dir() else 2
        target = versions / run_id / sku
    else:
        version = 1
        target = canonical
    if target.exists() or target.is_symlink() or not target.parent.resolve().is_relative_to(root):
        raise ValueError("Destino existente ou fora do armazenamento configurado.")
    if os.name == "nt" and len(str(target / "Fotos" / f"{sku}_variante.jpg")) > 240:
        raise ValueError("Caminho final muito longo para uso seguro no Windows; configure uma pasta-base mais curta.")
    if len(documents) > 30 or sum(len(data) for _, _, data in documents) > 100 * 1024 * 1024:
        raise ValueError("Documentos excedem o limite de 30 arquivos ou 100 MiB.")
    draft = _run_dir(run_id, root)
    pdf = (draft / "datasheet.pdf").read_bytes()
    if _sha(pdf) != record["pdf_sha256"]:
        raise ValueError("Datasheet do rascunho foi alterado; gere novamente.")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".prm-staging-", dir=target.parent))
    try:
        photos = staging / "Fotos"
        photos.mkdir()
        items = []
        ordered_images = []
        for index in range(1, record["image_count"] + 1):
            source = draft / f"image_{index}.jpg"
            content = source.read_bytes()
            filename = f"{sku}_variante.jpg" if index == 1 else f"{sku}_foto{index}.jpg"
            relative = f"Fotos/{filename}"
            (photos / filename).write_bytes(content)
            ordered_images.append(relative)
            items.append({"role": "main_image" if index == 1 else "gallery", "path": relative, "sha256": _sha(content)})
        pdf_name = f"{sku}_Datasheet.pdf"
        (staging / pdf_name).write_bytes(pdf)
        items.append({"role": "generated_datasheet", "path": pdf_name, "sha256": _sha(pdf)})
        analysis_content = json.dumps(record["analysis"], ensure_ascii=False, indent=2).encode("utf-8")
        (staging / "datasheet_dados.json").write_bytes(analysis_content)
        items.append({"role": "technical_analysis", "path": "datasheet_dados.json", "sha256": _sha(analysis_content)})
        counts: dict[str, int] = {}
        for role, original_name, content in documents:
            if not content or len(content) > 50 * 1024 * 1024:
                raise ValueError(f"Documento vazio ou acima de 50 MiB: {original_name}.")
            counts[role] = counts.get(role, 0) + 1
            filename = _document_name(sku, role, original_name, counts[role])
            if filename.lower().endswith(".pdf") and not content.startswith(b"%PDF-"):
                raise ValueError(f"Documento não é PDF: {original_name}.")
            if filename.lower().endswith(".zip") and not zipfile.is_zipfile(io.BytesIO(content)):
                raise ValueError(f"Documento ZIP inválido: {original_name}.")
            (staging / filename).write_bytes(content)
            items.append({"role": role, "path": filename, "sha256": _sha(content), "original_name": original_name})
        manifest = {
            "schema_version": 1, "package_id": run_id, "package_version": version,
            "status": "validated", "generated_at": datetime.now(timezone.utc).isoformat(),
            "company": product.company, "cigam_code": sku, "sku": sku,
            "product_name": product.technical_name, "commercial_title": product.commercial_title,
            "folder_path": str(target), "datasheet_path": str(target / pdf_name),
            "main_image_path": str(target / ordered_images[0]),
            "ordered_images": ordered_images,
            "image_processing": record.get("image_processing", {}),
            "drawings_3d": [item["path"] for item in items if item["role"] == "drawing_3d"],
            "documents": [item["path"] for item in items if item["role"] not in {"main_image", "gallery", "drawing_3d"}],
            "analysis": record["analysis"], "product": product.model_dump(mode="json"),
            "files": items,
        }
        _write_json(staging / "manifest.json", manifest)
        zip_path = staging / f"{sku}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file() and path != zip_path:
                    archive.write(path, arcname=f"{sku}/{path.relative_to(staging).as_posix()}")
        with zipfile.ZipFile(zip_path) as archive:
            if archive.testzip() is not None or f"{sku}/manifest.json" not in archive.namelist():
                raise ValueError("ZIP gerado não passou na validação.")
        if target.exists():
            raise FileExistsError("A pasta do produto surgiu durante a finalização; nada foi sobrescrito.")
        staging.rename(target)
        record.update({"status": "validated", "folder_path": str(target), "package_version": version, "manifest": manifest})
        _write_json(draft / "record.json", record)
        return record
    finally:
        if staging.exists() and staging.resolve().is_relative_to(root):
            shutil.rmtree(staging)
