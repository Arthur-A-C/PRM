import io
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

from app.dependencies import get_current_auth
from app.main import app
from app.services.security import hash_secret


def test_claude_analysis_accepts_pdf_and_images_without_manual_specs(monkeypatch):
    received = {}
    def fake_generate(company, name, attachments, **kwargs):
        received.update(company=company, name=name, attachments=attachments, kwargs=kwargs)
        data = {"modelo": name, "nivel": "completo", "categoria": "Industrial", "subtitulo": "Teste",
                "tags": ["a", "b", "c", "d"], "features": [], "descricao": ["Teste"],
                "imagens": [], "pendencias": [], "especificacoes": []}
        return SimpleNamespace(dados=data, resultado=SimpleNamespace(avisos=[], pendencias=[], conferencia_fontes="ok"), ciclos=1)
    monkeypatch.setattr("app.routers.digitalizacao.gerar_datasheet_com_claude", fake_generate)
    app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(
        user=SimpleNamespace(role="gestor"), login_session=SimpleNamespace(csrf_hash=hash_secret("test-csrf")),
    )
    image = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(image, format="PNG")
    try:
        response = TestClient(app).post(
            "/api/v1/digitalizacao/analisar",
            data={"empresa": "choice", "codigo": "00123", "nome": "Produto", "informacoes_adicionais": ""},
            files=[("datasheet", ("orig.pdf", b"%PDF-1.4 test", "application/pdf")),
                   ("imagens", ("foto.png", image.getvalue(), "image/png"))],
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["modelo"] == "Produto"
        assert set(received["attachments"]) == {"orig.pdf", "img_01.png"}
    finally:
        app.dependency_overrides.clear()


def test_pdf_folder_and_package_survive_new_request(monkeypatch, tmp_path):
    monkeypatch.setenv("PRM_PRODUCT_STORAGE_ROOT", str(tmp_path))
    app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(
        user=SimpleNamespace(role="gestor"),
        login_session=SimpleNamespace(csrf_hash=hash_secret("test-csrf")),
    )
    client = TestClient(app)
    image = io.BytesIO()
    Image.new("RGB", (12, 24), "blue").save(image, format="PNG")
    try:
        response = client.post(
            "/api/v1/digitalizacao/gerar-datasheet",
            data={
                "empresa": "choice", "codigo": "00123", "nome": "Produto técnico",
                "analysis_json": json.dumps({"modelo": "Produto técnico", "nivel": "completo", "categoria": "Produto", "subtitulo": "Técnico", "tags": ["a", "b", "c", "d"], "features": [], "descricao": ["Teste"], "imagens": [], "pendencias": [], "especificacoes": [{"secao": "Geral"}, {"chave": "Tensão", "valor": "24 V"}]}),
                "rotations_json": "[90]", "size": "original", "quality": "90",
            },
            files=[("imagens", ("foto.png", image.getvalue(), "image/png"))],
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert response.status_code == 200, response.text
        assert response.content.startswith(b"%PDF-")
        run_id = response.headers["X-PRM-Run-ID"]
        saved = client.get(f"/api/v1/digitalizacao/execucoes/{run_id}")
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "draft"
        assert client.get(f"/api/v1/digitalizacao/execucoes/{run_id}/fotos/1").status_code == 200
        product = {
            "company": "choice", "cigam_code": "00123", "sku": "00123",
            "technical_name": "Produto técnico", "commercial_title": "Produto comercial",
        }
        export = b"ID,Tipo,SKU,Nome,Publicado,Categorias,Descri\xc3\xa7\xc3\xa3o curta,Descri\xc3\xa7\xc3\xa3o\r\n"
        blocked = client.post(
            "/api/v1/digitalizacao/cadastro/woocommerce/csv",
            data={"run_id": run_id, "product_json": json.dumps({**product, "validation_status": "approved"})},
            files={"export_file": ("choice.csv", export, "text/csv")},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert blocked.status_code == 409
        approval = client.post(
            f"/api/v1/digitalizacao/execucoes/{run_id}/aprovar",
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert approval.status_code == 200, approval.text
        final = client.post(
            "/api/v1/digitalizacao/finalizar",
            data={"run_id": run_id, "product_json": json.dumps(product)},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert final.status_code == 200, final.text
        assert final.json()["status"] == "validated"
        assert (tmp_path / "choice" / "00123" / "manifest.json").is_file()
        assert client.get(f"/api/v1/digitalizacao/execucoes/{run_id}").json()["status"] == "validated"
        package = client.get(f"/api/v1/digitalizacao/execucoes/{run_id}/pacote")
        assert package.status_code == 200
        assert package.content.startswith(b"PK")
        csv_response = client.post(
            "/api/v1/digitalizacao/cadastro/woocommerce/csv",
            data={"run_id": run_id, "product_json": json.dumps({**product, "validation_status": "approved"})},
            files={"export_file": ("choice.csv", export, "text/csv")},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert csv_response.status_code == 200, csv_response.text
        (tmp_path / "choice" / "00123" / "Fotos" / "00123_variante.jpg").write_bytes(b"corrompido")
        corrupted = client.post(
            "/api/v1/digitalizacao/cadastro/woocommerce/csv",
            data={"run_id": run_id, "product_json": json.dumps({**product, "validation_status": "approved"})},
            files={"export_file": ("choice.csv", export, "text/csv")},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert corrupted.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_pdf_only_can_be_generated_and_approved_but_not_packaged(monkeypatch, tmp_path):
    monkeypatch.setenv("PRM_PRODUCT_STORAGE_ROOT", str(tmp_path))
    app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(
        user=SimpleNamespace(role="gestor"),
        login_session=SimpleNamespace(csrf_hash=hash_secret("test-csrf")),
    )
    client = TestClient(app)
    analysis = {
        "modelo": "Produto sem foto", "nivel": "resumido", "categoria": "Produto",
        "subtitulo": "Teste", "tags": ["a", "b", "c", "d"], "features": [],
        "descricao": ["Informação técnica."], "imagens": [], "pendencias": [],
    }
    try:
        generated = client.post(
            "/api/v1/digitalizacao/gerar-datasheet",
            data={"empresa": "choice", "codigo": "00099", "nome": "Produto sem foto",
                  "analysis_json": json.dumps(analysis), "rotations_json": "[]"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert generated.status_code == 200, generated.text
        run_id = generated.headers["X-PRM-Run-ID"]
        record = client.get(f"/api/v1/digitalizacao/execucoes/{run_id}").json()
        assert record["image_count"] == 0
        assert record["preview_count"] >= 1
        assert client.get(f"/api/v1/digitalizacao/execucoes/{run_id}/previas/1").status_code == 200
        approved = client.post(f"/api/v1/digitalizacao/execucoes/{run_id}/aprovar",
                               headers={"X-CSRF-Token": "test-csrf"})
        assert approved.status_code == 200
        final = client.post(
            "/api/v1/digitalizacao/finalizar",
            data={"run_id": run_id, "product_json": json.dumps({
                "company": "choice", "cigam_code": "00099", "sku": "00099",
                "technical_name": "Produto sem foto", "commercial_title": "Produto sem foto",
            })},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert final.status_code == 422
        assert "foto principal" in final.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_claude_image_reference_and_pending_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("PRM_PRODUCT_STORAGE_ROOT", str(tmp_path))
    app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(
        user=SimpleNamespace(role="gestor"),
        login_session=SimpleNamespace(csrf_hash=hash_secret("test-csrf")),
    )
    image = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(image, format="PNG")
    analysis = {
        "modelo": "Produto com foto", "nivel": "resumido", "categoria": "Produto",
        "subtitulo": "Teste", "tags": ["a", "b", "c", "d"], "features": [],
        "descricao": ["Informação técnica."], "pendencias": ["Conferir a tensão."],
        "imagens": [{"arquivo": "img_01.png", "papel": "capa", "legenda": "Foto principal"}],
    }
    client = TestClient(app)
    try:
        generated = client.post(
            "/api/v1/digitalizacao/gerar-datasheet",
            data={"empresa": "choice", "codigo": "00111", "nome": "Produto com foto",
                  "analysis_json": json.dumps(analysis), "rotations_json": "[90]"},
            files=[("imagens", ("foto.png", image.getvalue(), "image/png"))],
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert generated.status_code == 200, generated.text
        run_id = generated.headers["X-PRM-Run-ID"]
        assert client.get(f"/api/v1/digitalizacao/execucoes/{run_id}").json()["pending"] == ["Conferir a tensão."]
        denied = client.post(f"/api/v1/digitalizacao/execucoes/{run_id}/aprovar",
                             headers={"X-CSRF-Token": "test-csrf"})
        assert denied.status_code == 422
        approved = client.post(f"/api/v1/digitalizacao/execucoes/{run_id}/aprovar",
                               data={"acknowledge_pending": "true"},
                               headers={"X-CSRF-Token": "test-csrf"})
        assert approved.status_code == 200, approved.text
    finally:
        app.dependency_overrides.clear()
