import io
import json
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pymupdf
import pytest

from app.config import Settings
from app.services import datasheet_batches as batches


def pdf():
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), "Industrial product - USB: 2")
        return doc.tobytes()


def package(csv_text="codigo,nome,empresa\n10001,Produto,Choice\n", files=None, bom=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("produtos.csv", ("\ufeff" if bom else "") + csv_text)
        for name, content in (files if files is not None else {"datasheets/10001.pdf": pdf()}).items():
            z.writestr(name, content)
    return stream.getvalue()


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, batch_storage_dir=str(tmp_path / "batches"))


@pytest.fixture
def store(settings):
    return batches.BatchStore(settings)


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_valid_csv_bom_delimiter(settings, delimiter):
    text = delimiter.join(["codigo", "nome", "empresa"]) + "\n" + delimiter.join(["10001", "Produto", "CHOICE"])
    items, documents = batches.parse_archive(package(text, bom=True), settings, delimiter)
    assert items[0]["status"] == "pending" and documents


@pytest.mark.parametrize("text,files,expected", [
    ("codigo,nome,empresa\n10001,P,Choice", {}, "não encontrado"),
    ("codigo,nome,empresa\n10001,P,Choice", {"10001.pdf": b"%PDF-broken"}, "corrompido"),
    ("codigo,nome,empresa\n10001,P,Outra", {}, "Empresa"),
    ("codigo,nome,empresa\n10001,,Choice", {}, "Nome"),
    ("codigo,nome,empresa\n../escape,P,Choice", {}, "proibidos"),
    ("codigo,nome,empresa,datasheet_original\n10001,P,Choice,../x.pdf", {}, "relativo"),
    ("codigo,nome,empresa,datasheet_original\n10001,P,Choice,C:/x.pdf", {}, "relativo"),
    ("codigo,nome,empresa\n10001,P,Choice", {"100010.pdf": pdf()}, "não encontrado"),
    ("codigo,nome,empresa\n10001,P,Choice", {"a/10001.pdf": pdf(), "b/10001.PDF": pdf()}, "Vários"),
])
def test_invalid_rows_do_not_abort(settings, text, files, expected):
    items, _ = batches.parse_archive(package(text, files), settings)
    assert items[0]["status"] == "invalid" and expected in items[0]["error"]


def test_duplicates_per_company_and_case_insensitive_exact_path(settings):
    text = "codigo,nome,empresa,datasheet_original\nabc,P,CHOICE,DATA/ABC.PDF\nABC,Q,Choice,\nabc,R,SAG,DATA/ABC.PDF"
    items, _ = batches.parse_archive(package(text, {"data/abc.pdf": pdf()}), settings)
    assert [i["status"] for i in items] == ["invalid", "invalid", "pending"]


@pytest.mark.parametrize("path", ["../escape.pdf", "/tmp/x.pdf", "C:/x.pdf", "a\\x.pdf", "a/../x.pdf", "a/NUL.pdf", "bad.exe"])
def test_rejects_unsafe_zip(settings, path):
    raw = package(files={path: pdf()})
    if "\\" in path:
        # Windows zipfile normalizes separators on creation; simulate a hostile
        # archive received from elsewhere, replacing both filename headers.
        raw = raw.replace(path.replace("\\", "/").encode(), path.encode())
    with pytest.raises(ValueError):
        batches.parse_archive(raw, settings)


def test_symlink_rejected(settings):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        info = zipfile.ZipInfo("source.pdf")
        info.external_attr = (0o120777 << 16)
        z.writestr(info, "somewhere")
    with pytest.raises(ValueError, match="Links"):
        batches.parse_archive(stream.getvalue(), settings)


@pytest.mark.parametrize("text", ["wrong,columns\n1,2", "codigo,nome,empresa\n1,P", "codigo,nome,empresa\n", "codigo,nome,empresa,codigo\n1,P,Choice,2"])
def test_bad_csv(settings, text):
    with pytest.raises(ValueError):
        batches.parse_archive(package(text), settings)


def test_zip_limits_and_missing_csv(settings):
    with pytest.raises(ValueError, match="descompactado"):
        batches.parse_archive(package(files={"x.pdf": b"x" * (2 * 1024**2)}),
                              settings.model_copy(update={"batch_expanded_mib": 1}))
    with pytest.raises(ValueError, match="compressão"):
        batches.parse_archive(package(files={"x.pdf": b"x" * 100000}), settings)
    with pytest.raises(ValueError, match="Quantidade"):
        batches.parse_archive(package(), settings.model_copy(update={"batch_max_files": 1}))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("x.pdf", pdf())
    with pytest.raises(ValueError, match="exatamente um CSV"):
        batches.parse_archive(stream.getvalue(), settings)


