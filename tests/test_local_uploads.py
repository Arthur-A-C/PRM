"""Envios do navegador: caminhos relativos, blocos retomáveis, isolamento por usuário e uso pelos módulos."""
import io
import os
import time
import zipfile
from types import SimpleNamespace

import pymupdf
import pytest
from PIL import Image

from app.config import Settings
from app.services import image_resolution as tool
from app.services.local_uploads import MIB, OffsetMismatch, Uploads, clean_path, signature_ok

HEADERS = {"X-CSRF-Token": "csrf"}


def jpg(size=(800, 400), color=(200, 30, 30)):
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, "JPEG")
    return stream.getvalue()


def png(size=(300, 900)):
    stream = io.BytesIO()
    Image.new("RGBA", size, (0, 0, 0, 0)).save(stream, "PNG")
    return stream.getvalue()


def pdf():
    with pymupdf.open() as doc:
        doc.new_page().insert_text((40, 40), "Industrial product - USB: 2")
        return doc.tobytes()


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, upload_storage_dir=str(tmp_path / "uploads"),
                    batch_storage_dir=str(tmp_path / "batches"), upload_chunk_mib=1)


@pytest.fixture
def uploads(settings):
    return Uploads(settings)


def put_all(uploads, identifier, files, org="org", owner="owner"):
    for index, content in enumerate(files.values()):
        for start in range(0, len(content), MIB):
            uploads.write_chunk(identifier, org, owner, index, start, [content[start:start + MIB]])


def upload(uploads, profile, files, folder="Lote", org="org", owner="owner"):
    identifier = uploads.create(org, owner, profile, [{"caminho": k, "tamanho": len(v)} for k, v in files.items()], folder)
    put_all(uploads, identifier, files, org, owner)
    uploads.finish(identifier, org, owner)
    return identifier


# --- Caminhos e conteúdo ---------------------------------------------------------------------

@pytest.mark.parametrize("value", ["../x.jpg", "a/../b.jpg", "./a.jpg", "C:/Users/x.jpg", "c:x.jpg", "/etc/passwd.jpg",
                                   "\\\\servidor\\share\\x.jpg", "a//b.jpg", "CON.jpg", "lpt1/x.jpg", "a/b:c.jpg",
                                   "a/x?.jpg", "pasta./x.jpg", " a/x.jpg", "a\x00b.jpg", "", None])
def test_clean_path_rejects_traversal_drives_and_windows_names(value):
    with pytest.raises(ValueError):
        clean_path(value)


def test_clean_path_keeps_relative_structure():
    assert clean_path("Lote\\00119002000072\\Fotos\\foto 1.JPG") == "Lote/00119002000072/Fotos/foto 1.JPG"


def test_signature_must_match_extension():
    assert signature_ok(".jpg", jpg()[:4096]) and signature_ok(".png", png()[:4096]) and signature_ok(".pdf", pdf()[:4096])
    assert not signature_ok(".jpg", b"MZ\x90\x00 program")
    assert not signature_ok(".pdf", b"<html>")
    assert not signature_ok(".csv", b"a,b\x00\x00")
    assert not signature_ok(".exe", b"MZ")


@pytest.mark.parametrize("profile,files,error", [
    ("imagens", [{"caminho": "a.pdf", "tamanho": 10}], "não permitido"),
    ("lote", [{"caminho": "a.exe", "tamanho": 10}], "não permitido"),
    ("lote", [{"caminho": "a.pdf", "tamanho": 0}], "vazio"),
    ("lote", [{"caminho": "A/x.pdf", "tamanho": 5}, {"caminho": "a/X.PDF", "tamanho": 5}], "repetido"),
    ("imagens", [{"caminho": "Backup-fotos/a.jpg", "tamanho": 5}], "Backup-fotos"),
    ("lote", [{"caminho": "a.pdf", "tamanho": 1024 * MIB + 1}], "Arquivo acima do limite permitido de 1 GB."),
    ("outro", [{"caminho": "a.pdf", "tamanho": 5}], "não suportado"),
    ("lote", [], "ao menos"),
])
def test_create_validates_selection(uploads, profile, files, error):
    with pytest.raises(ValueError, match=error):
        uploads.create("org", "owner", profile, files, "Lote")


def test_browser_selection_accepts_files_up_to_one_gib(uploads):
    # Sizes are declared metadata here: nothing of this size is written or held in memory.
    uploads.create("org", "owner", "lote", [{"caminho": "a.pdf", "tamanho": 100 * MIB},
                                            {"caminho": "b.pdf", "tamanho": 1024 * MIB}], "Lote")


