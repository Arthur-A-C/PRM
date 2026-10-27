"""Registro verificável antes de cada remoção, usado pela restauração.

Before any write, the removal records what it is about to unlink: the previous main/gallery IDs, the
_wcda_arquivos entries and, best effort, each media record (ID, URL, MIME, title, alt text). The record is
written atomically with its SHA-256 and re-read from disk; if it cannot be written or does not verify,
nothing is removed.

No physical copy is made (decision of 26/10/2026: the files are kept on the company's own servers). So a
missing or broken file at the store never blocks a removal, and a restore relinks only the media that still
exist in the WordPress library; the PRM never re-uploads files and never deletes media.

Backups made before this change (version 1) may hold file copies: they are still verified on disk but no
longer used for re-uploads.
"""
import hashlib
import io
import json
import os
import re
import shutil
import time
import uuid

from app.services.store_http import StoreAPIError, read_json

VERSION = 2
SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class BackupError(ValueError):
    """Removal record could not be written or verified: the removal must not proceed."""


def root(jobs):
    return jobs.root / "removal_backups"


def folder(jobs, org, company, sku, dry_run_sha256):
    parts = [str(org), company, sku, dry_run_sha256[:32]]
    if any(not p or SAFE.sub("", p) != p or p in {".", ".."} for p in parts):
        raise BackupError("Identificação inválida para o backup.")
    return root(jobs).joinpath(*parts)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _write_atomic(path, data):
    # Short temporary names: Windows hosts keep the 260-character path limit.
    temporary = path.with_name(f".{uuid.uuid4().hex[:12]}.tmp")
    with open(temporary, "xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def verify(path):
    """Re-reads the manifest (and any version-1 file copies) from disk; any difference raises BackupError."""
    manifest_file, digest_file = path / "manifest.json", path / "manifest.sha256"
    if not manifest_file.is_file() or not digest_file.is_file():
        raise BackupError("Backup incompleto: manifesto ausente.")
    raw = manifest_file.read_bytes()
    if _sha(raw) != digest_file.read_text(encoding="ascii").strip():
        raise BackupError("Manifesto do backup alterado ou corrompido.")
    manifest = json.loads(raw)
    for entry in manifest.get("files", []):
        target = (path / entry["path"]).resolve()
        if not target.is_relative_to(path.resolve()) or not target.is_file() or target.is_symlink():
            raise BackupError(f"Arquivo do backup ausente: {entry['name']}.")
        data = target.read_bytes()
        if not data or len(data) != entry["bytes"] or _sha(data) != entry["sha256"]:
            raise BackupError(f"Arquivo do backup não confere (SHA-256): {entry['name']}.")
    return manifest


def _media_record(wp, media_id):
    """Metadata of one media item. Never blocks: a deleted or unreadable record is only noted."""
    try:
        record = read_json(wp, f"media/{int(media_id)}", {"context": "edit", "_fields": "id,source_url,mime_type,title,alt_text"})
    except StoreAPIError as exc:
        return {"media_id": media_id, "status": "missing" if exc.status == 404 else "unreadable"}
    except Exception:
        return {"media_id": media_id, "status": "unreadable"}
    if not isinstance(record, dict) or record.get("id") != media_id:
        return {"media_id": media_id, "status": "unreadable"}
    title = record.get("title")
    return {"media_id": media_id, "status": "present", "url": record.get("source_url"), "mime": record.get("mime_type"),
            "title": title.get("raw") if isinstance(title, dict) else title, "alt_text": record.get("alt_text") or ""}


def capture(jobs, *, org, company, sku, item_plan, state, wp, **_):
    """Record (no file download) of everything the removal will unlink. Idempotent per Dry Run."""
    dry = item_plan["dry_run"]
    target = folder(jobs, org, company, sku, dry["dry_run_sha256"])
    if (target / "manifest.json").is_file():
        manifest = verify(target)
        if manifest["dry_run_sha256"] == dry["dry_run_sha256"]:
            return summary(target, manifest)
    positions = {d["position"] for d in dry["unlink"]["documents"]}
    entries = state["wcda"]["entries"] if state["wcda"]["mode"] == "list" else []
    root(jobs).mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f"{target.name[:16]}.{uuid.uuid4().hex[:8]}.partial")
    staging.mkdir(parents=True)
    try:
        media = [_media_record(wp, i["id"]) for i in dry["unlink"]["images"]]
        documents = [{"position": n, "entry": e} for n, e in enumerate(entries) if n in positions and isinstance(e, dict)]
        manifest = {"version": VERSION, "created": time.time(), "org": str(org), "company": company, "sku": sku,
                    "product_id": item_plan["product_id"], "mode": dry["mode"], "dry_run_sha256": dry["dry_run_sha256"],
                    "before": {"main": (state["main"] or {}).get("id"), "gallery": [g["id"] for g in state["gallery"]],
                               "wcda_meta_id": state["wcda"]["meta_id"], "wcda": entries if state["wcda"]["mode"] == "list" else None},
                    "media": media, "documents": documents, "files": [], "bytes": 0,
                    "physical_copy": False, "media_deletion": False}
        raw = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
        _write_atomic(staging / "manifest.json", raw)
        _write_atomic(staging / "manifest.sha256", _sha(raw).encode("ascii"))
        verify(staging)
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
        return summary(target, verify(target))
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def summary(path, manifest):
    raw = (path / "manifest.json").read_bytes()
    files = manifest.get("files", [])
    if manifest.get("version", 1) >= 2:
        images, documents = len(manifest["media"]), len(manifest["documents"])
    else:
        images = sum(1 for f in files if f["kind"] == "image")
        documents = sum(1 for f in files if f["kind"] == "document")
    return {"verified": True, "files": len(files), "bytes": manifest["bytes"], "manifest_sha256": _sha(raw),
            "images": images, "documents": documents, "physical_copy": bool(files), "created": manifest["created"],
            "missing_media": [m["media_id"] for m in manifest.get("media", []) if m["status"] == "missing"]}


def archive(jobs, org, company, sku, dry_run_sha256):
    """ZIP of one verified backup (manifest, plus file copies of version-1 backups) for download."""
    import zipfile
    path = folder(jobs, org, company, sku, dry_run_sha256)
    verify(path)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        for entry in sorted(path.rglob("*")):
            if entry.is_file() and not entry.is_symlink():
                output.write(entry, entry.relative_to(path).as_posix())
    return stream.getvalue()
