"""Removal API: authenticated roles, organization scope, CSRF and explicit confirmation.

The worker independently revalidates the actor, approval and exact Dry Run before real writes.
"""
import json
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.dependencies import CurrentAuth, DbSession
from app.routers.registration import require_manager as _require_manager
from app.routers.store_integrations import authorized_settings as _authorized_settings
from app.services import removal_backup as backups
from app.services import store_removal_production as production
from app.services.store_config import COMPANIES
from app.services.store_file_removal import Removals, parse_skus
from app.services.store_registration_jobs import Jobs

router = APIRouter(prefix="/api/v1/remocao-arquivos", tags=["remocao-arquivos"])
Company = Literal["choice", "sag", "portwell"]
# Replaced only by tests/E2E harnesses that simulate the stores; production uses real HTTPS clients.
preflight_transport = None


class Selection(BaseModel):
    skus: list[str] | None = None
    confirmacao: str = ""


class Switch(BaseModel):
    ativar: bool
    confirmacao: str = ""


class PermissionChange(BaseModel):
    usuario: str
    empresa: Company
    aprovar: bool = False
    executar: bool = False
    restaurar: bool = False
    administrar: bool = False


def scope(auth):
    return str(auth.user.organization_id), str(auth.user.id)


def service():
    return Removals(Jobs())


