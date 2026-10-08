"""Datasheet Choice (componentes de automação: comando e sinalização, sensores, conectores)."""
from __future__ import annotations

from typing import Any

from app.services.datasheet_core import ASSETS, DatasheetResult, Theme, render_datasheet

CHOICE_THEME = Theme(
    brand="CHOICE",
    accent="#35A9D6",
    dark="#252525",
    text="#1D1D1D",
    muted="#666666",
    light="#F5F5F5",
    line="#DADDE1",
    section_bg="#ECEDEF",
    section_text="#252525",
    cover_bg="#303030",
    cover_text="#FFFFFF",
    cover_muted="#C9CDD1",
    cover_tag_border="#8A9096",
    header_bg="#F1F2F6",
    header_text="#252525",
    footer_bg="#303030",
    footer_text="#FFFFFF",
    logo_path=str(ASSETS / "choice_logo.png"),
    razao_social="Choice",
    # TODO PRM: preencher contato da Choice (aparece no rodapé, na capa e no bloco "Fale com a Choice")
    telefone="",
    site="www.choicetech.com.br",
    email="",
    endereco="",
    cidade="",
    titulo_contato="Fale com a Choice",
    fechamento=(),  # TODO PRM: texto institucional (1 a 3 parágrafos curtos)
)


def generate_choice_datasheet_full(data: dict[str, Any], anexos: dict[str, bytes] | list[bytes] | None = None,
                                   codigo: str | None = None) -> DatasheetResult:
    return render_datasheet(data, CHOICE_THEME, anexos, codigo=codigo)


def generate_choice_datasheet(data: dict[str, Any], images: dict[str, bytes] | list[bytes] | None = None,
                              codigo: str | None = None) -> bytes:
    """Assinatura antiga do PRM: devolve só os bytes do PDF."""
    return render_datasheet(data, CHOICE_THEME, images, codigo=codigo, previews=False).pdf
