"""SVG in folder image resolution: sanitized, rendered offline, always delivered as PNG on a white square."""
import io
import json
import zipfile

import pytest
from PIL import Image

from app.services import image_resolution as tool
from app.services.safe_svg import MAX_BYTES, render_svg, sanitize_svg
from test_local_uploads import settings, uploads, upload  # noqa: F401

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="red"/></svg>'
RED, WHITE = (255, 0, 0), (255, 255, 255)
# Typical Adobe Illustrator export: declaration, comment, DOCTYPE with internal entities, CSS classes, editor metadata.
ILLUSTRATOR = b'''<?xml version="1.0" encoding="utf-8"?>
<!-- Generator: Adobe Illustrator 24.0.0, SVG Export Plug-In . SVG Version: 6.00 Build 0)  -->
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd" [
\t<!ENTITY ns_extend "http://ns.adobe.com/Extensibility/1.0/">
\t<!ENTITY ns_svg "http://www.w3.org/2000/svg">
\t<!ENTITY ns_xlink "http://www.w3.org/1999/xlink">
]>
<svg version="1.1" xmlns:x="&ns_extend;" xmlns="&ns_svg;" xmlns:xlink="&ns_xlink;" x="0px" y="0px"
\t viewBox="0 0 100 50" xml:space="preserve">
<style type="text/css"><![CDATA[ .st0{fill:#00FF00;} ]]></style>
<metadata><x:sfw/></metadata>
<defs><linearGradient id="g0"><stop offset="0" stop-color="#0000FF"/></linearGradient>
<linearGradient id="g" xlink:href="#g0"/><symbol id="s" viewBox="0 0 10 10"><rect width="10" height="10" class="st0"/></symbol></defs>
<use xlink:href="#s" width="50" height="50"/><rect x="50" width="50" height="50" fill="url(#g)"/>
</svg>'''


def png(content):
    image = Image.open(io.BytesIO(content))
    return image.convert("RGB")


def write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def offline(monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        pytest.fail("Network access attempted while rendering SVG")
    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)


# 1, 5, 6: simple SVG -> PNG at the chosen size on white.
def test_simple_svg_becomes_png_at_the_chosen_size(tmp_path, offline):
    source = write(tmp_path, "0001/produto.svg", SVG)
    assert tool.convert_one(tmp_path, "0001/produto.svg", tool.Journal(tmp_path), 1500) == "done"
    with Image.open(source.with_suffix(".png")) as image:
        assert image.format == "PNG" and image.size == (1500, 1500)
        rgb = image.convert("RGB")
        assert rgb.getpixel((0, 0)) == WHITE and rgb.getpixel((750, 750)) == RED
    assert not source.exists()


# 2, 3: XML declaration, comments, DOCTYPE with internal entities, CSS classes, symbol/use and gradient inheritance.
def test_illustrator_export_is_sanitized_and_rendered(offline):
    markup, removed = sanitize_svg(ILLUSTRATOR)
    assert "<!DOCTYPE" not in markup and "<?xml" not in markup and "metadata" not in markup
    assert {"DOCTYPE", "declaração XML/instruções de processamento", "entidades internas expandidas"} <= set(removed)
    image = png(render_svg(ILLUSTRATOR, 1000))
    assert image.size == (1000, 500)
    assert image.getpixel((250, 250)) == (0, 255, 0)  # class from <style>, through <symbol>/<use>
    assert image.getpixel((750, 250)) == (0, 0, 255)  # gradient inherited through xlink:href="#g0"


def test_plain_declaration_and_svg_without_namespace(offline):
    image = png(render_svg(b'<?xml version="1.0"?>\n<svg width="10" height="10"><rect width="10" height="10" fill="red"/></svg>', 200))
    assert image.size == (200, 200) and image.getpixel((100, 100)) == RED


# 4: proportion kept, centred, white margins.
@pytest.mark.parametrize("width,height", [(400, 100), (100, 400)])
def test_svg_keeps_proportion_centred_on_white(tmp_path, width, height):
    body = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="{width}" height="{height}" fill="red"/></svg>'
    write(tmp_path, "a.svg", body.encode())
    tool.convert_one(tmp_path, "a.svg", tool.Journal(tmp_path), 1000)
    image = png((tmp_path / "a.png").read_bytes())
    assert image.size == (1000, 1000) and image.getpixel((500, 500)) == RED
    edge = (500, 100) if width > height else (100, 500)  # outside the 1000x250 band: white, not stretched
    assert image.getpixel(edge) == WHITE
    box = Image.eval(image.convert("L"), lambda v: 255 if v < 200 else 0).getbbox()
    assert abs((box[2] - box[0]) / (box[3] - box[1]) - width / height) < 0.02


