from __future__ import annotations

import io
import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader


load_dotenv()

MODEL = os.getenv("QWEN_MODEL", "qwen3.7-flash")


EXTRACTION_SYSTEM_PROMPT = """
Você é um extrator técnico especializado em datasheets industriais.

Você receberá o texto completo extraído de um PDF de fabricante.

Sua função é transformar esse material em TEXTO TÉCNICO ORGANIZADO para
revisão humana.

REGRAS OBRIGATÓRIAS:

1. Use somente informações presentes no documento.
2. Não use conhecimento externo.
3. Não invente nem complete valores ausentes.
4. Preserve números, unidades, códigos, interfaces, normas, frequências,
   temperaturas, dimensões, capacidades e nomes técnicos.
5. Extraia todo conteúdo técnico relevante, sem resumir agressivamente.
6. Remova apenas conteúdo claramente comercial/decorativo, contatos,
   copyright e repetições sem valor técnico.
7. Se o PDF contiver vários modelos da mesma família:
   - mantenha informações comuns à família;
   - mantenha informações específicas do modelo alvo;
   - não atribua ao modelo alvo valores exclusivos de outra variante;
   - quando a relação entre coluna/modelo e valor não estiver clara,
     marque a linha como "REVISAR".
8. Organize o conteúdo por seções técnicas.
9. Responda em português, mantendo termos técnicos originais quando útil.
10. Retorne apenas texto puro, sem JSON e sem bloco Markdown.

FORMATO DESEJADO:

PROCESSADOR
- Campo: valor
- Campo: valor

MEMÓRIA
- Campo: valor

I/O
- Campo: valor

ARMAZENAMENTO
- Campo: valor

EXPANSÃO
- Campo: valor

ALIMENTAÇÃO
- Campo: valor

FÍSICO
- Campo: valor

AMBIENTE
- Campo: valor

CERTIFICAÇÕES
- Campo: valor

Inclua outras seções quando existirem no documento.
""".strip()


ANALYSIS_SYSTEM_PROMPT = """
Você é um estruturador técnico de datasheets industriais.

Você receberá um texto técnico que já foi extraído do datasheet do
fabricante e revisado/ajustado pelo usuário.

Sua tarefa é transformar somente esse texto em JSON estruturado.

REGRAS OBRIGATÓRIAS:

1. Não invente especificações.
2. Não use conhecimento externo.
3. Não complete valores ausentes por suposição.
4. Preserve códigos, modelos, números, unidades, interfaces e normas.
5. O campo "model" deve ser exatamente o nome/modelo informado pelo usuário.
6. Se houver conflito ou conteúdo marcado como REVISAR, registre em "alertas".
7. Retorne somente JSON válido.
8. Não use Markdown.
9. Não escreva texto fora do JSON.

FORMATO OBRIGATÓRIO:

{
  "model": "string",
  "categoria": "string ou null",
  "subtitulo": "string ou null",
  "tags": ["string"],
  "features": ["string"],
  "specs": [
    {
      "secao": "string",
      "itens": [
        {
          "campo": "string",
          "valor": "string"
        }
      ]
    }
  ],
  "intro": "string ou null",
  "beneficios": [
    {
      "titulo": "string",
      "descricao": "string"
    }
  ],
  "aplicacoes": [
    {
      "titulo": "string",
      "descricao": "string"
    }
  ],
  "slogan": "string ou null",
  "alertas": ["string"],
  "nao_informado": ["string"]
}
""".strip()


def _get_client() -> OpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("QWEN_BASE_URL")

    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY não configurada.")

    if not base_url:
        raise ValueError("QWEN_BASE_URL não configurada.")

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


def extract_pdf_text(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        raise ValueError("O PDF enviado está vazio.")

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise ValueError("Não foi possível abrir o PDF enviado.") from exc

    pages: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""

        if text:
            pages.append(
                f"===== PÁGINA {page_number} =====\n{text}"
            )

    full_text = "\n\n".join(pages).strip()

    if not full_text:
        raise ValueError(
            "Não foi possível extrair texto do PDF. "
            "O arquivo pode ser escaneado como imagem ou não possuir camada de texto."
        )

    return full_text


def _clean_json_response(content: str) -> str:
    content = (content or "").strip()

    if content.startswith("```json"):
        content = content[len("```json"):].strip()
    elif content.startswith("```"):
        content = content[len("```"):].strip()

    if content.endswith("```"):
        content = content[:-3].strip()

    # Caso o modelo coloque algum texto antes/depois do objeto.
    first = content.find("{")
    last = content.rfind("}")

    if first != -1 and last != -1 and last > first:
        content = content[first:last + 1]

    return content.strip()


def _parse_json_response(content: str) -> dict[str, Any]:
    cleaned = _clean_json_response(content)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "O Qwen retornou uma resposta que não é JSON válido."
        ) from exc

    if not isinstance(result, dict):
        raise ValueError(
            "A resposta do Qwen não possui um objeto JSON na raiz."
        )

    return result


