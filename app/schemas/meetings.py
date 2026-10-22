"""Versioned, closed extraction contract. Model output never grants authority."""
from datetime import date as DateValue, datetime as DateTimeValue
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Due(Closed):
    raw_expression: str | None = Field(default=None, max_length=500)
    date: DateValue | None = None
    datetime: DateTimeValue | None = None
    timezone: str | None = None
    precision: Literal["unknown", "date", "datetime", "partial", "conditional"] = "unknown"
    origin: Literal["not_stated", "explicit", "relative", "human", "policy"] = "not_stated"
    needs_review: bool = True
    condition: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def consistent(self):
        if self.date and self.datetime:
            raise ValueError("Data e instante são mutuamente exclusivos")
        if self.datetime and (self.datetime.tzinfo is None or not self.timezone):
            raise ValueError("Instante exige offset e fuso")
        if self.timezone:
            ZoneInfo(self.timezone)
        if self.precision in {"partial", "unknown", "conditional"} and (self.date or self.datetime):
            raise ValueError("Prazo incompleto não pode ter data definitiva")
        return self


class Evidence(Closed):
    segment_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=3, max_length=5000)
    supports: list[Literal["action", "owner", "due", "correction", "decision"]] = Field(min_length=1)


class Proposal(Closed):
    local_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    commitment_type: Literal["explicit", "request", "offer", "suggestion"]
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(max_length=10000)
    owner_participant_id: str | None
    due: Due
    priority: Literal["low", "normal", "high"] | None
    checklist: list[str] = Field(max_length=40)
    depends_on_local_ids: list[str] = Field(max_length=50)
    evidence: list[Evidence] = Field(min_length=1, max_length=30)
    ambiguities: list[str] = Field(max_length=40)


class TaskProposal(Proposal):
    kind: Literal["task"]


class EventProposal(Proposal):
    kind: Literal["event"]
    time_candidate: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    duration_estimate_minutes: int | None = Field(default=None, ge=1, le=1440)
    participant_ids: list[str] = Field(default_factory=list, max_length=100)


class Extraction(Closed):
    schema_version: Literal["2.0"]
    summary: str = Field(max_length=10000)
    proposals: list[Annotated[TaskProposal | EventProposal, Field(discriminator="kind")]] = Field(max_length=150)
    decisions: list[str] = Field(max_length=100)
    context_notes: list[str] = Field(max_length=100)
    warnings: list[str] = Field(max_length=100)


def validate_extraction(raw: dict, segments: list[dict], participants: list[dict]) -> Extraction:
    result = Extraction.model_validate(raw)
    segment_map = {s["id"]: s for s in segments}
    people = {p["id"] for p in participants}
    proposals = {p.local_id: p for p in result.proposals}
    if len(proposals) != len(result.proposals):
        raise ValueError("IDs de propostas repetidos")
    for proposal in result.proposals:
        if proposal.owner_participant_id and proposal.owner_participant_id not in people:
            raise ValueError("Participante não autorizado")
        if isinstance(proposal, EventProposal) and not set(proposal.participant_ids) <= people:
            raise ValueError("Participantes do evento não autorizados")
        for evidence in proposal.evidence:
            segment = segment_map.get(evidence.segment_id)
            if not segment or evidence.quote not in segment["text"]:
                raise ValueError("Evidência não existe na revisão analisada")
        supports = {support for e in proposal.evidence for support in e.supports}
        if "action" not in supports or (proposal.owner_participant_id and "owner" not in supports):
            raise ValueError("Ação/responsável sem evidência")
        if (proposal.due.date or proposal.due.datetime) and "due" not in supports:
            raise ValueError("Prazo sem evidência")
        if proposal.due.origin in {"human", "policy"}:
            raise ValueError("IA não pode declarar decisão humana ou política")
        if not set(proposal.depends_on_local_ids) <= proposals.keys():
            raise ValueError("Dependência inexistente")
    visited, visiting = set(), set()
    def visit(key):
        if key in visiting:
            raise ValueError("Dependências cíclicas")
        if key in visited:
            return
        visiting.add(key)
        for dependency in proposals[key].depends_on_local_ids:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)
    for key in proposals:
        visit(key)
    return result
