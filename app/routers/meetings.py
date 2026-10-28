"""Authenticated meeting intake, review and a shared Cards/Alerts/Planner API."""
import hashlib
import json
import uuid
from datetime import date, datetime, time as Time, timezone
from datetime import date as Day  # campos chamados "date" não podem sombrear o tipo (anotações tardias do Python 3.14)
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import Field, field_validator
from sqlalchemy import select, inspect, or_, func
from app.config import get_settings
from app.dependencies import CurrentAuth, DbSession, AppSettings
from app.models import User
from app.models.meetings import Meeting, TranscriptRevision, MeetingRun, MeetingAudio, Activity, ActivityAudit, ActivityAlert
from app.schemas.meetings import Closed
from app.services.security import secrets_match
from app.services.meeting_pipeline import add_revision, analysis_context, enqueue, build_cards
from app.services.meeting_activities import (activity_query, get_activity, get_meeting, serialize, edit_activity,
    review, publish, export_cards, version_check, can_review, audit, operational_activity)
from app.services.meeting_deadlines import overview, deadline
from app.services import planner_hub


def ready(db: DbSession):
    if not inspect(db.get_bind()).has_table("activities"):
        raise HTTPException(503, "Módulo de reuniões ainda não migrado. Execute a migração documentada.")


router = APIRouter(prefix="/api/v1/planner", tags=["reuniões e atividades"], dependencies=[Depends(ready)])


def mutation(auth: CurrentAuth, x_csrf_token: Annotated[str | None, Header()] = None):
    if not x_csrf_token or not secrets_match(auth.login_session.csrf_hash, x_csrf_token):
        raise HTTPException(403, "Token CSRF inválido")


Write = Depends(mutation)


class MeetingInput(Closed):
    title: str = Field(min_length=3, max_length=240)
    partner: str = Field(default="", max_length=240)
    opportunity: str = Field(default="", max_length=240)
    meeting_date: date | None = None
    timezone: str = "America/Sao_Paulo"
    text: str = Field(default="", max_length=2097152)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("Fuso inválido") from exc
        return value


class TextInput(Closed):
    text: str = Field(min_length=1, max_length=2097152)
    reason: str = Field(min_length=3, max_length=1000)


class MetadataInput(Closed):
    version: int = Field(ge=1)
    meeting_date: date | None = None
    timezone: str = "America/Sao_Paulo"
    confirmed_event_date: date | None = None
    reason: str = Field(min_length=3, max_length=1000)
    _zone = field_validator("timezone")(MeetingInput.valid_zone.__func__)


class ParticipantInput(Closed):
    version: int = Field(ge=1)
    participant_id: str
    display_name: str = Field(min_length=2, max_length=200)
    kind: Literal["internal", "external", "unconfirmed"]
    user_id: uuid.UUID | None = None
    reason: str = Field(min_length=3, max_length=1000)


class AnalyzeInput(Closed):
    revision_id: uuid.UUID
    provider: Literal["anthropic", "fixture"] = "anthropic"
    accept_partial: bool = False
    consent_to_send_text: bool = False


class EditInput(Closed):
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)
    title: str = Field(default="", min_length=3, max_length=240)
    description: str = Field(default="", max_length=10000)
    assignee_user_id: uuid.UUID | None = None
    due_date: date | None = None
    due_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str = "America/Sao_Paulo"
    no_deadline_accepted: bool = False
    status: Literal["todo", "in_progress", "waiting_external", "blocked", "done", "cancelled"] = "todo"
    checklist: list[str] = Field(default_factory=list, max_length=40)
    priority: Literal["baixa", "normal", "alta"] | None = None
    _zone = field_validator("timezone")(MeetingInput.valid_zone.__func__)

    @field_validator("due_at", "end_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Horário exige offset/fuso explícito")
        return value


class Selection(Closed):
    id: uuid.UUID
    version: int = Field(ge=1)


class Selections(Closed):
    items: list[Selection] = Field(min_length=1, max_length=100)