def test_durable_scope_claim_and_stale_result(store):
    batch = store.create(package(), "org", "owner")
    with pytest.raises(LookupError):
        store.detail(batch, "other", "owner")
    with pytest.raises(LookupError):
        store.detail(batch, "org", "other")
    store.enqueue(batch, "org", "owner", "model")
    # A fresh instance simulates web restart; queue survives.
    restarted = batches.BatchStore(store.settings)
    job = restarted.claim()
    assert job and restarted.claim() is None
    with pytest.raises(ValueError, match="já"):
        restarted.enqueue(batch, "org", "owner", "model")
    with store.db(True) as db:
        db.execute("UPDATE items SET lease=0")
    assert restarted.claim() is None
    assert store.detail(batch, "org", "owner")["counts"] == {"error": 1}
    restarted.finish(job, {"state": "done"})
    assert store.detail(batch, "org", "owner")["counts"] == {"error": 1}


def test_concurrency_atomic_claim(store):
    batch = store.create(package(), "org", "owner")
    store.enqueue(batch, "org", "owner", "model")
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = list(executor.map(lambda _: store.claim(), range(4)))
    assert sum(job is not None for job in jobs) == 1


def test_transient_backoff_and_manual_retry_only_failures(store):
    batch = store.create(package("codigo,nome,empresa\n10001,P,Choice\n10001,P,SAG"), "org", "owner")
    store.enqueue(batch, "org", "owner", "model")
    job = store.claim()
    store.finish(job, {"state": "error", "transient": True, "technical": "RateLimitError"})
    with store.db() as db:
        row = db.execute("SELECT * FROM items WHERE id=1").fetchone()
        assert row["state"] == "queued" and row["available"] > time.time()
    other = store.claim()
    store.finish(other, {"state": "review"})
    with store.db(True) as db:
        db.execute("UPDATE items SET available=0,attempts=2 WHERE id=1")
    retry = store.claim()
    store.finish(retry, {"state": "error", "transient": True})
    assert store.detail(batch, "org", "owner")["counts"] == {"error": 1, "review": 1}
    store.enqueue(batch, "org", "owner", "new-model", retry=True)
    assert store.detail(batch, "org", "owner")["counts"] == {"queued": 1, "review": 1}


def test_timeout_signaled_not_retried(store, monkeypatch):
    batch = store.create(package(), "org", "owner")
    store.enqueue(batch, "org", "owner", "model")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("worker", 900)
    monkeypatch.setattr(batches.subprocess, "run", timeout)
    assert batches.run_once(store)
    item = store.detail(batch, "org", "owner")["items"][0]
    assert item["state"] == "error" and item["technical"] == "ProductTimeout"


def test_cleanup_preserves_active_and_history(store):
    batch = store.create(package(), "org", "owner")
    with store.db(True) as db:
        db.execute("UPDATE batches SET updated=0")
    assert store.cleanup() == [batch] and store.folder(batch).exists()
    store.enqueue(batch, "org", "owner", "model")
    with store.db(True) as db:
        db.execute("UPDATE batches SET updated=0")
    assert store.cleanup(True) == []
    store.finish(store.claim(), {"state": "error"})
    with store.db(True) as db:
        db.execute("UPDATE batches SET updated=0")
    assert store.cleanup(True) == [batch]
    assert not store.folder(batch).exists()
    assert store.detail(batch, "org", "owner")["state"] == "expired"


