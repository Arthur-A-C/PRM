"""Authorization, optimistic concurrency, publication and notification lifecycle."""
import csv
import io
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, or_, func
from app.models import User
from app.models.meetings import Meeting, Activity, ActivityAudit, ActivityAlert
from app.services.meeting_deadlines import deadline


def activity_query(user):
    query = select(Activity).where(Activity.organization_id == user.organization_id, operational_activity())
    if user.role not in {"gestor", "desenvolvedor"}:
        query = query.where(or_(Activity.creator_id == user.id, Activity.assignee_user_id == user.id))
    return query


def operational_activity():
    """Exclude fixture/staging proposals without deleting their history."""
    return func.coalesce(Activity.details["simulation"].as_boolean(), False).is_(False)


def get_activity(db, user, identifier, lock=False):
    query = activity_query(user).where(Activity.id == identifier)
    activity = db.scalar(query.with_for_update() if lock else query)
    if not activity:
        raise HTTPException(404, "Atividade não encontrada")
    return activity


def get_meeting(db, user, identifier, lock=False):
    query = select(Meeting).where(Meeting.organization_id == user.organization_id, Meeting.id == identifier)
    if user.role not in {"gestor", "desenvolvedor"}:
        query = query.where(Meeting.creator_id == user.id)
    meeting = db.scalar(query.with_for_update() if lock else query)
    if not meeting:
        raise HTTPException(404, "Reunião não encontrada ou transcrição não compartilhada")
    return meeting


def can_review(user, activity):
    return user.role in {"gestor", "desenvolvedor"} or activity.creator_id == user.id


def version_check(entity, expected):
    if entity.version != expected:
        raise HTTPException(409, "Registro alterado por outra pessoa; recarregue antes de salvar")


def serialize(activity, now=None, include_evidence=False):
    details = dict(activity.details)
    if not include_evidence:
        details["original"] = {k: v for k, v in details.get("original", {}).items() if k != "evidence"}
    return {"id": str(activity.id), "meeting_id": str(activity.meeting_id), "title": activity.title,
            "description": activity.description, "kind": activity.kind, "approval": activity.approval,
            "status": activity.status, "assignee_user_id": str(activity.assignee_user_id) if activity.assignee_user_id else None,
            "due_date": activity.due_date.isoformat() if activity.due_date else None,
            "due_at": activity.due_at.isoformat() if activity.due_at else None,
            "end_at": activity.end_at.isoformat() if activity.end_at else None,
            "timezone": activity.timezone, "no_deadline_accepted": activity.no_deadline_accepted,
            "version": activity.version, "deadline": deadline(activity, now), "details": details,
            "url": f"/cards?activity={activity.id}"}


def audit(db, user, activity, action, reason, changes):
    db.add(ActivityAudit(organization_id=user.organization_id, activity_id=activity.id, meeting_id=activity.meeting_id,
                         actor_id=user.id, action=action, reason=reason, changes=changes))


def sync_alerts(db, activity, now=None):
    now = now or datetime.now(timezone.utc)
    existing = db.scalars(select(ActivityAlert).where(ActivityAlert.activity_id == activity.id)).all()
    state = deadline(activity, now)
    kind = "overdue" if state["band"] == "overdue" else "today" if state.get("days") == 0 else "soon" if state["band"] in {"attention", "prioritize"} else "no_deadline" if state["band"] in {"no_deadline", "unconfirmed"} else None
    assignee = db.get(User, activity.assignee_user_id) if activity.assignee_user_id else None
    active = (activity.approval == "published" and activity.status not in {"done", "cancelled"}
              and not activity.details.get("simulation") and assignee and assignee.active
              and assignee.organization_id == activity.organization_id)
    for alert in existing:
        if not active or alert.deadline_version != activity.deadline_version or alert.recipient_id != activity.assignee_user_id or (alert.kind != kind and alert.kind != "assigned"):
            alert.resolved = True
    if not active:
        return
    for alert_kind in ["assigned", kind]:
        match = next((a for a in existing if a.deadline_version == activity.deadline_version
                      and a.recipient_id == activity.assignee_user_id and a.kind == alert_kind), None)
        if alert_kind and match:
            if match.resolved:
                match.resolved = False
                match.read_at = None
        elif alert_kind:
            db.add(ActivityAlert(organization_id=activity.organization_id, activity_id=activity.id,
                                 recipient_id=activity.assignee_user_id, deadline_version=activity.deadline_version, kind=alert_kind))


