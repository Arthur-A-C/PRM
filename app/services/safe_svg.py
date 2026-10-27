"""SVG → PNG for the image tools: sanitize, then rasterize offline with resvg.

Supplier SVGs (Illustrator, Inkscape, CorelDRAW exports) carry XML declarations, DOCTYPEs with internal
entities, comments, editor metadata and <style> classes. Those are removed or expanded, not refused.
Active or resource-loading content is removed before rendering: scripts, event handlers, javascript:,
foreignObject, animations, every href that is not an internal #id (or an embedded raster data: image),
url()/@import pointing outside the document, processing instructions and xml:base. External or
parameter entities make that one file fail (they are never resolved). resvg has no network loader and
never runs scripts; after sanitizing nothing is left that it could read from disk.
"""
import io
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
MAX_NODES = 100_000
MAX_DEPTH = 128
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"
FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
# Static drawing vocabulary. Anything else (script, foreignObject, animate/set, iframe, editor metadata…) is dropped.
TAGS = set("""svg g defs symbol use switch a view title desc style path rect circle ellipse line polyline polygon
text tspan textPath linearGradient radialGradient stop clipPath mask pattern marker image filter feBlend
feColorMatrix feComponentTransfer feComposite feConvolveMatrix feDiffuseLighting feDisplacementMap
feDistantLight feDropShadow feFlood feFuncA feFuncB feFuncG feFuncR feGaussianBlur feImage feMerge
feMergeNode feMorphology feOffset fePointLight feSpecularLighting feSpotLight feTile feTurbulence""".split())
PREDEFINED = {"amp", "lt", "gt", "quot", "apos"}
RASTER_DATA = re.compile(r"\s*data:image/(png|jpeg|jpg|gif|webp)\s*;\s*base64\s*,", re.I)
LOCAL_REF = re.compile(r"\s*#[A-Za-z_][\w.:-]*\s*")
LOCAL_URL = re.compile(r"url\(\s*['\"]?#[A-Za-z_][\w.:-]*['\"]?\s*\)", re.I)
DANGER = re.compile(r"url\s*\(|@import|javascript:|vbscript:|expression\s*\(|-moz-binding|behavior\s*:", re.I)
REF = re.compile(r"&([A-Za-z_][\w.-]*);")


class SvgError(ValueError):
    pass


def _decode(content):
    if content[:2] in {b"\xff\xfe", b"\xfe\xff"}:
        return content.decode("utf-16")
    declared = re.match(rb"\s*<\?xml[^>]*encoding\s*=\s*[\"']([A-Za-z0-9._-]+)[\"']", content.removeprefix(b"\xef\xbb\xbf"))
    encoding = declared.group(1).decode("ascii") if declared else "utf-8-sig"
    try:
        return content.decode("utf-8-sig" if encoding.lower() in {"utf-8", "utf8"} else encoding)
    except (LookupError, UnicodeError):
        raise SvgError("codificação de texto não suportada") from None


def _doctype_end(text, start):
    """Index after the DOCTYPE starting at `start`, honouring quotes and the [internal subset]."""
    quote, depth = None, 0
    for index in range(start + 9, len(text)):
        char = text[index]
        if quote:
            quote = None if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == ">" and depth <= 0:
            return index + 1
    raise SvgError("DOCTYPE incompleto")


def _entities(subset, removed):
    """Internal general entities (e.g. Illustrator's ns_svg) become plain text; anything external fails."""
    subset = re.sub(r"<!--.*?-->", "", subset, flags=re.S)
    values = {}
    for match in re.finditer(r"<!ENTITY\s+(%\s*)?([A-Za-z_][\w.-]*)\s+(.*?)>", subset, re.S):
        parameter, name, rest = match.groups()
        literal = re.fullmatch(r"\s*(\"[^\"]*\"|'[^']*')\s*", rest)
        if parameter or not literal:
            raise SvgError("entidade externa ou de parâmetro não permitida")
        values[name] = literal.group(1)[1:-1]
    def expand(name, seen):
        # Bounded nesting and size: no loops, no "billion laughs".
        if name in seen or len(seen) > 4:
            raise SvgError("entidade recursiva ou grande demais")
        value = REF.sub(lambda m: expand(m.group(1), seen + (name,)) if m.group(1) in values else m.group(0), values[name])
        if len(value) > 4096:
            raise SvgError("entidade recursiva ou grande demais")
        return value
    expanded = {name: expand(name, ()) for name in values}
    if expanded:
        removed.add("entidades internas expandidas")
    return expanded


