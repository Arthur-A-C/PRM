"""Cadastro via API com escopo explícito: galeria, documentos e/ou principal escolhida por SKU. Mocks only.

No test reaches a real store: every request goes to the Store/Shop doubles through httpx.MockTransport.
"""
import hashlib
import json

import httpx
import pytest
from registration_identity_fixture import mocked_registration_identity  # noqa: F401
from test_batch_publication import Shop, lot
from test_store_registration_zip import EXISTING, SKU, Store, commercial, drain, jobs, package, settings  # noqa: F401

from app.services import store_registration_authorization as authorization
from app.services.store_registration_plan import normalize_scope, scoped_order

pytestmark = pytest.mark.usefixtures("mocked_registration_identity")

ALL = {"gallery": True, "documents": True, "main": True}
GALLERY = {"gallery": True, "documents": False, "main": False}
DOCUMENTS = {"gallery": False, "documents": True, "main": False}
MAIN = {"gallery": False, "documents": False, "main": True}
VARIANTE, FOTO2 = f"{SKU}_variante.jpg", f"{SKU}_foto2.jpg"


def start(jobs, settings, store, scope, raw=None):
    identifier = jobs.create("choice", "org", "owner", None, raw or package(gallery=True), settings,
                             identification="folder", archive_name=SKU + ".zip", scope=scope)
    drain(jobs, settings, store)
    return identifier, item(jobs, identifier)


def item(jobs, identifier, sku=SKU):
    return next(i for i in jobs.detail(identifier, "org", "owner")["items"] if i["sku"] == sku)


def choose(jobs, settings, store, identifier, name, sku=SKU):
    option = next(o for o in item(jobs, identifier, sku)["dry_run"]["main_options"] if o["name"] == name)
    jobs.choose_main(identifier, "org", "owner", sku, option["sha256"])
    drain(jobs, settings, store)
    return item(jobs, identifier, sku)


def publish(jobs, settings, store, identifier, skus=None):
    jobs.approve(identifier, "org", "owner", skus)
    jobs.confirm(identifier, "org", "owner", settings, skus, confirmed=True)
    drain(jobs, settings, store)
    return item(jobs, identifier)


def wcda(store):
    return next((m["value"] for m in store.product["meta_data"] if m["key"] == "_wcda_arquivos"), None)


def image_ids(store):
    return [i["id"] for i in store.product["images"]]


def uploaded(store):
    return [u.rsplit("/", 1)[1] for i, u in store.library.items() if i > 10]


# --- Um escopo por vez ------------------------------------------------------------------------------

def test_gallery_only_adds_gallery_preserves_main_and_documents(jobs, settings):
    store = Store(images=[10], wcda=EXISTING)
    before = commercial(store.product)
    identifier, current = start(jobs, settings, store, GALLERY)
    dry = current["dry_run"]
    assert current["state"] == "review" and dry["registration_scope"] == {**GALLERY, "main_choice": None}
    assert [(a["name"], a["role"], a["action"]) for a in dry["images"]["actions"]] == [(FOTO2, "gallery", "upload")]
    assert dry["images"]["main_image"]["action"] == "preserve" and dry["documents"]["actions"] == []
    assert [i["name"] for i in dry["ignored"]] == [VARIANTE]  # folder-suggested main never goes to the gallery by itself
    assert {f["name"] for f in current["files"] if f["label"] == "fora do escopo"} >= {f"{SKU}_Datasheet.pdf", VARIANTE}
    done = publish(jobs, settings, store, identifier)
    assert done["state"] == "done" and [set(p) for p in store.puts] == [{"images"}]
    assert image_ids(store)[0] == 10 and len(image_ids(store)) == 2 and store.posts == 1
    assert wcda(store) == EXISTING and commercial(store.product) == before


def test_documents_only_never_touches_images(jobs, settings):
    store = Store(images=[10], wcda=EXISTING)
    identifier, current = start(jobs, settings, store, DOCUMENTS)
    assert current["state"] == "review" and current["dry_run"]["images"]["actions"] == []
    assert [d["label"] for d in current["dry_run"]["documents"]["actions"]] == ["Datasheet", "Desenho 3D"]
    publish(jobs, settings, store, identifier)
    assert [set(p) for p in store.puts] == [{"meta_data"}] and image_ids(store) == [10] and store.posts == 2
    assert wcda(store)[:2] == EXISTING and [d["label"] for d in wcda(store)[2:]] == ["Datasheet", "Desenho 3D"]


