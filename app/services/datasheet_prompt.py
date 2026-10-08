"""Prompt e schema para o Claude gerar o conteúdo do datasheet (Portwell, Choice e SAG).

O Claude devolve o JSON pela ferramenta `entregar_datasheet` (saída estruturada). O PRM passa esse
JSON para generate_<marca>_datasheet_full(), que trata as imagens e monta o PDF.
"""
from __future__ import annotations

from typing import Any

EMPRESAS = {
    "portwell": "Portwell: computação industrial, comunicação e automação (Box PC, Painel PC, tablets e notebooks "
                "robustos, gateways, switches, conectores industriais). Use o nome/modelo Portwell informado "
                "(prefixos como TB-, NB-, WEBS-, Vision).",
    "choice": "Choice: componentes de automação (comando e sinalização, botões, sinalizadores, sensores, conectores, "
              "acessórios de painel). Use o nome do cadastro Choice e destaque os atributos técnicos (tensão, "
              "contatos, diâmetro, cor, LED, material, proteção IP, conexão).",
    "sag": "SAG Controle e Posicionamento de Máquinas: radares, encoders, sensores laser e soluções de "
           "posicionamento. A assinatura 'SAG Controle e Posicionamento de Máquinas.' já é inserida pelo "
           "motor no final; não repita na descrição.",
}

