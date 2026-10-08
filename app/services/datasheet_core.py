"""Motor de datasheets do PRM (Portwell, Choice e SAG).

Recebe o JSON do produto (gerado pelo Claude no schema novo, ou no formato antigo do PRM),
trata as imagens (recorte, remoção de marca do fabricante, tradução de textos, remoção de fundo
da capa) e devolve o PDF pronto no padrão visual de cada empresa.

Entradas aceitas
----------------
Schema novo (recomendado, ver datasheet_prompt.py):
    modelo, modelo_cabecalho, nivel, categoria, subtitulo, tags, features, descricao,
    caracteristicas, tabelas, especificacoes, dimensoes, conectores, pedido, acessorios,
    aplicacoes, notas, imagens, termos_proibidos, conferencia_fontes, pendencias

Formato antigo do PRM (continua funcionando):
    model, categoria, subtitulo, tags, features, intro, beneficios, aplicacoes, slogan,
    specs ([{"secao": "...", "itens": [{"campo": "...", "valor": "..."}]}] ou tuplas)

Anexos: dicionário {nome_do_arquivo: bytes}. As imagens do schema novo referenciam esses nomes
em imagens[].arquivo. Uma lista simples de bytes também é aceita: vira img_01, img_02, ... na ordem.
"""
from __future__ import annotations

import io
import os
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BASE_DIR = Path(__file__).resolve().parent
ASSETS = BASE_DIR / "assets"

W, H = A4
ML = 20 * mm
MR = 20 * mm
CW = W - ML - MR
TOP_Y = H - 55
BOTTOM_Y = 60

# ----------------------------------------------------------------------------- fontes
_FONT_DIRS = [ASSETS / "fonts", Path("/usr/share/fonts/truetype/dejavu"),
              Path("/usr/share/fonts/dejavu"), Path("C:/Windows/Fonts")]


def _find_font(name: str) -> str | None:
    for d in _FONT_DIRS:
        p = d / name
        if p.exists():
            return str(p)
    return None


_REG = _find_font("DejaVuSans.ttf")
_BOLD = _find_font("DejaVuSans-Bold.ttf")
if _REG and _BOLD:
    pdfmetrics.registerFont(TTFont("Sans", _REG))
    pdfmetrics.registerFont(TTFont("Sans-Bold", _BOLD))
    F, FB = "Sans", "Sans-Bold"
else:  # sem DejaVu: Helvetica (alguns símbolos como ≥ podem não aparecer)
    F, FB = "Helvetica", "Helvetica-Bold"
PIL_FONT = _REG or _find_font("arial.ttf")
PIL_FONT_B = _BOLD or _find_font("arialbd.ttf")


# ----------------------------------------------------------------------------- tema
@dataclass(frozen=True)
class Theme:
    brand: str
    accent: str
    dark: str = "#1C1C1C"
    text: str = "#1C1C1C"
    muted: str = "#444444"
    light: str = "#F7F7F7"
    line: str = "#DDDDDD"
    section_bg: str = "#E4E4E4"
    section_text: str = "#1C1C1C"
    cover_bg: str = "#1C1C1C"
    cover_text: str = "#FFFFFF"
    cover_muted: str = "#BBBBBB"
    cover_tag_border: str = "#AAAAAA"
    header_bg: str = "#FFFFFF"
    header_text: str = "#1C1C1C"
    footer_bg: str = "#111111"
    footer_text: str = "#FFFFFF"
    logo_path: str | None = None          # logo para cabeçalho e capa (PNG com transparência)
    cover_logo_bg: str | None = None      # caixa atrás do logo na capa (ex.: "#FFFFFF")
    registered: bool = False              # desenha ® após o nome quando não há logo
    # contato
    razao_social: str = ""
    telefone: str = ""
    site: str = ""
    email: str = ""
    endereco: str = ""
    cidade: str = ""
    titulo_contato: str = ""
    fechamento: tuple[str, ...] = ()
    assinatura: str = ""                  # linha final fixa (ex.: SAG)
    footer_lines: tuple[str, ...] = ()    # sobrescreve o rodapé automático

    def c(self, attr: str) -> Color:
        return HexColor(getattr(self, attr))

    def contato_linhas(self) -> tuple[str, ...]:
        if self.footer_lines:
            return self.footer_lines
        l1 = "  |  ".join(x for x in (self.endereco, self.cidade) if x)
        l2 = "  ·  ".join(x for x in (self.telefone, self.site, self.email) if x)
        return tuple(x for x in (l1, l2) if x) or (self.brand,)


# ----------------------------------------------------------------------------- utilidades de texto
_TRAV = re.compile("\\s*[\u2014\u2013]\\s*")


def limpa(v: Any) -> Any:
    """Troca travessões por vírgula em todo o conteúdo (regra da casa)."""
    if isinstance(v, str):
        s = _TRAV.sub(", ", v)
        return s.replace(", ,", ",").replace(",,", ",")
    if isinstance(v, list):
        return [limpa(x) for x in v]
    if isinstance(v, tuple):
        return tuple(limpa(x) for x in v)
    if isinstance(v, dict):
        return {k: (limpa(x) if k not in ("imagens", "arquivo") else x) for k, x in v.items()}
    return v