class AssignmentBatch(Selections):
    assignee_user_id: uuid.UUID | None
    reason: str = Field(min_length=3, max_length=1000)


class ReviewInput(Closed):
    version: int = Field(ge=1)
    decision: Literal["approved", "rejected", "draft"]
    reason: str = Field(min_length=3, max_length=1000)


class ReviewBatch(Selections):
    decision: Literal["approved", "rejected", "draft"]
    reason: str = Field(min_length=3, max_length=1000)


class CommentInput(Closed):
    request_id: uuid.UUID
    text: str = Field(min_length=1, max_length=2000)


class PlannerItemInput(Closed):
    """Criação direta no Planner: tarefa, card (para revisão), reunião ou follow-up de fornecedor."""
    type: Literal["task", "card", "meeting", "followup"]
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(default="", max_length=10000)
    assignee_user_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    partner: str = Field(default="", max_length=240)
    priority: Literal["baixa", "normal", "alta"] = "normal"
    date: Day | None = None
    time: Time | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=720)
    participants: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=30)
    location: str = Field(default="", max_length=500)
    timezone: str = "America/Sao_Paulo"
    no_deadline_accepted: bool = False
    origin: Literal["planner", "supplier"] = "planner"
    _zone = field_validator("timezone")(MeetingInput.valid_zone.__func__)

    @field_validator("time")
    @classmethod
    def needs_date(cls, value, info):
        if value is not None and not info.data.get("date"):
            raise ValueError("Horário exige data")
        return value


class ScheduleInput(Closed):
    version: int = Field(ge=1)
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(default="", max_length=10000)
    date: Day
    time: Time | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=720)
    participants: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=30)
    location: str = Field(default="", max_length=500)
    assignee_user_id: uuid.UUID | None = None
    priority: Literal["baixa", "normal", "alta"] = "normal"
    status: Literal["todo", "done", "cancelled"] = "todo"
    timezone: str = "America/Sao_Paulo"
    reason: str = Field(min_length=3, max_length=1000)
    _zone = field_validator("timezone")(MeetingInput.valid_zone.__func__)


class ExportInput(Closed):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    format: Literal["json", "csv"]


@router.get("/users")
def users(auth: CurrentAuth, db: DbSession):
    query = select(User).where(User.organization_id == auth.user.organization_id, User.active.is_(True))
    if auth.user.role not in {"gestor", "desenvolvedor"}:
        query = query.where(User.id == auth.user.id)
    return {"current_user_id": str(auth.user.id), "can_manage": auth.user.role in {"gestor", "desenvolvedor"},
            "items": [{"id": str(u.id), "name": u.name, "role": u.role} for u in db.scalars(query.order_by(User.name))]}


@router.post("/meetings", dependencies=[Write])
def create_meeting(payload: MeetingInput, auth: CurrentAuth, db: DbSession, settings: AppSettings):
    if len(payload.text.encode()) > settings.meeting_text_max_bytes:
        raise HTTPException(413, "Transcrição acima do limite")
    meeting = Meeting(organization_id=auth.user.organization_id, creator_id=auth.user.id,
                      **payload.model_dump(exclude={"text"}), participants=[], version=1)
    db.add(meeting)
    db.flush()
    if payload.text.strip():
        add_revision(db, meeting, auth.user.id, payload.text)
    db.commit()
    return {"id": str(meeting.id)}


@router.get("/meetings")
def meetings(auth: CurrentAuth, db: DbSession, offset: int = 0):
    if offset < 0:
        raise HTTPException(422, "Página inválida")
    query = select(Meeting).where(Meeting.organization_id == auth.user.organization_id, planner_hub.not_container())
    if auth.user.role not in {"gestor", "desenvolvedor"}:
        query = query.where(Meeting.creator_id == auth.user.id)
    rows = db.scalars(query.order_by(Meeting.created_at.desc(), Meeting.id).offset(offset).limit(100)).all()
    return {"items": [{"id": str(m.id), "title": m.title, "date": m.meeting_date, "partner": m.partner} for m in rows],
            "next_offset": offset + 100 if len(rows) == 100 else None}


