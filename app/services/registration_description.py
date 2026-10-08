"""Deterministic, source-grounded commercial HTML from reviewed analysis."""

from __future__ import annotations

from html import escape

from app.schemas.registration import RegistrationProduct


SIGNATURES = {
    "choice": (
        "Controlamos e monitoramos processos críticos na indústria de Transformação, "
        "Data Center e Infraestrutura <strong>Choice automação, segurança e energia</strong> "
        "é o nosso core."
    ),
    "sag": (
        "SAG Controle e Posicionamento de Máquinas. "
        "Tecnologias para posicionamento de grandes maquinas via radares, encoders ou "
        "sensores laser para uso em ambientes pesados, postos e cabines de comando "
        "com as melhores tecnologias em automação, ergonomia e segurança ao operador "
        "e processo produtivo, além de serviços de projeto e assistência técnica especializados."
    ),
}


def build_description(product: RegistrationProduct) -> tuple[str, list[str]]:
    """Only included text is supplied by the user or the reviewed analysis."""
    title = escape(product.commercial_title)
    intro = escape(product.short_description or product.technical_name)
    sections = [f"<h1>{title}</h1>", f"<p>{intro}</p>"]
    if product.features:
        sections.append("<p>" + escape("; ".join(product.features)) + ".</p>")
    if product.benefits:
        sections.append("<h2>Benefícios do produto</h2><ul>")
        sections.extend(f"<li>{escape(item)}</li>" for item in product.benefits[:5])
        sections.append("</ul>")
    if product.applications:
        sections.append("<h2>Aplicações e uso</h2><ul>")
        sections.extend(f"<li>{escape(item)}</li>" for item in product.applications[:5])
        sections.append("</ul>")
    warnings = []
    signature = SIGNATURES.get(product.company)
    if signature:
        sections.append(f"<p>{signature}</p>")
    else:
        warnings.append("Assinatura institucional Portwell não configurada; revisar antes de publicar.")
    return "".join(sections), warnings
