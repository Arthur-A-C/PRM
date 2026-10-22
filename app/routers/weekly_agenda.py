"""Pauta Semanal de Desenvolvimento. Managers of the organization only; mutations need CSRF; every change is audited."""
import re
import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import inspect, select

from app.dependencies import AppSettings, CurrentAuth, DbSession
from app.models import User
from app.models.weekly_agenda import WeeklyAgendaRevision
from app.services import github_activity as gh
from app.services import weekly_agenda as agendas
from app.services.security import secrets_match

# Replaced only by tests/E2E harnesses (simulated GitHub/AI); production uses the real clients.
github_transport = None
ai_client = None


def ready(db: DbSession):
    if not inspect(db.get_bind()).has_table("weekly_agendas"):
        raise HTTPException(503, "Pauta semanal ainda não migrada. Execute a migração documentada.")


router = APIRouter(prefix="/api/v1/pauta-semanal", tags=["pauta semanal"], dependencies=[Depends(ready)])


def manager(auth: CurrentAuth):
    if auth.user.role not in agendas.MANAGERS:
        raise HTTPException(403, "A pauta semanal é restrita a gestores e desenvolvedores.")


def mutation(auth: CurrentAuth, x_csrf_token: Annotated[str | None, Header()] = None):
    manager(auth)
    if not x_csrf_token or not secrets_match(auth.login_session.csrf_hash, x_csrf_token):
        raise HTTPException(403, "Token CSRF inválido.")


Read, Write = Depends(manager), Depends(mutation)


class Versioned(BaseModel):
    version: int = Field(ge=1)


class GenerateInput(BaseModel):
    semana: date | None = None
    version: int | None = Field(default=None, ge=1)


class ItemInput(Versioned):
    text: str | None = Field(default=None, max_length=2000)
    hidden: bool | None = None


class OverviewInput(Versioned):
    text: str = Field(max_length=3000)


class ManualInput(Versioned):
    kind: Literal["subject", "note", "decision"]
    text: str = Field(min_length=1, max_length=3000)


class ManualEdit(Versioned):
    text: str = Field(min_length=1, max_length=3000)


class SettingsInput(BaseModel):
    enabled: bool
    weekday: int = Field(ge=0, le=6)
    draft_time: str
    ai_enabled: bool
    planner_filter: str = Field(default="", max_length=120)
    people: dict[str, str] = Field(default_factory=dict)

    @field_validator("draft_time")
    @classmethod
    def clock(cls, value):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Horário no formato HH:MM.")
        return value

    @field_validator("people")
    @classmethod
    def logins(cls, value):
        if len(value) > 60 or any(not re.fullmatch(r"[A-Za-z0-9-]{1,39}", k) or not 1 <= len(v.strip()) <= 120 for k, v in value.items()):
            raise ValueError("Mapeamento de pessoas inválido (login do GitHub → nome).")
        return {k: v.strip() for k, v in value.items()}


