"""Remoção de arquivos: four modes, preservation, concurrency, rollback and batch. Mocks only."""
import json
import threading
from copy import deepcopy

import httpx
import pytest

from app.services import store_file_removal as removal
from app.services import store_publish_grant as grants
from app.services.store_config import StoreSettings
from app.services.store_publish import PublishSettings
from app.services.store_registration_jobs import Jobs

ORIGIN = "https://staging.example.test"
DOCS = [{"label": "Datasheet", "url": ORIGIN + "/up/d.pdf", "filename": "d.pdf", "filesize": "90.8 KB"},
        {"label": "Desenho 3D", "url": ORIGIN + "/up/3d.zip", "filename": "3d.zip", "filesize": "2.84 MB"}]
COMMERCIAL = {"name": "Botoeira M1212P", "description": "<p>Texto do CSV</p>", "short_description": "<p>Curta</p>",
              "categories": [{"id": 5}], "attributes": [{"id": 0, "name": "Cor", "options": ["Preto"]}],
              "regular_price": "199.90", "sale_price": "", "stock_quantity": 7, "stock_status": "instock", "status": "publish"}


class Shop:
    """WooCommerce + WordPress double with the real image semantics (images[0] = main; featured_media = main only)."""
    def __init__(self, products=None):
        self.products = products or {"000123": self.product(101, featured=11, gallery=[12, 13], docs=DOCS)}
        self.methods, self.writes = [], []
        self.fail_on = None
        self.on_get = None

    @staticmethod
    def product(identifier, *, featured=0, gallery=(), docs=None, meta=True):
        data = {"id": identifier, **deepcopy(COMMERCIAL), "featured": featured, "gallery": list(gallery),
                "meta_data": [{"id": 1, "key": "_yoast_wpseo_focuskw", "value": "botoeira"}]}
        if meta: data["meta_data"].append({"id": 500 + identifier, "key": "_wcda_arquivos", "value": deepcopy(docs or [])})
        return data

    def find(self, identifier):
        return next((s, p) for s, p in self.products.items() if p["id"] == identifier)

    def wc_view(self, sku, p):
        images = ([p["featured"]] if p["featured"] else []) + p["gallery"]
        return {"id": p["id"], "sku": sku, **{k: deepcopy(p[k]) for k in COMMERCIAL},
                "images": [{"id": i, "src": f"{ORIGIN}/up/img-{i}.jpg", "position": n} for n, i in enumerate(images)],
                "meta_data": deepcopy(p["meta_data"])}

    def handle(self, request):
        path, method = request.url.path, request.method
        self.methods.append(method)
        assert method != "DELETE", "media or product must never be deleted"
        if method == "OPTIONS":
            return httpx.Response(200, headers={"Allow": "GET, POST" if path.endswith("/media") else "GET, POST, PUT, PATCH"})
        if path.endswith("/users/me"):
            return httpx.Response(200, json={"id": 7, "capabilities": {c: True for c in ("upload_files", "edit_products", "edit_published_products", "edit_others_products")}})
        if path.endswith("/products"):
            sku = request.url.params["sku"]
            return httpx.Response(200, json=[self.wc_view(sku, self.products[sku])] if sku in self.products else [])
        identifier = int(path.rsplit("/", 1)[1])
        sku, p = self.find(identifier)
        if method == "GET":
            if self.on_get: self.on_get(self)
            if "/wp/v2/product/" in path:
                return httpx.Response(200, json={"id": identifier, "featured_media": p["featured"]})
            return httpx.Response(200, json=self.wc_view(sku, p))
        payload = json.loads(request.content)
        self.writes.append((path.split("/wp-json/")[1], payload))
        if self.fail_on and self.fail_on(path, payload): return httpx.Response(500, json={})
        if "/wp/v2/product/" in path:
            assert set(payload) == {"featured_media"}
            p["featured"] = payload["featured_media"]
            return httpx.Response(200, json={"id": identifier, "featured_media": p["featured"]})
        assert set(payload) <= {"images", "meta_data"}
        if "images" in payload:  # WC_REST_Products_Controller::set_product_images
            ids = [i["id"] for i in payload["images"]]
            p["featured"], p["gallery"] = (ids[0], list(dict.fromkeys(ids[1:]))) if ids else (0, [])
        for meta in payload.get("meta_data", []):
            assert meta["key"] == "_wcda_arquivos"
            next(m for m in p["meta_data"] if m["id"] == meta["id"])["value"] = meta["value"]
        return httpx.Response(200, json=self.wc_view(sku, p))