def test_create_limits_count_total_and_open_envios(tmp_path):
    small = Uploads(Settings(_env_file=None, upload_storage_dir=str(tmp_path / "u"), upload_max_files=2,
                             upload_max_mib=1, upload_max_open=1))
    with pytest.raises(ValueError, match="Mais de 2"):
        small.create("org", "owner", "lote", [{"caminho": f"{n}.pdf", "tamanho": 1} for n in range(3)])
    with pytest.raises(ValueError, match="limite"):
        small.create("org", "owner", "lote", [{"caminho": "a.pdf", "tamanho": MIB + 1}])
    small.create("org", "owner", "lote", [{"caminho": "a.pdf", "tamanho": 1}])
    with pytest.raises(ValueError, match="em aberto"):
        small.create("org", "owner", "lote", [{"caminho": "a.pdf", "tamanho": 1}])
    small.create("org", "other", "lote", [{"caminho": "a.pdf", "tamanho": 1}])  # limit is per user


# --- Envio em blocos e retomada --------------------------------------------------------------

def test_chunked_upload_resumes_and_preserves_folders(uploads):
    big = jpg() + b"\x00" * (2 * MIB + 123)  # signature at the start, 3 blocks of 1 MiB
    files = {"00119002000072/Fotos/frente.jpg": big, "00119002000072/datasheet.pdf": pdf()}
    identifier = uploads.create("org", "owner", "lote", [{"caminho": k, "tamanho": len(v)} for k, v in files.items()], "Lote")
    assert uploads.write_chunk(identifier, "org", "owner", 0, 0, [big[:MIB]]) == (MIB, False)
    # Connection dropped and the browser retried an old offset: the server tells where to continue.
    with pytest.raises(OffsetMismatch) as mismatch:
        uploads.write_chunk(identifier, "org", "owner", 0, 0, [big[:MIB]])
    assert mismatch.value.received == MIB
    with pytest.raises(ValueError, match="incompleto|ainda não"):
        uploads.finish(identifier, "org", "owner")
    status = uploads.status(identifier, "org", "owner")
    assert [f["recebido"] for f in status["arquivos"]] == [MIB, 0] and status["estado"] == "uploading"
    put_all_from = status["arquivos"][0]["recebido"]
    for start in range(put_all_from, len(big), MIB):
        uploads.write_chunk(identifier, "org", "owner", 0, start, [big[start:start + MIB]])
    uploads.write_chunk(identifier, "org", "owner", 1, 0, [files["00119002000072/datasheet.pdf"]])
    assert uploads.finish(identifier, "org", "owner")["estado"] == "ready"
    root, record = uploads.workspace(identifier, "org", "owner", "lote")
    assert (root / "00119002000072/Fotos/frente.jpg").read_bytes() == big
    assert record["folder"] == "Lote"
    with pytest.raises(ValueError, match="concluído"):
        uploads.write_chunk(identifier, "org", "owner", 0, 0, [b"x"])


def test_parallel_files_in_same_new_folder(uploads):
    """Regression: the browser sends 3 files at once; siblings in a folder not yet created must all land."""
    import threading
    files = {f"119002000072/Fotos/{n}.jpg": jpg((300 + n, 200)) for n in range(6)}
    for _ in range(5):
        identifier = uploads.create("org", "owner", "imagens", [{"caminho": k, "tamanho": len(v)} for k, v in files.items()])
        errors = []
        def send_one(index, content):
            try:
                uploads.write_chunk(identifier, "org", "owner", index, 0, [content])
            except Exception as exc:  # collected and asserted below
                errors.append(exc)
        threads = [threading.Thread(target=send_one, args=(i, c)) for i, c in enumerate(files.values())]
        [t.start() for t in threads]; [t.join() for t in threads]
        assert errors == [] and uploads.finish(identifier, "org", "owner")["completos"] == 6
        uploads.discard(identifier, "org", "owner")


def test_rejects_disguised_content_and_oversized_blocks(uploads):
    identifier = uploads.create("org", "owner", "imagens", [{"caminho": "foto.jpg", "tamanho": 10}])
    with pytest.raises(ValueError, match="maior"):
        uploads.write_chunk(identifier, "org", "owner", 0, 0, [b"\xff\xd8\xff" + b"0" * 20])
    with pytest.raises(ValueError, match="não corresponde"):
        uploads.write_chunk(identifier, "org", "owner", 0, 0, [b"MZ" + b"0" * 8])
    assert uploads.status(identifier, "org", "owner")["arquivos"][0]["recebido"] == 0  # partial removed
    with pytest.raises(LookupError):
        uploads.write_chunk(identifier, "org", "owner", 5, 0, [b"x"])


