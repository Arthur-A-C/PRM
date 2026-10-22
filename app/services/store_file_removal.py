"""Remoção de arquivos de produtos WooCommerce: unlink images and/or _wcda_arquivos, never media.

Modes:
  all        unlink main image, gallery and every WCDA document
  gallery    unlink gallery images only (main image and documents preserved)
  documents  clear _wcda_arquivos only (images preserved)
  main       unlink the main image only, gallery and documents preserved, no implicit promotion

WooCommerce REST always makes images[0] the main image, so "main" is written through the
WordPress REST field featured_media=0 (gallery meta untouched) and the true main image is read
from featured_media: when it is 0, wc/v3 lists the gallery from position 0.

Queue, approval, single-use grants (store/SKU/product/mode/Dry Run hash), staging policy,
journal, audit and the commercial-field verification are the ones used by Cadastro via API.
Nothing is ever DELETEd: files stay in the WordPress media library.
"""
import csv
import hashlib
import io
import json
import time
import uuid
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from app.services import store_publish_grant as grants
from app.services.digitalization_storage import validate_sku
from app.services.store_config import COMPANIES
from app.services.store_document_update import KEY
from app.services.store_http import read_json
from app.services.store_publish import StagingPublisher, _protected_hash
from app.services.store_registration_jobs import Journal
from app.services.store_registration_plan import PROTECTED_FIELDS

