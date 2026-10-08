import base64
import json
import os
from typing import Optional

import anthropic
from dotenv import load_dotenv


load_dotenv()


MODEL = "claude-sonnet-5"


SYSTEM_PROMPT = """
Você é responsável por analisar materiais técnicos de produtos industriais
e estruturar as informações para geração automática de datasheets.

REGRAS OBRIGATÓRIAS:

1. Use SOMENTE informações presentes nos materiais fornecidos:
   - PDF;
   - imagens;
   - informações adicionais;
   - código e nome fornecidos pelo usuário.

2. NÃO invente especificações técnicas.

3. NÃO complete informações usando conhecimento externo.

4. NÃO presuma valores que não estejam claramente informados.

5. Se houver conflito entre materiais, não escolha silenciosamente.
   Registre o conflito em "alertas".

6. Fotografias podem ser usadas para compreender visualmente o produto,
   mas não devem ser usadas para inventar especificações técnicas que não
   estejam claramente visíveis ou documentadas.

7. Preserve unidades, padrões, interfaces, nomes de processadores,
   códigos e valores técnicos presentes no material original.

8. O campo "model" deve usar o nome/código definido pelo usuário,
   mesmo que o material do fornecedor utilize outro código semelhante.

9. Retorne SOMENTE JSON válido.
   Não use Markdown.
   Não coloque ```json.
   Não escreva explicações antes ou depois do JSON.

O JSON deve seguir esta estrutura:

{
  "model": "string",
  "categoria": "string ou null",
  "subtitulo": "string ou null",
  "tags": [
    "string"
  ],
  "features": [
    "string"
  ],
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
  "alertas": [
    "string"
  ],
  "nao_informado": [
    "string"
  ]
}

ORIENTAÇÕES DE CONTEÚDO:

"categoria":
Tipo geral do produto com base nos materiais recebidos.

"subtitulo":
Resumo curto contendo apenas características técnicas confirmadas.

"tags":
De 2 a 4 destaques técnicos confirmados.

"features":
Principais características técnicas confirmadas.

"specs":
Organize todas as especificações técnicas relevantes em seções.
Não descarte especificações úteis do material original.

Exemplo:

{
  "secao": "Memória",
  "itens": [
    {
      "campo": "Tecnologia",
      "valor": "DDR5 4800 MHz"
    },
    {
      "campo": "Capacidade",
      "valor": "Até 32 GB"
    }
  ]
}

"intro":
Texto técnico curto descrevendo o produto somente com informações confirmadas.

"beneficios":
Pode explicar benefícios diretamente decorrentes das características
confirmadas, mas nunca deve criar funcionalidades inexistentes.

"aplicacoes":
Inclua aplicações somente quando estiverem indicadas nos materiais ou
forem consequência direta e inequívoca da categoria do produto.
Evite afirmações específicas não comprovadas.

"slogan":
Resumo técnico curto para o rodapé/capa, usando apenas dados confirmados.

"alertas":
Inclua conflitos, ambiguidades ou informações que precisam de revisão humana.

"nao_informado":
Liste informações importantes que seriam úteis no datasheet,
mas que não estavam presentes nos materiais recebidos.
"""


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não encontrada no ambiente."
        )

    return anthropic.Anthropic(api_key=api_key)


def _encode_base64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("utf-8")


def _normalize_image_media_type(media_type: str) -> str:
    allowed = {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }

    if media_type not in allowed:
        raise ValueError(
            f"Formato de imagem não suportado pelo Claude: {media_type}"
        )

    return media_type


def _extract_text_response(message) -> str:
    texts = []

    for block in message.content:
        if getattr(block, "type", None) == "text":
            texts.append(block.text)

    result = "".join(texts).strip()

    if not result:
        raise RuntimeError(
            "Claude não retornou conteúdo textual."
        )

    return result


def _parse_json_response(raw_response: str) -> dict:
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Claude retornou uma resposta que não é JSON válido."
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            "Claude retornou JSON válido, mas a raiz não é um objeto."
        )

    return data


def analyze_product(
    codigo: str,
    nome: str,
    informacoes_adicionais: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    imagens: Optional[list[dict]] = None,
) -> dict:
    """
    Analisa os materiais de um produto utilizando Claude.

    imagens deve seguir o formato:

    [
        {
            "data": bytes_da_imagem,
            "media_type": "image/jpeg",
            "filename": "1.jpg",
        },
        ...
    ]

    Retorna um dict Python com os dados estruturados para
    revisão e posterior geração do datasheet.
    """

    if not codigo.strip():
        raise ValueError("O código do produto é obrigatório.")

    if not nome.strip():
        raise ValueError("O nome do produto é obrigatório.")

    imagens = imagens or []

    content = []

    # PDF do fornecedor
    if pdf_bytes:
        content.append(
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": _encode_base64(pdf_bytes),
                },
            }
        )

    # Imagens do produto
    for index, image in enumerate(imagens, start=1):
        image_data = image.get("data")
        media_type = image.get("media_type")
        filename = image.get("filename") or f"imagem_{index}"

        if not image_data:
            continue

        if not media_type:
            raise ValueError(
                f"Tipo MIME não informado para a imagem {filename}."
            )

        media_type = _normalize_image_media_type(media_type)

        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": _encode_base64(image_data),
                },
            }
        )

    user_context = f"""
Analise o produto abaixo e os materiais anexados.

CÓDIGO DEFINIDO PELO USUÁRIO:
{codigo.strip()}

NOME/MODELO DEFINIDO PELO USUÁRIO:
{nome.strip()}

INFORMAÇÕES ADICIONAIS:
{(informacoes_adicionais or "Nenhuma informação adicional fornecida.").strip()}

Quantidade de imagens recebidas:
{len(imagens)}

IMPORTANTE:
O valor de "model" no JSON final deve ser exatamente:

{nome.strip()}

Extraia e organize as informações necessárias para o gerador
de datasheet, seguindo rigorosamente as regras do sistema.
"""

    content.append(
        {
            "type": "text",
            "text": user_context,
        }
    )

    client = _get_client()

    message = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
    )

    raw_response = _extract_text_response(message)

    result = _parse_json_response(raw_response)

    # O modelo informado pelo usuário sempre tem prioridade.
    result["model"] = nome.strip()

    return result