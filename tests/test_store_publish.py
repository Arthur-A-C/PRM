import io
import json
import re
import zipfile
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.services.store_config import StoreSettings
from app.services.store_publish import PublishSettings, StagingPublisher, file_info, snapshot_hash
from app.services.store_registration_jobs import Jobs,Journal,parse_skus,process_one,extract_files
from app.services.store_registration_plan import prepare_files


def image_bytes():
    stream=io.BytesIO();Image.new("RGB",(30,30),"red").save(stream,"PNG");return stream.getvalue()


@pytest.fixture
def settings():
    return StoreSettings(_env_file=None,CHOICE_WC_URL="https://staging.example.test",
        CHOICE_WC_KEY="ck_test",CHOICE_WC_SECRET="cs_test",CHOICE_WP_USER="user",
        CHOICE_WP_APP_PASSWORD="app_password",PRM_STORE_ORGANIZATION_ID="org")


@pytest.fixture
def policy(tmp_path):
    return PublishSettings(_env_file=None,enabled=True,staging_origin="https://staging.example.test",
                           staging_sku="00123",storage_dir=str(tmp_path/"queue"))


def archive(documents=False):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("00123/00123_variante.png",image_bytes())
        z.writestr("00123/00123_foto2.png",image_bytes())
        if documents: z.writestr("00123/00123_Datasheet.pdf",b"%PDF-1.4 example")
    return buf.getvalue()


class Shop:
    def __init__(self):
        self.product={"id":8,"sku":"00123","name":"Untouched","description":"Untouched",
                      "images":[{"id":10}],"meta_data":[{"key":"_wcda_arquivos","value":[{"label":"Existing","url":"https://staging.example.test/doc.pdf"}]}]}
        self.calls=[];self.uploads=0;self.puts=0;self.uncertain=False;self.media={10:"https://staging.example.test/old.png"}
    def handle(self,request):
        self.calls.append(request.method)
        if request.method=="OPTIONS":
            return httpx.Response(200,headers={"Allow":"GET, POST" if "/wp/v2/media" in request.url.path else "GET, POST, PUT, PATCH, DELETE"})
        if request.method=="GET":
            if request.url.path.endswith("/users/me"): return httpx.Response(200,json={"id":7,"capabilities":{"upload_files": True, "edit_products": True, "edit_published_products": True, "edit_others_products": True}})
            if "/wp/v2/media" in request.url.path: return httpx.Response(200,json=[])
            return httpx.Response(200,json=[deepcopy(self.product)] if request.url.path.endswith("/products") else deepcopy(self.product))
        if request.method=="POST":
            self.uploads+=1
            if self.uncertain: raise httpx.ReadTimeout("private",request=request)
            name=re.search(rb'filename="([^"]+)"',request.content)[1].decode()
            self.media[20]="https://staging.example.test/up/"+name
            return httpx.Response(201,json={"id":20,"source_url":self.media[20]})
        if request.method=="PUT":
            self.puts+=1
            payload=json.loads(request.content)
            assert set(payload)=={"images"}
            # Like WooCommerce: linked images expose the media URL.
            self.product["images"]=[{"id":i["id"],"src":self.media[i["id"]]} for i in payload["images"]]
            return httpx.Response(200,json=self.product)
        pytest.fail("Unexpected method")


def preview(jobs,settings,shop,documents=False):
    identifier=jobs.create("choice","org","owner",["00123"],archive(documents),settings)
    assert process_one(jobs,settings,httpx.MockTransport(shop.handle))
    return identifier


def test_preview_confirm_publish_preserve_dedup_persistent(policy,settings):
    jobs=Jobs(policy);shop=Shop()
    identifier=preview(jobs,settings,shop)
    detail=jobs.detail(identifier,"org","owner")
    assert detail["items"][0]["state"]=="review"
    assert detail["items"][0]["existing_images"]==1
    assert all(method=="GET" for method in shop.calls)
    with pytest.raises(ValueError): jobs.confirm(identifier,"org","owner",settings)  # approval first
    jobs.approve(identifier,"org","owner")
    jobs.confirm(identifier,"org","owner",settings)
    assert process_one(Jobs(policy),settings,httpx.MockTransport(shop.handle))
    assert jobs.detail(identifier,"org","owner")["items"][0]["state"]=="done"
    assert shop.uploads==1  # identical main and gallery bytes
    assert [i["id"] for i in shop.product["images"]]==[10,20]
    assert shop.product["name"]=="Untouched" and shop.product["description"]=="Untouched"
    assert shop.product["meta_data"][0]["value"][0]["label"]=="Existing"
    jobs.reprocess(identifier,"org","owner")
    assert jobs.detail(identifier,"org","owner")["items"][0]["state"]=="done"
    # A new batch with identical bytes sees the linked media identity: nothing to send.
    second=preview(jobs,settings,shop)
    assert jobs.detail(second,"org","owner")["items"][0]["state"]=="blocked"
    with pytest.raises(ValueError): jobs.approve(second,"org","owner")
    assert shop.uploads==shop.puts==1