MODES = {"all": "Remover tudo", "gallery": "Remover fotos da galeria", "documents": "Remover documentos", "main": "Remover foto principal"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS removal_batches(id TEXT PRIMARY KEY,org TEXT,owner TEXT,company TEXT,origin TEXT,mode TEXT,created REAL);
CREATE TABLE IF NOT EXISTS removal_items(batch TEXT,sku TEXT,position INTEGER,state TEXT,error TEXT DEFAULT '',plan TEXT DEFAULT '{}',
  token TEXT DEFAULT '',lease REAL DEFAULT 0,PRIMARY KEY(batch,sku));
"""
ACTIVE = ("preview_running", "running")
MAX_SKUS = 500


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
    return state


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
    return bool(approval) and approval.get("dry_run_sha256") == dry.get("dry_run_sha256")


def journal_key(plan_):
    return f"remove:{plan_['product_id']}:{plan_['dry_run']['dry_run_sha256']}"


def restorable(jobs, record, sku, plan_):
    entry = Journal(jobs, record["org"] + "|" + record["origin"] + "|" + sku).get(journal_key(plan_)) if plan_.get("dry_run") else None
    return bool(entry and "before" in entry)


# --- Execution ----------------------------------------------------------------------------

class RemovalExecutor(StagingPublisher):
    """Same authentication, grant check and permission proof as the file publisher; writes only images/_wcda_arquivos."""

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
                and (state["wcda"]["entries"] if state["wcda"]["mode"] == "list" else None) == wcda and state["protected"] == protected)

    def execute(self, item_plan, *, audit=lambda event, detail=None: None):
        dry = item_plan["dry_run"]
        if not approved(item_plan): raise ValueError("Dry Run não aprovado ou alterado após a aprovação.")
        if dry["blockers"]: raise ValueError("Dry Run com bloqueios; nada enviado.")
        if self.grant:
            grants.check(self.grant, company=self.company, origin=self.woo.credentials.base_url, sku=self.sku,
                         product_id=item_plan["product_id"], dry_run_sha256=dry["dry_run_sha256"], purpose="remove_" + dry["mode"])
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
        if current["signature"] != item_plan["signature"]:
            raise ValueError("Produto alterado desde o Dry Run (alteração concorrente); nada removido.")
        audit("permissions_verified", self.permissions(product["id"], any(w["api"] == "wordpress" for w in dry["writes"])))
        fresh = self.state(product["id"])
        if fresh["signature"] != item_plan["signature"]:
            raise ValueError("Alteração concorrente detectada antes da gravação; nada removido.")
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
        verified = self.state(product["id"])
        if not self.same(verified, expected["main"], expected["gallery"], after_wcda, fresh["protected"]):
            raise ValueError("Remoção não confirmada pela releitura (estado ou campos protegidos divergentes); sem retry automático.")
        self.journal.put(key, {**self.journal.get(key), "state": "done"})
        audit("removal_verified", {"unlinked_images": len(dry["unlink"]["images"]), "unlinked_documents": len(dry["unlink"]["documents"])})
        return {"status": "done", "verified": True, "unlinked_images": [i["id"] for i in dry["unlink"]["images"]],
                "unlinked_documents": len(dry["unlink"]["documents"]), "media_deletion": False}

    def restore(self, item_plan, *, audit=lambda event, detail=None: None):
        """Put back the previous links only if the product is exactly in the post-removal state."""
        dry = item_plan["dry_run"]
        if self.grant:
            grants.check(self.grant, company=self.company, origin=self.woo.credentials.base_url, sku=self.sku,
                         product_id=item_plan["product_id"], dry_run_sha256=dry["dry_run_sha256"], purpose="restore_" + dry["mode"])
        key = journal_key(item_plan)
        entry = self.journal.get(key)
        if not entry or "before" not in entry: raise ValueError("Não há remoção registrada para restaurar.")
        if (self.journal.get("restore:" + key) or {}).get("state") == "done":
            return {"status": "restored", "reconciled": True}
        before, after = entry["before"], entry["after"]
        current = self.state(item_plan["product_id"])
        if self.same(current, before["main"], before["gallery"], before["wcda"], entry["protected"]):
            self.journal.put("restore:" + key, {"state": "done"})
            return {"status": "nothing_to_restore", "verified": True}
        if not self.same(current, after["main"], after["gallery"], entry["after_wcda"], entry["protected"]):
            raise ValueError("Restauração bloqueada: produto difere do estado pós-remoção; reconciliar manualmente.")
        audit("permissions_verified", self.permissions(item_plan["product_id"], True))
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
        self.journal.put("restore:" + key, {"state": "sending"})
        audit("restore_sent", {"writes": [o["api"] for o in operations]})
        self.apply(operations)
        verified = self.state(item_plan["product_id"])
        if not self.same(verified, before["main"], before["gallery"], before["wcda"], entry["protected"]):
            raise ValueError("Restauração não confirmada pela releitura; reconciliar manualmente.")
        self.journal.put("restore:" + key, {"state": "done"})
        audit("restored", {"main": before["main"], "gallery": len(before["gallery"]), "documents": len(before["wcda"] or [])})
        return {"status": "restored", "verified": True, "media_deletion": False}


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
        return identifier

    def access(self, db, identifier, org, owner):
        row = db.execute("SELECT * FROM removal_batches WHERE id=? AND org=? AND owner=?", (identifier, str(org), str(owner))).fetchone()
        if not row: raise LookupError("Lote não encontrado.")
        return dict(row)

    def gate(self, record, sku, plan_, db=None):
        """Staging policy, or a valid single-use grant for this exact store/SKU/product/mode/Dry Run."""
        try:
            self.jobs.policy.authorize(record["origin"], sku)
            return None
        except ValueError as exc:
            grant = grants.find(self.jobs, company=record["company"], origin=record["origin"], sku=sku, product_id=plan_.get("product_id"),
                                dry_run_sha256=(plan_.get("dry_run") or {}).get("dry_run_sha256"), purpose="remove_" + record["mode"],
                                batch=record["id"], db=db)
            if grant: return grant
            raise ValueError(f"{exc} Sem liberação de homologação válida para este item.") from None

    def detail(self, identifier, org, owner):
        with self.jobs.db() as db:
            record = self.access(db, identifier, org, owner)
            rows = db.execute("SELECT * FROM removal_items WHERE batch=? ORDER BY position", (identifier,)).fetchall()
            audits = {}
            for a in db.execute("SELECT sku,at,actor,event FROM audit WHERE batch=? ORDER BY at", (identifier,)):
                audits.setdefault(a["sku"], []).append({"at": a["at"], "actor": a["actor"], "event": a["event"]})
        items = []
        for row in rows:
            plan_ = json.loads(row["plan"])
            dry = plan_.get("dry_run")
            try:
                gate = "Liberado" if dry and not dry["blockers"] and (self.gate(record, row["sku"], plan_) or True) else None
            except ValueError as exc:
                gate = str(exc)
            items.append({"sku": row["sku"], "state": row["state"], "error": row["error"], "product_id": plan_.get("product_id"),
                          "dry_run": dry, "approval": plan_.get("approval"), "result": plan_.get("result"),
                          "restore": plan_.get("restore"), "write_gate": gate, "audit": audits.get(row["sku"], [])[-10:]})
        counts = {}
        for item in items: counts[item["state"]] = counts.get(item["state"], 0) + 1
        finished = sum(1 for i in items if i["state"] not in {"preview_queued", "preview_running", "queued", "running"})
        return {"id": identifier, "company": record["company"], "mode": record["mode"], "mode_label": MODES[record["mode"]],
                "created": record["created"], "items": items, "counts": counts, "total": len(items),
                "progress": round(100 * finished / len(items)) if items else 100,
                "done": counts.get("done", 0), "skipped": counts.get("nothing", 0) + counts.get("not_found", 0) + counts.get("cancelled", 0),
                "failed": counts.get("error", 0) + counts.get("blocked", 0) + counts.get("uncertain", 0)}

    def history(self, org, owner):
        with self.jobs.db() as db:
            return [dict(r) for r in db.execute("SELECT id,company,mode,created FROM removal_batches WHERE org=? AND owner=? ORDER BY created DESC LIMIT 100",
                                                (str(org), str(owner)))]

    def approve(self, identifier, org, owner, skus=None):
        with self.jobs.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.access(db, identifier, org, owner)
            rows = [r for r in db.execute("SELECT * FROM removal_items WHERE batch=? AND state='review'", (identifier,)).fetchall()
                    if skus is None or r["sku"] in skus]
            if skus is not None and len(rows) != len(set(skus)): raise ValueError("SKU fora do lote ou sem Dry Run apto.")
            if not rows: raise ValueError("Nenhum Dry Run pronto para aprovação.")
            for row in rows:
                plan_ = json.loads(row["plan"])
                plan_["approval"] = {"by": str(owner), "at": time.time(), "dry_run_sha256": plan_["dry_run"]["dry_run_sha256"], "writes_authorized": False}
                db.execute("UPDATE removal_items SET plan=? WHERE batch=? AND sku=?", (json.dumps(plan_), identifier, row["sku"]))
                self.jobs.audit(identifier, row["sku"], owner, "approved", {"dry_run_sha256": plan_["approval"]["dry_run_sha256"]}, db)
            return [r["sku"] for r in rows]

    def confirm(self, identifier, org, owner, settings, skus=None):
        with self.jobs.db() as db:
            db.execute("BEGIN IMMEDIATE")
            record = self.access(db, identifier, org, owner)
            if settings.credentials(record["company"], "wc").base_url != record["origin"]:
                raise ValueError("Destino alterado; crie um novo lote.")
            rows = [r for r in db.execute("SELECT * FROM removal_items WHERE batch=? AND state='review'", (identifier,)).fetchall()
                    if approved(json.loads(r["plan"])) and (skus is None or r["sku"] in skus)]
            if not rows: raise ValueError("Nenhum item aprovado apto.")
            for row in rows:
                self.gate(record, row["sku"], json.loads(row["plan"]), db)
            for row in rows:
                db.execute("UPDATE removal_items SET state='queued' WHERE batch=? AND sku=? AND state='review'", (identifier, row["sku"]))
                self.jobs.audit(identifier, row["sku"], owner, "queued", {"mode": record["mode"]}, db)
            return [r["sku"] for r in rows]

    def pause(self, identifier, org, owner):
        """Between products: queued items go back to review (approval kept); the running one finishes."""
        with self.jobs.db() as db:
            self.access(db, identifier, org, owner)
            return db.execute("UPDATE removal_items SET state='review' WHERE batch=? AND state='queued'", (identifier,)).rowcount

    def cancel(self, identifier, org, owner):
        with self.jobs.db() as db:
            self.access(db, identifier, org, owner)
            return db.execute("UPDATE removal_items SET state='cancelled',error='Cancelado antes da execução.' WHERE batch=? AND state IN ('queued','preview_queued')",
                              (identifier,)).rowcount

    def reprocess(self, identifier, org, owner):
        """Fresh Dry Run for failed/blocked/not found/cancelled items. Done items are never repeated."""
        with self.jobs.db() as db:
            self.access(db, identifier, org, owner)
            return db.execute("UPDATE removal_items SET state='preview_queued',error='',plan='{}' WHERE batch=? AND state IN ('error','blocked','not_found','cancelled')",
                              (identifier,)).rowcount

    def report(self, identifier, org, owner):
        data = self.detail(identifier, org, owner)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["sku", "modo", "estado", "produto_id", "principal_antes", "galeria_antes", "documentos_antes",
                         "imagens_desvinculadas", "documentos_desvinculados", "aprovado", "erro"])
        for item in data["items"]:
            dry = item["dry_run"] or {}
            current = dry.get("current") or {}
            row = [item["sku"], data["mode_label"], item["state"], str(item["product_id"] or ""),
                   str((current.get("main") or {}).get("id") or ""), str(len(current.get("gallery") or [])), str(len(current.get("documents") or [])),
                   " ".join(str(i["id"]) for i in (dry.get("unlink") or {}).get("images", [])), str(len((dry.get("unlink") or {}).get("documents", []))),
                   "sim" if item["approval"] else "não", item["error"]]
            writer.writerow([("'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v) for v in row])
        return output.getvalue().encode("utf-8-sig")

    def claim(self, batch=None, sku=None):
        with self.jobs.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE removal_items SET state='uncertain',error='Worker interrompido; reconciliar pela releitura.',token='' "
                       "WHERE state IN ('preview_running','running') AND lease<?", (time.time(),))
            if db.execute("SELECT 1 FROM removal_items WHERE state IN ('preview_running','running')").fetchone(): return None
            where = "".join([" AND i.batch=?" if batch else "", " AND i.sku=?" if sku else ""])
            row = db.execute("SELECT i.*,b.company,b.origin,b.org,b.mode FROM removal_items i JOIN removal_batches b ON b.id=i.batch "
                             "WHERE i.state IN ('preview_queued','queued')" + where + " ORDER BY b.created,i.position LIMIT 1",
                             tuple(v for v in (batch, sku) if v)).fetchone()
            if not row: return None
            job = dict(row); job["token"] = uuid.uuid4().hex
            db.execute("UPDATE removal_items SET state=?,token=?,lease=? WHERE batch=? AND sku=?",
                       ("preview_running" if job["state"] == "preview_queued" else "running", job["token"], time.time() + 900, job["batch"], job["sku"]))
            return job

    def finish(self, job, state, plan_=None, error=""):
        with self.jobs.db() as db:
            db.execute("UPDATE removal_items SET state=?,plan=?,error=?,token='' WHERE batch=? AND sku=? AND token=?",
                       (state, json.dumps(plan_ if plan_ is not None else json.loads(job["plan"])), error, job["batch"], job["sku"], job["token"]))


def process_one(jobs, settings, transport=None, *, batch=None, sku=None):
    """Dry Run or execution of one product. A failure never stops the rest of the batch."""
    removals = Removals(jobs)
    job = removals.claim(batch, sku)
    if not job: return False
    executor = None
    record = {"id": job["batch"], "company": job["company"], "origin": job["origin"], "org": job["org"], "mode": job["mode"]}
    audit = lambda event, detail=None: jobs.audit(job["batch"], job["sku"], "worker", event, detail)
    try:
        if settings.organization_id != job["org"] or settings.credentials(job["company"], "wc").base_url != job["origin"]:
            raise ValueError("Organização ou destino mudaram; crie um novo lote.")
        journal = Journal(jobs, job["org"] + "|" + job["origin"] + "|" + job["sku"])
        if job["state"] == "preview_queued":
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
            try:
                jobs.policy.authorize(job["origin"], job["sku"])
                dry["write_gate"] = "Staging autorizado para este SKU; execução exige aprovação e confirmação."
            except ValueError as exc:
                dry["write_gate"] = "Política de gravação: " + str(exc)
            dry["dry_run_sha256"] = hashlib.sha256(json.dumps({**dry, "signature": state["signature"]}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            item_plan = {"product_id": state["product_id"], "signature": state["signature"], "dry_run": dry}
            new_state = "blocked" if dry["blockers"] else "nothing" if dry["nothing_to_do"] else "review"
            removals.finish(job, new_state, item_plan, "; ".join(dry["blockers"]) or ("Nada a remover neste modo." if new_state == "nothing" else ""))
            audit("preview_" + new_state, {"dry_run_sha256": dry["dry_run_sha256"]})
        else:
            item_plan = json.loads(job["plan"])
            grant = removals.gate(record, job["sku"], item_plan)
            # Single use: consumed before the first write, so a retry always needs a new grant.
            if grant and not grants.consume(jobs, grant):
                raise ValueError("Liberação expirada ou já utilizada; nada removido.")
            executor = RemovalExecutor(job["company"], job["sku"], settings, jobs.policy, journal, transport=transport, grant=grant)
            result = executor.execute(item_plan, audit=audit)
            removals.finish(job, "done", {**item_plan, "result": result})
            audit("done", {"verified": result.get("verified")})
    except Exception as exc:
        error = str(exc) if type(exc) is ValueError and len(str(exc)) < 300 else "Falha " + type(exc).__name__ + "; confira configuração e permissões."
        removals.finish(job, "error", None, error)
        audit("error", {"error": error})
    finally:
        if executor: executor.close()
    return True


def restore_one(jobs, settings, batch, sku, *, actor, transport=None):
    """Rollback of one executed removal: staging policy or a single-use 'restore_<mode>' grant."""
    removals = Removals(jobs)
    with jobs.db() as db:
        record = dict(db.execute("SELECT * FROM removal_batches WHERE id=?", (batch,)).fetchone() or {})
        row = db.execute("SELECT * FROM removal_items WHERE batch=? AND sku=?", (batch, sku)).fetchone()
    if not record or not row: raise LookupError("Lote/SKU não encontrado.")
    item_plan = json.loads(row["plan"])
    grant = None
    try:
        jobs.policy.authorize(record["origin"], sku)
    except ValueError:
        grant = grants.find(jobs, company=record["company"], origin=record["origin"], sku=sku, product_id=item_plan.get("product_id"),
                            dry_run_sha256=item_plan["dry_run"]["dry_run_sha256"], purpose="restore_" + record["mode"], batch=batch)
        if not grant: raise ValueError("Restauração bloqueada: sem liberação de restauração válida para este item.") from None
        if not grants.consume(jobs, grant, actor): raise ValueError("Liberação de restauração expirada ou já utilizada.")
    journal = Journal(jobs, record["org"] + "|" + record["origin"] + "|" + sku)
    executor = RemovalExecutor(record["company"], sku, settings, jobs.policy, journal, transport=transport, grant=grant)
    audit = lambda event, detail=None: jobs.audit(batch, sku, actor, event, detail)
    try:
        result = executor.restore(item_plan, audit=audit)
    except Exception as exc:
        audit("restore_error", {"error": str(exc) if type(exc) is ValueError else type(exc).__name__})
        raise
    finally:
        executor.close()
    with jobs.db() as db:
        db.execute("UPDATE removal_items SET plan=? WHERE batch=? AND sku=?", (json.dumps({**item_plan, "restore": result}), batch, sku))
    return result
