"""Envios: files or whole folders chosen in the user's browser, copied into isolated server workspaces.

The browser never sends an absolute path (``C:\\...`` is meaningless to the server): every file
carries only its path relative to the folder the user selected. An envio belongs to one user of
one organization and lives in ``<root>/<org>/<user>/<id>``; ``files/`` holds only complete,
validated files, ``parts/`` the resumable partial uploads. A file is accepted only when its
declared size is reached exactly and its first bytes match the extension. Nothing here ever
touches the user's own computer: results are offered for download.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import threading
import time
import unicodedata
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from app.services.registration_files import DOCUMENT_EXTENSIONS, IMAGE_EXTENSIONS
from app.services.image_resolution import FORMATS

PROJECT = Path(__file__).resolve().parents[2]
MIB = 1024 * 1024
# Same extensions the batch ZIP parsers accept; anything else is skipped by the browser and refused here.
PROFILES = {
    "imagens": frozenset(FORMATS),
    "lote": frozenset(IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS | {".csv"}),
}
BACKUP = "Backup-fotos"
RESERVED = {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))}
FORBIDDEN = set('<>:"|?*')
SESSION_ID = re.compile(r"[0-9a-f]{32}")
OWNER_ID = re.compile(r"[\w-]{1,80}")
COMPRESSED = IMAGE_EXTENSIONS | {".pdf", ".zip", ".rar", ".7z"}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def clean_path(value):
    """Relative POSIX path inside the selected folder; rejects traversal, drives and names Windows cannot hold."""
    if not isinstance(value, str):
        raise ValueError("Caminho de arquivo inválido.")
    raw = value.replace("\\", "/")
    if not raw or len(raw) > 400 or raw.startswith("/") or re.match(r"[A-Za-z]:", raw) or any(ord(c) < 32 for c in raw):
        raise ValueError(f"Caminho de arquivo inválido: {value[:120]}")
    parts = raw.split("/")
    for part in parts:
        if (part in {"", ".", ".."} or part != part.strip() or part.endswith(".") or len(part) > 150
                or FORBIDDEN & set(part) or part.split(".")[0].casefold() in RESERVED):
            raise ValueError(f"Caminho de arquivo inválido: {value[:120]}")
    return "/".join(parts)


def signature_ok(suffix, head):
    """Content must match the extension: a renamed executable is not accepted as a photo or PDF."""
    if suffix == ".svg":
        if head[:2] in {b"\xff\xfe", b"\xfe\xff"}:
            head = head.decode("utf-16", "ignore").encode()
        return b'\x00' not in head and b'<' in head  # Sanitized and rendered at conversion (app.services.safe_svg).
    if suffix in {".jpg", ".jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if suffix == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if suffix == ".pdf":
        return b"%PDF-" in head[:1024]
    if suffix == ".zip":
        return head[:4] in {b"PK\x03\x04", b"PK\x05\x06"}
    if suffix == ".rar":
        return head.startswith(b"Rar!\x1a\x07")
    if suffix == ".7z":
        return head.startswith(b"7z\xbc\xaf\x27\x1c")
    if suffix == ".dwg":
        return head.startswith(b"AC10")
    if suffix in {".step", ".stp"}:
        return b"ISO-10303-21" in head
    if suffix in {".csv", ".dxf"}:
        return b"\x00" not in head
    return False


class Uploads:
    """File-system store; state is derived from disk so parallel chunk requests never rewrite a shared record."""

    def __init__(self, settings):
        self.settings = settings
        root = Path(settings.upload_storage_dir)
        self.root = (root if root.is_absolute() else PROJECT / root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # --- paths and records ------------------------------------------------------------------------

    def _owner_dir(self, org, owner):
        org, owner = str(org), str(owner)
        if not OWNER_ID.fullmatch(org) or not OWNER_ID.fullmatch(owner):
            raise LookupError("Envio não encontrado.")
        return self.root / org / owner

    def _dir(self, identifier, org, owner):
        if not isinstance(identifier, str) or not SESSION_ID.fullmatch(identifier):
            raise LookupError("Envio não encontrado.")
        folder = self._owner_dir(org, owner) / identifier
        if not (folder / "session.json").is_file():
            raise LookupError("Envio não encontrado.")
        return folder

    def _load(self, folder):
        return json.loads((folder / "session.json").read_text(encoding="utf-8"))

    def _save(self, folder, record):
        temporary = folder / f"session.{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, folder / "session.json")

    def _record(self, identifier, org, owner):
        folder = self._dir(identifier, org, owner)
        record = self._load(folder)
        # The directory already encodes the owner; the record is checked again so a moved folder cannot leak.
        if record.get("org") != str(org) or record.get("owner") != str(owner):
            raise LookupError("Envio não encontrado.")
        return folder, record

    def _lock(self, key):
        with _locks_guard:
            return _locks.setdefault(key, threading.Lock())

    # --- lifecycle ------------------------------------------------------------------------------

    def purge(self, now=None, busy=None):
        """Removes envios untouched (session.json mtime) for longer than the retention period.

        Folders left without a record (removal interrupted) expire the same way; a workspace a tool
        is still processing (``busy(files_dir)``) is kept.
        """
        limit = (now or time.time()) - self.settings.upload_retention_hours * 3600
        for folder in self.root.glob("*/*/*"):
            try:
                record = folder / "session.json"
                stamp = record.stat().st_mtime if record.is_file() else folder.stat().st_mtime
                if not folder.is_dir() or folder.is_symlink() or not SESSION_ID.fullmatch(folder.name) or stamp >= limit:
                    continue
                if busy is not None and busy(folder / "files"):
                    continue
                shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                continue

    def create(self, org, owner, profile, files, folder_name="", busy=None):
        if profile not in PROFILES:
            raise ValueError("Tipo de envio não suportado.")
        if not isinstance(files, list) or not files:
            raise ValueError("Selecione ao menos um arquivo.")
        if len(files) > self.settings.upload_max_files:
            raise ValueError(f"Mais de {self.settings.upload_max_files} arquivos; selecione uma pasta menor.")
        folder_name = clean_path(folder_name) if folder_name else ""
        if "/" in folder_name:
            raise ValueError("Nome de pasta inválido.")
        entries, seen, total = [], set(), 0
        for index, item in enumerate(files):
            path = clean_path(item.get("caminho") if isinstance(item, dict) else None)
            size = item.get("tamanho")
            if not isinstance(size, int) or isinstance(size, bool) or size < 1:
                raise ValueError(f"Arquivo vazio ou tamanho inválido: {path}")
            if size > self.settings.upload_max_file_mib * MIB:
                from app.services.upload_limits import check_size
                check_size(size,self.settings.upload_max_file_mib)
            suffix = PurePosixPath(path).suffix.lower()
            if suffix == ".svg":
                from app.services.safe_svg import MAX_BYTES
                if size > MAX_BYTES: raise ValueError(f"SVG acima de 20 MiB: {path}")
            if suffix not in PROFILES[profile]:
                raise ValueError(f"Tipo de arquivo não permitido neste módulo: {path}")
            if profile == "imagens" and path.split("/")[0].casefold() == BACKUP.casefold():
                raise ValueError("Não envie a pasta Backup-fotos; ela é criada pelo PRM no servidor.")
            # NFC + casefold: names that differ only in case or accent encoding collide on Windows/macOS.
            key = unicodedata.normalize("NFC", path).casefold()
            if key in seen:
                raise ValueError(f"Arquivo repetido (maiúsculas/minúsculas ou acentuação): {path}")
            seen.add(key)
            total += size
            entries.append({"index": index, "path": path, "size": size})
        folders = {"/".join(k.split("/")[:n]) for k in seen for n in range(1, k.count("/") + 1)}
        conflict = next((e["path"] for e in entries if unicodedata.normalize("NFC", e["path"]).casefold() in folders), None)
        if conflict:
            raise ValueError(f"Arquivo com o mesmo nome de uma pasta da seleção: {conflict}")
        if total > self.settings.upload_max_mib * MIB:
            raise ValueError(f"Seleção acima do limite de {self.settings.upload_max_mib} MiB por envio.")
        self.purge(busy=busy)
        base = self._owner_dir(org, owner)
        if base.is_dir() and sum(1 for p in base.glob("*/session.json")) >= self.settings.upload_max_open:
            raise ValueError("Há envios demais em aberto; conclua ou cancele os anteriores.")
        if shutil.disk_usage(self.root).free < total * 2 + 256 * MIB:
            raise ValueError("Espaço insuficiente no servidor para este envio.")
        identifier = uuid.uuid4().hex
        folder = base / identifier
        (folder / "parts").mkdir(parents=True)
        (folder / "files").mkdir()
        self._save(folder, {"id": identifier, "org": str(org), "owner": str(owner), "profile": profile,
                            "folder": folder_name, "files": entries, "bytes": total, "state": "uploading",
                            "created": time.time()})
        return identifier

    def _received(self, folder, entry):
        if (folder / "files" / entry["path"]).is_file():
            return entry["size"]
        part = folder / "parts" / f"{entry['index']}.part"
        return part.stat().st_size if part.is_file() else 0

    def status(self, identifier, org, owner):
        folder, record = self._record(identifier, org, owner)
        os.utime(folder / "session.json")
        files = [{"indice": e["index"], "caminho": e["path"], "tamanho": e["size"], "recebido": self._received(folder, e)}
                 for e in record["files"]]
        received = sum(f["recebido"] for f in files)
        return {"id": identifier, "perfil": record["profile"], "pasta": record["folder"], "estado": record["state"],
                "arquivos": files, "total_bytes": record["bytes"], "recebido_bytes": received,
                "completos": sum(1 for f in files if f["recebido"] == f["tamanho"]),
                "bloco_bytes": self.settings.upload_chunk_mib * MIB}

    def write_chunk(self, identifier, org, owner, index, offset, chunks):
        """Appends one chunk at ``offset``; returns (received, complete). ``chunks`` yields bytes."""
        folder, record = self._record(identifier, org, owner)
        if record["state"] != "uploading":
            raise ValueError("Este envio já foi concluído.")
        entry = next((e for e in record["files"] if e["index"] == index), None)
        if entry is None:
            raise LookupError("Arquivo não faz parte deste envio.")
        with self._lock(f"{identifier}:{index}"):
            current = self._received(folder, entry)
            if current == entry["size"]:
                return current, True
            if offset != current:
                raise OffsetMismatch(current)
            part = folder / "parts" / f"{index}.part"
            limit = self.settings.upload_chunk_mib * MIB
            written = 0
            with open(part, "ab") as handle:
                try:
                    for chunk in chunks:
                        written += len(chunk)
                        if written > limit or current + written > entry["size"]:
                            raise ValueError("Bloco maior que o permitido ou que o arquivo declarado.")
                        handle.write(chunk)
                    handle.flush()
                except (ValueError, OSError) as exc:
                    # The block is all-or-nothing: the file goes back to the last complete block.
                    handle.truncate(current)
                    if isinstance(exc, ValueError):
                        raise
                    raise ValueError("Falha ao gravar no servidor (espaço em disco?); tente retomar.") from None
            os.utime(folder / "session.json")  # an upload in progress is activity: not purged
            received = current + written
            if received < entry["size"]:
                return received, False
            with open(part, "rb") as handle:
                head = handle.read(4096)
            # SVG content is sanitized at conversion, file by file: one bad SVG never blocks the whole envio.
            if not signature_ok(PurePosixPath(entry["path"]).suffix.lower(), head):
                part.unlink()
                raise ValueError(f"Conteúdo não corresponde à extensão: {entry['path']}")
            target = folder / "files" / entry["path"]
            # Parent created first and resolved strictly: resolving a path whose folder another
            # request is creating at the same moment is unreliable on Windows.
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.parent.resolve(strict=True).is_relative_to((folder / "files").resolve(strict=True)):
                part.unlink()
                raise ValueError("Caminho de arquivo inválido.")
            os.replace(part, target)
            return received, True

    def finish(self, identifier, org, owner):
        folder, record = self._record(identifier, org, owner)
        missing = [e["path"] for e in record["files"] if not (folder / "files" / e["path"]).is_file()]
        if missing:
            raise ValueError(f"{len(missing)} arquivo(s) ainda não enviados; retome o envio.")
        record["state"] = "ready"
        self._save(folder, record)
        shutil.rmtree(folder / "parts", ignore_errors=True)
        return self.status(identifier, org, owner)

    def discard(self, identifier, org, owner, busy=None):
        """``busy(files_dir)`` lets a tool still working on the files refuse the removal."""
        folder, _ = self._record(identifier, org, owner)
        if busy is not None and busy(folder / "files"):
            raise ValueError("Há um processamento em andamento com estes arquivos; pare-o antes de descartar.")
        shutil.rmtree(folder, ignore_errors=True)

    # --- consumers ------------------------------------------------------------------------------

    def workspace(self, identifier, org, owner, profile):
        """Folder with the received files, for tools that process them in place (never the user's PC)."""
        folder, record = self._record(identifier, org, owner)
        if record["profile"] != profile:
            raise ValueError("Este envio foi feito para outro módulo.")
        if record["state"] != "ready":
            raise ValueError("Conclua o envio antes de processar.")
        os.utime(folder / "session.json")
        return folder / "files", record

    def archive(self, identifier, org, owner, limit_mib, streaming=False):
        """The envio as the ZIP the batch modules already parse; returns (bytes, name like 'Pasta.zip')."""
        files, record = self.workspace(identifier, org, owner, "lote")
        if record["bytes"] > limit_mib * MIB:
            raise ValueError(f"Seleção acima do limite de {limit_mib} MiB deste módulo.")
        import tempfile
        if shutil.disk_usage(tempfile.gettempdir()).free < record['bytes'] + 64*MIB:
            raise ValueError('Espaço em disco insuficiente para preparar ZIP.')
        stream = tempfile.TemporaryFile() if streaming else io.BytesIO()
        try:
            with zipfile.ZipFile(stream, "w") as output:
                for entry in record["files"]:
                    kind = zipfile.ZIP_STORED if PurePosixPath(entry["path"]).suffix.lower() in COMPRESSED else zipfile.ZIP_DEFLATED
                    output.write(files / entry["path"], entry["path"], compress_type=kind)
            stream.seek(0)
            return (stream if streaming else stream.getvalue()), (record["folder"] or "envio") + ".zip"
        except BaseException:
            stream.close();raise


class OffsetMismatch(Exception):
    """The client resumed from a different byte than the server holds; it must continue from ``received``."""

    def __init__(self, received):
        super().__init__(received)
        self.received = received