def run(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


def names(db, organization_id):
    return {str(u.id): u.name for u in db.scalars(select(User).where(User.organization_id == organization_id)).all()}


def serialize(db, agenda, full=True):
    people = names(db, agenda.organization_id)
    who = lambda value: people.get(str(value), "Agendamento automático") if value else "Agendamento automático"
    data = {"id": str(agenda.id), "title": agenda.title, "week_start": agenda.week_start.isoformat(), "week_end": agenda.week_end.isoformat(),
            "status": agenda.status, "status_label": agendas.STATE_LABELS[agenda.status], "version": agenda.version,
            "generated_at": agenda.generated_at.isoformat() if agenda.generated_at else None, "generated_by": who(agenda.generated_by_id),
            "approved_at": agenda.approved_at.isoformat() if agenda.approved_at else None,
            "approved_by": who(agenda.approved_by_id) if agenda.approved_by_id else None,
            "archived_at": agenda.archived_at.isoformat() if agenda.archived_at else None, "overview": agenda.overview}
    if not full:
        data["counts"] = {key: sum(1 for i in agenda.items if i["section"] == key and not i["hidden"]) for key, _ in agendas.SECTIONS}
        return data
    generation = agenda.generation or {}
    github = (agenda.sources or {}).get("github") or {}
    data.update({
        "sections": [{"key": key, "label": label, "items": [{**i, "status_label": agendas.STATUS_LABELS.get(i["status"], i["status"]),
                                                              "edited_by": people.get(i.get("edited_by"), i.get("edited_by"))}
                                                             for i in agenda.items if i["section"] == key]}
                     for key, label in agendas.SECTIONS],
        "manual": [{**m, "kind_label": agendas.MANUAL_KINDS[m["kind"]], "author": people.get(m["author"], m["author"])} for m in agenda.manual],
        "generation": {"ai": generation.get("ai"), "warnings": generation.get("warnings", []), "github_error": generation.get("github_error"),
                       "contributions": generation.get("contributions", []), "overview_edited": generation.get("overview_edited", False),
                       "scheduled_for": generation.get("scheduled_for")},
        "sources": {"repository": github.get("repository"), "default_branch": github.get("default_branch"),
                    "pulls": len(github.get("pulls") or []), "commits": len(github.get("commits") or []),
                    "issues": len(github.get("issues") or []), "planner": len((agenda.sources or {}).get("planner") or []),
                    "deployed_commit": (agenda.sources or {}).get("deployed_commit") or None, "calls": github.get("calls")}})
    return data


# --- Configuração ------------------------------------------------------------------------------------

@router.get("/configuracao", dependencies=[Read])
def configuration(auth: CurrentAuth, db: DbSession, settings: AppSettings):
    options = agendas.settings_for(db, auth.user.organization_id)
    db.commit()
    return {"enabled": options.enabled, "weekday": options.weekday, "draft_time": options.draft_time, "ai_enabled": options.ai_enabled,
            "planner_filter": options.planner_filter, "people": options.people,
            "integration": {"github_configured": bool(settings.github_token.get_secret_value()), "repository": settings.github_repository,
                            "deployed_commit": settings.deployed_commit.strip()[:40] or None, "ai_model_configured": bool(settings.meeting_ai_model),
                            "timezone": "America/Sao_Paulo"}}


@router.put("/configuracao", dependencies=[Write])
def update_configuration(body: SettingsInput, auth: CurrentAuth, db: DbSession, settings: AppSettings):
    options = agendas.settings_for(db, auth.user.organization_id)
    before = {"enabled": options.enabled, "weekday": options.weekday, "draft_time": options.draft_time, "ai_enabled": options.ai_enabled,
              "planner_filter": options.planner_filter, "people": options.people}
    options.enabled, options.weekday, options.draft_time = body.enabled, body.weekday, body.draft_time
    options.ai_enabled, options.planner_filter, options.people = body.ai_enabled, body.planner_filter.strip(), body.people
    options.updated_by_id = auth.user.id
    agendas.record(db, None, auth.user.organization_id, auth.user.id, "settings_changed", {"before": before, "after": body.model_dump()})
    db.commit()
    return configuration(auth, db, settings)


@router.post("/configuracao/teste", dependencies=[Write])
def test_github(settings: AppSettings):
    """Read-only access check to the configured repository (metadata only)."""
    try:
        client = gh.GitHubClient(settings.github_token.get_secret_value(), settings.github_repository, settings.github_api_url,
                                 settings.github_timeout_seconds, transport=github_transport)
    except gh.GitHubError as exc:
        return {"ok": False, "message": str(exc)}
    try:
        repo, _ = client.get("")
        broad = [s for s in client.scopes or [] if s in {"repo", "admin:org", "write:org", "delete_repo", "workflow"}]
        return {"ok": True, "repository": repo.get("full_name"), "private": bool(repo.get("private")),
                "message": "Acesso de leitura confirmado." + (f" Atenção: token clássico com escopos amplos ({', '.join(broad)}); "
                                                             "prefira um token fine-grained somente leitura." if broad else "")}
    except gh.GitHubError as exc:
        return {"ok": False, "message": str(exc)}
    finally:
        client.close()


# --- Pautas -------------------------------------------------------------------------------------------

@router.get("/pautas", dependencies=[Read])
def listing(auth: CurrentAuth, db: DbSession, q: str = "", status: Literal["", "draft", "approved", "archived"] = "", page: int = 1):
    rows, more = agendas.history(db, auth.user.organization_id, q[:200], status, limit=20, offset=(max(page, 1) - 1) * 20)
    return {"items": [serialize(db, a, full=False) for a in rows], "more": more, "page": max(page, 1)}


@router.get("/pautas/atual", dependencies=[Read])
def current(auth: CurrentAuth, db: DbSession):
    monday = agendas.current_week()[0]
    rows, _ = agendas.history(db, auth.user.organization_id, limit=60)
    agenda = next((a for a in rows if a.week_start == monday), None)
    return {"week_start": monday.isoformat(), "agenda": serialize(db, agenda) if agenda else None}


@router.post("/pautas", dependencies=[Write])
def generate(body: GenerateInput, auth: CurrentAuth, db: DbSession, settings: AppSettings):
    """Generates the week (default: current) or regenerates it keeping human edits."""
    monday = agendas.week_of(body.semana)[0] if body.semana else None
    agenda = run(lambda: agendas.generate(db, auth.user.organization_id, auth.user.id, settings, monday=monday,
                                          transport=github_transport, ai_client=ai_client, expected_version=body.version))
    db.commit()
    return serialize(db, agenda)


@router.get("/pautas/{identifier}", dependencies=[Read])
def detail(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return serialize(db, run(lambda: agendas.get_agenda(db, auth.user.organization_id, identifier)))


def change(identifier, auth, db, action):
    agenda = run(lambda: agendas.get_agenda(db, auth.user.organization_id, identifier, lock=True))
    run(lambda: action(agenda))
    db.commit()
    return serialize(db, agenda)


@router.patch("/pautas/{identifier}/itens/{key:path}", dependencies=[Write])
def edit_item(identifier: uuid.UUID, key: str, body: ItemInput, auth: CurrentAuth, db: DbSession):
    return change(identifier, auth, db, lambda a: agendas.edit_item(db, a, auth.user.id, key, body.version, text=body.text, hidden=body.hidden))


@router.post("/pautas/{identifier}/restaurar-item/{key:path}", dependencies=[Write])
def restore_item(identifier: uuid.UUID, key: str, body: Versioned, auth: CurrentAuth, db: DbSession):
    return change(identifier, auth, db, lambda a: agendas.edit_item(db, a, auth.user.id, key, body.version, restore=True))


@router.put("/pautas/{identifier}/resumo", dependencies=[Write])
def overview(identifier: uuid.UUID, body: OverviewInput, auth: CurrentAuth, db: DbSession):
    return change(identifier, auth, db, lambda a: agendas.set_overview(db, a, auth.user.id, body.version, body.text))


@router.post("/pautas/{identifier}/anotacoes", dependencies=[Write])
def add_manual(identifier: uuid.UUID, body: ManualInput, auth: CurrentAuth, db: DbSession):
    return change(identifier, auth, db, lambda a: agendas.add_manual(db, a, auth.user.id, body.version, body.kind, body.text))


@router.patch("/pautas/{identifier}/anotacoes/{entry}", dependencies=[Write])
def edit_manual(identifier: uuid.UUID, entry: str, body: ManualEdit, auth: CurrentAuth, db: DbSession):
    return change(identifier, auth, db, lambda a: agendas.edit_manual(db, a, auth.user.id, body.version, entry, text=body.text))


@router.delete("/pautas/{identifier}/anotacoes/{entry}", dependencies=[Write])
def remove_manual(identifier: uuid.UUID, entry: str, version: int, auth: CurrentAuth, db: DbSession):
    return change(identifier, auth, db, lambda a: agendas.edit_manual(db, a, auth.user.id, version, entry, remove=True))


@router.post("/pautas/{identifier}/{action}", dependencies=[Write])
def transition(identifier: uuid.UUID, action: Literal["aprovar", "reabrir", "arquivar", "desarquivar"], body: Versioned,
               auth: CurrentAuth, db: DbSession):
    name = {"aprovar": "approve", "reabrir": "reopen", "arquivar": "archive", "desarquivar": "unarchive"}[action]
    return change(identifier, auth, db, lambda a: agendas.transition(db, a, auth.user.id, body.version, name))


@router.get("/pautas/{identifier}/historico", dependencies=[Read])
def revisions(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession):
    agenda = run(lambda: agendas.get_agenda(db, auth.user.organization_id, identifier))
    people = names(db, auth.user.organization_id)
    rows = db.scalars(select(WeeklyAgendaRevision).where(WeeklyAgendaRevision.agenda_id == agenda.id)
                      .order_by(WeeklyAgendaRevision.created_at.desc()).limit(200)).all()
    return {"items": [{"at": r.created_at.isoformat() if r.created_at else None, "actor": people.get(str(r.actor_id), "Agendamento automático")
                       if r.actor_id else "Agendamento automático", "action": r.action, "changes": r.changes} for r in rows]}


@router.get("/pautas/{identifier}/pdf", dependencies=[Read])
def pdf(identifier: uuid.UUID, request: Request, auth: CurrentAuth, db: DbSession):
    from app.services.weekly_agenda_pdf import render
    agenda = run(lambda: agendas.get_agenda(db, auth.user.organization_id, identifier))
    content = render(agenda, names(db, auth.user.organization_id), base_url=str(request.base_url))
    agendas.record(db, agenda, auth.user.organization_id, auth.user.id, "exported_pdf", {"version": agenda.version})
    db.commit()
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="pauta-semanal-{agenda.week_start.isoformat()}.pdf"', "Cache-Control": "private, no-store"})
