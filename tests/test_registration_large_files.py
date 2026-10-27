import io
import hashlib
import zipfile
from pathlib import Path
import pytest
from app.services.upload_limits import check_size, file_hash, copy_bounded, MIB, CHUNK
from app.services.store_publish import file_info, PublishSettings
from app.services.store_registration_jobs import extract_files
from test_store_registration_roles import setup  # noqa: F401  (real identities + queue, mocked stores)
from test_store_removal_production import people  # noqa: F401

@pytest.mark.parametrize('size',[1,100*MIB,1024*MIB-1,1024*MIB])
def test_size_boundary(size): check_size(size)

def test_oversize():
    with pytest.raises(ValueError,match='1 GB'): check_size(1024*MIB+1)

def test_hash_streams(tmp_path,monkeypatch):
    p=tmp_path/'doc.pdf';p.write_bytes(b'%PDF-1.4'+b'x'*(2*CHUNK))
    monkeypatch.setattr(Path,'read_bytes',lambda *a:pytest.fail('whole-file read'))
    assert file_info(p)['bytes']==2*CHUNK+8
    assert file_info(p)['sha256']==file_hash(p)

def test_copy_is_bounded():
    class Reader(io.BytesIO):
        def read(self,n=-1):
            assert 0<n<=CHUNK
            return super().read(n)
    out=io.BytesIO();assert copy_bounded(Reader(b'abc'),out,3)==3
    with pytest.raises(ValueError):copy_bounded(Reader(b'abcd'),io.BytesIO(),3)

def test_zip_stream_extraction(tmp_path,monkeypatch):
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as z:z.writestr('000123/datasheet.pdf',b'%PDF-1.4')
    monkeypatch.setattr(zipfile.ZipFile,'read',lambda *a,**k:pytest.fail('whole-member read'))
    extract_files(raw,tmp_path,identification='folder',archive_name='000123.zip')
    assert (tmp_path/'000123/datasheet.pdf').exists()

def test_policy_unified(monkeypatch):
    monkeypatch.setenv('PRM_UPLOAD_MAX_FILE_MIB','1024')
    assert PublishSettings(_env_file=None).max_file_mib==1024


# --- Mensagens, pacote e limpeza ---------------------------------------------------------------------

def test_exact_messages():
    from app.services.upload_limits import check_package
    with pytest.raises(ValueError) as error:
        check_size(1024 * MIB + 1)
    assert str(error.value) == 'Arquivo acima do limite permitido de 1 GB.'
    check_package(2048 * MIB, 2048)
    with pytest.raises(ValueError, match='Pacote .* acima do limite permitido de 2 GB. Cada arquivo pode ter até 1 GB'):
        check_package(2048 * MIB + 1, 2048)


def small_zip(files):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w', zipfile.ZIP_STORED) as z:
        for name, size in files.items():
            z.writestr(name, b'%PDF-1.4' + b'x' * (size - 8))
    raw.seek(0)
    return raw


def test_package_is_limited_separately_from_each_file(tmp_path):
    # Scaled down (1 MiB per file): files at the per-file limit travel together in one package.
    extract_files(small_zip({'000123/a.pdf': MIB, '000123/b.pdf': MIB}), tmp_path / 'ok', identification='folder',
                  archive_name='000123.zip', limit_mib=1, package_mib=3)
    assert (tmp_path / 'ok/000123/a.pdf').stat().st_size == MIB and (tmp_path / 'ok/000123/b.pdf').exists()
    with pytest.raises(ValueError, match='Arquivo acima do limite permitido de 1,0 MB'):
        extract_files(small_zip({'000123/a.pdf': MIB + 1}), tmp_path / 'big', identification='folder',
                      archive_name='000123.zip', limit_mib=1, package_mib=3)
    with pytest.raises(ValueError, match='Pacote'):
        extract_files(small_zip({'000123/a.pdf': MIB, '000123/b.pdf': MIB}), tmp_path / 'pkg', identification='folder',
                      archive_name='000123.zip', limit_mib=1, package_mib=1)


def test_failed_import_leaves_no_temporary_folder(tmp_path):
    from app.services.store_registration_jobs import Jobs
    from app.services.store_config import StoreSettings
    jobs = Jobs(PublishSettings(_env_file=None, storage_dir=str(tmp_path / 'q')))
    settings = StoreSettings(_env_file=None, CHOICE_WC_URL='https://choicetech.com.br', CHOICE_WC_KEY='ck', CHOICE_WC_SECRET='cs',
                             CHOICE_WP_USER='u', CHOICE_WP_APP_PASSWORD='p', PRM_STORE_ORGANIZATION_ID='org')
    before = {p.name for p in (tmp_path / 'q').iterdir()}
    with pytest.raises(ValueError):
        jobs.create('choice', 'org', 'owner', None, small_zip({'000123/a.pdf': 100, '000123/virus.exe': 100}), settings,
                    identification='folder', archive_name='000123.zip')
    assert jobs.policy.max_file_mib == 1024
    jobs.policy.max_file_mib = 1  # oversize after extraction started: the half-written folder must go
    with pytest.raises(ValueError, match='1,0 MB'):
        jobs.create('choice', 'org', 'owner', None, small_zip({'000123/a.pdf': 100, '000123/b.pdf': 2 * MIB}), settings,
                    identification='folder', archive_name='000123.zip')
    assert {p.name for p in (tmp_path / 'q').iterdir()} == before


