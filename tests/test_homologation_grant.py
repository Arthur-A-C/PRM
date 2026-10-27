"""Single-use production homologation grant (Choice / 119002000072 / 16321). Mocks only, no network."""
import time

import httpx
import pytest
from registration_identity_fixture import mocked_registration_identity
pytestmark = pytest.mark.usefixtures("mocked_registration_identity")

from app.services import store_publish_grant as grants
from app.services.store_config import StoreSettings
from app.services.store_publish import PublishSettings
from app.services.store_registration_jobs import Jobs, process_one, rollback_one
from test_store_registration_zip import COMMERCIAL, EXISTING, Store, commercial, package

SKU, PRODUCT, CHOICE = "119002000072", 16321, "https://choicetech.com.br"


@pytest.fixture
def settings():
    # Production origin on purpose: the MockTransport never reaches the network.
    return StoreSettings(_env_file=None, CHOICE_WC_URL=CHOICE, CHOICE_WC_KEY="ck_test", CHOICE_WC_SECRET="cs_test",
                         CHOICE_WP_USER="wpuser", CHOICE_WP_APP_PASSWORD="app_password", PRM_STORE_ORGANIZATION_ID="org")


@pytest.fixture
def jobs(tmp_path):
    # Current production policy: writes disabled, no staging target.
    return Jobs(PublishSettings(_env_file=None, storage_dir=str(tmp_path / "queue")))


def store(sku=SKU, **kwargs):
    s = Store(sku=sku, **kwargs)
    s.product["id"] = PRODUCT
    return s


def drain(jobs, settings, s):
    while process_one(jobs, settings, httpx.MockTransport(s.handle)): pass


def prepared(jobs, settings, s, sku=SKU):
    identifier = jobs.create("choice", "org", "owner", None, package(sku=sku), settings, identification="folder", archive_name=sku + ".zip")
    drain(jobs, settings, s)
    jobs.approve(identifier, "org", "owner")
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    return identifier, item


def grant(jobs, identifier, item, purpose="publish", minutes=30, **override):
    return grants.issue(jobs, **{"batch": identifier, "sku": item["sku"], "product_id": item["product_id"],
                                 "dry_run_sha256": item["dry_run"]["dry_run_sha256"], "purpose": purpose,
                                 "minutes": minutes, "actor": "tester", **override})


def test_without_grant_still_requires_explicit_confirmation(jobs, settings):
    s = store(wcda=[])
    identifier, item = prepared(jobs, settings, s)
    assert item["state"] == "review" and jobs.detail(identifier, "org", "owner")["can_confirm"] is True
    with pytest.raises(ValueError, match="Confirme"):
        jobs.confirm(identifier, "org", "owner", settings)
    assert set(s.methods) == {"GET"}


def test_grant_publishes_only_files_with_app_password_and_cannot_be_reused(jobs, settings):
    s = store(wcda=[])
    before = commercial(s.product)
    identifier, item = prepared(jobs, settings, s)
    issued = grant(jobs, identifier, item)
    detail = jobs.detail(identifier, "org", "owner")
    assert detail["can_confirm"] and "homologation_grant" not in detail["items"][0]
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    drain(jobs, settings, s)
    done = jobs.detail(identifier, "org", "owner")["items"][0]
    assert done["state"] == "done" and done["result"]["verified"]
    # Only images and _wcda_arquivos changed, through the WordPress application password.
    assert commercial(s.product) == before and len(s.puts) == 1 and set(s.puts[0]) == {"images", "meta_data"}
    assert len(s.product["images"]) == 1 and len(s.product["meta_data"][-1]["value"]) == 2
    assert set(s.write_auth) == {httpx.BasicAuth("wpuser", "app_password")._auth_header}
    events = [e["event"] for e in done["audit"]]
    assert events.index("queued") < events.index("permissions_verified") < events.index("upload_done") < events.index("put_sent")
    assert [g["state"] for g in grants.listing(jobs) if g["id"] == issued["id"]] == ["issued"]
    # Reuse is impossible: the consumed grant unlocks nothing else, and a new preview finds nothing to send.
    assert grants.find(jobs, company="choice", origin=CHOICE, sku=SKU, product_id=PRODUCT,
                       dry_run_sha256=item["dry_run"]["dry_run_sha256"], purpose="publish") is not None
    second = jobs.create("choice", "org", "owner", None, package(sku=SKU), settings, identification="folder", archive_name=SKU + ".zip")
    drain(jobs, settings, s)
    item2 = jobs.detail(second, "org", "owner")["items"][0]
    assert item2["state"] == "blocked" and len(s.puts) == 1  # files already linked by identity
    with pytest.raises(ValueError): grant(jobs, second, item2)


