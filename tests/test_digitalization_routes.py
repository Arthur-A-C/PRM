import io
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

from app.dependencies import get_current_auth
from app.main import app
from app.services.security import hash_secret


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
                "analysis_json": json.dumps({"name": "Produto técnico", "model": "Produto técnico", "specs": [{"secao": "Geral", "itens": [{"campo": "Tensão", "valor": "24 V"}]}]}),
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
