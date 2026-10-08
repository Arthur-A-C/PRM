"""Teste rápido: python -m pytest tests/test_datasheets.py (rodar na raiz do PRM)."""
import io

from PIL import Image

from app.services.datasheet_choice import generate_choice_datasheet_full
from app.services.datasheet_portwell import generate_portwell_datasheet, generate_portwell_datasheet_full
from app.services.datasheet_sag import generate_sag_datasheet


def _foto(cor=(60, 60, 60)) -> bytes:
    im = Image.new("RGB", (800, 600), "white")
    im.paste(Image.new("RGB", (500, 350), cor), (150, 120))
    buf = io.BytesIO(); im.save(buf, format="JPEG"); return buf.getvalue()


NOVO = {
    "modelo": "WEBS-TESTE", "nivel": "completo", "categoria": "Box PC Industrial",
    "subtitulo": "Intel Core i5  ·  6× COM", "tags": ["a", "b", "c", "d"], "features": ["Fanless — teste"],
    "descricao": ["Parágrafo — com travessão."], "caracteristicas": [["Fanless: ", "sem ventoinha"]],
    "especificacoes": [{"secao": "Sistema"}, {"chave": "CPU", "valor": "i5-1235U"}],
    "imagens": [{"arquivo": "img_01.jpg", "papel": "capa", "legenda": "Vista", "fundo": "branco_liso",
                 "remover_fundo": True, "marcas": [{"caixa": [0.4, 0.4, 0.6, 0.5], "acao": "apagar"}],
                 "textos": [{"caixa": [0.1, 0.05, 0.5, 0.12], "original": "Power", "traducao": "Energia"}]},
                {"arquivo": "img_02.jpg", "papel": "traseira", "legenda": "Traseira"}],
    "termos_proibidos": ["FABRICANTEX"], "pendencias": ["teste"],
}
LEGADO = {"model": "X1", "categoria": "Produto", "intro": "Texto", "beneficios": [{"titulo": "A", "descricao": "B"}],
          "specs": [{"secao": "S", "itens": [{"campo": "C", "valor": "V"}, "Peso: 1 kg"]}]}


def test_novo_formato():
    r = generate_portwell_datasheet_full(NOVO, {"img_01.jpg": _foto(), "img_02.jpg": _foto((90, 90, 90))}, codigo="123")
    assert r.pdf.startswith(b"%PDF") and r.filename == "123_Datasheet.pdf" and r.previews
    r2 = generate_choice_datasheet_full(NOVO, {"img_01.jpg": _foto()})
    assert r2.pdf.startswith(b"%PDF")


def test_formato_antigo():
    assert generate_portwell_datasheet(LEGADO, [_foto(), _foto()]).startswith(b"%PDF")
    assert generate_sag_datasheet(LEGADO, [_foto()], codigo="ABC").startswith(b"%PDF")
