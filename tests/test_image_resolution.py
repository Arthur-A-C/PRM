"""Folder image resolution: temporary directories only, never real user files."""
import hashlib
import io
import json
import os
from pathlib import Path

import pytest
from PIL import Image

from app.services import image_resolution as tool
from app.services.registration_package import fit_square


@pytest.fixture(autouse=True)
def allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("PRM_IMAGE_TOOL_ROOTS", str(tmp_path))


def image(path, size=(800, 400), color=(200, 30, 30), fmt=None, mode="RGB"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path, fmt or {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[path.suffix.lower()])
    return path.read_bytes()


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def products(tmp_path):
    root = tmp_path / "Produtos"
    originals = {
        "119002000072/foto1.jpg": image(root / "119002000072/foto1.jpg"),
        "119002000072/foto2.png": image(root / "119002000072/foto2.png", (300, 900), (0, 0, 0, 0), mode="RGBA"),
        "119002000073/foto1.jpg": image(root / "119002000073/foto1.jpg", (2000, 1000)),
        "119002000073/Fotos/detalhe.webp": image(root / "119002000073/Fotos/detalhe.webp", (640, 480)),
    }
    (root / "119002000072/datasheet.pdf").write_bytes(b"%PDF-1.4")
    (root / "119002000072/3d.zip").write_bytes(b"PK")
    (root / "119002000073/desenho.step").write_text("ISO-10303")
    return root, originals


def run(root, **kwargs):
    task = tool.start_conversion(str(root), confirmed=True, background=False, **kwargs)
    return task.public()


# --- Identificação e prévia ------------------------------------------------------------------

def test_recursive_scan_only_images_and_never_backup(products):
    root, originals = products
    (root / tool.BACKUP / "119002000072").mkdir(parents=True)
    image(root / tool.BACKUP / "119002000072/antiga.jpg")
    assert tool.scan(root) == sorted(originals, key=str.casefold)
    assert tool.scan(root, recursive=False) == []
    summary = tool.preview(str(root))
    assert summary["images"] == 4 and summary["folders"] == 3 and summary["pending"] == 4
    assert summary["by_extension"] == {".jpg": 2, ".png": 1, ".webp": 1} and summary["space_ok"]


def test_symlinks_and_outside_roots_are_refused(products, tmp_path):
    root, _ = products
    outside = tmp_path.parent / ("fora-" + tmp_path.name)
    outside.mkdir()
    image(outside / "segredo.jpg")
    try:
        os.symlink(outside, root / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        try:
            import _winapi  # Windows junctions need no administrator rights
            _winapi.CreateJunction(str(outside), str(root / "link"))
        except (ImportError, OSError):
            pytest.skip("Sem permissão para criar links neste sistema.")
    assert not any(rel.startswith("link/") for rel in tool.scan(root))
    with pytest.raises(ValueError, match="raízes permitidas"):
        tool.resolve_root(str(outside))


def test_root_validation(products, tmp_path):
    root, _ = products
    with pytest.raises(ValueError, match="caminho completo"): tool.resolve_root("Produtos")
    with pytest.raises(ValueError, match="não encontrada"): tool.resolve_root(str(tmp_path / "nao-existe"))
    (root / tool.BACKUP).mkdir()
    with pytest.raises(ValueError, match="Backup-fotos"): tool.resolve_root(str(root / tool.BACKUP))
    listing = tool.list_folders(str(root))
    assert [f["name"] for f in listing["folders"]] == ["119002000072", "119002000073", tool.BACKUP]


# --- Redimensionamento -------------------------------------------------------------------------

@pytest.mark.parametrize("size,fmt", [((800, 400), "JPEG"), ((300, 900), "PNG"), ((3000, 3000), "WEBP"), ((100, 100), "JPEG")])
def test_fit_square_exact_size_proportion_white_background(size, fmt):
    source = io.BytesIO(); Image.new("RGB", size, (0, 0, 255)).save(source, fmt)
    result = Image.open(io.BytesIO(fit_square(source.getvalue(), size=1500, image_format=fmt)))
    assert result.size == (1500, 1500) and result.format == fmt
    rgb = result.convert("RGB")
    scale = min(1500 / size[0], 1500 / size[1])
    width, height = round(size[0] * scale), round(size[1] * scale)
    if width < 1500: assert rgb.getpixel((2, 750))[0] > 240  # white side band, no stretching
    if height < 1500: assert rgb.getpixel((750, 2))[0] > 240
    assert rgb.getpixel((750, 750))[2] > 200 and rgb.getpixel((750, 750))[0] < 60  # content kept, not deformed


def test_fit_square_flattens_transparency_and_rejects_corrupt():
    source = io.BytesIO(); Image.new("RGBA", (200, 200), (0, 0, 0, 0)).save(source, "PNG")
    assert Image.open(io.BytesIO(fit_square(source.getvalue(), image_format="PNG"))).convert("RGB").getpixel((750, 750)) == (255, 255, 255)
    with pytest.raises(Exception): fit_square(b"not an image")


# --- Conversão, backup e nomes ------------------------------------------------------------------

def test_conversion_replaces_in_place_and_moves_originals_to_backup(products):
    root, originals = products
    result = run(root)
    assert result["status"] == "finished" and (result["done"], result["skipped"], result["failed"]) == (4, 0, 0)
    for rel, data in originals.items():
        converted = Image.open(root / rel)
        assert converted.size == (1500, 1500) and converted.format == tool.FORMATS[Path(rel).suffix.lower()]
        assert (root / tool.BACKUP / rel).read_bytes() == data  # same name, same subfolder structure
    # Only one version per name in the original folders; documents untouched.
    assert sorted(p.name for p in (root / "119002000072").iterdir()) == ["3d.zip", "datasheet.pdf", "foto1.jpg", "foto2.png"]
    assert (root / "119002000072/datasheet.pdf").read_bytes() == b"%PDF-1.4"
    assert not list(root.rglob("*" + tool.TEMP))


def test_repeated_run_skips_converted_and_does_not_duplicate_backups(products):
    root, _ = products
    run(root)
    before = sorted(p.relative_to(root).as_posix() for p in (root / tool.BACKUP).rglob("*") if p.is_file())
    second = run(root)
    assert (second["done"], second["skipped"]) == (0, 4)
    assert sorted(p.relative_to(root).as_posix() for p in (root / tool.BACKUP).rglob("*") if p.is_file()) == before
    assert tool.preview(str(root))["already_converted"] == 4


def test_backup_name_collision_keeps_existing_and_uses_versioned_name(products):
    root, originals = products
    existing = image(root / tool.BACKUP / "119002000072/foto1.jpg", (50, 50), (0, 255, 0))
    run(root)
    assert (root / tool.BACKUP / "119002000072/foto1.jpg").read_bytes() == existing  # never overwritten
    assert (root / tool.BACKUP / "119002000072/foto1.backup-2.jpg").read_bytes() == originals["119002000072/foto1.jpg"]


def test_identical_existing_backup_is_reused(products):
    root, originals = products
    (root / tool.BACKUP / "119002000072").mkdir(parents=True)
    (root / tool.BACKUP / "119002000072/foto1.jpg").write_bytes(originals["119002000072/foto1.jpg"])
    run(root)
    assert not (root / tool.BACKUP / "119002000072/foto1.backup-2.jpg").exists()


def test_write_failure_keeps_original_and_continues_with_others(products, monkeypatch):
    root, originals = products
    real_replace = os.replace
    def failing(src, dst):
        if str(dst).endswith("foto2.png"): raise PermissionError("bloqueado")
        return real_replace(src, dst)
    monkeypatch.setattr(tool.os, "replace", failing)
    result = run(root)
    assert result["failed"] == 1 and result["done"] == 3 and result["errors"][0]["file"] == "119002000072/foto2.png"
    assert (root / "119002000072/foto2.png").read_bytes() == originals["119002000072/foto2.png"]
    assert not list((root / "119002000072").glob("*" + tool.TEMP)) and not list((root / "119002000072").glob(".*"))
    monkeypatch.setattr(tool.os, "replace", real_replace)
    retry = run(root)
    assert (retry["done"], retry["skipped"]) == (1, 3)
    assert not (root / tool.BACKUP / "119002000072/foto2.backup-2.png").exists()  # backup from the failed try reused


def test_corrupt_image_is_reported_without_touching_it(products):
    root, _ = products
    (root / "119002000073/quebrada.jpg").write_bytes(b"\xff\xd8 corrompida")
    result = run(root)
    assert result["failed"] == 1 and result["done"] == 4
    assert (root / "119002000073/quebrada.jpg").read_bytes() == b"\xff\xd8 corrompida"
    assert not (root / tool.BACKUP / "119002000073/quebrada.jpg").exists()


def test_interruption_between_backup_and_replace_is_resumed(products, monkeypatch):
    root, originals = products
    real_replace, calls = os.replace, {"n": 0}
    def crash(src, dst):
        if str(dst).endswith(".jpg") and TEMP_NAME(src) and calls["n"] == 0:
            calls["n"] += 1
            raise KeyboardInterrupt()  # process killed right before the atomic replace
        return real_replace(src, dst)
    TEMP_NAME = lambda src: str(src).endswith(tool.TEMP)
    monkeypatch.setattr(tool.os, "replace", crash)
    with pytest.raises(KeyboardInterrupt):
        tool.convert_one(root, "119002000072/foto1.jpg", tool.Journal(root), 1500)
    journal = json.loads((root / tool.BACKUP / tool.JOURNAL).read_text(encoding="utf-8"))
    assert journal["entries"]["119002000072/foto1.jpg"]["state"] == "replacing"
    assert (root / "119002000072/foto1.jpg").read_bytes() == originals["119002000072/foto1.jpg"]
    monkeypatch.setattr(tool.os, "replace", real_replace)
    result = run(root)
    assert result["done"] == 4 and Image.open(root / "119002000072/foto1.jpg").size == (1500, 1500)
    assert not (root / tool.BACKUP / "119002000072/foto1.backup-2.jpg").exists()


def test_interruption_after_replace_closes_entry_without_reconverting(products):
    root, _ = products
    run(root)
    journal = tool.Journal(root)
    journal.set("119002000072/foto1.jpg", state="replacing")  # crash after os.replace, before "done"
    converted = (root / "119002000072/foto1.jpg").read_bytes()
    result = run(root)
    assert result["done"] == 1 and result["skipped"] == 3
    assert (root / "119002000072/foto1.jpg").read_bytes() == converted


def test_stop_request_rolls_back_current_file(products):
    root, originals = products
    journal, event = tool.Journal(root), tool.threading.Event()
    event.set()
    with pytest.raises(InterruptedError):
        tool.convert_one(root, "119002000072/foto1.jpg", journal, 1500, event)
    assert (root / "119002000072/foto1.jpg").read_bytes() == originals["119002000072/foto1.jpg"]
    assert journal.entries["119002000072/foto1.jpg"]["state"] == "backed_up"


# --- Restauração -----------------------------------------------------------------------------

def test_restore_puts_originals_back_and_removes_backups(products):
    root, originals = products
    run(root)
    result = tool.start_restore(str(root), confirmed=True, background=False).public()
    assert result["done"] == 4 and result["failed"] == 0
    for rel, data in originals.items():
        assert (root / rel).read_bytes() == data and not (root / tool.BACKUP / rel).exists()
    assert tool.preview(str(root))["pending"] == 4  # can be converted again


def test_restore_never_overwrites_an_image_changed_after_conversion(products):
    root, _ = products
    run(root)
    image(root / "119002000072/foto1.jpg", (10, 10), (1, 2, 3))
    result = tool.start_restore(str(root), confirmed=True, background=False).public()
    assert result["failed"] == 1 and result["done"] == 3
    assert Image.open(root / "119002000072/foto1.jpg").size == (10, 10)
    assert (root / tool.BACKUP / "119002000072/foto1.jpg").exists()


# --- Segurança ----------------------------------------------------------------------------

def test_requires_confirmation_backup_and_space(products, monkeypatch):
    root, originals = products
    with pytest.raises(ValueError, match="Backup-fotos"):
        tool.start_conversion(str(root), backup=False, confirmed=True, background=False)
    with pytest.raises(ValueError, match="Confirme"):
        tool.start_conversion(str(root), background=False)
    monkeypatch.setattr(tool.shutil, "disk_usage", lambda _: tool.shutil._ntuple_diskusage(1, 1, 0))
    assert tool.preview(str(root))["space_ok"] is False
    with pytest.raises(ValueError, match="Espaço"):
        tool.start_conversion(str(root), confirmed=True, background=False)
    assert all((root / rel).read_bytes() == data for rel, data in originals.items())
    assert not (root / tool.BACKUP).exists()


def test_concurrent_runs_on_same_folder_are_refused(products):
    root, _ = products
    blocker = tool.Task("x", "convert", str(tool.resolve_root(str(root))))
    tool._tasks["x"] = blocker
    try:
        with pytest.raises(ValueError, match="andamento"):
            tool.start_conversion(str(root), confirmed=True, background=False)
    finally:
        tool._tasks.pop("x")


# --- API e página --------------------------------------------------------------------------

def test_api_preview_convert_status_and_restore(products):
    import time
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.dependencies import get_current_auth
    from app.routers import image_resolution
    from app.services.security import hash_secret
    root, originals = products
    app = FastAPI(); app.include_router(image_resolution.router)
    auth = SimpleNamespace(user=SimpleNamespace(role="gestor", id="u", organization_id="o"),
                           login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_current_auth] = lambda: auth
    headers = {"X-CSRF-Token": "csrf"}
    def wait(client, task):
        for _ in range(200):
            task = client.get(f"/api/v1/imagens/tarefas/{task['id']}").json()
            if task["status"] != "running": return task
            time.sleep(.05)
        raise AssertionError("tarefa não terminou")
    with TestClient(app) as client:
        body = {"caminho": str(root)}
        assert client.post("/api/v1/imagens/previa", json=body).status_code == 403  # CSRF
        preview = client.post("/api/v1/imagens/previa", json=body, headers=headers).json()
        assert preview["pending"] == 4 and preview["size"] == 1500
        assert client.post("/api/v1/imagens/processar", json=body, headers=headers).status_code == 422  # confirmation
        assert client.post("/api/v1/imagens/processar", json={**body, "confirmar": True, "mover_para_backup": False}, headers=headers).status_code == 422
        task = wait(client, client.post("/api/v1/imagens/processar", json={**body, "confirmar": True}, headers=headers).json())
        assert task["status"] == "finished" and task["done"] == 4
        assert Image.open(root / "119002000072/foto1.jpg").size == (1500, 1500)
        restored = wait(client, client.post("/api/v1/imagens/restaurar", json={**body, "confirmar": True}, headers=headers).json())
        assert restored["done"] == 4 and (root / "119002000072/foto1.jpg").read_bytes() == originals["119002000072/foto1.jpg"]
        folders = client.get("/api/v1/imagens/pastas").json()
        assert [f["path"] for f in folders["folders"]] == [str(Path(os.environ["PRM_IMAGE_TOOL_ROOTS"]).resolve())]
        auth.user.role = "vendedor"
        assert client.get("/api/v1/imagens/pastas").status_code == 403
        assert client.post("/api/v1/imagens/previa", json=body, headers=headers).status_code == 403


def test_page_registered_with_unique_ids_and_controls():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from test_operations_workspace import Elements, render
    html = render("Resolução de Imagens")
    nodes = Elements(html).nodes
    ids = [attrs["id"] for _, attrs in nodes if "id" in attrs]
    assert len(ids) == len(set(ids))
    assert {"res-path", "res-browse", "res-recursive", "res-size", "res-backup", "res-confirm", "res-start",
            "res-progress", "res-done", "res-skipped", "res-failed", "res-restore", "res-dialog"} <= set(ids)
    backup = next(attrs for _, attrs in nodes if attrs.get("id") == "res-backup")
    assert "checked" in backup and "disabled" in backup
    assert '<option value="1500" selected>' in html
    assert "/js/image-resolution.js" in html and "/css/image-resolution.css" in html
    assert "/js/image-resolution.js" not in render("Digitalização")
