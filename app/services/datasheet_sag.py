"""Datasheet SAG (controle e posicionamento de máquinas: radares, encoders, sensores laser)."""
from __future__ import annotations

from typing import Any

from app.services.datasheet_core import ASSETS, DatasheetResult, Theme, render_datasheet

SAG_THEME = Theme(
    brand="SAG",
    accent="#005ED3",
    dark="#2E4259",
    text="#151B22",
    muted="#56616D",
    light="#F4F7FC",
    line="#D7E1EC",
    section_bg="#E7F0FB",
    section_text="#16202A",
    cover_bg="#F1F2F6",
    cover_text="#005ED3",
    cover_muted="#2E4259",
    cover_tag_border="#005ED3",
    header_bg="#FFFFFF",
    header_text="#16202A",
    footer_bg="#2E4259",
    footer_text="#FFFFFF",
    logo_path=str(ASSETS / "sag_logo.png"),
    cover_logo_bg="#FFFFFF",
    razao_social="SAG Controle e Posicionamento de Máquinas",
    # TODO PRM: preencher contato da SAG
    telefone="",
    site="",
    email="",
    endereco="",
    cidade="Joinville-SC  ·  Brasil",
    titulo_contato="Fale com a SAG",
    fechamento=(),  # TODO PRM: parágrafo institucional sobre tecnologias de posicionamento
    assinatura="SAG Controle e Posicionamento de Máquinas.",
)


def generate_sag_datasheet_full(data: dict[str, Any], anexos: dict[str, bytes] | list[bytes] | None = None,
                                codigo: str | None = None) -> DatasheetResult:
    return render_datasheet(data, SAG_THEME, anexos, codigo=codigo)


def generate_sag_datasheet(data: dict[str, Any], images: dict[str, bytes] | list[bytes] | None = None,
                           codigo: str | None = None) -> bytes:
    """Assinatura antiga do PRM: devolve só os bytes do PDF."""
    return render_datasheet(data, SAG_THEME, images, codigo=codigo, previews=False).pdf
