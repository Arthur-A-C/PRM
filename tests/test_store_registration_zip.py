"""Cadastro via API, files only: PRM ZIP -> SKU -> images/WCDA Dry Run -> approval -> staging write (mocked)."""
import hashlib
import io
import json
import re
import zipfile
from copy import deepcopy

import httpx
import pytest
from PIL import Image

from app.services.store_config import StoreSettings
from app.services.store_publish import PublishSettings
from app.services.store_registration_jobs import Jobs, extract_files, process_one, parse_skus
from app.services.store_registration_plan import format_filesize, identity


SKU = "000123"
ORIGIN = "https://staging.example.test"
COMMERCIAL = {"name": "Estação de comando M1212P", "description": "<p>Descrição do CSV</p>", "short_description": "<p>Curta</p>",
              "categories": [{"id": 5, "name": "Botoeiras"}], "attributes": [{"id": 0, "name": "Cor", "options": ["Preto"]}],
              "regular_price": "199.90", "sale_price": "", "stock_quantity": 7, "stock_status": "instock",
              "manage_stock": True, "status": "publish"}


def jpeg(color="red"):
    stream = io.BytesIO(); Image.new("RGB", (30, 30), color).save(stream, "JPEG"); return stream.getvalue()


def inner_zip():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive: archive.writestr("modelo.step", "ISO-10303")
    return stream.getvalue()


