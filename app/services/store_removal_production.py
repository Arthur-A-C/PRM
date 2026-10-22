"""Produção da Remoção de arquivos: trava mestra, ambiente por loja, permissões por usuário e preflight.

Two environments per store:
  homologação (default)  unchanged rules: staging policy (PRM_PUBLISH_*) or CLI grants limited to
                         store_publish_grant.HOMOLOGATION_TARGETS
  produção               switched on per store in the UI by an administrator. Switching it on authorizes
                         nothing by itself: every batch still needs Dry Run, approval, a typed confirmation
                         and single-use grants issued for the executing user.

Nothing here can unlock a production write unless PRM_REMOVAL_PRODUCTION_ALLOWED=true is set in the
process environment; the API and the worker check it independently. User permissions live in
PostgreSQL (store_operation_permissions) and are re-checked by the worker before each write.
"""
import json
import os
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import User
from app.models.store_operations import STORE_COMPANIES, StoreOperationPermission
from app.services.store_config import secure_url
from app.services.store_http import StoreAPIError, http_client, read_json

MASTER_SWITCH = "PRM_REMOVAL_PRODUCTION_ALLOWED"
ACTIONS = {"approve": "can_approve", "execute": "can_execute", "restore": "can_restore", "admin": "can_admin"}
ACTION_LABELS = {"approve": "aprovar", "execute": "executar", "restore": "restaurar", "admin": "administrar"}
MANAGERS = {"gestor", "desenvolvedor"}
REQUIRED_CAPABILITIES = ("upload_files", "edit_products", "edit_published_products", "edit_others_products")
GRANT_MINUTES = 30
ENV_SCHEMA = """CREATE TABLE IF NOT EXISTS removal_environments(org TEXT,company TEXT,production INTEGER DEFAULT 0,
  four_eyes INTEGER DEFAULT 1,changed_by TEXT DEFAULT '',changed_at REAL DEFAULT 0,preflight TEXT DEFAULT '{}',
  PRIMARY KEY(org,company));"""


class PermissionDenied(Exception):
    """Authenticated but not allowed: HTTP 403 and an audit entry."""


def master_switch():
    """Read at call time, so the API and the worker each enforce the value they actually run with."""
    return os.environ.get(MASTER_SWITCH, "").strip().lower() == "true"


def is_https(request):
    """The browser reached the PRM over HTTPS (directly or through a trusted proxy, see uvicorn --forwarded-allow-ips)."""
    return request.url.scheme == "https"


# --- Environments (same SQLite as queue, grants and audit: read by API and worker) -------------

def read_environment(db, org, company):
    """Store environment inside any open transaction. No row = homologation, four-eyes on."""
    if company not in STORE_COMPANIES:
        raise ValueError("Empresa inválida.")
    row = db.execute("SELECT * FROM removal_environments WHERE org=? AND company=?", (str(org), company)).fetchone()
    row = dict(row) if row else {"production": 0, "four_eyes": 1, "changed_by": "", "changed_at": 0, "preflight": "{}"}
    return {"company": company, "production": bool(row["production"]), "four_eyes": bool(row["four_eyes"]),
            "changed_by": row["changed_by"], "changed_at": row["changed_at"], "preflight": json.loads(row["preflight"] or "{}"),
            "master_switch": master_switch(), "active": bool(row["production"]) and master_switch()}


