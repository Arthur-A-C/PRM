"""Validation at the Claude/human-edit boundary (the renderer accepts legacy data)."""
from __future__ import annotations

from typing import Any


IMAGE_ROLES = {"capa", "perspectiva", "frontal", "traseira", "lateral", "superior",
               "inferior", "multivista", "painel_io", "dimensoes", "detalhe", "acessorio", "descartar"}


def validate_analysis(data: Any, *, name: str, attachments: set[str] | None = None) -> dict:
    if not isinstance(data, dict):
        raise ValueError("A análise deve ser um objeto JSON.")
    required = ("modelo", "nivel", "categoria", "subtitulo", "tags", "features",
                "descricao", "imagens", "pendencias")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError("Campos obrigatórios ausentes na análise: " + ", ".join(missing))
    if data["modelo"] != name:
        raise ValueError("O modelo retornado não corresponde ao nome do produto solicitado.")
    if data["nivel"] not in {"completo", "resumido"}:
        raise ValueError("Nível do datasheet inválido.")
    for key in ("categoria", "subtitulo"):
        if not isinstance(data[key], str):
            raise ValueError(f"Campo {key} deve ser texto.")
    for key in ("tags", "features", "descricao", "pendencias"):
        if not isinstance(data[key], list) or any(not isinstance(x, str) for x in data[key]):
            raise ValueError(f"Campo {key} deve ser uma lista de textos.")
    if len(data["tags"]) != 4 or len(data["features"]) > 6:
        raise ValueError("A capa exige quatro tags e até seis características.")
    if not isinstance(data["imagens"], list):
        raise ValueError("Campo imagens deve ser uma lista.")
    for image in data["imagens"]:
        if not isinstance(image, dict) or image.get("papel") not in IMAGE_ROLES or not isinstance(image.get("arquivo"), str):
            raise ValueError("Instrução de imagem inválida.")
        if attachments is not None and image["arquivo"] not in attachments:
            raise ValueError(f"Imagem referenciada não foi enviada: {image['arquivo']}.")
    if sum(image["papel"] == "capa" for image in data["imagens"]) > 1:
        raise ValueError("A análise indica mais de uma imagem de capa.")
    if data["nivel"] == "completo":
        specs = data.get("especificacoes")
        if not isinstance(specs, list):
            raise ValueError("Datasheet completo exige a lista especificacoes.")
    return data
