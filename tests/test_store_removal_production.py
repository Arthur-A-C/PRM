"""Remoção de arquivos em produção: ambientes, permissões, quatro olhos, backup, restauração e auditoria. Mocks only.

No test talks to a real store: every request goes to the Shop double through httpx.MockTransport.
"""
import io
import json
import sys
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).parent))
from test_store_file_removal import COMMERCIAL, Shop, commercial, jpeg  # noqa: E402

from app.models.identity import Organization, User
from app.models.store_operations import StoreOperationPermission
from app.services import removal_backup as backups
from app.services import store_file_removal as removal
from app.services import store_publish_grant as grants
from app.services import store_removal_production as production
from app.services.store_config import StoreSettings
from app.services.store_publish import PublishSettings
from app.services.store_registration_jobs import Jobs

ORIGINS = {"choice": "https://choicetech.com.br", "portwell": "https://portwell.com.br", "sag": "https://sagloja.devsplcomunic.com.br"}
PORTWELL_SKU, PORTWELL_PRODUCT, PORTWELL_MAIN = "315003005779", 18035, 18039


def docs_for(origin):
    return [{"label": "Datasheet", "url": origin + "/up/d.pdf", "filename": "d.pdf", "filesize": "90.8 KB"},
            {"label": "Desenho 3D", "url": origin + "/up/3d.zip", "filename": "3d.zip", "filesize": "2.84 MB"}]


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(removal, "VERIFY_DELAYS", (0, 0))
    monkeypatch.delenv(production.MASTER_SWITCH, raising=False)


@pytest.fixture
def switch(monkeypatch):
    monkeypatch.setenv(production.MASTER_SWITCH, "true")


@pytest.fixture
def settings():
    values = {"PRM_STORE_ORGANIZATION_ID": None}
    for company, origin in ORIGINS.items():
        prefix = company.upper()
        values.update({f"{prefix}_WC_URL": origin, f"{prefix}_WC_KEY": f"ck_{company}_secret", f"{prefix}_WC_SECRET": f"cs_{company}_secret",
                       f"{prefix}_WP_USER": f"user_{company}", f"{prefix}_WP_APP_PASSWORD": f"app_{company}_secret"})
    return values