def package(sku=SKU, company="choice", *, tamper=None, extra=None, folder=True, gallery=False, legacy_original=False):
    """Same layout as digitalization_storage.finalize_draft: SKU/manifest.json + Fotos + PRM datasheet + 3D.

    legacy_original reproduces packages exported before the supplier datasheet was left out.
    """
    files = {f"Fotos/{sku}_variante.jpg": jpeg(), f"{sku}_Datasheet.pdf": b"%PDF-1.4 gerado",
             f"{sku}_Desenho_3D.zip": inner_zip(),
             "datasheet_dados.json": b'{"descricao": ["Nao usado neste modulo."]}'}
    roles = {f"Fotos/{sku}_variante.jpg": "main_image", f"{sku}_Datasheet.pdf": "generated_datasheet",
             f"{sku}_Desenho_3D.zip": "drawing_3d", "datasheet_dados.json": "technical_analysis"}
    if legacy_original:
        files[f"{sku}_Datasheet_Original.pdf"] = b"%PDF-1.4 fabricante"; roles[f"{sku}_Datasheet_Original.pdf"] = "source_datasheet"
    ordered = [f"Fotos/{sku}_variante.jpg"]
    if gallery:
        files[f"Fotos/{sku}_foto2.jpg"] = jpeg("blue"); roles[f"Fotos/{sku}_foto2.jpg"] = "gallery"; ordered.append(f"Fotos/{sku}_foto2.jpg")
    manifest = {"schema_version": 1, "status": "validated", "company": company, "cigam_code": sku, "sku": sku,
                "folder_path": "C:\\outra\\maquina\\" + sku, "ordered_images": ordered,
                "product": {"company": company, "cigam_code": sku, "sku": sku, "technical_name": "M1212P", "commercial_title": "M1212P"},
                "files": [{"role": roles[p], "path": p, "sha256": hashlib.sha256(c).hexdigest()} for p, c in files.items()]}
    if tamper: tamper(manifest, files)
    files["manifest.json"] = json.dumps(manifest).encode()
    files.update(extra or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for path, content in files.items():
            archive.writestr(f"{sku}/{path}" if folder else path, content)
    return stream.getvalue()


class Store:
    """Stateful WooCommerce + WordPress media double. Writes only ever reach this object."""
    def __init__(self, sku=SKU, images=(), wcda=None, wcda_meta=True):
        self.library = {10: ORIGIN + "/wp-content/uploads/foto-antiga.jpg"}
        self.titles = {10: "foto-antiga"}
        self.product = {"id": 6260, "sku": sku, **deepcopy(COMMERCIAL),
                        "images": [{"id": i, "src": self.library[i]} for i in images],
                        "meta_data": [{"id": 1, "key": "_yoast_wpseo_focuskw", "value": "botoeira"}] +
                                     ([{"id": 92930, "key": "_wcda_arquivos", "value": deepcopy(wcda or [])}] if wcda_meta else [])}
        self.next_id = 100
        self.methods, self.puts, self.posts = [], [], 0
        self.matches = None
        self.fail_upload, self.lose_upload = set(), set()
        self.lose_put = self.mutate_on_put = False
        self.on_get = None
        self.capabilities = {"upload_files": True, "edit_products": True, "edit_published_products": True, "edit_others_products": True}
        self.product_allow, self.media_allow = "GET, POST, PUT, PATCH, DELETE", "GET, POST"
        self.write_auth = []

    def handle(self, request):
        path, method = request.url.path, request.method
        self.methods.append(method)
        if method in {"POST", "PUT"}: self.write_auth.append(request.headers.get("authorization"))
        if method == "OPTIONS":
            return httpx.Response(200, headers={"Allow": self.media_allow if "/wp/v2/media" in path else self.product_allow})
        if path.endswith("/users/me"):
            return httpx.Response(200, json={"id": 7, "capabilities": self.capabilities})
        if "/wp/v2/media" in path:
            if method == "GET":
                # Like WordPress REST: search matches the attachment title, not the file URL.
                term = request.url.params["search"]
                return httpx.Response(200, json=[{"id": i, "source_url": u} for i, u in self.library.items() if term in self.titles.get(i, "")])
            assert method == "POST"
            self.posts += 1
            name = re.search(rb'filename="([^"]+)"', request.content)[1].decode()
            if any(s in name for s in self.fail_upload): return httpx.Response(500, json={"message": "falha"})
            self.next_id += 1
            self.library[self.next_id] = ORIGIN + "/wp-content/uploads/2026/10/" + name
            self.titles[self.next_id] = re.search(rb'name="title"\r\n\r\n([^\r]*)', request.content)[1].decode()
            if any(s in name for s in self.lose_upload): raise httpx.ReadTimeout("perdida", request=request)
            return httpx.Response(201, json={"id": self.next_id, "source_url": self.library[self.next_id]})
        if path.endswith("/products"):
            rows = self.matches if self.matches is not None else [self.product]
            return httpx.Response(200, json=[r for r in deepcopy(rows) if r["sku"] == request.url.params["sku"]])
        if method == "GET":
            if self.on_get: self.on_get(self)
            return httpx.Response(200, json=deepcopy(self.product))
        assert method == "PUT"
        payload = json.loads(request.content)
        self.puts.append(payload)
        assert set(payload) <= {"images", "meta_data"}
        if "images" in payload:
            self.product["images"] = [{"id": i["id"], "src": self.library[i["id"]]} for i in payload["images"]]
        for meta in payload.get("meta_data", []):
            assert meta["key"] == "_wcda_arquivos"
            target = next(m for m in self.product["meta_data"] if m["id"] == meta["id"])
            target["value"] = meta["value"]
        if self.mutate_on_put: self.product["name"] = "Alterado por outro processo"
        if self.lose_put: raise httpx.ReadTimeout("perdida", request=request)
        return httpx.Response(200, json=deepcopy(self.product))


@pytest.fixture
def settings():
    return StoreSettings(_env_file=None, CHOICE_WC_URL=ORIGIN, CHOICE_WC_KEY="ck_test", CHOICE_WC_SECRET="cs_test",
                         CHOICE_WP_USER="user", CHOICE_WP_APP_PASSWORD="app_password", PRM_STORE_ORGANIZATION_ID="org")


@pytest.fixture
def jobs(tmp_path):
    return Jobs(PublishSettings(_env_file=None, enabled=True, staging_origin=ORIGIN, staging_sku=SKU, storage_dir=str(tmp_path / "queue")))


def drain(jobs, settings, store):
    while process_one(jobs, settings, httpx.MockTransport(store.handle)): pass


def preview(jobs, settings, store, raw=None, name=SKU + ".zip"):
    identifier = jobs.create("choice", "org", "owner", None, raw or package(), settings, identification="folder", archive_name=name)
    drain(jobs, settings, store)
    return identifier, jobs.detail(identifier, "org", "owner")["items"][0]


def publish(jobs, settings, store, identifier, **approval):
    jobs.approve(identifier, "org", "owner", **approval)
    jobs.confirm(identifier, "org", "owner", settings)
    drain(jobs, settings, store)
    return jobs.detail(identifier, "org", "owner")["items"][0]


def commercial(product):
    return {k: product[k] for k in COMMERCIAL} | {"sku": product["sku"],
            "other_meta": [m for m in product["meta_data"] if m["key"] != "_wcda_arquivos"]}


# --- Localização e identificação -------------------------------------------------------------

def test_sku_from_folder_without_csv_and_dry_run_has_only_files(jobs, settings):
    store = Store(wcda=[])
    _, item = preview(jobs, settings, store)
    assert item["sku"] == SKU and item["product_id"] == 6260 and item["state"] == "review"
    assert set(store.methods) == {"GET"}
    dry = item["dry_run"]
    assert dry["scope"] == "files_only" and dry["writable_keys"] == ["images", "meta_data"]
    assert not {"field_changes", "content_payload", "changed_fields"} & set(dry)
    assert "Descrição" not in json.dumps(dry, ensure_ascii=False) and "Nao usado" not in json.dumps(dry)
    assert [(a["name"], a["action"]) for a in dry["images"]["actions"]] == [(f"{SKU}_variante.jpg", "upload")]
    assert [(d["label"], d["action"]) for d in dry["documents"]["actions"]] == [
        ("Datasheet", "add"), ("Desenho 3D", "add")]
    assert dry["ignored"] == []


def test_legacy_package_with_supplier_datasheet_imports_but_never_publishes_it(jobs, settings):
    store = Store(wcda=[])
    identifier, item = preview(jobs, settings, store, package(legacy_original=True))
    dry = item["dry_run"]
    assert item["state"] == "review" and [d["label"] for d in dry["documents"]["actions"]] == ["Datasheet", "Desenho 3D"]
    assert [(i["name"], i["label"]) for i in dry["ignored"]] == [(f"{SKU}_Datasheet_Original.pdf", "Datasheet do fornecedor")]
    publish(jobs, settings, store, identifier)
    value = next(m for m in store.product["meta_data"] if m["key"] == "_wcda_arquivos")["value"]
    assert [d["label"] for d in value] == ["Datasheet", "Desenho 3D"] and store.posts == 3
    assert not any("fabricante" in u or "Original" in u for u in store.library.values())


def test_dry_run_prepared_before_the_rule_is_never_executed(jobs, settings):
    import json as _json
    store = Store(wcda=[])
    identifier, item = preview(jobs, settings, store)
    with jobs.db() as db:
        plan = _json.loads(db.execute("SELECT plan FROM jobs WHERE batch=?", (identifier,)).fetchone()[0])
        plan["dry_run"]["documents"]["actions"].append({"label": "Datasheet do fabricante", "name": "x.pdf", "role": "source_datasheet",
                                                        "bytes": 1, "sha256": "0" * 64, "upload_name": "x.pdf", "action": "add", "wcda_entry": None})
        plan["downloads"].append({"path": "x", "name": "x.pdf", "role": "source_datasheet", "sha256": "0" * 64, "bytes": 1, "label": "x"})
        db.execute("UPDATE jobs SET plan=? WHERE batch=?", (_json.dumps(plan), identifier))
    item = publish(jobs, settings, store, identifier)
    assert item["state"] == "error" and "datasheet do fornecedor" in item["error"] and store.posts == 0 and not store.puts


def test_flat_zip_named_by_sku_keeps_leading_zeros(jobs, settings):
    _, item = preview(jobs, settings, Store(wcda=[]), package(folder=False))
    assert item["sku"] == SKU and item["product_id"] == 6260


def test_leading_zero_sku_never_matched_numerically(jobs, settings):
    store = Store(); store.matches = [{**store.product, "sku": "123"}]
    _, item = preview(jobs, settings, store)
    assert item["state"] == "awaiting_product" and "não existe" in item["error"]


def test_missing_product_is_blocked_and_never_created(jobs, settings):
    store = Store(); store.matches = []
    identifier, item = preview(jobs, settings, store)
    assert item["state"] == "awaiting_product" and "Aguardando cadastro por CSV" in item["error"]
    assert set(store.methods) == {"GET"} and store.posts == 0 and not store.puts
    with pytest.raises(ValueError): jobs.approve(identifier, "org", "owner")
    # Once the CSV flow registers the product, the item is resumed without a new import.
    store.matches = None
    jobs.reprocess(identifier, "org", "owner"); drain(jobs, settings, store)
    assert jobs.detail(identifier, "org", "owner")["items"][0]["state"] == "review"


def test_duplicate_store_sku_blocks(jobs, settings):
    store = Store(); store.matches = [store.product, {**store.product, "id": 9}]
    _, item = preview(jobs, settings, store)
    assert item["state"] == "error" and "duplicado" in item["error"]


def test_duplicate_folders_and_csv_rows_rejected(jobs, settings):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("abc-1/abc-1_variante.jpg", jpeg()); archive.writestr("ABC-1/ABC-1_foto2.jpg", jpeg())
    with pytest.raises(ValueError, match="duplicados"):
        jobs.create("choice", "org", "owner", None, stream.getvalue(), settings, identification="folder")
    with pytest.raises(ValueError, match="duplicado"):
        parse_skus(f"sku\n{SKU}\n{SKU}".encode(), "a.csv", details=True, strict=True)
    assert [p.name for p in jobs.root.iterdir() if len(p.name) == 32] == []


@pytest.mark.parametrize("tamper,message", [
    (lambda m, f: m["files"][0].update(sha256="0" * 64), "Hash"),
    (lambda m, f: m.update(sku="999"), "diverge"),
    (lambda m, f: m.update(company="sag"), "diverge"),
    (lambda m, f: m["files"].append({"role": "manual", "path": "ausente.pdf", "sha256": "0" * 64}), "Manifesto|ausente"),
    (lambda m, f: m["files"].append({"role": "manual", "path": "../fora.pdf", "sha256": "0" * 64}), "inválido"),
    (lambda m, f: m.update(status="draft"), "não corresponde"),
])
def test_invalid_manifest_rejected_before_store_query(jobs, settings, tamper, message):
    store = Store()
    _, item = preview(jobs, settings, store, package(tamper=tamper))
    assert item["state"] == "error" and re.search(message, item["error"]) and store.methods == []


def test_undeclared_file_in_manifest_package_rejected(jobs, settings):
    _, item = preview(jobs, settings, Store(), package(extra={"intruso.pdf": b"%PDF-1.4"}))
    assert item["state"] == "error" and "não declarado" in item["error"]


def test_batch_export_bundle_and_unsupported_format(jobs, settings, tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(f"CHOICE/{SKU}.pdf", b"%PDF-1.4 lote")
        archive.writestr(f"CHOICE/{SKU}/analysis.json", "{}")
        archive.writestr(f"CHOICE/{SKU}/{SKU}_Desenho 3D.step", "ISO-10303")
        archive.writestr(f"CHOICE/{SKU}/fontes/foto fornecedor.jpg", jpeg())
        archive.writestr("relatorio_processamento.csv", "codigo\n" + SKU)
        archive.writestr("erros.csv", "codigo\n")
    _, item = preview(jobs, settings, Store(wcda=[]), stream.getvalue(), name="lote.zip")
    dry = item["dry_run"]
    assert [d["name"] for d in dry["documents"]["actions"]] == [f"{SKU}_Datasheet.pdf"]
    assert dry["ignored"][0]["name"] == f"{SKU}_Desenho 3D.step" and dry["images"]["actions"] == []
    assert any(f["label"] == "fonte (não publicada)" for f in item["files"])
    with pytest.raises(ValueError, match="outra empresa"):
        extract_files(stream.getvalue(), tmp_path / "sag", identification="folder", company="sag")


# --- Imagens ------------------------------------------------------------------------------

def test_upload_sets_main_image_on_product_without_images(jobs, settings):
    store = Store(wcda=[])
    identifier, item = preview(jobs, settings, store)
    assert item["dry_run"]["images"]["main_image"]["action"] == "set_from_upload"
    before = commercial(store.product)
    done = publish(jobs, settings, store, identifier)
    assert done["state"] == "done" and done["result"]["verified"]
    image = store.product["images"][0]
    assert identity(hashlib.sha256(jpeg()).hexdigest()) in image["src"]
    assert commercial(store.product) == before


def test_gallery_preserves_existing_main_and_order(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, item = preview(jobs, settings, store, package(gallery=True))
    main = item["dry_run"]["images"]["main_image"]
    assert main["action"] == "preserve" and main["replacement_available"]
    publish(jobs, settings, store, identifier)
    ids = [i["id"] for i in store.product["images"]]
    assert ids[0] == 10 and len(ids) == 3


def test_main_image_replacement_only_with_explicit_approval(jobs, settings):
    store = Store(images=[10], wcda=[])
    identifier, _ = preview(jobs, settings, store)
    publish(jobs, settings, store, identifier, replace_main=[SKU])
    ids = [i["id"] for i in store.product["images"]]
    assert ids[0] != 10 and ids[1] == 10  # previous main kept in the gallery, never removed


def test_replace_main_rejected_when_not_applicable(jobs, settings):
    identifier, _ = preview(jobs, settings, Store(wcda=[]))
    with pytest.raises(ValueError, match="Substituição"):
        jobs.approve(identifier, "org", "owner", replace_main=[SKU])


def test_linked_image_by_identity_is_not_resent_and_name_conflict_blocks(jobs, settings):
    digest = hashlib.sha256(jpeg()).hexdigest()
    store = Store(wcda=[]); store.library[10] = f"{ORIGIN}/wp-content/uploads/prm-{digest}-1.jpg"
    store.product["images"] = [{"id": 10, "src": store.library[10]}]
    _, item = preview(jobs, settings, store)
    assert item["dry_run"]["images"]["actions"][0]["action"] == "already_linked"
    store = Store(wcda=[]); store.library[10] = f"{ORIGIN}/wp-content/uploads/{SKU}_variante.jpg"
    store.product["images"] = [{"id": 10, "src": store.library[10]}]
    _, item = preview(jobs, settings, store)
    assert item["state"] == "blocked" and "mesmo nome" in item["error"]


def test_identical_files_in_package_uploaded_once(jobs, settings):
    extra = {"Fotos/copia.jpg": jpeg()}
    def tamper(manifest, files):
        files["Fotos/copia.jpg"] = jpeg()
        manifest["ordered_images"].append("Fotos/copia.jpg")
        manifest["files"].append({"role": "gallery", "path": "Fotos/copia.jpg", "sha256": hashlib.sha256(jpeg()).hexdigest()})
    store = Store(wcda=[])
    identifier, item = preview(jobs, settings, store, package(tamper=tamper))
    assert [a["action"] for a in item["dry_run"]["images"]["actions"]] == ["upload", "duplicate_in_package"]
    publish(jobs, settings, store, identifier)
    assert len(store.product["images"]) == 1 and store.posts == 3  # 1 image + 2 documents


# --- Documentos WCDA ----------------------------------------------------------------------

EXISTING = [{"label": "Manual", "url": ORIGIN + "/up/manual.pdf", "filename": "manual.pdf", "filesize": "421.1 KB"},
            {"label": "Certificado", "url": ORIGIN + "/up/cert.pdf", "filename": "cert.pdf", "filesize": "86.7 KB"}]


def test_wcda_append_preserves_existing_documents_and_order(jobs, settings):
    store = Store(wcda=EXISTING)
    identifier, item = preview(jobs, settings, store)
    assert item["dry_run"]["documents"]["mode"] == "append" and item["dry_run"]["documents"]["final_count"] == 4
    publish(jobs, settings, store, identifier)
    value = next(m for m in store.product["meta_data"] if m["key"] == "_wcda_arquivos")["value"]
    assert value[:2] == EXISTING
    added = value[2:]
    assert [d["label"] for d in added] == ["Datasheet", "Desenho 3D"]
    assert set(added[0]) == {"label", "url", "filename", "filesize"}
    assert added[0]["url"] in store.library.values() and added[0]["filename"] == added[0]["url"].rsplit("/", 1)[1]
    assert added[0]["filesize"] == format_filesize(len(b"%PDF-1.4 gerado"))
    put = store.puts[-1]
    assert [m["key"] for m in put["meta_data"]] == ["_wcda_arquivos"] and put["meta_data"][0]["id"] == 92930


def test_first_inclusion_into_empty_wcda_with_rollback_to_empty(jobs, settings):
    store = Store(wcda=[])
    identifier, item = preview(jobs, settings, store)
    docs = item["dry_run"]["documents"]
    assert docs["mode"] == "first_inclusion" and docs["existing"] == [] and item["dry_run"]["rollback"]["wcda_before_count"] == 0
    assert all(a["wcda_entry"]["url"] is None for a in docs["actions"])  # no invented URLs before upload
    done = publish(jobs, settings, store, identifier)
    assert done["result"]["rollback"]["meta_data"] == [{"id": 92930, "key": "_wcda_arquivos", "value": []}]
    assert done["result"]["rollback"]["media_deletion"] is False


def test_missing_wcda_meta_blocks_documents(jobs, settings):
    _, item = preview(jobs, settings, Store(wcda_meta=False))
    assert item["state"] == "blocked" and any("_wcda_arquivos incompatível" in b for b in item["blockers"])


def test_wcda_label_conflict_blocks_and_linked_document_is_ignored(jobs, settings):
    store = Store(wcda=[{"label": "Datasheet", "url": ORIGIN + "/up/outro.pdf", "filename": "outro.pdf", "filesize": "1 MB"}])
    _, item = preview(jobs, settings, store)
    assert item["state"] == "blocked" and any("WCDA" in b for b in item["blockers"])
    digest = hashlib.sha256(b"%PDF-1.4 gerado").hexdigest()
    store = Store(wcda=[{"label": "Ficha", "url": f"{ORIGIN}/up/x_{identity(digest)}.pdf", "filename": "x.pdf", "filesize": "1 KB"}])
    _, item = preview(jobs, settings, store)
    assert item["dry_run"]["documents"]["actions"][0]["action"] == "already_linked"


# --- Falhas, concorrência e recuperação -----------------------------------------------------

def test_partial_upload_failure_keeps_uploaded_media_and_retry_does_not_duplicate(jobs, settings):
    store = Store(wcda=[]); store.fail_upload = {"Desenho"}
    identifier, _ = preview(jobs, settings, store)
    item = publish(jobs, settings, store, identifier)
    assert item["state"] == "error" and not store.puts and store.posts == 3
    assert len(store.library) == 3  # 2 uploads preserved, nothing deleted
    store.fail_upload = set()
    jobs.reprocess(identifier, "org", "owner"); drain(jobs, settings, store)
    item = publish(jobs, settings, store, identifier)
    assert item["state"] == "done" and store.posts == 4 and len(store.puts) == 1
    assert any(e["event"] == "upload_reused" for e in item["audit"]) and any(e["event"] == "error" for e in item["audit"])


def test_lost_upload_response_is_reconciled_by_library_identity(jobs, settings):
    store = Store(wcda=[]); store.lose_upload = {"prm-"}
    identifier, _ = preview(jobs, settings, store)
    assert publish(jobs, settings, store, identifier)["state"] == "error" and store.posts == 1
    store.lose_upload = set()
    jobs.reprocess(identifier, "org", "owner"); drain(jobs, settings, store)
    item = publish(jobs, settings, store, identifier)
    assert item["state"] == "done" and store.posts == 3 and len(store.product["images"]) == 1


def test_concurrent_change_before_put_sends_nothing(jobs, settings):
    store = Store(wcda=[])
    identifier, _ = preview(jobs, settings, store)
    store.product["images"] = [{"id": 10, "src": store.library[10]}]
    item = publish(jobs, settings, store, identifier)
    assert item["state"] == "error" and "alterado" in item["error"] and store.posts == 0 and not store.puts


def test_concurrent_change_after_uploads_preserves_media_without_put(jobs, settings):
    store = Store(wcda=[])
    identifier, _ = preview(jobs, settings, store)
    calls = {"n": 0}
    def touch(s):
        calls["n"] += 1
        if s.posts: s.product["meta_data"][-1]["value"] = [EXISTING[0]]
    store.on_get = touch
    item = publish(jobs, settings, store, identifier)
    assert item["state"] == "error" and "concorrente" in item["error"] and store.posts == 3 and not store.puts


def test_lost_put_response_is_reconciled_without_second_put(jobs, settings):
    store = Store(wcda=[]); store.lose_put = True
    identifier, _ = preview(jobs, settings, store)
    item = publish(jobs, settings, store, identifier)
    assert item["state"] == "done" and len(store.puts) == 1  # read-back verified the persisted state


def test_commercial_field_change_during_put_is_never_accepted(jobs, settings):
    store = Store(wcda=[]); store.mutate_on_put = True
    identifier, _ = preview(jobs, settings, store)
    item = publish(jobs, settings, store, identifier)
    assert item["state"] == "error" and "não confirmada" in item["error"] and len(store.puts) == 1


def test_put_payload_never_contains_commercial_fields(jobs, settings):
    store = Store(images=[10], wcda=EXISTING)
    before = commercial(store.product)
    identifier, _ = preview(jobs, settings, store, package(gallery=True))
    publish(jobs, settings, store, identifier)
    assert len(store.puts) == 1 and set(store.puts[0]) == {"images", "meta_data"}
    assert all(m["key"] == "_wcda_arquivos" for m in store.puts[0]["meta_data"])
    assert commercial(store.product) == before


# --- Aprovação e bloqueios de gravação -----------------------------------------------------

def test_confirm_requires_approval_of_exact_dry_run(jobs, settings):
    store = Store(wcda=[])
    identifier, _ = preview(jobs, settings, store)
    with pytest.raises(ValueError, match="aprovado"): jobs.confirm(identifier, "org", "owner", settings)
    assert jobs.approve(identifier, "org", "owner", skus=[SKU]) == [SKU]
    with pytest.raises(ValueError): jobs.approve(identifier, "org", "owner", skus=["outro"])
    with pytest.raises(LookupError): jobs.approve(identifier, "org", "intruder")
    item = jobs.detail(identifier, "org", "owner")["items"][0]
    assert item["approval"]["writes_authorized"] is False and item["state"] == "review" and not store.posts


@pytest.mark.parametrize("host", ["choicetech.com.br", "sagloja.devsplcomunic.com.br", "portwell.com.br"])
def test_production_stores_stay_read_only_even_when_policy_enabled(tmp_path, host):
    settings = StoreSettings(_env_file=None, CHOICE_WC_URL="https://" + host, CHOICE_WC_KEY="ck", CHOICE_WC_SECRET="cs",
                             CHOICE_WP_USER="u", CHOICE_WP_APP_PASSWORD="p", PRM_STORE_ORGANIZATION_ID="org")
    jobs = Jobs(PublishSettings(_env_file=None, enabled=True, staging_origin="https://" + host, staging_sku=SKU,
                                storage_dir=str(tmp_path / "queue")))
    store = Store(wcda=[])
    identifier, item = preview(jobs, settings, store)
    assert "bloqueada" in item["dry_run"]["write_gate"]
    jobs.approve(identifier, "org", "owner")
    assert jobs.detail(identifier, "org", "owner")["can_confirm"] is False
    with pytest.raises(ValueError, match="bloqueada"): jobs.confirm(identifier, "org", "owner", settings)
    assert set(store.methods) == {"GET"}


def test_api_files_flow_with_individual_approval(tmp_path, settings, monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.dependencies import get_current_auth
    from app.routers import store_integrations, store_registration
    from app.services.security import hash_secret
    policy = PublishSettings(_env_file=None, storage_dir=str(tmp_path / "queue"))
    app = FastAPI(); app.include_router(store_registration.router)
    auth = SimpleNamespace(user=SimpleNamespace(role="gestor", id="owner", organization_id="org"),
                           login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_current_auth] = lambda: auth
    monkeypatch.setattr(store_integrations, "StoreSettings", lambda: settings)
    monkeypatch.setattr(store_registration, "Jobs", lambda: Jobs(policy))
    with TestClient(app) as client:
        response = client.post("/api/v1/cadastro-api", data={"empresa": "choice", "identificacao": "folder"},
                               files={"arquivos": (SKU + ".zip", package())}, headers={"X-CSRF-Token": "csrf"})
        assert response.status_code == 200, response.text
        identifier = response.json()["id"]
        drain(Jobs(policy), settings, Store(wcda=[]))
        url = f"/api/v1/cadastro-api/{identifier}"
        assert client.post(url + "/aprovar", json={"skus": [SKU]}).status_code == 403
        approved = client.post(url + "/aprovar", json={"skus": [SKU]}, headers={"X-CSRF-Token": "csrf"})
        assert approved.status_code == 200 and approved.json()["items"][0]["approval"]["replace_main"] is False
        assert client.post(url + "/confirmar", headers={"X-CSRF-Token": "csrf"}).status_code == 422  # writes disabled
        report = client.get(url + "/relatorio").content.decode("utf-8-sig")
        assert f"{SKU}_variante.jpg" in report and "Desenho 3D" in report and "Original" not in report and ",sim" in report
        dry_run = client.get(url + "/dry-run").text
        for secret in ("ck_test", "cs_test", "app_password", str(tmp_path)):
            assert secret not in dry_run


def test_wcda_service_first_inclusion_is_opt_in_with_empty_rollback():
    from app.services.store_document_update import prepare_document_update, rollback_payload, verify_document_update
    product = Store(wcda=[]).product
    entry = {"label": "Datasheet", "url": ORIGIN + "/up/d_prm-0123456789abcdef.pdf", "filename": "d_prm-0123456789abcdef.pdf", "filesize": "90.8 KB"}
    with pytest.raises(ValueError, match="rollback não vazio"):
        prepare_document_update("choice", ORIGIN, product, SKU, [entry])
    plan = prepare_document_update("choice", ORIGIN, product, SKU, [entry], allow_empty=True)
    assert plan.first_inclusion and plan.added == 1
    after = deepcopy(product); after["meta_data"][-1]["value"] = [entry]
    assert verify_document_update(plan, after)["verified"]
    assert rollback_payload(plan, after) == {"meta_data": [{"id": 92930, "key": "_wcda_arquivos", "value": []}]}
