"""Planner como centro operacional: criação direta e agenda unificada, sem novo armazenamento.

- Tarefas e cards continuam sendo `Activity` (mesmas regras de aprovação, publicação, prazos e alertas).
- Reunião agendada é um `Meeting` + uma `Activity` do tipo evento (o item visual na agenda), ligados entre si.
- Follow-up de fornecedor continua em `SupplierTask` / próxima ação do fornecedor; a agenda só os lê.
- `Activity` exige reunião e execução de origem. Itens avulsos (sem reunião) ficam ancorados num registro
  "Planner · itens avulsos" por organização, criado sob demanda e oculto das listas de reuniões.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, inspect, or_, select
from sqlalchemy.exc import IntegrityError

from app.models import User
from app.models.meetings import Activity, ActivityAudit, Meeting, MeetingRun
from app.services.access import MANAGERS
from app.services.meeting_activities import activity_query, audit, sync_alerts
from app.services.meeting_deadlines import deadline

CONTAINER_KEY = "planner-container"
PRIORITIES = ("baixa", "normal", "alta")
OPEN_ACTIVITY = ("todo", "in_progress", "waiting_external", "blocked")


def not_container():
    return func.coalesce(Meeting.metadata_confirmed["planner_container"].as_boolean(), False).is_(False)


def container(db, user):
    """Registro de origem dos itens criados direto no Planner (um por organização, idempotente)."""
    run = db.scalar(select(MeetingRun).where(MeetingRun.organization_id == user.organization_id, MeetingRun.key == CONTAINER_KEY))
    if run:
        return db.get(Meeting, run.meeting_id), run
    try:
        with db.begin_nested():
            meeting = Meeting(organization_id=user.organization_id, creator_id=user.id, title="Planner · itens avulsos",
                              metadata_confirmed={"planner_container": True}, participants=[], version=1)
            db.add(meeting)
            db.flush()
            run = MeetingRun(organization_id=user.organization_id, meeting_id=meeting.id, stage="planner", key=CONTAINER_KEY,
                             state="succeeded", context={"origin": "planner", "purpose": "itens criados no Planner"})
            db.add(run)
            db.flush()
    except IntegrityError:  # Outra requisição criou o registro ao mesmo tempo.
        run = db.scalar(select(MeetingRun).where(MeetingRun.organization_id == user.organization_id, MeetingRun.key == CONTAINER_KEY))
        meeting = db.get(Meeting, run.meeting_id)
    return meeting, run


def eligible_assignee(db, user, identifier):
    identifier = identifier or user.id
    person = db.scalar(select(User).where(User.id == identifier, User.organization_id == user.organization_id, User.active.is_(True)))
    if not person or (user.role not in MANAGERS and person.id != user.id):
        raise HTTPException(403, "Responsável não elegível; somente gestor atribui a outra pessoa")
    return person


def supplier_scope(db, user, identifier):
    if not identifier:
        return None
    from app.services import suppliers as supplier_service
    supplier = supplier_service.scope(db, user, identifier, lock=True)
    if getattr(supplier, "archived_at", None):
        raise HTTPException(409, "Fornecedor arquivado; restaure-o antes de agendar")
    return supplier


def instant(day, at, zone, minutes=None):
    start = datetime.combine(day, at, ZoneInfo(zone))
    return start, (start + timedelta(minutes=minutes) if minutes else None)


def create_item(db, user, payload):
    """Cria tarefa, card, reunião ou follow-up. O chamador faz o commit."""
    supplier = supplier_scope(db, user, payload.supplier_id)
    origin = "fornecedor" if payload.origin == "supplier" else "planner"
    links = {"supplier_id": str(supplier.id), "supplier_name": supplier.name} if supplier else {}
    if payload.type == "followup":
        return create_followup(db, user, supplier, payload)
    assignee = eligible_assignee(db, user, payload.assignee_user_id)
    if payload.type == "meeting":
        return create_meeting(db, user, supplier, assignee, payload, origin, links)
    meeting, run = container(db, user)
    due_date, due_at = (payload.date, None) if not payload.time else (None, instant(payload.date, payload.time, payload.timezone)[0]) if payload.date else (None, None)
    kind = payload.type
    details = {"planner_kind": kind, "origin": origin, "priority": payload.priority, "created_in_planner": True,
               "edited_by_human": True, **links}
    activity = Activity(organization_id=user.organization_id, meeting_id=meeting.id, analysis_run_id=run.id,
                        proposal_local_id=uuid.uuid4().hex, creator_id=user.id, assignee_user_id=assignee.id,
                        kind="task", title=payload.title, description=payload.description, approval="draft",
                        status="todo", due_date=due_date, due_at=due_at, timezone=payload.timezone,
                        no_deadline_accepted=payload.no_deadline_accepted and not (due_date or due_at), details=details)
    if kind == "task":
        # Tarefa criada por uma pessoa não passa pela revisão de propostas da IA: entra publicada.
        if not (due_date or due_at or activity.no_deadline_accepted):
            raise HTTPException(422, "Informe o prazo ou marque explicitamente “sem prazo”")
        activity.approval = "published"
    db.add(activity)
    db.flush()
    audit(db, user, activity, "created_in_planner", "Criado no Planner" if kind == "task" else "Card criado no Planner para revisão",
          {"type": kind, "origin": origin, **links})
    if kind == "task":
        sync_alerts(db, activity)
    if supplier:
        supplier_note(db, user, supplier, "planner_task_created" if kind == "task" else "planner_card_created", {"title": payload.title, "activity_id": str(activity.id)})
    return {"type": kind, "activity_id": str(activity.id)}


def create_meeting(db, user, supplier, assignee, payload, origin, links):
    if not payload.date:
        raise HTTPException(422, "Reunião precisa de data")
    schedule = schedule_data(payload, assignee)
    meeting = Meeting(organization_id=user.organization_id, creator_id=user.id, title=payload.title,
                      partner=supplier.name if supplier else payload.partner, meeting_date=payload.date, timezone=payload.timezone,
                      metadata_confirmed={"schedule": schedule, "origin": origin, **links}, participants=[], version=1)
    db.add(meeting)
    db.flush()
    run = MeetingRun(organization_id=user.organization_id, meeting_id=meeting.id, stage="schedule",
                     key=f"schedule-{meeting.id.hex}", state="succeeded", context={"origin": origin, **links})
    db.add(run)
    db.flush()
    due_date, due_at, end_at = event_window(payload)
    event = Activity(organization_id=user.organization_id, meeting_id=meeting.id, analysis_run_id=run.id,
                     proposal_local_id="meeting-event", creator_id=user.id, assignee_user_id=assignee.id, kind="event",
                     title=payload.title, description=payload.description, approval="published", status="todo",
                     due_date=due_date, due_at=due_at, end_at=end_at, timezone=payload.timezone,
                     details={"planner_kind": "meeting", "origin": origin, "priority": payload.priority,
                              "created_in_planner": True, "edited_by_human": True, "schedule": schedule, **links})
    db.add(event)
    db.flush()
    audit(db, user, event, "meeting_scheduled", "Reunião agendada no " + ("fornecedor" if origin == "fornecedor" else "Planner"),
          {"meeting_id": str(meeting.id), **links})
    sync_alerts(db, event)
    if supplier:
        supplier_note(db, user, supplier, "meeting_scheduled", {"title": payload.title, "meeting_id": str(meeting.id),
                                                               "date": payload.date.isoformat(), "time": payload.time.isoformat() if payload.time else None})
    return {"type": "meeting", "meeting_id": str(meeting.id), "activity_id": str(event.id)}


def schedule_data(payload, assignee):
    return {"time": payload.time.strftime("%H:%M") if payload.time else None, "duration_minutes": payload.duration_minutes,
            "participants": payload.participants, "location": payload.location, "notes": payload.description,
            "responsible_user_id": str(assignee.id)}


def event_window(payload):
    if payload.time:
        start, end = instant(payload.date, payload.time, payload.timezone, payload.duration_minutes)
        return None, start, end
    return payload.date, None, None


def reschedule(db, user, meeting, payload):
    """Edita/reagenda a reunião e o item da agenda juntos (mesma versão otimista da reunião)."""
    if meeting.version != payload.version:
        raise HTTPException(409, "Registro alterado por outra pessoa; recarregue antes de salvar")
    event = db.scalar(select(Activity).where(Activity.meeting_id == meeting.id, Activity.proposal_local_id == "meeting-event").with_for_update())
    if not event:
        raise HTTPException(409, "Esta reunião não tem item de agenda; ela foi importada por transcrição")
    assignee = eligible_assignee(db, user, payload.assignee_user_id or event.assignee_user_id)
    schedule = schedule_data(payload, assignee)
    before = {"title": meeting.title, "date": meeting.meeting_date.isoformat() if meeting.meeting_date else None,
              "schedule": (meeting.metadata_confirmed or {}).get("schedule")}
    meeting.title, meeting.meeting_date, meeting.timezone = payload.title, payload.date, payload.timezone
    meeting.metadata_confirmed = {**(meeting.metadata_confirmed or {}), "schedule": schedule}
    meeting.version += 1
    old_deadline = (event.due_date, event.due_at, event.assignee_user_id, event.timezone)
    event.title, event.description = payload.title, payload.description
    event.due_date, event.due_at, event.end_at = event_window(payload)
    event.assignee_user_id, event.timezone = assignee.id, payload.timezone
    event.status = payload.status
    event.completed_at = (event.completed_at or datetime.now(timezone.utc)) if payload.status == "done" else None
    event.details = {**event.details, "schedule": schedule, "priority": payload.priority, "edited_by_human": True}
    if old_deadline != (event.due_date, event.due_at, event.assignee_user_id, event.timezone):
        event.deadline_version += 1
    event.version += 1
    db.add(ActivityAudit(organization_id=user.organization_id, activity_id=event.id, meeting_id=meeting.id, actor_id=user.id,
                         action="meeting_rescheduled", reason=payload.reason,
                         changes={"before": before, "after": {"title": payload.title, "date": payload.date.isoformat(), "schedule": schedule}}))
    sync_alerts(db, event)
    return {"version": meeting.version, "activity_id": str(event.id)}


def create_followup(db, user, supplier, payload):
    if not supplier:
        raise HTTPException(422, "Follow-up exige um fornecedor")
    from app.models.suppliers import SupplierTask
    from app.services import suppliers as supplier_service
    owner = payload.assignee_user_id or user.id
    supplier_service.responsible(db, user, owner)
    task = SupplierTask(supplier_id=supplier.id, organization_id=supplier.organization_id, actor_id=user.id, assignee_user_id=owner,
                        data={"title": payload.title, "description": payload.description, "due_date": payload.date.isoformat() if payload.date else None,
                              "priority": payload.priority, "status": "pendente", "completed_at": None, "origin": "planner"})
    db.add(task)
    supplier_service.audit(db, supplier, user, "task_created", {"title": payload.title, "origin": "planner"})
    supplier_service.touch(supplier)
    db.flush()
    return {"type": "followup", "supplier_id": str(supplier.id), "task_id": str(task.id)}


def supplier_note(db, user, supplier, event, data):
    from app.services import suppliers as supplier_service
    supplier_service.audit(db, supplier, user, event, data)
    supplier_service.touch(supplier)


# --------------------------------------------------------------------------------------------- agenda unificada

def item_type(activity):
    kind = (activity.details or {}).get("planner_kind")
    if kind == "meeting" or activity.kind == "event":
        return "meeting"
    if kind == "followup":
        return "followup"
    return "task" if kind == "task" else "card"


def local_day(activity):
    if activity.due_date:
        return activity.due_date
    if activity.due_at:
        at = activity.due_at if activity.due_at.tzinfo else activity.due_at.replace(tzinfo=timezone.utc)
        return at.astimezone(ZoneInfo(activity.timezone)).date()
    return None


def from_activity(activity, now, meetings):
    details = activity.details or {}
    meeting = meetings.get(activity.meeting_id)
    planner_meeting = details.get("planner_kind") == "meeting"
    day = local_day(activity)
    state = deadline(activity, now)
    return {"key": f"activity:{activity.id}", "type": item_type(activity), "source": "activity", "id": str(activity.id),
            "activity_id": str(activity.id), "meeting_id": str(activity.meeting_id) if meeting and not meeting.get("container") else None,
            "meeting_title": meeting["title"] if meeting and not meeting.get("container") else None,
            "title": activity.title, "description": activity.description, "date": day.isoformat() if day else None,
            "start": activity.due_at.isoformat() if activity.due_at else None, "end": activity.end_at.isoformat() if activity.end_at else None,
            "timezone": activity.timezone, "assignee_user_id": str(activity.assignee_user_id) if activity.assignee_user_id else None,
            "status": activity.status, "approval": activity.approval, "band": state["band"],
            "overdue": state["band"] == "overdue", "priority": details.get("priority") or "normal",
            "supplier_id": details.get("supplier_id"), "supplier_name": details.get("supplier_name"),
            "origin": details.get("origin") or ("ia" if details.get("field_origin") == "ai" else "reuniao"),
            "schedule": details.get("schedule"), "version": activity.version, "source_type": details.get("source_type"),
            "category": details.get("category"), "automation": bool(details.get("automation")),
            "open": planner_meeting and "meeting" or "activity"}


def activities_in(db, user, start, end, now):
    lower = datetime.combine(start - timedelta(days=1), time.min, timezone.utc)
    upper = datetime.combine(end + timedelta(days=1), time.min, timezone.utc)
    base = activity_query(user).where(Activity.approval != "rejected")
    dated = base.where(or_((Activity.due_date >= start) & (Activity.due_date < end),
                           (Activity.due_at < upper) & (or_(Activity.due_at >= lower, Activity.end_at > lower))))
    overdue = base.where(Activity.approval == "published", Activity.status.in_(OPEN_ACTIVITY),
                         or_(Activity.due_date < start, Activity.due_at < lower))
    undated = base.where(Activity.due_date.is_(None), Activity.due_at.is_(None), Activity.status.in_(OPEN_ACTIVITY))
    rows = {}
    for query, limit in ((dated, 2000), (overdue, 500), (undated, 300)):
        for row in db.scalars(query.order_by(Activity.created_at.desc()).limit(limit)):
            rows[row.id] = row
    return list(rows.values())


def meeting_index(db, user, ids):
    if not ids:
        return {}
    rows = db.execute(select(Meeting.id, Meeting.title, Meeting.metadata_confirmed).where(
        Meeting.organization_id == user.organization_id, Meeting.id.in_(ids))).all()
    return {r.id: {"title": r.title, "container": bool((r.metadata_confirmed or {}).get("planner_container"))} for r in rows}


def meetings_without_event(db, user, start, end):
    """Reuniões importadas por transcrição (sem item de agenda) aparecem no dia registrado."""
    query = select(Meeting).where(Meeting.organization_id == user.organization_id, not_container(),
                                  Meeting.meeting_date >= start, Meeting.meeting_date < end)
    if user.role not in MANAGERS:
        query = query.where(Meeting.creator_id == user.id)
    scheduled = select(Activity.meeting_id).where(Activity.organization_id == user.organization_id,
                                                  Activity.proposal_local_id == "meeting-event")
    query = query.where(Meeting.id.not_in(scheduled))
    return [{"key": f"meeting:{m.id}", "type": "meeting", "source": "meeting", "id": str(m.id), "meeting_id": str(m.id),
             "activity_id": None, "meeting_title": m.title, "title": m.title, "description": "", "date": m.meeting_date.isoformat(),
             "start": None, "end": None, "timezone": m.timezone, "assignee_user_id": str(m.creator_id), "status": "done",
             "approval": "published", "band": "done", "overdue": False, "priority": "normal",
             "supplier_id": (m.metadata_confirmed or {}).get("supplier_id"), "supplier_name": m.partner or None,
             "origin": "reuniao", "schedule": None, "version": m.version, "open": "meeting"}
            for m in db.scalars(query.limit(500))]


def supplier_items(db, user, start, end, today):
    if not inspect(db.connection()).has_table("suppliers"):
        return []
    from app.models.suppliers import Supplier, SupplierTask
    query = select(Supplier).where(Supplier.organization_id == user.organization_id)
    if hasattr(Supplier, "archived_at"):
        query = query.where(Supplier.archived_at.is_(None))
    if user.role not in MANAGERS:
        query = query.where(Supplier.responsible_user_id == user.id)
    suppliers = {s.id: s for s in db.scalars(query)}
    if not suppliers:
        return []
    output = []

    def keep(day, done):
        if not day:
            return not done
        return start <= day < end or (day < start and not done)

    for task in db.scalars(select(SupplierTask).where(SupplierTask.organization_id == user.organization_id,
                                                      SupplierTask.supplier_id.in_(list(suppliers)))):
        data, supplier = task.data or {}, suppliers[task.supplier_id]
        day = date.fromisoformat(data["due_date"]) if data.get("due_date") else None
        done = data.get("status") == "concluida"
        if not keep(day, done):
            continue
        output.append({"key": f"supplier-task:{task.id}", "type": "followup", "source": "supplier_task", "id": str(task.id),
                       "activity_id": None, "meeting_id": None, "meeting_title": None, "title": data.get("title") or "Tarefa do fornecedor",
                       "description": data.get("description") or "", "date": day.isoformat() if day else None, "start": None, "end": None,
                       "timezone": "America/Sao_Paulo", "assignee_user_id": str(task.assignee_user_id), "status": "done" if done else "todo",
                       "approval": "published", "band": "done" if done else ("overdue" if day and day < today else "on_time" if day else "no_deadline"),
                       "overdue": bool(day and day < today and not done), "priority": data.get("priority") or "normal",
                       "supplier_id": str(supplier.id), "supplier_name": supplier.name, "origin": data.get("origin") or "fornecedor",
                       "schedule": None, "version": None, "open": "supplier", "task": data})
    mirrored = mirrored_next_actions(db, user, [str(i) for i in suppliers])
    for supplier in suppliers.values():
        data = supplier.data or {}
        if not data.get("next_action") or str(supplier.id) in mirrored:
            continue  # a próxima ação já está na agenda como item próprio (espelho único)
        day = date.fromisoformat(data["next_action_date"]) if data.get("next_action_date") else None
        if not keep(day, False):
            continue
        output.append({"key": f"supplier-next:{supplier.id}", "type": "followup", "source": "supplier_next", "id": str(supplier.id),
                       "activity_id": None, "meeting_id": None, "meeting_title": None, "title": data["next_action"],
                       "description": "Próxima ação do fornecedor", "date": day.isoformat() if day else None, "start": None, "end": None,
                       "timezone": "America/Sao_Paulo", "assignee_user_id": str(supplier.responsible_user_id), "status": "todo",
                       "approval": "published", "band": "overdue" if day and day < today else "on_time" if day else "no_deadline",
                       "overdue": bool(day and day < today), "priority": "normal", "supplier_id": str(supplier.id),
                       "supplier_name": supplier.name, "origin": "fornecedor", "schedule": None, "version": None, "open": "supplier"})
    return output


def mirrored_next_actions(db, user, supplier_ids):
    if not supplier_ids:
        return set()
    from app.services.supplier_followups import OPEN as FOLLOWUP_OPEN, Source
    rows = db.scalars(select(Activity.details).where(Activity.organization_id == user.organization_id, Activity.status.in_(FOLLOWUP_OPEN),
                                                     Activity.details["source_type"].as_string() == Source.NEXT_ACTION,
                                                     Activity.details["supplier_id"].as_string().in_(supplier_ids)))
    return {d.get("supplier_id") for d in rows}


def feed(db, user, start, end, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Sao_Paulo")).date()
    rows = activities_in(db, user, start, end, now)
    meetings = meeting_index(db, user, {r.meeting_id for r in rows})
    items = [from_activity(r, now, meetings) for r in rows]
    items += meetings_without_event(db, user, start, end)
    items += supplier_items(db, user, start, end, today)
    items.sort(key=lambda i: (i["date"] or "9999-99-99", i["start"] or "", i["title"].casefold()))
    return {"start": start.isoformat(), "end": end.isoformat(), "today": today.isoformat(), "items": items}


def summary(db, user, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Sao_Paulo")).date()
    items = feed(db, user, today, today + timedelta(days=1), now)["items"]
    open_item = lambda i: i["status"] not in {"done", "cancelled"}
    review = db.scalar(select(func.count()).select_from(
        activity_query(user).where(Activity.approval.in_(["draft", "approved"])).subquery()))
    followups = [i for i in items if i["type"] == "followup" and open_item(i) and i["date"]]
    supplier_counts = {"suppliers_inactive": 0, "hot_no_next": 0}
    if inspect(db.connection()).has_table("suppliers"):
        from app.services.supplier_followups import summary_counts
        supplier_counts = summary_counts(db, user)
    return {"today": today.isoformat(),
            "meetings_today": sum(1 for i in items if i["type"] == "meeting" and i["date"] == today.isoformat() and i["status"] != "cancelled"),
            "overdue_tasks": sum(1 for i in items if i["type"] in {"task", "card"} and i["overdue"] and open_item(i)),
            "cards_review": review or 0,
            "followups": sum(1 for i in followups if i["date"] <= today.isoformat()),
            "followups_overdue": sum(1 for i in followups if i["date"] < today.isoformat()),
            "followups_today": sum(1 for i in followups if i["date"] == today.isoformat()),
            **supplier_counts}
