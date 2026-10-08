from __future__ import annotations

import io
from typing import Any

from PIL import Image
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


GREEN = HexColor("#7DC240")
DARK = HexColor("#1C1C1C")
GRAY = HexColor("#444444")
LIGHT = HexColor("#F7F7F7")
LINE = HexColor("#DDDDDD")
SECTION = HexColor("#E4E4E4")

W, H = A4
ML = 20 * mm
MR = 20 * mm
CW = W - ML - MR
FOOTER_H = 36
HEADER_H = 36


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _draw_footer(c: canvas.Canvas) -> None:
    c.setFillColor(DARK)
    c.rect(0, 0, W, FOOTER_H, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(0, FOOTER_H - 1.5, W, 1.5, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica", 7)
    c.drawCentredString(
        W / 2, 20,
        "+55 41 3121.7200 · www.portwell.com.br · contato@portwell.com",
    )
    c.drawCentredString(
        W / 2, 10,
        "Rua José Correia Sérgio, 146 – Fazendinha, Curitiba-PR · Brasil",
    )


def _draw_header(c: canvas.Canvas, model: str, right_text: str) -> None:
    c.setFillColor(white)
    c.rect(0, H - HEADER_H, W, HEADER_H, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(0, H - HEADER_H, W, 1.5, fill=1, stroke=0)
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(ML, H - 23, "Portwell")
    c.setFont("Helvetica-Bold", 12)
    model_width = c.stringWidth(model, "Helvetica-Bold", 12)
    c.drawString((W - model_width) / 2, H - 23, model)
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 8)
    width = c.stringWidth(right_text, "Helvetica", 8)
    c.drawString(W - MR - width, H - 22, right_text)


def _section_title(c: canvas.Canvas, y: float, title: str) -> float:
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(ML, y, title)
    c.setFillColor(GREEN)
    c.rect(ML, y - 7, CW, 1.5, fill=1, stroke=0)
    return y - 26


def _draw_wrapped(c, text, x, y, width, font="Helvetica", size=8.5, leading=12):
    c.setFont(font, size)
    for line in simpleSplit(text, font, size, width):
        c.drawString(x, y, line)
        y -= leading
    return y


def _split_kv(text: str) -> tuple[str, str]:
    if ":" in text:
        field, value = text.split(":", 1)
        return field.strip(), value.strip()
    return "Especificação", text


def _flatten_specs(sections) -> list[tuple]:
    rows = []

    for section in sections or []:
        # Formato esperado: {"secao": "...", "itens": [...]}
        if isinstance(section, dict):
            section_name = _text(section.get("secao") or section.get("section"))
            if section_name:
                rows.append((section_name,))

            for item in section.get("itens", []) or []:
                if isinstance(item, dict):
                    field = _text(item.get("campo") or item.get("key"))
                    value = _text(item.get("valor") or item.get("value"))
                    if field or value:
                        rows.append((field or "Campo", value or "Não informado"))
                elif isinstance(item, (list, tuple)):
                    if len(item) >= 2:
                        rows.append((_text(item[0]), _text(item[1])))
                elif isinstance(item, str):
                    item = item.strip()
                    if item:
                        rows.append(_split_kv(item))

        # Formato antigo: ("Campo", "Valor")
        elif isinstance(section, (list, tuple)):
            if len(section) == 1:
                rows.append((_text(section[0]),))
            elif len(section) >= 2:
                rows.append((_text(section[0]), _text(section[1])))

        # Caso o Qwen devolva especificação como texto
        elif isinstance(section, str):
            section = section.strip()
            if section:
                rows.append(_split_kv(section))

    return rows


def _draw_specs_table(c, y, rows, model):
    row_height = 16
    section_height = 16
    for row in rows:
        if y < FOOTER_H + 35:
            _draw_footer(c)
            c.showPage()
            _draw_header(c, model, "Especificações Técnicas")
            y = H - 55

        if len(row) == 1:
            c.setFillColor(SECTION)
            c.rect(ML, y - section_height, CW, section_height, fill=1, stroke=0)
            c.setFillColor(GREEN)
            c.rect(ML, y - section_height, 3, section_height, fill=1, stroke=0)
            c.setFillColor(DARK)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(ML + 7, y - 11, _text(row[0]))
            y -= section_height
            continue

        key, value = row
        c.setFillColor(LIGHT)
        c.rect(ML, y - row_height, CW, row_height, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.line(ML, y - row_height, ML + CW, y - row_height)
        c.setFillColor(GREEN)
        c.rect(ML, y - row_height, 3, row_height, fill=1, stroke=0)
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 7.2)
        c.drawString(ML + 7, y - 11, _text(key)[:42])
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 7.2)
        value_text = _text(value)
        if len(value_text) > 75:
            value_text = value_text[:72] + "..."
        c.drawString(ML + 205, y - 11, value_text)
        y -= row_height
    return y


def _prepare_image(data: bytes) -> ImageReader:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    buffer.seek(0)
    return ImageReader(buffer)


def _draw_product_image(c, image_bytes, x, y, width, height):
    try:
        c.drawImage(
            _prepare_image(image_bytes), x, y,
            width=width, height=height,
            preserveAspectRatio=True, anchor="c", mask="auto",
        )
    except Exception:
        c.setFillColor(LIGHT)
        c.rect(x, y, width, height, fill=1, stroke=0)
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + width / 2, y + height / 2, "Imagem indisponível")


