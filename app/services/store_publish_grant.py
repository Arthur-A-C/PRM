"""Single-use production homologation grants for the files-only publisher.

A grant is issued only by the local CLI (scripts/homologation_grant.py), never by the web UI.
It is bound to one hard-coded target (store, origin, SKU, product ID), to the exact approved
Dry Run hash, to one purpose, and to a short validity. Consumption is atomic and happens
before the first upload, so a grant can never be reused. Everything else stays blocked by
PublishSettings.authorize.
"""
import json
import time
import uuid

from app.services.store_config import secure_url

# The only production writes that a grant may ever unlock. Changing this is a code review decision.
HOMOLOGATION_TARGETS = {("choice", "https://choicetech.com.br", "119002000072", 16321)}
REMOVAL_MODES = ("all", "gallery", "documents", "main")
# File removal: one purpose per mode, plus the restore of the same removal. Same allowlist, same single use.
REMOVAL_PURPOSES = {f"remove_{m}" for m in REMOVAL_MODES} | {f"restore_{m}" for m in REMOVAL_MODES}
PURPOSES = {"publish", "rollback"} | REMOVAL_PURPOSES
MAX_MINUTES = 120
MAX_SCOPE_ITEMS = 50
SCHEMA = """CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY,purpose TEXT,company TEXT,origin TEXT,sku TEXT,
  product_id INTEGER,batch TEXT,dry_run_sha256 TEXT,created REAL,expires REAL,actor TEXT,state TEXT,consumed REAL DEFAULT 0);"""


def target_allowed(company, origin, sku, product_id):
    try:
        origin = secure_url(origin)
    except ValueError:
        return False
    return (company, origin, sku, product_id) in HOMOLOGATION_TARGETS


def update_key(product_id, dry_run_sha256):
    return f"files:{product_id}:{dry_run_sha256}"


def issue(jobs, *, batch, sku, product_id, dry_run_sha256, purpose, minutes, actor, now=None, scope=""):
    """Validate everything against the stored, approved plan before writing a grant row."""
    from app.services.store_registration_jobs import Journal, approved
    now = time.time() if now is None else now
    if purpose not in PURPOSES: raise ValueError("Finalidade inválida.")
    if type(minutes) is not int or not 1 <= minutes <= MAX_MINUTES:
        raise ValueError(f"Validade deve ser de 1 a {MAX_MINUTES} minutos.")
    if type(product_id) is not int: raise ValueError("ID de produto inválido.")
    with jobs.db() as db:
        db.execute("BEGIN IMMEDIATE")
        record = db.execute("SELECT * FROM batches WHERE id=?", (batch,)).fetchone()
        row = db.execute("SELECT * FROM jobs WHERE batch=? AND sku=?", (batch, sku)).fetchone()
        if not record or not row: raise LookupError("Lote/SKU não encontrado.")
        if not target_allowed(record["company"], record["origin"], sku, product_id):
            raise ValueError("Alvo fora da homologação permitida (loja/origem/SKU/produto).")
        plan = json.loads(row["plan"])
        dry = plan.get("dry_run") or {}
        if plan.get("product_id") != product_id or dry.get("product_id") != product_id:
            raise ValueError("Produto do Dry Run diverge do informado.")
        if dry.get("dry_run_sha256") != dry_run_sha256:
            raise ValueError("Hash informado diverge do Dry Run armazenado.")
        if not approved({"approval": plan.get("approval"), "dry_run": dry}):
            raise ValueError("Dry Run não aprovado com este hash.")
        if purpose == "publish":
            from app.services.store_registration_plan import stale_supplier_datasheet
            if row["state"] != "review" or dry.get("blockers"):
                raise ValueError("Item não está pronto para envio (estado/bloqueios).")
            if stale_supplier_datasheet(dry):
                raise ValueError("Dry Run anterior à regra do datasheet do fornecedor; refaça a prévia e aprove novamente.")
        else:
            entry = Journal(jobs, record["org"] + "|" + record["origin"] + "|" + sku).get(update_key(product_id, dry_run_sha256))
            if not entry or "rollback" not in entry:
                raise ValueError("Não há publicação registrada para recuperar.")
        active = db.execute("SELECT 1 FROM grants WHERE company=? AND sku=? AND purpose=? AND state='issued' AND expires>?",
                            (record["company"], sku, purpose, now)).fetchone()
        if active: raise ValueError("Já existe liberação ativa para este alvo; revogue-a antes de emitir outra.")
        grant = {"id": uuid.uuid4().hex, "purpose": purpose, "company": record["company"], "origin": secure_url(record["origin"]),
                 "sku": sku, "product_id": product_id, "batch": batch, "dry_run_sha256": dry_run_sha256,
                 "created": now, "expires": now + minutes * 60, "actor": str(actor), "state": "issued", "consumed": 0,
                 "scope": scope}
        db.execute("INSERT INTO grants(id,purpose,company,origin,sku,product_id,batch,dry_run_sha256,created,expires,actor,state,consumed,scope) "
                   "VALUES(:id,:purpose,:company,:origin,:sku,:product_id,:batch,:dry_run_sha256,:created,:expires,:actor,:state,:consumed,:scope)", grant)
        jobs.audit(batch, sku, actor, "grant_issued", {"grant": grant["id"], "purpose": purpose, "expires": grant["expires"], "scope": scope}, db)
        return grant