# --- Rota: tamanho lido do arquivo em disco, nunca do conteúdo inteiro ----------------------------------

def test_route_rejects_oversized_package_without_reading_it_into_memory(setup, monkeypatch):
    from starlette.datastructures import UploadFile
    from app.config import Settings, get_settings
    setup.client.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, upload_max_mib=1)
    monkeypatch.setattr(setup.jobs, 'create', lambda *a, **k: pytest.fail('package must be refused before any import'))
    monkeypatch.setattr(UploadFile, 'read', lambda *a, **k: pytest.fail('ZIP read entirely into memory'))
    response = setup.client.post('/api/v1/cadastro-api', headers={'X-CSRF-Token': 'csrf'},
                                 data={'empresa': 'choice', 'identificacao': 'folder', 'escopo': 'gallery,documents'},
                                 files={'arquivos': ('000123.zip', small_zip({'000123/a.pdf': 2 * MIB}).getvalue(), 'application/zip')})
    assert response.status_code == 422, response.text
    assert 'Pacote (ZIP ou pasta) acima do limite permitido de 1,0 MB' in response.json()['detail']


# --- Limite real da loja (WordPress/PHP) e recusas legíveis --------------------------------------------

def test_store_limit_blocks_in_the_dry_run_and_unknown_limit_warns():
    from app.services.store_registration_plan import store_limit_check
    dry = {"images": {"actions": [{"name": "foto.jpg", "bytes": 300 * MIB, "action": "upload"},
                                  {"name": "antiga.jpg", "bytes": 900 * MIB, "action": "already_linked"}]},
           "documents": {"actions": [{"label": "Desenho 3D", "name": "3d.zip", "bytes": 64 * MIB, "action": "add"}]}, "blockers": []}
    assert store_limit_check(dry, 128 * MIB) == []
    assert dry["store_upload_limit"] == 128 * MIB and len(dry["blockers"]) == 1  # the already linked file is never sent
    assert dry["blockers"][0].startswith("foto.jpg tem 300,0 MB, acima do limite de upload da loja (128,0 MB). O PRM aceita até 1 GB")
    unknown = {"images": {"actions": dry["images"]["actions"]}, "documents": {"actions": []}, "blockers": []}
    assert "não informou" in store_limit_check(unknown, None)[0] and unknown["blockers"] == []


@pytest.mark.parametrize("answer,expected", [
    ({"environment": {"max_upload_size": 67108864}}, 67108864),
    ({"environment": {}}, None),
])
def test_store_limit_is_read_only_from_system_status(answer, expected):
    import httpx
    from app.services.registration_woo_api import WooClient, WooCredentials
    seen = []
    def handle(request):
        seen.append((request.method, request.url.path, request.url.params.get("_fields")))
        return httpx.Response(200, json=answer)
    woo = WooClient(WooCredentials("https://choicetech.com.br", "ck", "cs"), transport=httpx.MockTransport(handle))
    assert woo.upload_limit() == expected
    assert seen == [("GET", "/wp-json/wc/v3/system_status", "environment")]


def test_store_without_permission_for_system_status_gives_no_limit():
    import httpx
    from app.services.registration_woo_api import WooClient, WooCredentials
    woo = WooClient(WooCredentials("https://choicetech.com.br", "ck", "cs"),
                    transport=httpx.MockTransport(lambda r: httpx.Response(403, json={})))
    assert woo.upload_limit() is None


@pytest.mark.parametrize("response,size_reason", [
    (dict(status_code=413, text="<html>413 Request Entity Too Large</html>", headers={"content-type": "text/html"}), True),
    (dict(status_code=500, json={"code": "rest_upload_unknown_error", "message": "excede a diretiva upload_max_filesize"}), True),
    (dict(status_code=400, json={"code": "rest_upload_file_too_big", "message": "too big"}), True),
    (dict(status_code=403, json={"code": "rest_cannot_create", "message": "Sem permissão"}), False),
])
def test_store_refusal_is_readable_and_never_network(response, size_reason):
    import httpx
    from app.services.store_publish import store_refusal
    message = store_refusal(httpx.Response(**response), 300 * MIB)
    assert ("por tamanho" in message) == size_reason and f"HTTP {response['status_code']}" in message
    assert "DNS" not in message and "comunicação" not in message and "<html>" not in message


# --- Gateway e interface ------------------------------------------------------------------------------

def test_gateway_accepts_one_gib_plus_multipart_margin():
    import re
    conf = (Path(__file__).parents[1] / "docker/nginx.conf").read_text(encoding="utf-8")
    size = re.search(r"client_max_body_size\s+(\d+)m;", conf)
    assert size and int(size.group(1)) * MIB > 1024 * MIB  # strictly above 1 GiB: room for multipart overhead
    assert "proxy_request_buffering off;" in conf  # streamed to the API, no second copy in the gateway
    for key in ("client_body_timeout", "proxy_read_timeout", "proxy_send_timeout"):
        value = re.search(rf"{key}\s+(\d+)s;", conf)
        assert value and int(value.group(1)) >= 1800, key


def test_registration_screen_shows_the_limit():
    root = Path(__file__).parents[1]
    template = (root / "app/templates/store_registration.html").read_text(encoding="utf-8")
    script = (root / "app/static/js/store-registration.js").read_text(encoding="utf-8")
    assert "Limite: até 1 GB por arquivo" in template
    assert "100 MB" not in template + script and "104857600" not in template + script