def test_main_only_requires_explicit_choice_and_keeps_previous_main_in_gallery(jobs, settings):
    store = Store(images=[10], wcda=EXISTING)
    identifier, current = start(jobs, settings, store, MAIN)
    dry = current["dry_run"]
    assert current["state"] == "awaiting_main" and dry["main_choice_required"]
    assert [(o["name"], o["suggested"]) for o in dry["main_options"]] == [(VARIANTE, True), (FOTO2, False)]
    with pytest.raises(ValueError):  # nothing to approve while the main is not chosen
        jobs.approve(identifier, "org", "owner", [SKU])
    current = choose(jobs, settings, store, identifier, FOTO2)
    main = current["dry_run"]["images"]["main_image"]
    assert current["state"] == "review" and main["action"] == "replace" and main["current"]["id"] == 10
    assert main["proposed"]["name"] == FOTO2 and "será substituída" in main["message"] and "preservada na galeria" in main["message"]
    assert [a["name"] for a in current["dry_run"]["images"]["actions"]] == [FOTO2]  # gallery out of scope
    done = publish(jobs, settings, store, identifier)
    assert done["approval"]["replace_main"] is True and [set(p) for p in store.puts] == [{"images"}]
    assert image_ids(store)[1:] == [10] and uploaded(store) == [f"prm-{current['dry_run']['images']['actions'][0]['sha256']}.jpg"]
    assert wcda(store) == EXISTING and "DELETE" not in store.methods