def test_documents_block_before_upload(policy,settings):
    jobs=Jobs(policy);shop=Shop()
    identifier=preview(jobs,settings,shop,True)
    detail=jobs.detail(identifier,"org","owner")
    assert detail["items"][0]["state"]=="blocked"
    assert any(f["label"]=="Datasheet" for f in detail["items"][0]["files"])
    with pytest.raises(ValueError): jobs.confirm(identifier,"org","owner",settings)
    assert shop.uploads==shop.puts==0


def test_uncertain_upload_not_repeated(policy,settings):
    jobs=Jobs(policy);shop=Shop();identifier=preview(jobs,settings,shop)
    jobs.approve(identifier,"org","owner");jobs.confirm(identifier,"org","owner",settings);shop.uncertain=True
    process_one(jobs,settings,httpx.MockTransport(shop.handle))
    assert shop.uploads==1
    jobs.reprocess(identifier,"org","owner");process_one(jobs,settings,httpx.MockTransport(shop.handle))
    jobs.approve(identifier,"org","owner");jobs.confirm(identifier,"org","owner",settings);shop.uncertain=False
    process_one(jobs,settings,httpx.MockTransport(shop.handle))
    assert shop.uploads==1 and shop.puts==0


def test_concurrent_change_and_missing_sku(policy,settings):
    jobs=Jobs(policy);shop=Shop();identifier=preview(jobs,settings,shop)
    jobs.approve(identifier,"org","owner");jobs.confirm(identifier,"org","owner",settings)
    shop.product["images"].append({"id":99})
    process_one(jobs,settings,httpx.MockTransport(shop.handle))
    assert jobs.detail(identifier,"org","owner")["items"][0]["state"]=="error"
    assert shop.uploads==0
    identifier=jobs.create("choice","org","owner",["00123"],archive(),settings)
    process_one(jobs,settings,httpx.MockTransport(lambda _:httpx.Response(200,json=[])))
    assert "não existe" in jobs.detail(identifier,"org","owner")["items"][0]["error"]


def test_owner_org_and_expired_lease(policy,settings):
    jobs=Jobs(policy);identifier=jobs.create("choice","org","owner",["00123"],archive(),settings)
    with pytest.raises(LookupError): jobs.detail(identifier,"other","owner")
    with pytest.raises(LookupError): jobs.confirm(identifier,"org","other",settings)
    job=jobs.claim()
    assert jobs.claim() is None
    with jobs.db() as db: db.execute("UPDATE jobs SET lease=0")
    assert jobs.claim() is None
    jobs.finish(job,"done")
    assert jobs.detail(identifier,"org","owner")["items"][0]["state"]=="uncertain"


@pytest.mark.parametrize("host",["choicetech.com.br","sagloja.devsplcomunic.com.br","portwell.com.br"])
def test_production_write_block_even_enabled(policy,host):
    policy.staging_origin="https://"+host
    with pytest.raises(ValueError,match="bloqueada"): policy.authorize(policy.staging_origin,"00123")


def test_disabled_or_wrong_sku_or_destination(policy):
    with pytest.raises(ValueError): policy.authorize(policy.staging_origin,"999")
    with pytest.raises(ValueError): policy.authorize("https://other.test","00123")
    policy.enabled=False
    with pytest.raises(ValueError): policy.authorize(policy.staging_origin,"00123")


@pytest.mark.parametrize("content",["SKU\n00123\n00123\nABC-9", "\ufeffcodigo cigam;nome\n00123;Teste\nABC-9;Outro","00123\nABC-9"])
def test_csv_skus_preserve_zeros(content):
    assert parse_skus(content.encode("utf-8"),"a.csv")==["00123","ABC-9"]


