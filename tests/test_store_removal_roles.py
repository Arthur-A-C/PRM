"""Role-v1 removal: real queue/identity checks, disposable files and mocked stores only."""
import json

import pytest

from app.models.identity import User
from app.models.store_operations import StoreOperationPermission
from app.services import removal_backup as backups
from app.services import store_file_removal as removal
from app.services import store_publish_grant as grants
from app.services.store_publish import PublishSettings
from test_store_file_removal import Shop, commercial
from test_store_removal_production import (
    Flow, H, ORIGINS, PORTWELL_SKU, api, docs_for, jobs, people, portwell,
    quick, settings, store_settings,
)


@pytest.fixture(autouse=True)
def no_legacy_authorization(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Removal invoked a legacy authorization gate")
    monkeypatch.setattr(PublishSettings, "authorize", forbidden)
    for name in ("find", "issue_removal", "consume"):
        monkeypatch.setattr(grants, name, forbidden)


@pytest.mark.parametrize("actor", ["ana", "dev"])
@pytest.mark.parametrize("company", sorted(ORIGINS))
@pytest.mark.parametrize("mode", ["main", "gallery", "documents", "all"])
def test_roles_all_stores_all_modes_without_permission_rows(jobs, store_settings, people, actor, company, mode):
    with people.session() as db:
        db.query(StoreOperationPermission).delete()
        db.commit()
    sku = "000007"
    shop = Shop({sku: Shop.product(700, featured=11, gallery=[12], docs=docs_for(ORIGINS[company]))}, origin=ORIGINS[company])
    before = commercial(shop, sku)
    flow = Flow(jobs, store_settings, people, shop, company, mode, [sku])
    flow.approve(actor)
    flow.execute(actor)
    item = flow.item()
    assert item["sku"] == sku and item["state"] == "done"
    assert item["backup"]["verified"] and item["result"]["verified"]
    assert commercial(shop, sku) == before
    flow.restore(actor)
    assert flow.item()["state"] == "restored" and flow.item()["restore"]["verified"]
    assert shop.products[sku]["featured"] == 11 and shop.products[sku]["gallery"] == [12]
    assert commercial(shop, sku) == before
    assert "DELETE" not in shop.methods and flow.grant_states() == []


@pytest.mark.parametrize("change", ["payload", "hash", "sku", "product_id", "mode", "approver", "actor", "org", "company", "origin", "confirmed"])
def test_worker_rejects_modified_confirmation_or_dry_run(jobs, store_settings, people, change):
    flow = portwell(jobs, store_settings, people)
    flow.approve("ana")
    flow.execute("ana", drain=False)
    with jobs.db() as db:
        plan = json.loads(db.execute("SELECT plan FROM removal_items WHERE batch=?", (flow.batch,)).fetchone()[0])
        if change == "payload": plan["dry_run"]["writes"][0]["payload"]["featured_media"] = 666
        elif change == "hash": plan["dry_run"]["dry_run_sha256"] = "0" * 64
        elif change == "mode": plan["dry_run"]["mode"] = "all"
        elif change == "actor": plan["execution"]["by"] = flow.uid("vera")
        elif change == "approver": plan["execution"]["approver"] = flow.uid("dev")
        elif change == "confirmed": plan["execution"]["confirmed"] = False
        else: plan["execution"][change] = "modified"
        db.execute("UPDATE removal_items SET plan=? WHERE batch=?", (json.dumps(plan), flow.batch))
    flow.drain()
    assert flow.item()["state"] == "blocked" and not flow.shop.writes


@pytest.mark.parametrize("change", ["role", "inactive", "organization", "approver", "queue_token", "price"])
def test_revalidation_after_backup_prevents_writes(jobs, store_settings, people, monkeypatch, change):
    flow = portwell(jobs, store_settings, people)
    flow.approve("ana")
    flow.execute("bia", drain=False)
    capture = backups.capture

    def modified_during_backup(*args, **kwargs):
        result = capture(*args, **kwargs)
        if change == "queue_token":
            with jobs.db() as db:
                db.execute("UPDATE removal_items SET token='lost' WHERE batch=?", (flow.batch,))
        elif change == "price":
            flow.shop.products[PORTWELL_SKU]["regular_price"] = "1234.56"
        else:
            with people.session() as db:
                user = db.get(User, people.users["ana" if change == "approver" else "bia"].id)
                if change in ("role", "approver"): user.role = "vendedor"
                elif change == "inactive": user.active = False
                else: user.organization_id = people.users["fora"].organization_id
                db.commit()
        return result

    monkeypatch.setattr(backups, "capture", modified_during_backup)
    flow.drain()
    assert not flow.shop.writes and "done" not in flow.events()


@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_stopped_restore_can_be_confirmed_again(jobs, store_settings, people, action):
    flow = portwell(jobs, store_settings, people)
    flow.approve("ana"); flow.execute("ana"); flow.restore("ana", drain=False)
    writes = len(flow.shop.writes)
    assert getattr(flow.removals, action)(flow.batch, flow.org, flow.uid("ana"), companies=flow.companies("ana")) == 1
    flow.drain()
    assert len(flow.shop.writes) == writes and flow.item()["restorable"]
    flow.restore("ana")
    assert flow.item()["state"] == "restored"


def test_restore_refuses_invalid_backup(jobs, store_settings, people, monkeypatch):
    flow = portwell(jobs, store_settings, people)
    flow.approve("ana"); flow.execute("ana"); flow.restore("ana", drain=False)
    writes = len(flow.shop.writes)
    def invalid(*args, **kwargs):
        raise backups.BackupError("Backup inválido")
    monkeypatch.setattr(backups, "verify", invalid)
    flow.drain()
    assert flow.item()["state"] == "restore_error" and len(flow.shop.writes) == writes


@pytest.mark.parametrize("action", ["aprovar", "executar", "restaurar", "reconferir", "pausar", "cancelar", "reprocessar"])
def test_seller_cannot_operate_any_action(api, action):
    c = api.https
    batch = c.post("/api/v1/remocao-arquivos", data={"empresa": "portwell", "modo": "main", "skus": PORTWELL_SKU}, headers=H).json()["id"]
    api.state.user = api.users["vera"]
    result = c.post(f"/api/v1/remocao-arquivos/{batch}/{action}", json={}, headers=H)
    assert result.status_code == 403 and "cargo" in result.json()["detail"]
    assert not api.shop.writes


def test_fastapi_validation_returns_details_array(api):
    result = api.https.post("/api/v1/remocao-arquivos/not-a-batch/executar", json={"skus": 123}, headers=H)
    assert result.status_code == 422 and isinstance(result.json()["detail"], list)
