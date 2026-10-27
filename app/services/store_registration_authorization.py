"""Files-only publication authorization. Reuses the removal module's central active-role rule."""
import hashlib
import json
import time

from app.services import store_removal_production as access

VERSION = "files-role-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def binding(record, sku, plan):
    bound = {"version": VERSION, "org": record["org"], "company": record["company"], "origin": record["origin"],
             "sku": sku, "product_id": plan["product_id"], "snapshot_hash": plan["snapshot_hash"],
             "protected_hash": plan.get("protected_hash"),
             "files_sha256": digest({k: plan[k] for k in ("images", "downloads")})}
    inputs = plan.get("input") or {}
    # Scope and chosen main are signed too: changing either after approval demands a new Dry Run.
    # Plans prepared without a scope keep their original binding.
    if inputs.get("scope") is not None:
        bound["scope_sha256"] = digest({"scope": inputs["scope"], "main_choice": inputs.get("main_choice") or None})
    return bound


def seal(record, sku, plan):
    dry = plan["dry_run"]
    dry["authorization"] = binding(record, sku, plan)
    dry["dry_run_sha256"] = digest({k: v for k, v in dry.items() if k != "dry_run_sha256"})


def validate(record, sku, plan, *, approval=True, recovery=False):
    dry = plan.get("dry_run") or {}
    if not dry or digest({k: v for k, v in dry.items() if k != "dry_run_sha256"}) != dry.get("dry_run_sha256"):
        raise ValueError("Hash do Dry Run inválido; refaça a prévia.")
    if (dry.get("scope") != "files_only" or set(dry.get("writable_keys", [])) != {"images", "meta_data"}
            or dry.get("sku") != sku or type(plan.get("product_id")) is not int
            or plan["product_id"] != dry.get("product_id") or dry.get("blockers")):
        raise ValueError("SKU, produto ou escopo de arquivos inválido; nada enviado.")
    if not recovery or dry.get("authorization"):
        if dry.get("authorization") != binding(record, sku, plan):
            raise ValueError("Prévia antiga ou plano alterado; refaça o Dry Run e aprove novamente.")
    if not recovery:
        from app.services.store_registration_plan import check_scope
        check_scope(plan)
    review = plan.get("approval") or {}
    if approval and (review.get("dry_run_sha256") != dry["dry_run_sha256"] or not review.get("by")
                     or type(review.get("replace_main")) is not bool):
        raise ValueError("Dry Run não aprovado ou aprovação inválida.")


def check_identity(actor, org, company, approver, *, session_factory=None):
    with (session_factory or access.session)() as db:
        access.check_approval(db, actor, org, company, approver, "execute")


def confirmation(record, sku, plan, actor, action):
    return {"version": VERSION, "confirmed": True, "by": str(actor), "at": time.time(), "action": action,
            "org": record["org"], "company": record["company"], "origin": record["origin"], "sku": sku,
            "product_id": plan["product_id"], "dry_run_sha256": plan["dry_run"]["dry_run_sha256"],
            "approval": plan["approval"]}


def recheck(jobs, job, plan, action, session_factory=None):
    validate(job, job["sku"], plan, recovery=action == "rollback")
    request = plan.get("execution" if action == "publish" else "rollback_request") or {}
    expected = confirmation(job, job["sku"], plan, job["owner"], action)
    if any(request.get(k) != v for k, v in expected.items() if k != "at"):
        raise ValueError("Confirmação ausente ou escopo alterado; revise e confirme novamente.")
    running = "running" if action == "publish" else "rollback_running"
    with jobs.db() as db:
        row = db.execute("SELECT state,token,plan FROM jobs WHERE batch=? AND sku=?", (job["batch"], job["sku"])).fetchone()
    if not row or row["state"] != running or row["token"] != job["token"] or json.loads(row["plan"]) != plan:
        raise ValueError("Operação da fila alterada ou interrompida; nada enviado.")
    check_identity(request["by"], job["org"], job["company"], plan["approval"]["by"], session_factory=session_factory)
    jobs.audit(job["batch"], job["sku"], request["by"], "file_role_verified", {"action": action, "policy": VERSION})