def test_xlsx_skus(tmp_path):
    from openpyxl import Workbook
    book=Workbook();book.active.append(["Código CIGAM"]);book.active.append(["00123"]);book.active.append([12345])
    stream=io.BytesIO();book.save(stream)
    assert parse_skus(stream.getvalue(),"a.xlsx")==["00123","12345"]


def test_zip_slip(tmp_path):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z: z.writestr("../escape.pdf",b"x")
    with pytest.raises(ValueError): extract_files(stream.getvalue(),tmp_path)
    assert not (tmp_path.parent/"escape.pdf").exists()


def test_legacy_file_rules_and_multiple_labels(tmp_path):
    folder=tmp_path/"00123";folder.mkdir()
    for name in ["00123_variante.png","00123_foto2.png","00123_foto10.png","00123_Manual A.pdf","00123_Manual B.zip","00123_3d.zip"]:
        (folder/name).write_bytes(b"fixture")
    plan=prepare_files(folder,"00123")
    assert plan["main_image"].endswith("_variante.png")
    assert [Path(p).name for p in plan["gallery"]]==["00123_foto2.png","00123_foto10.png"]
    assert [i["label"] for i in plan["downloads"]]==["Manual A","Manual B","Desenho 3D"]
    photos=folder/"Fotos";photos.mkdir()
    (photos/"a.png").write_bytes(b"fixture");(photos/"b.png").write_bytes(b"fixture");(photos/"front.png").write_bytes(b"fixture")
    plan=prepare_files(folder,"00123")
    assert plan["main_image"].endswith("b.png") and plan["gallery"][0].endswith("front.png")


def test_file_validation(tmp_path):
    file=tmp_path/"a.jpg";file.write_bytes(b"not an image")
    with pytest.raises(Exception): file_info(file)
    file=tmp_path/"a.svg";file.write_bytes(b"<svg/>")
    with pytest.raises(ValueError): file_info(file)


def test_existing_filename_blocks_duplicate_without_upload(policy,settings):
    jobs=Jobs(policy);shop=Shop()
    shop.product["images"][0]["src"]="https://staging.example.test/00123_variante.png"
    identifier=preview(jobs,settings,shop)
    assert "mesmo nome" in jobs.detail(identifier,"org","owner")["items"][0]["error"]
    assert shop.uploads==0


def test_bad_item_does_not_block_others(policy,settings):
    jobs=Jobs(policy);shop=Shop()
    identifier=jobs.create("choice","org","owner",["missing","00123"],archive(),settings)
    process_one(jobs,settings,httpx.MockTransport(shop.handle))
    process_one(jobs,settings,httpx.MockTransport(shop.handle))
    states={i["sku"]:i["state"] for i in jobs.detail(identifier,"org","owner")["items"]}
    assert states=={"missing":"error","00123":"review"}


def test_api_access_csrf_and_production_gate(policy,settings,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import store_registration,store_integrations
    from app.dependencies import get_current_auth
    from app.services.security import hash_secret
    from types import SimpleNamespace
    app=FastAPI();app.include_router(store_registration.router)
    auth=SimpleNamespace(user=SimpleNamespace(role="gestor",id="owner",organization_id="org"),
                         login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_current_auth]=lambda:auth
    monkeypatch.setattr(store_integrations,"StoreSettings",lambda:settings)
    monkeypatch.setattr(store_registration,"Jobs",lambda:Jobs(policy))
    with TestClient(app) as client:
        fields={"empresa":"choice"}
        files={"planilha":("codes.csv",b"SKU\n00123"),"arquivos":("files.zip",archive())}
        assert client.post("/api/v1/cadastro-api",data=fields,files=files).status_code==403
        response=client.post("/api/v1/cadastro-api",data=fields,files=files,headers={"X-CSRF-Token":"csrf"})
        assert response.status_code==200,response.text
        identifier=response.json()["id"]
        process_one(Jobs(policy),settings,httpx.MockTransport(Shop().handle))
        assert client.get(f"/api/v1/cadastro-api/{identifier}/relatorio").status_code==200
        policy.enabled=False
        assert client.post(f"/api/v1/cadastro-api/{identifier}/confirmar",headers={"X-CSRF-Token":"csrf"}).status_code==422
        auth.user.id="other"
        assert client.get(f"/api/v1/cadastro-api/{identifier}").status_code==404
        auth.user.role="vendedor"
        assert client.get("/api/v1/cadastro-api").status_code==403