@pytest.fixture
def settings():
    return StoreSettings(_env_file=None, CHOICE_WC_URL=ORIGIN, CHOICE_WC_KEY="ck_test", CHOICE_WC_SECRET="cs_test",
                         CHOICE_WP_USER="user", CHOICE_WP_APP_PASSWORD="app_password", PRM_STORE_ORGANIZATION_ID="org")


class OpenStaging(PublishSettings):
    def authorize(self, origin, sku):
        if origin != ORIGIN: raise ValueError("Gravação bloqueada nesta política de teste.")


@pytest.fixture
def jobs(tmp_path):
    return Jobs(OpenStaging(_env_file=None, storage_dir=str(tmp_path / "queue")))


def drain(jobs, settings, shop):
    while removal.process_one(jobs, settings, httpx.MockTransport(shop.handle)): pass


def dry(jobs, settings, shop, mode, skus=("000123",)):
    removals = removal.Removals(jobs)
    identifier = removals.create("choice", "org", "owner", mode, list(skus), settings)
    drain(jobs, settings, shop)
    return removals, identifier, removals.detail(identifier, "org", "owner")


def execute(removals, identifier, jobs, settings, shop, skus=None):
    removals.approve(identifier, "org", "owner", skus)
    removals.confirm(identifier, "org", "owner", settings, skus)
    drain(jobs, settings, shop)
    return removals.detail(identifier, "org", "owner")


def commercial(shop, sku="000123"):
    p = shop.products[sku]
    return {k: p[k] for k in COMMERCIAL} | {"meta": [m for m in p["meta_data"] if m["key"] != "_wcda_arquivos"]}


def docs(shop, sku="000123"):
    return next(m for m in shop.products[sku]["meta_data"] if m["key"] == "_wcda_arquivos")["value"]


# --- Os quatro modos -------------------------------------------------------------------------

def test_remove_all_unlinks_images_and_documents_only(jobs, settings):
    shop = Shop(); before = commercial(shop)
    removals, identifier, view = dry(jobs, settings, shop, "all")
    item = view["items"][0]
    assert item["state"] == "review" and set(shop.methods) == {"GET"}
    d = item["dry_run"]
    assert [i["id"] for i in d["unlink"]["images"]] == [11, 12, 13] and len(d["unlink"]["documents"]) == 2
    assert d["proposed"] == {"main": None, "gallery": [], "documents": []} and d["media_deletion"] is False
    assert d["writes"] == [{"api": "woocommerce", "method": "PUT", "endpoint": "products/101",
                            "payload": {"images": [], "meta_data": [{"id": 601, "key": "_wcda_arquivos", "value": []}]}}]
    result = execute(removals, identifier, jobs, settings, shop)["items"][0]
    assert result["state"] == "done" and result["result"]["verified"]
    p = shop.products["000123"]
    assert (p["featured"], p["gallery"], docs(shop)) == (0, [], []) and commercial(shop) == before


def test_remove_gallery_keeps_main_and_documents(jobs, settings):
    shop = Shop(); before = commercial(shop)
    removals, identifier, view = dry(jobs, settings, shop, "gallery")
    d = view["items"][0]["dry_run"]
    assert [i["id"] for i in d["unlink"]["images"]] == [12, 13] and d["unlink"]["documents"] == []
    assert [i["id"] for i in d["preserve"]["images"]] == [11] and len(d["preserve"]["documents"]) == 2
    assert d["writes"][0]["payload"] == {"images": [{"id": 11}]}  # main kept explicitly at position 0
    execute(removals, identifier, jobs, settings, shop)
    p = shop.products["000123"]
    assert (p["featured"], p["gallery"], docs(shop)) == (11, [], DOCS) and commercial(shop) == before