def test_gallery_and_documents(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, _ = start(jobs, settings, store, {"gallery": True, "documents": True, "main": False})
    publish(jobs, settings, store, identifier)
    assert [set(p) for p in store.puts] == [{"images", "meta_data"}]
    assert image_ids(store)[0] == 10 and len(image_ids(store)) == 2 and len(wcda(store)) == 2


def test_main_and_documents(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, _ = start(jobs, settings, store, {"gallery": False, "documents": True, "main": True})
    choose(jobs, settings, store, identifier, VARIANTE)
    publish(jobs, settings, store, identifier)
    assert image_ids(store)[1:] == [10] and len(wcda(store)) == 2
    assert not any(FOTO2 in u or "foto2" in u for u in uploaded(store)) and store.posts == 3


def test_everything_with_explicit_main(jobs, settings):
    store = Store(images=[10], wcda=[])
    before = commercial(store.product)
    identifier, current = start(jobs, settings, store, normalize_scope("all"))
    assert current["state"] == "awaiting_main"
    current = choose(jobs, settings, store, identifier, VARIANTE)
    assert [(a["name"], a["role"]) for a in current["dry_run"]["images"]["actions"]] == [(VARIANTE, "main_image"), (FOTO2, "gallery")]
    final = current["dry_run"]["images"]["final_order"]
    assert [f["name"] for f in final] == [VARIANTE, "foto-antiga.jpg", FOTO2]
    publish(jobs, settings, store, identifier)
    assert len(image_ids(store)) == 3 and image_ids(store)[1] == 10 and len(wcda(store)) == 2
    assert commercial(store.product) == before


def test_product_without_main_needs_main_in_scope_for_gallery(jobs, settings):
    store = Store(wcda=[])
    identifier, current = start(jobs, settings, store, GALLERY)
    assert current["state"] == "blocked" and "Marque Foto principal" in current["error"]
    current = choose_after_scope(jobs, settings, store, identifier, ALL, VARIANTE)
    assert current["state"] == "review" and current["dry_run"]["images"]["main_image"]["action"] == "set"
    publish(jobs, settings, store, identifier)
    assert len(image_ids(store)) == 2 and store.puts[0]["images"][0]["id"] == image_ids(store)[0]


def choose_after_scope(jobs, settings, store, identifier, scope, name):
    jobs.set_scope(identifier, "org", "owner", scope)
    drain(jobs, settings, store)
    return choose(jobs, settings, store, identifier, name)


def test_chosen_main_already_in_gallery_is_promoted_without_upload(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, _ = start(jobs, settings, store, GALLERY)
    publish(jobs, settings, store, identifier)
    gallery_id = image_ids(store)[1]
    posts = store.posts
    second, current = start(jobs, settings, store, MAIN)
    current = choose(jobs, settings, store, second, FOTO2)
    assert current["dry_run"]["images"]["main_image"]["source"] == "existing"
    publish(jobs, settings, store, second)
    assert image_ids(store) == [gallery_id, 10] and store.posts == posts


# --- Regras de preservação -----------------------------------------------------------------------

def test_existing_main_never_changes_without_main_scope(jobs, settings):
    for scope in (GALLERY, DOCUMENTS, {"gallery": True, "documents": True, "main": False}):
        store = Store(images=[10], wcda=[])
        identifier, current = start(jobs, settings, store, scope)
        assert current["dry_run"]["images"]["main_image"]["action"] == "preserve"
        publish(jobs, settings, store, identifier)
        assert image_ids(store)[0] == 10


def test_absent_wcda_is_created_only_when_documents_in_scope(jobs, settings):
    store = Store(images=[10], wcda_meta=False)
    identifier, current = start(jobs, settings, store, DOCUMENTS)
    assert current["dry_run"]["documents"]["mode"] == "absent"
    publish(jobs, settings, store, identifier)
    assert [d["label"] for d in wcda(store)] == ["Datasheet", "Desenho 3D"]
    other = Store(images=[10], wcda_meta=False)
    identifier, _ = start(jobs, settings, other, GALLERY)
    publish(jobs, settings, other, identifier)
    assert wcda(other) is None and all("meta_data" not in p for p in other.puts)


def test_nothing_new_for_the_scope_is_not_an_error(jobs, settings):
    store = Store(images=[10], wcda=[])
    raw = package(gallery=True)  # same bytes twice: the 3D ZIP carries a timestamp
    identifier, _ = start(jobs, settings, store, DOCUMENTS, raw)
    publish(jobs, settings, store, identifier)
    puts = len(store.puts)
    second, current = start(jobs, settings, store, DOCUMENTS, raw)
    assert current["state"] == "nothing", current["error"]
    assert current["error"] == "Nenhum documento novo encontrado para o escopo selecionado."
    with pytest.raises(ValueError):
        jobs.approve(second, "org", "owner", [SKU])
    assert len(store.puts) == puts


def test_main_scope_on_sku_without_images_changes_only_documents(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, current = start(jobs, settings, store, ALL, raw=_without_images(package()))
    assert current["state"] == "review" and current["dry_run"]["images"]["main_image"]["action"] == "unavailable"
    publish(jobs, settings, store, identifier)
    assert image_ids(store) == [10] and len(wcda(store)) == 2


def _without_images(raw):
    import io, zipfile
    source, target = zipfile.ZipFile(io.BytesIO(raw)), io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        for info in source.infolist():
            if "/Fotos/" in info.filename: continue
            data = source.read(info)
            if info.filename.endswith("manifest.json"):
                manifest = json.loads(data)
                manifest["ordered_images"] = []
                manifest["files"] = [f for f in manifest["files"] if not f["path"].startswith("Fotos/")]
                data = json.dumps(manifest).encode()
            archive.writestr(info, data)
    return target.getvalue()


# --- Assinatura, concorrência e worker ----------------------------------------------------------------

def plan_of(jobs):
    with jobs.db() as db:
        return json.loads(db.execute("SELECT plan FROM jobs").fetchone()[0])


def save(jobs, plan):
    with jobs.db() as db:
        db.execute("UPDATE jobs SET plan=?", (json.dumps(plan),))


def test_scope_change_after_approval_requires_new_dry_run(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, _ = start(jobs, settings, store, GALLERY)
    jobs.approve(identifier, "org", "owner", [SKU])
    jobs.set_scope(identifier, "org", "owner", DOCUMENTS)
    assert item(jobs, identifier)["approval"] is None
    drain(jobs, settings, store)
    assert item(jobs, identifier)["approval"] is None
    with pytest.raises(ValueError):
        jobs.confirm(identifier, "org", "owner", settings, [SKU], confirmed=True)
    # Scope edited behind the UI after approval: the signature no longer matches.
    jobs.approve(identifier, "org", "owner", [SKU])
    plan = plan_of(jobs); plan["input"]["scope"] = GALLERY; save(jobs, plan)
    with pytest.raises(ValueError, match="refaça o Dry Run"):
        jobs.confirm(identifier, "org", "owner", settings, [SKU], confirmed=True)
    assert store.posts == 0 and not store.puts


def test_main_choice_change_after_approval_requires_new_dry_run(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, _ = start(jobs, settings, store, MAIN)
    current = choose(jobs, settings, store, identifier, VARIANTE)
    jobs.approve(identifier, "org", "owner", [SKU])
    current = choose(jobs, settings, store, identifier, FOTO2)
    assert current["approval"] is None and current["dry_run"]["images"]["main_image"]["proposed"]["name"] == FOTO2
    jobs.approve(identifier, "org", "owner", [SKU])
    jobs.confirm(identifier, "org", "owner", settings, [SKU], confirmed=True)
    plan = plan_of(jobs)
    plan["input"]["main_choice"] = {"sha256": plan["dry_run"]["main_options"][0]["sha256"], "name": VARIANTE}
    save(jobs, plan)
    drain(jobs, settings, store)
    assert item(jobs, identifier)["state"] == "error" and store.posts == 0 and not store.puts


def test_main_choice_must_be_an_image_of_the_sku_and_main_in_scope(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, _ = start(jobs, settings, store, MAIN)
    with pytest.raises(ValueError, match="não pertence"):
        jobs.choose_main(identifier, "org", "owner", SKU, "0" * 64)
    other, _ = start(jobs, settings, store, GALLERY)
    sha = item(jobs, other)["dry_run"]["main_options"][0]["sha256"]
    with pytest.raises(ValueError, match="Marque Foto principal"):
        jobs.choose_main(other, "org", "owner", SKU, sha)
    for bad in ({}, {"gallery": False, "documents": False, "main": False}, {"gallery": "sim", "documents": True, "main": False}, "fotos"):
        with pytest.raises(ValueError):
            normalize_scope(bad)


def reseal(jobs, plan):
    """What a forged plan would need to pass the hash and binding checks: only the scope guard is left."""
    record = {"org": "org", "company": "choice", "origin": "https://staging.example.test"}
    authorization.seal(record, SKU, plan)
    plan["approval"]["dry_run_sha256"] = plan["dry_run"]["dry_run_sha256"]
    plan["execution"]["dry_run_sha256"] = plan["dry_run"]["dry_run_sha256"]
    plan["execution"]["approval"] = plan["approval"]
    save(jobs, plan)


@pytest.mark.parametrize("forgery", ["documents_outside_scope", "main_outside_scope"])
def test_worker_enforces_the_scope_even_on_a_resealed_plan(jobs, settings, forgery):
    store = Store(images=[10], wcda=[])
    identifier, _ = start(jobs, settings, store, GALLERY)
    jobs.approve(identifier, "org", "owner", [SKU])
    jobs.confirm(identifier, "org", "owner", settings, [SKU], confirmed=True)
    plan = plan_of(jobs)
    if forgery == "documents_outside_scope":
        # A real file of the SKU, unchanged on disk: only the scope guard can refuse it.
        path = jobs.root / identifier / SKU / f"{SKU}_Datasheet.pdf"
        plan["downloads"] = [{"name": path.name, "role": "generated_datasheet", "label": "Datasheet", "bytes": path.stat().st_size,
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "path": str(path)}]
    else:
        plan["images"][0]["role"] = "main_image"
        plan["dry_run"]["images"]["actions"][0]["role"] = "main_image"
        plan["dry_run"]["images"]["main_image"].update(action="replace", source="upload")
    reseal(jobs, plan)
    drain(jobs, settings, store)
    current = item(jobs, identifier)
    assert current["state"] == "error" and "escopo" in current["error"].lower()
    assert store.posts == 0 and not store.puts


def test_scoped_order_refuses_main_change_or_gallery_outside_scope():
    dry = {"images": {"main_image": {"action": "preserve"}}}
    gallery = [{"sha256": "a", "role": "gallery"}]
    assert scoped_order([10], dry, GALLERY, gallery, {"a": {"id": 20}}) == [10, 20]
    with pytest.raises(ValueError, match="Galeria fora"):
        scoped_order([10], dry, MAIN, gallery, {"a": {"id": 20}})
    with pytest.raises(ValueError, match="Principal fora"):
        scoped_order([10], dry, GALLERY, [{"sha256": "a", "role": "main_image"}], {"a": {"id": 20}})
    with pytest.raises(ValueError, match="só muda com Foto principal"):
        scoped_order([], dry, GALLERY, gallery, {"a": {"id": 20}})


# --- Lote com vários SKUs e seleção em massa ---------------------------------------------------------

def test_bulk_approval_and_send_with_batch_scope(jobs, settings):
    skus = ["000201", "000202", "000203"]
    shop = Shop(skus)
    identifier = jobs.create("choice", "org", "owner", None, numbered(lot(skus)), settings, identification="folder",
                             archive_name="lote.zip", scope=ALL)
    while _process(jobs, settings, shop): pass
    items = jobs.detail(identifier, "org", "owner")["items"]
    assert {i["state"] for i in items} == {"review"}  # <SKU>_1 detected: no manual choice per SKU
    assert jobs.approve(identifier, "org", "owner") == skus  # "Selecionar todos" + Aprovar
    jobs.confirm(identifier, "org", "owner", settings, confirmed=True)
    while _process(jobs, settings, shop): pass
    items = jobs.detail(identifier, "org", "owner")["items"]
    assert {i["state"] for i in items} == {"done"}
    for sku in skus:
        product = shop.products[sku]
        assert len(product["images"]) == 2 and next(m for m in product["meta_data"] if m["key"] == "_wcda_arquivos")["value"]
        names = [shop.library[i["id"]] for i in product["images"]]
        assert names[0].endswith(".png") and names[1].endswith(".jpg")  # _1.png main, _2.jpg gallery


def test_bulk_folders_outside_the_pattern_need_a_manual_main_per_sku(jobs, settings):
    skus = ["000201", "000202"]
    shop = Shop(skus)
    identifier = jobs.create("choice", "org", "owner", None, lot(skus), settings, identification="folder",
                             archive_name="lote.zip", scope=ALL)
    while _process(jobs, settings, shop): pass
    items = jobs.detail(identifier, "org", "owner")["items"]
    assert {i["state"] for i in items} == {"awaiting_main"}
    assert all("Foto principal não encontrada no padrão " + i["sku"] + "_1.ext." in i["error"] for i in items)
    for i in items:  # manual, explicit, per SKU
        option = next(o for o in i["dry_run"]["main_options"] if o["name"].endswith("_variante.png"))
        jobs.choose_main(identifier, "org", "owner", i["sku"], option["sha256"])
    while _process(jobs, settings, shop): pass
    assert {i["state"] for i in jobs.detail(identifier, "org", "owner")["items"]} == {"review"}


def numbered(raw):
    """Same lot, images renamed to the official <SKU>_<n>.ext pattern."""
    import io, zipfile
    source, target = zipfile.ZipFile(io.BytesIO(raw)), io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        for info in source.infolist():
            name = info.filename.replace("_variante.png", "_1.png").replace("_foto2.jpg", "_2.jpg")
            archive.writestr(name, source.read(info))
    return target.getvalue()


def _process(jobs, settings, shop):
    from app.services.store_registration_jobs import process_one
    return process_one(jobs, settings, httpx.MockTransport(shop.handle))


def test_older_batches_without_scope_keep_the_previous_plan(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier = jobs.create("choice", "org", "owner", None, package(gallery=True), settings, identification="folder", archive_name=SKU + ".zip")
    drain(jobs, settings, store)
    current = item(jobs, identifier)
    assert current["scope"] is None and "registration_scope" not in current["dry_run"]
    assert [a["role"] for a in current["dry_run"]["images"]["actions"]] == ["main_image", "gallery"]