@pytest.mark.parametrize("company", ["choice", "sag", "portwell"])
@pytest.mark.parametrize("mode", ["csv", "folder"])
def test_real_generator_with_mock_ai_and_downloads(store, monkeypatch, company, mode):
    import anthropic
    if mode == "folder":
        batch = store.create(folder_package({"10001/datasheet.pdf": pdf(), "10001/Fotos/principal.png": photo(),
                                             "10001/desenho.step": b"ISO-10303-21;"}), "org", "owner",
                             identification="folder", company=company)
    else:
        batch = store.create(package(f"codigo,nome,empresa\n10001,Produto,{company}"), "org", "owner")
    store.enqueue(batch, "org", "owner", "claude-sonnet-5-5")
    data = {"modelo":"Produto", "nivel":"completo", "categoria":"Produto", "subtitulo":"Industrial",
            "tags":["Industrial","USB","Produto","Documentação"], "features":[], "descricao":["Produto industrial."],
            "imagens":[], "especificacoes":[{"chave":"USB","valor":"2"}],
            "pendencias":["Revisar imagem ausente"], "revisao_ok":True}
    if mode == "folder":
        data["modelo"] = "10001"
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="tool_use", content=[
            SimpleNamespace(type="tool_use", name="entregar_datasheet", input=data, id="tool")])
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)))
    job = store.claim()
    batches.produce(store, job)
    result = json.loads((store.folder(batch) / job["token"] / "result.json").read_text(encoding="utf-8"))
    assert result["state"] == "review"
    store.finish(job, result)
    output, filename = store.output_file(batch, 1, "org", "owner")
    assert output.read_bytes().startswith(b"%PDF-") and filename == "10001.pdf"
    assert len(calls) == 2  # initial + review_ok, not duplicated by batch code
    stream = io.BytesIO()
    store.bundle(batch, "org", "owner", stream)
    with zipfile.ZipFile(stream) as archive:
        assert f"{company.upper()}/10001.pdf" in archive.namelist()
        assert "relatorio_processamento.csv" in archive.namelist()
        assert "erros.csv" in archive.namelist()
        if mode == "folder":
            assert archive.read(f"{company.upper()}/10001/fontes/Fotos/principal.png") == photo()
            assert archive.read(f"{company.upper()}/10001/fontes/desenho.step") == b"ISO-10303-21;"
            assert json.loads(archive.read(f"{company.upper()}/10001/analysis.json"))["especificacoes"]
    if mode == "folder":
        sent = calls[0]["messages"][0]["content"]
        assert any(block["type"] == "image" for block in sent)
        assert not any("desenho.step" in block.get("text", "") for block in sent)


def test_provider_error_sanitized(store, monkeypatch):
    import anthropic
    batch = store.create(package(), "org", "owner")
    store.enqueue(batch, "org", "owner", "model")
    def fail(**kwargs):
        raise anthropic.RateLimitError("SECRET", response=httpx.Response(429, request=httpx.Request("POST","https://example.test")), body={"secret":"SECRET"})
    monkeypatch.setattr(anthropic, "Anthropic", fail)
    job = store.claim()
    batches.produce(store, job)
    result = (store.folder(batch)/job["token"]/"result.json").read_text(encoding="utf-8")
    assert "SECRET" not in result and json.loads(result)["transient"]


