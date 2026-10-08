"""Datasheet Portwell (computação industrial, comunicação e automação)."""
from __future__ import annotations

from typing import Any

from app.services.datasheet_core import ASSETS, DatasheetResult, Theme, render_datasheet

PORTWELL_THEME = Theme(
    brand="Portwell",
    registered=True,
    accent="#7DC240",
    dark="#1C1C1C",
    text="#1C1C1C",
    muted="#444444",
    light="#F7F7F7",
    line="#DDDDDD",
    section_bg="#E4E4E4",
    section_text="#1C1C1C",
    cover_bg="#1C1C1C",
    cover_text="#FFFFFF",
    cover_muted="#BBBBBB",
    cover_tag_border="#AAAAAA",
    header_bg="#FFFFFF",
    header_text="#1C1C1C",
    footer_bg="#111111",
    footer_text="#FFFFFF",
    logo_path=str(ASSETS / "portwell_logo.png") if (ASSETS / "portwell_logo.png").exists() else None,
    razao_social="Portwell Industrial Automation",
    telefone="+55 41 3121.7200",
    site="www.portwell.com.br",
    email="contato@portwell.com",
    endereco="Rua José Correia Sérgio, 146, Fazendinha, 81320-010",
    cidade="Curitiba-PR  ·  Brasil",
    titulo_contato="Fale com a Portwell",
    fechamento=(
        "Tecnologias que nunca param, para o seu negócio. Na Portwell, automação, computação e comunicação são o nosso core.",
        "Estamos comprometidos em levar automação inteligente para empresas que buscam eficiência, escalabilidade e competitividade.",
        "Como distribuidores credenciados das maiores multinacionais do segmento, garantimos soluções robustas, suporte especializado e inovação constante.",
    ),
)


def generate_portwell_datasheet_full(data: dict[str, Any], anexos: dict[str, bytes] | list[bytes] | None = None,
                                     codigo: str | None = None) -> DatasheetResult:
    return render_datasheet(data, PORTWELL_THEME, anexos, codigo=codigo)


def generate_portwell_datasheet(data: dict[str, Any], images: dict[str, bytes] | list[bytes] | None = None,
                                codigo: str | None = None) -> bytes:
    """Assinatura antiga do PRM: devolve só os bytes do PDF."""
    return render_datasheet(data, PORTWELL_THEME, images, codigo=codigo, previews=False).pdf
