import io
import json
import zipfile

import pytest
from PIL import Image
from reportlab.pdfgen import canvas
from pypdf import PdfReader

from app.schemas.registration import RegistrationProduct
from app.services.digitalization_storage import create_draft, finalize_draft, load_run, run_file, validate_sku, verify_package
from app.services.registration_files import classify_files
from app.services.registration_package import process_image
from app.services.datasheet_choice import generate_choice_datasheet
from app.services.datasheet_sag import generate_sag_datasheet
from app.services.datasheet_portwell import generate_portwell_datasheet


def _pdf():
    output = io.BytesIO()
    page = canvas.Canvas(output)
    page.drawString(30, 30, "Produto")
    page.save()
    return output.getvalue()


def _image():
    output = io.BytesIO()
    Image.new("RGB", (10, 20), "red").save(output, format="PNG")
    return output.getvalue()


def _product(sku="00123"):
    return RegistrationProduct(company="choice", cigam_code=sku, sku=sku, technical_name="Produto técnico", commercial_title="Produto comercial")


def test_draft_persists_processed_images_pdf_and_exact_sku(monkeypatch, tmp_path):
    monkeypatch.setenv("PRM_PRODUCT_STORAGE_ROOT", str(tmp_path))
    processed = process_image(_image(), rotation=90, size=None)
    record = create_draft("choice", "00123", "Produto técnico", {"specs": ["x"]}, [processed], _pdf())
    assert load_run(record["run_id"])["sku"] == "00123"
    assert run_file(record["run_id"], "datasheet").read_bytes().startswith(b"%PDF-")
    saved = Image.open(tmp_path / "_runs" / record["run_id"] / "image_1.jpg")
    assert saved.size == (20, 10)


def test_rotation_changes_actual_image_pixels():
    source = Image.new("RGB", (20, 30), "blue")
    for x in range(20):
        for y in range(10):
            source.putpixel((x, y), (255, 0, 0))
    output = io.BytesIO()
    source.save(output, format="PNG")
    processed = Image.open(io.BytesIO(process_image(output.getvalue(), rotation=90, size=None, quality=100)))
    assert processed.size == (30, 20)
    assert processed.getpixel((25, 10))[0] > 190  # former top is now on the right
    assert processed.getpixel((5, 10))[2] > 150


def test_finalize_creates_folder_manifest_and_valid_zip(monkeypatch, tmp_path):
    monkeypatch.setenv("PRM_PRODUCT_STORAGE_ROOT", str(tmp_path))
    record = create_draft("choice", "00123", "Produto técnico", {"specs": ["x"]}, [process_image(_image(), rotation=90), process_image(_image())], _pdf())
    final = finalize_draft(record["run_id"], _product(), [("source_datasheet", "orig.pdf", _pdf())])
    folder = tmp_path / "choice" / "00123"
    assert final["status"] == "validated"
    assert folder.is_dir()
    assert (folder / "Fotos" / "00123_variante.jpg").is_file()
    assert (folder / "Fotos" / "00123_foto2.jpg").is_file()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["main_image_path"] == str(folder / "Fotos" / "00123_variante.jpg")
    assert manifest["ordered_images"] == ["Fotos/00123_variante.jpg", "Fotos/00123_foto2.jpg"]
    files = classify_files(folder)
    assert files["main_image"] == manifest["main_image_path"]
    assert files["gallery"] == [str(folder / "Fotos" / "00123_foto2.jpg")]
    with zipfile.ZipFile(run_file(record["run_id"], "package")) as archive:
        assert archive.testzip() is None
        assert "00123/manifest.json" in archive.namelist()
        assert "00123/Fotos/00123_variante.jpg" in archive.namelist()


def test_existing_folder_requires_explicit_new_version(monkeypatch, tmp_path):
    monkeypatch.setenv("PRM_PRODUCT_STORAGE_ROOT", str(tmp_path))
    first = create_draft("choice", "00123", "Produto técnico", {"x": 1}, [process_image(_image())], _pdf())
    finalize_draft(first["run_id"], _product(), [])
    second = create_draft("choice", "00123", "Produto técnico", {"x": 2}, [process_image(_image())], _pdf())
    with pytest.raises(FileExistsError):
        finalize_draft(second["run_id"], _product(), [])
    updated = finalize_draft(second["run_id"], _product(), [], new_version=True)
    assert updated["package_version"] == 2
    assert (tmp_path / "choice" / "00123" / "manifest.json").is_file()
    assert (tmp_path / "choice" / "_versions" / "00123" / second["run_id"] / "00123" / "manifest.json").is_file()


def test_modified_final_file_invalidates_package(monkeypatch, tmp_path):
    monkeypatch.setenv("PRM_PRODUCT_STORAGE_ROOT", str(tmp_path))
    record = create_draft("choice", "00123", "Produto técnico", {"x": 1}, [process_image(_image())], _pdf())
    finalize_draft(record["run_id"], _product(), [])
    assert verify_package(record["run_id"])["status"] == "validated"
    (tmp_path / "choice" / "00123" / "Fotos" / "00123_variante.jpg").write_bytes(b"alterado")
    with pytest.raises(ValueError, match="divergente"):
        verify_package(record["run_id"])


@pytest.mark.parametrize("sku", ["A/B", "CON", "00123.", " 00123", "A:B", "..", "A\\B"])
def test_invalid_sku_is_rejected_without_silent_rewrite(sku):
    with pytest.raises(ValueError):
        validate_sku(sku)


@pytest.mark.parametrize("company,generator", [
    ("CHOICE", lambda data, images: generate_choice_datasheet(data, images, codigo="00123")),
    ("SAG", lambda data, images: generate_sag_datasheet(data, images, codigo="00123")),
    ("PORTWELL", lambda data, images: generate_portwell_datasheet(data, images)),
])
def test_each_company_generates_its_own_pdf(company, generator):
    pdf = generator({"name": "Produto técnico", "model": "00123", "specs": []}, [process_image(_image())])
    text = " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages).upper()
    assert company in text
    assert pdf.startswith(b"%PDF-")
