"""Digitalização e Publicação em Lote: import → datasheets → internal package → Dry Run → approval → publish.

Mocks only: AI, WooCommerce and WordPress are simulated; no network and no real store writes.
"""
import hashlib
import io
import itertools
import json
import re
import zipfile
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import pymupdf
import pytest
from PIL import Image

from app.config import Settings
from app.services import store_publish_grant as grants
from app.services.batch_publication import Pipelines
from app.services.datasheet_batches import BatchStore
from app.services.store_config import StoreSettings
from app.services.store_publish import PRODUCTION_HOSTS, PublishSettings
from app.services.store_registration_jobs import Jobs, process_one, rollback_one

ORIGIN = "https://staging.example.test"
SKUS = ["000123", "000124", "ABC-9"]
COMMERCIAL = {"name": "Nome do CSV", "description": "<p>Descrição do CSV</p>", "short_description": "<p>Curta</p>",
              "categories": [{"id": 5}], "attributes": [{"id": 0, "name": "Cor", "options": ["Preto"]}],
              "regular_price": "10.00", "sale_price": "", "stock_quantity": 3, "stock_status": "instock", "status": "publish"}


def pdf(text):
    with pymupdf.open() as doc:
        doc.new_page().insert_text((40, 40), text)
        return doc.tobytes()


SUPPLIER = {sku: pdf("Supplier datasheet " + sku) for sku in SKUS}


def image(color, fmt="PNG"):
    stream = io.BytesIO(); Image.new("RGBA" if fmt == "PNG" else "RGB", (40, 30), color).save(stream, fmt); return stream.getvalue()


def inner_zip(tag="modelo"):
    stream = io.BytesIO()
    # A filename string makes writestr embed the wall clock (ZIP's two-second precision).
    # This fixture represents the SAME file, not new archives with different timestamps.
    entry = zipfile.ZipInfo("modelo.step", date_time=(2020, 1, 1, 0, 0, 0))
    with zipfile.ZipFile(stream, "w") as archive: archive.writestr(entry, "ISO-10303 " + tag)
    return stream.getvalue()


def shade(sku, offset=0):
    digest = hashlib.sha256((sku + str(offset)).encode()).digest()
    return (digest[0], digest[1], digest[2])