class Environments:
    def __init__(self, jobs):
        self.jobs = jobs
        with jobs.db() as db:
            db.executescript(ENV_SCHEMA)

    def get(self, org, company, db=None):
        if db is not None:
            return read_environment(db, org, company)
        with self.jobs.db() as conn:
            return read_environment(conn, org, company)

    def production_active(self, org, company, db=None):
        return self.get(org, company, db)["active"]

    def _write(self, org, company, actor, event, detail, **values):
        with self.jobs.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.get(org, company, db)
            row = {"production": int(current["production"]), "four_eyes": int(current["four_eyes"]),
                   "preflight": json.dumps(current["preflight"]), **values}
            db.execute("INSERT OR REPLACE INTO removal_environments(org,company,production,four_eyes,changed_by,changed_at,preflight) "
                       "VALUES(?,?,?,?,?,?,?)", (str(org), company, row["production"], row["four_eyes"], str(actor), time.time(), row["preflight"]))
            self.jobs.audit("ambiente:" + company, "", actor, event, detail, db)

    def set_production(self, org, company, enabled, actor, preflight=None):
        if enabled and not master_switch():
            raise ValueError(f"Produção bloqueada no servidor: {MASTER_SWITCH} não está ativa.")
        if enabled and not (preflight or {}).get("ok"):
            raise ValueError("Teste de conexão e permissões da loja não aprovado; produção não ativada.")
        values = {"production": int(bool(enabled))}
        if preflight is not None:
            values["preflight"] = json.dumps(preflight)
        self._write(org, company, actor, "production_enabled" if enabled else "production_disabled",
                    {"preflight_ok": bool((preflight or {}).get("ok"))} if enabled else {}, **values)

    def set_four_eyes(self, org, company, enabled, actor):
        self._write(org, company, actor, "four_eyes_enabled" if enabled else "four_eyes_disabled", {}, four_eyes=int(bool(enabled)))

    def record_preflight(self, org, company, result, actor):
        self._write(org, company, actor, "preflight_ok" if result["ok"] else "preflight_failed",
                    {"failed": [c["name"] for c in result["checks"] if not c["ok"]]}, preflight=json.dumps(result))


# --- Permissions (PostgreSQL) ------------------------------------------------------------------

def _uuid(value):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError:
        return None


def flags(row, user):
    """Effective permissions; administration additionally requires the "desenvolvedor" role."""
    if row is None or not user.active or user.role not in MANAGERS:
        return {action: False for action in ACTIONS}
    result = {action: bool(getattr(row, column)) for action, column in ACTIONS.items()}
    result["admin"] = result["admin"] and user.role == "desenvolvedor"
    return result


def permissions_for(db: Session, user, company):
    if company not in STORE_COMPANIES:
        raise ValueError("Empresa inválida.")
    user_id, organization_id = _uuid(user.id), _uuid(user.organization_id)
    if user_id is None or organization_id is None:
        return {action: False for action in ACTIONS}
    row = db.scalar(select(StoreOperationPermission).where(
        StoreOperationPermission.user_id == user_id, StoreOperationPermission.company == company,
        StoreOperationPermission.organization_id == organization_id))
    return flags(row, user)


def summary(db: Session, user):
    return {company: permissions_for(db, user, company) for company in STORE_COMPANIES}


def require(db: Session, user, company, action):
    if not permissions_for(db, user, company)[action]:
        role = " (exige papel desenvolvedor)" if action == "admin" else ""
        raise PermissionDenied(f"Sem permissão para {ACTION_LABELS[action]} remoções na {company.upper()}{role}.")


def user_may(db: Session, user_id, organization_id, company, action):
    """Worker-side re-check by the IDs stored in a grant: user still exists, is active, same org and allowed."""
    user = db.get(User, _uuid(user_id)) if _uuid(user_id) else None
    if user is None or str(user.organization_id) != str(organization_id):
        return False
    return permissions_for(db, user, company)[action]


def people(db: Session, organization_id):
    """User ID -> name for audit and reports (IDs are what the queue stores)."""
    organization_id = _uuid(organization_id)
    if organization_id is None:
        return {}
    return {str(u.id): u.name for u in db.scalars(select(User).where(User.organization_id == organization_id)).all()}


def listing(db: Session, organization_id):
    organization_id = _uuid(organization_id)
    users = db.scalars(select(User).where(User.organization_id == organization_id, User.active.is_(True),
                                          User.role.in_(sorted(MANAGERS))).order_by(User.name)).all()
    rows = db.scalars(select(StoreOperationPermission).where(StoreOperationPermission.organization_id == organization_id)).all()
    by_user = {}
    for row in rows:
        by_user.setdefault(row.user_id, {})[row.company] = row
    return [{"id": str(u.id), "name": u.name, "email": u.email, "role": u.role,
             "companies": {c: flags(by_user.get(u.id, {}).get(c), u) for c in STORE_COMPANIES}} for u in users]


