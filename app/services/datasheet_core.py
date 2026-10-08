from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import os
import re

from PIL import Image
from reportlab.lib.colors import HexColor, Color, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


W, H = A4
ML = 18 * mm
MR = 18 * mm
CW = W - ML - MR
HEADER_H = 39
FOOTER_H = 38


@dataclass(frozen=True)
class Theme:
    brand: str
    primary: str
    accent: str
    dark: str
    text: str
    muted: str
    light: str
    line: str
    cover_bg: str
    cover_text: str
    cover_muted: str
    header_bg: str
    header_text: str
    footer_bg: str
    footer_text: str
    section_bg: str
    section_text: str
    logo_path: str | None = None
    cover_logo_bg: str | None = None
    footer_lines: tuple[str, ...] = ()

    def color(self, attr: str) -> Color:
        return HexColor(getattr(self, attr))


def _safe_code(value: str) -> str:
    value = (value or "produto").strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value.strip("_-") or "produto"


def _as_pairs(items: Iterable[Any] | None) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in items or []:
        if isinstance(item, dict):
            title = str(item.get("titulo") or item.get("title") or "").strip()
            body = str(item.get("descricao") or item.get("body") or "").strip()
            if title or body:
                result.append((title, body))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            result.append((str(item[0]), str(item[1])))
        elif item:
            result.append(("", str(item)))
    return result


def _as_specs(items: Iterable[Any] | None) -> list[tuple[str, ...]]:
    result: list[tuple[str, ...]] = []
    for item in items or []:
        if isinstance(item, dict):
            if item.get("secao") or item.get("section"):
                result.append((str(item.get("secao") or item.get("section")),))
            else:
                key = item.get("campo") or item.get("key")
                value = item.get("valor") if "valor" in item else item.get("value")
                if key is not None and value not in (None, ""):
                    result.append((str(key), str(value)))
        elif isinstance(item, (list, tuple)):
            if len(item) == 1:
                result.append((str(item[0]),))
            elif len(item) >= 2 and item[1] not in (None, ""):
                result.append((str(item[0]), str(item[1])))
    return result


def normalize_product(product: dict[str, Any]) -> dict[str, Any]:
    code = str(product.get("codigo") or product.get("code") or product.get("model") or "").strip()
    model = str(product.get("model") or code).strip()
    images = product.get("images") or {}
    if not isinstance(images, dict):
        images = {}

    normalized = {
        "codigo": code or model,
        "model": model or code,
        "categoria": str(product.get("categoria") or product.get("category") or "Produto industrial").strip(),
        "subtitulo": str(product.get("subtitulo") or product.get("subtitle") or "").strip(),
        "tags": [str(x) for x in (product.get("tags") or []) if x],
        "features": [str(x) for x in (product.get("features") or product.get("destaques") or []) if x],
        "specs": _as_specs(product.get("specs") or product.get("especificacoes")),
        "intro": str(product.get("intro") or product.get("descricao") or "").strip(),
        "beneficios": _as_pairs(product.get("beneficios")),
        "aplicacoes": _as_pairs(product.get("aplicacoes")),
        "slogan": str(product.get("slogan") or "").strip(),
        "main_image": product.get("main_image") or images.get("main"),
        "gallery": list(product.get("gallery") or images.get("gallery") or []),
        "views": list(product.get("views") or images.get("views") or []),
        "footer_lines": tuple(product.get("footer_lines") or ()),
    }
    return normalized


def _draw_text_lines(c: canvas.Canvas, text: str, x: float, y: float, max_width: float,
                     font: str, size: float, color: Color, leading: float | None = None,
                     max_lines: int | None = None) -> float:
    if not text:
        return y
    c.setFont(font, size)
    c.setFillColor(color)
    leading = leading or size * 1.35
    lines = simpleSplit(str(text), font, size, max_width)
    if max_lines is not None:
        lines = lines[:max_lines]
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def _image_reader(path: str | os.PathLike[str]) -> ImageReader | None:
    try:
        p = Path(path)
        if not p.exists():
            return None
        return ImageReader(str(p))
    except Exception:
        return None


