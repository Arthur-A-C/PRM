"""Real persisted PRM identities + real queue, with mocked WooCommerce/WordPress only."""
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_auth
from app.models.identity import User
from app.routers import store_registration as router, store_integrations
from app.services import store_registration_authorization as authorization, store_publish_grant as grants
from app.services.store_config import StoreSettings
from app.services.store_publish import PublishSettings
from app.services.store_registration_jobs import Jobs, process_one
from app.services.security import hash_secret
from test_store_removal_production import people, ORIGINS
from test_store_registration_zip import Store, package, commercial, EXISTING
from test_batch_publication import Shop, lot
from test_store_registration_scope import numbered


@pytest.fixture
def setup(tmp_path, people, monkeypatch):
    env={"PRM_STORE_ORGANIZATION_ID":str(people.org.id)}
    for company, origin in ORIGINS.items():
        env.update({company.upper()+"_WC_URL":origin,company.upper()+"_WC_KEY":"ck_test",company.upper()+"_WC_SECRET":"cs_test",
                    company.upper()+"_WP_USER":"test",company.upper()+"_WP_APP_PASSWORD":"test_password"})
    settings=StoreSettings(_env_file=None,**env)
    jobs=Jobs(PublishSettings(_env_file=None,storage_dir=str(tmp_path/"queue")))
    monkeypatch.setattr(authorization.access,"session",people.session)
    monkeypatch.setattr(store_integrations,"StoreSettings",lambda:settings)
    monkeypatch.setattr(router,"Jobs",lambda:jobs)
    def forbidden(*args,**kwargs): pytest.fail("Legacy authorization invoked")
    monkeypatch.setattr(PublishSettings,"authorize",forbidden)
    for name in ("find","consume","issue"):
        monkeypatch.setattr(grants,name,forbidden)
    app=FastAPI();app.include_router(router.router)
    state=SimpleNamespace(user=people.users["ana"])
    app.dependency_overrides[get_current_auth]=lambda:SimpleNamespace(user=state.user,login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    with TestClient(app) as client:
        yield SimpleNamespace(jobs=jobs,settings=settings,people=people,client=client,state=state)


H={"X-CSRF-Token":"csrf"}


def drain(setup, store):
    while process_one(setup.jobs,setup.settings,httpx.MockTransport(store.handle)): pass


def create(setup, company="choice", sku="000123", raw=None, escopo="all"):
    response=setup.client.post("/api/v1/cadastro-api",data={"empresa":company,"identificacao":"folder","escopo":escopo},
                               files={"arquivos":(sku+".zip",raw or package(sku=sku,company=company,gallery=True))},headers=H)
    assert response.status_code==200,response.text
    return "/api/v1/cadastro-api/"+response.json()["id"]


def ready(setup, url, store):
    """Preview, then the explicit main choice (the image the folder suggests) for SKUs waiting for it."""
    drain(setup,store)
    for item in setup.client.get(url).json()["items"]:
        if item["state"]=="awaiting_main":
            option=next(o for o in item["dry_run"]["main_options"] if o["suggested"])
            response=setup.client.post(url+"/principal",json={"sku":item["sku"],"sha256":option["sha256"]},headers=H)
            assert response.status_code==200,response.text
    drain(setup,store)


def approve_confirm(setup,url,sku="000123",replace=False):
    body={"skus":[sku],"replace_main":[sku] if replace else []}
    result=setup.client.post(url+"/aprovar",json=body,headers=H)
    assert result.status_code==200,result.text
    result=setup.client.post(url+"/confirmar",json={"skus":[sku],"confirmado":True},headers=H)
    assert result.status_code==200,result.text


@pytest.mark.parametrize("actor",["ana","dev"])
@pytest.mark.parametrize("company",sorted(ORIGINS))
@pytest.mark.parametrize("replace",[False,True])
def test_roles_upload_verify_and_restore_without_grants(setup,actor,company,replace):
    setup.state.user=setup.people.users[actor]
    store=Store(images=[10],wcda=EXISTING)
    before=commercial(store.product)
    url=create(setup,company,escopo="all" if replace else "gallery,documents");ready(setup,url,store)
    approve_confirm(setup,url,replace=replace);drain(setup,store)
    view=setup.client.get(url).json(); item=view["items"][0]
    assert item["state"]=="done" and item["result"]["verified"]
    assert commercial(store.product)==before
    ids=[i["id"] for i in store.product["images"]]
    assert (ids[0]!=10 and ids[1]==10) if replace else ids[0]==10
    assert store.product["meta_data"][-1]["value"][:len(EXISTING)]==EXISTING
    assert "homologation_grant" not in item and grants.listing(setup.jobs)==[]
    result=setup.client.post(url+"/restaurar",json={"skus":["000123"],"confirmado":True},headers=H)
    assert result.status_code==200,result.text
    drain(setup,store)
    assert setup.client.get(url).json()["items"][0]["state"]=="rolled_back"
    assert [i["id"] for i in store.product["images"]]==[10]
    assert store.product["meta_data"][-1]["value"]==EXISTING and commercial(store.product)==before
    assert "DELETE" not in store.methods


@pytest.mark.parametrize("change",["role","inactive","organization","actor","hash","file_plan","approval","confirmed","product_id","sku"])
def test_worker_revalidates_identity_and_bound_plan(setup,change):
    store=Store(wcda=[]);url=create(setup);ready(setup,url,store);approve_confirm(setup,url)
    if change in {"role","inactive","organization"}:
        with setup.people.session() as db:
            user=db.get(User,setup.state.user.id)
            if change=="role": user.role="vendedor"
            elif change=="inactive": user.active=False
            else: user.organization_id=setup.people.users["fora"].organization_id
            db.commit()
    else:
        with setup.jobs.db() as db:
            row=db.execute("SELECT batch,sku,plan FROM jobs").fetchone();p=json.loads(row["plan"])
            if change=="hash": p["dry_run"]["dry_run_sha256"]="0"*64
            elif change=="file_plan": p["images"][0]["role"]="gallery"
            elif change=="approval": p["approval"]["replace_main"]=True
            elif change=="actor": p["execution"]["by"]=str(setup.people.users["vera"].id)
            elif change=="confirmed": p["execution"]["confirmed"]=False
            else: p["execution"][change]="modified"
            db.execute("UPDATE jobs SET plan=?",(json.dumps(p),))
    drain(setup,store)
    with setup.jobs.db() as db: assert db.execute("SELECT state FROM jobs").fetchone()[0]=="error"
    assert store.posts==0 and not store.puts


def test_role_revoked_between_uploads_prevents_further_writes(setup):
    store=Store(wcda=[]);url=create(setup);ready(setup,url,store);approve_confirm(setup,url)
    handle=store.handle
    def revoke(request):
        response=handle(request)
        if request.method=="POST":
            with setup.people.session() as db:
                db.get(User,setup.state.user.id).active=False;db.commit()
        return response
    store.handle=revoke
    drain(setup,store)
    assert store.posts==1 and not store.puts


@pytest.mark.parametrize("endpoint",["aprovar","confirmar","restaurar","reprocessar"])
def test_seller_denied(setup,endpoint):
    setup.state.user=setup.people.users["vera"]
    response=setup.client.post("/api/v1/cadastro-api/x/"+endpoint,json={"skus":["000123"],"confirmado":True},headers=H)
    assert response.status_code==403
    assert setup.client.get("/api/v1/cadastro-api").status_code==403


def test_csrf_confirmation_owner_and_organization(setup):
    store=Store(wcda=[]);url=create(setup);ready(setup,url,store)
    assert setup.client.post(url+"/aprovar",json={"skus":["000123"]}).status_code==403
    assert setup.client.post(url+"/confirmar",json={"skus":["000123"]},headers=H).status_code==422
    assert setup.client.post(url+"/confirmar",json={"confirmado":True},headers=H).status_code==422
    setup.state.user=setup.people.users["dev"]
    assert setup.client.get(url).status_code==404
    setup.state.user=setup.people.users["fora"]
    assert setup.client.get(url).status_code==403
    assert store.posts==0


def test_one_selected_sku_does_not_queue_the_other_22(setup):
    skus=[f"000{n:03}" for n in range(23)]
    store=Shop(skus)
    url=create(setup,raw=numbered(lot(skus)));ready(setup,url,store)
    approve_confirm(setup,url,skus[0])
    items=setup.client.get(url).json()["items"]
    assert sum(i["state"]=="queued" for i in items)==1
    assert sum(i["state"]=="review" for i in items)==22
    assert store.posts==0 and not store.puts


def test_old_preview_requires_manual_refresh_without_auto_queue(setup):
    store=Store(wcda=[]);url=create(setup);ready(setup,url,store)
    with setup.jobs.db() as db:
        p=json.loads(db.execute("SELECT plan FROM jobs").fetchone()[0])
        p["dry_run"].pop("authorization")
        p["dry_run"]["dry_run_sha256"]=authorization.digest({k:v for k,v in p["dry_run"].items() if k!="dry_run_sha256"})
        db.execute("UPDATE jobs SET plan=?",(json.dumps(p),))
    assert setup.client.get(url).json()["items"][0]["needs_refresh"]
    assert setup.client.post(url+"/aprovar",json={"skus":["000123"]},headers=H).status_code==422
    assert setup.client.post(url+"/reprocessar",json={"skus":["000123"]},headers=H).status_code==200
    drain(setup,store)
    assert not setup.client.get(url).json()["items"][0]["needs_refresh"] and store.posts==0


def test_scope_and_main_endpoints_validate_on_the_server(setup):
    store=Store(images=[10],wcda=[])
    bad=setup.client.post("/api/v1/cadastro-api",data={"empresa":"choice","identificacao":"folder","escopo":"fotos"},
                          files={"arquivos":("000123.zip",package(gallery=True))},headers=H)
    assert bad.status_code==422 and "Escopo" in bad.json()["detail"]
    url=create(setup,escopo="gallery");drain(setup,store)
    item=setup.client.get(url).json()["items"][0]
    assert item["scope"]=={"gallery":True,"documents":False,"main":False} and item["state"]=="review"
    sha=item["dry_run"]["main_options"][0]["sha256"]
    # Main is not in the scope yet: the choice is refused by the backend, not only hidden in the page.
    assert setup.client.post(url+"/principal",json={"sku":"000123","sha256":sha},headers=H).status_code==422
    assert setup.client.post(url+"/escopo",json={"escopo":{"gallery":True,"documents":True}},headers=H).status_code==422
    changed=setup.client.post(url+"/escopo",json={"escopo":{"gallery":False,"documents":False,"main":True}},headers=H)
    assert changed.status_code==200 and changed.json()["items"][0]["state"]=="preview_queued"
    drain(setup,store)
    assert setup.client.get(url).json()["items"][0]["state"]=="awaiting_main"
    assert setup.client.post(url+"/principal",json={"sku":"000123","sha256":"0"*64},headers=H).status_code==422
    assert setup.client.post(url+"/principal",json={"sku":"000123","sha256":sha}).status_code==403  # CSRF
    assert setup.client.post(url+"/principal",json={"sku":"000123","sha256":sha},headers=H).status_code==200
    drain(setup,store)
    item=setup.client.get(url).json()["items"][0]
    assert item["state"]=="review" and item["main_choice"]["sha256"]==sha
    setup.state.user=setup.people.users["vera"]
    assert setup.client.post(url+"/escopo",json={"escopo":{"gallery":True,"documents":True,"main":False}},headers=H).status_code==403
    assert setup.client.post(url+"/principal",json={"sku":"000123","sha256":sha},headers=H).status_code==403
    assert store.posts==0 and not store.puts
