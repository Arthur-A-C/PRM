"""PDF export of a Pauta Semanal (reportlab, no browser needed). Hidden items are left out; sources stay as links."""
import io
from datetime import datetime, timezone
from html import escape
from urllib.parse import urljoin

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.services.weekly_agenda import MANUAL_KINDS, SECTIONS, STATE_LABELS, STATUS_LABELS, TZ


def _when(value):
    if not value:
        return "—"
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return moment.astimezone(TZ).strftime("%d/%m/%Y %H:%M")


def render(agenda, people, base_url=""):
    """``people`` maps PRM user IDs to names (authorship); ``base_url`` turns internal links absolute."""
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, textColor=colors.HexColor("#4b5563"))
    badge = ParagraphStyle("badge", parent=small, textColor=colors.HexColor("#1d4ed8"))
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, leading=20, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, leading=15, spaceBefore=10, spaceAfter=4,
                        textColor=colors.HexColor("#0f172a"))
    doc = SimpleDocTemplate(stream, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=agenda.title, author="PRM")
    name = lambda value: people.get(str(value), "agendamento automático" if not value else str(value))
    flow = [Paragraph(escape(agenda.title), h1),
            Paragraph(f"Situação: <b>{STATE_LABELS[agenda.status]}</b> · versão {agenda.version} · gerada em {_when(agenda.generated_at)} "
                      f"por {escape(name(agenda.generated_by_id))}"
                      + (f" · aprovada em {_when(agenda.approved_at)} por {escape(name(agenda.approved_by_id))}" if agenda.approved_at else ""), small),
            Spacer(1, 4)]
    ai = (agenda.generation or {}).get("ai") or {}
    flow.append(Paragraph("Redação: " + ("IA sobre dados coletados, com verificação por regras" if ai.get("used") else "estrutura por regras (sem IA)")
                          + ". Fontes: GitHub (metadados) e Planner do PRM.", small))
    if agenda.overview:
        flow += [Spacer(1, 6), Paragraph(escape(agenda.overview), body)]
    link = lambda url: url if url.startswith("http") else urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
    for key, label in SECTIONS:
        items = [i for i in agenda.items if i["section"] == key and not i["hidden"]]
        if not items:
            continue
        flow.append(Paragraph(escape(label), h2))
        for item in items:
            flow.append(Paragraph("• " + escape(item["text"]), body))
            sources = " · ".join(f'<link href="{escape(link(l["url"]))}">{escape(l["label"])}</link>' for l in item["links"][:8])
            flow.append(Paragraph(f"{escape(STATUS_LABELS.get(item['status'], item['status']))}"
                                  + (f" · {escape(', '.join(item['people']))}" if item["people"] else "")
                                  + (f" · Fontes: {sources}" if sources else "")
                                  + (" · editado na reunião" if item.get("edited") else ""), badge))
            flow.append(Spacer(1, 3))
    for kind, label in [("subject", "Assuntos adicionados"), ("note", "Observações"), ("decision", "Decisões registradas na reunião")]:
        entries = [m for m in agenda.manual if m["kind"] == kind]
        if entries:
            flow.append(Paragraph(label, h2))
            for entry in entries:
                flow.append(Paragraph("• " + escape(entry["text"]), body))
                flow.append(Paragraph(f"{MANUAL_KINDS[kind]} de {escape(name(entry['author']))} em {_when(entry['created_at'])}", small))
    people_block = (agenda.generation or {}).get("contributions") or []
    if people_block:
        flow.append(Paragraph("Contribuições por pessoa (com evidência)", h2))
        for entry in people_block:
            counts = ", ".join(f"{STATUS_LABELS.get(k, k).lower()}: {v}" for k, v in entry["counts"].items())
            flow.append(Paragraph(f"<b>{escape(entry['person'])}</b> — {escape(counts)}", body))
    flow += [Spacer(1, 10), Paragraph(f"Exportado pelo PRM em {_when(datetime.now(timezone.utc))}. Integrado na main não significa implantado; "
                                      "somente itens marcados como implantados têm prova no commit em produção.", small)]
    doc.build(flow)
    return stream.getvalue()