def test_api_auth_csrf_and_owner_scope(settings, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.dependencies import get_current_auth, get_settings
    from app.routers.datasheet_batches import router
    from app.services.security import hash_secret
    app = FastAPI()
    monkeypatch.setenv("DATASHEET_MODEL", "model-mock")
    app.include_router(router)
    auth = SimpleNamespace(user=SimpleNamespace(id="owner", organization_id="org", role="gestor"),
                           login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_current_auth] = lambda: auth
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        assert client.post("/api/v1/digitalizacao/lotes", files={"arquivo":("x.zip",package())}).status_code == 403
        response = client.post("/api/v1/digitalizacao/lotes", headers={"X-CSRF-Token":"csrf"},
                               files={"arquivo":("x.zip",package())})
        assert response.status_code == 200, response.text
        identifier = response.json()["id"]
        assert client.get(f"/api/v1/digitalizacao/lotes/{identifier}").status_code == 200
        assert client.post(f"/api/v1/digitalizacao/lotes/{identifier}/iniciar").status_code == 403
        queued = client.post(f"/api/v1/digitalizacao/lotes/{identifier}/iniciar",
                             headers={"X-CSRF-Token":"csrf"})
        assert queued.status_code == 200 and queued.json()["counts"] == {"queued": 1}
        assert client.post(f"/api/v1/digitalizacao/lotes/{identifier}/iniciar",
                           headers={"X-CSRF-Token":"csrf"}).status_code == 422
        auth.user.id = "other"
        assert client.get(f"/api/v1/digitalizacao/lotes/{identifier}").status_code == 404
        assert client.get(f"/api/v1/digitalizacao/lotes/{identifier}/download").status_code == 404
        assert client.post(f"/api/v1/digitalizacao/lotes/{identifier}/reprocessar",
                           headers={"X-CSRF-Token":"csrf"}).status_code == 404

        response = client.post("/api/v1/digitalizacao/lotes", headers={"X-CSRF-Token":"csrf"},
                               data={"identificacao":"folder", "empresa":"choice"},
                               files={"arquivo":("x.zip",folder_package({"00123/datasheet.pdf":pdf()}))})
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["codigo"] == "00123"
        assert response.json()["counts"] == {"pending":1}
        response = client.post("/api/v1/digitalizacao/lotes", headers={"X-CSRF-Token":"csrf"},
                               data={"identificacao":"folder"},
                               files={"arquivo":("x.zip",folder_package({"00123/datasheet.pdf":pdf()}))})
        assert response.status_code == 422


def folder_package(files, csv_text=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        if csv_text is not None:
            archive.writestr("complemento.csv", csv_text)
    return stream.getvalue()


def photo():
    from PIL import Image
    stream = io.BytesIO()
    Image.new("RGB", (50, 50), "blue").save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize('prefix,root', [('', ''), ('Produtos/', ''), ('Products/', ''), ('Lote/Produtos/', 'Lote/Produtos')])
def test_folder_without_csv_preserves_sku_and_empty_folder(settings, prefix, root):
    raw = folder_package({prefix+'00119002000072/':b'', prefix+'00119002000072/datasheet.pdf':pdf(),
                          prefix+'00119002000072/Fotos/photo.png':photo(), prefix+'00119002000073/':b''})
    items, documents = batches.parse_archive(raw, settings, identification='folder', company='choice', root=root)
    assert [i['codigo'] for i in items] == ['00119002000072','00119002000073']
    assert items[0]['status']=='pending' and len(items[0]['assets'])==2
    assert items[0]['nome']=='00119002000072' and items[0]['warnings']
    assert items[1]['status']=='invalid' and 'vazia' in items[1]['error']
    assert len(documents)==2


def test_optional_csv_complements_exact_folder_and_selects_pdf(settings):
    raw=folder_package({'00123/a.pdf':pdf(),'00123/b.pdf':pdf()},
        'codigo,nome,empresa,descricao,datasheet_original\n00123,Produto,CHOICE,Descrição,b.pdf')
    items,_=batches.parse_archive(raw,settings,identification='folder',company='choice')
    assert items[0]['codigo']=='00123' and items[0]['nome']=='Produto'
    assert items[0]['descricao']=='Descrição' and items[0]['pdf']=='00123/b.pdf'
    assert items[0]['status']=='pending' and len(items[0]['assets'])==2


@pytest.mark.parametrize('csv_text',[
    'codigo,nome\n123,Produto', 'codigo,nome\n00123,Produto\n00123,Outro',
    'codigo,empresa\n00123,SAG', 'codigo,nome\n00123', 'nome\nProduto',
    'codigo,codigo\n00123,00123', 'codigo,datasheet_original\n00123,../fora.pdf',
])
def test_folder_csv_never_silently_changes_identity(settings,csv_text):
    raw=folder_package({'00123/datasheet.pdf':pdf()},csv_text)
    try:
        items,_=batches.parse_archive(raw,settings,identification='folder',company='choice')
    except ValueError:
        return
    assert items[0]['status']=='invalid'


@pytest.mark.parametrize('files,reason',[
    ({'abc/datasheet.pdf':pdf(),'ABC/original.pdf':pdf()},'duplicados'),
    ({'00123/Fotos/photo.png':photo()},'ausente'),
    ({'00123/a.pdf':pdf(),'00123/b.pdf':pdf()},'ambíguo'),
    ({'00123/datasheet.pdf':b'fake'},'PDF'),
    ({'00123/datasheet.pdf':pdf(),'00123/image.png':b'fake'},'Imagem'),
    ({'00123/datasheet.pdf':pdf(),'00123/manual.pdf':b''},'vazio'),
])
def test_folder_invalid_items_are_previewed(settings,files,reason):
    items,_=batches.parse_archive(folder_package(files),settings,identification='folder',company='choice')
    assert all(i['status']=='invalid' and reason in i['error'] for i in items)


@pytest.mark.parametrize('name',['00123/tool.exe','NUL/datasheet.pdf','../00123/datasheet.pdf',
                               '00123 /datasheet.pdf','datasheet.pdf'])
def test_folder_rejects_unsafe_unsupported_and_unassigned_files(settings,name):
    with pytest.raises(ValueError):
        batches.parse_archive(folder_package({name:pdf()}),settings,identification='folder',company='choice')


def test_folder_assets_durable_inventory_and_no_automatic_queue(store):
    raw=folder_package({'00123/datasheet.pdf':pdf(),'00123/Fotos/photo.png':photo(),
                       '00123/Documentos/manual.pdf':pdf(),'00123/3d/model.step':b'ISO-10303-21;'})
    batch=store.create(raw,'org','owner',identification='folder',company='choice')
    restarted=batches.BatchStore(store.settings)
    assert restarted.claim() is None
    item=restarted.detail(batch,'org','owner')['items'][0]
    assert item['state']=='pending' and len(item['assets'])==4
    assert len([a for a in item['assets'] if a['analyze']])==3
    assert all((store.folder(batch)/a['stored']).is_file() for a in item['assets'])
    assert all('key' not in a for a in item['assets'])
    with pytest.raises(ValueError):
        batches.parse_archive(raw,store.settings,identification='not-supported',company='choice')