def issue_scope(jobs, *, batch, skus, minutes, actor, max_items, now=None):
    """Several publish grants under one explicit scope: all-or-nothing, each row consumed and audited alone.

    Every SKU must still be in HOMOLOGATION_TARGETS; a scope never widens what a single grant allows.
    """
    if type(max_items) is not int or not 1 <= max_items <= MAX_SCOPE_ITEMS:
        raise ValueError(f"Limite do escopo deve ser de 1 a {MAX_SCOPE_ITEMS} itens.")
    skus = list(dict.fromkeys(skus))
    if not skus or len(skus) > max_items:
        raise ValueError("Quantidade de SKUs fora do limite declarado para o escopo.")
    with jobs.db() as db:
        rows = {r["sku"]: json.loads(r["plan"]) for r in db.execute("SELECT sku,plan FROM jobs WHERE batch=?", (batch,))}
        record = db.execute("SELECT * FROM batches WHERE id=?", (batch,)).fetchone()
    if not record: raise LookupError("Lote não encontrado.")
    outside = [s for s in skus if s not in rows or not target_allowed(record["company"], record["origin"], s, rows[s].get("product_id"))]
    if outside:
        raise ValueError("Fora dos alvos permitidos de homologação: " + ", ".join(outside) + ". Nenhuma liberação emitida.")
    scope = uuid.uuid4().hex
    issued = []
    try:
        for sku in skus:
            dry = rows[sku]["dry_run"]
            issued.append(issue(jobs, batch=batch, sku=sku, product_id=rows[sku]["product_id"], dry_run_sha256=dry["dry_run_sha256"],
                                purpose="publish", minutes=minutes, actor=actor, now=now, scope=scope))
    except Exception:
        for grant in issued:
            revoke(jobs, grant["id"], actor)
        raise
    return {"scope": scope, "grants": issued}


