"""Backup verificável antes de cada remoção, usado pela restauração.

Before any write, every image and WCDA document the removal will unlink is downloaded from the store,
validated (type, size, Content-Length), stored with its metadata (media ID, URL, MIME, title, alt text,
WCDA entry) and SHA-256, and the whole backup is re-read and re-hashed from disk. If anything cannot be
captured or does not verify, the removal is blocked: nothing is written to the store.

The PRM never deletes media. Restoring normally relinks the original media IDs; the stored files are the
safety net when someone deleted the media from the library in the meantime (they are uploaded again).
Downloads never carry store credentials and only follow HTTPS URLs on the store host (or hosts listed in
PRM_REMOVAL_BACKUP_MEDIA_HOSTS, e.g. a CDN).
"""
import hashlib
import io
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from PIL import Image
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.store_config import ROOT
from app.services.store_http import StoreAPIError, read_json

MIB = 1024 * 1024
VERSION = 1
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class BackupSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", env_prefix="PRM_REMOVAL_BACKUP_")
    max_file_mib: int = Field(200, ge=1, le=4096)
    max_item_mib: int = Field(1024, ge=1, le=20480)
    max_total_gib: int = Field(50, ge=1, le=2048)
    min_free_gib: int = Field(2, ge=0, le=1024)
    media_hosts: str = ""
    timeout_seconds: float = Field(60, ge=5, le=600)


class BackupError(ValueError):
    """Backup could not be captured or verified: the removal must not proceed."""


def root(jobs):
    return jobs.root / "removal_backups"


def folder(jobs, org, company, sku, dry_run_sha256):
    parts = [str(org), company, sku, dry_run_sha256[:32]]
    if any(not p or SAFE.sub("", p) != p or p in {".", ".."} for p in parts):
        raise BackupError("Identificação inválida para o backup.")
    return root(jobs).joinpath(*parts)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _usage(path):
    total = 0
    if path.is_dir():
        for entry in path.rglob("*"):
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
    return total


def _validate(kind, data, mime, name):
    """Content must be what it claims: decodable image, PDF/ZIP signature; never empty."""
    if not data:
        raise BackupError(f"Arquivo vazio: {name}.")
    if kind == "image":
        try:
            with Image.open(io.BytesIO(data)) as image:
                fmt = image.format
                image.verify()
        except Exception:
            raise BackupError(f"Imagem inválida ou corrompida no download: {name}.") from None
        if fmt not in IMAGE_FORMATS:
            raise BackupError(f"Formato de imagem não suportado no backup: {name}.")
        return f"image/{fmt.lower()}"
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise BackupError(f"PDF inválido no download: {name}.")
    if suffix == ".zip" and not data.startswith(b"PK"):
        raise BackupError(f"ZIP inválido no download: {name}.")
    if data[:200].lstrip().lower().startswith((b"<!doctype html", b"<html")) and suffix not in {".html", ".htm"}:
        raise BackupError(f"A loja devolveu uma página HTML no lugar do arquivo: {name}.")
    return mime or "application/octet-stream"