def test_remove_documents_clears_only_wcda(jobs, settings):
    shop = Shop(); before = commercial(shop)
    removals, identifier, view = dry(jobs, settings, shop, "documents")
    d = view["items"][0]["dry_run"]
    assert d["unlink"]["images"] == [] and [x["label"] for x in d["unlink"]["documents"]] == ["Datasheet", "Desenho 3D"]
    assert d["writes"][0]["payload"] == {"meta_data": [{"id": 601, "key": "_wcda_arquivos", "value": []}]}
    execute(removals, identifier, jobs, settings, shop)
    p = shop.products["000123"]
    assert (p["featured"], p["gallery"], docs(shop)) == (11, [12, 13], []) and commercial(shop) == before


def test_remove_main_never_promotes_a_gallery_image(jobs, settings):
    shop = Shop(); before = commercial(shop)
    removals, identifier, view = dry(jobs, settings, shop, "main")
    d = view["items"][0]["dry_run"]
    assert [i["id"] for i in d["unlink"]["images"]] == [11] and [g["id"] for g in d["proposed"]["gallery"]] == [12, 13]
    assert d["writes"] == [{"api": "wordpress", "method": "POST", "endpoint": "product/101", "payload": {"featured_media": 0}}]
    assert any("sem promoção" in w for w in d["warnings"])
    result = execute(removals, identifier, jobs, settings, shop)["items"][0]
    assert result["state"] == "done"
    p = shop.products["000123"]
    assert (p["featured"], p["gallery"], docs(shop)) == (0, [12, 13], DOCS) and commercial(shop) == before
    assert not any("products/" in path for path, _ in shop.writes)  # WooCommerce images never rewritten


def test_why_main_removal_cannot_use_woocommerce_images():
    shop = Shop()
    shop.handle(httpx.Request("PUT", ORIGIN + "/wp-json/wc/v3/products/101", json={"images": [{"id": 12}, {"id": 13}]}))
    assert shop.products["000123"]["featured"] == 12  # images[0] is promoted: the reason for featured_media=0


def test_reading_gallery_without_main_uses_featured_media(jobs, settings):
    shop = Shop({"000123": Shop.product(101, featured=0, gallery=[12, 13], docs=DOCS)})
    _, _, view = dry(jobs, settings, shop, "main")
    d = view["items"][0]["dry_run"]
    assert d["current"]["main"] is None and [g["id"] for g in d["current"]["gallery"]] == [12, 13]
    assert view["items"][0]["state"] == "nothing"
    _, _, view = dry(jobs, settings, shop, "gallery")
    assert view["items"][0]["dry_run"]["writes"][0]["payload"] == {"images": []}


# --- SKUs, duplicidades e bloqueios -----------------------------------------------------------

def test_sku_input_preserves_zeros_and_removes_duplicates():
    skus, duplicates = removal.parse_skus("000123\n000124; 000123,ABC-9\t000124")
    assert skus == ["000123", "000124", "ABC-9"] and duplicates == 2
    skus, _ = removal.parse_skus("", b"SKU\n000777\n000123", "lista.csv")
    assert skus == ["000777", "000123"]
    with pytest.raises(ValueError): removal.parse_skus("1.2e+11")
    with pytest.raises(ValueError): removal.parse_skus("  ")