def draw_contain_image(c: canvas.Canvas, path: str | None, x: float, y: float,
                       box_w: float, box_h: float, pad: float = 8,
                       bg: Color | None = white, border: Color | None = None,
                       radius: float = 8) -> bool:
    if bg is not None:
        c.setFillColor(bg)
        c.roundRect(x, y, box_w, box_h, radius, fill=1, stroke=0)
    if border is not None:
        c.setStrokeColor(border)
        c.setLineWidth(0.6)
        c.roundRect(x, y, box_w, box_h, radius, fill=0, stroke=1)

    if not path or not Path(path).exists():
        return False

    try:
        with Image.open(path) as im:
            iw, ih = im.size
        avail_w = max(1, box_w - 2 * pad)
        avail_h = max(1, box_h - 2 * pad)
        scale = min(avail_w / iw, avail_h / ih)
        dw, dh = iw * scale, ih * scale
        dx = x + (box_w - dw) / 2
        dy = y + (box_h - dh) / 2
        c.drawImage(str(path), dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask="auto")
        return True
    except Exception:
        return False


def _draw_placeholder(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                      theme: Theme, label: str = "Imagem do produto") -> None:
    c.setFillColor(theme.color("light"))
    c.setStrokeColor(theme.color("line"))
    c.roundRect(x, y, w, h, 8, fill=1, stroke=1)
    c.setFillColor(theme.color("muted"))
    c.setFont("Helvetica", 8)
    c.drawCentredString(x + w / 2, y + h / 2, label)


def _draw_logo(c: canvas.Canvas, theme: Theme, x: float, y: float, w: float, h: float,
               fallback_color: Color | None = None) -> None:
    logo_path = theme.logo_path
    if logo_path and Path(logo_path).exists():
        if draw_contain_image(c, logo_path, x, y, w, h, pad=0, bg=None):
            return
    c.setFillColor(fallback_color or theme.color("cover_text"))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(x, y + h / 3, theme.brand.upper())


def draw_header(c: canvas.Canvas, theme: Theme, model: str, right_text: str) -> None:
    bg = theme.color("header_bg")
    c.setFillColor(bg)
    c.rect(0, H - HEADER_H, W, HEADER_H, fill=1, stroke=0)

    logo_w = 72
    logo_h = 22
    _draw_logo(c, theme, ML, H - HEADER_H + 8, logo_w, logo_h,
               fallback_color=theme.color("header_text"))

    c.setFillColor(theme.color("header_text"))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(W / 2, H - HEADER_H + 14, model)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(W - MR, H - HEADER_H + 14, right_text)

    c.setFillColor(theme.color("accent"))
    c.rect(0, H - HEADER_H - 2, W, 2, fill=1, stroke=0)


def draw_footer(c: canvas.Canvas, theme: Theme, custom_lines: tuple[str, ...] = ()) -> None:
    lines = custom_lines or theme.footer_lines
    c.setFillColor(theme.color("footer_bg"))
    c.rect(0, 0, W, FOOTER_H, fill=1, stroke=0)
    c.setFillColor(theme.color("accent"))
    c.rect(0, FOOTER_H - 2, W, 2, fill=1, stroke=0)

    c.setFillColor(theme.color("footer_text"))
    if lines:
        size = 6.6 if len(lines) > 1 else 7.3
        c.setFont("Helvetica", size)
        start_y = 22 if len(lines) > 1 else 15
        for i, line in enumerate(lines[:2]):
            c.drawCentredString(W / 2, start_y - i * 10, line)
    else:
        c.setFont("Helvetica", 7.2)
        c.drawCentredString(W / 2, 14, theme.brand)