def test_envio_is_invisible_to_other_users_and_organizations(uploads):
    identifier = upload(uploads, "lote", {"10001/a.pdf": pdf()})
    for org, owner in [("org", "other"), ("other", "owner"), ("org", "../org/owner"), ("org", "")]:
        with pytest.raises(LookupError):
            uploads.status(identifier, org, owner)
        with pytest.raises(LookupError):
            uploads.discard(identifier, org, owner)
    for bad in ["../" + identifier, identifier.upper(), "x" * 32]:
        with pytest.raises(LookupError):
            uploads.status(bad, "org", "owner")
    assert uploads.status(identifier, "org", "owner")["estado"] == "ready"


def test_archive_matches_batch_zip_contract(uploads):
    content = {"00123/datasheet.pdf": pdf(), "00123/Fotos/a.jpg": jpg(), "complemento.csv": b"codigo\n00123\n"}
    identifier = upload(uploads, "lote", content, folder="Lote Outubro")
    raw, name = uploads.archive(identifier, "org", "owner", 100)
    assert name == "Lote Outubro.zip"
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert {n: archive.read(n) for n in archive.namelist()} == content
    with pytest.raises(ValueError, match="limite"):
        uploads.archive(identifier, "org", "owner", 0)
    images = upload(uploads, "imagens", {"a.jpg": jpg()})
    with pytest.raises(ValueError, match="outro módulo"):
        uploads.archive(images, "org", "owner", 100)


def test_purge_removes_only_expired(uploads):
    old = uploads.create("org", "owner", "lote", [{"caminho": "a.pdf", "tamanho": 5}])
    new = uploads.create("org", "owner", "lote", [{"caminho": "a.pdf", "tamanho": 5}])
    record = uploads.root / "org" / "owner" / old / "session.json"
    os.utime(record, (time.time() - 25 * 3600,) * 2)
    uploads.purge()
    with pytest.raises(LookupError):
        uploads.status(old, "org", "owner")
    assert uploads.status(new, "org", "owner")["id"] == new


# --- API --------------------------------------------------------------------------------------