@router.get("/meetings/{identifier}")
def meeting_detail(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession):
    meeting = get_meeting(db, auth.user, identifier)
    revisions = db.scalars(select(TranscriptRevision).where(TranscriptRevision.meeting_id == identifier).order_by(TranscriptRevision.created_at.desc())).all()
    runs = db.scalars(select(MeetingRun).where(MeetingRun.meeting_id == identifier).order_by(MeetingRun.created_at.desc()).limit(100)).all()
    audio = db.scalars(select(MeetingAudio).where(MeetingAudio.meeting_id == identifier)).all()
    event = db.scalar(select(Activity.id).where(Activity.meeting_id == identifier, Activity.proposal_local_id == "meeting-event"))
    return {"event_activity_id": str(event) if event else None, "creator_id": str(meeting.creator_id),"id": str(meeting.id), "title": meeting.title, "partner": meeting.partner, "version": meeting.version,
            "meeting_date": meeting.meeting_date, "timezone": meeting.timezone, "participants": meeting.participants,
            "metadata": meeting.metadata_confirmed,
            "revisions": [{"id": str(r.id), "source": r.source, "sha256": r.sha256, "segments": r.segments,
                           "text": r.original, "quality": r.quality} for r in revisions],
            "runs": [{"id": str(r.id), "stage": r.stage, "state": r.state, "error": r.error,
                      "provider": r.context.get("provider"), "summary": (r.result or {}).get("summary"),
                      "warnings": (r.result or {}).get("warnings", []), "revision_id": str(r.revision_id),
                      "decisions": (r.result or {}).get("decisions", []), "usage": r.context.get("usage")} for r in runs],
            "audio": [{"id": str(a.id), "name": a.original_name, "duration": a.duration_seconds,
                       "url": f"/api/v1/planner/audio/{a.id}"} for a in audio]}


@router.patch("/meetings/{identifier}/metadata", dependencies=[Write])
def metadata(identifier: uuid.UUID, payload: MetadataInput, auth: CurrentAuth, db: DbSession):
    meeting = get_meeting(db, auth.user, identifier, lock=True)
    version_check(meeting, payload.version)
    meeting.meeting_date, meeting.timezone = payload.meeting_date, payload.timezone
    # Agendamento e vínculos do Planner (schedule, fornecedor) são preservados ao confirmar metadados.
    kept = {k: v for k, v in (meeting.metadata_confirmed or {}).items() if k in {"schedule", "supplier_id", "supplier_name", "planner_origin"}}
    meeting.metadata_confirmed = {**kept, "event_date": payload.confirmed_event_date.isoformat() if payload.confirmed_event_date else None,
                                  "origin": "human", "reason": payload.reason, "actor": str(auth.user.id)}
    meeting.version += 1
    db.add(ActivityAudit(organization_id=auth.user.organization_id, meeting_id=meeting.id, actor_id=auth.user.id,
                         action="metadata", reason=payload.reason, changes=payload.model_dump(mode="json")))
    db.commit()
    return {"version": meeting.version}


@router.patch("/meetings/{identifier}/participants", dependencies=[Write])
def participants(identifier: uuid.UUID, payload: ParticipantInput, auth: CurrentAuth, db: DbSession):
    meeting = get_meeting(db, auth.user, identifier, lock=True)
    version_check(meeting, payload.version)
    values = [dict(p) for p in meeting.participants]
    person = next((p for p in values if p["id"] == payload.participant_id), None)
    if not person:
        raise HTTPException(422, "Participante inválido")
    if payload.user_id:
        user = db.get(User, payload.user_id)
        if not user or not user.active or user.organization_id != auth.user.organization_id or payload.kind != "internal":
            raise HTTPException(422, "Usuário interno inválido")
    person.update(display_name=payload.display_name, kind=payload.kind, user_id=str(payload.user_id) if payload.user_id else None,
                  confirmed_by=str(auth.user.id))
    meeting.participants, meeting.version = values, meeting.version + 1
    db.add(ActivityAudit(organization_id=auth.user.organization_id, meeting_id=meeting.id, actor_id=auth.user.id,
                         action="participant", reason=payload.reason, changes=payload.model_dump(mode="json")))
    db.commit()
    return {"version": meeting.version}