def run(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except production.PermissionDenied as exc:
        raise HTTPException(403, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


def context(auth, db):
    """Store permissions of the current user and the stores whose batches they may see."""
    perms = production.summary(db, auth.user)
    return perms, [c for c, p in perms.items() if any(p.values())]


def phrase(kind, count, company):
    return {"executar": f"EXECUTAR {count} {company.upper()}", "restaurar": f"RESTAURAR {count} {company.upper()}",
            "producao": f"ATIVAR PRODUCAO {company.upper()}", "quatro_olhos": f"DESATIVAR QUATRO OLHOS {company.upper()}"}[kind]


def confirmation(given, expected):
    if " ".join((given or "").upper().split()) != expected:
        raise ValueError(f"Confirmação digitada não confere. Digite exatamente: {expected}")


def blocked(jobs, batch, auth, action, reason):
    """Refusals are audited too (who tried what, and why)."""
    jobs.audit(batch, "", str(auth.user.id), "blocked_attempt", {"action": action, "reason": str(reason)[:300]})


def guarded(jobs, batch, auth, action, work):
    try:
        return run(work)
    except HTTPException as exc:
        if exc.status_code in {403, 422}:
            blocked(jobs, batch, auth, action, exc.detail)
        raise


def authorized_settings(auth):
    try:
        production.require_role(auth.user)
    except production.PermissionDenied as exc:
        raise HTTPException(403, str(exc)) from None
    return _authorized_settings(auth)


def require_manager(auth, csrf_token):
    authorized_settings(auth)
    _require_manager(auth, csrf_token)


def operation_gate(perms, company, action):
    if not perms[company][action]:
        raise production.PermissionDenied(production.ROLE_DENIED)


# --- Ambientes e permissões ------------------------------------------------------------------------

@router.get("/ambientes")
def environments(request: Request, auth: CurrentAuth, db: DbSession):
    authorized_settings(auth)
    perms, _ = context(auth, db)
    envs = production.Environments(Jobs())
    org = str(auth.user.organization_id)
    return {"authorization": "role-v1", "https": production.is_https(request), "role": auth.user.role,
            "companies": [{**production.operation_status(c), "preflight": envs.get(org, c)["preflight"], "permissions": perms[c]} for c in COMPANIES]}


@router.post("/ambientes/{empresa}/teste")
def test_store(empresa: Company, auth: CurrentAuth, db: DbSession,
               csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    """Read-only preflight: credentials, WooCommerce key, WordPress capabilities, media upload."""
    require_manager(auth, csrf_token)
    settings = authorized_settings(auth)
    jobs = Jobs()

    def work():
        perms, _ = context(auth, db)
        if not any(perms[empresa].values()):
            raise production.PermissionDenied(f"Sem permissão de remoção na {empresa.upper()}.")
        result = production.preflight(settings, empresa, transport=preflight_transport)
        production.Environments(jobs).record_preflight(str(auth.user.organization_id), empresa, result, str(auth.user.id))
        return result
    return guarded(jobs, "ambiente:" + empresa, auth, "preflight", work)


@router.post("/ambientes/{empresa}/producao", deprecated=True)
@router.post("/ambientes/{empresa}/quatro-olhos", deprecated=True)
def retired_environment(empresa: Company, body: Switch, auth: CurrentAuth,
                        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    raise HTTPException(410, "A autorização de remoção agora é definida pelo cargo. Revise e confirme a operação no lote.")


@router.get("/permissoes")
def permissions(auth: CurrentAuth, db: DbSession):
    authorized_settings(auth)
    perms, _ = context(auth, db)
    if not any(p["admin"] for p in perms.values()):
        raise HTTPException(403, "Somente administradores da remoção gerenciam permissões.")
    return {"users": production.listing(db, auth.user.organization_id),
            "admin_of": [c for c, p in perms.items() if p["admin"]]}


@router.put("/permissoes", deprecated=True)
def change_permission(body: PermissionChange, auth: CurrentAuth,
                      csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    raise HTTPException(410, "Gestores e desenvolvedores têm permissões automáticas. Não é necessário cadastrar permissões por loja.")


# --- Lotes ---------------------------------------------------------------------------------------

@router.post("")
async def create(auth: CurrentAuth, db: DbSession, empresa: Annotated[Literal["choice", "sag", "portwell"], Form()],
                 modo: Annotated[Literal["all", "gallery", "documents", "main"], Form()],
                 skus: Annotated[str, Form()] = "", planilha: Annotated[UploadFile | None, File()] = None,
                 csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    settings = authorized_settings(auth)
    try:
        sheet = await planilha.read(5 * 1024**2 + 1) if planilha and planilha.filename else None
        values, duplicates = run(lambda: parse_skus(skus, sheet, planilha.filename if sheet else ""))
        removals = service()
        identifier = run(lambda: removals.create(empresa, *scope(auth), modo, values, settings))
        return {**view(identifier, auth, db, removals), "duplicates_removed": duplicates}
    finally:
        if planilha: await planilha.close()


@router.get("")
def history(auth: CurrentAuth, db: DbSession):
    authorized_settings(auth)
    _, companies = context(auth, db)
    return {"items": service().history(*scope(auth), companies)}


def view(identifier, auth, db, removals=None):
    perms, companies = context(auth, db)
    data = (removals or service()).detail(identifier, *scope(auth), companies)
    data["people"] = production.people(db, auth.user.organization_id)
    data["permissions"] = perms[data["company"]]
    return data


@router.get("/{identifier}")
def detail(identifier: str, auth: CurrentAuth, db: DbSession):
    authorized_settings(auth)
    return run(lambda: view(identifier, auth, db))


def batch_action(identifier, auth, db, csrf_token, name, action):
    """Common path: CSRF, organization, visibility, audited refusals, fresh detail in the answer."""
    require_manager(auth, csrf_token)
    settings = authorized_settings(auth)
    removals = service()
    perms, companies = context(auth, db)

    def work():
        record = removals.record(identifier, *scope(auth), companies)
        environment = production.operation_status(record["company"])
        return action(removals, settings, record, environment, perms, companies)
    result = guarded(removals.jobs, identifier, auth, name, work)
    return {"result": result, **run(lambda: view(identifier, auth, db, removals))}


def target_count(removals, identifier, auth, companies, skus, states, approved_only=False):
    data = removals.detail(identifier, *scope(auth), companies)
    items = [i for i in data["items"] if i["state"] in states and (skus is None or i["sku"] in skus)
             and (not approved_only or (i["approval"] and i["approval"]["dry_run_sha256"] == (i["dry_run"] or {}).get("dry_run_sha256")))]
    return len(items)


@router.post("/{identifier}/aprovar")
def approve(identifier: str, request: Request, auth: CurrentAuth, db: DbSession, body: Selection | None = None,
            csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    body = body or Selection()

    def action(removals, settings, record, environment, perms, companies):
        operation_gate(perms, record["company"], "approve")
        return removals.approve(identifier, *scope(auth), body.skus, companies=companies)
    return batch_action(identifier, auth, db, csrf_token, "aprovar", action)


@router.post("/{identifier}/executar")
def confirm(identifier: str, request: Request, auth: CurrentAuth, db: DbSession, body: Selection | None = None,
            csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    # Only queues approved items; the worker re-checks identity, confirmation, state and backup.
    body = body or Selection()

    def action(removals, settings, record, environment, perms, companies):
        operation_gate(perms, record["company"], "execute")
        count = target_count(removals, identifier, auth, companies, body.skus, {"review"}, approved_only=True)
        confirmation(body.confirmacao, phrase("executar", count, record["company"]))
        return removals.confirm(identifier, *scope(auth), settings, body.skus, companies=companies, confirmed=True, authorization_session=db)
    return batch_action(identifier, auth, db, csrf_token, "executar", action)


@router.post("/{identifier}/restaurar")
def restore(identifier: str, request: Request, auth: CurrentAuth, db: DbSession, body: Selection | None = None,
            csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    body = body or Selection()

    def action(removals, settings, record, environment, perms, companies):
        operation_gate(perms, record["company"], "restore")
        count = sum(1 for i in removals.detail(identifier, *scope(auth), companies)["items"]
                    if i["restorable"] and (body.skus is None or i["sku"] in body.skus))
        confirmation(body.confirmacao, phrase("restaurar", count, record["company"]))
        return removals.request_restore(identifier, *scope(auth), body.skus, companies=companies, confirmed=True, authorization_session=db)
    return batch_action(identifier, auth, db, csrf_token, "restaurar", action)


@router.post("/{identifier}/reconferir")
def reconcile(identifier: str, auth: CurrentAuth, db: DbSession, body: Selection | None = None,
              csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    body = body or Selection()
    return batch_action(identifier, auth, db, csrf_token, "reconferir",
                        lambda r, s, record, e, p, companies: r.request_reconcile(identifier, *scope(auth), body.skus, companies=companies))


@router.post("/{identifier}/pausar")
def pause(identifier: str, auth: CurrentAuth, db: DbSession, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return batch_action(identifier, auth, db, csrf_token, "pausar",
                        lambda r, s, record, e, p, companies: r.pause(identifier, *scope(auth), companies=companies))


@router.post("/{identifier}/cancelar")
def cancel(identifier: str, auth: CurrentAuth, db: DbSession, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return batch_action(identifier, auth, db, csrf_token, "cancelar",
                        lambda r, s, record, e, p, companies: r.cancel(identifier, *scope(auth), companies=companies))


@router.post("/{identifier}/reprocessar")
def reprocess(identifier: str, auth: CurrentAuth, db: DbSession, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return batch_action(identifier, auth, db, csrf_token, "reprocessar",
                        lambda r, s, record, e, p, companies: r.reprocess(identifier, *scope(auth), companies=companies))


@router.get("/{identifier}/relatorio")
def report(identifier: str, auth: CurrentAuth, db: DbSession):
    authorized_settings(auth)
    _, companies = context(auth, db)
    people = production.people(db, auth.user.organization_id)
    return Response(run(lambda: service().report(identifier, *scope(auth), companies=companies, people=people)), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="remocao-arquivos.csv"', "Cache-Control": "private, no-store"})


@router.get("/{identifier}/dry-run")
def dry_run(identifier: str, auth: CurrentAuth, db: DbSession):
    authorized_settings(auth)
    data = run(lambda: view(identifier, auth, db))
    return Response(json.dumps(data, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="remocao-dry-run.json"', "Cache-Control": "private, no-store"})


@router.get("/{identifier}/auditoria")
def audit(identifier: str, auth: CurrentAuth, db: DbSession):
    authorized_settings(auth)
    _, companies = context(auth, db)
    removals = service()
    run(lambda: removals.record(identifier, *scope(auth), companies))
    people = production.people(db, auth.user.organization_id)
    with removals.jobs.db() as conn:
        rows = conn.execute("SELECT sku,at,actor,event,detail FROM audit WHERE batch=? ORDER BY at", (identifier,)).fetchall()
    return {"items": [{"sku": r["sku"], "at": r["at"], "actor": people.get(r["actor"], r["actor"]), "event": r["event"],
                       "detail": json.loads(r["detail"] or "{}")} for r in rows]}


@router.get("/{identifier}/backup/{sku}")
def backup(identifier: str, sku: str, auth: CurrentAuth, db: DbSession):
    authorized_settings(auth)
    _, companies = context(auth, db)
    removals = service()
    record = run(lambda: removals.record(identifier, *scope(auth), companies))
    item = next((i for i in run(lambda: removals.detail(identifier, *scope(auth), companies))["items"] if i["sku"] == sku), None)
    if not item or not item["dry_run"]:
        raise HTTPException(404, "Item sem Dry Run neste lote.")
    try:
        content = backups.archive(removals.jobs, record["org"], record["company"], sku, item["dry_run"]["dry_run_sha256"])
    except backups.BackupError as exc:
        raise HTTPException(404, f"Backup indisponível: {exc}") from None
    return Response(content, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="backup-{record["company"]}-{sku}.zip"', "Cache-Control": "private, no-store"})