@pytest.fixture
def people():
    """PostgreSQL stand-in (SQLite) with one organization and its users."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (Organization, User, StoreOperationPermission):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        org = Organization(name="Portwell Group"); other_org = Organization(name="Outra")
        db.add_all([org, other_org]); db.flush()
        users = {}
        for key, role, organization in [("dev", "desenvolvedor", org), ("ana", "gestor", org), ("bia", "gestor", org),
                                        ("caio", "gestor", org), ("vera", "vendedor", org), ("fora", "desenvolvedor", other_org)]:
            users[key] = User(name=key.title(), email=f"{key}@example.test", role=role, organization_id=organization.id,
                              password_hash="unused", active=True)
            db.add(users[key])
        db.flush()
        for company in ORIGINS:
            db.add(StoreOperationPermission(organization_id=org.id, user_id=users["dev"].id, company=company, can_admin=True,
                                            can_approve=True, can_execute=True, can_restore=True))
            db.add(StoreOperationPermission(organization_id=org.id, user_id=users["ana"].id, company=company, can_approve=True))
            db.add(StoreOperationPermission(organization_id=org.id, user_id=users["bia"].id, company=company, can_execute=True, can_restore=True))
        db.commit()
    yield SimpleNamespace(engine=engine, org=org, users=users, session=lambda: Session(engine, expire_on_commit=False))
    engine.dispose()


@pytest.fixture
def store_settings(settings, people):
    return StoreSettings(_env_file=None, **{**settings, "PRM_STORE_ORGANIZATION_ID": str(people.org.id)})


@pytest.fixture
def jobs(tmp_path):
    # Real policy: production hosts are always refused by staging; only grants can unlock them.
    return Jobs(PublishSettings(_env_file=None, storage_dir=str(tmp_path / "q")))


def shops(products=None):
    return {company: Shop(products.get(company) if products else None, origin=origin) for company, origin in ORIGINS.items()} if products else None


def portwell_shop():
    origin = ORIGINS["portwell"]
    return Shop({PORTWELL_SKU: Shop.product(PORTWELL_PRODUCT, featured=PORTWELL_MAIN, gallery=[18040, 18041], docs=docs_for(origin))}, origin=origin)


class Flow:
    """One store, one batch, the real queue and worker, users from the PostgreSQL stand-in."""

    def __init__(self, jobs, settings, people, shop, company, mode, skus):
        self.jobs, self.settings, self.people, self.shop, self.company = jobs, settings, people, shop, company
        self.org = str(people.org.id)
        self.removals = removal.Removals(jobs)
        self.envs = production.Environments(jobs)
        self.batch = self.removals.create(company, self.org, self.uid("ana"), mode, list(skus), settings)
        self.drain()

    def uid(self, key):
        return str(self.people.users[key].id)

    def companies(self, key):
        with self.people.session() as db:
            perms = production.summary(db, self.people.users[key])
        return [c for c, p in perms.items() if any(p.values())]

    def drain(self):
        while removal.process_one(self.jobs, self.settings, httpx.MockTransport(self.shop.handle), session_factory=self.people.session):
            pass

    def enable(self):
        self.envs.set_production(self.org, self.company, True, self.uid("dev"), preflight={"ok": True, "checks": []})

    def approve(self, key="ana", skus=None):
        return self.removals.approve(self.batch, self.org, self.uid(key), skus, companies=self.companies(key))

    def execute(self, key="bia", skus=None, drain=True):
        queued = self.removals.confirm(self.batch, self.org, self.uid(key), self.settings, skus, companies=self.companies(key), production_confirmed=True)
        if drain: self.drain()
        return queued

    def restore(self, key="bia", skus=None):
        queued = self.removals.request_restore(self.batch, self.org, self.uid(key), skus, companies=self.companies(key), production_confirmed=True)
        self.drain()
        return queued

    def view(self, key="ana"):
        return self.removals.detail(self.batch, self.org, self.uid(key), self.companies(key))

    def item(self, sku=None):
        items = self.view()["items"]
        return next(i for i in items if sku is None or i["sku"] == sku)

    def events(self, sku=None):
        with self.jobs.db() as db:
            return [r["event"] for r in db.execute("SELECT event FROM audit WHERE batch=? AND (? IS NULL OR sku=?) ORDER BY at", (self.batch, sku, sku))]

    def grant_states(self):
        return [g["state"] for g in grants.listing(self.jobs)]


def portwell(jobs, settings, people, mode="main"):
    return Flow(jobs, settings, people, portwell_shop(), "portwell", mode, [PORTWELL_SKU])


# --- Homologação preservada e trava mestra ------------------------------------------------------

def test_production_is_off_by_default_and_homologation_targets_unchanged(jobs, store_settings, people):
    flow = portwell(jobs, store_settings, people)
    assert flow.item()["state"] == "review"
    flow.approve()
    with pytest.raises(ValueError, match="Sem liberação"):
        flow.execute()
    assert grants.HOMOLOGATION_TARGETS == {("choice", "https://choicetech.com.br", "119002000072", 16321)}
    assert set(flow.shop.methods) <= {"GET"} and not flow.shop.writes


def test_master_switch_is_required_to_enable_and_to_issue(jobs, store_settings, people, monkeypatch):
    flow = portwell(jobs, store_settings, people)
    with pytest.raises(ValueError, match=production.MASTER_SWITCH):
        flow.enable()
    monkeypatch.setenv(production.MASTER_SWITCH, "true")
    flow.enable()
    monkeypatch.setenv(production.MASTER_SWITCH, "false")  # turned off on the server: the UI switch alone is not enough
    flow.approve()
    with pytest.raises(ValueError, match="Sem liberação"):
        flow.execute()
    assert not flow.shop.writes and flow.envs.get(flow.org, "portwell")["production"] and not flow.envs.get(flow.org, "portwell")["active"]


def test_master_switch_off_in_the_worker_blocks_before_any_write(jobs, store_settings, people, switch, monkeypatch):
    flow = portwell(jobs, store_settings, people)
    flow.enable(); flow.approve()
    flow.execute(drain=False)
    monkeypatch.setenv(production.MASTER_SWITCH, "")  # worker container without the variable
    flow.drain()
    item = flow.item()
    assert item["state"] == "blocked" and production.MASTER_SWITCH in item["error"]
    assert not flow.shop.writes and "blocked_worker" in flow.events(PORTWELL_SKU) and flow.grant_states() == ["issued"]


def test_enabling_production_requires_successful_preflight(jobs, store_settings, people, switch):
    envs = production.Environments(jobs)
    with pytest.raises(ValueError, match="Teste de conexão"):
        envs.set_production(str(people.org.id), "sag", True, "dev", preflight={"ok": False, "checks": []})
    assert not envs.get(str(people.org.id), "sag")["production"]


# --- Fluxo completo: caso real da Portwell -----------------------------------------------------

def test_portwell_main_image_removal_with_backup_and_restore(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people, mode="main")
    before = commercial(flow.shop, PORTWELL_SKU)
    dry = flow.item()["dry_run"]
    assert dry["product_id"] == PORTWELL_PRODUCT and dry["unlink"]["images"][0]["id"] == PORTWELL_MAIN
    assert dry["writes"] == [{"api": "wordpress", "method": "POST", "endpoint": f"product/{PORTWELL_PRODUCT}", "payload": {"featured_media": 0}}]
    flow.enable(); flow.approve("ana")
    flow.execute("bia")
    item = flow.item()
    p = flow.shop.products[PORTWELL_SKU]
    assert item["state"] == "done" and item["result"]["verified"]
    assert (p["featured"], p["gallery"]) == (0, [18040, 18041]) and commercial(flow.shop, PORTWELL_SKU) == before
    assert item["backup"]["images"] == 1 and item["backup"]["verified"]
    manifest = backups.verify(backups.folder(jobs, flow.org, "portwell", PORTWELL_SKU, dry["dry_run_sha256"]))
    assert manifest["files"][0]["media_id"] == PORTWELL_MAIN and manifest["before"]["main"] == PORTWELL_MAIN
    assert flow.grant_states() == ["consumed"]
    assert {"approved", "queued", "grant_issued", "backup_verified", "grant_consumed", "removal_sent", "removal_verified", "done"} <= set(flow.events(PORTWELL_SKU))
    assert item["approval"]["by"] == flow.uid("ana") and item["execution"] == {**item["execution"], "by": flow.uid("bia"), "env": "production"}
    flow.restore("bia")
    assert flow.item()["state"] == "restored"
    assert (p["featured"], p["gallery"]) == (PORTWELL_MAIN, [18040, 18041]) and commercial(flow.shop, PORTWELL_SKU) == before
    assert flow.grant_states().count("consumed") == 2 and "DELETE" not in flow.shop.methods


# --- Quatro olhos e permissões (API e worker) --------------------------------------------------

def test_four_eyes_blocks_the_approver_from_executing(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people)
    flow.enable(); flow.approve("dev")
    with pytest.raises(ValueError, match="quatro olhos"):
        flow.execute("dev")
    assert not flow.shop.writes
    flow.envs.set_four_eyes(flow.org, "portwell", False, flow.uid("dev"))
    flow.execute("dev")
    assert flow.item()["state"] == "done"
    with jobs.db() as db:
        assert db.execute("SELECT event FROM audit WHERE batch='ambiente:portwell' ORDER BY at DESC").fetchone()["event"] == "four_eyes_disabled"


def test_worker_rechecks_permission_revoked_after_the_grant(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people)
    flow.enable(); flow.approve()
    flow.execute("bia", drain=False)
    with people.session() as db:
        row = db.query(StoreOperationPermission).filter_by(user_id=people.users["bia"].id, company="portwell").one()
        row.can_execute = False; db.commit()
    flow.drain()
    item = flow.item()
    assert item["state"] == "blocked" and "não tem mais permissão" in item["error"] and not flow.shop.writes


def test_worker_rechecks_deactivated_user_and_environment(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people)
    flow.enable(); flow.approve()
    flow.execute("bia", drain=False)
    flow.envs.set_production(flow.org, "portwell", False, flow.uid("dev"))
    flow.drain()
    assert flow.item()["state"] == "blocked" and not flow.shop.writes


def test_four_eyes_rechecked_in_the_worker_with_forged_grant(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people)
    flow.enable(); flow.approve("dev")
    # A grant issued directly (bypassing confirm) for the approver must still be refused by the worker.
    with jobs.db() as db:
        db.execute("BEGIN IMMEDIATE")
        grants.issue_removal(jobs, batch=flow.batch, sku=PORTWELL_SKU, minutes=30, actor=flow.uid("dev"), env="production",
                             approver=flow.uid("dev"), db=db)
        db.execute("UPDATE removal_items SET state='queued' WHERE batch=?", (flow.batch,))
    flow.drain()
    assert flow.item()["state"] == "blocked" and "quatro olhos" in flow.item()["error"] and not flow.shop.writes


def test_production_grants_are_short_and_removal_only(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people)
    flow.enable(); flow.approve()
    with pytest.raises(ValueError, match="1 a 30"):
        grants.issue_removal(jobs, batch=flow.batch, sku=PORTWELL_SKU, minutes=31, actor=flow.uid("bia"), env="production")
    assert not grants.production_allowed(jobs.db().__enter__(), flow.org, "portwell", "publish")
    grant = {"env": "production", "purpose": "publish", "company": "portwell", "origin": ORIGINS["portwell"], "sku": PORTWELL_SKU, "product_id": PORTWELL_PRODUCT}
    with pytest.raises(ValueError, match="não corresponde"):
        grants.check(grant, company="portwell", origin=ORIGINS["portwell"], sku=PORTWELL_SKU)


def test_permission_rules(people):
    with people.session() as db:
        dev, ana, vera, fora = (people.users[k] for k in ("dev", "ana", "vera", "fora"))
        assert production.permissions_for(db, dev, "sag")["admin"]
        assert not production.permissions_for(db, ana, "sag")["execute"]
        with pytest.raises(ValueError, match="desenvolvedor"):
            production.update(db, dev, ana.id, "sag", {"admin": True})
        with pytest.raises(ValueError, match="Vendedores"):
            production.update(db, dev, vera.id, "sag", {"approve": True})
        with pytest.raises(LookupError):
            production.update(db, dev, fora.id, "sag", {"approve": True})
        with pytest.raises(production.PermissionDenied):
            production.update(db, ana, dev.id, "sag", {"approve": True})
        with pytest.raises(ValueError, match="própria administração"):
            production.update(db, dev, dev.id, "sag", {"approve": True})
        before, after = production.update(db, dev, ana.id, "sag", {"approve": True, "execute": True})
        assert not before["execute"] and after["execute"]
        # An admin flag stored for a non-developer never grants administration.
        db.add(StoreOperationPermission(organization_id=people.org.id, user_id=people.users["caio"].id, company="sag", can_admin=True))
        db.commit()
        assert not production.permissions_for(db, people.users["caio"], "sag")["admin"]
        db.get(User, people.users["bia"].id).active = False; db.commit()
        assert not production.user_may(db, people.users["bia"].id, people.org.id, "sag", "execute")
        assert not production.user_may(db, people.users["fora"].id, people.org.id, "sag", "admin")


# --- Backup -----------------------------------------------------------------------------------

@pytest.mark.parametrize("damage", ["missing", "corrupt", "media_record", "cdn"])
def test_unverifiable_backup_blocks_the_removal(jobs, store_settings, people, switch, damage):
    flow = portwell(jobs, store_settings, people, mode="all")
    flow.enable(); flow.approve()
    if damage == "missing": flow.shop.missing_files.add("d.pdf")
    if damage == "corrupt": flow.shop.corrupt_files.add("3d.zip")
    if damage == "media_record": flow.shop.deleted_media.add(18040)
    if damage == "cdn": flow.shop.origin = "https://cdn.terceiro.example"
    flow.execute()
    item = flow.item()
    assert item["state"] == "blocked" and not [w for w in flow.shop.writes if w[0] != "wp/v2/media"]
    assert flow.grant_states() == ["issued"]  # never consumed: nothing was written
    assert not list(backups.root(jobs).rglob("*.partial"))


def test_backup_respects_storage_limit(jobs, store_settings, people, switch, monkeypatch):
    flow = portwell(jobs, store_settings, people, mode="all")
    flow.enable(); flow.approve()
    monkeypatch.setattr(backups, "MIB", 1)  # every limit becomes tiny
    flow.execute()
    assert flow.item()["state"] == "blocked" and "limite" in flow.item()["error"].lower() and not flow.shop.writes


def test_backup_detects_tampering_on_disk(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people, mode="documents")
    flow.enable(); flow.approve(); flow.execute()
    path = backups.folder(jobs, flow.org, "portwell", PORTWELL_SKU, flow.item()["dry_run"]["dry_run_sha256"])
    target = next((path / "files").iterdir())
    target.write_bytes(target.read_bytes() + b"x")
    with pytest.raises(backups.BackupError, match="não confere"):
        backups.verify(path)


def test_restore_reuploads_media_deleted_from_the_library(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people, mode="all")
    flow.enable(); flow.approve(); flow.execute()
    flow.shop.deleted_media.update({PORTWELL_MAIN, 18041})
    flow.restore()
    item = flow.item()
    p = flow.shop.products[PORTWELL_SKU]
    assert item["state"] == "restored" and len(item["restore"]["reuploaded"]) == 2
    assert p["featured"] >= 900000 and p["gallery"][0] == 18040 and p["gallery"][1] >= 900000
    assert flow.shop.uploads[f"new-{p['featured']}.jpg"] == jpeg(PORTWELL_MAIN)  # same bytes as the original
    assert "media_reuploaded" in flow.events(PORTWELL_SKU)


def test_restore_reuploads_missing_document_and_keeps_label(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people, mode="documents")
    flow.enable(); flow.approve(); flow.execute()
    flow.shop.missing_files.add("d.pdf")
    flow.restore()
    value = next(m for m in flow.shop.products[PORTWELL_SKU]["meta_data"] if m["key"] == "_wcda_arquivos")["value"]
    assert flow.item()["state"] == "restored"
    assert value[0]["label"] == "Datasheet" and "/up/new-" in value[0]["url"] and value[1] == docs_for(ORIGINS["portwell"])[1]


def test_restore_needs_permission_and_production(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people)
    flow.enable(); flow.approve(); flow.execute()
    flow.envs.set_production(flow.org, "portwell", False, flow.uid("dev"))
    with pytest.raises(ValueError, match="Restauração bloqueada"):
        flow.restore()
    flow.enable()
    with people.session() as db:
        db.query(StoreOperationPermission).filter_by(user_id=people.users["bia"].id, company="portwell").one().can_restore = False
        db.commit()
    flow.restore("bia")  # queued with the grant, refused by the worker
    assert flow.item()["state"] == "restore_error" and "não tem mais permissão" in flow.item()["error"]
    assert flow.shop.products[PORTWELL_SKU]["featured"] == 0


# --- Verificação e reconferência ----------------------------------------------------------------

def test_stale_read_back_is_never_done_and_reconcile_settles_it(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people, mode="main")
    flow.enable(); flow.approve()
    original = flow.shop.handle
    flow.shop.handle = lambda request: httpx.Response(200, json={}) if request.method == "POST" and "/wp/v2/product/" in request.url.path else original(request)
    flow.execute()
    assert flow.item()["state"] == "uncertain" and "não confirmada" in flow.item()["error"]
    flow.removals.request_reconcile(flow.batch, flow.org, flow.uid("ana"), companies=flow.companies("ana"))
    flow.drain()
    assert flow.item()["state"] == "review" and flow.item()["approval"] is None  # store unchanged: approve again
    flow.shop.handle = original
    flow.approve(); flow.execute()
    assert flow.item()["state"] == "done"


def test_reconcile_confirms_a_write_that_landed_late(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people, mode="main")
    flow.enable(); flow.approve()
    original, late = flow.shop.handle, []
    def handle(request):
        if request.method == "POST" and "/wp/v2/product/" in request.url.path:
            late.append(request); return httpx.Response(200, json={})
        return original(request)
    flow.shop.handle = handle
    flow.execute()
    assert flow.item()["state"] == "uncertain"
    original(late[0])  # the store applies it later (cache/queue)
    flow.removals.request_reconcile(flow.batch, flow.org, flow.uid("bia"), companies=flow.companies("bia"))
    flow.drain()
    assert flow.item()["state"] == "done" and flow.item()["result"]["reconciled"]


def test_reprocess_never_replans_an_item_that_may_have_been_written(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people, mode="main")
    flow.enable(); flow.approve()
    flow.shop.fail_on = lambda path, payload: True
    flow.shop.handle_original = flow.shop.handle
    flow.execute()
    assert flow.item()["state"] == "error"  # explicit 500, verified unchanged: safe to plan again
    assert flow.removals.reprocess(flow.batch, flow.org, flow.uid("ana"), companies=flow.companies("ana")) == 1


# --- Concorrência, duplicidade e rede -----------------------------------------------------------

def test_product_changed_between_dry_run_and_execution(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people, mode="gallery")
    flow.enable(); flow.approve()
    flow.shop.products[PORTWELL_SKU]["gallery"].append(18050)
    flow.execute()
    assert flow.item()["state"] == "error" and "concorrente" in flow.item()["error"] and not flow.shop.writes
    assert flow.grant_states() == ["issued"]


def test_duplicate_execution_is_refused(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people)
    flow.enable(); flow.approve()
    flow.execute("bia", drain=False)
    with pytest.raises(ValueError, match="Nenhum item aprovado"):
        flow.execute("bia", drain=False)
    flow.drain()
    writes = len(flow.shop.writes)
    with pytest.raises(ValueError):
        flow.execute("bia")
    grant = grants.listing(jobs)[0]
    assert not grants.consume(jobs, grant) and len(flow.shop.writes) == writes == 1


def test_pause_revokes_unused_production_grants(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people)
    flow.enable(); flow.approve()
    flow.execute("bia", drain=False)
    flow.removals.pause(flow.batch, flow.org, flow.uid("bia"), companies=flow.companies("bia"))
    assert flow.grant_states() == ["revoked"] and flow.item()["state"] == "review"


@pytest.mark.parametrize("failure", ["connect", "timeout_after_write"])
def test_network_failures(jobs, store_settings, people, switch, failure):
    flow = portwell(jobs, store_settings, people, mode="main")
    flow.enable(); flow.approve()
    original = flow.shop.handle
    def handle(request):
        if request.method == "POST" and "/wp/v2/product/" in request.url.path:
            if failure == "connect": raise httpx.ConnectError("rede", request=request)
            original(request); raise httpx.ReadTimeout("resposta perdida", request=request)
        return original(request)
    flow.shop.handle = handle
    flow.execute()
    item = flow.item()
    if failure == "connect":
        # Unknown outcome is decided by the read-back: nothing changed, so it is never "done".
        assert item["state"] == "uncertain" and flow.shop.products[PORTWELL_SKU]["featured"] == PORTWELL_MAIN
    else:
        assert item["state"] == "done" and flow.shop.products[PORTWELL_SKU]["featured"] == 0


def test_invalid_credentials_fail_preflight_and_execution(jobs, store_settings, people, switch):
    shop = portwell_shop()
    original = shop.handle
    shop.handle = lambda request: httpx.Response(401, json={"code": "rest_not_logged_in"}) if request.url.path.endswith("/users/me") else original(request)
    result = production.preflight(store_settings, "portwell", transport=httpx.MockTransport(shop.handle))
    assert not result["ok"] and any("401" in c["detail"] for c in result["checks"])
    assert "app_portwell_secret" not in json.dumps(result) and "ck_portwell_secret" not in json.dumps(result)
    flow = Flow(jobs, store_settings, people, shop, "portwell", "main", [PORTWELL_SKU])
    flow.enable(); flow.approve(); flow.execute()
    assert flow.item()["state"] == "error" and not shop.writes


# --- Diferenças entre lojas ----------------------------------------------------------------------

@pytest.mark.parametrize("company,shape", [
    ("choice", {"featured": 11, "gallery": [12, 13], "docs": True}),
    ("portwell", {"featured": 18039, "gallery": [18040], "docs": True}),
    ("sag", {"featured": 0, "gallery": [31, 32], "docs": False}),  # SAG: gallery without main, no WCDA meta
])
def test_three_stores_remove_all_and_restore(jobs, store_settings, people, switch, company, shape):
    origin = ORIGINS[company]
    product = Shop.product(500, featured=shape["featured"], gallery=shape["gallery"], docs=docs_for(origin), meta=shape["docs"])
    shop = Shop({"000777": product}, origin=origin)
    before = commercial(shop, "000777")
    flow = Flow(jobs, store_settings, people, shop, company, "all", ["000777"])
    dry = flow.item()["dry_run"]
    assert ("Produto sem metadado" in " ".join(dry["warnings"])) == (not shape["docs"])
    flow.enable(); flow.approve(); flow.execute()
    item = flow.item()
    p = shop.products["000777"]
    assert item["state"] == "done" and (p["featured"], p["gallery"]) == (0, [])
    assert item["backup"]["documents"] == (2 if shape["docs"] else 0) and commercial(shop, "000777") == before
    assert backups.folder(jobs, flow.org, company, "000777", dry["dry_run_sha256"]).is_dir()
    flow.restore()
    assert flow.item()["state"] == "restored" and (p["featured"], p["gallery"]) == (shape["featured"], shape["gallery"])


def test_environments_are_independent_per_store(jobs, store_settings, people, switch):
    flow = portwell(jobs, store_settings, people)
    flow.enable()
    assert flow.envs.get(flow.org, "portwell")["active"] and not flow.envs.get(flow.org, "choice")["active"]
    assert not flow.envs.get("outra-org", "portwell")["active"]


# --- API -----------------------------------------------------------------------------------------

@pytest.fixture
def api(jobs, store_settings, people, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.dependencies import get_current_auth
    from app.db import get_db_session
    from app.routers import store_file_removal as router, store_integrations
    from app.services.security import hash_secret
    app = FastAPI(); app.include_router(router.router)
    state = SimpleNamespace(user=people.users["ana"])
    shop = portwell_shop()
    session = people.session()
    app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(user=state.user, login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_db_session] = lambda: session
    monkeypatch.setattr(store_integrations, "StoreSettings", lambda: store_settings)
    monkeypatch.setattr(router, "Jobs", lambda: jobs)
    monkeypatch.setattr(router, "preflight_transport", httpx.MockTransport(shop.handle))
    secure = TestClient(app, base_url="https://prm.local")
    plain = TestClient(app, base_url="http://prm.local")
    drain = lambda: [None for _ in iter(lambda: removal.process_one(jobs, store_settings, httpx.MockTransport(shop.handle), session_factory=people.session), False)]
    yield SimpleNamespace(https=secure, http=plain, state=state, users=people.users, shop=shop, drain=drain, jobs=jobs)
    session.close()


H = {"X-CSRF-Token": "csrf"}


def blocked_attempts(jobs):
    with jobs.db() as db:
        return [json.loads(r["detail"]) for r in db.execute("SELECT detail FROM audit WHERE event='blocked_attempt' ORDER BY at")]


def test_api_full_production_flow_over_https(api, switch):
    c, u = api.https, api.users
    api.state.user = u["dev"]
    envs = c.get("/api/v1/remocao-arquivos/ambientes").json()
    assert envs["master_switch"] and envs["https"] and not envs["companies"][2]["active"]
    wrong = c.post("/api/v1/remocao-arquivos/ambientes/portwell/producao", json={"ativar": True, "confirmacao": "sim"}, headers=H)
    assert wrong.status_code == 422 and "ATIVAR PRODUCAO PORTWELL" in wrong.json()["detail"]
    on = c.post("/api/v1/remocao-arquivos/ambientes/portwell/producao", json={"ativar": True, "confirmacao": "ativar producao portwell"}, headers=H)
    assert on.status_code == 200 and on.json()["active"] and on.json()["preflight"]["ok"]
    api.state.user = u["ana"]
    created = c.post("/api/v1/remocao-arquivos", data={"empresa": "portwell", "modo": "main", "skus": PORTWELL_SKU}, headers=H).json()
    batch = created["id"]; api.drain()
    url = f"/api/v1/remocao-arquivos/{batch}"
    assert c.post(url + "/aprovar", json={}, headers=H).status_code == 200
    assert c.post(url + "/executar", json={"confirmacao": "EXECUTAR 1 PORTWELL"}, headers=H).status_code == 403  # ana cannot execute
    api.state.user = u["bia"]
    assert c.get(url).status_code == 200  # bia sees ana's batch through her store permission
    assert c.post(url + "/executar", json={"confirmacao": "EXECUTAR 2 PORTWELL"}, headers=H).status_code == 422
    done = c.post(url + "/executar", json={"confirmacao": "EXECUTAR 1 PORTWELL"}, headers=H)
    assert done.status_code == 200 and done.json()["items"][0]["state"] == "queued"
    api.drain()
    view = c.get(url).json()
    assert view["items"][0]["state"] == "done" and view["people"][str(u["ana"].id)] == "Ana"
    backup = c.get(url + f"/backup/{PORTWELL_SKU}")
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        assert "manifest.json" in archive.namelist() and any(n.startswith("files/image-") for n in archive.namelist())
    report = c.get(url + "/relatorio").content.decode("utf-8-sig")
    assert "aprovado_por" in report and "Ana" in report and "Bia" in report and "production" in report
    assert c.post(url + "/restaurar", json={"confirmacao": "RESTAURAR 1 PORTWELL"}, headers=H).status_code == 200
    api.drain()
    audit = c.get(url + "/auditoria").json()["items"]
    assert {"approved", "grant_issued", "backup_verified", "removal_verified", "restore_done", "blocked_attempt"} <= {a["event"] for a in audit}
    assert any(a["actor"] == "Ana" and a["event"] == "blocked_attempt" for a in audit)
    for response in (view, audit, envs):
        text = json.dumps(response)
        assert "secret" not in text and "app_portwell" not in text


def test_api_requires_https_for_production_and_audits_refusals(api, switch):
    flow_user = api.users["dev"]
    api.state.user = flow_user
    enabled = api.https.post("/api/v1/remocao-arquivos/ambientes/portwell/producao", json={"ativar": True, "confirmacao": "ATIVAR PRODUCAO PORTWELL"}, headers=H)
    assert enabled.status_code == 200, enabled.text
    api.state.user = api.users["ana"]
    batch = api.http.post("/api/v1/remocao-arquivos", data={"empresa": "portwell", "modo": "main", "skus": PORTWELL_SKU}, headers=H).json()["id"]
    api.drain()
    denied = api.http.post(f"/api/v1/remocao-arquivos/{batch}/aprovar", json={}, headers=H)
    assert denied.status_code == 403 and "HTTPS" in denied.json()["detail"]
    api.state.user = flow_user
    assert api.http.post("/api/v1/remocao-arquivos/ambientes/sag/producao", json={"ativar": True, "confirmacao": "ATIVAR PRODUCAO SAG"}, headers=H).status_code == 403
    # Switching off is the emergency brake: allowed even without HTTPS.
    assert api.http.post("/api/v1/remocao-arquivos/ambientes/portwell/producao", json={"ativar": False}, headers=H).status_code == 200
    reasons = [b["reason"] for b in blocked_attempts(api.jobs)]
    assert sum("HTTPS" in r for r in reasons) == 2


def test_api_environment_and_permission_administration(api, switch, monkeypatch):
    c, u = api.https, api.users
    api.state.user = u["ana"]
    assert c.post("/api/v1/remocao-arquivos/ambientes/choice/producao", json={"ativar": True, "confirmacao": "ATIVAR PRODUCAO CHOICE"}, headers=H).status_code == 403
    assert c.get("/api/v1/remocao-arquivos/permissoes").status_code == 403
    api.state.user = u["dev"]
    monkeypatch.delenv(production.MASTER_SWITCH)
    assert c.post("/api/v1/remocao-arquivos/ambientes/choice/producao", json={"ativar": True, "confirmacao": "ATIVAR PRODUCAO CHOICE"}, headers=H).status_code == 422
    listing = c.get("/api/v1/remocao-arquivos/permissoes").json()
    assert {x["email"] for x in listing["users"]} == {"dev@example.test", "ana@example.test", "bia@example.test", "caio@example.test"}
    change = {"usuario": str(u["caio"].id), "empresa": "sag", "aprovar": True, "executar": False, "restaurar": False, "administrar": False}
    assert c.put("/api/v1/remocao-arquivos/permissoes", json=change, headers=H).json()["permissions"]["approve"]
    assert c.put("/api/v1/remocao-arquivos/permissoes", json={**change, "administrar": True}, headers=H).status_code == 422
    assert api.http.put("/api/v1/remocao-arquivos/permissoes", json=change, headers=H).status_code == 403
    assert c.put("/api/v1/remocao-arquivos/permissoes", json=change).status_code == 403  # CSRF
    off = c.post("/api/v1/remocao-arquivos/ambientes/sag/quatro-olhos", json={"ativar": False, "confirmacao": "x"}, headers=H)
    assert off.status_code == 422
    assert not c.post("/api/v1/remocao-arquivos/ambientes/sag/quatro-olhos", json={"ativar": False, "confirmacao": "DESATIVAR QUATRO OLHOS SAG"}, headers=H).json()["four_eyes"]
    with api.jobs.db() as db:
        events = {r["event"] for r in db.execute("SELECT event FROM audit WHERE batch IN ('permissoes:sag','ambiente:sag','ambiente:choice')")}
    assert {"permission_changed", "four_eyes_disabled", "blocked_attempt"} <= events


def test_api_visibility_between_users_and_organizations(api):
    c, u = api.https, api.users
    api.state.user = u["caio"]  # no store permission
    batch = c.post("/api/v1/remocao-arquivos", data={"empresa": "portwell", "modo": "main", "skus": PORTWELL_SKU}, headers=H).json()["id"]
    api.state.user = u["bia"]
    assert c.get(f"/api/v1/remocao-arquivos/{batch}").status_code == 200  # store permission
    api.state.user = u["fora"]
    assert c.get(f"/api/v1/remocao-arquivos/{batch}").status_code in {403, 404}
    api.state.user = u["vera"]
    assert c.get(f"/api/v1/remocao-arquivos/{batch}").status_code == 403


# --- Página, migração e bootstrap ---------------------------------------------------------------

def test_page_has_production_controls():
    from test_operations_workspace import Elements, render
    html = render("Remoção de Arquivos")
    ids = [a["id"] for _, a in Elements(html).nodes if "id" in a]
    assert len(ids) == len(set(ids))
    assert {"rm-environments", "rm-env-grid", "rm-permissions", "rm-perm-rows", "rm-confirm", "rm-confirm-phrase", "rm-confirm-input",
            "rm-audit", "rm-audit-toggle", "rm-batch-env"} <= set(ids)
    actions = [a.get("data-action") for _, a in Elements(html).nodes if a.get("data-action")]
    assert {"aprovar", "executar", "restaurar", "reconferir", "pausar", "cancelar", "reprocessar"} <= set(actions)
    assert "store_removal_restore.py" not in html  # restoring no longer needs the terminal


def test_migration_adds_only_the_permission_table():
    import importlib.util
    path = Path(__file__).parents[1] / "migrations/versions/20261022_0012_store_operation_permissions.py"
    spec = importlib.util.spec_from_file_location("m0012", path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.down_revision == "20261021_0011" and [t.name for t in module.STORE_OPERATION_TABLES] == ["store_operation_permissions"]


def test_bootstrap_cli_grants_admin_only_to_developers(people, jobs):
    import importlib.util
    path = Path(__file__).parents[1] / "scripts/removal_permissions.py"
    spec = importlib.util.spec_from_file_location("removal_permissions", path); cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
    with people.session() as db:
        with pytest.raises(SystemExit, match="desenvolvedor"):
            cli.grant_admin(db, "ana@example.test", ["sag"], "cli:test", jobs)
        user = cli.grant_admin(db, "caio@example.test".replace("caio", "dev"), ["sag"], "cli:test", jobs)
        assert production.permissions_for(db, user, "sag")["admin"]
    with jobs.db() as db:
        assert db.execute("SELECT event FROM audit WHERE batch='permissoes:sag'").fetchone()["event"] == "permission_bootstrap"
    assert not production.Environments(jobs).get(str(people.org.id), "sag")["production"]  # bootstrap never enables production
