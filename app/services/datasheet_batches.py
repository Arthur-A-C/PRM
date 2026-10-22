"""Single-host durable datasheet queue. No catalog writes or automatic publication."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import uuid
import zipfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import pymupdf

from app.services.digitalization_storage import validate_sku
from app.services.registration_files import IMAGE_EXTENSIONS, DOCUMENT_EXTENSIONS, DOCUMENT_ROLES

log = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[2]
COMPANIES = {"choice", "portwell", "sag"}
ACTIVE = ("queued", "running")


def relative_name(value: str) -> str:
    """Validate even on Windows; never use archive names as output paths."""
    if not value or "\\" in value or ":" in value or value.startswith("/"):
        raise ValueError("Caminho relativo inválido no ZIP/CSV.")
    parts = value.rstrip("/").split("/")
    if any(p in {"", ".", ".."} or p.endswith((" ", ".")) for p in parts):
        raise ValueError("Caminho relativo inválido no ZIP/CSV.")
    for part in parts:
        validate_sku(part)
    return "/".join(parts)


def identify_product_folders(file_names, directories, root="", *, archive_name=""):
    """Shared ZIP identity rules. Returns exact SKU -> prefix, never reads disk/network.

    With archive_name supplied, a flat archive can use its exact basename as SKU.
    Mixed flat/product-folder layouts are rejected, not guessed.
    """
    file_names = {relative_name(n) for n in file_names if not n.lower().endswith(".csv")}
    directories = [relative_name(n) for n in directories]
    names = list(file_names) + directories
    if root:
        root = relative_name(root) + "/"
    else:
        first = {n.split("/")[0] for n in names if not n.lower().endswith(".csv")}
        root = next(iter(first)) + "/" if len(first) == 1 and next(iter(first)).casefold() in {"produtos", "products"} else ""
    resource_dirs = {"fotos", "imagens", "images", "documentos", "documents", "fontes", "3d"}
    top_dirs = {n.split("/")[0].casefold() for n in names if "/" in n or n in directories}
    flat = any("/" not in n for n in file_names) or (file_names and top_dirs and top_dirs <= resource_dirs)
    if archive_name and not root and flat:
        name = relative_name(archive_name)
        if "/" in name or not name.lower().endswith(".zip"):
            raise ValueError("ZIP sem pasta exige nome de arquivo SKU.zip válido, sem caminho.")
        sku = validate_sku(name[:-4])
        if top_dirs - resource_dirs or sku.casefold() in resource_dirs | {"produtos", "products"}:
            raise ValueError("ZIP mistura arquivos soltos e pastas de produto; organize uma pasta por SKU.")
        return {sku: ""}
    folders = {}
    for name in names:
        if name.lower().endswith(".csv"):
            continue
        if root and (name == root.rstrip("/") or root.startswith(name + "/")):
            continue
        if not name.startswith(root):
            raise ValueError("Arquivo/pasta fora da pasta raiz selecionada.")
        rel = name[len(root):].rstrip("/")
        if not rel:
            continue
        parts = rel.split("/")
        if len(parts) == 1 and name in file_names:
            raise ValueError("No modo pastas, coloque os arquivos dentro de uma pasta CIGAM/SKU.")
        folders.setdefault(parts[0], root + parts[0] + "/")
    return folders


def _folder_products(archive, entries, directories, settings, delimiter, company, root):
    """Interpret only uploaded ZIP entries; never inspect a configured/network folder."""
    if company not in COMPANIES:
        raise ValueError("Selecione Choice, SAG ou Portwell para identificar por pasta.")
    prefixes = identify_product_folders([i.orig_filename for i in entries.values()], directories, root)
    folders = {sku: [] for sku in prefixes}
    for key, info in entries.items():
        if key.endswith(".csv"):
            continue
        sku = next(s for s, prefix in prefixes.items() if info.orig_filename.startswith(prefix))
        name = info.orig_filename[len(prefixes[sku]):]
        folders[sku].append((key, name))
    if not folders or len(folders) > settings.batch_max_products:
        raise ValueError("Nenhuma pasta de produto ou quantidade acima do limite.")
    csvs = [k for k in entries if k.endswith(".csv")]
    if len(csvs) > 1:
        raise ValueError("Envie no máximo um CSV complementar.")
    complements = {}
    if csvs:
        try:
            reader = csv.DictReader(io.StringIO(archive.read(entries[csvs[0]]).decode("utf-8-sig")), delimiter=delimiter)
            if not reader.fieldnames or "codigo" not in reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("CSV complementar exige coluna codigo e cabeçalhos únicos.")
            for row in reader:
                if None in row or any(v is None or len(v) > 10000 for v in row.values()):
                    raise ValueError("CSV complementar com colunas/valores inválidos.")
                code = validate_sku(row["codigo"])
                if code not in folders:
                    raise ValueError("Código do CSV sem pasta de mesmo nome exato; nenhum SKU será substituído.")
                if code in complements:
                    raise ValueError("Código duplicado no CSV complementar.")
                if row.get("empresa", "").strip() and row["empresa"].strip().lower() != company:
                    raise ValueError("Empresa do CSV diverge da empresa selecionada.")
                complements[code] = row
        except (UnicodeError, csv.Error) as exc:
            raise ValueError("CSV complementar inválido; use UTF-8 e o delimitador correto.") from exc
    counts = Counter(s.casefold() for s in folders)
    products, documents = [], {}
    for index, (sku, files) in enumerate(sorted(folders.items()), 1):
        row = complements.get(sku, {})
        item = {"id": index, "codigo": sku, "nome": row.get("nome", "").strip() or sku,
                "empresa": company, "descricao": row.get("descricao", ""),
                "categoria": row.get("categoria", ""), "observacoes": row.get("observacoes", ""),
                "pdf": "", "error": "", "identification": "folder", "folder": prefixes[sku].rstrip("/"),
                "assets": [], "warnings": []}
        try:
            validate_sku(sku)
            if counts[sku.casefold()] > 1:
                raise ValueError("SKUs de pasta duplicados (inclusive diferenças de maiúsculas).")
            if not files:
                raise ValueError("Pasta vazia.")
            pdfs = [key for key, _ in files if key.endswith(".pdf")]
            supplied = row.get("datasheet_original", "").strip()
            if supplied:
                supplied = relative_name(supplied)
                candidates = [key for key, name in files if key in pdfs and
                              supplied in {entries[key].orig_filename, name}]
            else:
                candidates = [key for key, name in files if key in pdfs and
                              (PurePosixPath(name).stem == sku or DOCUMENT_ROLES[0][1].search(PurePosixPath(name).stem))]
                if not candidates and len(pdfs) == 1:
                    candidates = pdfs
            if len(candidates) != 1:
                raise ValueError("PDF de origem ausente ou ambíguo; informe datasheet_original no CSV complementar.")
            primary = candidates[0]
            images = [key for key, _ in files if PurePosixPath(key).suffix in IMAGE_EXTENSIONS]
            if len(images) > 20 or len(pdfs) > 5:
                raise ValueError("Limite por produto: 20 imagens e 5 PDFs.")
            if sum(entries[k].file_size for k, _ in files) > 60 * 1024**2:
                raise ValueError("Arquivos do produto excedem 60 MiB.")
            for number, (key, name) in enumerate(sorted(files), 1):
                content = archive.read(entries[key])
                if not content:
                    raise ValueError("Arquivo vazio na pasta do produto.")
                suffix = PurePosixPath(key).suffix
                role = next((r for r, pattern in DOCUMENT_ROLES if pattern.search(PurePosixPath(name).stem)), "other")
                if suffix == ".pdf":
                    try:
                        with pymupdf.open(stream=content, filetype="pdf") as doc:
                            if not content.startswith(b"%PDF-") or doc.needs_pass or not 1 <= len(doc) <= 100:
                                raise ValueError()
                            for page in doc:
                                page.get_text()
                    except Exception:
                        raise ValueError("PDF corrompido, protegido ou fora dos limites.") from None
                elif suffix in IMAGE_EXTENSIONS:
                    from PIL import Image
                    try:
                        with Image.open(io.BytesIO(content)) as image:
                            expected = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[suffix]
                            if image.format != expected or image.width * image.height > 40_000_000:
                                raise ValueError()
                            image.verify()
                    except Exception:
                        raise ValueError("Imagem inválida ou acima de 40 megapixels.") from None
                    role = "image"
                if key == primary:
                    role = "source_datasheet"
                item["assets"].append({"key": key, "name": name, "role": role, "bytes": len(content),
                                       "stored": f"{index}-assets/{number}{suffix}",
                                       "analyze": suffix == ".pdf" or suffix in IMAGE_EXTENSIONS})
                documents[key] = content
            item["pdf"] = entries[primary].orig_filename
            item["source_key"] = primary
            if not row.get("nome", "").strip():
                item["warnings"].append("Nome não informado: SKU usado como referência; revisar nome e descrição gerados.")
            if any(not a["analyze"] for a in item["assets"]):
                item["warnings"].append("Documentos 3D/compactados preservados no pacote, sem extração pela IA.")
        except ValueError as exc:
            item["error"] = str(exc)
        item["status"] = "invalid" if item["error"] else "pending"
        products.append(item)
    return products, documents


def parse_archive(raw: bytes, settings, delimiter=",", *, identification="csv", company="", root=""):
    if identification not in {"csv", "folder"}:
        raise ValueError("Modo de identificação inválido.")
    if delimiter not in {",", ";", "\t"}:
        raise ValueError("Delimitador deve ser vírgula, ponto e vírgula ou tabulação.")
    if len(raw) > settings.batch_upload_mib * 1024**2:
        raise ValueError("ZIP acima do limite configurado.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("ZIP inválido.") from exc
    with archive:
        entries, size, directories, seen = {}, 0, [], set()
        infos = archive.infolist()
        if len(infos) > settings.batch_max_files:
            raise ValueError("Quantidade de arquivos acima do limite.")
        for info in infos:
            # orig_filename preserves backslashes/NUL that zipfile may normalize.
            name = relative_name(info.orig_filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
                raise ValueError("Links e arquivos especiais não são permitidos.")
            if info.flag_bits & 1:
                raise ValueError("ZIP criptografado não é permitido.")
            if name in seen:
                raise ValueError("Caminhos duplicados no ZIP.")
            seen.add(name)
            if info.is_dir():
                directories.append(name)
                continue
            allowed = {".pdf", ".csv"} if identification == "csv" else IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS | {".csv"}
            if PurePosixPath(name).suffix.lower() not in allowed:
                raise ValueError("Arquivo não suportado no ZIP para o modo selecionado.")
            key = name.casefold()
            if key in entries:
                raise ValueError("Caminhos duplicados no ZIP.")
            size += info.file_size
            if size > settings.batch_expanded_mib * 1024**2 or info.file_size > 30 * 1024**2:
                raise ValueError("Tamanho descompactado acima do limite.")
            if info.file_size / max(1, info.compress_size) > settings.batch_max_ratio:
                raise ValueError("Taxa de compressão suspeita.")
            entries[key] = info
        if identification == "folder":
            return _folder_products(archive, entries, directories, settings, delimiter, company, root)
        csvs = [k for k in entries if k.endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError("Envie exatamente um CSV no ZIP.")
        try:
            text = archive.read(entries[csvs[0]]).decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            if not reader.fieldnames or not {"codigo", "nome", "empresa"} <= set(reader.fieldnames):
                raise ValueError("CSV precisa das colunas codigo, nome e empresa.")
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("CSV contém colunas duplicadas.")
            rows = []
            for row in reader:
                if len(rows) >= settings.batch_max_products:
                    raise ValueError("Quantidade de produtos acima do limite.")
                if None in row or any(v is None for v in row.values()):
                    raise ValueError("CSV com quantidade inconsistente de colunas.")
                if any(len(v) > 10000 for v in row.values()):
                    raise ValueError("Campo do CSV excede 10.000 caracteres.")
                rows.append(row)
        except (UnicodeError, csv.Error, zipfile.BadZipFile, RuntimeError) as exc:
            raise ValueError("CSV inválido; use UTF-8 e o delimitador correto.") from exc
        if not rows:
            raise ValueError("CSV sem produtos.")
        counts = Counter((r["empresa"].strip().lower(), r["codigo"].casefold()) for r in rows)
        pdfs = [k for k in entries if k.endswith(".pdf")]
        products, documents, checked = [], {}, {}
        for index, row in enumerate(rows, 1):
            item = {"id": index, "codigo": row["codigo"], "nome": row["nome"].strip(),
                    "empresa": row["empresa"].strip().lower(),
                    "descricao": row.get("descricao", ""), "categoria": row.get("categoria", ""),
                    "observacoes": row.get("observacoes", ""), "pdf": "", "error": ""}
            try:
                validate_sku(item["codigo"])
                if not item["nome"]:
                    raise ValueError("Nome obrigatório.")
                if item["empresa"] not in COMPANIES:
                    raise ValueError("Empresa deve ser Choice, SAG ou Portwell.")
                if counts[(item["empresa"], item["codigo"].casefold())] > 1:
                    raise ValueError("Código duplicado na mesma empresa.")
                supplied = row.get("datasheet_original", "").strip()
                if supplied:
                    name = relative_name(supplied).casefold()
                    candidates = [name] if name in pdfs else []
                else:
                    # Exact stem only: 10001 never matches 100010 or another variant.
                    candidates = [k for k in pdfs if PurePosixPath(k).stem.casefold() == item["codigo"].casefold()]
                if len(candidates) > 1:
                    raise ValueError("Vários PDFs candidatos; informe datasheet_original.")
                if not candidates:
                    raise ValueError("PDF correspondente não encontrado.")
                key = candidates[0]
                item["pdf"] = entries[key].filename
                if key not in checked:
                    try:
                        content = archive.read(entries[key])
                        if not content.startswith(b"%PDF-"):
                            raise ValueError("PDF inválido.")
                        with pymupdf.open(stream=content, filetype="pdf") as doc:
                            if doc.needs_pass or not 1 <= len(doc) <= 100:
                                raise ValueError("PDF protegido, vazio ou acima de 100 páginas.")
                            for page in doc:
                                page.get_text()
                        documents[key] = content
                        checked[key] = ""
                    except Exception:
                        checked[key] = "PDF corrompido, protegido ou fora dos limites."
                if checked[key]:
                    raise ValueError(checked[key])
                item["source_key"] = key
            except ValueError as exc:
                item["error"] = str(exc)
            item["status"] = "invalid" if item["error"] else "pending"
            products.append(item)
        return products, documents


class BatchStore:
    def __init__(self, settings):
        self.settings = settings
        self.root = Path(settings.batch_storage_dir)
        if not self.root.is_absolute():
            self.root = PROJECT / self.root
        self.root = self.root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS batches(
                    id TEXT PRIMARY KEY, org TEXT NOT NULL, owner TEXT NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL, expired INTEGER DEFAULT 0,
                    model TEXT DEFAULT '');
                CREATE TABLE IF NOT EXISTS items(
                    batch TEXT NOT NULL, id INTEGER NOT NULL, data TEXT NOT NULL,
                    state TEXT NOT NULL, error TEXT DEFAULT '', technical TEXT DEFAULT '',
                    attempts INTEGER DEFAULT 0, available REAL DEFAULT 0,
                    lease REAL DEFAULT 0, token TEXT DEFAULT '', output TEXT DEFAULT '',
                    PRIMARY KEY(batch,id));
                CREATE INDEX IF NOT EXISTS queue_state ON items(state,available);
            """)

    @contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.root / "queue.sqlite3", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def folder(self, batch):
        if not re.fullmatch(r"[0-9a-f]{32}", batch):
            raise LookupError("Lote não encontrado.")
        path = (self.root / batch).resolve()
        if path.parent != self.root:
            raise LookupError("Lote não encontrado.")
        return path

    def create(self, raw, org, owner, delimiter=",", *, identification="csv", company="", root=""):
        items, documents = parse_archive(raw, self.settings, delimiter, identification=identification, company=company, root=root)
        batch = uuid.uuid4().hex
        folder = self.folder(batch)
        folder.mkdir()
        try:
            for item in items:
                if item["status"] == "pending":
                    (folder / f"{item['id']}.pdf").write_bytes(documents[item.pop("source_key")])
                    for asset in item.get("assets", []):
                        path = folder / asset["stored"]
                        path.parent.mkdir(exist_ok=True)
                        path.write_bytes(documents[asset.pop("key")])
            now = time.time()
            with self.db(True) as db:
                db.execute("INSERT INTO batches(id,org,owner,created,updated) VALUES(?,?,?,?,?)",
                           (batch, str(org), str(owner), now, now))
                db.executemany("INSERT INTO items(batch,id,data,state,error) VALUES(?,?,?,?,?)",
                    [(batch, i["id"], json.dumps(i, ensure_ascii=False), i["status"], i["error"]) for i in items])
        except BaseException:
            shutil.rmtree(folder)
            raise
        return batch

    def authorize(self, db, batch, org, owner):
        self.folder(batch)
        row = db.execute("SELECT * FROM batches WHERE id=? AND org=? AND owner=?",
                         (batch, str(org), str(owner))).fetchone()
        if not row:
            raise LookupError("Lote não encontrado.")
        return row

    def detail(self, batch, org, owner):
        with self.db() as db:
            record = dict(self.authorize(db, batch, org, owner))
            items = []
            for row in db.execute("SELECT * FROM items WHERE batch=? ORDER BY id", (batch,)):
                items.append({**json.loads(row["data"]), **{k: row[k] for k in
                              ("state", "error", "technical", "attempts")}, "download": bool(row["output"]) and not record["expired"]})
        counts = Counter(i["state"] for i in items)
        finished = sum(counts[k] for k in ("done", "review", "error", "invalid"))
        state = ("expired" if record["expired"] else "running" if counts["running"] else
                 "queued" if counts["queued"] else "pending" if counts["pending"] else "finished")
        return {"id": batch, "created": record["created"], "state": state, "model": record["model"],
                "counts": dict(counts), "total": len(items), "progress": round(100 * finished / len(items)),
                "items": items}

    def history(self, org, owner):
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM batches WHERE org=? AND owner=? ORDER BY created DESC LIMIT 100",
                                          (str(org), str(owner)))]
        return [{k: v for k, v in self.detail(b, org, owner).items() if k != "items"} for b in ids]

    def enqueue(self, batch, org, owner, model, retry=False):
        if not model:
            raise ValueError("Configure DATASHEET_MODEL no servidor.")
        with self.db(True) as db:
            record = self.authorize(db, batch, org, owner)
            if record["expired"]:
                raise ValueError("Arquivos expirados; envie um novo lote.")
            if db.execute("SELECT 1 FROM items WHERE batch=? AND state IN ('queued','running')", (batch,)).fetchone():
                raise ValueError("Lote já está em processamento.")
            # Successful/review items are deliberately never queued by retry.
            db.execute("UPDATE items SET state='queued',error='',technical='',attempts=0,available=0 WHERE batch=? AND state=?",
                       (batch, "error" if retry else "pending"))
            db.execute("UPDATE batches SET model=?,updated=? WHERE id=?", (model, time.time(), batch))

    def claim(self):
        now = time.time()
        with self.db(True) as db:
            expired = db.execute("SELECT DISTINCT batch FROM items WHERE state='running' AND lease<?", (now,)).fetchall()
            db.execute("UPDATE items SET state='error',error='Processamento interrompido; confira antes de reprocessar.',"
                       "technical='LeaseExpired',token='' WHERE state='running' AND lease<?", (now,))
            for row in expired:
                db.execute("UPDATE batches SET updated=? WHERE id=?", (now, row[0]))
            count = db.execute("SELECT COUNT(*) FROM items WHERE state='running'").fetchone()[0]
            if count >= self.settings.batch_concurrency:
                return None
            row = db.execute("SELECT i.*,b.model FROM items i JOIN batches b ON b.id=i.batch "
                             "WHERE i.state='queued' AND i.available<=? AND b.expired=0 ORDER BY b.created,i.id LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            job = dict(row)
            job["token"] = uuid.uuid4().hex
            job["attempts"] += 1
            db.execute("UPDATE items SET state='running',attempts=?,token=?,lease=? WHERE batch=? AND id=?",
                       (job["attempts"], job["token"], now + self.settings.batch_timeout_seconds + 60, job["batch"], job["id"]))
            return job

    def finish(self, job, result):
        state, error = result.get("state", "error"), result.get("error", "")
        delay = 0
        if result.get("transient") and job["attempts"] < self.settings.batch_max_attempts:
            state = "queued"
            delay = min(300, 15 * 2 ** (job["attempts"] - 1))
        with self.db(True) as db:
            changed = db.execute("UPDATE items SET state=?,error=?,technical=?,available=?,output=?,token='' "
                "WHERE batch=? AND id=? AND state='running' AND token=?",
                (state, error, result.get("technical", ""), time.time() + delay, result.get("output", ""),
                 job["batch"], job["id"], job["token"])).rowcount
            if changed:
                db.execute("UPDATE batches SET updated=? WHERE id=?", (time.time(), job["batch"]))
        log.info("datasheet_batch batch=%s item=%s state=%s applied=%s", job["batch"], job["id"], state, bool(changed))

    def output_file(self, batch, item, org, owner):
        with self.db() as db:
            record = self.authorize(db, batch, org, owner)
            row = db.execute("SELECT * FROM items WHERE batch=? AND id=?", (batch, item)).fetchone()
            if record["expired"] or not row or row["state"] not in {"done", "review"} or not row["output"]:
                raise LookupError("PDF indisponível.")
            path = (self.folder(batch) / row["output"]).resolve()
            if not path.is_relative_to(self.folder(batch)) or not path.is_file():
                raise LookupError("PDF indisponível.")
            return path, json.loads(row["data"])["codigo"] + ".pdf"

    def bundle(self, batch, org, owner, stream):
        detail = self.detail(batch, org, owner)
        if detail["state"] == "expired":
            raise ValueError("Arquivos expirados.")
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            rows = []
            for item in detail["items"]:
                name = ""
                if item["download"]:
                    path, filename = self.output_file(batch, item["id"], org, owner)
                    name = item["empresa"].upper() + "/" + filename
                    archive.write(path, name)
                    analysis = path.parent / "analysis.json"
                    if analysis.is_file():
                        archive.write(analysis, f"{item['empresa'].upper()}/{item['codigo']}/analysis.json")
                # Keep sources available even when generation fails; never include credentials/backups.
                if item["state"] != "invalid":
                    for asset in item.get("assets", []):
                        source = self.folder(batch) / asset["stored"]
                        if source.is_file():
                            archive.write(source, f"{item['empresa'].upper()}/{item['codigo']}/fontes/{asset['name']}")
                rows.append([item["codigo"], item["nome"], item["empresa"], item["state"], name, item["error"]])
            for filename, selected in (("relatorio_processamento.csv", rows),
                                       ("erros.csv", [r for r in rows if r[3] in {"error", "invalid", "review"}])):
                output = io.StringIO(newline="")
                writer = csv.writer(output)
                writer.writerow(["codigo", "produto", "empresa", "status", "arquivo", "erro"])
                # Protect spreadsheet users from CSV formula injection.
                writer.writerows([("'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v) for v in row] for row in selected)
                archive.writestr(filename, output.getvalue().encode("utf-8-sig"))

    def cleanup(self, apply=False):
        cutoff = time.time() - self.settings.batch_retention_days * 86400
        removed = []
        with self.db(True) as db:
            rows = db.execute("SELECT id FROM batches b WHERE expired=0 AND updated<? AND NOT EXISTS "
                "(SELECT 1 FROM items i WHERE i.batch=b.id AND i.state IN ('queued','running'))", (cutoff,)).fetchall()
            for row in rows:
                folder = self.folder(row[0])
                removed.append(row[0])
                if apply:
                    if folder.exists():
                        shutil.rmtree(folder)
                    db.execute("UPDATE batches SET expired=1 WHERE id=?", (row[0],))
        return removed


def produce(store, job):
    """Runs only in a killable child process; uses the unchanged individual pipeline."""
    import anthropic
    from app.services.datasheet_claude import gerar_datasheet_com_claude
    data = json.loads(job["data"])
    target = store.folder(job["batch"]) / job["token"]
    target.mkdir(exist_ok=True)
    try:
        client = anthropic.Anthropic(timeout=120, max_retries=0)
        attachments = {a["name"]: (store.folder(job["batch"]) / a["stored"]).read_bytes()
                       for a in data.get("assets", []) if a["analyze"]}
        if not attachments:
            attachments = {"original.pdf": (store.folder(job["batch"]) / f"{job['id']}.pdf").read_bytes()}
        generation = gerar_datasheet_com_claude(data["empresa"], data["nome"], attachments,
            cadastro=data["descricao"], observacoes=f"Categoria informada: {data['categoria']}\n{data['observacoes']}",
            codigo=data["codigo"], model=job["model"], client=client)
        result = generation.resultado
        if not result.pdf.startswith(b"%PDF-"):
            raise ValueError("PDF gerado inválido.")
        (target / "datasheet.pdf").write_bytes(result.pdf)
        warnings = list(result.avisos) + list(result.pendencias) + data.get("warnings", [])
        (target / "analysis.json").write_text(json.dumps(generation.dados, ensure_ascii=False), encoding="utf-8")
        response = {"state": "review" if warnings else "done", "error": "; ".join(warnings)[:2000],
                    "output": f"{job['token']}/datasheet.pdf"}
    except Exception as exc:
        # Never store exception bodies, which can contain credentials or source documents.
        transient = isinstance(exc, anthropic.RateLimitError) or (
            isinstance(exc, anthropic.APIStatusError) and exc.status_code in {500, 502, 503, 504})
        response = {"state": "error", "error": "Falha temporária da IA." if transient else
                    "Não foi possível gerar. Confira fontes e configuração antes de reprocessar.",
                    "technical": type(exc).__name__, "transient": transient}
    (target / "result.json").write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")


def run_once(store):
    job = store.claim()
    if not job:
        return False
    log.info("datasheet_batch batch=%s item=%s attempt=%s", job["batch"], job["id"], job["attempts"])
    target = store.folder(job["batch"]) / job["token"]
    target.mkdir()
    (target / "job.json").write_text(json.dumps(job), encoding="utf-8")
    try:
        subprocess.run([sys.executable, str(PROJECT / "scripts" / "datasheet_batch_worker.py"),
                        "--child", str(target / "job.json")], cwd=PROJECT, check=True,
                       env={**os.environ, "PRM_BATCH_STORAGE_DIR": str(store.root)},
                       timeout=store.settings.batch_timeout_seconds,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        result = json.loads((target / "result.json").read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired:
        result = {"state": "error", "error": "Tempo limite atingido; confira antes de reprocessar.",
                  "technical": "ProductTimeout"}
    except Exception as exc:
        result = {"state": "error", "error": "Worker falhou; confira antes de reprocessar.", "technical": type(exc).__name__}
    store.finish(job, result)
    return True