def test_missing_sku_is_skipped_and_duplicate_store_sku_fails(jobs, settings):
    shop = Shop()
    _, _, view = dry(jobs, settings, shop, "all", ("999999",))
    assert view["items"][0]["state"] == "not_found" and set(shop.methods) == {"GET"}
    original = shop.handle
    def duplicated(request):
        if request.url.path.endswith("/products"):
            row = shop.wc_view("000123", shop.products["000123"])
            return httpx.Response(200, json=[row, {**row, "id": 202}])
        return original(request)
    shop.handle = duplicated
    _, _, view = dry(jobs, settings, shop, "all")
    assert view["items"][0]["state"] == "error" and "duplicado" in view["items"][0]["error"]


def test_invalid_wcda_blocks_document_modes_only(jobs, settings):
    p = Shop.product(101, featured=11, gallery=[12], docs=DOCS)
    p["meta_data"].append({"id": 999, "key": "_wcda_arquivos", "value": []})  # duplicated meta
    shop = Shop({"000123": p})
    _, _, view = dry(jobs, settings, shop, "documents")
    assert view["items"][0]["state"] == "blocked"
    _, _, view = dry(jobs, settings, shop, "gallery")
    assert view["items"][0]["state"] == "review"


def test_nothing_to_remove_is_not_queued(jobs, settings):
    shop = Shop({"000123": Shop.product(101, featured=0, gallery=[], docs=[], meta=False)})
    removals, identifier, view = dry(jobs, settings, shop, "all")
    assert view["items"][0]["state"] == "nothing" and view["skipped"] == 1
    with pytest.raises(ValueError): removals.approve(identifier, "org", "owner")


def test_inconsistent_main_image_is_refused(jobs, settings):
    shop = Shop()
    original = shop.handle
    shop.handle = lambda r: httpx.Response(200, json={"id": 101, "featured_media": 99}) if "/wp/v2/product/" in r.url.path and r.method == "GET" else original(r)
    _, _, view = dry(jobs, settings, shop, "main")
    assert view["items"][0]["state"] == "error" and "inconsistente" in view["items"][0]["error"]


# --- Segurança: aprovação, produção, concorrência e verificação --------------------------------

def test_execution_requires_approval_of_exact_dry_run(jobs, settings):
    shop = Shop()
    removals, identifier, _ = dry(jobs, settings, shop, "all")
    with pytest.raises(ValueError, match="aprovado"): removals.confirm(identifier, "org", "owner", settings)
    assert not shop.writes


@pytest.mark.parametrize("host", ["choicetech.com.br", "sagloja.devsplcomunic.com.br", "portwell.com.br"])
def test_production_is_blocked_without_a_grant(tmp_path, host):
    settings = StoreSettings(_env_file=None, CHOICE_WC_URL="https://" + host, CHOICE_WC_KEY="ck", CHOICE_WC_SECRET="cs",
                             CHOICE_WP_USER="u", CHOICE_WP_APP_PASSWORD="p", PRM_STORE_ORGANIZATION_ID="org")
    jobs = Jobs(PublishSettings(_env_file=None, enabled=True, staging_origin="https://" + host, staging_sku="000123", storage_dir=str(tmp_path / "q")))
    shop = Shop()
    removals, identifier, view = dry(jobs, settings, shop, "all")
    assert "bloqueada" in view["items"][0]["dry_run"]["write_gate"]
    removals.approve(identifier, "org", "owner")
    with pytest.raises(ValueError, match="Sem liberação"): removals.confirm(identifier, "org", "owner", settings)
    assert set(shop.methods) == {"GET"}