def draw_section_title(c: canvas.Canvas, theme: Theme, y: float, text: str) -> float:
    c.setFillColor(theme.color("section_text"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(ML, y, text)
    width = min(CW, c.stringWidth(text, "Helvetica-Bold", 11) + 24)
    c.setFillColor(theme.color("accent"))
    c.rect(ML, y - 7, width, 2, fill=1, stroke=0)
    return y - 25


def _spec_row_height(c: canvas.Canvas, row: tuple[str, ...], col_key: float, col_val: float) -> float:
    if len(row) == 1:
        return 19
    key, value = row
    k_lines = simpleSplit(key, "Helvetica-Bold", 7.3, col_key - 18)
    v_lines = simpleSplit(value, "Helvetica", 7.3, col_val - 18)
    return max(18, (max(len(k_lines), len(v_lines)) * 9.5) + 7)


def split_specs_for_page(c: canvas.Canvas, specs: list[tuple[str, ...]], available_h: float,
                         key_w: float) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
    fit: list[tuple[str, ...]] = []
    rest: list[tuple[str, ...]] = []
    used = 0.0
    val_w = CW - key_w
    overflow = False
    for row in specs:
        rh = _spec_row_height(c, row, key_w, val_w)
        if not overflow and used + rh <= available_h:
            fit.append(row)
            used += rh
        else:
            overflow = True
            rest.append(row)
    return fit, rest


def draw_specs_table(c: canvas.Canvas, theme: Theme, y: float, specs: list[tuple[str, ...]],
                     key_w: float = 185) -> float:
    row_y = y
    val_w = CW - key_w
    for idx, row in enumerate(specs):
        rh = _spec_row_height(c, row, key_w, val_w)
        if len(row) == 1:
            c.setFillColor(theme.color("section_bg"))
            c.rect(ML, row_y - rh, CW, rh, fill=1, stroke=0)
            c.setFillColor(theme.color("accent"))
            c.rect(ML, row_y - rh, 4, rh, fill=1, stroke=0)
            c.setFillColor(theme.color("section_text"))
            c.setFont("Helvetica-Bold", 7.8)
            c.drawString(ML + 10, row_y - rh + 6, row[0])
        else:
            key, value = row
            if idx % 2 == 0:
                c.setFillColor(theme.color("light"))
                c.rect(ML, row_y - rh, CW, rh, fill=1, stroke=0)
            c.setFillColor(theme.color("accent"))
            c.rect(ML, row_y - rh, 2.5, rh, fill=1, stroke=0)

            c.setFillColor(theme.color("text"))
            c.setFont("Helvetica-Bold", 7.3)
            ky = row_y - 11
            for line in simpleSplit(key, "Helvetica-Bold", 7.3, key_w - 18):
                c.drawString(ML + 9, ky, line)
                ky -= 9.5

            c.setFillColor(theme.color("muted"))
            c.setFont("Helvetica", 7.3)
            vy = row_y - 11
            for line in simpleSplit(value, "Helvetica", 7.3, val_w - 18):
                c.drawString(ML + key_w + 8, vy, line)
                vy -= 9.5

        c.setStrokeColor(theme.color("line"))
        c.setLineWidth(0.35)
        c.line(ML, row_y - rh, ML + CW, row_y - rh)
        row_y -= rh

    c.setStrokeColor(theme.color("line"))
    c.setLineWidth(0.5)
    c.rect(ML, row_y, CW, y - row_y, fill=0, stroke=1)
    return row_y


def draw_cover(c: canvas.Canvas, theme: Theme, p: dict[str, Any]) -> None:
    c.setFillColor(theme.color("cover_bg"))
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(theme.color("accent"))
    c.rect(0, H - 5, W, 5, fill=1, stroke=0)

    # Logo
    logo_x, logo_y, logo_w, logo_h = ML, H - 78, 112, 42
    if theme.cover_logo_bg:
        c.setFillColor(HexColor(theme.cover_logo_bg))
        c.roundRect(logo_x - 8, logo_y - 4, logo_w + 16, logo_h + 8, 7, fill=1, stroke=0)
    _draw_logo(c, theme, logo_x, logo_y, logo_w, logo_h,
               fallback_color=theme.color("cover_text"))

    # Product image card
    img_x = W * 0.54
    img_y = 170
    img_w = W - MR - img_x
    img_h = 410
    if not draw_contain_image(c, p.get("main_image"), img_x, img_y, img_w, img_h,
                              pad=14, bg=white, border=theme.color("line"), radius=14):
        _draw_placeholder(c, img_x, img_y, img_w, img_h, theme, "Foto principal")

    text_w = img_x - ML - 22
    y = H - 160
    c.setFillColor(theme.color("cover_muted"))
    c.setFont("Helvetica-Bold", 9)
    y = _draw_text_lines(c, p["categoria"], ML, y, text_w, "Helvetica-Bold", 9,
                         theme.color("cover_muted"), 12, 3)
    y -= 5
    if p["subtitulo"]:
        y = _draw_text_lines(c, p["subtitulo"], ML, y, text_w, "Helvetica", 8.3,
                             theme.color("cover_muted"), 11, 4)
        y -= 10

    c.setFillColor(theme.color("cover_text"))
    c.setFont("Helvetica-Bold", 23)
    for line in simpleSplit(p["model"], "Helvetica-Bold", 23, text_w):
        c.drawString(ML, y, line)
        y -= 28
    y -= 4

    tags = p["tags"][:4]
    for tag in tags:
        lines = simpleSplit(tag, "Helvetica", 7.4, text_w - 20)
        h = 18 + max(0, len(lines) - 1) * 8
        c.setStrokeColor(theme.color("accent"))
        c.setFillColor(theme.color("cover_bg"))
        c.roundRect(ML, y - h + 4, text_w, h, 5, fill=1, stroke=1)
        c.setFillColor(theme.color("cover_text"))
        c.setFont("Helvetica", 7.4)
        ly = y - 8
        for line in lines[:2]:
            c.drawString(ML + 9, ly, line)
            ly -= 8
        y -= h + 5

    y -= 4
    for feat in p["features"][:5]:
        if y < 115:
            break
        c.setFillColor(theme.color("accent"))
        c.circle(ML + 4, y + 3, 3.2, fill=1, stroke=0)
        y = _draw_text_lines(c, feat, ML + 13, y, text_w - 13, "Helvetica", 7.8,
                             theme.color("cover_text"), 10.2, 2) - 3

    draw_footer(c, theme, p.get("footer_lines") or ())
    c.showPage()


def draw_specs_pages(c: canvas.Canvas, theme: Theme, p: dict[str, Any]) -> None:
    draw_header(c, theme, p["model"], "Especificações Técnicas")
    y = H - HEADER_H - 28
    y = draw_section_title(c, theme, y, "Visão Geral")
    y = _draw_text_lines(c, p["intro"], ML, y, CW, "Helvetica", 8.5,
                         theme.color("muted"), 12)
    y -= 8
    y = draw_section_title(c, theme, y, "Especificações Técnicas")

    remaining = list(p["specs"])
    key_w = 185
    first = True
    while remaining:
        available = y - FOOTER_H - 18
        fits, remaining = split_specs_for_page(c, remaining, available, key_w)
        if not fits and remaining:
            fits, remaining = remaining[:1], remaining[1:]
        draw_specs_table(c, theme, y, fits, key_w=key_w)
        draw_footer(c, theme, p.get("footer_lines") or ())
        c.showPage()
        if remaining:
            draw_header(c, theme, p["model"], "Especificações Técnicas")
            y = H - HEADER_H - 28
            y = draw_section_title(c, theme, y, "Especificações Técnicas (continuação)")
        first = False


def _draw_feature_list(c: canvas.Canvas, theme: Theme, y: float, title: str,
                       items: list[tuple[str, str]]) -> float:
    y = draw_section_title(c, theme, y, title)
    for item_title, body in items:
        if y < FOOTER_H + 75:
            break
        c.setFillColor(theme.color("accent"))
        c.circle(ML + 4, y + 4, 3.3, fill=1, stroke=0)
        tx = ML + 14
        available = CW - 14
        if item_title:
            c.setFillColor(theme.color("text"))
            c.setFont("Helvetica-Bold", 8.3)
            title_lines = simpleSplit(item_title, "Helvetica-Bold", 8.3, available)
            for line in title_lines:
                c.drawString(tx, y, line)
                y -= 11
        if body:
            c.setFillColor(theme.color("muted"))
            c.setFont("Helvetica", 8.2)
            for line in simpleSplit(body, "Helvetica", 8.2, available):
                c.drawString(tx, y, line)
                y -= 11
        y -= 5
    return y


def draw_benefits_page(c: canvas.Canvas, theme: Theme, p: dict[str, Any]) -> None:
    draw_header(c, theme, p["model"], "Benefícios e Aplicações")
    y = H - HEADER_H - 28
    y = _draw_feature_list(c, theme, y, "Benefícios do Produto", p["beneficios"])
    y -= 4
    if y > FOOTER_H + 145:
        y = _draw_feature_list(c, theme, y, "Aplicações e Uso", p["aplicacoes"])
    else:
        draw_footer(c, theme, p.get("footer_lines") or ())
        c.showPage()
        draw_header(c, theme, p["model"], "Aplicações e Uso")
        y = H - HEADER_H - 28
        y = _draw_feature_list(c, theme, y, "Aplicações e Uso", p["aplicacoes"])

    if p["slogan"] and y > FOOTER_H + 55:
        c.setFillColor(theme.color("accent"))
        c.rect(ML, y, CW, 2, fill=1, stroke=0)
        y -= 16
        _draw_text_lines(c, p["slogan"], ML, y, CW, "Helvetica-Bold", 8.4,
                         theme.color("text"), 11)

    draw_footer(c, theme, p.get("footer_lines") or ())
    c.showPage()


def _normalize_views(p: dict[str, Any]) -> list[dict[str, str]]:
    views: list[dict[str, str]] = []
    for item in p.get("views") or []:
        if isinstance(item, dict) and item.get("path"):
            views.append({"path": str(item["path"]), "label": str(item.get("label") or "Vista do produto")})
        elif isinstance(item, str):
            views.append({"path": item, "label": "Vista do produto"})
    if not views:
        if p.get("main_image"):
            views.append({"path": str(p["main_image"]), "label": "Vista principal"})
        labels = ["Vista secundária", "Vista traseira", "Vista lateral", "Detalhe"]
        for idx, path in enumerate(p.get("gallery") or []):
            if path:
                views.append({"path": str(path), "label": labels[min(idx, len(labels) - 1)]})
    return views[:4]


def draw_views_page(c: canvas.Canvas, theme: Theme, p: dict[str, Any]) -> None:
    views = _normalize_views(p)
    if not views:
        return

    draw_header(c, theme, p["model"], "Visões do Produto")
    y = H - HEADER_H - 28
    y = draw_section_title(c, theme, y, "Visões do Produto")

    gap = 12
    cell_w = (CW - gap) / 2
    cell_h = 245
    start_y = y - cell_h
    positions = [
        (ML, start_y),
        (ML + cell_w + gap, start_y),
        (ML, start_y - cell_h - 34),
        (ML + cell_w + gap, start_y - cell_h - 34),
    ]

    for idx, view in enumerate(views):
        x, py = positions[idx]
        if py < FOOTER_H + 28:
            break
        ok = draw_contain_image(c, view["path"], x, py, cell_w, cell_h,
                                pad=10, bg=white, border=theme.color("line"), radius=7)
        if not ok:
            _draw_placeholder(c, x, py, cell_w, cell_h, theme, view["label"])
        c.setFillColor(theme.color("dark"))
        c.rect(x, py - 22, cell_w, 20, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica", 7.8)
        c.drawCentredString(x + cell_w / 2, py - 15, view["label"])

    draw_footer(c, theme, p.get("footer_lines") or ())
    c.showPage()


def build_datasheet(product: dict[str, Any], theme: Theme, output_dir: str | os.PathLike[str] = ".") -> str:
    p = normalize_product(product)
    if not p["codigo"]:
        raise ValueError("O produto precisa ter 'codigo' ou 'model'.")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_code(p['codigo'])}_Datasheet.pdf"
    final_path = output_path / filename

    c = canvas.Canvas(str(final_path), pagesize=A4)
    c.setTitle(f"{p['model']} — Datasheet {theme.brand}")
    c.setAuthor(theme.brand)

    draw_cover(c, theme, p)
    draw_specs_pages(c, theme, p)
    draw_benefits_page(c, theme, p)
    draw_views_page(c, theme, p)

    c.save()
    return str(final_path)
