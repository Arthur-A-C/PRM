"""Final audit of the role-based files publish path (mocks only, no network).

Registration no longer uses grants: every write needs the approved, sealed Dry Run and an explicit
confirmation by an active gestor/desenvolvedor. Identity is mocked here (file-processing tests);
real role/organization checks live in test_store_registration_roles.py.
"""
import threading

import httpx
import pytest

from app.services import store_publish_grant as grants
from app.services.store_config import StoreSettings
from app.services.store_publish import PublishSettings
from app.services.store_registration_jobs import Jobs, process_one, rollback_one
from test_homologation_grant import CHOICE, PRODUCT, SKU, drain, grant, jobs, prepared, settings, store  # noqa: F401
from test_store_registration_zip import EXISTING, Store, commercial, package
from registration_identity_fixture import mocked_registration_identity  # noqa: F401

pytestmark = pytest.mark.usefixtures("mocked_registration_identity")


def queued(jobs, settings, s):
    identifier, item = prepared(jobs, settings, s)
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    return identifier


def test_targeted_worker_processes_only_the_authorized_item(jobs, settings):
    other = Store(sku="000123", wcda=[])
    older = jobs.create("choice", "org", "owner", None, package(sku="000123"), settings, identification="folder", archive_name="000123.zip")
    s = store(wcda=[])
    # Target is prepared with a targeted claim so the older batch stays pending throughout.
    target = jobs.create("choice", "org", "owner", None, package(sku=SKU), settings, identification="folder", archive_name=SKU + ".zip")
    assert process_one(jobs, settings, httpx.MockTransport(s.handle), batch=target, sku=SKU)
    jobs.approve(target, "org", "owner")
    jobs.confirm(target, "org", "owner", settings, [SKU], confirmed=True)
    assert process_one(jobs, settings, httpx.MockTransport(s.handle), batch=target, sku=SKU)
    assert not process_one(jobs, settings, httpx.MockTransport(s.handle), batch=target, sku=SKU)  # nothing else for it
    assert jobs.detail(target, "org", "owner")["items"][0]["state"] == "done"
    assert jobs.detail(older, "org", "owner")["items"][0]["state"] == "preview_queued" and other.methods == []


def test_two_workers_consume_a_grant_exactly_once(jobs, settings):
    identifier, item = prepared(jobs, settings, store(wcda=[]))
    issued = grant(jobs, identifier, item)
    barrier, results = threading.Barrier(8), []
    def worker():
        barrier.wait(); results.append(grants.consume(jobs, issued))
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sorted(results) == [False] * 7 + [True]


def test_two_workers_never_claim_the_same_item(jobs, settings):
    queued(jobs, settings, store(wcda=[]))
    barrier, claims = threading.Barrier(6), []
    def worker():
        barrier.wait(); claims.append(jobs.claim())
    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len([c for c in claims if c]) == 1


def test_concurrent_change_between_uploads_and_put_blocks_update(jobs, settings):
    s = store(wcda=[])
    identifier = queued(jobs, settings, s)
    s.on_get = lambda shop: shop.posts and shop.product["images"].append({"id": 10, "src": shop.library[10]}) if not shop.product["images"] else None
    drain(jobs, settings, s)
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    assert item["state"] == "error" and "concorrente" in item["error"] and s.posts == 3 and not s.puts


class PluginStore(Store):
    """Simulates WordPress/plugin side effects of a product save."""
    def __init__(self, effect, **kwargs):
        super().__init__(sku=SKU, **kwargs)
        self.product["id"] = PRODUCT
        self.product["meta_data"].insert(1, {"id": 2, "key": "_yoast_indexnow_last_ping", "value": "100"})
        self.product["meta_data"].insert(2, {"id": 3, "key": "_oembed_time_abc", "value": "100"})
        self.effect = effect

    def handle(self, request):
        response = super().handle(request)
        if request.method == "PUT": self.effect(self.product)
        return response


def meta(product, key):
    return next(m for m in product["meta_data"] if m["key"] == key)


@pytest.mark.parametrize("effect", [
    lambda p: meta(p, "_yoast_indexnow_last_ping").update(value="200"),
    lambda p: meta(p, "_oembed_time_abc").update(value="200"),
])
def test_plugin_volatile_meta_on_save_is_not_a_false_failure(jobs, settings, effect):
    s = PluginStore(effect, wcda=[])
    identifier = queued(jobs, settings, s)
    drain(jobs, settings, s)
    assert jobs.detail(identifier, "org", "owner")["items"][0]["state"] == "done"


