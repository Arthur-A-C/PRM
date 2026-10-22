import base64
import json
import ssl
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.store_config import StoreSettings, secure_url
from app.services.store_connections import check_company, ConnectionHistory
from app.services.store_http import http_client, read_json, StoreAPIError
from app.services.registration_woo_api import WooClient, credentials_for


@pytest.fixture
def settings(tmp_path):
    values = {}
    for company in ("CHOICE", "SAG", "PORTWELL"):
        values.update({company+"_WC_URL":"https://example.test", company+"_WC_KEY":"ck_private",
                       company+"_WC_SECRET":"cs_private", company+"_WP_USER":"private_user",
                       company+"_WP_APP_PASSWORD":"private_password"})
    return StoreSettings(_env_file=None, **values, PRM_STORE_ORGANIZATION_ID="org",
                         PRM_STORE_STATUS_DIR=str(tmp_path))


def response(request):
    if "/wc/v3/" in request.url.path:
        if not request.headers.get("Authorization"):
            return httpx.Response(401, json={"message":"secret echo never returned"})
        return httpx.Response(200, json=[{"id":1, "sku":"00123",
            "meta_data":[{"key":"wcda_arquivos","value":[{"label":"Private document","url":"private"}]}]}])
    if request.url.path.endswith("users/me"):
        return httpx.Response(200, json={"id":1,"email":"private@example.test",
            "capabilities":{"read":True,"upload_files":True,"edit_products":False}})
    return httpx.Response(200, json=[])


@pytest.mark.parametrize("company", ["choice","sag","portwell"])
def test_authenticated_read_only_and_redacted(company, settings):
    calls = []
    def handler(request):
        calls.append(request)
        return response(request)
    result = check_company(company, settings, httpx.MockTransport(handler))
    assert result["woocommerce"]["authenticated"] and result["wordpress"]["authenticated"]
    assert result["wordpress"]["permissions"]["upload_files"] is True
    assert result["woocommerce"]["permissions"]["write_products"] is None
    assert result["wordpress"]["allowed_upload_formats"] is None
    assert result["woocommerce"]["wcda"]["sample_fields"] == [{"key":"wcda_arquivos","value_type":"list"}]
    assert all(r.method == "GET" and r.url.scheme == "https" for r in calls)
    assert len(calls) == 4
    expected = "Basic " + base64.b64encode(b"ck_private:cs_private").decode()
    assert calls[0].headers["Authorization"] == expected
    assert "Authorization" not in calls[1].headers
    assert calls[2].headers["Authorization"] == "Basic " + base64.b64encode(b"private_user:private_password").decode()
    assert all("ck_private" not in str(r.url) and "cs_private" not in str(r.url) for r in calls)
    serialized = json.dumps(result)
    for value in ("ck_private", "cs_private", "private_user", "private_password", "private@example.test", "Private document"):
        assert value not in serialized and value not in repr(settings)


def test_missing_credentials_make_no_requests():
    settings = StoreSettings(_env_file=None, CHOICE_WC_KEY="", CHOICE_WC_SECRET="",
                             CHOICE_WP_USER="", CHOICE_WP_APP_PASSWORD="")
    def no_request(_):
        pytest.fail("Request with missing credentials")
    result = check_company("choice", settings, httpx.MockTransport(no_request))
    assert result["woocommerce"]["status"] == "not_configured"
    assert result["wordpress"]["attempted"] is False


@pytest.mark.parametrize("status,code", [(401,"unauthorized"),(403,"forbidden"),(404,"not_found"),(429,"rate_limited"),(500,"http_error"),(302,"redirect")])
def test_http_errors_and_no_redirect_secret_leaks(settings, status, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"message":"ck_private cs_private private_password"},
                              headers={"Location":"https://evil.test/?secret=cs_private"})
    result = check_company("choice", settings, httpx.MockTransport(handler))
    assert result["woocommerce"]["status"] == code
    assert result["wordpress"]["status"] == code
    assert len(calls) == 2 and all(r.url.host == "example.test" for r in calls)
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["timeout","connection","tls"])
def test_transport_errors(settings, kind):
    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("SECRET", request=request)
        if kind == "tls":
            raise httpx.ConnectError("SECRET", request=request) from ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")
        raise httpx.ConnectError("SECRET", request=request)
    result = check_company("choice", settings, httpx.MockTransport(handler))
    assert result["woocommerce"]["status"] == {"timeout":"timeout","connection":"connection_error","tls":"tls_error"}[kind]
    assert "SECRET" not in json.dumps(result)


def test_public_response_is_not_authentication(settings):
    result = check_company("choice", settings, httpx.MockTransport(lambda _: httpx.Response(200,json=[])))
    assert result["woocommerce"]["status"] == "public_endpoint"
    assert not result["woocommerce"]["authenticated"]
    assert not result["wordpress"]["authenticated"]