@pytest.mark.parametrize("override,message", [
    ({"sku": "119002000073"}, "não encontrado"),
    ({"product_id": 16322}, "Alvo fora"),
    ({"dry_run_sha256": "0" * 64}, "Hash"),
    ({"minutes": 121}, "Validade"),
    ({"minutes": 0}, "Validade"),
    ({"purpose": "delete"}, "Finalidade"),
])
def test_grant_rejects_anything_but_the_exact_target_and_dry_run(jobs, settings, override, message):
    identifier, item = prepared(jobs, settings, store(wcda=[]))
    with pytest.raises((ValueError, LookupError), match=message):
        grant(jobs, identifier, item, **override)


def test_grant_is_impossible_for_other_skus_products_or_stores(jobs, settings):
    other = store(wcda=[], sku="000123")
    identifier, item = prepared(jobs, settings, other, sku="000123")
    with pytest.raises(ValueError, match="Alvo fora"):
        grant(jobs, identifier, item)
    assert not grants.target_allowed("sag", CHOICE, SKU, PRODUCT)
    assert not grants.target_allowed("choice", "https://www.choicetech.com.br", SKU, PRODUCT)
    assert not grants.target_allowed("choice", CHOICE, SKU, 16322)
    assert grants.target_allowed("choice", CHOICE, SKU, PRODUCT)


def test_grant_requires_approval_and_unique_active_grant(jobs, settings):
    s = store(wcda=[])
    identifier = jobs.create("choice", "org", "owner", None, package(sku=SKU), settings, identification="folder", archive_name=SKU + ".zip")
    drain(jobs, settings, s)
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    with pytest.raises(ValueError, match="não aprovado"): grant(jobs, identifier, item)
    jobs.approve(identifier, "org", "owner")
    issued = grant(jobs, identifier, item)
    with pytest.raises(ValueError, match="ativa"): grant(jobs, identifier, item)
    grants.revoke(jobs, issued["id"], "tester")
    assert jobs.detail(identifier, "org", "owner")["can_confirm"] is True  # legacy revocation is not the role gate
    with pytest.raises(ValueError): grants.revoke(jobs, issued["id"], "tester")


def test_expired_legacy_grant_cannot_block_role_confirmation(jobs, settings):
    s = store(wcda=[])
    identifier, item = prepared(jobs, settings, s)
    issued = grant(jobs, identifier, item, minutes=1)
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    with jobs.db() as db: db.execute("UPDATE grants SET expires=? WHERE id=?", (time.time() - 1, issued["id"]))
    drain(jobs, settings, s)
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    assert item["state"] == "done" and s.posts == 3 and len(s.puts) == 1


def test_concurrent_workers_cannot_both_consume(jobs, settings):
    identifier, item = prepared(jobs, settings, store(wcda=[]))
    issued = grant(jobs, identifier, item)
    assert grants.consume(jobs, issued) is True
    assert grants.consume(jobs, issued) is False


@pytest.mark.parametrize("field,value,missing", [
    ("capabilities", {"upload_files": False, "edit_products": True, "edit_published_products": True, "edit_others_products": True}, "upload_files"),
    ("capabilities", {"upload_files": True, "edit_products": True, "edit_published_products": False, "edit_others_products": True}, "edit_published_products"),
    ("product_allow", "GET", "PUT products/16321"),
    ("media_allow", "GET", "POST media"),
])
def test_missing_permissions_stop_before_any_upload(jobs, settings, field, value, missing):
    s = store(wcda=[])
    identifier, item = prepared(jobs, settings, s)
    grant(jobs, identifier, item)
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    setattr(s, field, value)
    drain(jobs, settings, s)
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    assert item["state"] == "error" and missing in item["error"] and s.posts == 0 and not s.puts


