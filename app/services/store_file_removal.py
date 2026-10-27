"""Remoção de arquivos de produtos WooCommerce: unlink images and/or _wcda_arquivos, never media.

Modes:
  all        unlink main image, gallery and every WCDA document
  gallery    unlink gallery images only (main image and documents preserved)
  documents  clear _wcda_arquivos only (images preserved)
  main       unlink the main image only, gallery and documents preserved, no implicit promotion

WooCommerce REST always makes images[0] the main image, so "main" is written through the
WordPress REST field featured_media=0 (gallery meta untouched) and the true main image is read
from featured_media: when it is 0, wc/v3 lists the gallery from position 0.

Authorization is based on active PRM role (gestor/desenvolvedor), organization, approved Dry Run
and explicit confirmation. The worker checks these before writes; a verified removal record (IDs and
metadata, no file copy), journal, concurrent-change checks and read-back protect every removal and restore.
Nothing is ever DELETEd: files stay in the WordPress media library.
"""
import csv
import hashlib
import io
import json
import time
import uuid
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from app.services import removal_backup as backups
from app.services import store_removal_production as production
from app.services.digitalization_storage import validate_sku
from app.services.store_config import COMPANIES
from app.services.store_document_update import KEY
from app.services.store_http import StoreAPIError, read_json
from app.services.store_publish import StagingPublisher, _legacy_protected_hash, _protected_hash
from app.services.store_registration_jobs import Journal
from app.services.store_registration_plan import PROTECTED_FIELDS