# 7, 8: active and external content removed; nothing is executed, fetched or read from disk.
def test_script_events_and_javascript_are_removed(offline):
    body = (b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" onload="alert(1)">'
            b'<script>document.title="x"</script><a href="javascript:alert(1)"><rect width="10" height="10" fill="red" onclick="x()"/></a>'
            b'<foreignObject><iframe xmlns="http://www.w3.org/1999/xhtml" src="https://example.com"/></foreignObject>'
            b'<set attributeName="fill" to="blue"/></svg>')
    markup, removed = sanitize_svg(body)
    for word in ("script", "onload", "onclick", "javascript", "foreignObject", "iframe", "<set", "example.com"):
        assert word not in markup
    assert "eventos (on*)" in removed and "elemento script" in removed
    assert png(render_svg(body, 100)).getpixel((50, 50)) == RED


def test_external_and_local_references_are_never_loaded(tmp_path, offline):
    local = tmp_path / "secret.png"
    Image.new("RGB", (10, 10), (0, 0, 255)).save(local)
    body = (f'<?xml-stylesheet href="https://example.com/a.css"?><svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="100">'
            f'<style>@import url("https://example.com/x.css"); .a{{fill:url(https://example.com/p)}} .b{{fill:red}}</style>'
            f'<image width="100" height="100" xlink:href="{local.as_posix()}"/>'
            f'<image width="100" height="100" href="file:///{local.as_posix()}"/>'
            f'<image width="100" height="100" href="https://example.com/x.png"/>'
            f'<rect class="b" x="40" y="40" width="20" height="20" style="stroke:url(http://example.com/s)"/></svg>').encode()
    markup, removed = sanitize_svg(body)
    assert "example.com" not in markup and local.name not in markup
    image = png(render_svg(body, 100))
    assert image.getpixel((10, 10)) == WHITE  # the local blue file was not read
    assert image.getpixel((50, 50)) == RED


def test_embedded_raster_and_internal_references_are_kept():
    import base64
    raw = io.BytesIO()
    Image.new("RGB", (10, 10), (0, 0, 255)).save(raw, "PNG")
    body = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><image width="10" height="10" '
            f'href="data:image/png;base64,{base64.b64encode(raw.getvalue()).decode()}"/></svg>').encode()
    assert png(render_svg(body, 100)).getpixel((50, 50)) == (0, 0, 255)


@pytest.mark.parametrize("body", [
    b'<!DOCTYPE svg [<!ENTITY a SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
    b'<!DOCTYPE svg [<!ENTITY % p SYSTEM "https://example.com/x.dtd"> %p;]><svg xmlns="http://www.w3.org/2000/svg"/>',
    b'<!DOCTYPE svg [<!ENTITY a "&b;&b;"><!ENTITY b "&a;&a;">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"', b'<html><body/></html>', b'x' * (MAX_BYTES + 1),
], ids=["external-entity", "parameter-entity", "entity-loop", "truncated", "not-svg", "too-big"])
def test_dangerous_or_broken_svg_fails_alone(body, offline):
    with pytest.raises(ValueError):
        render_svg(body, 1000)


# 9, 10, 11, 13: a broken SVG fails alone; the batch continues; raster formats unchanged; folders preserved.
def test_batch_continues_after_a_broken_svg(tmp_path):
    raster = {}
    for ext, fmt in ((".jpg", "JPEG"), (".jpeg", "JPEG"), (".png", "PNG"), (".webp", "WEBP")):
        buffer = io.BytesIO()
        Image.new("RGB", (300, 150), RED).save(buffer, fmt)
        raster["A/B/foto" + ext] = buffer.getvalue()
    for rel, content in {**raster, "A/39929_variante.svg": ILLUSTRATOR, "A/quebrado.svg": b"<svg", "C/ok.svg": SVG}.items():
        write(tmp_path, rel, content)
    task = tool.convert_root(tmp_path, size=1000, confirmed=True, background=False)
    data = task.public()
    assert task.status == "finished" and data["processed"] == 7
    assert (data["done"], data["svg_converted"], data["failed"]) == (6, 2, 1)
    assert data["errors"][0]["file"] == "A/quebrado.svg" and data["errors"][0]["error"].startswith("Erro ao converter SVG")
    assert (tmp_path / "A/quebrado.svg").read_bytes() == b"<svg"  # original untouched
    assert (tmp_path / "A/39929_variante.png").is_file() and (tmp_path / "C/ok.png").is_file()
    for rel in raster:  # same names, same formats, in place
        with Image.open(tmp_path / rel) as image:
            assert image.size == (1000, 1000) and image.format == ("JPEG" if "jp" in rel else rel.rsplit(".", 1)[1].upper())
    assert sorted(p.relative_to(tmp_path / "Backup-fotos").as_posix() for p in (tmp_path / "Backup-fotos").rglob("*.*")
                  if p.name != tool.JOURNAL) == sorted([*raster, "A/39929_variante.svg", "C/ok.svg"])