def extract_specs_text_with_qwen(
    codigo: str,
    nome: str,
    pdf_bytes: bytes,
    pdf_filename: str = "datasheet.pdf",
) -> str:
    codigo = (codigo or "").strip()
    nome = (nome or "").strip()

    if not codigo:
        raise ValueError("Código do produto não informado.")

    if not nome:
        raise ValueError("Nome do produto não informado.")

    pdf_text = extract_pdf_text(pdf_bytes)

    client = _get_client()

    prompt = f"""
MODELO/CÓDIGO ALVO:
{codigo}

NOME DO PRODUTO INFORMADO PELO USUÁRIO:
{nome}

ARQUIVO:
{pdf_filename}

IMPORTANTE SOBRE FAMÍLIAS DE PRODUTOS:
O documento pode conter vários modelos ou variantes.
Considere "{codigo}" e "{nome}" como referências do modelo alvo.
Extraia informações comuns à família e informações específicas do modelo alvo.
Não copie para o modelo alvo valores exclusivos de outras variantes.

CONTEÚDO DO PDF:

{pdf_text}

FIM DO PDF.

Extraia e organize todo o conteúdo técnico relevante seguindo as regras.
""".strip()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": EXTRACTION_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0,
            max_tokens=16000,
        )
    except Exception as exc:
        raise RuntimeError(f"Erro na API do Qwen: {exc}") from exc

    content = response.choices[0].message.content

    if not content or not str(content).strip():
        raise ValueError("O Qwen retornou uma extração vazia.")

    return str(content).strip()


def analyze_product_with_qwen(
    codigo: str,
    nome: str,
    informacoes_adicionais: str = "",
) -> dict[str, Any]:
    codigo = (codigo or "").strip()
    nome = (nome or "").strip()
    informacoes_adicionais = (informacoes_adicionais or "").strip()

    if not codigo:
        raise ValueError("Código do produto não informado.")

    if not nome:
        raise ValueError("Nome do produto não informado.")

    if not informacoes_adicionais:
        raise ValueError(
            "Nenhuma especificação foi informada para análise."
        )

    client = _get_client()

    prompt = f"""
CÓDIGO DO PRODUTO:
{codigo}

NOME/MODELO DEFINIDO PELO USUÁRIO:
{nome}

TEXTO TÉCNICO REVISADO:
{informacoes_adicionais}

Transforme o texto acima no JSON técnico solicitado.

O campo "model" deve ser exatamente:
{nome}

Não invente informações.
""".strip()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": ANALYSIS_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0,
            max_tokens=12000,
        )
    except Exception as exc:
        raise RuntimeError(f"Erro na API do Qwen: {exc}") from exc

    content = response.choices[0].message.content

    if not content:
        raise ValueError("O Qwen retornou uma resposta vazia.")

    result = _parse_json_response(str(content))
    result["model"] = nome


    return result

def extract_and_translate_specs_with_qwen(
    codigo: str,
    nome: str,
    pdf_bytes: bytes,
    pdf_filename: str = "datasheet.pdf",
) -> str:
    codigo = (codigo or "").strip()
    nome = (nome or "").strip()

    if not codigo:
        raise ValueError(
            "Código do produto não informado."
        )

    if not nome:
        raise ValueError(
            "Nome do produto não informado."
        )

    # Primeiro o Python extrai o texto bruto do PDF
    pdf_text = extract_pdf_text(pdf_bytes)

    client = _get_client()

    system_prompt = """
Você é um especialista em documentação técnica industrial.

Você receberá o texto extraído de um datasheet de fabricante.

Sua tarefa é:

1. Traduzir o conteúdo técnico para português do Brasil.
2. Organizar as informações em seções técnicas claras.
3. Manter nomes próprios, modelos e códigos exatamente como aparecem.
4. Manter siglas técnicas quando necessário:
   PCIe, USB, HDMI, DisplayPort, SATA, NVMe, RAID, LAN, BIOS, etc.
5. Não traduzir nomes de tecnologias quando a tradução puder causar perda
   de precisão.
6. Manter todos os números, unidades e valores exatamente como aparecem.
7. Não inventar nenhuma especificação.
8. Não usar conhecimento externo.
9. Não completar informações que não estejam no documento.
10. Quando houver vários modelos no mesmo datasheet, não misturar
    informações exclusivas entre eles.
11. Traduzir títulos, descrições e campos técnicos quando possível.
12. Retornar apenas texto puro.
13. Não utilizar JSON.
14. Não utilizar Markdown com ```.

Organize preferencialmente no formato:

PROCESSADOR
- Campo: valor

CHIPSET
- Campo: valor

MEMÓRIA
- Campo: valor

GRÁFICOS
- Campo: valor

ÁUDIO
- Campo: valor

REDE
- Campo: valor

I/O
- Campo: valor

ARMAZENAMENTO
- Campo: valor

EXPANSÃO
- Campo: valor

ALIMENTAÇÃO
- Campo: valor

CARACTERÍSTICAS FÍSICAS
- Campo: valor

SISTEMA OPERACIONAL
- Campo: valor

AMBIENTE
- Campo: valor

CERTIFICAÇÕES
- Campo: valor

Adicione outras seções quando necessário.

O resultado deve ser escrito em português do Brasil.
""".strip()

    user_prompt = f"""
CÓDIGO/MODELO ALVO:
{codigo}

NOME DEFINIDO PELO USUÁRIO:
{nome}

ARQUIVO:
{pdf_filename}

O datasheet pode conter vários modelos de uma mesma família.

Priorize:

- informações comuns à família;
- informações específicas do modelo {codigo};
- informações específicas do produto {nome}.

Não atribua ao modelo alvo valores que sejam claramente exclusivos
de outra variante.

Traduza e organize TODO o conteúdo técnico relevante abaixo.

========================
INÍCIO DO DATASHEET
========================

{pdf_text}

========================
FIM DO DATASHEET
========================
""".strip()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=0,
            max_tokens=16000,
        )

    except Exception as exc:
        raise RuntimeError(
            f"Erro na API do Qwen: {exc}"
        ) from exc

    content = (
        response
        .choices[0]
        .message
        .content
    )

    if not content:
        raise ValueError(
            "O Qwen retornou uma tradução vazia."
        )

    return str(content).strip()