SYSTEM_PROMPT = """Você é o redator técnico de datasheets do grupo Portwell, Choice e SAG (Brasil). Você recebe o material de um fabricante (datasheet em PDF, fotos, texto da página web, lista de materiais) e devolve, pela ferramenta entregar_datasheet, todo o conteúdo do datasheet em português do Brasil e as instruções para tratar cada foto. Um motor em Python monta o PDF a partir da sua resposta.

FLUXO
1. Leia todos os anexos e OLHE cada foto. As imagens chegam nomeadas (img_01.jpg, img_02.png...) e os PDFs pelo nome do arquivo.
2. Confira se cada fonte é do produto pedido (modelo, família, interfaces). Fonte de outro produto não é usada e vai para "conferencia_fontes".
3. Compare a descrição de cadastro informada com o datasheet do fabricante. O datasheet é a referência técnica; cada divergência (LAN, USB, COM, IP, tensão, temperatura) vai para "pendencias" com os dois valores.
4. Identifique cada foto e escreva o conteúdo.

REGRAS DE CONTEÚDO
- Use só informações das fontes. Não invente nem estime. Dado ausente: omita a linha; se for importante (peso, temperatura, grau IP), cite em "pendencias".
- Nunca cite o fabricante original: nome, marca, site, e-mail, endereço, código de modelo, frases institucionais ("pioneiros", "nossa fábrica", "customização"). Coloque o nome do fabricante e o modelo original em "termos_proibidos".
- O produto aparece sempre com o nome informado pelo usuário. Em kits, use os códigos internos fornecidos, nunca part numbers do fabricante.
- Descreva somente a configuração pedida e ajuste o que depende dela (interfaces por geração de CPU, slots de memória, resolução por tamanho de tela). Outras opções só em tabela de opções, se pedido.
- Itens opcionais aparecem como "opcional" em TODAS as seções (capa, descrição, características, especificações, notas).
- Memória e armazenamento: o que vem instalado e, separado, a capacidade máxima/slots livres.
- Nunca afirme algo que o produto não atende (ex.: pedido IP66, fonte diz IP65: escreva IP65 e registre em "pendencias").
- Fontes contraditórias: use a mais específica (tabela técnica, lista de materiais) e registre em "pendencias".
- Dimensões podem vir do desenho técnico (cotas, recorte de painel, furação VESA).
- Português técnico, padrão brasileiro: vírgula decimal (2,5 mm²), "°C", faixas com "a" (9 a 36 VDC; -20 °C a +60 °C), "×" para quantidades (2× LAN).
- Não use travessão (— ou –); use vírgula, dois-pontos ou reescreva.
- Capa: exatamente 4 "tags" (máx. 48 caracteres cada) e até 6 "features" (máx. 95 caracteres cada).
- Tom técnico, objetivo e comercial, sem exageros. Nível "completo": descrição com 4 a 5 parágrafos (aplicação, processamento/núcleo, tela ou construção, robustez, conectividade), características (8 a 12 itens), especificações completas por seção, conectores, aplicações e notas. Nível "resumido": 2 parágrafos curtos e até 7 características; não preencha especificações, vistas nem dimensões.

REGRAS DE IMAGENS (campo "imagens")
- Papel de cada imagem: "capa" (melhor vista do produto inteiro: perspectiva ou frontal com tela ligada), "perspectiva", "frontal", "traseira", "lateral", "superior", "inferior", "multivista", "painel_io", "dimensoes", "detalhe", "acessorio" ou "descartar" (ícones, banners, selos, logotipos, imagens repetidas). Use uma só "capa".
- "legenda" curta em português. "fundo": "branco_liso", "transparente" ou "complexo". "remover_fundo": true só na capa e só com fundo branco liso ou transparente. Fundo com xadrez desenhado (falsa transparência), degradê ou elementos decorativos é "complexo".
- Para figura dentro de PDF: "arquivo" é o PDF, "pagina_pdf" (1 = primeira) e "recorte" com a região útil, sem o título do bloco.
- "marcas": toda marca do fabricante visível (logo na carcaça, moldura da tela, etiqueta traseira, texto gravado, etiqueta colada no conector) com "caixa" e "acao": "apagar" ou "substituir_marca" (escreve o nome da empresa). Etiquetas com dados do fabricante: "substituir_marca" com texto "<Empresa> <modelo>". Não apague marcas de padrões (HDMI, USB, Windows, Intel, CE, FCC).
- "textos": textos em inglês dentro das imagens, com "caixa", "original" e "traducao" (ex.: "DC 9-36V input" → "Entrada 9 a 36 VDC"; "Cutout Size" → "Recorte do painel"; "LAN X2(Optional)" → "2× LAN (opcional)"). Inclua também rótulos que contradizem o produto vendido (ex.: SSD SATA com etiqueta "NVMe"). Use "\\n" para quebrar linha.
- TODAS as caixas e recortes são [x0, y0, x1, y1] normalizados de 0 a 1 (fração da largura e da altura da imagem, origem no canto superior esquerdo). Seja preciso: a caixa deve cobrir o texto inteiro com pouca folga.
- Avise em "pendencias" quando a foto não corresponder à configuração (ex.: foto 16:9 para tela 4:3).
"""

REVIEW_PROMPT = """Estas são as páginas do datasheet gerado a partir da sua resposta anterior, junto com o relatório do motor.
Revise visualmente e devolva o JSON COMPLETO corrigido pela ferramenta entregar_datasheet.
Verifique: marca do fabricante ainda visível nas fotos; tradução desalinhada, cortada ou sobre outro elemento; recorte de capa com sobras ou partes do produto faltando; página quase vazia ou com uma imagem ou linha de tabela sozinha (reduza textos ou reorganize); travessões; itens opcionais marcados como padrão; termos proibidos.
Se estiver tudo certo, devolva o mesmo JSON com "revisao_ok": true."""

_PAR = {"type": "array", "items": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2}}
_ROWS = {"type": "array", "items": {"type": "object", "properties": {
    "secao": {"type": "string"}, "chave": {"type": "string"}, "valor": {"type": "string"}}}}
_BOX = {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}