class Downloader:
    """Public media download: no credentials, HTTPS only, allowed hosts only, size limits, manual redirects."""

    def __init__(self, origin, settings, transport=None):
        self.settings = settings
        hosts = {urlsplit(origin).hostname} | {h.strip().lower() for h in settings.media_hosts.split(",") if h.strip()}
        self.hosts = {h for h in hosts if h}
        self.client = httpx.Client(timeout=httpx.Timeout(settings.timeout_seconds, connect=10), follow_redirects=False,
                                   verify=True, trust_env=False, transport=transport,
                                   headers={"User-Agent": "PRM-Backup/1", "Accept": "*/*"})

    def close(self):
        self.client.close()

    def allowed(self, url):
        parts = urlsplit(url or "")
        return parts.scheme == "https" and (parts.hostname or "").lower() in self.hosts and not parts.username and not parts.password

    def get(self, url, limit):
        for _ in range(4):
            if not self.allowed(url):
                raise BackupError("URL de mídia fora da loja ou sem HTTPS; configure PRM_REMOVAL_BACKUP_MEDIA_HOSTS se usar CDN.")
            try:
                with self.client.stream("GET", url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        url = str(httpx.URL(url).join(response.headers.get("location", "")))
                        continue
                    if response.status_code != 200:
                        raise BackupError(f"Download do arquivo recusado pela loja (HTTP {response.status_code}).")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > limit:
                            raise BackupError(f"Arquivo acima do limite de backup ({limit // MIB} MiB).")
                    expected = response.headers.get("content-length")
                    if expected and expected.isdigit() and int(expected) != len(data):
                        raise BackupError("Download incompleto (tamanho diferente do anunciado pela loja).")
                    return bytes(data), response.headers.get("content-type", "").split(";")[0].strip()
            except httpx.HTTPError:
                raise BackupError("Falha de rede ao baixar arquivo para o backup.") from None
        raise BackupError("Redirecionamentos demais ao baixar arquivo para o backup.")


def _write_atomic(path, data):
    # Short temporary names: Windows hosts keep the 260-character path limit.
    temporary = path.with_name(f".{uuid.uuid4().hex[:12]}.tmp")
    with open(temporary, "xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def verify(path):
    """Re-reads manifest and files from disk; any difference raises BackupError."""
    manifest_file, digest_file = path / "manifest.json", path / "manifest.sha256"
    if not manifest_file.is_file() or not digest_file.is_file():
        raise BackupError("Backup incompleto: manifesto ausente.")
    raw = manifest_file.read_bytes()
    if _sha(raw) != digest_file.read_text(encoding="ascii").strip():
        raise BackupError("Manifesto do backup alterado ou corrompido.")
    manifest = json.loads(raw)
    for entry in manifest["files"]:
        target = (path / entry["path"]).resolve()
        if not target.is_relative_to(path.resolve()) or not target.is_file() or target.is_symlink():
            raise BackupError(f"Arquivo do backup ausente: {entry['name']}.")
        data = target.read_bytes()
        if len(data) != entry["bytes"] or _sha(data) != entry["sha256"]:
            raise BackupError(f"Arquivo do backup não confere (SHA-256): {entry['name']}.")
    return manifest


def capture(jobs, *, org, company, sku, item_plan, state, wp, origin, transport=None, settings=None):
    """Download + validate + store + re-verify everything the removal will unlink. Idempotent per Dry Run."""
    settings = settings or BackupSettings()
    dry = item_plan["dry_run"]
    target = folder(jobs, org, company, sku, dry["dry_run_sha256"])
    if (target / "manifest.json").is_file():
        manifest = verify(target)
        if manifest["dry_run_sha256"] == dry["dry_run_sha256"]:
            return summary(target, manifest)
    unlink_ids = [i["id"] for i in dry["unlink"]["images"]]
    positions = {d["position"] for d in dry["unlink"]["documents"]}
    entries = state["wcda"]["entries"] if state["wcda"]["mode"] == "list" else []
    documents = [(n, e) for n, e in enumerate(entries) if n in positions and isinstance(e, dict)]
    base = root(jobs)
    base.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(base).free < settings.min_free_gib * 1024 * MIB:
        raise BackupError("Espaço livre insuficiente no servidor para o backup; remoção bloqueada.")
    used = _usage(base)
    staging = target.with_name(f"{target.name[:16]}.{uuid.uuid4().hex[:8]}.partial")
    staging.mkdir(parents=True)
    downloader = Downloader(origin, settings, transport)
    files, total = [], 0
    try:
        def store(kind, number, url, name, mime, extra):
            nonlocal total
            limit = min(settings.max_file_mib * MIB, settings.max_item_mib * MIB - total)
            data, served = downloader.get(url, limit)
            mime = _validate(kind, data, mime or served, name)
            total += len(data)
            if used + total > settings.max_total_gib * 1024 * MIB:
                raise BackupError("Limite total de backups atingido (PRM_REMOVAL_BACKUP_MAX_TOTAL_GIB); remoção bloqueada.")
            local = f"files/{kind}-{number:03d}-{SAFE.sub('_', name)[:60] or 'arquivo'}"
            (staging / "files").mkdir(exist_ok=True)
            _write_atomic(staging / local, data)
            files.append({"kind": kind, "name": name, "url": url, "mime": mime, "bytes": len(data), "sha256": _sha(data),
                          "path": local, **extra})

        for number, media_id in enumerate(unlink_ids):
            try:
                record = read_json(wp, f"media/{int(media_id)}", {"context": "edit", "_fields": "id,source_url,mime_type,title,alt_text,caption"})
            except StoreAPIError as exc:
                raise BackupError(f"Mídia #{media_id} ilegível pela API WordPress ({exc}); backup não validado.") from None
            if not isinstance(record, dict) or record.get("id") != media_id or not record.get("source_url"):
                raise BackupError(f"Registro da mídia #{media_id} inválido; backup não validado.")
            name = Path(unquote(urlsplit(record["source_url"]).path)).name or f"midia-{media_id}"
            title = record.get("title")
            store("image", number, record["source_url"], name, record.get("mime_type"),
                  {"media_id": media_id, "title": title.get("raw") if isinstance(title, dict) else title,
                   "alt_text": record.get("alt_text") or ""})
        for number, (position, entry) in enumerate(documents):
            url = entry.get("url")
            name = entry.get("filename") or Path(unquote(urlsplit(url or "").path)).name or f"documento-{position}"
            store("document", number, url, name, "", {"position": position, "entry": entry})
        manifest = {"version": VERSION, "created": time.time(), "org": str(org), "company": company, "sku": sku,
                    "product_id": item_plan["product_id"], "mode": dry["mode"], "dry_run_sha256": dry["dry_run_sha256"],
                    "before": {"main": (state["main"] or {}).get("id"), "gallery": [g["id"] for g in state["gallery"]],
                               "wcda_meta_id": state["wcda"]["meta_id"], "wcda": entries if state["wcda"]["mode"] == "list" else None},
                    "files": files, "bytes": total, "media_deletion": False}
        raw = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
        _write_atomic(staging / "manifest.json", raw)
        _write_atomic(staging / "manifest.sha256", _sha(raw).encode("ascii"))
        verify(staging)
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
        return summary(target, verify(target))
    finally:
        downloader.close()
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def summary(path, manifest):
    raw = (path / "manifest.json").read_bytes()
    return {"verified": True, "files": len(manifest["files"]), "bytes": manifest["bytes"], "manifest_sha256": _sha(raw),
            "images": sum(1 for f in manifest["files"] if f["kind"] == "image"),
            "documents": sum(1 for f in manifest["files"] if f["kind"] == "document"), "created": manifest["created"]}


def archive(jobs, org, company, sku, dry_run_sha256):
    """ZIP of one verified backup (manifest + files) for download."""
    import zipfile
    path = folder(jobs, org, company, sku, dry_run_sha256)
    verify(path)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        for entry in sorted(path.rglob("*")):
            if entry.is_file() and not entry.is_symlink():
                output.write(entry, entry.relative_to(path).as_posix())
    return stream.getvalue()


def file_bytes(path, entry):
    data = (path / entry["path"]).read_bytes()
    if _sha(data) != entry["sha256"]:
        raise BackupError(f"Arquivo do backup não confere (SHA-256): {entry['name']}.")
    return data