def test_grant_scoped_to_store_sku_product_mode_and_hash(tmp_path):
    settings = StoreSettings(_env_file=None, CHOICE_WC_URL="https://choicetech.com.br", CHOICE_WC_KEY="ck", CHOICE_WC_SECRET="cs",
                             CHOICE_WP_USER="u", CHOICE_WP_APP_PASSWORD="p", PRM_STORE_ORGANIZATION_ID="org")
    jobs = Jobs(PublishSettings(_env_file=None, storage_dir=str(tmp_path / "q")))
    shop = Shop({"119002000072": Shop.product(16321, featured=11, gallery=[12], docs=DOCS),
                 "000123": Shop.product(101, featured=21, gallery=[22], docs=[])})
    before = commercial(shop, "119002000072")
    removals, identifier, _ = dry(jobs, settings, shop, "gallery", ("119002000072", "000123"))
    removals.approve(identifier, "org", "owner")
    with pytest.raises(ValueError, match="Alvo fora"):
        grants.issue_removal(jobs, batch=identifier, sku="000123", minutes=30, actor="t")
    grant = grants.issue_removal(jobs, batch=identifier, sku="119002000072", minutes=30, actor="t")
    assert grant["purpose"] == "remove_gallery" and grant["product_id"] == 16321
    with pytest.raises(ValueError, match="Sem liberação"): removals.confirm(identifier, "org", "owner", settings)  # 000123 still blocked
    removals.confirm(identifier, "org", "owner", settings, ["119002000072"])
    drain(jobs, settings, shop)
    assert shop.products["119002000072"]["gallery"] == [] and commercial(shop, "119002000072") == before
    assert [g["state"] for g in grants.listing(jobs)] == ["consumed"]
    with pytest.raises(ValueError): grants.issue_removal(jobs, batch=identifier, sku="119002000072", minutes=30, actor="t")  # done, not review


def test_concurrent_change_after_dry_run_writes_nothing(jobs, settings):
    shop = Shop()
    removals, identifier, _ = dry(jobs, settings, shop, "gallery")
    shop.products["000123"]["gallery"].append(14)  # someone added a photo
    item = execute(removals, identifier, jobs, settings, shop)["items"][0]
    assert item["state"] == "error" and "concorrente" in item["error"] and not shop.writes


def test_concurrent_change_between_permission_check_and_write(jobs, settings):
    shop = Shop()
    removals, identifier, _ = dry(jobs, settings, shop, "documents")
    seen = {"options": False}
    original = shop.handle
    def handle(request):
        if request.method == "OPTIONS": seen["options"] = True
        elif seen["options"] and request.method == "GET" and "/wp/v2/product/" not in request.url.path and not request.url.path.endswith("/products"):
            shop.products["000123"]["meta_data"][-1]["value"] = DOCS[:1]
        return original(request)
    shop.handle = handle
    item = execute(removals, identifier, jobs, settings, shop)["items"][0]
    assert item["state"] == "error" and "concorrente" in item["error"] and not shop.writes


def test_commercial_field_changed_during_write_is_detected(jobs, settings):
    shop = Shop()
    removals, identifier, _ = dry(jobs, settings, shop, "all")
    shop.fail_on = lambda path, payload: shop.products["000123"].update(regular_price="1.00") and False
    item = execute(removals, identifier, jobs, settings, shop)["items"][0]
    assert item["state"] == "error" and "não confirmada" in item["error"]


# --- Rollback ---------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["all", "gallery", "documents", "main"])
def test_restore_puts_back_previous_links_for_each_mode(jobs, settings, mode):
    shop = Shop(); before = commercial(shop)
    removals, identifier, _ = dry(jobs, settings, shop, mode)
    execute(removals, identifier, jobs, settings, shop)
    result = removal.restore_one(jobs, settings, identifier, "000123", actor="t", transport=httpx.MockTransport(shop.handle))
    assert result["status"] == "restored" and result["media_deletion"] is False
    p = shop.products["000123"]
    assert (p["featured"], p["gallery"], docs(shop)) == (11, [12, 13], DOCS) and commercial(shop) == before
    assert removal.restore_one(jobs, settings, identifier, "000123", actor="t", transport=httpx.MockTransport(shop.handle))["reconciled"]


def test_restore_of_gallery_without_main_does_not_leave_a_promoted_image(jobs, settings):
    shop = Shop({"000123": Shop.product(101, featured=0, gallery=[12, 13], docs=DOCS)})
    removals, identifier, _ = dry(jobs, settings, shop, "all")
    execute(removals, identifier, jobs, settings, shop)
    removal.restore_one(jobs, settings, identifier, "000123", actor="t", transport=httpx.MockTransport(shop.handle))
    p = shop.products["000123"]
    assert (p["featured"], p["gallery"]) == (0, [12, 13])