def _prepare(text, removed):
    """Drop prolog noise (PIs, DOCTYPE) and expand safe internal entities before any XML parser runs."""
    if "<?" in text:
        removed.add("declaração XML/instruções de processamento")
    text = re.sub(r"<\?.*?\?>", "", text, flags=re.S)  # <?xml ...?>, <?xml-stylesheet href=...?>: never followed
    entities = {}
    match = re.search(r"<!DOCTYPE", text, re.I)
    if match:
        end = _doctype_end(text, match.start())
        doctype = text[match.start():end]
        subset = doctype[doctype.find("[") + 1:doctype.rfind("]")] if "[" in doctype else ""
        entities = _entities(subset, removed)
        text = text[:match.start()] + text[end:]
        removed.add("DOCTYPE")
        if re.search(r"<!DOCTYPE|<!ENTITY", text, re.I):
            raise SvgError("mais de um DOCTYPE")
    if entities:
        escape = {k: v.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;") for k, v in entities.items()}
        text = REF.sub(lambda m: escape.get(m.group(1), m.group(0)), text)
        if len(text) > 3 * MAX_BYTES:
            raise SvgError("expansão de entidades grande demais")
    if "<!--" in text:
        removed.add("comentários")
    return text


def _clean_css(css, removed):
    """Keep drawing declarations; drop @import/@font-face and any url() that is not an internal #id."""
    original = css
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@(import|namespace|charset)[^;{}]*;?|@font-face\s*\{[^}]*\}", "", css, flags=re.I)
    if css != re.sub(r"/\*.*?\*/", "", original, flags=re.S):
        removed.add("regras @ de CSS")

    def declarations(block):
        kept = []
        for item in block.split(";"):
            if DANGER.search(LOCAL_URL.sub("", item)):
                removed.add("referências externas em CSS")
            elif item.strip():
                kept.append(item.strip())
        return ";".join(kept)

    css = re.sub(r"\{([^{}]*)\}", lambda m: "{" + declarations(m.group(1)) + "}", css) if "{" in css else declarations(css)
    if DANGER.search(LOCAL_URL.sub("", css)):
        removed.add("referências externas em CSS")
        return None  # leftovers we cannot place: drop the whole stylesheet rather than guess
    return css


def _local(name):
    return name.rsplit("}", 1)[-1]


def _namespace(name):
    return name[1:].split("}", 1)[0] if name.startswith("{") else ""


def _clean_tree(root, removed):
    nodes, stack = 0, [(root, 0)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise SvgError("SVG complexo demais")
        for child in list(node):
            if _namespace(child.tag) != SVG_NS or _local(child.tag) not in TAGS:
                removed.add("elemento " + _local(child.tag) if _namespace(child.tag) == SVG_NS else "metadados do editor")
                node.remove(child)
            else:
                stack.append((child, depth + 1))
        tag = _local(node.tag)
        for key in list(node.attrib):
            value, name, namespace = node.attrib[key], _local(key).lower(), _namespace(key)
            drop = None
            if namespace not in {"", XLINK_NS, XML_NS} or (namespace == XML_NS and name == "base"):
                drop = "atributos do editor/xml:base"
            elif name.startswith("on"):
                drop = "eventos (on*)"
            elif name in {"href", "src"}:
                if not (LOCAL_REF.fullmatch(value) or (tag in {"image", "feImage"} and RASTER_DATA.match(value))):
                    drop = "referências externas (href)"
            elif name == "style":
                css = _clean_css(value, removed)
                if css is None:
                    drop = "estilo com referência externa"
                else:
                    node.set(key, css)
            elif DANGER.search(LOCAL_URL.sub("", value)):
                drop = "atributos com referência externa"
            if drop:
                removed.add(drop)
                del node.attrib[key]
        if tag == "style":
            css = _clean_css("".join(node.itertext()), removed)
            for child in list(node):
                node.remove(child)
            node.text = css or ""


def sanitize_svg(content):
    """Clean SVG markup ready for rendering, plus the sorted list of what was removed (for the manifest)."""
    if len(content) > MAX_BYTES:
        raise SvgError("SVG excede 20 MiB")
    removed = set()
    text = _prepare(_decode(content), removed)
    try:
        root = ET.fromstring(text)  # no DOCTYPE left: expat has no entity to resolve
    except ET.ParseError:
        raise SvgError("XML inválido ou incompleto") from None
    for element in root.iter():  # <svg> written without xmlns is still SVG
        if not element.tag.startswith("{"):
            element.tag = "{%s}%s" % (SVG_NS, element.tag)
    if _local(root.tag) != "svg":
        raise SvgError("o elemento raiz não é <svg>")
    _clean_tree(root, removed)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    return ET.tostring(root, encoding="unicode"), sorted(removed)


def validate_svg(content):
    """Raises ValueError when the file cannot be prepared for rendering; returns the sanitized markup."""
    return sanitize_svg(content)[0].encode("utf-8")


def _render(markup, **fit):
    import resvg_py
    # System fonts skipped: same output on Windows and in Docker; text falls back to the bundled DejaVu.
    return bytes(resvg_py.svg_to_bytes(svg_string=markup, background="#ffffff", skip_system_fonts=True,
                                       font_files=[str(p) for p in sorted(FONTS.glob("*.ttf"))],
                                       font_family="DejaVu Sans", sans_serif_family="DejaVu Sans", **fit))


def render_svg(content, size, details=None):
    """PNG whose longer side is `size`, proportional, on white. `details` receives the sanitizing report."""
    from PIL import Image
    markup, removed = sanitize_svg(content)
    if details is not None:
        details["sanitized"] = removed
    try:
        rendered = _render(markup, width=size)
        with Image.open(io.BytesIO(rendered)) as probe:
            width, height = probe.size
        if not all(math.isfinite(x) and x > 0 for x in (width, height)):
            raise SvgError("dimensões inválidas")
        return rendered if height <= size else _render(markup, height=size)
    except SvgError:
        raise
    except Exception:
        raise SvgError("o conteúdo gráfico não pôde ser renderizado") from None