def update(db: Session, admin, target_id, company, values):
    """Set one user's permissions for one store; returns (before, after) for the audit trail."""
    require(db, admin, company, "admin")
    target = db.get(User, _uuid(target_id)) if _uuid(target_id) else None
    if target is None or target.organization_id != admin.organization_id or not target.active:
        raise LookupError("Usuário não encontrado nesta organização.")
    if target.role not in MANAGERS:
        raise ValueError("Vendedores não recebem permissões de remoção.")
    wanted = {action: bool(values.get(action, False)) for action in ACTIONS}
    if wanted["admin"] and target.role != "desenvolvedor":
        raise ValueError("Administração da remoção exige o papel desenvolvedor.")
    if target.id == admin.id and not wanted["admin"]:
        raise ValueError("Você não pode retirar a própria administração; peça a outro administrador.")
    row = db.scalar(select(StoreOperationPermission).where(StoreOperationPermission.user_id == target.id,
                                                           StoreOperationPermission.company == company))
    before = flags(row, target)
    if row is None:
        row = StoreOperationPermission(organization_id=target.organization_id, user_id=target.id, company=company)
        db.add(row)
    for action, column in ACTIONS.items():
        setattr(row, column, wanted[action])
    row.granted_by_id = admin.id
    db.commit()
    return before, flags(row, target)


def session():
    """Worker session on the PRM database (same PRM_DATABASE_URL as the API)."""
    from app.db import get_engine
    return Session(get_engine())


# --- Preflight (read-only) ---------------------------------------------------------------------

def preflight(settings, company, transport=None):
    """GET/OPTIONS only: credentials, HTTPS origin, WooCommerce key, WordPress capabilities and media upload."""
    checks = []

    def check(name, action):
        try:
            detail = action()
            checks.append({"name": name, "ok": True, "detail": detail or "ok"})
        except (ValueError, StoreAPIError) as exc:
            checks.append({"name": name, "ok": False, "detail": str(exc)[:300]})
        except Exception as exc:  # network/protocol surprises: a failed check, never a crash or a leaked detail
            checks.append({"name": name, "ok": False, "detail": f"Falha {type(exc).__name__} ao consultar a loja."})

    clients = {}

    def credentials():
        wc, wp = settings.credentials(company, "wc"), settings.credentials(company, "wp")
        if secure_url(wc.base_url) != secure_url(wp.base_url):
            raise ValueError("WordPress e WooCommerce com origens diferentes.")
        clients["wc"] = http_client(wc.base_url, "wc/v3", auth=(wc.username, wc.password), timeout=settings.timeout, transport=transport)
        clients["wp"] = http_client(wp.base_url, "wp/v2", auth=(wp.username, wp.password), timeout=settings.timeout, transport=transport)
        return f"origem {secure_url(wc.base_url)}"

    def woocommerce():
        rows = read_json(clients["wc"], "products", {"per_page": 1, "_fields": "id"})
        if not isinstance(rows, list):
            raise ValueError("Resposta inesperada do WooCommerce.")
        return "chave WooCommerce aceita"

    def capabilities():
        me = read_json(clients["wp"], "users/me", {"context": "edit", "_fields": "id,capabilities"})
        caps = me.get("capabilities") if isinstance(me, dict) else None
        if not isinstance(caps, dict):
            raise ValueError("Capacidades do usuário WordPress indisponíveis.")
        missing = [c for c in REQUIRED_CAPABILITIES if caps.get(c) is not True]
        if missing:
            raise ValueError("Capacidades ausentes: " + ", ".join(missing))
        return "capacidades de edição e upload confirmadas"

    def media():
        response = clients["wp"].options("media")
        allow = {m.strip().upper() for m in response.headers.get("allow", "").split(",") if m.strip()} if response.status_code == 200 else set()
        if "POST" not in allow:
            raise ValueError("Upload de mídia não permitido (necessário para restaurar a partir do backup).")
        return "upload de mídia permitido"

    try:
        check("credenciais", credentials)
        if "wc" in clients:
            check("woocommerce", woocommerce)
            check("wordpress_capacidades", capabilities)
            check("wordpress_midia", media)
    finally:
        for client in clients.values():
            client.close()
    return {"ok": bool(checks) and all(c["ok"] for c in checks) and len(checks) == 4, "checks": checks, "at": time.time()}