def test_partial_upload_failure_needs_new_grant_and_never_duplicates(jobs, settings):
    s = store(wcda=[]); s.fail_upload = {"Desenho"}
    identifier, item = prepared(jobs, settings, s)
    grant(jobs, identifier, item)
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    drain(jobs, settings, s)
    assert jobs.detail(identifier, "org", "owner")["items"][0]["state"] == "error" and not s.puts and s.posts == 3
    s.fail_upload = set()
    jobs.reprocess(identifier, "org", "owner"); drain(jobs, settings, s)
    jobs.approve(identifier, "org", "owner")
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    with pytest.raises(ValueError, match="Confirme"): jobs.confirm(identifier, "org", "owner", settings)
    # Retrying uses persisted uploads and fresh approval, not another grant.
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    drain(jobs, settings, s)
    assert jobs.detail(identifier, "org", "owner")["items"][0]["state"] == "done"
    assert s.posts == 4 and len(s.puts) == 1 and len(s.library) == 4  # 3 new media, no duplicate


def test_rollback_restores_files_only_keeps_media_and_is_single_use(jobs, settings):
    s = store(wcda=EXISTING)
    before = commercial(s.product)
    identifier, item = prepared(jobs, settings, s)
    with pytest.raises(ValueError, match="Não há publicação"): grant(jobs, identifier, item, purpose="rollback")
    grant(jobs, identifier, item)
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    drain(jobs, settings, s)
    media = dict(s.library)
    with pytest.raises(ValueError, match="Confirme"):
        rollback_one(jobs, settings, identifier, SKU, actor="owner", transport=httpx.MockTransport(s.handle))
    grant(jobs, identifier, item, purpose="rollback")
    result = rollback_one(jobs, settings, identifier, SKU, actor="owner", confirmed=True, transport=httpx.MockTransport(s.handle))
    assert result["status"] == "rolled_back" and result["media_deletion"] is False
    assert s.product["images"] == [] and s.product["meta_data"][-1]["value"] == EXISTING
    assert commercial(s.product) == before and s.library == media and "DELETE" not in s.methods
    with pytest.raises(ValueError):
        rollback_one(jobs, settings, identifier, SKU, actor="owner", confirmed=True, transport=httpx.MockTransport(s.handle))


def test_rollback_refused_when_product_diverged(jobs, settings):
    s = store(wcda=[])
    identifier, item = prepared(jobs, settings, s)
    grant(jobs, identifier, item)
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    drain(jobs, settings, s)
    s.product["images"].append({"id": 10, "src": s.library[10]})  # someone edited after the publish
    grant(jobs, identifier, item, purpose="rollback")
    with pytest.raises(ValueError, match="difere"):
        rollback_one(jobs, settings, identifier, SKU, actor="owner", confirmed=True, transport=httpx.MockTransport(s.handle))
    assert len(s.puts) == 1


def test_missing_product_never_created_even_with_grant(jobs, settings):
    s = store(wcda=[])
    identifier, item = prepared(jobs, settings, s)
    grant(jobs, identifier, item)
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    s.matches = []
    drain(jobs, settings, s)
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    assert item["state"] == "error" and not s.puts and s.posts == 0


def test_cli_requires_exact_confirmation(monkeypatch, jobs, settings):
    import sys
    import scripts.homologation_grant as cli
    monkeypatch.setattr(cli, "Jobs", lambda: jobs)
    monkeypatch.setattr(sys, "argv", ["x", "issue", "--batch", "b", "--sku", SKU, "--product-id", str(PRODUCT),
                                      "--dry-run-sha256", "0" * 64, "--purpose", "publish", "--confirm", "sim"])
    with pytest.raises(SystemExit, match="AUTORIZO publish 119002000072"):
        cli.main()
    assert grants.listing(jobs) == []