def lot(skus=SKUS, shared=False):
    """One folder per SKU: supplier datasheet, photos, 3D drawing and a manual (distinct content per SKU)."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for sku in skus:
            archive.writestr(f"{sku}/datasheet.pdf", SUPPLIER.get(sku) or pdf("Supplier " + sku))
            archive.writestr(f"{sku}/Fotos/{sku}_variante.png", image("red" if shared else shade(sku)))
            archive.writestr(f"{sku}/Fotos/{sku}_foto2.jpg", image("blue" if shared else shade(sku, 1), "JPEG"))
            archive.writestr(f"{sku}/{sku}_Desenho 3D.zip", inner_zip("comum" if shared else sku))
            archive.writestr(f"{sku}/{sku}_Manual.pdf", pdf("Manual " + sku))
    return stream.getvalue()


class Shop:
    """Stateful multi-product WooCommerce + WordPress double. Any write only reaches this object."""
    def __init__(self, skus=SKUS):
        self.products = {sku: {"id": 100 + n, "sku": sku, **deepcopy(COMMERCIAL), "images": [],
                               "meta_data": [{"id": 1, "key": "_yoast_wpseo_focuskw", "value": "x"},
                                             {"id": 500 + n, "key": "_wcda_arquivos", "value": []}]} for n, sku in enumerate(skus)}
        self.library, self.titles, self.next_id = {}, {}, 1000
        self.methods, self.puts, self.posts, self.fail_upload = [], [], 0, set()

    def by_id(self, identifier):
        return next(p for p in self.products.values() if p["id"] == identifier)

    def handle(self, request):
        path, method = request.url.path, request.method
        self.methods.append(method)
        if method == "OPTIONS":
            return httpx.Response(200, headers={"Allow": "GET, POST" if "/media" in path else "GET, POST, PUT, PATCH"})
        if path.endswith("/users/me"):
            return httpx.Response(200, json={"id": 7, "capabilities": {c: True for c in ("upload_files", "edit_products", "edit_published_products", "edit_others_products")}})
        if "/wp/v2/media" in path:
            if method == "GET":
                term = request.url.params["search"]
                return httpx.Response(200, json=[{"id": i, "source_url": u} for i, u in self.library.items() if term in self.titles[i]])
            self.posts += 1
            name = re.search(rb'filename="([^"]+)"', request.content)[1].decode()
            if any(s in name for s in self.fail_upload): return httpx.Response(500, json={})
            self.next_id += 1
            self.library[self.next_id] = ORIGIN + "/wp-content/uploads/" + name
            self.titles[self.next_id] = name.rsplit(".", 1)[0]
            return httpx.Response(201, json={"id": self.next_id, "source_url": self.library[self.next_id]})
        if path.endswith("/products"):
            sku = request.url.params["sku"]
            return httpx.Response(200, json=[deepcopy(self.products[sku])] if sku in self.products else [])
        identifier = int(path.rsplit("/", 1)[1])
        if method == "GET":
            return httpx.Response(200, json=deepcopy(self.by_id(identifier)))
        payload = json.loads(request.content)
        assert set(payload) <= {"images", "meta_data"}
        self.puts.append(payload)
        product = self.by_id(identifier)
        if "images" in payload:
            product["images"] = [{"id": i["id"], "src": self.library[i["id"]]} for i in payload["images"]]
        for meta in payload.get("meta_data", []):
            assert meta["key"] == "_wcda_arquivos"
            next(m for m in product["meta_data"] if m["id"] == meta["id"])["value"] = meta["value"]
        return httpx.Response(200, json=deepcopy(product))


class OpenStaging(PublishSettings):
    """Test policy: any SKU on the staging origin; production hosts still refused."""
    def authorize(self, origin, sku):
        if not self.enabled or urlsplit(origin).hostname in PRODUCTION_HOSTS or origin != ORIGIN:
            raise ValueError("Gravação bloqueada nesta política de teste.")


@pytest.fixture
def app_settings(tmp_path):
    return Settings(_env_file=None, batch_storage_dir=str(tmp_path / "batches"))


@pytest.fixture
def store_settings():
    return StoreSettings(_env_file=None, CHOICE_WC_URL=ORIGIN, CHOICE_WC_KEY="ck_test", CHOICE_WC_SECRET="cs_test",
                         CHOICE_WP_USER="user", CHOICE_WP_APP_PASSWORD="app_password", PRM_STORE_ORGANIZATION_ID="org")


def make(tmp_path, app_settings, store_settings, policy=None):
    jobs = Jobs(policy or OpenStaging(_env_file=None, enabled=True, storage_dir=str(tmp_path / "queue")))
    return Pipelines(app_settings, store_settings, jobs=jobs, batches=BatchStore(app_settings))


def generate(pipes):
    """Worker double: same output contract as datasheet_batches.produce (datasheet.pdf + analysis.json)."""
    store = pipes.batches
    while (job := store.claim()):
        target = store.folder(job["batch"]) / job["token"]
        target.mkdir()
        (target / "datasheet.pdf").write_bytes(pdf("Datasheet PRM " + json.loads(job["data"])["codigo"]))
        (target / "analysis.json").write_text('{"especificacoes": []}', encoding="utf-8")
        store.finish(job, {"state": "done", "output": f"{job['token']}/datasheet.pdf"})


def drain(pipes, shop):
    while process_one(pipes.jobs, pipes.store_settings, httpx.MockTransport(shop.handle)): pass


def ready(tmp_path, app_settings, store_settings, shop=None, skus=SKUS, policy=None):
    pipes = make(tmp_path, app_settings, store_settings, policy)
    identifier = pipes.create(lot(skus), "choice", "org", "owner")
    pipes.process(identifier, "org", "owner", "model")
    generate(pipes)
    pipes.handoff(identifier, "org", "owner")
    drain(pipes, shop or Shop(skus))
    return pipes, identifier


def rows(pipes, identifier):
    return {r["sku"]: r for r in pipes.overview(identifier, "org", "owner")["items"]}


def commercial(product):
    return {k: product[k] for k in COMMERCIAL} | {"sku": product["sku"], "meta": [m for m in product["meta_data"] if m["key"] != "_wcda_arquivos"]}


# --- Importação e processamento ----------------------------------------------------------

def test_import_multiple_skus_by_folder_preserving_leading_zeros(tmp_path, app_settings, store_settings):
    pipes = make(tmp_path, app_settings, store_settings)
    identifier = pipes.create(lot(), "choice", "org", "owner")
    view = pipes.overview(identifier, "org", "owner")
    assert [r["sku"] for r in view["items"]] == ["000123", "000124", "ABC-9"]
    first = view["items"][0]
    assert first["folder"] == "000123" and first["images"] == 2 and first["documents"] == 2  # supplier PDF not counted
    assert first["processing"] == "pending" and first["store"] is None and first["stage"] == 1
    assert view["stages"]["1"] == 3


def test_individual_processing_pause_and_resume(tmp_path, app_settings, store_settings):
    pipes = make(tmp_path, app_settings, store_settings)
    identifier = pipes.create(lot(), "choice", "org", "owner")
    pipes.process(identifier, "org", "owner", "model", items=[2])
    assert [r["processing"] for r in rows(pipes, identifier).values()] == ["pending", "queued", "pending"]
    pipes.process(identifier, "org", "owner", "model", items=[1, 3])
    assert pipes.pause(identifier, "org", "owner") == 3
    assert {r["processing"] for r in rows(pipes, identifier).values()} == {"pending"}
    pipes.process(identifier, "org", "owner", "model")
    generate(pipes)
    assert {r["datasheet"] for r in rows(pipes, identifier).values()} == {"Gerado"}
    with pytest.raises(ValueError): pipes.process(identifier, "org", "owner", "model", items=[1])  # done items are never re-queued


def test_real_datasheet_generator_with_mocked_ai_uses_supplier_pdf(tmp_path, app_settings, store_settings, monkeypatch):
    import anthropic
    from app.services import datasheet_batches as batches
    pipes = make(tmp_path, app_settings, store_settings)
    identifier = pipes.create(lot(["000123"]), "choice", "org", "owner")
    pipes.process(identifier, "org", "owner", "model")
    data = {"modelo": "000123", "nivel": "completo", "categoria": "Produto", "subtitulo": "Industrial",
            "tags": ["Industrial", "USB", "Produto", "Documentação"], "features": [], "descricao": ["Produto industrial."],
            "imagens": [], "especificacoes": [{"chave": "USB", "valor": "2"}], "pendencias": [], "revisao_ok": True}
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="tool_use", name="entregar_datasheet", input=data, id="t")])
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)))
    job = pipes.batches.claim()
    batches.produce(pipes.batches, job)
    pipes.batches.finish(job, json.loads((pipes.batches.folder(job["batch"]) / job["token"] / "result.json").read_text(encoding="utf-8")))
    import base64
    # The supplier datasheet is the generator's source (sent to the mocked AI), never packaged.
    assert base64.b64encode(SUPPLIER["000123"]).decode()[:120] in repr(calls[0])
    assert rows(pipes, identifier)["000123"]["datasheet"] in {"Gerado", "Gerado com pendências"}
    raw, _, _ = pipes.archive(identifier, "org", "owner")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.read("000123/000123_Datasheet.pdf").startswith(b"%PDF-")


# --- Organização e exclusão do original ---------------------------------------------------

def test_package_organization_without_supplier_datasheet(tmp_path, app_settings, store_settings):
    pipes = make(tmp_path, app_settings, store_settings)
    identifier = pipes.create(lot(), "choice", "org", "owner")
    pipes.process(identifier, "org", "owner", "model"); generate(pipes)
    raw, packaged, _ = pipes.archive(identifier, "org", "owner")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("000123/manifest.json"))
        assert {"000123/Fotos/000123_variante.jpg", "000123/Fotos/000123_foto2.jpg", "000123/000123_Datasheet.pdf",
                "000123/000123_Desenho_3D.zip", "000123/000123_Manual.pdf", "000123/datasheet_dados.json"} <= names
        assert Image.open(io.BytesIO(archive.read("000123/Fotos/000123_variante.jpg"))).format == "JPEG"
        assert all(SUPPLIER["000123"] != archive.read(n) for n in names if n.endswith(".pdf"))
        assert {f["role"] for f in manifest["files"]} == {"main_image", "gallery", "generated_datasheet", "drawing_3d", "manual", "technical_analysis"}
        assert all(hashlib.sha256(archive.read("000123/" + f["path"])).hexdigest() == f["sha256"] for f in manifest["files"])
        assert manifest["ordered_images"] == ["Fotos/000123_variante.jpg", "Fotos/000123_foto2.jpg"]
    assert [s for s, _ in packaged] == SKUS
    # Supplier datasheet remains preserved in the processing sources.
    item = pipes.batches.detail(pipes.record(identifier, "org", "owner")["datasheet_batch"], "org", "owner")["items"][0]
    source = next(a for a in item["assets"] if a["role"] == "source_datasheet")
    assert (pipes.batches.folder(pipes.record(identifier, "org", "owner")["datasheet_batch"]) / source["stored"]).read_bytes() == SUPPLIER["000123"]


# --- Integração, Dry Run e produtos inexistentes -------------------------------------------

def test_internal_handoff_dry_run_in_batch_and_awaiting_csv(tmp_path, app_settings, store_settings):
    shop = Shop(["000123", "ABC-9"])  # 000124 not registered yet
    pipes, identifier = ready(tmp_path, app_settings, store_settings, shop)
    view = rows(pipes, identifier)
    assert view["000123"]["store"] == "review" and view["ABC-9"]["store"] == "review"
    assert view["000124"]["store"] == "awaiting_product" and view["000124"]["store_label"] == "Aguardando cadastro por CSV"
    assert view["000123"]["uploads"] == 2 and view["000123"]["documents_add"] == 3  # PRM datasheet, manual, 3D
    assert view["000123"]["ignored"] == []
    assert set(shop.methods) <= {"GET"}
    with pytest.raises(ValueError, match="Nenhum produto novo"): pipes.handoff(identifier, "org", "owner")  # no duplicate hand-off
    # The CSV flow registers 000124; publication resumes without re-importing or re-generating.
    shop.products["000124"] = {**deepcopy(shop.products["000123"]), "id": 777, "sku": "000124",
                               "meta_data": [{"id": 1, "key": "_yoast_wpseo_focuskw", "value": "x"}, {"id": 778, "key": "_wcda_arquivos", "value": []}]}
    pipes.resume(identifier, "org", "owner"); drain(pipes, shop)
    assert rows(pipes, identifier)["000124"]["store"] == "review"


# --- Aprovação, publicação, bloqueios e campos protegidos ----------------------------------

def test_individual_and_multiple_approval_then_publish_only_files(tmp_path, app_settings, store_settings):
    shop = Shop()
    pipes, identifier = ready(tmp_path, app_settings, store_settings, shop)
    before = {s: commercial(p) for s, p in shop.products.items()}
    result = pipes.approve(identifier, "org", "owner", ["000124"])
    assert result[0]["ok"] and rows(pipes, identifier)["000124"]["approved"]
    pipes.approve(identifier, "org", "owner")  # the remaining ones in batch
    assert all(r["approved"] for r in rows(pipes, identifier).values())
    assert pipes.publish(identifier, "org", "owner")[0]["ok"]
    drain(pipes, shop)
    view = rows(pipes, identifier)
    assert {r["store"] for r in view.values()} == {"done"} and all(r["stage"] == 6 for r in view.values())
    for sku, product in shop.products.items():
        assert commercial(product) == before[sku]
        assert len(product["images"]) == 2
        assert [d["label"] for d in next(m for m in product["meta_data"] if m["key"] == "_wcda_arquivos")["value"]] == ["Datasheet", "Manual", "Desenho 3D"]
    assert not any("Supplier" in json.dumps(p) for p in shop.products.values())
    assert all(set(p) <= {"images", "meta_data"} for p in shop.puts)


def test_publication_blocked_without_policy_or_grant(tmp_path, app_settings, store_settings):
    shop = Shop()
    policy = PublishSettings(_env_file=None, storage_dir=str(tmp_path / "queue"))  # real default: writes disabled
    pipes, identifier = ready(tmp_path, app_settings, store_settings, shop, policy=policy)
    pipes.approve(identifier, "org", "owner")
    result = pipes.publish(identifier, "org", "owner")
    assert not result[0]["ok"] and "Sem liberação" in result[0]["error"]
    assert shop.posts == 0 and not shop.puts and {r["store"] for r in rows(pipes, identifier).values()} == {"review"}


def test_publish_requires_approval_of_the_dry_run(tmp_path, app_settings, store_settings):
    pipes, identifier = ready(tmp_path, app_settings, store_settings)
    result = pipes.publish(identifier, "org", "owner")
    assert not result[0]["ok"] and "aprovado" in result[0]["error"]


# --- Falhas parciais, retomada, duplicidades, auditoria e recuperação -----------------------

def test_partial_failure_isolated_and_resumed_without_duplicate_uploads(tmp_path, app_settings, store_settings):
    shop = Shop()
    shop.fail_upload = {"ABC-9_Manual"}
    pipes, identifier = ready(tmp_path, app_settings, store_settings, shop)
    pipes.approve(identifier, "org", "owner"); pipes.publish(identifier, "org", "owner"); drain(pipes, shop)
    view = rows(pipes, identifier)
    assert view["000123"]["store"] == "done" and view["000124"]["store"] == "done" and view["ABC-9"]["store"] == "error"
    posts = shop.posts
    shop.fail_upload = set()
    pipes.resume(identifier, "org", "owner"); drain(pipes, shop)
    pipes.approve(identifier, "org", "owner", ["ABC-9"]); pipes.publish(identifier, "org", "owner", ["ABC-9"]); drain(pipes, shop)
    assert rows(pipes, identifier)["ABC-9"]["store"] == "done"
    assert shop.posts == posts + 2  # the refused manual and the 3D not reached; earlier ABC-9 uploads are reused
    assert len(shop.library) == 15  # 5 media per SKU, no duplicates


def test_interrupted_processing_resumes_without_reprocessing_done_items(tmp_path, app_settings, store_settings):
    pipes = make(tmp_path, app_settings, store_settings)
    identifier = pipes.create(lot(), "choice", "org", "owner")
    pipes.process(identifier, "org", "owner", "model")
    job = pipes.batches.claim()  # worker dies while running this item
    with pipes.batches.db(True) as db: db.execute("UPDATE items SET lease=0 WHERE batch=? AND id=?", (job["batch"], job["id"]))
    generate(pipes)  # expired lease becomes an error; other items finish
    view = rows(pipes, identifier)
    assert view["000123"]["processing"] == "error" and view["000124"]["datasheet"] == "Gerado"
    pipes.process(identifier, "org", "owner", "model", retry=True); generate(pipes)
    assert {r["datasheet"] for r in rows(pipes, identifier).values()} == {"Gerado"}


def test_identical_images_are_uploaded_once(tmp_path, app_settings, store_settings):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("000123/datasheet.pdf", SUPPLIER["000123"])
        archive.writestr("000123/Fotos/000123_variante.png", image("red"))
        archive.writestr("000123/Fotos/000123_foto2.png", image("red"))  # same pixels → same processed bytes
    pipes = make(tmp_path, app_settings, store_settings)
    identifier = pipes.create(stream.getvalue(), "choice", "org", "owner")
    pipes.process(identifier, "org", "owner", "model"); generate(pipes)
    pipes.handoff(identifier, "org", "owner")
    shop = Shop(["000123"]); drain(pipes, shop)
    pipes.approve(identifier, "org", "owner"); pipes.publish(identifier, "org", "owner"); drain(pipes, shop)
    assert len(shop.products["000123"]["images"]) == 1 and shop.posts == 2  # 1 image + PRM datasheet


def test_audit_trail_and_rollback_after_publication(tmp_path, app_settings, store_settings):
    shop = Shop(["000123"])
    pipes, identifier = ready(tmp_path, app_settings, store_settings, shop, skus=["000123"])
    pipes.approve(identifier, "org", "owner"); pipes.publish(identifier, "org", "owner"); drain(pipes, shop)
    row = rows(pipes, identifier)["000123"]
    events = [a["event"] for a in pipes.jobs.detail(row["store_batch"], "org", "owner")["items"][0]["audit"]]
    for event in ("handoff", "preview_review", "approved", "queued", "permissions_verified", "upload_done", "put_sent", "verified", "done"):
        assert event in events
    before = commercial(shop.products["000123"])
    result = rollback_one(pipes.jobs, store_settings, row["store_batch"], "000123", actor="tester", transport=httpx.MockTransport(shop.handle))
    assert result["status"] == "rolled_back" and shop.products["000123"]["images"] == []
    assert commercial(shop.products["000123"]) == before and len(shop.library) == 5  # media kept


def test_shared_3d_fixture_is_independent_of_clock(monkeypatch):
    monkeypatch.setattr(zipfile.time, "localtime", lambda *args: (2026, 10, 22, 12, 0, 0, 3, 295, -1))
    first = inner_zip("comum")
    monkeypatch.setattr(zipfile.time, "localtime", lambda *args: (2026, 10, 22, 12, 0, 2, 3, 295, -1))
    second = inner_zip("comum")
    assert first == second
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    assert first != inner_zip("outro modelo")  # Different source bytes must remain different.
    with zipfile.ZipFile(io.BytesIO(second)) as archive:
        assert archive.read("modelo.step") == b"ISO-10303 comum"


@pytest.mark.parametrize("zip_clock_step", [0, 2], ids=["same-timestamp", "cross-timestamp-boundaries"])
def test_same_file_in_several_products_is_uploaded_once(tmp_path, app_settings, store_settings, monkeypatch, zip_clock_step):
    # Exercise both fast runs and runs spanning ZIP timestamp boundaries without sleeping.
    localtime = zipfile.time.localtime
    ticks = itertools.count(1700000000, zip_clock_step)
    monkeypatch.setattr(zipfile.time, "localtime", lambda *args: localtime(next(ticks)))
    shop = Shop()
    pipes = make(tmp_path, app_settings, store_settings)
    shared_lot = lot(shared=True)
    with zipfile.ZipFile(io.BytesIO(shared_lot)) as archive:
        sources = [archive.read(f"{sku}/{sku}_Desenho 3D.zip") for sku in SKUS]
    assert len({hashlib.sha256(blob).digest() for blob in sources}) == 1
    identifier = pipes.create(shared_lot, "choice", "org", "owner")
    pipes.process(identifier, "org", "owner", "model"); generate(pipes)
    pipes.handoff(identifier, "org", "owner"); drain(pipes, shop)
    pipes.approve(identifier, "org", "owner"); pipes.publish(identifier, "org", "owner"); drain(pipes, shop)
    # 2 shared photos + 1 shared 3D uploaded once; datasheet and manual differ per SKU.
    assert shop.posts == 3 + 2 * 3 and len(shop.library) == 9
    assert len({p["images"][0]["id"] for p in shop.products.values()}) == 1
    assert len([url for url in shop.library.values() if url.endswith(".zip")]) == 1


# --- Liberação para múltiplos SKUs --------------------------------------------------------

def test_scope_grant_stays_inside_the_homologation_allowlist(tmp_path, app_settings):
    settings = StoreSettings(_env_file=None, CHOICE_WC_URL="https://choicetech.com.br", CHOICE_WC_KEY="ck", CHOICE_WC_SECRET="cs",
                             CHOICE_WP_USER="u", CHOICE_WP_APP_PASSWORD="p", PRM_STORE_ORGANIZATION_ID="org")
    policy = PublishSettings(_env_file=None, storage_dir=str(tmp_path / "queue"))
    shop = Shop(["119002000072", "000123"]); shop.products["119002000072"]["id"] = 16321
    pipes, identifier = ready(tmp_path, app_settings, settings, shop, skus=["119002000072", "000123"], policy=policy)
    pipes.approve(identifier, "org", "owner")
    store_batch = rows(pipes, identifier)["000123"]["store_batch"]
    with pytest.raises(ValueError, match="Fora dos alvos permitidos: 000123|Fora dos alvos permitidos de homologação: 000123"):
        grants.issue_scope(pipes.jobs, batch=store_batch, skus=["119002000072", "000123"], minutes=30, actor="t", max_items=5)
    assert grants.listing(pipes.jobs) == []  # all-or-nothing
    with pytest.raises(ValueError, match="Limite"):
        grants.issue_scope(pipes.jobs, batch=store_batch, skus=["119002000072"], minutes=30, actor="t", max_items=51)
    issued = grants.issue_scope(pipes.jobs, batch=store_batch, skus=["119002000072"], minutes=30, actor="t", max_items=1)
    assert len(issued["grants"]) == 1 and issued["grants"][0]["scope"] == issued["scope"]
    result = pipes.publish(identifier, "org", "owner")
    assert not result[0]["ok"]  # 000123 has no grant: the whole confirmation is refused, nothing queued
    assert pipes.publish(identifier, "org", "owner", ["119002000072"])[0]["ok"]
    drain(pipes, shop)
    view = rows(pipes, identifier)
    assert view["119002000072"]["store"] == "done" and view["000123"]["store"] == "review"
    assert [g["state"] for g in grants.listing(pipes.jobs)] == ["consumed"]


# --- API e interface -----------------------------------------------------------------------

def test_api_flow_permissions_and_export(tmp_path, app_settings, store_settings, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.dependencies import get_current_auth
    from app.routers import batch_publication, store_integrations
    from app.services.security import hash_secret
    jobs = Jobs(OpenStaging(_env_file=None, enabled=True, storage_dir=str(tmp_path / "queue")))
    app = FastAPI(); app.include_router(batch_publication.router)
    auth = SimpleNamespace(user=SimpleNamespace(role="gestor", id="owner", organization_id="org"),
                           login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_current_auth] = lambda: auth
    app.dependency_overrides[get_settings] = lambda: app_settings
    monkeypatch.setattr(store_integrations, "StoreSettings", lambda: store_settings)
    monkeypatch.setattr(batch_publication, "Pipelines", lambda a, s: Pipelines(a, s, jobs=jobs))
    monkeypatch.setenv("DATASHEET_MODEL", "model")
    with TestClient(app) as client:
        files = {"arquivo": ("lote.zip", lot(["000123"]))}
        assert client.post("/api/v1/publicacao-lote", data={"empresa": "choice"}, files=files).status_code == 403
        response = client.post("/api/v1/publicacao-lote", data={"empresa": "choice"}, files=files, headers={"X-CSRF-Token": "csrf"})
        assert response.status_code == 200, response.text
        identifier = response.json()["id"]
        assert response.json()["items"][0]["sku"] == "000123"
        assert client.post(f"/api/v1/publicacao-lote/{identifier}/processar", json={"items": None}, headers={"X-CSRF-Token": "csrf"}).status_code == 200
        generate(Pipelines(app_settings, store_settings, jobs=jobs))
        export = client.get(f"/api/v1/publicacao-lote/{identifier}/exportar")
        with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
            assert "000123/000123_Datasheet.pdf" in archive.namelist()
            assert all(archive.read(n) != SUPPLIER["000123"] for n in archive.namelist())
        prepared = client.post(f"/api/v1/publicacao-lote/{identifier}/preparar", json={"skus": ["000123"]}, headers={"X-CSRF-Token": "csrf"})
        assert prepared.status_code == 200 and prepared.json()["items"][0]["store"] == "preview_queued"
        auth.user.id = "other"
        assert client.get(f"/api/v1/publicacao-lote/{identifier}").status_code == 404
        auth.user.role = "vendedor"
        assert client.get("/api/v1/publicacao-lote").status_code == 403


def test_page_is_registered_for_managers_only():
    from app.routers import pages
    import inspect
    source = inspect.getsource(pages)
    import re
    restricted = re.search(r'if title in \{([^}]*)\} and auth\.user\.role not in', source)[1]
    assert '"digitalizacao/publicacao-lote"' in source and '"Publicação em Lote"' in restricted