def test_wordpress_auth_success_and_media_forbidden_distinct(settings):
    def handler(request):
        if request.url.path.endswith("/media"):
            return httpx.Response(403)
        return response(request)
    result = check_company("choice", settings, httpx.MockTransport(handler))
    assert result["wordpress"]["authenticated"]
    assert result["wordpress"]["status"] == "limited"
    assert result["wordpress"]["media"]["status"] == "forbidden"


@pytest.mark.parametrize("url", ["http://example.test","https://u:p@example.test","https://example.test?key=SECRET",
                                    "https://example.test/wp-admin","https://example.test:444","https://example.test/#secret"])
def test_https_origin_validation(url):
    with pytest.raises(ValueError):
        secure_url(url)


def test_html_and_large_responses(settings):
    for content in (b"<html>login</html>", b"x"*(4*1024**2+1)):
        result = check_company("choice", settings, httpx.MockTransport(lambda _:httpx.Response(200,content=content)))
        assert result["woocommerce"]["status"] == "invalid_response"


def test_exact_sku_detail_and_read_only_client(settings):
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/12"):
            return httpx.Response(200,json={"id":12,"sku":"00123"})
        return httpx.Response(200,json=[{"id":12,"sku":"00123"},{"id":13,"sku":"001234"}])
    client = WooClient(credentials_for("choice",settings),transport=httpx.MockTransport(handler))
    try:
        assert client.find_by_sku("00123")["id"] == 12
        assert client.product(12)["sku"] == "00123"
        assert not hasattr(client,"update") and not hasattr(client,"upload")
        with pytest.raises(ValueError):
            read_json(client.client, "https://evil.test")
    finally:
        client.close()
    assert all(r.method == "GET" for r in calls)


def test_status_persistence_and_organization_scope(settings):
    record = check_company("choice",settings,httpx.MockTransport(response))
    history = ConnectionHistory(settings)
    history.save("org", record)
    assert ConnectionHistory(settings).list("org")[0] == record
    assert history.list("other")[0]["checked_at"] is None
    assert "cs_private" not in history.path.read_bytes().decode("latin-1")


def test_manager_csrf_and_bound_organization(settings, monkeypatch):
    from app.routers import store_integrations
    from app.dependencies import get_current_auth
    from app.services.security import hash_secret
    app = FastAPI()
    app.include_router(store_integrations.router)
    auth = SimpleNamespace(user=SimpleNamespace(role="gestor",organization_id="org"),
                           login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_current_auth] = lambda:auth
    monkeypatch.setattr(store_integrations, "StoreSettings", lambda:settings)
    monkeypatch.setattr(store_integrations, "check_company", lambda c,s:check_company(c,s,httpx.MockTransport(response)))
    with TestClient(app) as client:
        assert client.post("/api/v1/integracoes/lojas/choice/testar").status_code == 403
        assert client.post("/api/v1/integracoes/lojas/choice/testar",headers={"X-CSRF-Token":"csrf"}).status_code == 200
        assert client.get("/api/v1/integracoes/lojas").json()["items"][0]["checked_at"]
        auth.user.role = "leitor"
        assert client.get("/api/v1/integracoes/lojas").status_code == 403
        auth.user.role = "gestor"; auth.user.organization_id = "other"
        assert client.get("/api/v1/integracoes/lojas").status_code == 403
        auth.user.organization_id = "org"; settings.organization_id = ""
        assert client.get("/api/v1/integracoes/lojas").status_code == 503


def test_legacy_env_aliases(monkeypatch):
    # Other tests load .env into process env; never compare/display a real key.
    for field in ("CHOICE_WC_KEY", "CHOICE_WC_SECRET", "CHOICE_WC_URL"):
        monkeypatch.delenv(field, raising=False)
    monkeypatch.setenv("PRM_WOO_CHOICE_KEY","legacy_key")
    monkeypatch.setenv("PRM_WOO_CHOICE_SECRET","legacy_secret")
    settings = StoreSettings(_env_file=None)
    matches = settings.credentials("choice","wc").username == "legacy_key"
    assert matches, "Legacy credential alias mismatch"


def test_future_download_plan_preserves_labels_without_writes(tmp_path):
    from app.services.store_registration_plan import prepare_files
    folder = tmp_path / "00123"; folder.mkdir()
    for filename in ("00123_variante.jpg","00123_foto2.jpg","00123_Datasheet.pdf",
                     "00123_Manual A.pdf","00123_Manual B.zip","00123_Certificado.pdf"):
        (folder/filename).write_bytes(b"fixture")
    before = sorted(p.name for p in folder.iterdir())
    plan = prepare_files(folder,"00123")
    assert [item["label"] for item in plan["downloads"]] == ["Datasheet","Manual A","Manual B","Certificado"]
    assert plan["main_image"].endswith("_variante.jpg") and len(plan["gallery"]) == 1
    assert plan["wcda_mapping"] == "candidate_contract_append"
    assert sorted(p.name for p in folder.iterdir()) == before
