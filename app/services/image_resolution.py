"""Folder image resolution: square images in place, originals preserved in Backup-fotos.

Per image: render in memory → temporary file next to the original → verified copy of the
original into Backup-fotos (exclusive create, never overwritten) → atomic os.replace of the
original. A journal in Backup-fotos records every step, so an interruption is resumed without
losing originals, duplicating backups or converting the same image twice. Restore reverses it.
Only JPG/JPEG/PNG/WEBP are touched; symlinks/junctions and Backup-fotos are never followed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from app.services.registration_package import fit_square

BACKUP = "Backup-fotos"
JOURNAL = ".prm-resolucao.json"
TEMP = ".prm-tmp"
FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
SIZES = (1000, 1200, 1500, 1600, 2000)
MAX_FILES = 20000


def allowed_roots():
    """Folders the server process may work in. PRM_IMAGE_TOOL_ROOTS (separated by ';') or the user's home."""
    raw = os.environ.get("PRM_IMAGE_TOOL_ROOTS", "")
    roots = [Path(p.strip()) for p in raw.split(";") if p.strip()] or [Path.home()]
    return [r.resolve() for r in roots if r.is_dir()]


def resolve_root(value):
    """The selected folder must exist, be readable/writable by this process and sit inside an allowed root."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Informe a pasta.")
    path = Path(value.strip())
    if not path.is_absolute():
        raise ValueError("Informe o caminho completo da pasta.")
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        raise ValueError("Pasta não encontrada ou inacessível pelo servidor do PRM.") from None
    if not resolved.is_dir():
        raise ValueError("O caminho não é uma pasta.")
    if not any(resolved == r or resolved.is_relative_to(r) for r in allowed_roots()):
        raise ValueError("Pasta fora das raízes permitidas (PRM_IMAGE_TOOL_ROOTS).")
    if not os.access(resolved, os.R_OK | os.W_OK | os.X_OK):
        raise ValueError("O processo do PRM não tem permissão de leitura e gravação nesta pasta.")
    if resolved.name.casefold() == BACKUP.casefold():
        raise ValueError("Selecione a pasta principal, não a pasta Backup-fotos.")
    return resolved


def list_folders(value=None):
    """Directory picker: allowed roots, or the subfolders of one of them (names only, no files)."""
    if not value:
        return {"path": None, "parent": None, "folders": [{"name": str(r), "path": str(r)} for r in allowed_roots()]}
    root = resolve_root(value)
    folders = []
    with os.scandir(root) as entries:
        for entry in entries:
            if _is_link(entry) or not entry.is_dir(follow_symlinks=False) or entry.name.startswith("."):
                continue
            folders.append({"name": entry.name, "path": str(root / entry.name)})
    parent = root.parent if any(root.parent == r or root.parent.is_relative_to(r) for r in allowed_roots()) and root.parent != root else None
    return {"path": str(root), "parent": str(parent) if parent else None,
            "folders": sorted(folders, key=lambda f: f["name"].casefold())[:500]}


def _is_link(entry):
    return entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction())


def scan(root, recursive=True):
    """Relative POSIX paths of images, never inside Backup-fotos, never through links."""
    found, stack = [], [root]
    while stack:
        folder = stack.pop()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name.casefold())
        except OSError:
            continue
        for entry in entries:
            if _is_link(entry) or entry.name.startswith("."):
                continue
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                if folder == root and entry.name.casefold() == BACKUP.casefold():
                    continue
                if recursive:
                    stack.append(path)
            elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in FORMATS and TEMP not in entry.name:
                if path.resolve().is_relative_to(root):
                    found.append(path.relative_to(root).as_posix())
                    if len(found) > MAX_FILES:
                        raise ValueError(f"Mais de {MAX_FILES} imagens; selecione uma pasta menor.")
    return sorted(found, key=str.casefold)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Journal:
    """Per-root state in Backup-fotos/.prm-resolucao.json, written atomically."""

    def __init__(self, root):
        self.root = root
        self.path = root / BACKUP / JOURNAL
        self.data = {"version": 1, "entries": {}}
        if self.path.is_file():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or not isinstance(loaded.get("entries"), dict):
                raise ValueError("Registro de conversão em Backup-fotos inválido; não prosseguir automaticamente.")
            self.data = loaded

    @property
    def entries(self):
        return self.data["entries"]

    def save(self):
        self.path.parent.mkdir(exist_ok=True)
        temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + TEMP)
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporary, self.path)

    def set(self, rel, **values):
        self.entries[rel] = {**self.entries.get(rel, {}), **values, "updated": time.time()}
        self.save()


def converted(root, rel, journal):
    """True when the file on disk is exactly the output PRM wrote for it."""
    entry = journal.entries.get(rel)
    target = root / rel
    return bool(entry and entry.get("state") == "done" and target.is_file() and sha256(target) == entry.get("output_sha256"))


def preview(value, recursive=True, size=1500):
    if size not in SIZES:
        raise ValueError("Resolução não suportada.")
    root = resolve_root(value)
    images = scan(root, recursive)
    journal = Journal(root)
    done = [rel for rel in images if converted(root, rel, journal)]
    pending = [rel for rel in images if rel not in done]
    total = sum((root / rel).stat().st_size for rel in pending)
    # Backup copy of each original plus one rendered temporary at a time (generous 64 MiB margin).
    required = total + 64 * 1024 * 1024
    free = shutil.disk_usage(root).free
    folders = {str(Path(rel).parent) for rel in images}
    by_extension = {}
    for rel in images:
        by_extension[Path(rel).suffix.lower()] = by_extension.get(Path(rel).suffix.lower(), 0) + 1
    return {"root": str(root), "recursive": recursive, "size": size, "backup": str(root / BACKUP),
            "images": len(images), "pending": len(pending), "already_converted": len(done), "folders": len(folders),
            "by_extension": by_extension, "bytes": total, "required_bytes": required, "free_bytes": free,
            "space_ok": free >= required, "restorable": sum(1 for e in journal.entries.values() if e.get("state") == "done"),
            "sample": pending[:30]}


def _backup_target(root, rel, original_sha):
    """Backup-fotos/<rel>; an identical existing backup is reused, a different one gets a versioned name."""
    target = root / BACKUP / rel
    if not target.exists():
        return target, False
    if target.is_file() and sha256(target) == original_sha:
        return target, True
    for number in range(2, 1000):
        candidate = target.with_name(f"{target.stem}.backup-{number}{target.suffix}")
        if not candidate.exists():
            return candidate, False
        if candidate.is_file() and sha256(candidate) == original_sha:
            return candidate, True
    raise ValueError("Conflitos de backup demais para este arquivo.")


def _copy_verified(source, target, expected_sha):
    """Exclusive create through a temporary file; never overwrites an existing backup."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + "." + uuid.uuid4().hex + TEMP)
    try:
        with open(source, "rb") as reader, open(temporary, "xb") as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        if sha256(temporary) != expected_sha:
            raise ValueError("Backup não confere com o original.")
        try:
            # Hard link = atomic create that fails if the name exists: a backup is never overwritten.
            os.link(temporary, target)
        except FileExistsError:
            raise ValueError("Backup de mesmo nome surgiu durante a cópia; nada substituído.") from None
        except OSError:
            # Volumes without hard links (FAT/exFAT, some shares): rename refuses an existing name on Windows.
            if target.exists():
                raise ValueError("Backup de mesmo nome já existe; nada substituído.") from None
            os.rename(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def convert_one(root, rel, journal, size, stop=None):
    """Returns 'done', 'skipped' or raises ValueError. Never leaves two versions in the original folder."""
    source = root / rel
    if converted(root, rel, journal):
        return "skipped"
    entry = journal.entries.get(rel, {})
    image_format = FORMATS[source.suffix.lower()]
    original_sha = sha256(source)
    # Interrupted after the replace: the file already is the rendered output → just close the entry.
    if entry.get("state") == "replacing" and original_sha == entry.get("output_sha256"):
        journal.set(rel, state="done")
        return "done"
    content = source.read_bytes()
    try:
        rendered = fit_square(content, size=size, image_format=image_format)
    except Exception as exc:
        raise ValueError("Imagem inválida ou corrompida; mantida sem alteração.") from exc
    with Image.open(io.BytesIO(rendered)) as check:
        if check.size != (size, size):
            raise ValueError("Redimensionamento não resultou no tamanho exato; mantida sem alteração.")
    temporary = source.with_name("." + source.name + "." + uuid.uuid4().hex + TEMP)
    try:
        with open(temporary, "xb") as writer:
            writer.write(rendered)
            writer.flush()
            os.fsync(writer.fileno())
        # Original preserved before anything replaces it (reused when an identical backup exists).
        if entry.get("state") in {"backed_up", "replacing"} and entry.get("original_sha256") == original_sha and (root / entry["backup"]).is_file():
            backup = root / entry["backup"]
        else:
            backup, reused = _backup_target(root, rel, original_sha)
            if not reused:
                _copy_verified(source, backup, original_sha)
            journal.set(rel, state="backed_up", original_sha256=original_sha, backup=backup.relative_to(root).as_posix(), size=size)
        if sha256(backup) != original_sha:
            raise ValueError("Backup não confere com o original; nada substituído.")
        output_sha = hashlib.sha256(rendered).hexdigest()
        journal.set(rel, state="replacing", output_sha256=output_sha)
        if stop is not None and stop.is_set():
            raise InterruptedError()
        os.replace(temporary, source)
        journal.set(rel, state="done", error="")
        return "done"
    except InterruptedError:
        journal.set(rel, state="backed_up")
        raise
    except Exception as exc:
        # The original is untouched (os.replace is atomic) and its backup stays recorded for safety.
        current = journal.entries.get(rel, {})
        if current.get("state") == "replacing":
            journal.set(rel, state="backed_up")
        message = str(exc) if isinstance(exc, ValueError) else "Falha ao gravar a nova imagem; original mantido."
        raise ValueError(message) from None
    finally:
        if temporary.exists():
            temporary.unlink()


def restore_one(root, rel, journal):
    """Put the original back in place; the backup file is moved back, not left duplicated."""
    entry = journal.entries.get(rel) or {}
    if entry.get("state") not in {"done", "backed_up", "replacing"} or not entry.get("backup"):
        return "skipped"
    backup, target = root / entry["backup"], root / rel
    if not backup.is_file() or sha256(backup) != entry.get("original_sha256"):
        raise ValueError("Backup ausente ou alterado; restauração deste arquivo interrompida.")
    if target.exists() and sha256(target) not in {entry.get("output_sha256"), entry.get("original_sha256")}:
        raise ValueError("Imagem alterada depois da conversão; não sobrescrita pela restauração.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name("." + target.name + "." + uuid.uuid4().hex + TEMP)
    try:
        shutil.copyfile(backup, temporary)
        if sha256(temporary) != entry["original_sha256"]:
            raise ValueError("Cópia de restauração não confere; nada substituído.")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    backup.unlink()
    journal.set(rel, state="restored", output_sha256="")
    return "done"


@dataclass
class Task:
    id: str
    kind: str
    root: str
    total: int = 0
    done: int = 0
    skipped: int = 0
    failed: int = 0
    current: str = ""
    status: str = "running"
    errors: list = field(default_factory=list)
    started: float = field(default_factory=time.time)
    finished: float = 0
    stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self):
        return {"id": self.id, "kind": self.kind, "root": self.root, "total": self.total, "done": self.done,
                "skipped": self.skipped, "failed": self.failed, "current": self.current, "status": self.status,
                "errors": self.errors[-200:], "progress": round(100 * (self.done + self.skipped + self.failed) / self.total) if self.total else 100,
                "started": self.started, "finished": self.finished}


_tasks: dict[str, Task] = {}
_lock = threading.Lock()


def _run(task, worker):
    try:
        worker(task)
        task.status = "stopped" if task.stop.is_set() else "finished"
    except Exception as exc:
        task.status = "failed"
        task.errors.append({"file": "", "error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__})
    finally:
        task.current = ""
        task.finished = time.time()


def _start(kind, root, worker, *, background=True):
    with _lock:
        if any(t.root == str(root) and t.status == "running" for t in _tasks.values()):
            raise ValueError("Já existe um processamento em andamento para esta pasta.")
        task = Task(uuid.uuid4().hex, kind, str(root))
        _tasks[task.id] = task
    if background:
        threading.Thread(target=_run, args=(task, worker), daemon=True, name="prm-image-" + kind).start()
    else:
        _run(task, worker)
    return task


def start_conversion(value, *, recursive=True, size=1500, backup=True, confirmed=False, background=True):
    if not backup:
        raise ValueError("A substituição exige mover as imagens antigas para Backup-fotos.")
    if not confirmed:
        raise ValueError("Confirme a substituição das imagens.")
    summary = preview(value, recursive, size)
    if not summary["space_ok"]:
        raise ValueError("Espaço livre insuficiente para backup e processamento.")
    root = Path(summary["root"])

    def worker(task):
        images = scan(root, recursive)
        journal = Journal(root)
        task.total = len(images)
        for rel in images:
            if task.stop.is_set():
                break
            task.current = rel
            try:
                result = convert_one(root, rel, journal, size, task.stop)
                if result == "done": task.done += 1
                else: task.skipped += 1
            except InterruptedError:
                break
            except ValueError as exc:
                task.failed += 1
                task.errors.append({"file": rel, "error": str(exc)})
                journal.set(rel, error=str(exc), **({} if journal.entries.get(rel, {}).get("state") else {"state": "error"}))
    return _start("convert", root, worker, background=background)


def start_restore(value, *, confirmed=False, background=True):
    if not confirmed:
        raise ValueError("Confirme a restauração das imagens originais.")
    root = resolve_root(value)

    def worker(task):
        journal = Journal(root)
        names = [rel for rel, e in journal.entries.items() if e.get("state") in {"done", "backed_up", "replacing"}]
        task.total = len(names)
        for rel in names:
            if task.stop.is_set():
                break
            task.current = rel
            try:
                if restore_one(root, rel, journal) == "done": task.done += 1
                else: task.skipped += 1
            except ValueError as exc:
                task.failed += 1
                task.errors.append({"file": rel, "error": str(exc)})
    return _start("restore", root, worker, background=background)


def task(identifier):
    found = _tasks.get(identifier)
    if not found:
        raise LookupError("Processamento não encontrado.")
    return found


def stop(identifier):
    """Graceful: the current image finishes or is rolled back; resume skips what is done."""
    found = task(identifier)
    found.stop.set()
    return found