@router.post("/meetings/{identifier}/transcripts", dependencies=[Write])
def transcript(identifier: uuid.UUID, payload: TextInput, auth: CurrentAuth, db: DbSession, settings: AppSettings):
    meeting = get_meeting(db, auth.user, identifier, lock=True)
    if not payload.text.strip() or len(payload.text.encode()) > settings.meeting_text_max_bytes:
        raise HTTPException(422, "Texto vazio ou acima do limite")
    revision = add_revision(db, meeting, auth.user.id, payload.text, "manual", {"complete": True, "alignment": "approximate", "reason": payload.reason})
    db.commit()
    return {"id": str(revision.id)}


@router.post("/meetings/{identifier}/txt", dependencies=[Write])
async def upload_txt(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession, settings: AppSettings, file: UploadFile = File(...)):
    meeting = get_meeting(db, auth.user, identifier, lock=True)
    raw = await file.read(settings.meeting_text_max_bytes + 1)
    if len(raw) > settings.meeting_text_max_bytes:
        raise HTTPException(413, "TXT excede limite")
    try:
        text = raw.decode("utf-8-sig")
        revision = add_revision(db, meeting, auth.user.id, text, "txt", {"complete": True, "original_bytes_sha256": hashlib.sha256(raw).hexdigest()})
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(422, "Envie TXT UTF-8 não vazio") from exc
    db.commit()
    return {"id": str(revision.id)}


@router.post("/meetings/{identifier}/analyses", dependencies=[Write])
def analyze(identifier: uuid.UUID, payload: AnalyzeInput, auth: CurrentAuth, db: DbSession, settings: AppSettings):
    meeting = get_meeting(db, auth.user, identifier, lock=True)
    revision = db.get(TranscriptRevision, payload.revision_id)
    if not revision or revision.meeting_id != meeting.id:
        raise HTTPException(404, "Revisão não encontrada")
    if not revision.quality.get("complete", False) and not payload.accept_partial:
        raise HTTPException(422, "Transcrição parcial exige aceite explícito")
    if payload.provider == "anthropic" and not payload.consent_to_send_text:
        raise HTTPException(422, "Confirme envio do texto ao provedor configurado")
    if payload.provider == "fixture":
        from app.services.meeting_fixture import READ_AI_HASH
        hashes = {revision.sha256, revision.quality.get("original_bytes_sha256")}
        if not settings.meeting_enable_fixture or READ_AI_HASH not in hashes:
            raise HTTPException(422, "Simulador disponível somente para fixture READ AI exata e ambiente habilitado")
    context = analysis_context(meeting, revision, settings, payload.provider)
    context["partial_accepted"] = payload.accept_partial
    run = enqueue(db, meeting, "analysis", context, revision_id=revision.id)
    db.commit()
    return {"id": str(run.id), "state": run.state}


@router.post("/meetings/{identifier}/audio", dependencies=[Write])
async def upload_audio(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession, settings: AppSettings, file: UploadFile = File(...)):
    meeting = get_meeting(db, auth.user, identifier)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm"}:
        raise HTTPException(422, "Formato de áudio não aceito")
    root = Path(settings.meeting_storage_dir).resolve()
    if root.is_relative_to(Path("app/static").resolve()):
        raise HTTPException(503, "Armazenamento de reuniões deve ser privado")
    root.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex + suffix
    path = root / key
    size, digest = 0, hashlib.sha256()
    try:
        with path.open("xb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.audio_max_bytes:
                    raise HTTPException(413, "Áudio excede limite de tamanho")
                digest.update(chunk)
                target.write(chunk)
        if not size:
            raise HTTPException(422, "Áudio vazio")
        audio = MeetingAudio(meeting_id=meeting.id, original_name=Path(file.filename.replace('\\', '/')).name[:240],
                             storage_key=key, sha256=digest.hexdigest(), size=size)
        db.add(audio)
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)  # Only this request's new, random upload is removed.
        raise
    return {"id": str(audio.id), "state": "uploaded_unverified"}