def test_restore_refused_when_product_changed_after_removal(jobs, settings):
    shop = Shop()
    removals, identifier, _ = dry(jobs, settings, shop, "gallery")
    execute(removals, identifier, jobs, settings, shop)
    shop.products["000123"]["gallery"] = [44]
    with pytest.raises(ValueError, match="difere"):
        removal.restore_one(jobs, settings, identifier, "000123", actor="t", transport=httpx.MockTransport(shop.handle))


# --- Lote: progresso, falhas, pausa, retomada e relatório -------------------------------------

def batch_shop():
    return Shop({f"00{n}": Shop.product(100 + n, featured=10 * n + 1, gallery=[10 * n + 2], docs=DOCS) for n in range(1, 5)})


def test_batch_continues_after_individual_failure_and_resumes_without_repeating(jobs, settings):
    shop = batch_shop()
    shop.fail_on = lambda path, payload: path.endswith("products/102")
    removals, identifier, view = dry(jobs, settings, shop, "all", ("001", "002", "003", "004", "999"))
    assert view["counts"] == {"review": 4, "not_found": 1}
    view = execute(removals, identifier, jobs, settings, shop)
    assert {i["sku"]: i["state"] for i in view["items"]} == {"001": "done", "002": "error", "003": "done", "004": "done", "999": "not_found"}
    assert (view["done"], view["skipped"], view["failed"], view["progress"]) == (3, 1, 1, 100)
    writes = len(shop.writes)
    shop.fail_on = None
    assert removals.reprocess(identifier, "org", "owner") == 2  # failed + not found, never the done ones
    drain(jobs, settings, shop)
    view = execute(removals, identifier, jobs, settings, shop, ["002"])
    assert view["items"][1]["state"] == "done" and len(shop.writes) == writes + 1  # only the retried product is written again
    assert all(shop.products[s]["featured"] == 0 for s in ("001", "002", "003", "004"))


def test_pause_and_cancel_between_products(jobs, settings):
    shop = batch_shop()
    removals, identifier, _ = dry(jobs, settings, shop, "documents", ("001", "002", "003"))
    removals.approve(identifier, "org", "owner"); removals.confirm(identifier, "org", "owner", settings)
    assert removal.process_one(jobs, settings, httpx.MockTransport(shop.handle))  # first product only
    assert removals.pause(identifier, "org", "owner") == 2
    view = removals.detail(identifier, "org", "owner")
    assert [i["state"] for i in view["items"]] == ["done", "review", "review"] and all(i["approval"] for i in view["items"])
    removals.confirm(identifier, "org", "owner", settings, ["002"])
    assert removals.cancel(identifier, "org", "owner") == 1
    drain(jobs, settings, shop)
    assert [i["state"] for i in removals.detail(identifier, "org", "owner")["items"]] == ["done", "cancelled", "review"]
    assert docs(shop, "002") == DOCS


def test_worker_interruption_marks_uncertain_and_reconciles_by_read_back(jobs, settings):
    shop = Shop()
    removals, identifier, _ = dry(jobs, settings, shop, "gallery")
    removals.approve(identifier, "org", "owner"); removals.confirm(identifier, "org", "owner", settings)
    original = shop.handle
    def lose(request):
        response = original(request)
        if request.method == "PUT": raise httpx.ReadTimeout("perdida", request=request)
        return response
    shop.handle = lose
    drain(jobs, settings, shop)
    assert removals.detail(identifier, "org", "owner")["items"][0]["state"] == "done"  # lost response, verified by read-back