def _t(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _pairs(items: Iterable[Any] | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for it in items or []:
        if isinstance(it, dict):
            a = _t(it.get("titulo") or it.get("title"))
            b = _t(it.get("texto") or it.get("descricao") or it.get("description") or it.get("body"))
        elif isinstance(it, (list, tuple)):
            a = _t(it[0] if len(it) > 0 else ""); b = _t(it[1] if len(it) > 1 else "")
        elif isinstance(it, str):
            a, b = "", it.strip()
        else:
            continue
        if a and b and not a.endswith((":", ": ")):
            a = a + ": "
        elif a and not b:
            a, b = "", a
        elif a and not a.endswith(" "):
            a = a + " "
        if a or b:
            out.append((a, b))
    return out


def _spec_rows(items: Iterable[Any] | None) -> list[tuple[str, ...]]:
    """Aceita: [{"secao"}, {"chave","valor"}], [{"secao", "itens":[...]}], tuplas e 'Campo: valor'."""
    rows: list[tuple[str, ...]] = []
    for it in items or []:
        if isinstance(it, dict):
            sec = _t(it.get("secao") or it.get("section"))
            if sec:
                rows.append((sec,))
            itens = it.get("itens")
            if itens is not None:
                for sub in itens or []:
                    rows.extend(_spec_rows([sub]))
                continue
            k = _t(it.get("chave") or it.get("campo") or it.get("key"))
            v = _t(it.get("valor") if "valor" in it else it.get("value"))
            if k and v:
                rows.append((k, v))
        elif isinstance(it, (list, tuple)):
            if len(it) == 1 and _t(it[0]):
                rows.append((_t(it[0]),))
            elif len(it) >= 2 and _t(it[1]):
                rows.append((_t(it[0]), _t(it[1])))
        elif isinstance(it, str) and it.strip():
            k, _, v = it.partition(":")
            rows.append((k.strip(), v.strip()) if v else ("Especificação", k.strip()))
    return rows


# ----------------------------------------------------------------------------- normalização
def normalize(data: dict[str, Any], codigo: str | None = None) -> dict[str, Any]:
    """Converte o formato antigo do PRM para o schema novo e limpa o texto."""
    d = dict(data or {})
    modelo = _t(d.get("modelo") or d.get("model") or codigo) or "Produto"
    n: dict[str, Any] = {
        "codigo": _t(codigo or d.get("codigo") or modelo),
        "modelo": modelo,
        "modelo_cabecalho": _t(d.get("modelo_cabecalho")) or modelo,
        "nivel": _t(d.get("nivel")) or "completo",
        "categoria": _t(d.get("categoria") or d.get("category")) or "Produto Industrial",
        "subtitulo": _t(d.get("subtitulo") or d.get("subtitle")),
        "tags": [_t(x) for x in d.get("tags") or [] if _t(x)],
        "features": [_t(x) for x in (d.get("features") or d.get("destaques") or []) if _t(x)],
        "descricao": d.get("descricao") if isinstance(d.get("descricao"), list)
        else [x for x in [_t(d.get("descricao") or d.get("intro"))] if x],
        "titulo_caracteristicas": _t(d.get("titulo_caracteristicas"))
        or ("Benefícios do Produto" if d.get("beneficios") and not d.get("caracteristicas") else "Principais Características"),
        "caracteristicas": _pairs(d.get("caracteristicas") or d.get("beneficios")),
        "tabelas": d.get("tabelas") or [],
        "especificacoes": _spec_rows(d.get("especificacoes") or d.get("specs")),
        "dimensoes": _spec_rows(d.get("dimensoes")),
        "conectores": d.get("conectores") or [],
        "pedido": d.get("pedido") or None,
        "acessorios": _pairs(d.get("acessorios")),
        "aplicacoes": _pairs(d.get("aplicacoes")),
        "notas": _pairs(d.get("notas")),
        "slogan": _t(d.get("slogan")),
        "imagens": d.get("imagens") or [],
        "termos_proibidos": [x for x in d.get("termos_proibidos") or [] if _t(x)],
        "conferencia_fontes": _t(d.get("conferencia_fontes")),
        "pendencias": [x for x in d.get("pendencias") or [] if _t(x)],
    }
    return limpa(n)


# ----------------------------------------------------------------------------- imagens
def _box(cx: list[float], w: int, h: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = [float(v) for v in cx]
    if max(x0, y0, x1, y1) <= 1.0:  # normalizado 0..1
        x0, x1, y0, y1 = x0 * w, x1 * w, y0 * h, y1 * h
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1))
    return int(max(0, x0)), int(max(0, y0)), int(min(w, x1)), int(min(h, y1))


def _border_color(a: np.ndarray, x0: int, y0: int, x1: int, y1: int, m: int = 4) -> tuple[int, int, int]:
    h, w = a.shape[:2]
    parts = [a[max(0, y0 - m):y0, x0:x1], a[y1:min(h, y1 + m), x0:x1],
             a[y0:y1, max(0, x0 - m):x0], a[y0:y1, x1:min(w, x1 + m)]]
    pts = np.concatenate([p.reshape(-1, 3) for p in parts if p.size]) if any(p.size for p in parts) else np.empty((0, 3))
    return tuple(int(v) for v in np.median(pts, axis=0)) if len(pts) else (255, 255, 255)


def _write_text(im: Image.Image, box: tuple[int, int, int, int], text: str, bold: bool = False) -> Image.Image:
    x0, y0, x1, y1 = box
    if x1 - x0 < 3 or y1 - y0 < 3 or not PIL_FONT:
        return im
    S = 3
    big = im.resize((im.width * S, im.height * S), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    bg = _border_color(np.asarray(im), x0, y0, x1, y1)
    d.rectangle((x0 * S, y0 * S, x1 * S, y1 * S), fill=bg)
    fg = (30, 30, 30) if sum(bg) > 380 else (235, 235, 235)
    lines = text.split("\n"); bh = (y1 - y0) * S; bw = (x1 - x0) * S
    size = max(6, int(bh / len(lines) * 0.78))
    font_path = PIL_FONT_B if bold and PIL_FONT_B else PIL_FONT
    while True:
        f = ImageFont.truetype(font_path, size)
        if size <= 6 or max(d.textbbox((0, 0), ln, font=f)[2] for ln in lines) <= bw * 0.98:
            break
        size -= 1
    lh = bh / len(lines)
    for i, ln in enumerate(lines):
        bb = d.textbbox((0, 0), ln, font=f)
        d.text((x0 * S + (bw - (bb[2] - bb[0])) / 2 - bb[0], y0 * S + i * lh + (lh - (bb[3] - bb[1])) / 2 - bb[1]),
               ln, font=f, fill=fg)
    return big.resize(im.size, Image.LANCZOS)


def _erase(im: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    x0, y0, x1, y1 = box
    a = np.asarray(im).copy()
    if x1 - x0 < 2 or y1 - y0 < 2:
        return im
    bg = np.array(_border_color(a, x0, y0, x1, y1))
    try:
        import cv2
        m = np.zeros(a.shape[:2], np.uint8)
        m[y0:y1, x0:x1] = (np.abs(a[y0:y1, x0:x1].astype(int) - bg).sum(axis=2) > 30).astype(np.uint8) * 255
        m = cv2.dilate(m, np.ones((5, 5), np.uint8))
        return Image.fromarray(cv2.inpaint(a, m, 6, cv2.INPAINT_TELEA))
    except Exception:
        a[y0:y1, x0:x1] = bg
        return Image.fromarray(a)


def _trim(im: Image.Image, thr: int = 238, pad: float = 0.02) -> Image.Image:
    a = np.asarray(im.convert("L")); ys, xs = np.where(a < thr)
    if not len(xs):
        return im
    p = int(max(im.size) * pad)
    return im.crop((max(0, xs.min() - p), max(0, ys.min() - p),
                    min(im.width, xs.max() + p), min(im.height, ys.max() + p)))


def remove_background(im: Image.Image, thr: int = 235, up: int = 2,
                      erode_px: float = 1.2, feather_px: float = 1.6) -> Image.Image:
    """Remove fundo claro e liso (flood fill pelas bordas). Devolve RGBA recortado."""
    im = im.convert("RGB"); w0, h0 = im.size
    big = im.resize((w0 * up, h0 * up), Image.LANCZOS); a = np.asarray(big)
    near = a.min(axis=2) >= thr; h, w = near.shape
    bg = np.zeros((h, w), bool); dq: deque = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near[y, x] and not bg[y, x]:
                bg[y, x] = True; dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if near[y, x] and not bg[y, x]:
                bg[y, x] = True; dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and near[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True; dq.append((ny, nx))
    fg = ~bg
    try:
        import cv2
        n, lbl, st, _ = cv2.connectedComponentsWithStats(fg.astype(np.uint8), connectivity=8)
        if n > 1:
            areas = st[1:, cv2.CC_STAT_AREA]; big_area = areas.max()
            keep = np.zeros_like(fg)
            for i in range(1, n):
                if st[i, cv2.CC_STAT_AREA] > big_area * 0.02:
                    keep |= (lbl == i)
            fg = keep
    except Exception:
        pass
    alpha = Image.fromarray((fg * 255).astype(np.uint8))
    k = max(3, int(erode_px * 2) * 2 + 1)
    alpha = alpha.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.GaussianBlur(feather_px))
    out = big.convert("RGBA"); out.putalpha(alpha); out = out.resize((w0, h0), Image.LANCZOS)
    bb = out.getbbox()
    return out.crop(bb) if bb else out


def _load(spec: dict[str, Any], anexos: dict[str, bytes]) -> Image.Image:
    nome = spec.get("arquivo")
    raw = anexos.get(nome)
    if raw is None:
        raise KeyError(f"anexo '{nome}' não enviado")
    if str(nome).lower().endswith(".pdf") or raw[:4] == b"%PDF":
        import pymupdf
        doc = pymupdf.open(stream=raw, filetype="pdf")
        pg = doc[int(spec.get("pagina_pdf") or 1) - 1]
        pix = pg.get_pixmap(dpi=220)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        im = Image.open(io.BytesIO(raw))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, "white"); bg.alpha_composite(im); im = bg
        im = im.convert("RGB")
    if spec.get("recorte"):
        im = im.crop(_box(spec["recorte"], im.width, im.height))
    return im


@dataclass
class Prepared:
    papel: str
    legenda: str
    image: Image.Image
    spec: dict[str, Any] = field(default_factory=dict)

    @property
    def wide(self) -> bool:
        return self.image.width > 1.6 * self.image.height

    def reader(self) -> ImageReader:
        buf = io.BytesIO()
        self.image.save(buf, format="PNG"); buf.seek(0)
        return ImageReader(buf)


def prepare_images(p: dict[str, Any], anexos: dict[str, bytes], theme: Theme, avisos: list[str]) -> list[Prepared]:
    specs = list(p.get("imagens") or [])
    if not specs:  # formato antigo: lista de imagens sem papel
        nomes = sorted(anexos)
        for i, nome in enumerate(nomes):
            if str(nome).lower().endswith(".pdf"):
                continue
            specs.append({"arquivo": nome, "papel": "capa" if not specs else "perspectiva",
                          "legenda": "Vista principal" if not specs else "Vista do produto",
                          "fundo": "complexo", "remover_fundo": False})
    out: list[Prepared] = []
    for spec in specs:
        papel = _t(spec.get("papel")) or "detalhe"
        if papel == "descartar":
            continue
        try:
            im = _load(spec, anexos)
        except Exception as e:
            avisos.append(f"Imagem {spec.get('arquivo')}: não carregou ({e})."); continue
        for mk in spec.get("marcas") or []:
            try:
                b = _box(mk["caixa"], im.width, im.height)
                if str(mk.get("acao", "")).startswith("substituir"):
                    im = _write_text(im, b, _t(mk.get("texto")) or theme.brand, bold=True)
                else:
                    im = _erase(im, b)
            except Exception as e:
                avisos.append(f"Imagem {spec.get('arquivo')}: falha ao tratar marca ({e}).")
        for tx in spec.get("textos") or []:
            try:
                im = _write_text(im, _box(tx["caixa"], im.width, im.height), limpa(_t(tx.get("traducao"))))
            except Exception as e:
                avisos.append(f"Imagem {spec.get('arquivo')}: falha ao traduzir texto ({e}).")
        if papel != "dimensoes":
            im = _trim(im)
        if papel == "capa" and spec.get("remover_fundo") and spec.get("fundo") in ("branco_liso", "transparente"):
            try:
                im = remove_background(im)
            except Exception as e:
                avisos.append(f"Remoção de fundo da capa falhou ({e}); usada a foto com fundo.")
        out.append(Prepared(papel, limpa(_t(spec.get("legenda"))), im, spec))
    return out


# ----------------------------------------------------------------------------- layout em fluxo
class Flow:
    def __init__(self, buf, theme: Theme, model: str):
        self.t = theme
        self.cv = canvas.Canvas(buf, pagesize=A4)
        self.cv.setTitle(f"{model}, Datasheet {theme.brand}")
        self.cv.setAuthor(theme.razao_social or theme.brand)
        self.model = model
        self.header_right = "Datasheet"
        self.y = TOP_Y
        self.page_open = False

    # --- moldura
    def _logo(self, x, y, w, h, color: Color, align="left") -> None:
        c = self.cv; lp = self.t.logo_path
        if lp and Path(lp).exists():
            try:
                with Image.open(lp) as im:
                    iw, ih = im.size
                s = min(w / iw, h / ih); dw, dh = iw * s, ih * s
                dx = x if align == "left" else x + (w - dw) / 2
                c.drawImage(lp, dx, y + (h - dh) / 2, width=dw, height=dh, mask="auto"); return
            except Exception:
                pass
        size = min(h * 0.75, 22)
        c.setFillColor(color); c.setFont(FB, size)
        tw = c.stringWidth(self.t.brand, FB, size)
        dx = x if align == "left" else x + (w - tw) / 2
        c.drawString(dx, y + (h - size) / 2 + size * 0.15, self.t.brand)
        if self.t.registered:
            c.setFont(F, size * 0.42); c.drawString(dx + tw + 1.2, y + (h - size) / 2 + size * 0.8, "®")

    def header(self) -> None:
        c = self.cv; t = self.t
        c.setFillColor(t.c("header_bg")); c.rect(0, H - 36, W, 36, fill=1, stroke=0)
        self._logo(ML, H - 31, 80, 22, t.c("header_text"))
        c.setFillColor(t.c("header_text")); c.setFont(FB, 12.5)
        c.drawCentredString(W / 2, H - 24.3, self.model)
        c.setFillColor(t.c("muted")); c.setFont(F, 9)
        c.drawRightString(W - MR, H - 22.6, self.header_right)
        c.setFillColor(t.c("accent")); c.rect(0, H - 36, W, 1.3, fill=1, stroke=0)

    def footer(self) -> None:
        c = self.cv; t = self.t
        c.setFillColor(t.c("footer_bg")); c.rect(0, 0, W, 36, fill=1, stroke=0)
        c.setFillColor(t.c("accent")); c.rect(0, 36, W, 1.3, fill=1, stroke=0)
        c.setFillColor(t.c("footer_text"))
        lines = t.contato_linhas()[:2]
        c.setFont(F, 6.8 if len(lines) > 1 else 7.3)
        ys = (21, 10) if len(lines) > 1 else (15,)
        for yy, ln in zip(ys, lines):
            c.drawCentredString(W / 2, yy, ln)

    # --- paginação
    def new_page(self, header_right: str | None = None) -> None:
        if self.page_open:
            self.footer(); self.cv.showPage()
        if header_right:
            self.header_right = header_right
        self.header(); self.y = TOP_Y; self.page_open = True

    def need(self, h: float) -> None:
        if not self.page_open or self.y - h < BOTTOM_Y:
            self.new_page()

    def finish(self) -> None:
        if self.page_open:
            self.footer(); self.cv.showPage(); self.page_open = False
        self.cv.save()

    # --- blocos
    def section(self, text: str, space_before: float = 0) -> None:
        self.y -= space_before; self.need(46)
        c = self.cv
        c.setFont(FB, 11); c.setFillColor(self.t.c("section_text")); c.drawString(ML, self.y, text)
        c.setFillColor(self.t.c("accent")); c.rect(ML, self.y - 7, CW, 1.5, fill=1, stroke=0)
        self.y -= 26

    def paragraph(self, text: str, size=8.5, leading=12.5, space_after=8, color: Color | None = None,
                  align="left", bold=False) -> None:
        if not text:
            return
        font = FB if bold else F
        for line in simpleSplit(text, font, size, CW):
            self.need(leading)
            self.cv.setFont(font, size); self.cv.setFillColor(color or self.t.c("muted"))
            if align == "center":
                self.cv.drawCentredString(W / 2, self.y, line)
            else:
                self.cv.drawString(ML, self.y, line)
            self.y -= leading
        self.y -= space_after

    def bullets(self, items: list[tuple[str, str]], size=8.5, leading=12, gap=4) -> None:
        c = self.cv
        for title, body in items:
            tx = ML + 13; avail = CW - 13
            tw = c.stringWidth(title, FB, size) if title else 0
            first, rest = "", body
            if body:
                for word in body.split():
                    test = (first + " " + word).strip()
                    if c.stringWidth(test, F, size) <= avail - tw:
                        first = test; rest = body[len(first):].strip()
                    else:
                        break
            rest_lines = simpleSplit(rest, F, size, avail) if rest else []
            self.need(min(leading * (1 + len(rest_lines)) + gap, 3 * leading + gap))
            c.setFillColor(self.t.c("accent")); c.circle(ML + 4, self.y + 4, 3.2, fill=1, stroke=0)
            if title:
                c.setFont(FB, size); c.setFillColor(self.t.c("text")); c.drawString(tx, self.y, title)
            if first:
                c.setFont(F, size); c.setFillColor(self.t.c("muted")); c.drawString(tx + tw, self.y, first)
            self.y -= leading
            for line in rest_lines:
                self.need(leading)
                c.setFont(F, size); c.setFillColor(self.t.c("muted")); c.drawString(tx, self.y, line)
                self.y -= leading
            self.y -= gap

    def spec_table(self, rows: list[tuple[str, ...]], col1=165, size=7.5, rh_min=17, lead=9.5, space_after=10) -> None:
        c = self.cv; t = self.t; avail_val = CW - col1 - 8; data_i = 0; top = None

        def close(tp, bottom):
            c.setStrokeColor(t.c("line")); c.setLineWidth(0.4); c.rect(ML, bottom, CW, tp - bottom, fill=0, stroke=1)

        for row in rows:
            if len(row) == 1:
                rh = rh_min - 1
            else:
                nv = len(simpleSplit(row[1], F, size, avail_val)); nk = len(simpleSplit(row[0], FB, size, col1 - 14))
                rh = rh_min + (max(nv, nk) - 1) * lead
            need_h = rh + (rh_min if len(row) == 1 else 0)
            if not self.page_open or self.y - need_h < BOTTOM_Y:
                if top is not None:
                    close(top, self.y)
                self.new_page(); top = self.y
            if top is None:
                top = self.y
            if len(row) == 1:
                c.setFillColor(t.c("section_bg")); c.rect(ML, self.y - rh, CW, rh, fill=1, stroke=0)
                c.setFillColor(t.c("accent")); c.rect(ML, self.y - rh, 3, rh, fill=1, stroke=0)
                c.setFont(FB, size); c.setFillColor(t.c("section_text")); c.drawString(ML + 7, self.y - rh + 5, row[0])
                data_i = 0
            else:
                k, v = row
                c.setFillColor(t.c("light") if data_i % 2 == 0 else white); c.rect(ML, self.y - rh, CW, rh, fill=1, stroke=0)
                c.setFillColor(t.c("accent")); c.rect(ML, self.y - rh, 3, rh, fill=1, stroke=0)
                c.setFont(FB, size); c.setFillColor(t.c("text"))
                kls = simpleSplit(k, FB, size, col1 - 14); ky = self.y - rh + 5 + (len(kls) - 1) * lead
                for kl in kls:
                    c.drawString(ML + 7, ky, kl); ky -= lead
                c.setFont(F, size); c.setFillColor(t.c("muted"))
                vl = simpleSplit(v, F, size, avail_val); ly = self.y - rh + 5 + (len(vl) - 1) * lead
                for ln in vl:
                    c.drawString(ML + col1, ly, ln); ly -= lead
                data_i += 1
            c.setStrokeColor(t.c("line")); c.setLineWidth(0.3); c.line(ML, self.y - rh, ML + CW, self.y - rh)
            self.y -= rh
        if top is not None:
            close(top, self.y)
        self.y -= space_after

    def grid_table(self, head: list[str], rows: list[list[Any]], widths: list[float] | None = None,
                   size=7.5, rh=17, lead=9.5, space_after=10) -> None:
        c = self.cv; t = self.t
        widths = widths or [1] * len(head)
        sc = CW / sum(widths); wds = [w * sc for w in widths]
        self.need(rh * 2 + 10)

        def draw_head():
            c.setFillColor(t.c("dark")); c.rect(ML, self.y - rh, CW, rh, fill=1, stroke=0)
            c.setFont(FB, size); c.setFillColor(white); x = ML
            for i, hd in enumerate(head):
                c.drawCentredString(x + wds[i] / 2, self.y - rh + 5.5, _t(hd)); x += wds[i]
            self.y -= rh

        def close(tp, hb):
            c.setStrokeColor(t.c("line")); c.setLineWidth(0.4); c.rect(ML, self.y, CW, tp - self.y, fill=0, stroke=1)
            x = ML
            for w_ in wds[:-1]:
                x += w_; c.line(x, self.y, x, hb)

        top = self.y; draw_head(); hb = self.y
        for r_i, row in enumerate(rows):
            cells = [simpleSplit(_t(cell), F, size, wds[i] - 10) for i, cell in enumerate(row[:len(wds)])]
            h_ = rh + (max(len(x) for x in cells) - 1) * lead
            if self.y - h_ < BOTTOM_Y:
                close(top, hb); self.new_page(); top = self.y; draw_head(); hb = self.y
            c.setFillColor(t.c("light") if r_i % 2 == 0 else white); c.rect(ML, self.y - h_, CW, h_, fill=1, stroke=0)
            c.setFillColor(t.c("accent")); c.rect(ML, self.y - h_, 3, h_, fill=1, stroke=0)
            x = ML
            for i, ls in enumerate(cells):
                c.setFont(FB if i == 0 else F, size); c.setFillColor(t.c("text") if i == 0 else t.c("muted"))
                ly = self.y - h_ + 5.5 + (len(ls) - 1) * lead
                for ln in ls:
                    c.drawCentredString(x + wds[i] / 2, ly, ln); ly -= lead
                x += wds[i]
            c.setStrokeColor(t.c("line")); c.setLineWidth(0.3); c.line(ML, self.y - h_, ML + CW, self.y - h_)
            self.y -= h_
        close(top, hb); self.y -= space_after

    def image(self, img: Prepared, max_w=None, max_h=260, card=True, space_after=6) -> None:
        max_w = max_w or CW
        iw, ih = img.image.size; s = min(max_w / iw, max_h / ih); w, h = iw * s, ih * s
        cap = 18 if img.legenda else 0
        self.need(h + 16 + cap)
        c = self.cv
        if card:
            c.setFillColor(white); c.setStrokeColor(self.t.c("line")); c.setLineWidth(0.6)
            c.rect(ML, self.y - h - 16, CW, h + 16, fill=1, stroke=1)
            c.setFillColor(self.t.c("accent")); c.rect(ML, self.y - h - 16, 3, h + 16, fill=1, stroke=0)
            c.drawImage(img.reader(), ML + (CW - w) / 2, self.y - h - 8, width=w, height=h, mask="auto")
            self.y -= h + 16
        else:
            c.drawImage(img.reader(), ML + (CW - w) / 2, self.y - h, width=w, height=h, mask="auto")
            self.y -= h
        if img.legenda:
            self.y -= 10
            c.setFont(F, 7); c.setFillColor(HexColor("#888888")); c.drawCentredString(W / 2, self.y, img.legenda)
            self.y -= 8
        self.y -= space_after

    def image_row(self, items: list[Prepared], max_h=180, space_after=12) -> None:
        n = len(items); gap = 10; cw_each = (CW - gap * (n - 1)) / n
        sizes = []
        for it in items:
            iw, ih = it.image.size; s = min(cw_each / iw, max_h / ih); sizes.append((iw * s, ih * s))
        h_max = max(s[1] for s in sizes)
        self.need(h_max + 40)
        c = self.cv; x = ML; base = self.y - h_max
        for it, (w, h) in zip(items, sizes):
            c.drawImage(it.reader(), x + (cw_each - w) / 2, base, width=w, height=h, mask="auto")
            c.setFillColor(self.t.c("dark")); c.rect(x, base - 24, cw_each, 16, fill=1, stroke=0)
            c.setFillColor(self.t.c("accent")); c.rect(x, base - 24, 2.5, 16, fill=1, stroke=0)
            c.setFont(F, 7); c.setFillColor(white); c.drawCentredString(x + cw_each / 2, base - 19, it.legenda[:70])
            x += cw_each + gap
        self.y = base - 24 - space_after

    def kv_two_col(self, items: list[tuple[str, str]], size=8, leading=13, space_after=8) -> None:
        c = self.cv; col_w = CW / 2; usable = col_w - 12
        hs = []
        for k, v in items:
            fits = c.stringWidth(k, FB, size) + 4 + c.stringWidth(v, F, size) <= usable - 11
            hs.append(leading if fits else leading * 1.75)
        rows = (len(items) + 1) // 2
        rh = [max(hs[2 * r], hs[2 * r + 1] if 2 * r + 1 < len(hs) else 0) for r in range(rows)]
        self.need(sum(rh) + 6)
        y0 = self.y
        for i, (k, v) in enumerate(items):
            cx = ML if i % 2 == 0 else ML + col_w; yy = y0 - sum(rh[:i // 2])
            c.setFillColor(self.t.c("accent")); c.circle(cx + 3, yy + 3, 2.6, fill=1, stroke=0)
            c.setFont(FB, size); c.setFillColor(self.t.c("text")); c.drawString(cx + 11, yy, k)
            kw = c.stringWidth(k, FB, size); c.setFont(F, size); c.setFillColor(self.t.c("muted"))
            if kw + 4 + c.stringWidth(v, F, size) <= usable - 11:
                c.drawString(cx + 11 + kw + 4, yy, v)
            else:
                for j, ln in enumerate(simpleSplit(v, F, size, usable - 11)[:2]):
                    c.drawString(cx + 11, yy - leading * 0.75 - j * leading * 0.75, ln)
        self.y = y0 - sum(rh) - space_after

    # --- capa
    def cover(self, p: dict[str, Any], foto: Prepared | None) -> None:
        c = self.cv; t = self.t
        c.setFillColor(t.c("cover_bg")); c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFillColor(t.c("accent")); c.rect(0, H - 3, W, 3, fill=1, stroke=0)
        lw, lh = 150, 34; lx = (W - lw) / 2; ly = H - 62
        if t.cover_logo_bg:
            c.setFillColor(HexColor(t.cover_logo_bg)); c.roundRect(lx - 10, ly - 6, lw + 20, lh + 12, 7, fill=1, stroke=0)
        self._logo(lx, ly, lw, lh, t.c("cover_text"), align="center")
        if foto:
            iw, ih = foto.image.size; s = min((CW - 40) / iw, 330 / ih); w, h = iw * s, ih * s
            c.drawImage(foto.reader(), (W - w) / 2, H - 118 - h, width=w, height=h, mask="auto")
        ty = 230
        c.setFont(FB, 11); c.setFillColor(t.c("cover_muted")); c.drawString(ML, ty + 54, p["categoria"][:95])
        c.setFont(F, 9); c.drawString(ML, ty + 38, p["subtitulo"][:120])
        c.setFont(FB, 18 if len(p["modelo"]) <= 40 else 14); c.setFillColor(t.c("cover_text")); c.drawString(ML, ty, p["modelo"])
        for i, tag in enumerate(p["tags"][:4]):
            x = ML if i % 2 == 0 else W / 2; yo = ty - 28 if i < 2 else ty - 48
            tw = min(c.stringWidth(tag, F, 7.5) + 16, W / 2 - ML - 6)
            c.setStrokeColor(t.c("cover_tag_border")); c.setFillColor(t.c("cover_bg"))
            c.roundRect(x, yo, tw, 16, 3, fill=1, stroke=1)
            c.setFillColor(t.c("cover_text")); c.setFont(F, 7.5); c.drawString(x + 8, yo + 4.5, tag)
        by = ty - 70
        for feat in p["features"][:6]:
            c.setFillColor(t.c("accent")); c.circle(ML + 4, by + 4, 3.5, fill=1, stroke=0)
            c.setFillColor(t.c("cover_text")); c.setFont(F, 8.5)
            c.drawString(ML + 13, by, simpleSplit(feat, F, 8.5, CW - 13)[0]); by -= 15
        c.setFillColor(t.c("cover_muted")); c.setFont(F, 7)
        c.drawCentredString(W / 2, 16, "  ·  ".join(x for x in (t.telefone, t.site, t.email) if x) or t.brand)
        c.showPage()


# ----------------------------------------------------------------------------- montagem
@dataclass
class DatasheetResult:
    pdf: bytes
    filename: str
    avisos: list[str]
    pendencias: list[str]
    conferencia_fontes: str
    previews: list[bytes]  # PNG de cada página, para revisão visual (pelo Claude ou por pessoa)


def _contact(fl: Flow, p: dict[str, Any]) -> None:
    t = fl.t
    fl.section(t.titulo_contato or f"Fale com a {t.brand}", space_before=6)
    for par in t.fechamento:
        fl.paragraph(par, size=8, space_after=6)
    kv = [(k, v) for k, v in (("Telefone:", t.telefone), ("Site:", t.site), ("E-mail:", t.email),
                              ("Endereço:", t.endereco), ("Cidade:", t.cidade), ("Modelo:", p["modelo"])) if v]
    fl.y -= 4; fl.kv_two_col(kv)
    if t.assinatura:
        fl.paragraph(t.assinatura, size=8, bold=True, color=t.c("text"))


def render_datasheet(data: dict[str, Any], theme: Theme, anexos: dict[str, bytes] | list[bytes] | None = None,
                     codigo: str | None = None, previews: bool = True) -> DatasheetResult:
    if isinstance(anexos, list):
        anexos = {f"img_{i:02d}.jpg": b for i, b in enumerate(anexos, start=1)}
    anexos = anexos or {}
    p = normalize(data, codigo)
    avisos: list[str] = []
    imgs = prepare_images(p, anexos, theme, avisos)

    def by(*papeis: str) -> list[Prepared]:
        return [i for i in imgs if i.papel in papeis]

    capa = (by("capa") or by("perspectiva") or by("frontal") or [None])[0]
    if capa is None:
        avisos.append("Nenhuma imagem para a capa.")
    for f in p["features"]:
        if len(f) > 95:
            avisos.append(f'Feature da capa com {len(f)} caracteres (máx. 95): "{f[:40]}..."')

    buf = io.BytesIO()
    fl = Flow(buf, theme, p["modelo_cabecalho"])
    fl.cover(p, capa)

    fl.new_page("Descrição do Produto")
    fl.section("Descrição do Produto")
    for par in p["descricao"]:
        fl.paragraph(par, space_after=9)

    if p["nivel"] == "resumido":
        if p["caracteristicas"]:
            fl.section(p["titulo_caracteristicas"], space_before=4); fl.bullets(p["caracteristicas"])
        _contact(fl, p)
    else:
        if p["caracteristicas"] or p["tabelas"]:
            fl.new_page("Destaques")
            if p["caracteristicas"]:
                fl.section(p["titulo_caracteristicas"]); fl.bullets(p["caracteristicas"])
            for tb in p["tabelas"]:
                fl.section(_t(tb.get("titulo")) or "Tabela", space_before=6)
                fl.grid_table(tb.get("cabecalho") or [], tb.get("linhas") or [], tb.get("larguras"))
                if tb.get("nota"):
                    fl.paragraph(_t(tb["nota"]), size=7.5, space_after=6, color=HexColor("#666666"))

        if p["especificacoes"]:
            fl.new_page("Especificações Técnicas"); fl.section("Especificações Técnicas")
            fl.spec_table(p["especificacoes"])

        vistas = [i for i in by("multivista", "perspectiva", "frontal", "traseira", "lateral", "superior",
                                "inferior", "detalhe") if i is not capa]
        painel = by("painel_io")
        if vistas or painel or p["conectores"]:
            fl.new_page("Vistas do Produto")
            if vistas:
                fl.section("Vistas do Produto")
                for v in [v for v in vistas if v.wide]:
                    fl.image(v, max_h=170)
                outras = [v for v in vistas if not v.wide]
                for k in range(0, len(outras), 2):
                    par = outras[k:k + 2]
                    if len(par) == 2:
                        fl.image_row(par)
                    else:
                        fl.image(par[0], max_w=CW * 0.7, max_h=220)
            for v in painel:
                fl.section(v.legenda or "Painel de Conexões", space_before=4)
                v.legenda = ""; fl.image(v, max_h=260)
            for g in p["conectores"]:
                fl.section(_t(g.get("grupo")) or "Conectores", space_before=4)
                fl.kv_two_col([(_t(a), _t(b)) for a, b in (g.get("itens") or [])])

        dims = by("dimensoes")
        if dims or p["dimensoes"]:
            fl.new_page("Dimensões Mecânicas"); fl.section("Dimensões  ·  unidade: mm")
            for v in dims:
                fl.image(v, max_h=320)
            if p["dimensoes"]:
                fl.section("Tabela de Dimensões"); fl.spec_table(p["dimensoes"])

        fl.new_page("Informações Adicionais")
        if p["pedido"]:
            fl.section("Informações de Pedido")
            pd = p["pedido"]; fl.grid_table(pd.get("cabecalho") or [], pd.get("linhas") or [], pd.get("larguras"))
        for titulo, chave in (("Acessórios", "acessorios"), ("Aplicações e Uso", "aplicacoes"), ("Notas", "notas")):
            if p[chave]:
                fl.section(titulo, space_before=4); fl.bullets(p[chave])
        acc = by("acessorio")
        if acc:
            fl.image_row(acc[:3], max_h=110)
        if p["slogan"]:
            fl.paragraph(p["slogan"], size=9, bold=True, color=theme.c("text"), space_after=10)
        _contact(fl, p)

    fl.finish()
    pdf = buf.getvalue()

    pngs: list[bytes] = []
    try:
        import pymupdf
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        texto = ""
        for i, pg in enumerate(doc):
            texto += pg.get_text()
            if previews:
                pngs.append(pg.get_pixmap(dpi=90).tobytes("png"))
            if i > 0:
                corpo = sum(len(b[4]) for b in pg.get_text("blocks") if 40 < b[1] < 800)
                area = sum(r.width * r.height for im in pg.get_images() for r in pg.get_image_rects(im[0]) if 40 < r.y0 < 790)
                if corpo < 600 and area < 60000:
                    avisos.append(f"Página {i + 1} quase vazia: revisar tamanhos de imagem/tabela.")
        for termo in p["termos_proibidos"]:
            if termo.lower() in texto.lower():
                avisos.append(f'Termo proibido encontrado no PDF: "{termo}".')
    except ImportError:
        avisos.append("PyMuPDF não instalado: prévias e verificações automáticas desativadas.")

    nome = re.sub(r"[^A-Za-z0-9._-]+", "_", p["codigo"] or p["modelo"]).strip("_-") or "produto"
    return DatasheetResult(pdf, f"{nome}_Datasheet.pdf", avisos, p["pendencias"], p["conferencia_fontes"], pngs)


def build_datasheet(product: dict[str, Any], theme: Theme, output_dir: str | os.PathLike[str] = ".",
                    anexos: dict[str, bytes] | list[bytes] | None = None) -> str:
    """Compatibilidade com a assinatura antiga: grava o PDF em output_dir e devolve o caminho.
    Se o produto vier com main_image/gallery (caminhos), eles viram os anexos."""
    if anexos is None:
        paths = [x for x in [product.get("main_image"), *(product.get("gallery") or [])] if x]
        anexos = [Path(x).read_bytes() for x in paths if Path(x).exists()]
    res = render_datasheet(product, theme, anexos, codigo=product.get("codigo"), previews=False)
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    final = out / res.filename
    final.write_bytes(res.pdf)
    return str(final)
