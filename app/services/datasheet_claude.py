"""Orquestra a geração do datasheet com a API do Claude.

Fluxo: anexos (PDF/fotos) + dados do produto -> Claude (JSON via ferramenta) -> motor (PDF)
-> prévias das páginas voltam ao Claude para revisão -> JSON corrigido -> PDF final.

Configuração: ANTHROPIC_API_KEY e DATASHEET_MODEL (id do modelo Claude com visão e leitura de PDF).
Dependência: pip install anthropic
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
from dataclasses import dataclass
from typing import Any, Callable

from PIL import Image

from app.services.datasheet_core import DatasheetResult
from app.services.datasheet_prompt import REVIEW_PROMPT, TOOL, system_prompt, user_message
from app.services.datasheet_validation import validate_analysis

MAX_EDGE = 1568  # lado máximo enviado à API; as caixas são normalizadas, então o motor usa o original


def _generator(empresa: str) -> Callable[..., DatasheetResult]:
    empresa = empresa.lower()
    if empresa == "portwell":
        from app.services.datasheet_portwell import generate_portwell_datasheet_full as f
    elif empresa == "choice":
        from app.services.datasheet_choice import generate_choice_datasheet_full as f
    elif empresa == "sag":
        from app.services.datasheet_sag import generate_sag_datasheet_full as f
    else:
        raise ValueError(f"Empresa desconhecida: {empresa}")
    return f


def _image_block(raw: bytes) -> dict[str, Any]:
    im = Image.open(io.BytesIO(raw))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, "white"); bg.alpha_composite(im); im = bg
    im = im.convert("RGB")
    if max(im.size) > MAX_EDGE:
        s = MAX_EDGE / max(im.size); im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, format="JPEG", quality=90)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode()}}


def _attachments(anexos: dict[str, bytes]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for nome, raw in anexos.items():
        if not raw or len(raw) > 30 * 1024 * 1024:
            raise ValueError(f"Anexo vazio ou acima de 30 MiB: {nome}.")
        if nome.lower().endswith(".pdf") or raw[:4] == b"%PDF":
            if not raw.startswith(b"%PDF-"):
                raise ValueError(f"PDF inválido: {nome}.")
            blocks.append({"type": "text", "text": f"Arquivo: {nome}"})
            blocks.append({"type": "document", "title": nome, "source": {
                "type": "base64", "media_type": "application/pdf", "data": base64.b64encode(raw).decode()}})
        elif (mimetypes.guess_type(nome)[0] or "").startswith("image") or raw[:4] in (b"\x89PNG", b"RIFF") or raw[:2] == b"\xff\xd8":
            blocks.append({"type": "text", "text": f"Imagem: {nome}"})
            try:
                blocks.append(_image_block(raw))
            except (OSError, ValueError) as exc:
                raise ValueError(f"Imagem inválida: {nome}.") from exc
        else:
            raise ValueError(f"Anexo não suportado para análise: {nome}.")
    return blocks


@dataclass
class GeracaoDatasheet:
    resultado: DatasheetResult
    dados: dict[str, Any]
    ciclos: int


def gerar_datasheet_com_claude(empresa: str, nome: str, anexos: dict[str, bytes], *, configuracao: str = "",
                               opcionais: str = "", nivel: str = "completo", cadastro: str = "",
                               texto_site: str = "", observacoes: str = "", codigo: str | None = None,
                               revisoes: int = 2, model: str | None = None, client=None) -> GeracaoDatasheet:
    """anexos: {nome_arquivo: bytes}. Nomeie as fotos img_01.jpg, img_02.png... na ordem desejada."""
    import anthropic

    model = model or os.environ.get("DATASHEET_MODEL")
    if not model:
        raise RuntimeError("Defina DATASHEET_MODEL com o id do modelo Claude a usar.")
    if not client and not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Defina ANTHROPIC_API_KEY no ambiente do servidor.")
    client = client or anthropic.Anthropic(timeout=120.0, max_retries=1)
    gerar = _generator(empresa)

    content = _attachments(anexos)
    content.append({"type": "text", "text": user_message(empresa, nome, configuracao, opcionais, nivel, cadastro,
                                                         texto_site, observacoes, list(anexos))})
    messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
    system = [{"type": "text", "text": system_prompt(empresa), "cache_control": {"type": "ephemeral"}}]

    def ask() -> tuple[dict[str, Any], Any]:
        resp = client.messages.create(model=model, max_tokens=32000, temperature=0.2, system=system,
                                      tools=[TOOL], tool_choice={"type": "tool", "name": TOOL["name"]},
                                      messages=messages)
        if getattr(resp, "stop_reason", None) == "max_tokens":
            raise ValueError("O Claude atingiu o limite de tokens; reduza os anexos ou o nível de detalhe.")
        tool = next((b for b in resp.content if b.type == "tool_use" and b.name == TOOL["name"]), None)
        if tool is None or not isinstance(tool.input, dict):
            raise ValueError("O Claude não devolveu o JSON estruturado pela ferramenta entregar_datasheet.")
        return validate_analysis(dict(tool.input), name=nome, attachments=set(anexos)), resp

    dados, resp = ask()
    resultado = gerar(dados, anexos, codigo=codigo)
    ciclos = 1
    for _ in range(max(0, revisoes)):
        tool_id = next(b for b in resp.content if b.type == "tool_use" and b.name == TOOL["name"]).id
        relatorio = {"avisos": resultado.avisos, "paginas": len(resultado.previews)}
        review: list[dict[str, Any]] = [{"type": "text", "text": "Relatório do motor: " + json.dumps(relatorio, ensure_ascii=False)}]
        for i, png in enumerate(resultado.previews, start=1):
            review.append({"type": "text", "text": f"Página {i}"})
            review.append(_image_block(png))
        review.append({"type": "text", "text": REVIEW_PROMPT})
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": review}]})
        novo, resp = ask()
        ciclos += 1
        if novo.get("revisao_ok"):
            break
        dados = novo
        resultado = gerar(dados, anexos, codigo=codigo)
    return GeracaoDatasheet(resultado, dados, ciclos)