def _normalize_pairs(items):
    result = []

    for item in items or []:
        if isinstance(item, dict):
            title = _text(item.get("titulo") or item.get("title"))
            description = _text(
                item.get("descricao") or item.get("description") or item.get("body")
            )
        elif isinstance(item, (list, tuple)):
            title = _text(item[0] if len(item) > 0 else "")
            description = _text(item[1] if len(item) > 1 else "")
        elif isinstance(item, str):
            title, description = item.strip(), ""
        else:
            continue

        if title or description:
            result.append({"titulo": title, "descricao": description})

    return result


def _draw_bullet_list(c, y, items, model, page_title):
    for item in items:
        title = _text(item.get("titulo"))
        description = _text(item.get("descricao"))
        if not title and not description:
            continue
        if y < FOOTER_H + 35:
            _draw_footer(c)
            c.showPage()
            _draw_header(c, model, page_title)
            y = H - 55
        c.setFillColor(GREEN)
        c.circle(ML + 4, y + 4, 3.5, fill=1, stroke=0)
        c.setFillColor(DARK)
        y = _draw_wrapped(c, f"{title} {description}".strip(), ML + 13, y, CW - 13)
        y -= 5
    return y


def generate_portwell_datasheet(data: dict, images: list[bytes] | None = None) -> bytes:
    images = images or []
    model = _text(data.get("model")) or "Produto"
    categoria = _text(data.get("categoria")) or "Produto Industrial – Portwell"
    subtitulo = _text(data.get("subtitulo"))
    tags = [_text(x) for x in data.get("tags", []) if _text(x)]
    features = [_text(x) for x in data.get("features", []) if _text(x)]
    intro = _text(data.get("intro"))
    beneficios = _normalize_pairs(data.get("beneficios"))
    aplicacoes = _normalize_pairs(data.get("aplicacoes"))
    slogan = _text(data.get("slogan"))
    specs = _flatten_specs(data.get("specs", []))

    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    c.setTitle(f"{model} — Datasheet Portwell")
    c.setAuthor("Portwell")

    # ---------- Capa ----------
    c.setFillColor(DARK)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(0, H - 3, W, 3, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 55, "Portwell")

    y = 260
    c.setFillColor(HexColor("#BBBBBB"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(ML, y + 54, categoria)
    c.setFillColor(HexColor("#999999"))
    c.setFont("Helvetica", 9)
    if subtitulo:
        y_sub = y + 38
        for line in simpleSplit(subtitulo, "Helvetica", 9, CW):
            c.drawString(ML, y_sub, line)
            y_sub -= 11

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(ML, y, model)

    tag_y = y - 30
    for tag in tags[:4]:
        width = min(c.stringWidth(tag, "Helvetica", 7.5) + 16, CW)
        c.setStrokeColor(HexColor("#AAAAAA"))
        c.setFillColor(DARK)
        c.roundRect(ML, tag_y, width, 16, 3, fill=1, stroke=1)
        c.setFillColor(white)
        c.setFont("Helvetica", 7.5)
        c.drawString(ML + 8, tag_y + 4.5, tag[:90])
        tag_y -= 22

    feature_y = tag_y - 5
    for feature in features[:5]:
        c.setFillColor(GREEN)
        c.circle(ML + 4, feature_y + 4, 3.5, fill=1, stroke=0)
        c.setFillColor(white)
        feature_y = _draw_wrapped(c, feature, ML + 13, feature_y, CW - 13)
        feature_y -= 3

    c.setFillColor(HexColor("#777777"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(
        W / 2, 16,
        "+55 41 3121.7200 · www.portwell.com.br · contato@portwell.com",
    )
    c.showPage()

    # ---------- Especificações ----------
    _draw_header(c, model, "Especificações Técnicas")
    y = H - 55
    if intro:
        y = _section_title(c, y, "Visão Geral")
        c.setFillColor(GRAY)
        y = _draw_wrapped(c, intro, ML, y, CW)
        y -= 10
    y = _section_title(c, y, "Especificações Técnicas")
    _draw_specs_table(c, y, specs, model)
    _draw_footer(c)
    c.showPage()

    # ---------- Benefícios e Aplicações ----------
    page_title = "Benefícios e Aplicações"
    _draw_header(c, model, page_title)
    y = H - 55
    y = _section_title(c, y, "Benefícios do Produto")
    y = _draw_bullet_list(c, y, beneficios, model, page_title)

    y -= 8
    if y < FOOTER_H + 60:
        _draw_footer(c)
        c.showPage()
        _draw_header(c, model, page_title)
        y = H - 55
    y = _section_title(c, y, "Aplicações e Uso")
    y = _draw_bullet_list(c, y, aplicacoes, model, page_title)

    if slogan:
        if y < FOOTER_H + 50:
            _draw_footer(c)
            c.showPage()
            _draw_header(c, model, page_title)
            y = H - 55
        y -= 5
        c.setFillColor(GREEN)
        c.rect(ML, y, CW, 1.5, fill=1, stroke=0)
        y -= 16
        c.setFillColor(DARK)
        _draw_wrapped(c, slogan, ML, y, CW, font="Helvetica-Bold", size=9)

    _draw_footer(c)
    c.showPage()

    # ---------- Imagens ----------
    if images:
        _draw_header(c, model, "Visões do Produto")
        y = _section_title(c, H - 55, "Visões do Produto")
        gap = 10
        image_width = (CW - gap) / 2
        image_height = 210
        x1 = ML
        x2 = ML + image_width + gap
        image_y = y - image_height
        _draw_product_image(c, images[0], x1, image_y, image_width, image_height)
        if len(images) > 1:
            _draw_product_image(c, images[1], x2, image_y, image_width, image_height)

        caption_y = image_y - 25
        c.setFillColor(DARK)
        c.rect(x1, caption_y, image_width, 20, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica", 8.5)
        c.drawCentredString(x1 + image_width / 2, caption_y + 6, "Vista Principal")
        if len(images) > 1:
            c.setFillColor(DARK)
            c.rect(x2, caption_y, image_width, 20, fill=1, stroke=0)
            c.setFillColor(white)
            c.drawCentredString(x2 + image_width / 2, caption_y + 6, "Vista Secundária")
        _draw_footer(c)
        c.showPage()

    c.save()
    output.seek(0)
    return output.read()