def issue_removal(jobs, *, batch, sku, minutes, actor, restore=False, now=None):
    """Single-use grant for one approved removal (or its restore), bound to store, SKU, product, mode and Dry Run hash."""
    from app.services import store_file_removal as removal
    now = time.time() if now is None else now
    if type(minutes) is not int or not 1 <= minutes <= MAX_MINUTES:
        raise ValueError(f"Validade deve ser de 1 a {MAX_MINUTES} minutos.")
    with jobs.db() as db:
        db.execute("BEGIN IMMEDIATE")
        record = db.execute("SELECT * FROM removal_batches WHERE id=?", (batch,)).fetchone()
        row = db.execute("SELECT * FROM removal_items WHERE batch=? AND sku=?", (batch, sku)).fetchone()
        if not record or not row: raise LookupError("Lote/SKU não encontrado.")
        plan = json.loads(row["plan"])
        dry = plan.get("dry_run") or {}
        product_id = plan.get("product_id")
        if not target_allowed(record["company"], record["origin"], sku, product_id):
            raise ValueError("Alvo fora da homologação permitida (loja/origem/SKU/produto).")
        if not removal.approved(plan):
            raise ValueError("Dry Run não aprovado com este hash.")
        if restore:
            if row["state"] not in {"done", "uncertain", "error"} or not removal.restorable(jobs, record, sku, plan):
                raise ValueError("Não há remoção registrada para restaurar.")
        elif row["state"] != "review" or dry.get("blockers"):
            raise ValueError("Item não está pronto para remoção (estado/bloqueios).")
        purpose = ("restore_" if restore else "remove_") + record["mode"]
        if db.execute("SELECT 1 FROM grants WHERE company=? AND sku=? AND purpose=? AND state='issued' AND expires>?",
                      (record["company"], sku, purpose, now)).fetchone():
            raise ValueError("Já existe liberação ativa para este alvo; revogue-a antes de emitir outra.")
        grant = {"id": uuid.uuid4().hex, "purpose": purpose, "company": record["company"], "origin": secure_url(record["origin"]),
                 "sku": sku, "product_id": product_id, "batch": batch, "dry_run_sha256": dry["dry_run_sha256"],
                 "created": now, "expires": now + minutes * 60, "actor": str(actor), "state": "issued", "consumed": 0, "scope": "removal"}
        db.execute("INSERT INTO grants(id,purpose,company,origin,sku,product_id,batch,dry_run_sha256,created,expires,actor,state,consumed,scope) "
                   "VALUES(:id,:purpose,:company,:origin,:sku,:product_id,:batch,:dry_run_sha256,:created,:expires,:actor,:state,:consumed,:scope)", grant)
        jobs.audit(batch, sku, actor, "grant_issued", {"grant": grant["id"], "purpose": purpose, "expires": grant["expires"]}, db)
        return grant


def find(jobs, *, company, origin, sku, product_id, dry_run_sha256, purpose, batch=None, now=None, db=None):
    now = time.time() if now is None else now
    if not target_allowed(company, origin, sku, product_id): return None
    query = ("SELECT * FROM grants WHERE company=? AND origin=? AND sku=? AND product_id=? AND dry_run_sha256=? "
             "AND purpose=? AND state='issued' AND expires>?" + (" AND batch=?" if batch else ""))
    params = (company, secure_url(origin), sku, product_id, dry_run_sha256, purpose, now) + ((batch,) if batch else ())
    if db is not None:
        row = db.execute(query, params).fetchone()
    else:
        with jobs.db() as conn: row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def consume(jobs, grant, actor="worker", now=None):
    """Atomic single use: only one caller can flip issued -> consumed while unexpired."""
    now = time.time() if now is None else now
    with jobs.db() as db:
        changed = db.execute("UPDATE grants SET state='consumed',consumed=? WHERE id=? AND state='issued' AND expires>?",
                             (now, grant["id"], now)).rowcount
        if changed == 1:
            jobs.audit(grant["batch"], grant["sku"], actor, "grant_consumed", {"grant": grant["id"], "purpose": grant["purpose"]}, db)
    return changed == 1


def revoke(jobs, grant_id, actor):
    with jobs.db() as db:
        row = db.execute("SELECT * FROM grants WHERE id=?", (grant_id,)).fetchone()
        if not row: raise LookupError("Liberação não encontrada.")
        if db.execute("UPDATE grants SET state='revoked' WHERE id=? AND state='issued'", (grant_id,)).rowcount != 1:
            raise ValueError("Liberação já utilizada, revogada ou inexistente.")
        jobs.audit(row["batch"], row["sku"], actor, "grant_revoked", {"grant": grant_id}, db)


def listing(jobs):
    with jobs.db() as db:
        return [dict(r) for r in db.execute("SELECT id,purpose,company,sku,product_id,batch,dry_run_sha256,created,expires,state,consumed,scope "
                                            "FROM grants ORDER BY created DESC LIMIT 50")]


def check(grant, *, company, origin, sku, product_id=None, dry_run_sha256=None, purpose=None):
    """Publisher-side re-validation of a consumed grant against what is about to be written."""
    ok = (grant["company"] == company and grant["origin"] == secure_url(origin) and grant["sku"] == sku
          and target_allowed(company, origin, sku, grant["product_id"])
          and (product_id is None or grant["product_id"] == product_id)
          and (dry_run_sha256 is None or grant["dry_run_sha256"] == dry_run_sha256)
          and (purpose is None or grant["purpose"] == purpose))
    if not ok: raise ValueError("Liberação de homologação não corresponde à gravação solicitada.")