class TranscribeInput(Closed):
    audio_id: uuid.UUID
    analyze_after: bool = False
    consent_to_send_text: bool = False


@router.post("/meetings/{identifier}/transcriptions", dependencies=[Write])
def transcribe(identifier: uuid.UUID, payload: TranscribeInput, auth: CurrentAuth, db: DbSession, settings: AppSettings):
    meeting = get_meeting(db, auth.user, identifier, lock=True)
    audio = db.get(MeetingAudio, payload.audio_id)
    if not audio or audio.meeting_id != meeting.id:
        raise HTTPException(404, "Áudio não encontrado")
    if payload.analyze_after and not payload.consent_to_send_text:
        raise HTTPException(422, "Confirme envio do texto antes de encadear a análise")
    run = enqueue(db, meeting, "transcription", {"audio_id": str(audio.id), "sha256": audio.sha256,
        "model": settings.asr_model, "language": settings.asr_language, "analyze_after": payload.analyze_after})
    db.commit()
    return {"id": str(run.id), "state": run.state}


@router.get("/audio/{identifier}")
def player(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession, settings: AppSettings):
    audio = db.get(MeetingAudio, identifier)
    if not audio:
        raise HTTPException(404, "Áudio não encontrado")
    get_meeting(db, auth.user, audio.meeting_id)
    root = Path(settings.meeting_storage_dir).resolve()
    path = (root / audio.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Arquivo não disponível")
    return FileResponse(path, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/items", dependencies=[Write])
def create_item(payload: PlannerItemInput, auth: CurrentAuth, db: DbSession):
    result = planner_hub.create_item(db, auth.user, payload)
    db.commit()
    return result


@router.patch("/meetings/{identifier}/schedule", dependencies=[Write])
def schedule(identifier: uuid.UUID, payload: ScheduleInput, auth: CurrentAuth, db: DbSession):
    meeting = get_meeting(db, auth.user, identifier, lock=True)
    result = planner_hub.reschedule(db, auth.user, meeting, payload)
    db.commit()
    return result


@router.get("/feed")
def feed(start: date, end: date, auth: CurrentAuth, db: DbSession):
    if not 0 < (end - start).days <= 120:
        raise HTTPException(422, "Intervalo da agenda deve ter de 1 a 120 dias; fim exclusivo")
    return planner_hub.feed(db, auth.user, start, end)


@router.get("/summary")
def summary(auth: CurrentAuth, db: DbSession):
    return planner_hub.summary(db, auth.user)


@router.post("/runs/{identifier}/cancel", dependencies=[Write])
def cancel(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession):
    run = db.scalar(select(MeetingRun).where(MeetingRun.id == identifier).with_for_update())
    if not run:
        raise HTTPException(404, "Execução inexistente")
    get_meeting(db, auth.user, run.meeting_id)
    if run.state not in {"queued", "running", "failed"}:
        raise HTTPException(409, "Etapa já concluída; revise/rejeite os rascunhos")
    run.state = "cancelled"
    db.commit()
    return {"state": "cancelled", "warning": "Chamada já enviada pode ser faturada; nenhum passo posterior será iniciado"}


@router.post("/runs/{identifier}/retry", dependencies=[Write])
def retry(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession):
    run = db.scalar(select(MeetingRun).where(MeetingRun.id == identifier).with_for_update())
    if not run:
        raise HTTPException(404, "Execução inexistente")
    get_meeting(db, auth.user, run.meeting_id)
    if run.state != "failed" or run.attempts >= 3:
        raise HTTPException(409, "Retry indisponível; limite de três tentativas por execução")
    run.state, run.error = "queued", None
    db.commit()
    return {"state": "queued"}


@router.post("/runs/{identifier}/cards/build", dependencies=[Write])
def build(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession):
    run = db.get(MeetingRun, identifier)
    if not run:
        raise HTTPException(404, "Execução inexistente")
    meeting = get_meeting(db, auth.user, run.meeting_id)
    if run.stage != "analysis" or run.state != "succeeded":
        raise HTTPException(422, "Análise ainda não validada")
    job = enqueue(db, meeting, "cards", {"generator": "cards-1"}, revision_id=run.revision_id, predecessor_id=run.id)
    db.commit()
    return {"id": str(job.id), "state": job.state}


def filtered(db, user, assignee=None, status=None, meeting=None, partner=None, mine=False, approval=None, owner=None, opportunity=None):
    query = activity_query(user).join(Meeting, Meeting.id == Activity.meeting_id)
    for column, value in [(Activity.assignee_user_id, user.id if mine else assignee), (Activity.status, status),
                          (Activity.meeting_id, meeting), (Activity.approval, approval), (Meeting.partner, partner),
                          (Meeting.opportunity, opportunity)]:
        if value:
            query = query.where(column == value)
    if owner:
        query = query.where(Activity.details["owner"]["name"].as_string() == owner)
    return query


@router.get("/activities")
def activities(auth: CurrentAuth, db: DbSession, assignee: uuid.UUID | None = None, status: str | None = None,
               meeting: uuid.UUID | None = None, partner: str | None = None, mine: bool = False,
               approval: str | None = None, band: str | None = None, bucket: str | None = None,
               owner: str | None = None, opportunity: str | None = None, offset: int = 0, limit: int = 100,
               undated: bool = False):
    if offset < 0 or not 1 <= limit <= 200:
        raise HTTPException(422, "Paginação inválida")
    query = filtered(db, auth.user, assignee, status, meeting, partner, mine, approval, owner, opportunity)
    if undated:
        query = query.where(Activity.due_date.is_(None), Activity.due_at.is_(None),
                            Activity.approval != "rejected", Activity.status.not_in(["done", "cancelled"]))
    if not band and not bucket:
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(Activity.created_at.desc(), Activity.id).offset(offset).limit(limit)).all()
        return {"total": total, "items": [serialize(a) for a in rows], "offset": offset}
    rows = list(db.scalars(query.order_by(Activity.created_at.desc(), Activity.id)))
    now = datetime.now(timezone.utc)
    rows = [a for a in rows if (not band or deadline(a, now)["band"] == band) and (not bucket or deadline(a, now)["bucket"] == bucket)]
    return {"total": len(rows), "items": [serialize(a, now) for a in rows[offset:offset + limit]], "offset": offset}


@router.get("/activities/overview")
def activity_overview(auth: CurrentAuth, db: DbSession, assignee: uuid.UUID | None = None, status: str | None = None,
                      meeting: uuid.UUID | None = None, partner: str | None = None, mine: bool = False,
                      owner: str | None = None, opportunity: str | None = None):
    rows = list(db.scalars(filtered(db, auth.user, assignee, status, meeting, partner, mine, None, owner, opportunity)))
    return overview(rows)


@router.get("/activities/calendar")
def calendar(start: date, end: date, auth: CurrentAuth, db: DbSession,
             assignee: uuid.UUID | None = None, status: str | None = None, partner: str | None = None,
             meeting: uuid.UUID | None = None, mine: bool = False, band: str | None = None, bucket: str | None = None,
             owner: str | None = None, opportunity: str | None = None, include_proposals: bool = False):
    from datetime import timedelta
    if not 0 < (end - start).days <= 62:
        raise HTTPException(422, "Intervalo do calendário deve ter de 1 a 62 dias; fim exclusivo")
    # UTC guard band avoids dropping local dates at +/-14h boundaries.
    lower = datetime.combine(start - timedelta(days=1), datetime.min.time(), timezone.utc)
    upper = datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
    query = filtered(db, auth.user, assignee, status, meeting, partner, mine, None, owner, opportunity)
    query = query.where(Activity.approval.in_(["published", "draft", "approved"] if include_proposals else ["published"]))
    query = query.where(or_((Activity.due_date >= start) & (Activity.due_date < end),
                           (Activity.due_at < upper) & (or_(Activity.due_at >= lower, Activity.end_at > lower))))
    output = []
    for row in db.scalars(query):
        local_date = row.due_date or row.due_at.astimezone(ZoneInfo(row.timezone)).date()
        last = (row.end_at - timedelta(microseconds=1)).astimezone(ZoneInfo(row.timezone)).date() if row.end_at else local_date
        state = deadline(row)
        if last >= start and local_date < end and (not band or state["band"] == band) and (not bucket or state["bucket"] == bucket):
            output.append({**serialize(row), "calendar_date": local_date.isoformat(), "calendar_end": last.isoformat()})
    return {"items": output, "start": start, "end": end}


@router.get("/activities/{identifier}")
def detail(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession):
    activity = get_activity(db, auth.user, identifier)
    meeting = db.get(Meeting, activity.meeting_id)
    evidence_access = auth.user.role in {"gestor", "desenvolvedor"} or meeting.creator_id == auth.user.id
    history = db.scalars(select(ActivityAudit).where(ActivityAudit.activity_id == identifier).order_by(ActivityAudit.created_at.desc()).limit(100)).all()
    return {**serialize(activity, include_evidence=evidence_access), "can_review": can_review(auth.user, activity),
            "evidence_access": evidence_access,
            "history": [{"action": h.action, "reason": h.reason, "at": h.created_at, "actor_id": h.actor_id} for h in history]}


@router.patch("/activities/{identifier}", dependencies=[Write])
def edit(identifier: uuid.UUID, payload: EditInput, auth: CurrentAuth, db: DbSession):
    activity = get_activity(db, auth.user, identifier, lock=True)
    edit_activity(db, auth.user, activity, payload)
    if inspect(db.connection()).has_table("suppliers"):  # mesma conexão: não descarta a edição pendente
        from app.services.supplier_followups import on_planner_item_closed
        on_planner_item_closed(db, activity, auth.user)
    db.commit()
    return serialize(activity)


@router.post("/activities/{identifier}/review", dependencies=[Write])
def decide(identifier: uuid.UUID, payload: ReviewInput, auth: CurrentAuth, db: DbSession):
    activity = get_activity(db, auth.user, identifier, lock=True)
    review(db, auth.user, activity, payload.decision, payload.version, payload.reason)
    db.commit()
    return serialize(activity)


@router.post("/publish", dependencies=[Write])
def publication(payload: Selections, auth: CurrentAuth, db: DbSession):
    rows = publish(db, auth.user, payload.items)
    db.commit()
    return {"items": [serialize(r) for r in rows]}


@router.post("/review", dependencies=[Write])
def review_batch(payload: ReviewBatch, auth: CurrentAuth, db: DbSession):
    if len({item.id for item in payload.items}) != len(payload.items):
        raise HTTPException(422, "Seleção contém IDs repetidos")
    rows = []
    try:
        for item in sorted(payload.items, key=lambda item: str(item.id)):
            row = get_activity(db, auth.user, item.id, lock=True)
            review(db, auth.user, row, payload.decision, item.version, payload.reason)
            rows.append(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"items": [serialize(row) for row in rows]}


@router.post("/activities/{identifier}/comments", dependencies=[Write])
def comment(identifier: uuid.UUID, payload: CommentInput, auth: CurrentAuth, db: DbSession):
    row = get_activity(db, auth.user, identifier, lock=True)
    # The activity lock serializes retries; comments never change task/deadline versions.
    previous = db.scalar(select(ActivityAudit).where(ActivityAudit.activity_id == row.id,
        ActivityAudit.actor_id == auth.user.id, ActivityAudit.action == "comment",
        ActivityAudit.changes["request_id"].as_string() == str(payload.request_id)))
    if previous:
        if previous.reason != payload.text:
            raise HTTPException(409, "Identificador de comentário já usado com outro texto")
        return {"id": str(previous.id), "created": False}
    entry = ActivityAudit(organization_id=auth.user.organization_id, activity_id=row.id,
        meeting_id=row.meeting_id, actor_id=auth.user.id, action="comment", reason=payload.text,
        changes={"request_id": str(payload.request_id)})
    db.add(entry)
    db.commit()
    return {"id": str(entry.id), "created": True}


@router.post("/assign", dependencies=[Write])
def assignment_batch(payload: AssignmentBatch, auth: CurrentAuth, db: DbSession):
    if len({entry.id for entry in payload.items}) != len(payload.items):
        raise HTTPException(422, "Seleção contém IDs repetidos")
    rows = []
    try:
        for entry in sorted(payload.items, key=lambda item: str(item.id)):
            row = get_activity(db, auth.user, entry.id, lock=True)
            edit_activity(db, auth.user, row, EditInput(version=entry.version,
                assignee_user_id=payload.assignee_user_id, reason=payload.reason))
            rows.append(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"items": [serialize(row) for row in rows]}


@router.post("/export", dependencies=[Write])
def export(payload: ExportInput, auth: CurrentAuth, db: DbSession):
    rows = [get_activity(db, auth.user, identifier) for identifier in dict.fromkeys(payload.ids)]
    result = export_cards(rows, payload.format)
    db.add(ActivityAudit(organization_id=auth.user.organization_id, actor_id=auth.user.id, action="export",
                         reason="Exportação sem transcrição/evidências", changes={"ids": [str(r.id) for r in rows], "format": payload.format}))
    db.commit()
    return Response(result, media_type="application/json" if payload.format == "json" else "text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="cards.{payload.format}"', "Cache-Control": "no-store"})


@router.get("/alerts")
def alerts(auth: CurrentAuth, db: DbSession):
    # Reading never schedules alerts. Worker/publication handles idempotent scheduling.
    query = select(ActivityAlert, Activity).join(Activity, Activity.id == ActivityAlert.activity_id).where(
        ActivityAlert.organization_id == auth.user.organization_id, Activity.organization_id == auth.user.organization_id,
        ActivityAlert.recipient_id == auth.user.id, ActivityAlert.resolved.is_(False),
        Activity.assignee_user_id == auth.user.id, Activity.approval == "published",
        Activity.status.not_in(["done", "cancelled"]), operational_activity())
    from app.services.supplier_followups import category
    return {"items": [{"id": str(a.id), "activity_id": str(row.id), "title": row.title, "kind": a.kind,
                       "read_at": a.read_at, "at": a.created_at, "deadline": deadline(row),
                       "due_date": row.due_date, "due_at": row.due_at, "timezone": row.timezone,
                       "category": category(row.details), "automation": bool((row.details or {}).get("automation")),
                       "supplier_id": (row.details or {}).get("supplier_id"), "supplier_name": (row.details or {}).get("supplier_name"),
                       "suggest_meeting": bool((row.details or {}).get("suggest_meeting"))}
                      for a, row in db.execute(query.order_by(ActivityAlert.created_at.desc()).limit(200))]}


@router.post("/alerts/{identifier}/read", dependencies=[Write])
def read_alert(identifier: uuid.UUID, auth: CurrentAuth, db: DbSession):
    alert = db.scalar(select(ActivityAlert).where(ActivityAlert.id == identifier, ActivityAlert.organization_id == auth.user.organization_id,
                                                ActivityAlert.recipient_id == auth.user.id).with_for_update())
    if not alert:
        raise HTTPException(404, "Alerta não encontrado")
    alert.read_at = alert.read_at or datetime.now(timezone.utc)
    db.commit()
    return {"read": True}