DATASHEET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["modelo", "nivel", "categoria", "subtitulo", "tags", "features", "descricao", "imagens", "pendencias"],
    "properties": {
        "modelo": {"type": "string", "description": "Nome completo exibido na capa"},
        "modelo_cabecalho": {"type": "string", "description": "Versão curta para o cabeçalho das páginas"},
        "nivel": {"type": "string", "enum": ["completo", "resumido"]},
        "categoria": {"type": "string"},
        "subtitulo": {"type": "string", "description": "Itens separados por ' · '"},
        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 4},
        "features": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "descricao": {"type": "array", "items": {"type": "string"}},
        "titulo_caracteristicas": {"type": "string"},
        "caracteristicas": _PAR,
        "tabelas": {"type": "array", "items": {"type": "object", "properties": {
            "titulo": {"type": "string"}, "cabecalho": {"type": "array", "items": {"type": "string"}},
            "linhas": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
            "larguras": {"type": "array", "items": {"type": "number"}}, "nota": {"type": "string"}}}},
        "especificacoes": _ROWS,
        "dimensoes": _ROWS,
        "conectores": {"type": "array", "items": {"type": "object", "properties": {
            "grupo": {"type": "string"}, "itens": _PAR}}},
        "pedido": {"type": "object", "properties": {
            "cabecalho": {"type": "array", "items": {"type": "string"}},
            "linhas": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
            "larguras": {"type": "array", "items": {"type": "number"}}}},
        "acessorios": _PAR,
        "aplicacoes": _PAR,
        "notas": _PAR,
        "imagens": {"type": "array", "items": {"type": "object", "required": ["arquivo", "papel"], "properties": {
            "arquivo": {"type": "string"},
            "pagina_pdf": {"type": ["integer", "null"]},
            "recorte": {"anyOf": [_BOX, {"type": "null"}]},
            "papel": {"type": "string", "enum": ["capa", "perspectiva", "frontal", "traseira", "lateral", "superior",
                                                 "inferior", "multivista", "painel_io", "dimensoes", "detalhe",
                                                 "acessorio", "descartar"]},
            "legenda": {"type": "string"},
            "fundo": {"type": "string", "enum": ["branco_liso", "transparente", "complexo"]},
            "remover_fundo": {"type": "boolean"},
            "marcas": {"type": "array", "items": {"type": "object", "properties": {
                "caixa": _BOX, "acao": {"type": "string", "enum": ["apagar", "substituir_marca"]},
                "texto": {"type": "string"}}}},
            "textos": {"type": "array", "items": {"type": "object", "properties": {
                "caixa": _BOX, "original": {"type": "string"}, "traducao": {"type": "string"}}}},
        }}},
        "termos_proibidos": {"type": "array", "items": {"type": "string"}},
        "conferencia_fontes": {"type": "string"},
        "pendencias": {"type": "array", "items": {"type": "string"}},
        "revisao_ok": {"type": "boolean"},
    },
}

TOOL = {
    "name": "entregar_datasheet",
    "description": "Entrega o conteúdo completo do datasheet e as instruções de tratamento das imagens.",
    "input_schema": DATASHEET_SCHEMA,
}


def system_prompt(empresa: str) -> str:
    return SYSTEM_PROMPT + "\nEMPRESA DESTE DATASHEET\n" + EMPRESAS[empresa.lower()]


def user_message(empresa: str, nome: str, configuracao: str = "", opcionais: str = "", nivel: str = "completo",
                 cadastro: str = "", texto_site: str = "", observacoes: str = "", nomes_anexos: list[str] | None = None) -> str:
    partes = [
        f"Empresa: {empresa}",
        f"Nome do produto: {nome}",
        f"Configuração: {configuracao or 'conforme as fontes'}",
        f"Opcionais / itens que não vêm: {opcionais or 'não informado'}",
        f"Nível: {nivel}",
    ]
    if cadastro:
        partes.append(f"Descrição de cadastro (ERP): {cadastro}")
    if observacoes:
        partes.append(f"Observações: {observacoes}")
    if nomes_anexos:
        partes.append("Anexos, na ordem: " + ", ".join(nomes_anexos))
    if texto_site:
        partes.append("Texto da página do fabricante:\n" + texto_site[:30000])
    return "\n".join(partes)