@pytest.mark.parametrize("effect", [
    lambda p: p.update(regular_price="1.00"),
    lambda p: p.update(stock_quantity=0),
    lambda p: p.update(status="draft"),
    lambda p: p.update(name="Outro nome"),
    lambda p: p.update(description="<p>x</p>"),
    lambda p: p.update(categories=[]),
    lambda p: p.update(attributes=[]),
    lambda p: meta(p, "_yoast_wpseo_focuskw").update(value="alterado"),
    lambda p: p["meta_data"].append({"id": 9, "key": "manager_id", "value": "1"}),
])
def test_post_put_verification_detects_protected_field_changes(jobs, settings, effect):
    s = PluginStore(effect, wcda=[])
    identifier = queued(jobs, settings, s)
    drain(jobs, settings, s)
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    # The PUT was sent and the read-back does not match: never "done", and "uncertain" (manual reconciliation)
    # rather than "error", which would suggest a safe blind retry.
    assert item["state"] == "uncertain" and "não confirmada" in item["error"] and len(s.puts) == 1


def test_every_write_touches_only_images_and_wcda(jobs, settings):
    s = store(images=[10], wcda=EXISTING)
    before = commercial(s.product)
    identifier, item = prepared(jobs, settings, s)
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True); drain(jobs, settings, s)
    rollback_one(jobs, settings, identifier, SKU, actor="owner", confirmed=True, transport=httpx.MockTransport(s.handle))
    assert len(s.puts) == 2 and all(set(p) <= {"images", "meta_data"} for p in s.puts)
    assert all(m["key"] == "_wcda_arquivos" and m["id"] == 92930 for p in s.puts for m in p.get("meta_data", []))
    assert commercial(s.product) == before and [i["id"] for i in s.product["images"]] == [10]
    assert meta(s.product, "_wcda_arquivos")["value"] == EXISTING
    assert {"POST", "PUT", "GET", "OPTIONS"} >= set(s.methods) and "DELETE" not in s.methods


def test_first_inclusion_publish_and_rollback_round_trip(jobs, settings):
    s = store(wcda=[])
    identifier, item = prepared(jobs, settings, s)
    assert item["dry_run"]["documents"]["mode"] == "first_inclusion"
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True); drain(jobs, settings, s)
    value = meta(s.product, "_wcda_arquivos")["value"]
    assert [d["label"] for d in value] == ["Datasheet", "Desenho 3D"]
    assert all(d["url"].startswith(s.library[101].rsplit("/", 1)[0]) for d in value)  # real URLs returned by the upload
    result = rollback_one(jobs, settings, identifier, SKU, actor="owner", confirmed=True, transport=httpx.MockTransport(s.handle))
    assert result["status"] == "rolled_back" and meta(s.product, "_wcda_arquivos")["value"] == [] and s.product["images"] == []
    assert len(s.library) == 4  # uploaded media kept


def test_no_credential_reaches_storage_logs_or_output(tmp_path, capsys, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    secrets = ["ck_SEGREDO_WOO", "cs_SEGREDO_WOO", "SENHA-APP-SEGREDO"]
    settings = StoreSettings(_env_file=None, CHOICE_WC_URL=CHOICE, CHOICE_WC_KEY=secrets[0], CHOICE_WC_SECRET=secrets[1],
                             CHOICE_WP_USER="wpuser", CHOICE_WP_APP_PASSWORD=secrets[2], PRM_STORE_ORGANIZATION_ID="org")
    jobs = Jobs(PublishSettings(_env_file=None, storage_dir=str(tmp_path / "queue")))
    s = store(wcda=[]); s.fail_upload = {"Desenho"}  # include an error path in the audit trail
    identifier = queued(jobs, settings, s)
    drain(jobs, settings, s)
    detail = str(jobs.detail(identifier, "org", "owner")) + repr(settings) + str(grants.listing(jobs))
    stored = b"".join(p.read_bytes() for p in (tmp_path / "queue").rglob("*") if p.is_file())
    captured = capsys.readouterr()
    for secret in secrets:
        assert secret not in detail and secret.encode() not in stored
        assert secret not in captured.out + captured.err and secret not in caplog.text


class FlippingStore(Store):
    """Portwell-like: two "Painel PC" categories listed in alternating order on each product response."""
    PAINEL = [{"id": 506, "name": "Painel PC", "slug": "painel-pc-painel-pc"}, {"id": 444, "name": "Painel PC", "slug": "painel-pc"}]

    def __init__(self, **kwargs):
        super().__init__(sku=SKU, **kwargs)
        self.product["id"] = PRODUCT
        self.product["categories"] = [dict(c) for c in self.PAINEL]
        self.responses = 0

    def handle(self, request):
        response = super().handle(request)
        if "/wc/v3/products" in request.url.path and response.status_code == 200:
            self.responses += 1
            if self.responses % 2:
                data = response.json()
                for product in data if isinstance(data, list) else [data]:
                    product["categories"] = list(reversed(product["categories"]))
                return httpx.Response(200, json=data)
        return response


def test_store_reordering_categories_is_not_a_concurrent_change(jobs, settings):
    s = FlippingStore(wcda=[])
    before = commercial(s.product)
    identifier = queued(jobs, settings, s)
    drain(jobs, settings, s)
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    assert item["state"] == "done", item["error"]
    assert len(s.puts) == 1 and commercial(s.product) == before