@pytest.fixture
def client(settings, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.dependencies import get_current_auth, get_settings
    from app.routers import datasheet_batches, image_resolution, local_uploads
    from app.services.security import hash_secret
    monkeypatch.setenv("DATASHEET_MODEL", "model-mock")
    monkeypatch.delenv("PRM_IMAGE_TOOL_ROOTS", raising=False)
    app = FastAPI()
    for module in (local_uploads, datasheet_batches, image_resolution):
        app.include_router(module.router)
    auth = SimpleNamespace(user=SimpleNamespace(id="owner", organization_id="org", role="gestor"),
                           login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_current_auth] = lambda: auth
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        test_client.prm_user = auth.user
        yield test_client


def send(client, profile, files, folder="Lote"):
    body = {"perfil": profile, "pasta": folder, "arquivos": [{"caminho": k, "tamanho": len(v)} for k, v in files.items()]}
    created = client.post("/api/v1/envios", json=body, headers=HEADERS)
    assert created.status_code == 200, created.text
    identifier = created.json()["id"]
    for entry, content in zip(created.json()["arquivos"], files.values()):
        response = client.put(f"/api/v1/envios/{identifier}/arquivos/{entry['indice']}?inicio=0", content=content,
                              headers={**HEADERS, "Content-Type": "application/octet-stream"})
        assert response.status_code == 200 and response.json()["completo"], response.text
    assert client.post(f"/api/v1/envios/{identifier}/concluir", headers=HEADERS).status_code == 200
    return identifier


def test_api_requires_csrf_manager_and_reports_resume_offset(client):
    body = {"perfil": "lote", "arquivos": [{"caminho": "10001/a.pdf", "tamanho": 20}]}
    assert client.post("/api/v1/envios", json=body).status_code == 403
    assert client.post("/api/v1/envios", json={**body, "arquivos": [{"caminho": "../a.pdf", "tamanho": 20}]}, headers=HEADERS).status_code == 422
    identifier = client.post("/api/v1/envios", json=body, headers=HEADERS).json()["id"]
    url = f"/api/v1/envios/{identifier}/arquivos/0"
    assert client.put(url + "?inicio=0", content=b"%PDF-1.4 ", headers={"Content-Type": "application/octet-stream"}).status_code == 403
    assert client.put(url + "?inicio=0", content=b"%PDF-1.4 ", headers=HEADERS).json() == {"recebido": 9, "completo": False}
    resend = client.put(url + "?inicio=0", content=b"%PDF-1.4 ", headers=HEADERS)
    assert resend.status_code == 409 and resend.json()["recebido"] == 9
    assert client.put(url + "?inicio=9", content=b"x" * (2 * MIB), headers=HEADERS).status_code == 413
    assert client.post(f"/api/v1/envios/{identifier}/concluir", headers=HEADERS).status_code == 422
    client.prm_user.id = "other"
    assert client.get(f"/api/v1/envios/{identifier}").status_code == 404
    assert client.delete(f"/api/v1/envios/{identifier}", headers=HEADERS).status_code == 404
    client.prm_user.id = "owner"
    assert client.delete(f"/api/v1/envios/{identifier}", headers=HEADERS).status_code == 200
    assert client.get(f"/api/v1/envios/{identifier}").status_code == 404
    client.prm_user.role = "vendedor"
    assert client.post("/api/v1/envios", json=body, headers=HEADERS).status_code == 403


def test_batch_module_accepts_folder_envio_and_consumes_it(client):
    identifier = send(client, "lote", {"00123/datasheet.pdf": pdf(), "00123/foto.jpg": jpg()}, folder="Meu lote")
    client.prm_user.id = "other"  # someone else cannot start a batch with this envio
    assert client.post("/api/v1/digitalizacao/lotes", data={"identificacao": "folder", "empresa": "choice", "envio": identifier},
                       headers=HEADERS).status_code == 404
    client.prm_user.id = "owner"
    response = client.post("/api/v1/digitalizacao/lotes", data={"identificacao": "folder", "empresa": "choice", "envio": identifier},
                           headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["codigo"] == "00123"
    assert client.get(f"/api/v1/envios/{identifier}").status_code == 404  # batch keeps its own copy
    assert client.post("/api/v1/digitalizacao/lotes", data={"identificacao": "folder", "empresa": "choice"},
                       headers=HEADERS).status_code == 422  # neither ZIP nor envio


def wait(client, task):
    for _ in range(200):
        task = client.get(f"/api/v1/imagens/tarefas/{task['id']}").json()
        if task["status"] != "running":
            return task
        time.sleep(.05)
    raise AssertionError("tarefa não terminou")


def test_image_workspace_converts_copy_and_returns_zip(client, settings):
    originals = {"119002000072/foto1.jpg": jpg(), "119002000072/foto2.png": png(), "119002000073/Fotos/detalhe.jpg": jpg((2000, 1000))}
    identifier = send(client, "imagens", originals, folder="Produtos")
    base = f"/api/v1/imagens/envios/{identifier}"
    preview = client.post(f"{base}/previa", json={"tamanho": 1500}, headers=HEADERS).json()
    assert preview["pending"] == 3 and preview["root"] == "Produtos" and str(settings.upload_storage_dir) not in str(preview)
    assert client.post(f"{base}/processar", json={"tamanho": 1500}, headers=HEADERS).status_code == 422  # confirmation
    started = client.post(f"{base}/processar", json={"tamanho": 1500, "confirmar": True}, headers=HEADERS).json()
    assert started["root"] == "Produtos"
    client.prm_user.id = "other"
    assert client.get(f"/api/v1/imagens/tarefas/{started['id']}").status_code == 404
    assert client.post(f"{base}/previa", json={}, headers=HEADERS).status_code == 404
    assert client.get(f"{base}/resultado.zip").status_code == 404
    client.prm_user.id = "owner"
    task = wait(client, started)
    assert task["status"] == "finished" and task["done"] == 3
    result = client.get(f"{base}/resultado.zip")
    assert result.status_code == 200 and "Produtos" in result.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert sorted(archive.namelist()) == sorted(originals)
        for name in originals:
            assert Image.open(io.BytesIO(archive.read(name))).size == (1500, 1500)
    with zipfile.ZipFile(io.BytesIO(client.get(f"{base}/resultado.zip?backup=true").content)) as archive:
        assert archive.read("Backup-fotos/119002000072/foto1.jpg") == originals["119002000072/foto1.jpg"]
        assert not any(n.endswith(tool.JOURNAL) for n in archive.namelist())
    again = client.post(f"{base}/previa", json={"tamanho": 1500}, headers=HEADERS).json()
    assert again["already_converted"] == 3 and again["pending"] == 0
    assert client.delete(f"/api/v1/envios/{identifier}", headers=HEADERS).status_code == 200


def test_server_folder_mode_is_opt_in(client, tmp_path):
    folders = client.get("/api/v1/imagens/pastas").json()
    assert folders["enabled"] is False and folders["folders"] == []
    response = client.post("/api/v1/imagens/previa", json={"caminho": str(tmp_path)}, headers=HEADERS)
    assert response.status_code == 422 and "raízes" in response.json()["detail"]


def test_pages_load_picker_only_where_used():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from test_operations_workspace import render
    for title in ("Resolução de Imagens", "Publicação em Lote", "Cadastro via API", "Geração em Lote"):
        html = render(title)
        assert "/js/local-files.js" in html and "/css/local-files.css" in html and "data-local-files=" in html
    assert "/js/local-files.js" not in render("Digitalização")
    assert 'id="digitalizacao-imagens-pasta"' in render("Digitalização")


# --- Revisão de segurança --------------------------------------------------------------------

@pytest.mark.parametrize("names", [["Lote/café.pdf", "Lote/café.pdf"], ["10001/x.pdf", "10001/x.pdf/y.pdf"],
                                   ["A/B.pdf", "a/b.PDF"]])
def test_rejects_names_that_collide_on_disk(uploads, names):
    with pytest.raises(ValueError, match="repetido|mesmo nome"):
        uploads.create("org", "owner", "lote", [{"caminho": n, "tamanho": 5} for n in names])


def test_failed_write_rolls_back_to_last_complete_block(uploads):
    content = pdf()
    identifier = uploads.create("org", "owner", "lote", [{"caminho": "a.pdf", "tamanho": len(content)}])
    uploads.write_chunk(identifier, "org", "owner", 0, 0, [content[:10]])

    def broken():
        yield content[10:20]
        raise OSError(28, "No space left on device")
    with pytest.raises(ValueError, match="Falha ao gravar"):
        uploads.write_chunk(identifier, "org", "owner", 0, 10, broken())
    assert uploads.status(identifier, "org", "owner")["arquivos"][0]["recebido"] == 10
    uploads.write_chunk(identifier, "org", "owner", 0, 10, [content[10:]])
    assert uploads.finish(identifier, "org", "owner")["completos"] == 1
    root, _ = uploads.workspace(identifier, "org", "owner", "lote")
    assert (root / "a.pdf").read_bytes() == content


def test_purge_keeps_busy_workspace_and_removes_orphans(uploads):
    busy_id = upload(uploads, "imagens", {"a.jpg": jpg()})
    orphan = uploads.root / "org" / "owner" / ("f" * 32)
    (orphan / "files").mkdir(parents=True)
    old = time.time() - 25 * 3600
    for path in (uploads.root / "org" / "owner" / busy_id / "session.json", orphan):
        os.utime(path, (old, old))
    busy_files = uploads.root / "org" / "owner" / busy_id / "files"
    uploads.purge(busy=lambda files: files == busy_files)
    assert uploads.status(busy_id, "org", "owner")["estado"] == "ready" and not orphan.exists()
    os.utime(uploads.root / "org" / "owner" / busy_id / "session.json", (old, old))
    uploads.purge()
    with pytest.raises(LookupError):
        uploads.status(busy_id, "org", "owner")


def test_chunk_writes_refresh_activity(uploads):
    identifier = uploads.create("org", "owner", "lote", [{"caminho": "a.pdf", "tamanho": 20}])
    record = uploads.root / "org" / "owner" / identifier / "session.json"
    os.utime(record, (time.time() - 25 * 3600,) * 2)
    uploads.write_chunk(identifier, "org", "owner", 0, 0, [b"%PDF-1.4 "])
    uploads.purge()
    assert uploads.status(identifier, "org", "owner")["arquivos"][0]["recebido"] == 9


def test_simultaneous_result_downloads_do_not_share_files(client, settings):
    identifier = send(client, "imagens", {"a/foto.jpg": jpg()}, folder="Fotos")
    started = client.post(f"/api/v1/imagens/envios/{identifier}/processar", json={"confirmar": True}, headers=HEADERS).json()
    assert wait(client, started)["status"] == "finished"
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: client.get(f"/api/v1/imagens/envios/{identifier}/resultado.zip"), range(4)))
    for result in results:
        assert result.status_code == 200
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            assert archive.namelist() == ["a/foto.jpg"]
    session = Uploads(settings).root / "org" / "owner" / identifier
    assert not list(session.glob("resultado*"))  # each temporary ZIP removed after its download