def edit_activity(db, user, activity, payload):
    if activity.details.get("simulation"):
        raise HTTPException(409, "Exemplos de staging não são cards operacionais.")
    version_check(activity, payload.version)
    before = serialize(activity)
    changes = payload.model_dump(exclude_unset=True)
    allowed = {"status"} if not can_review(user, activity) else {
        "title", "description", "assignee_user_id", "due_date", "due_at", "end_at", "timezone",
        "no_deadline_accepted", "status", "checklist"}
    if set(changes) - allowed - {"version", "reason"}:
        raise HTTPException(403, "Sem permissão para editar esses campos")
    if "assignee_user_id" in changes and changes["assignee_user_id"]:
        assigned = db.scalar(select(User).where(User.id == changes["assignee_user_id"], User.organization_id == user.organization_id, User.active.is_(True)))
        if not assigned or (user.role not in {"gestor", "desenvolvedor"} and assigned.id != user.id):
            raise HTTPException(403, "Responsável não elegível; somente gestor atribui a outra pessoa")
    for field in allowed & changes.keys():
        if field == "checklist":
            activity.details = {**activity.details, "checklist": changes[field], "edited_by_human": True}
        else:
            setattr(activity, field, changes[field])
    if activity.due_date and activity.due_at:
        raise HTTPException(422, "Informe data OU instante, não ambos")
    if activity.end_at and (not activity.due_at or activity.end_at <= activity.due_at):
        raise HTTPException(422, "Fim exige início anterior confirmado")
    if activity.kind == "event" and activity.approval == "published" and not (activity.due_date or activity.due_at):
        raise HTTPException(422, "Evento publicado precisa de data")
    if activity.approval == "published" and (not activity.assignee_user_id or not (activity.due_date or activity.due_at or activity.no_deadline_accepted)):
        raise HTTPException(422, "Publicação exige responsável e prazo ou aceite explícito sem prazo")
    after = serialize(activity)
    if any(before[k] != after[k] for k in ["due_date", "due_at", "assignee_user_id", "timezone"]):
        activity.deadline_version += 1
    activity.version += 1
    if activity.status == "done" and not activity.completed_at:
        activity.completed_at = datetime.now(timezone.utc)
    elif activity.status != "done":
        activity.completed_at = None
    if activity.approval == "approved":
        activity.approval = "draft"
    activity.details = {**activity.details, "edited_by_human": True}
    audit(db, user, activity, "edit", payload.reason, {"before": before, "after": serialize(activity)})
    sync_alerts(db, activity)


def review(db, user, activity, decision, expected, reason):
    if not can_review(user, activity):
        raise HTTPException(403, "Somente curador da reunião ou gestor pode revisar")
    version_check(activity, expected)
    if activity.approval == "published":
        raise HTTPException(409, "Atividade já publicada")
    if decision == "approved" and not activity.assignee_user_id:
        raise HTTPException(422, "Atribua um responsável interno antes de aprovar")
    activity.approval = decision
    activity.version += 1
    audit(db, user, activity, decision, reason, {})


def publish(db, user, selections):
    # Lock in stable order. Validate all items before committing any publication.
    entries = sorted(selections, key=lambda item: str(item.id))
    rows = [get_activity(db, user, entry.id, lock=True) for entry in entries]
    for entry, row in zip(entries, rows):
        if not can_review(user, row):
            raise HTTPException(403, "Publicação não autorizada")
        if row.approval == "published":
            continue  # Repeated publish returns same entity, no extra task/notification.
        version_check(row, entry.version)
        if row.approval != "approved" or not row.assignee_user_id:
            raise HTTPException(422, "Seleção contém card não aprovado/sem responsável")
        assignee = db.get(User, row.assignee_user_id)
        if not assignee or not assignee.active or assignee.organization_id != user.organization_id:
            raise HTTPException(422, "Responsável inativo ou fora da organização")
        if not (row.due_date or row.due_at) and (row.kind == "event" or not row.no_deadline_accepted):
            raise HTTPException(422, "Evento precisa de data; tarefa sem prazo exige aceite explícito")
    for row in rows:
        if row.approval == "published":
            continue
        row.approval = "published"
        row.version += 1
        audit(db, user, row, "published", "Publicação explícita após revisão", {})
        sync_alerts(db, row)
    return rows


def export_cards(rows, fmt):
    timestamp = datetime.now(timezone.utc).isoformat()
    if fmt == "json":
        return json.dumps({"card_export_schema_version": "1.0", "exported_at": timestamp,
                           "count": len(rows), "cards": [serialize(row) for row in rows]}, ensure_ascii=False).encode("utf-8")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["ID", "Título", "Descrição", "Tipo", "Publicação", "Status", "Responsável", "Data", "Instante", "Fuso", "Link", "Exportado em"])
    def safe(value):
        value = str(value or "")
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value
    for a in rows:
        writer.writerow([safe(v) for v in [a.id, a.title, a.description, a.kind, a.approval, a.status,
                                           a.assignee_user_id, a.due_date, a.due_at, a.timezone, f"/cards?activity={a.id}", timestamp]])
    return output.getvalue().encode("utf-8-sig")
