"""Explicit, human-authored READ AI test extraction. Never a model result."""
from app.services.meeting_transcripts import digest

READ_AI_HASH = "e87dc87ecdf6e8d5bbc6dbc92996aaeaecdbcded3915acaa1b05696e41bec9f1"


def read_ai_example(segments):
    def segment(timestamp):
        return next(s for s in segments if s["timestamp"] == timestamp)
    def evidence(timestamp, quote, supports=None):
        return {"segment_id": segment(timestamp)["id"], "quote": quote, "supports": supports or ["action", "owner"]}
    def task(key, title, timestamp, quote, commitment="explicit", raw=None, checklist=None):
        return {"local_id": key, "kind": "task", "commitment_type": commitment, "title": title,
                "description": title, "owner_participant_id": segment(timestamp)["participant_id"],
                "due": {"raw_expression": raw, "precision": "partial" if raw else "unknown",
                        "origin": "explicit" if raw else "not_stated", "needs_review": True},
                "priority": None, "checklist": checklist or [], "depends_on_local_ids": [],
                "evidence": [evidence(timestamp, quote)], "ambiguities": ["Definir acompanhamento interno", "Confirmar prazo"]}
    proposals = [
        task("configurador", "Verificar possibilidade de aproveitar configurador interno no site", "16:04",
             "Eu teria que ver isso, ver se tem como a gente trazer", "suggestion"),
        task("proposta", "Preparar proposta integrada de loja, ERP e hub de marketplace", "48:46",
             "Mas aí eu vou trazer esses três cenários em um projeto só", checklist=["Loja virtual", "Integração ERP", "Hub de marketplace", "Valores separados"]),
        task("api", "Compartilhar documentação da API do ERP", "48:34", "Posso te passar depois ali", "offer", "depois"),
        task("cto", "Consultar o CTO sobre integrações existentes com o ERP", "48:46", "Mas eu vou perguntar também para o nosso CTO aqui"),
        task("materiais", "Encaminhar funcionalidades, demonstração e cases", "54:50", "eu te encaminho também para já você ter acesso",
             checklist=["Funcionalidades", "Acesso à demonstração", "Cases"]),
        task("convite", "Enviar convite da apresentação da proposta", "54:50", "Mas eu te mando o convite aqui na quinta, Luiz.", raw="na quinta"),
    ]
    proposals[1]["evidence"].append(evidence("48:08", "Eu vou customizar utilizar esse projeto para te apresentar com o orçamento dessa loja virtual"))
    proposals[1]["ambiguities"].append("Dependência da consulta ao CTO é inferida, confirmar")
    event = task("apresentacao", "Apresentação da proposta de e-commerce e integrações", "51:47",
                 "na quinta-feira, dia 24, eu consigo te apresentar", raw="quinta-feira, dia 24")
    event.update(kind="event", time_candidate="15:00", duration_estimate_minutes=40, participant_ids=[])
    event["evidence"] += [evidence("54:36", "As duas, né? Isso. Pode ser as três? Tem como? Ou 11 horas da manhã?", ["correction"]),
                          evidence("54:47", "Pode ser as três.", ["due"]),
                          evidence("54:50", "Tá, vou agendar aqui então.", ["action"])]
    event["ambiguities"] += ["Mês/ano ausentes da transcrição", "15:00 candidata, confirmar fuso", "40 minutos são estimativa"]
    proposals.append(event)
    return {"schema_version": "2.0", "summary": "EXEMPLO SIMULADO e revisável da reunião sobre e-commerce e integrações.",
            "proposals": proposals, "decisions": ["Saída logística somente de Curitiba (12:20)."],
            "context_notes": ["Migração e módulo financeiro são horizontes, não cronogramas aprovados.",
                              "Demonstração 'usar amanhã' não é compromisso de implantação."],
            "warnings": ["Fixture determinística elaborada para testes, sem chamada de IA.", "Responsáveis internos pendentes."]}
