"""Extrai Portwell, Choice e SAG de um lockup (logos escuras sobre fundo claro).

Uso: python -m scripts.extract_brand_logos --source CAMINHO.png [--portwell OFICIAL.png] [--output app/static/brand]

- Separa as marcas pelos traços verticais finos entre elas (ou pelos maiores vãos).
- Converte a luminância em canal alfa: o desenho e o antisserrilhado originais são
  preservados; o fundo claro vira transparência real. A tinta é preta pura e o tema
  da interface decide a cor final via CSS.
- Não altera o arquivo de origem.
"""

import argparse
from pathlib import Path

from PIL import Image

NAMES = ("portwell", "choice", "sag")


def ink_alpha(gray: int, paper: int, ink: int) -> int:
    if gray >= paper:
        return 0
    if gray <= ink:
        return 255
    return round(255 * (paper - gray) / (paper - ink))


def runs(values, minimum=1):
    found, start = [], None
    for index, value in enumerate(list(values) + [0]):
        if value >= minimum and start is None:
            start = index
        elif value < minimum and start is not None:
            found.append((start, index - 1))
            start = None
    return found


def split_groups(gray: Image.Image, threshold: int):
    width, height = gray.size
    px = gray.load()
    columns = [sum(1 for y in range(height) if px[x, y] < threshold) for x in range(width)]
    rows = [y for y in range(height) if any(px[x, y] < threshold for x in range(0, width, 2))]
    content = rows[-1] - rows[0] + 1
    segments = runs(columns)
    separators = [(a, b) for a, b in segments
                  if b - a + 1 <= max(3, width // 150) and max(columns[a:b + 1]) >= 0.6 * content]
    if len(separators) >= 2:
        cuts = sorted(separators)[:2]
        bounds = [(0, cuts[0][0] - 1), (cuts[0][1] + 1, cuts[1][0] - 1), (cuts[1][1] + 1, width - 1)]
    else:
        inked = [s for s in segments if s not in separators]
        gaps = sorted(((inked[i + 1][0] - inked[i][1], i) for i in range(len(inked) - 1)), reverse=True)[:2]
        splits = sorted(i for _, i in gaps)
        bounds = [(inked[0][0], inked[splits[0]][1]), (inked[splits[0] + 1][0], inked[splits[1]][1]),
                  (inked[splits[1] + 1][0], inked[-1][1])]
    separator_columns = {x for a, b in separators for x in range(a - 4, b + 5)}  # inclui o halo
    return bounds, separator_columns


def extract(source: Path, output: Path, paper: int = 236, ink: int = 40, pad: int = 4, overrides=None):
    image = Image.open(source).convert("L")
    bounds, separator_columns = split_groups(image, threshold=(paper + ink) // 2)
    output.mkdir(parents=True, exist_ok=True)
    width, height = image.size
    px = image.load()
    results = {}
    for name, (left, right) in zip(NAMES, bounds):
        alpha = Image.new("L", image.size, 0)
        apx = alpha.load()
        for x in range(max(0, left), min(width, right + 1)):
            if x in separator_columns:
                continue
            for y in range(height):
                apx[x, y] = ink_alpha(px[x, y], paper, ink)
        box = alpha.getbbox()
        if box is None:
            raise ValueError(f"Nenhum traço encontrado para {name}.")
        box = (max(0, box[0] - pad), max(0, box[1] - pad), min(width, box[2] + pad), min(height, box[3] + pad))
        logo = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
        logo.putalpha(alpha.crop(box))
        target = output / f"{name}.png"
        logo.save(target, optimize=True)
        results[name] = logo.size
        print(f"{name}: {logo.size[0]}x{logo.size[1]} -> {target}")
    scale = {name: h for name, (_, h) in results.items()}  # altura relativa vem do lockup
    for name, path in (overrides or {}).items():
        results[name] = replace_with_official(path, output / f"{name}.png", height=scale[name] * 2)
        print(f"{name}: arquivo oficial {path} -> {results[name][0]}x{results[name][1]}")
    tallest = max(scale.values())
    lines = ["/* Gerado por scripts.extract_brand_logos — não editar à mão.",
             "   --brand-h preserva a escala relativa das marcas no arquivo de origem. */"]
    for name, (w, h) in results.items():
        lines.append(f".brand-logo-{name} {{ aspect-ratio: {w} / {h}; --brand-h: {scale[name] / tallest:.4f}; }}")
    (output / "brand.css").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def replace_with_official(path: Path, target: Path, height: int):
    """Usa um arquivo isolado (alfa ou fundo claro) como fonte fiel; mantém a altura do lockup."""
    image = Image.open(path)
    if image.mode == "RGBA" and image.getchannel("A").getextrema()[0] < 255:
        alpha = image.getchannel("A")
    else:
        gray = image.convert("L")
        alpha = gray.point(lambda g: ink_alpha(g, 236, 40))
    box = alpha.getbbox()
    alpha = alpha.crop(box)
    inner = height - 8  # mesmo respiro de 4 px do recorte do lockup, em escala 2x
    width = round(alpha.width * inner / alpha.height)
    alpha = alpha.resize((width, inner), Image.LANCZOS)
    logo = Image.new("RGBA", (width + 8, height), (0, 0, 0, 0))
    canvas = Image.new("L", logo.size, 0)
    canvas.paste(alpha, (4, 4))
    logo.putalpha(canvas)
    logo.save(target, optimize=True)
    return logo.size


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("app/static/brand"))
    parser.add_argument("--portwell", type=Path, help="Logo Portwell oficial isolada (substitui o recorte do lockup)")
    args = parser.parse_args()
    extract(args.source, args.output, overrides={"portwell": args.portwell} if args.portwell else None)


if __name__ == "__main__":
    main()