def test_report_csv_and_two_workers_claim_once(jobs, settings):
    shop = batch_shop()
    removals, identifier, _ = dry(jobs, settings, shop, "main", ("001", "002"))
    report = removals.report(identifier, "org", "owner").decode("utf-8-sig")
    assert report.splitlines()[0].startswith("sku,modo,estado") and "001,Remover foto principal,review,101,11" in report
    removals.approve(identifier, "org", "owner"); removals.confirm(identifier, "org", "owner", settings)
    barrier, claims = threading.Barrier(4), []
    def worker():
        barrier.wait(); claims.append(removals.claim())
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len([c for c in claims if c]) == 1


def test_unconfirmed_previous_send_is_never_retried_blindly(jobs, settings):
    shop = Shop()
    removals, identifier, view = dry(jobs, settings, shop, "documents")
    item_plan = {"product_id": 101, "dry_run": view["items"][0]["dry_run"]}
    from app.services.store_registration_jobs import Journal
    Journal(jobs, "org|" + ORIGIN + "|000123").put(removal.journal_key(item_plan), {"state": "sending", "after_wcda": [], "protected": "x"})
    item = execute(removals, identifier, jobs, settings, shop)["items"][0]
    assert item["state"] == "error" and "incerta" in item["error"] and not shop.writes


def test_api_flow_and_page(jobs, settings, monkeypatch):
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.dependencies import get_current_auth
    from app.routers import store_file_removal as router, store_integrations
    from app.services.security import hash_secret
    app = FastAPI(); app.include_router(router.router)
    auth = SimpleNamespace(user=SimpleNamespace(role="gestor", id="owner", organization_id="org"), login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_current_auth] = lambda: auth
    monkeypatch.setattr(store_integrations, "StoreSettings", lambda: settings)
    monkeypatch.setattr(router, "Jobs", lambda: jobs)
    shop = Shop()
    with TestClient(app) as client:
        form = {"empresa": "choice", "modo": "gallery", "skus": "000123\n000123"}
        assert client.post("/api/v1/remocao-arquivos", data=form).status_code == 403
        created = client.post("/api/v1/remocao-arquivos", data=form, files={"planilha": ("l.csv", b"SKU\n999999")}, headers={"X-CSRF-Token": "csrf"})
        assert created.status_code == 200 and created.json()["duplicates_removed"] == 1 and created.json()["total"] == 2
        identifier = created.json()["id"]
        drain(jobs, settings, shop)
        url = f"/api/v1/remocao-arquivos/{identifier}"
        assert client.post(url + "/executar", json={"skus": None}, headers={"X-CSRF-Token": "csrf"}).status_code == 422  # not approved
        assert client.post(url + "/aprovar", json={"skus": ["000123"]}, headers={"X-CSRF-Token": "csrf"}).status_code == 200
        state = lambda body: next(i["state"] for i in body["items"] if i["sku"] == "000123")
        assert state(client.post(url + "/executar", json={"skus": ["000123"]}, headers={"X-CSRF-Token": "csrf"}).json()) == "queued"
        drain(jobs, settings, shop)
        assert state(client.get(url).json()) == "done" and shop.products["000123"]["gallery"] == []
        assert "Remover fotos da galeria" in client.get(url + "/relatorio").content.decode("utf-8-sig")
        assert "ck_test" not in client.get(url + "/dry-run").text
        auth.user.role = "vendedor"
        assert client.get("/api/v1/remocao-arquivos").status_code == 403
    sys.path.insert(0, str(Path(__file__).parent))
    from test_operations_workspace import Elements, render
    html = render("Remoção de Arquivos")
    nodes = Elements(html).nodes
    ids = [a["id"] for _, a in nodes if "id" in a]
    assert len(ids) == len(set(ids)) and {"rm-form", "rm-skus", "rm-sheet", "rm-progress", "rm-items", "rm-report"} <= set(ids)
    assert [a.get("value") for t, a in nodes if t == "input" and a.get("name") == "modo"] == ["all", "gallery", "documents", "main"]
    assert "/js/store-file-removal.js" in html and "/js/store-file-removal.js" not in render("Cadastro via API")