# 12: manifest records SVG -> PNG with hashes; restore and resume keep working.
def test_manifest_records_svg_to_png_and_restore(tmp_path):
    write(tmp_path, "0001/39929_variante.svg", ILLUSTRATOR)
    journal = tool.Journal(tmp_path)
    tool.convert_one(tmp_path, "0001/39929_variante.svg", journal, 1000)
    entry = json.loads((tmp_path / "Backup-fotos" / tool.JOURNAL).read_text(encoding="utf-8"))["entries"]["0001/39929_variante.svg"]
    assert entry["source"] == "0001/39929_variante.svg" and entry["output"] == "0001/39929_variante.png"
    assert entry["converted_from"] == "svg" and entry["state"] == "done" and "DOCTYPE" in entry["sanitized"]
    assert entry["original_sha256"] and entry["output_sha256"] and not entry["renamed"]
    assert tool.summarize(tmp_path, size=1000)["already_converted"] == 1
    assert tool.convert_one(tmp_path, "0001/39929_variante.png", journal, 1000) == "skipped"
    out = tmp_path.parent / (tmp_path.name + ".zip")
    tool.result_archive(tmp_path, out)
    with zipfile.ZipFile(out) as archive:
        assert archive.namelist() == ["0001/39929_variante.png"]
    assert tool.restore_one(tmp_path, "0001/39929_variante.svg", journal) == "done"
    assert (tmp_path / "0001/39929_variante.svg").read_bytes() == ILLUSTRATOR and not (tmp_path / "0001/39929_variante.png").exists()


def test_existing_png_of_the_same_name_is_never_overwritten(tmp_path):
    svg = write(tmp_path, "foto.svg", SVG)
    existing = io.BytesIO()
    Image.new("RGB", (50, 50), (0, 0, 255)).save(existing, "PNG")
    write(tmp_path, "foto.png", existing.getvalue())
    task = tool.convert_root(tmp_path, size=1000, confirmed=True, background=False)
    assert task.failed == 0 and task.svg_converted == 1
    with Image.open(tmp_path / "foto.png") as image:  # the user's PNG: resized in place, still blue
        assert image.convert("RGB").getpixel((500, 500)) == (0, 0, 255)
    with Image.open(tmp_path / "foto-svg.png") as image:  # the SVG under a safe name
        assert image.convert("RGB").getpixel((500, 500)) == RED
    entry = tool.Journal(tmp_path).entries["foto.svg"]
    assert entry["output"] == "foto-svg.png" and entry["renamed"] and not svg.exists()
    assert tool.restore_one(tmp_path, "foto.svg", tool.Journal(tmp_path)) == "done"
    assert svg.read_bytes() == SVG and not (tmp_path / "foto-svg.png").exists() and (tmp_path / "foto.png").exists()


def test_changed_output_blocks_restore(tmp_path):
    write(tmp_path, "a.svg", SVG)
    journal = tool.Journal(tmp_path)
    tool.convert_one(tmp_path, "a.svg", journal, 1000)
    (tmp_path / "a.png").write_bytes(b"edited")
    with pytest.raises(ValueError):
        tool.restore_one(tmp_path, "a.svg", journal)
    assert (tmp_path / "a.png").read_bytes() == b"edited"


def test_interrupted_svg_finalization(tmp_path):
    write(tmp_path, "a.svg", SVG)
    journal = tool.Journal(tmp_path)
    tool.convert_one(tmp_path, "a.svg", journal, 1000)
    journal.set("a.svg", state="replacing")
    assert tool.convert_one(tmp_path, "a.png", journal, 1000) == "skipped"
    assert journal.entries["a.svg"]["state"] == "done"


# 14: preview and upload count SVG as an accepted image; a broken SVG never blocks the envio.
def test_preview_counts_svg_as_image(tmp_path):
    write(tmp_path, "A/foto.jpg", b"\xff\xd8\xff")
    write(tmp_path, "A/desenho.svg", ILLUSTRATOR)
    write(tmp_path, "A/manual.pdf", b"%PDF-1.4")
    summary = tool.summarize(tmp_path, size=1500)
    assert summary["images"] == 2 and summary["pending"] == 2 and summary["by_extension"] == {".jpg": 1, ".svg": 1}


def test_svg_upload_accepted_even_when_not_renderable(uploads):
    assert upload(uploads, "imagens", {"0001/produto.svg": ILLUSTRATOR, "0001/quebrado.svg": b"<svg"})