MODES = {"all": "Remover tudo", "gallery": "Remover fotos da galeria", "documents": "Remover documentos", "main": "Remover foto principal"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS removal_batches(id TEXT PRIMARY KEY,org TEXT,owner TEXT,company TEXT,origin TEXT,mode TEXT,created REAL);
CREATE TABLE IF NOT EXISTS removal_items(batch TEXT,sku TEXT,position INTEGER,state TEXT,error TEXT DEFAULT '',plan TEXT DEFAULT '{}',
  token TEXT DEFAULT '',lease REAL DEFAULT 0,PRIMARY KEY(batch,sku));
"""
QUEUED = {"preview_queued": "preview_running", "queued": "running", "restore_queued": "restoring", "reconcile_queued": "reconciling"}
# A worker that dies mid-item leaves an unknown store state: never "done", always read back first.
INTERRUPTED = {"preview_running": "uncertain", "running": "uncertain", "restoring": "restore_error", "reconciling": "uncertain"}
RESTORABLE = {"done", "uncertain", "error", "restore_error"}
MAX_SKUS = 500
# Read-back after a write: stores with object cache may answer stale data for a moment.
VERIFY_DELAYS = (0, 1, 2, 4)


class Uncertain(ValueError):
    """The write may or may not have happened: the read-back does not show the expected state."""


class Blocked(ValueError):
    """Refused before any write (policy, permission, environment, backup)."""


# --- SKUs -----------------------------------------------------------------------------------

def parse_skus(text="", sheet=None, sheet_name=""):
    """Pasted list (lines, commas, semicolons, tabs) and/or CSV/XLSX; text values, zeros preserved, exact duplicates removed."""
    from app.services.store_registration_jobs import parse_skus as parse_sheet
    values, duplicates = [], 0
    if sheet:
        values += parse_sheet(sheet, sheet_name)
    for raw in (text or "").replace(";", "\n").replace(",", "\n").replace("\t", "\n").splitlines():
        if raw.strip():
            values.append(raw.strip())
    skus = []
    for value in values:
        sku = validate_sku(value)
        if "e+" in sku.lower():
            raise ValueError("SKU em notação científica; envie como texto.")
        if sku in skus:
            duplicates += 1
        else:
            skus.append(sku)
    if not skus: raise ValueError("Informe ao menos um SKU.")
    if len(skus) > MAX_SKUS: raise ValueError(f"Limite de {MAX_SKUS} SKUs por lote.")
    return skus, duplicates


# --- Product state ------------------------------------------------------------------------

def _image(item, role):
    return {"id": item.get("id"), "name": Path(unquote(urlsplit(item.get("src") or "").path)).name or None, "role": role}


def read_state(woo, wp, product_id):
    """True main/gallery split (featured_media), WCDA documents and the hashes used for concurrency checks."""
    product = woo.product(product_id)
    view = read_json(wp, f"product/{product_id}", {"context": "edit", "_fields": "id,featured_media"})
    featured = view.get("featured_media") if isinstance(view, dict) else None
    if type(featured) is not int or view.get("id") != product_id:
        raise ValueError("Imagem principal ilegível pela API WordPress; nada alterado.")
    images = [i for i in product.get("images", []) if isinstance(i, dict)]
    if featured and (not images or images[0].get("id") != featured):
        raise ValueError("Imagem principal inconsistente entre WordPress e WooCommerce; revisão manual necessária.")
    main = _image(images[0], "main") if featured else None
    gallery = [_image(i, "gallery") for i in (images[1:] if featured else images)]
    metas = [m for m in product.get("meta_data", []) if isinstance(m, dict) and m.get("key") == KEY]
    if not metas:
        wcda = {"mode": "absent", "meta_id": None, "entries": []}
    elif len(metas) > 1 or not isinstance(metas[0].get("value"), list) or type(metas[0].get("id")) is not int:
        wcda = {"mode": "invalid", "meta_id": None, "entries": [], "reason": "Metadado _wcda_arquivos duplicado ou não é lista."}
    else:
        wcda = {"mode": "list", "meta_id": metas[0]["id"], "entries": deepcopy(metas[0]["value"])}
    state = {"product_id": product_id, "sku": product.get("sku"), "name": product.get("name"), "main": main, "gallery": gallery, "wcda": wcda}
    state["signature"] = signature(state)
    state["protected"] = _protected_hash(product)
    # Only to recognize hashes stored before term order stopped counting (journals, old Dry Runs).
    state["protected_legacy"] = _legacy_protected_hash(product)
    return state


def protected_is(state, stored):
    return bool(stored) and stored in {state["protected"], state.get("protected_legacy")}


def signature(state):
    """Images (main, gallery order) and WCDA value: what a removal reads and writes."""
    value = {"main": (state["main"] or {}).get("id"), "gallery": [g["id"] for g in state["gallery"]],
             "wcda": state["wcda"]["entries"] if state["wcda"]["mode"] == "list" else state["wcda"]["mode"]}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def documents(entries):
    return [{"position": n, "label": e.get("label"), "filename": e.get("filename"), "filesize": e.get("filesize")}
            for n, e in enumerate(entries) if isinstance(e, dict)]


# --- Dry Run ------------------------------------------------------------------------------

def plan(mode, state):
    """Writes, proposed state and lists of unlinked/preserved files. Pure: no I/O."""
    if mode not in MODES: raise ValueError("Modo de remoção inválido.")
    main, gallery, wcda = state["main"], state["gallery"], state["wcda"]
    docs = wcda["entries"]
    touch_images = mode in {"all", "gallery", "main"}
    touch_docs = mode in {"all", "documents"}
    blockers, warnings, writes = [], [], []
    after_main = None if mode in {"all", "main"} else main
    after_gallery = [] if mode in {"all", "gallery"} else gallery
    after_docs = [] if touch_docs and wcda["mode"] == "list" else docs
    if touch_docs and wcda["mode"] == "invalid":
        blockers.append(wcda["reason"] + " Documentos não podem ser limpos com segurança.")
    woo = {}
    if mode in {"all", "gallery"} and (after_main, after_gallery) != (main, gallery):
        # images[0] becomes the main image in WooCommerce: keep it explicitly when only the gallery goes.
        woo["images"] = [{"id": main["id"]}] if after_main else []
    if touch_docs and wcda["mode"] == "list" and docs:
        woo["meta_data"] = [{"id": wcda["meta_id"], "key": KEY, "value": []}]
    if woo:
        writes.append({"api": "woocommerce", "method": "PUT", "endpoint": f"products/{state['product_id']}", "payload": woo})
    if mode == "main" and main:
        # featured_media=0 removes only the main image; the gallery is not reordered or promoted.
        writes.append({"api": "wordpress", "method": "POST", "endpoint": f"product/{state['product_id']}", "payload": {"featured_media": 0}})
        if gallery:
            warnings.append("Galeria preservada sem promoção: a loja exibirá a imagem padrão no lugar da principal.")
    unlink_images = ([main] if main and not after_main else []) + [g for g in gallery if g not in after_gallery]
    unlink_docs = documents(docs) if docs and not after_docs else []
    if wcda["mode"] == "absent" and touch_docs:
        warnings.append("Produto sem metadado _wcda_arquivos: nenhum documento a remover.")
    return {
        "mode": mode, "mode_label": MODES[mode], "sku": state["sku"], "product_id": state["product_id"], "product_name": state["name"],
        "current": {"main": main, "gallery": gallery, "documents": documents(docs), "wcda": wcda["mode"]},
        "proposed": {"main": after_main, "gallery": after_gallery, "documents": documents(after_docs)},
        "unlink": {"images": unlink_images, "documents": unlink_docs},
        "preserve": {"images": [i for i in [main, *gallery] if i and i not in unlink_images],
                     "documents": [] if unlink_docs else documents(docs)},
        "writes": writes, "nothing_to_do": not writes and not blockers,
        "protected_fields": PROTECTED_FIELDS, "media_deletion": False,
        "blockers": blockers, "warnings": warnings,
        "rollback": {"main": (main or {}).get("id"), "gallery": [g["id"] for g in gallery], "wcda_meta_id": wcda["meta_id"],
                     "wcda_count": len(docs), "strategy": "Restaura somente os vínculos de imagens e/ou _wcda_arquivos anteriores; mídia nunca é excluída."},
    }


def approved(plan_):
    approval, dry = plan_.get("approval") or {}, plan_.get("dry_run") or {}
    return bool(approval) and bool(dry.get("dry_run_sha256")) and approval.get("dry_run_sha256") == dry.get("dry_run_sha256")


def journal_key(plan_):
    return f"remove:{plan_['product_id']}:{plan_['dry_run']['dry_run_sha256']}"


def restorable(jobs, record, sku, plan_):
    entry = Journal(jobs, record["org"] + "|" + record["origin"] + "|" + sku).get(journal_key(plan_)) if plan_.get("dry_run") else None
    return bool(entry and "before" in entry)


# --- Execution ----------------------------------------------------------------------------

class RemovalExecutor(StagingPublisher):
    """Removal-only client. Other publishers keep their existing authorization policies."""

    def __init__(self, company, sku, settings, policy, journal, *, transport=None, authorization_check=None):
        from app.services.registration_woo_api import WooClient, WooCredentials, credentials_for
        from app.services.store_config import secure_url
        from app.services.store_http import http_client
        if not callable(authorization_check):
            raise Blocked("Executor sem verificação de autorização; nada alterado.")
        self.authorize_write = authorization_check
        self.authorize_write()
        self.company, self.sku, self.journal, self.transport = company, sku, journal, transport
        wc, wp = credentials_for(company, settings), settings.credentials(company, "wp")
        if secure_url(wp.base_url) != secure_url(wc.base_url):
            raise ValueError("WordPress e WooCommerce com origens diferentes; gravação recusada.")
        self.woo = WooClient(WooCredentials(wp.base_url, wp.username, wp.password), transport=transport, timeout=settings.timeout)
        self.wp = http_client(wp.base_url, "wp/v2", auth=(wp.username, wp.password), transport=transport, timeout=settings.timeout)

    def state(self, product_id):
        return read_state(self.woo, self.wp, product_id)

    def permissions(self, product_id, wordpress):
        proof = self.verify_permissions(product_id)
        if wordpress:
            response = self.wp.options(f"product/{product_id}")
            allow = {m.strip().upper() for m in response.headers.get("allow", "").split(",") if m.strip()} if response.status_code == 200 else set()
            if not allow & {"POST", "PUT", "PATCH"}:
                raise ValueError(f"Permissões insuficientes para editar product/{product_id} no WordPress. Nada enviado.")
            proof["wordpress_allow"] = sorted(allow)
        return proof

    def write(self, operation):
        self.authorize_write()
        payload = operation["payload"]
        if operation["api"] == "woocommerce":
            if not payload or not set(payload) <= {"images", "meta_data"} or any(m.get("key") != KEY for m in payload.get("meta_data", [])):
                raise ValueError("Payload fora do escopo de arquivos; nada enviado.")
            response = self.woo.client.put(f"products/{int(operation['endpoint'].split('/')[1])}", json=payload)
        else:
            if set(payload) != {"featured_media"} or type(payload["featured_media"]) is not int:
                raise ValueError("Payload WordPress fora do escopo; nada enviado.")
            response = self.wp.post(f"product/{int(operation['endpoint'].split('/')[1])}", json=payload)
        return response.status_code

    def apply(self, operations):
        for operation in operations:
            try:
                status = self.write(operation)
            except httpx.RequestError:
                status = None  # lost response: decided by the read-back only
            if status not in {200, 201, None}:
                raise ValueError(f"Loja recusou a gravação (HTTP {status}); conferir pela releitura.")

    @staticmethod
    def same(state, main, gallery, wcda, protected):
        return ((state["main"] or {}).get("id") == main and [g["id"] for g in state["gallery"]] == gallery
                and (state["wcda"]["entries"] if state["wcda"]["mode"] == "list" else None) == wcda and protected_is(state, protected))

    def confirm(self, product_id, main, gallery, wcda, protected):
        """Read back (WooCommerce + WordPress) until the expected state shows up; None if it never does."""
        state = None
        for delay in VERIFY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                state = self.state(product_id)
            except (ValueError, httpx.HTTPError):
                continue
            if self.same(state, main, gallery, wcda, protected):
                return state
        return None

    def execute(self, item_plan, *, audit=lambda event, detail=None: None, backup=None, before_write=None):
        """Backup and fresh authorization are mandatory before any removal write."""
        dry = item_plan["dry_run"]
        if not approved(item_plan): raise ValueError("Dry Run não aprovado ou alterado após a aprovação.")
        if dry["blockers"]: raise ValueError("Dry Run com bloqueios; nada enviado.")
        self.authorize_write()
        product = self.woo.find_by_sku(self.sku)
        if not product or product["id"] != item_plan["product_id"] or product.get("sku") != self.sku:
            raise ValueError("Produto/SKU não corresponde à prévia; nada removido.")
        key = journal_key(item_plan)
        expected = {"main": (dry["proposed"]["main"] or {}).get("id"), "gallery": [g["id"] for g in dry["proposed"]["gallery"]]}
        previous = self.journal.get(key)
        if previous and previous.get("state") == "rejected":
            previous = None  # an explicit refusal verified as "nothing changed" may be retried after approval
        current = self.state(product["id"])
        if previous:
            if self.same(current, expected["main"], expected["gallery"], previous["after_wcda"], previous["protected"]):
                self.journal.put(key, {**previous, "state": "done"})
                return {"status": "done", "verified": True, "reconciled": True}
            raise ValueError("Remoção anterior incerta; reconciliar antes de tentar novamente.")
        if current["signature"] != item_plan["signature"] or (dry.get("protected_signature") and not protected_is(current, dry["protected_signature"])):
            raise ValueError("Produto alterado desde o Dry Run (alteração concorrente); nada removido.")
        audit("permissions_verified", self.permissions(product["id"], any(w["api"] == "wordpress" for w in dry["writes"])))
        fresh = self.state(product["id"])
        if fresh["signature"] != item_plan["signature"] or fresh["protected"] != current["protected"]:
            raise ValueError("Alteração concorrente detectada antes da gravação; nada removido.")
        if backup is None:
            raise Blocked("Backup obrigatório não configurado; nada removido.")
        saved = backup(fresh)
        if not saved or saved.get("verified") is not True:
            raise Blocked("Backup não verificado; nada removido.")
        audit("backup_verified", {k: saved[k] for k in ("files", "bytes", "images", "documents", "manifest_sha256")})
        if before_write:
            before_write()
        checked = self.state(product["id"])
        if checked["signature"] != item_plan["signature"] or checked["protected"] != fresh["protected"] or checked["sku"] != self.sku:
            raise ValueError("Alteração concorrente detectada durante o backup; nada removido.")
        after_wcda = [] if any("meta_data" in w["payload"] for w in dry["writes"]) else (fresh["wcda"]["entries"] if fresh["wcda"]["mode"] == "list" else None)
        before = {"main": (fresh["main"] or {}).get("id"), "gallery": [g["id"] for g in fresh["gallery"]],
                  "wcda": fresh["wcda"]["entries"] if fresh["wcda"]["mode"] == "list" else None, "wcda_meta_id": fresh["wcda"]["meta_id"]}
        self.journal.put(key, {"state": "sending", "mode": dry["mode"], "before": before, "after": expected,
                               "after_wcda": after_wcda, "protected": fresh["protected"], "media_deletion": False})
        audit("removal_sent", {"mode": dry["mode"], "writes": [w["api"] + ":" + ",".join(w["payload"]) for w in dry["writes"]]})
        try:
            self.apply(dry["writes"])
        except ValueError:
            unchanged = self.state(product["id"])
            if unchanged["signature"] == item_plan["signature"] and unchanged["protected"] == fresh["protected"]:
                self.journal.put(key, {**self.journal.get(key), "state": "rejected"})
            raise
        if self.confirm(product["id"], expected["main"], expected["gallery"], after_wcda, fresh["protected"]) is None:
            raise Uncertain("Remoção não confirmada pela releitura (estado ou campos protegidos divergentes); use Reconferir. Sem retry automático.")
        self.journal.put(key, {**self.journal.get(key), "state": "done"})
        audit("removal_verified", {"unlinked_images": len(dry["unlink"]["images"]), "unlinked_documents": len(dry["unlink"]["documents"])})
        return {"status": "done", "verified": True, "unlinked_images": [i["id"] for i in dry["unlink"]["images"]],
                "unlinked_documents": len(dry["unlink"]["documents"]), "media_deletion": False, "backup": saved}

    def reconcile(self, item_plan):
        """Read-only: decides an uncertain item from the store state alone."""
        key = journal_key(item_plan)
        entry = self.journal.get(key)
        if not entry or "before" not in entry:
            return {"status": "not_sent", "message": "Nada foi enviado à loja para este item; refaça o Dry Run se necessário."}
        current = self.state(item_plan["product_id"])
        after = entry["after"]
        if self.same(current, after["main"], after["gallery"], entry["after_wcda"], entry["protected"]):
            self.journal.put(key, {**entry, "state": "done"})
            return {"status": "done", "verified": True, "reconciled": True, "media_deletion": False}
        before = entry["before"]
        if self.same(current, before["main"], before["gallery"], before["wcda"], entry["protected"]):
            self.journal.put(key, {**entry, "state": "rejected"})
            return {"status": "unchanged", "message": "A loja não foi alterada; aprove novamente para executar."}
        return {"status": "diverged", "message": "Estado atual difere do previsto e do anterior; revisão manual na loja."}

    def media_exists(self, entry_id):
        """True when the media is still in the WordPress library (it can be relinked); False when deleted."""
        try:
            record = read_json(self.wp, f"media/{int(entry_id)}", {"context": "edit", "_fields": "id"})
            return isinstance(record, dict) and record.get("id") == entry_id
        except StoreAPIError as exc:
            if exc.status != 404:
                raise ValueError(f"Mídia #{entry_id} ilegível ({exc}); restauração interrompida.") from None
            return False

    def restore(self, item_plan, *, audit=lambda event, detail=None: None, backup_path=None, before_write=None):
        """Put back the previous links only if the product is exactly in the post-removal state."""
        dry = item_plan["dry_run"]
        self.authorize_write()
        if not approved(item_plan):
            raise Blocked("Dry Run não aprovado; restauração bloqueada.")
        key = journal_key(item_plan)
        entry = self.journal.get(key)
        if not entry or "before" not in entry: raise ValueError("Não há remoção registrada para restaurar.")
        done = self.journal.get("restore:" + key) or {}
        if done.get("state") == "done":
            return {"status": "restored", "reconciled": True}
        before, after = deepcopy(entry["before"]), entry["after"]
        current = self.state(item_plan["product_id"])
        if current["sku"] != self.sku:
            raise Blocked("SKU diferente do Dry Run; restauração bloqueada.")
        if self.same(current, before["main"], before["gallery"], before["wcda"], entry["protected"]):
            self.journal.put("restore:" + key, {"state": "done"})
            return {"status": "nothing_to_restore", "verified": True}
        if done.get("state") == "sending" and done.get("expected"):
            expected = done["expected"]
            if self.same(current, expected["main"], expected["gallery"], expected["wcda"], entry["protected"]):
                self.journal.put("restore:" + key, {**done, "state": "done"})
                return {"status": "restored", "verified": True, "reconciled": True, "media_deletion": False}
        if not self.same(current, after["main"], after["gallery"], entry["after_wcda"], entry["protected"]):
            raise ValueError("Restauração bloqueada: produto difere do estado pós-remoção; reconciliar manualmente.")
        # The removal record must still verify; it holds no file copy, so nothing is ever re-uploaded.
        if backup_path is None:
            raise Blocked("Registro da remoção indisponível; restauração bloqueada.")
        backups.verify(backup_path)
        audit("permissions_verified", self.permissions(item_plan["product_id"], True))
        if before_write:
            before_write()
        # Only media still in the library is relinked; media deleted meanwhile is reported, never re-uploaded.
        removed_images = [i for i in [before["main"], *before["gallery"]] if i and i not in [after["main"], *after["gallery"]]]
        missing = [i for i in removed_images if not self.media_exists(i)]
        if missing:
            audit("media_missing", {"ids": missing})
            before["main"] = None if before["main"] in missing else before["main"]
            before["gallery"] = [i for i in before["gallery"] if i not in missing]
        # WCDA entries come back exactly as they were (label, URL, filename), even if a link is broken.
        woo, operations = {}, []
        images_changed = (before["main"], before["gallery"]) != (after["main"], after["gallery"])
        if images_changed and dry["mode"] == "main":
            operations.append({"api": "wordpress", "endpoint": f"product/{item_plan['product_id']}", "payload": {"featured_media": before["main"]}})
        elif images_changed:
            if before["main"]:
                woo["images"] = [{"id": i} for i in [before["main"], *before["gallery"]]]
            elif before["gallery"]:
                # Gallery without main: WooCommerce makes images[0] main, so repeat it and clear featured_media afterwards.
                woo["images"] = [{"id": i} for i in [before["gallery"][0], *before["gallery"]]]
            else:
                woo["images"] = []
        if before["wcda"] is not None and before["wcda"] != entry["after_wcda"]:
            woo["meta_data"] = [{"id": before["wcda_meta_id"], "key": KEY, "value": before["wcda"]}]
        if woo:
            operations.insert(0, {"api": "woocommerce", "endpoint": f"products/{item_plan['product_id']}", "payload": woo})
        if images_changed and dry["mode"] != "main" and not before["main"] and before["gallery"]:
            operations.append({"api": "wordpress", "endpoint": f"product/{item_plan['product_id']}", "payload": {"featured_media": 0}})
        # Library checks take time: do not overwrite concurrent edits during recovery.
        latest = self.state(item_plan["product_id"])
        if latest["sku"] != self.sku or not self.same(latest, after["main"], after["gallery"], entry["after_wcda"], entry["protected"]):
            raise Blocked("Alteração concorrente durante a restauração; vínculos não alterados.")
        self.journal.put("restore:" + key, {"state": "sending", "expected": {"main": before["main"], "gallery": before["gallery"], "wcda": before["wcda"]}})
        audit("restore_sent", {"writes": [o["api"] for o in operations], "media_missing": len(missing)})
        self.apply(operations)
        if self.confirm(item_plan["product_id"], before["main"], before["gallery"], before["wcda"], entry["protected"]) is None:
            raise Uncertain("Restauração não confirmada pela releitura; use Reconferir ou revise manualmente.")
        self.journal.put("restore:" + key, {"state": "done"})
        audit("restored", {"main": before["main"], "gallery": len(before["gallery"]), "documents": len(before["wcda"] or [])})
        return {"status": "restored", "verified": True, "media_deletion": False, "missing_media": missing}


class RemovalReader(RemovalExecutor):
    """Read-only access for reconciliation: no policy or grant needed because it never writes."""

    def __init__(self, company, sku, settings, journal, *, transport=None):
        from app.services.registration_woo_api import WooClient, credentials_for
        from app.services.store_http import http_client
        self.company, self.sku, self.journal, self.grant, self.transport = company, sku, journal, None, transport
        wp = settings.credentials(company, "wp")
        self.woo = WooClient(credentials_for(company, settings), transport=transport, timeout=settings.timeout)
        self.wp = http_client(wp.base_url, "wp/v2", auth=(wp.username, wp.password), transport=transport, timeout=settings.timeout)

    def write(self, operation):
        raise ValueError("Reconferência é somente leitura; nada enviado.")


# --- Queue --------------------------------------------------------------------------------

class Removals:
    def __init__(self, jobs):
        self.jobs = jobs
        with jobs.db() as db:
            db.executescript(SCHEMA)

    def create(self, company, org, owner, mode, skus, settings):
        if company not in COMPANIES: raise ValueError("Empresa inválida.")
        if mode not in MODES: raise ValueError("Modo de remoção inválido.")
        origin = settings.credentials(company, "wc").base_url
        identifier = uuid.uuid4().hex
        with self.jobs.db() as db:
            db.execute("INSERT INTO removal_batches VALUES(?,?,?,?,?,?,?)", (identifier, str(org), str(owner), company, origin, mode, time.time()))
            db.executemany("INSERT INTO removal_items(batch,sku,position,state) VALUES(?,?,?,'preview_queued')",
                           [(identifier, sku, n) for n, sku in enumerate(skus)])
            self.jobs.audit(identifier, "", owner, "batch_created", {"company": company, "mode": mode, "skus": len(skus)}, db)
        return identifier

    def access(self, db, identifier, org, user, companies=()):
        """The creator, or anyone holding a removal permission for that store (needed for the four-eyes rule)."""
        row = db.execute("SELECT * FROM removal_batches WHERE id=? AND org=?", (identifier, str(org))).fetchone()
        if not row or (row["owner"] != str(user) and row["company"] not in set(companies)): raise LookupError("Lote não encontrado.")
        return dict(row)

    def record(self, identifier, org, user, companies=()):
        with self.jobs.db() as db:
            return self.access(db, identifier, org, user, companies)

    def detail(self, identifier, org, user, companies=()):
        with self.jobs.db() as db:
            record = self.access(db, identifier, org, user, companies)
            rows = db.execute("SELECT * FROM removal_items WHERE batch=? ORDER BY position", (identifier,)).fetchall()
            audits = {}
            for a in db.execute("SELECT sku,at,actor,event,detail FROM audit WHERE batch=? ORDER BY at", (identifier,)):
                audits.setdefault(a["sku"], []).append({"at": a["at"], "actor": a["actor"], "event": a["event"], "detail": json.loads(a["detail"] or "{}")})
            environment = production.operation_status(record["company"])
        items = []
        for row in rows:
            plan_ = json.loads(row["plan"])
            dry = plan_.get("dry_run")
            gate = "Pronto para executar" if approved(plan_) else "Dry Run pronto" if dry and not dry["blockers"] else "Bloqueado"
            items.append({"sku": row["sku"], "state": row["state"], "error": row["error"], "product_id": plan_.get("product_id"),
                          "dry_run": dry, "approval": plan_.get("approval"), "result": plan_.get("result"),
                          "execution": plan_.get("execution"), "backup": plan_.get("backup"),
                          "restore": plan_.get("restore"), "write_gate": gate, "audit": audits.get(row["sku"], [])[-15:],
                          "restorable": row["state"] in RESTORABLE and bool(dry) and restorable(self.jobs, record, row["sku"], plan_)})
        counts = {}
        for item in items: counts[item["state"]] = counts.get(item["state"], 0) + 1
        finished = sum(1 for i in items if i["state"] not in set(QUEUED) | set(QUEUED.values()))
        return {"id": identifier, "company": record["company"], "mode": record["mode"], "mode_label": MODES[record["mode"]],
                "owner": record["owner"], "created": record["created"], "items": items, "counts": counts, "total": len(items),
                "environment": environment, "batch_audit": audits.get("", [])[-30:],
                "progress": round(100 * finished / len(items)) if items else 100,
                "done": counts.get("done", 0) + counts.get("restored", 0),
                "skipped": counts.get("nothing", 0) + counts.get("not_found", 0) + counts.get("cancelled", 0),
                "failed": counts.get("error", 0) + counts.get("blocked", 0) + counts.get("uncertain", 0) + counts.get("restore_error", 0)}

    def history(self, org, user, companies=()):
        companies = list(companies)
        marks = ",".join("?" * len(companies))
        query = ("SELECT id,company,mode,created,owner FROM removal_batches WHERE org=? AND (owner=?"
                 + (f" OR company IN ({marks})" if companies else "") + ") ORDER BY created DESC LIMIT 100")
        with self.jobs.db() as db:
            return [dict(r) for r in db.execute(query, (str(org), str(user), *companies))]

    def approve(self, identifier, org, user, skus=None, *, companies=()):
        with self.jobs.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.access(db, identifier, org, user, companies)
            rows = [r for r in db.execute("SELECT * FROM removal_items WHERE batch=? AND state='review'", (identifier,)).fetchall()
                    if skus is None or r["sku"] in skus]
            if skus is not None and len(rows) != len(set(skus)): raise ValueError("SKU fora do lote ou sem Dry Run apto.")
            if not rows: raise ValueError("Nenhum Dry Run pronto para aprovação.")
            for row in rows:
                plan_ = json.loads(row["plan"])
                plan_["approval"] = {"by": str(user), "at": time.time(), "dry_run_sha256": plan_["dry_run"]["dry_run_sha256"], "writes_authorized": False}
                db.execute("UPDATE removal_items SET plan=? WHERE batch=? AND sku=?", (json.dumps(plan_), identifier, row["sku"]))
                self.jobs.audit(identifier, row["sku"], user, "approved", {"dry_run_sha256": plan_["approval"]["dry_run_sha256"]}, db)
            return [r["sku"] for r in rows]

    def authorize_item(self, db, record, row, plan_, user, action, authorization_session):
        validate_plan(record, row["sku"], plan_)
        with (nullcontext(authorization_session) if authorization_session is not None else production.session()) as auth_db:
            self_approved = production.check_approval(auth_db, user, record["org"], record["company"],
                                                      plan_["approval"]["by"], action)
        self.jobs.audit(record["id"], row["sku"], user, "role_authorized",
                        {"policy": "role-v1", "action": action, "self_approved": self_approved,
                         "approver": plan_["approval"]["by"], "dry_run_sha256": plan_["dry_run"]["dry_run_sha256"]}, db)

    def confirm(self, identifier, org, user, settings, skus=None, *, companies=(), confirmed=False, authorization_session=None):
        """Persist explicit confirmation and its exact scope; no external authorization is issued."""
        if not confirmed:
            raise ValueError("Confirme a execução antes de continuar.")
        with self.jobs.db() as db:
            db.execute("BEGIN IMMEDIATE")
            record = self.access(db, identifier, org, user, companies)
            if settings.organization_id != str(org) or settings.credentials(record["company"], "wc").base_url != record["origin"]:
                raise ValueError("Organização ou destino alterados; crie um novo lote.")
            rows = [r for r in db.execute("SELECT * FROM removal_items WHERE batch=? AND state='review'", (identifier,)).fetchall()
                    if approved(json.loads(r["plan"])) and (skus is None or r["sku"] in skus)]
            if skus is not None and len(rows) != len(set(skus)):
                raise ValueError("SKU fora do lote ou sem Dry Run aprovado.")
            if not rows: raise ValueError("Nenhum item aprovado apto.")
            for row in rows:
                plan_ = json.loads(row["plan"])
                self.authorize_item(db, record, row, plan_, user, "execute", authorization_session)
                plan_["execution"] = operation_request(record, row["sku"], plan_, user)
                db.execute("UPDATE removal_items SET state='queued',plan=? WHERE batch=? AND sku=?",
                           (json.dumps(plan_), identifier, row["sku"]))
                self.jobs.audit(identifier, row["sku"], user, "queued", {"mode": record["mode"], "authorization": "role-v1"}, db)
            return [r["sku"] for r in rows]

    def request_restore(self, identifier, org, user, skus=None, *, companies=(), confirmed=False, authorization_session=None):
        if not confirmed:
            raise ValueError("Confirme a restauração antes de continuar.")
        with self.jobs.db() as db:
            db.execute("BEGIN IMMEDIATE")
            record = self.access(db, identifier, org, user, companies)
            rows = [r for r in db.execute("SELECT * FROM removal_items WHERE batch=? ORDER BY position", (identifier,)).fetchall()
                    if r["state"] in RESTORABLE and (skus is None or r["sku"] in skus)]
            rows = [r for r in rows if restorable(self.jobs, record, r["sku"], json.loads(r["plan"]))]
            if skus is not None and len(rows) != len(set(skus)): raise ValueError("SKU sem remoção registrada para restaurar.")
            if not rows: raise ValueError("Nenhum item com remoção registrada para restaurar.")
            for row in rows:
                plan_ = json.loads(row["plan"])
                self.authorize_item(db, record, row, plan_, user, "restore", authorization_session)
                plan_["restore_request"] = operation_request(record, row["sku"], plan_, user)
                db.execute("UPDATE removal_items SET state='restore_queued',error='',plan=? WHERE batch=? AND sku=?",
                           (json.dumps(plan_), identifier, row["sku"]))
                self.jobs.audit(identifier, row["sku"], user, "restore_queued", {"authorization": "role-v1"}, db)
            return [r["sku"] for r in rows]

    def request_reconcile(self, identifier, org, user, skus=None, *, companies=()):
        """Read-only re-check of uncertain/error items against the store; no grant needed, nothing is written."""
        with self.jobs.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.access(db, identifier, org, user, companies)
            rows = [r for r in db.execute("SELECT * FROM removal_items WHERE batch=? AND state IN ('uncertain','error','restore_error')",
                                          (identifier,)).fetchall() if skus is None or r["sku"] in skus]
            if not rows: raise ValueError("Nenhum item incerto ou com erro para reconferir.")
            for row in rows:
                db.execute("UPDATE removal_items SET state='reconcile_queued' WHERE batch=? AND sku=?", (identifier, row["sku"]))
                self.jobs.audit(identifier, row["sku"], user, "reconcile_queued", {"previous": row["state"]}, db)
            return [r["sku"] for r in rows]

    def pause(self, identifier, org, user, *, companies=()):
        """Between products: queued items go back to review (approval kept); the running one finishes."""
        with self.jobs.db() as db:
            self.access(db, identifier, org, user, companies)
            count = db.execute("UPDATE removal_items SET state='review' WHERE batch=? AND state='queued'", (identifier,)).rowcount
            count += db.execute("UPDATE removal_items SET state='restore_error',error='Restauração pausada; confirme novamente para continuar.' WHERE batch=? AND state='restore_queued'", (identifier,)).rowcount
            self.jobs.audit(identifier, "", user, "paused", {"items": count}, db)
            return count

    def cancel(self, identifier, org, user, *, companies=()):
        with self.jobs.db() as db:
            self.access(db, identifier, org, user, companies)
            count = db.execute("UPDATE removal_items SET state='cancelled',error='Cancelado antes da execução.' WHERE batch=? AND state IN ('queued','preview_queued')",
                               (identifier,)).rowcount
            count += db.execute("UPDATE removal_items SET state='restore_error',error='Restauração cancelada antes da execução.' WHERE batch=? AND state='restore_queued'", (identifier,)).rowcount
            self.jobs.audit(identifier, "", user, "cancelled", {"items": count}, db)
            return count

    def reprocess(self, identifier, org, user, *, companies=()):
        """Fresh Dry Run for failed/blocked/not found/cancelled items. Done items are never repeated."""
        with self.jobs.db() as db:
            record = self.access(db, identifier, org, user, companies)
            # An item whose writes may have happened (journal "sending") must be reconciled, not re-planned.
            rows = db.execute("SELECT * FROM removal_items WHERE batch=? AND state IN ('error','blocked','not_found','cancelled')", (identifier,)).fetchall()
            safe = [r["sku"] for r in rows if not self._sent(record, r)]
            for sku in safe:
                db.execute("UPDATE removal_items SET state='preview_queued',error='',plan='{}' WHERE batch=? AND sku=?", (identifier, sku))
            return len(safe)

    def _sent(self, record, row):
        plan_ = json.loads(row["plan"] or "{}")
        if not plan_.get("dry_run"): return False
        entry = Journal(self.jobs, record["org"] + "|" + record["origin"] + "|" + row["sku"]).get(journal_key(plan_))
        return bool(entry and entry.get("state") in {"sending", "done"})

    def report(self, identifier, org, user, *, companies=(), people=None):
        data = self.detail(identifier, org, user, companies)
        name = lambda value: (people or {}).get(value, value or "")
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["sku", "modo", "estado", "produto_id", "principal_antes", "galeria_antes", "documentos_antes",
                         "imagens_desvinculadas", "documentos_desvinculados", "aprovado", "aprovado_por", "executado_por",
                         "ambiente", "backup_arquivos", "restaurado", "erro"])
        for item in data["items"]:
            dry = item["dry_run"] or {}
            current = dry.get("current") or {}
            row = [item["sku"], data["mode_label"], item["state"], str(item["product_id"] or ""),
                   str((current.get("main") or {}).get("id") or ""), str(len(current.get("gallery") or [])), str(len(current.get("documents") or [])),
                   " ".join(str(i["id"]) for i in (dry.get("unlink") or {}).get("images", [])), str(len((dry.get("unlink") or {}).get("documents", []))),
                   "sim" if item["approval"] else "não", name((item["approval"] or {}).get("by")), name((item["execution"] or {}).get("by")),
                   (item["execution"] or {}).get("env", ""), str((item["backup"] or {}).get("files", "")),
                   "sim" if item["state"] == "restored" else "não", item["error"]]
            writer.writerow([("'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v) for v in row])
        return output.getvalue().encode("utf-8-sig")

    def claim(self, batch=None, sku=None):
        with self.jobs.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for running, interrupted in INTERRUPTED.items():
                db.execute("UPDATE removal_items SET state=?,error='Worker interrompido; reconferir pela releitura.',token='' "
                           "WHERE state=? AND lease<?", (interrupted, running, time.time()))
            marks = ",".join("?" * len(QUEUED))
            if db.execute(f"SELECT 1 FROM removal_items WHERE state IN ({marks})", tuple(QUEUED.values())).fetchone(): return None
            where = "".join([" AND i.batch=?" if batch else "", " AND i.sku=?" if sku else ""])
            row = db.execute("SELECT i.*,b.company,b.origin,b.org,b.mode FROM removal_items i JOIN removal_batches b ON b.id=i.batch "
                             f"WHERE i.state IN ({marks})" + where + " ORDER BY b.created,i.position LIMIT 1",
                             tuple(QUEUED) + tuple(v for v in (batch, sku) if v)).fetchone()
            if not row: return None
            job = dict(row); job["token"] = uuid.uuid4().hex
            # The returned job carries its running state (preview_running, running, restoring, reconciling).
            job["state"] = QUEUED[job["state"]]
            db.execute("UPDATE removal_items SET state=?,token=?,lease=? WHERE batch=? AND sku=?",
                       (job["state"], job["token"], time.time() + 900, job["batch"], job["sku"]))
            return job

    def finish(self, job, state, plan_=None, error=""):
        with self.jobs.db() as db:
            db.execute("UPDATE removal_items SET state=?,plan=?,error=?,token='' WHERE batch=? AND sku=? AND token=?",
                       (state, json.dumps(plan_ if plan_ is not None else json.loads(job["plan"])), error, job["batch"], job["sku"], job["token"]))


# --- Worker -------------------------------------------------------------------------------

def validate_plan(record, sku, item_plan):
    dry = item_plan.get("dry_run") or {}
    if not approved(item_plan) or dry.get("blockers"):
        raise Blocked("Dry Run não aprovado ou bloqueado; nada alterado.")
    value = {k: v for k, v in dry.items() if k != "dry_run_sha256"}
    digest = hashlib.sha256(json.dumps({**value, "signature": item_plan.get("signature")},
                                      sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if digest != dry.get("dry_run_sha256"):
        raise Blocked("Hash do Dry Run inválido; refaça a prévia.")
    if (dry.get("sku") != sku or dry.get("mode") != record["mode"] or record["mode"] not in MODES
            or type(item_plan.get("product_id")) is not int or item_plan["product_id"] != dry.get("product_id")):
        raise Blocked("SKU, produto ou modo diferente do Dry Run; nada alterado.")


def operation_request(record, sku, item_plan, user):
    return {"by": str(user), "at": time.time(), "confirmed": True, "authorization": "role-v1",
            "env": "production", "org": record["org"], "company": record["company"], "origin": record["origin"],
            "sku": sku, "product_id": item_plan["product_id"], "approver": item_plan["approval"]["by"],
            "dry_run_sha256": item_plan["dry_run"]["dry_run_sha256"]}


def role_recheck(jobs, job, item_plan, action, session_factory):
    """Fresh identity and exact queued confirmation, also checked immediately before writes."""
    validate_plan(job, job["sku"], item_plan)
    key = "execution" if action == "execute" else "restore_request"
    request = item_plan.get(key) or {}
    if request.get("confirmed") is not True or request.get("authorization") != "role-v1" or not request.get("by"):
        raise Blocked("Confirmação ausente ou antiga; revise e confirme novamente pela interface.")
    expected = operation_request(job, job["sku"], item_plan, request["by"])
    if any(request.get(k) != expected[k] for k in ("org", "company", "origin", "sku", "product_id", "approver", "dry_run_sha256")):
        raise Blocked("Escopo da confirmação alterado; nada enviado.")
    with jobs.db() as db:
        row = db.execute("SELECT state,token,plan FROM removal_items WHERE batch=? AND sku=?", (job["batch"], job["sku"])).fetchone()
    if not row or row["state"] != job["state"] or row["token"] != job["token"] or json.loads(row["plan"]) != item_plan:
        raise Blocked("Operação da fila alterada ou interrompida; nada enviado.")
    with (session_factory or production.session)() as session:
        try:
            self_approved = production.check_approval(session, request["by"], job["org"], job["company"],
                                                       request["approver"], action)
        except (production.PermissionDenied, ValueError) as exc:
            raise Blocked(str(exc)) from None
    jobs.audit(job["batch"], job["sku"], request["by"], "role_verified",
               {"policy": "role-v1", "action": action, "self_approved": self_approved})


def _error_text(exc):
    return str(exc) if isinstance(exc, ValueError) and len(str(exc)) < 300 else "Falha " + type(exc).__name__ + "; confira configuração e permissões."


def process_one(jobs, settings, transport=None, *, batch=None, sku=None, session_factory=None, backup_settings=None):
    """Dry Run, execution, restore or read-only reconciliation of one product. A failure never stops the rest of the batch."""
    removals = Removals(jobs)
    job = removals.claim(batch, sku)
    if not job: return False
    executor = None
    record = {"id": job["batch"], "company": job["company"], "origin": job["origin"], "org": job["org"], "mode": job["mode"]}
    audit = lambda event, detail=None: jobs.audit(job["batch"], job["sku"], "worker", event, detail)
    item_plan = json.loads(job["plan"])
    try:
        if settings.organization_id != job["org"] or settings.credentials(job["company"], "wc").base_url != job["origin"]:
            raise Blocked("Organização ou destino mudaram; crie um novo lote.")
        journal = Journal(jobs, job["org"] + "|" + job["origin"] + "|" + job["sku"])
        if job["state"] == "preview_running":
            from app.services.registration_woo_api import WooClient, credentials_for
            from app.services.store_http import http_client
            wp_credentials = settings.credentials(job["company"], "wp")
            woo = WooClient(credentials_for(job["company"], settings), transport=transport, timeout=settings.timeout)
            wp = http_client(wp_credentials.base_url, "wp/v2", auth=(wp_credentials.username, wp_credentials.password), transport=transport, timeout=settings.timeout)
            try:
                found = woo.find_by_sku(job["sku"])
                if not found:
                    removals.finish(job, "not_found", {}, "SKU não existe na loja; nada removido.")
                    audit("not_found")
                    return True
                state = read_state(woo, wp, found["id"])
            finally:
                woo.close(); wp.close()
            if state["sku"] != job["sku"]: raise ValueError("SKU mudou durante a consulta; refaça o Dry Run.")
            dry = plan(job["mode"], state)
            dry["write_gate"] = "Dry Run pronto; revise, aprove e confirme antes de executar."
            dry["protected_signature"] = state["protected"]
            dry["dry_run_sha256"] = hashlib.sha256(json.dumps({**dry, "signature": state["signature"]}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            item_plan = {"product_id": state["product_id"], "signature": state["signature"], "dry_run": dry}
            new_state = "blocked" if dry["blockers"] else "nothing" if dry["nothing_to_do"] else "review"
            removals.finish(job, new_state, item_plan, "; ".join(dry["blockers"]) or ("Nada a remover neste modo." if new_state == "nothing" else ""))
            audit("preview_" + new_state, {"dry_run_sha256": dry["dry_run_sha256"]})
        elif job["state"] == "running":
            check = lambda: role_recheck(jobs, job, item_plan, "execute", session_factory)
            executor = RemovalExecutor(job["company"], job["sku"], settings, jobs.policy, journal,
                                       transport=transport, authorization_check=check)
            backup = lambda state: backups.capture(jobs, org=job["org"], company=job["company"], sku=job["sku"], item_plan=item_plan,
                                                   state=state, wp=executor.wp)
            result = executor.execute(item_plan, audit=audit, backup=backup, before_write=check)
            removals.finish(job, "done", {**item_plan, "result": result, "backup": result.get("backup") or item_plan.get("backup")})
            audit("done", {"verified": result.get("verified")})
        elif job["state"] == "restoring":
            check = lambda: role_recheck(jobs, job, item_plan, "restore", session_factory)
            executor = RemovalExecutor(job["company"], job["sku"], settings, jobs.policy, journal,
                                       transport=transport, authorization_check=check)
            path = backups.folder(jobs, job["org"], job["company"], job["sku"], item_plan["dry_run"]["dry_run_sha256"])
            result = executor.restore(item_plan, audit=audit, backup_path=path if (path / "manifest.json").is_file() else None,
                                      before_write=check)
            removals.finish(job, "restored", {**item_plan, "restore": result})
            audit("restore_done", {"status": result["status"]})
        else:  # reconciling: read-only
            executor = RemovalReader(job["company"], job["sku"], settings, journal, transport=transport)
            result = executor.reconcile(item_plan)
            if result["status"] == "done":
                removals.finish(job, "done", {**item_plan, "result": result})
            elif result["status"] == "unchanged":
                # Nothing changed in the store: back to review, approval cleared (a new approval and confirmation are needed).
                removals.finish(job, "review", {k: v for k, v in item_plan.items() if k not in {"approval", "execution"}}, "")
            else:
                removals.finish(job, "uncertain", None, result["message"])
            audit("reconciled", {"status": result["status"]})
    except (Blocked, backups.BackupError) as exc:
        # Identity, confirmation or backup refusal: preserve the journal for any partial recovery.
        error = _error_text(exc)
        state = "restore_error" if job["state"] == "restoring" else "blocked" if job["state"] == "running" else "error"
        removals.finish(job, state, None, error)
        audit("blocked_worker", {"error": error})
    except Uncertain as exc:
        removals.finish(job, "uncertain" if job["state"] == "running" else "restore_error", None, _error_text(exc))
        audit("uncertain", {"error": _error_text(exc)})
    except Exception as exc:
        error = _error_text(exc)
        removals.finish(job, "restore_error" if job["state"] == "restoring" else "error", None, error)
        audit("error", {"error": error})
    finally:
        if executor is not None:
            executor.close()
    return True


def restore_one(jobs, settings, batch, sku, *, actor, transport=None, backup_settings=None):
    """Legacy CLI entry point cannot bypass logged-in role authorization and confirmation."""
    raise ValueError("Use Restaurar na interface autenticada do PRM, com confirmação da operação.")
