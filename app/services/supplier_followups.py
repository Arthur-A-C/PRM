"""Follow-up automático de fornecedores: regras avaliadas em lote e entregues ao Planner.

Cada regra gera, no máximo, um item aberto por fornecedor (e por documento/limite, no caso de validade).
O item é uma `Activity` publicada (tipo Follow-up no Planner), atribuída ao responsável atual do fornecedor e com
alerta em Meus alertas pelo mecanismo já existente (`sync_alerts`). Nada é apagado: quando a condição deixa de
existir o item é concluído/cancelado com o motivo e auditoria.

Idempotência:
- chave lógica = organização + fornecedor + regra (+ documento, limite e data de validade);
- antes de criar, procura item aberto da mesma chave; a avaliação trava as linhas do fornecedor;
- a chave também vai para `proposal_local_id` (único por organização/execução no banco) como trava final;
- um episódio encerrado por uma pessoa não é recriado até a condição recomeçar (ex.: nova interação).

Reuniões nunca são criadas aqui: a regra de fornecedor quente apenas sugere “Agendar reunião”.
"""
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, inspect, or_, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models import User
from app.models.meetings import Activity, ActivityAudit
from app.models.suppliers import Supplier, SupplierDocument, SupplierInteraction, SupplierTask
from app.services.meeting_activities import activity_query, sync_alerts

ZONE = ZoneInfo("America/Sao_Paulo")
OPEN = ("todo", "in_progress", "waiting_external", "blocked")


class Source:
    """Valores de `details.source_type` dos itens automáticos (únicos pontos de verdade)."""
    INACTIVE = "supplier_inactive"
    HOT_NO_NEXT = "supplier_hot_no_next"
    WAITING_REPLY = "supplier_waiting_reply"
    MISSING_REGISTRATION = "supplier_missing_registration"
    DOCUMENT_EXPIRING = "supplier_document_expiring"
    NEXT_ACTION = "supplier_next_action"


@dataclass(frozen=True)
class Rule:
    code: str          # parte curta da chave lógica
    category: str      # rótulo em Meus alertas e no Planner
    priority: str = "normal"
    suggest_meeting: bool = False


RULES = {
    Source.INACTIVE: Rule("ina", "Sem interação"),
    Source.HOT_NO_NEXT: Rule("hot", "Fornecedor quente", "alta", suggest_meeting=True),
    Source.WAITING_REPLY: Rule("wai", "Follow-up"),
    Source.MISSING_REGISTRATION: Rule("reg", "Documento"),
    Source.DOCUMENT_EXPIRING: Rule("d", "Documento"),
    Source.NEXT_ACTION: Rule("nxt", "Próxima ação"),
}

# Etapas e categorias do CRM usadas pelas regras (chaves de app.services.suppliers.STAGES / CATEGORIES).
WAITING_REPLY_STAGE = "aguardando"
REGISTRATION_REQUIRED_STAGES = frozenset({"documentacao", "homologacao", "negociacao", "ativo"})
DORMANT_STAGES = frozenset({"congelado", "descartado"})  # fornecedor parado: sem cobranças automáticas
HOT_SCORE = "quente"
REGISTRATION_CATEGORY = "Ficha cadastral"
REPLACED_DOCUMENT_STATUS = "Substituído"
INTERACTION_EVENTS = ("interaction_created",)  # o que conta como “interação registrada”
HOT_PROGRESS_EVENTS = ("score_changed", "next_action_changed")
STAGE_EVENTS = ("stage_changed",)


def aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def local_today(now):
    return now.astimezone(ZONE).date()


def business_day(day):
    """Prazo padrão dos itens automáticos: hoje, ou o próximo dia útil (seg–sex)."""
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def is_automation():
    return func.coalesce(Activity.details["automation"].as_boolean(), False).is_(True)


def item_key(details):
    return (details.get("supplier_id"), details.get("source_type"), details.get("document_key") or "")


def category(details):
    rule = RULES.get((details or {}).get("source_type"))
    return rule.category if rule else None


@dataclass
class Spec:
    source: str
    supplier: Supplier
    title: str
    description: str
    due_date: date | None = None
    due_at: datetime | None = None
    no_deadline: bool = False
    reference: datetime | None = None      # início do episódio (recriação só depois disso)
    document_key: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def key(self):
        return (str(self.supplier.id), self.source, self.document_key)


# ----------------------------------------------------------------------------------------------- avaliação

def evaluate(db, now=None, supplier_ids=None, organization_id=None, settings=None):
    """Avalia as regras em lote (worker) ou para alguns fornecedores (ações na tela). O chamador faz o commit."""
    settings = settings or get_settings()
    now = now or datetime.now(timezone.utc)
    today = local_today(now)
    query = select(Supplier)
    if organization_id:
        query = query.where(Supplier.organization_id == organization_id)
    if supplier_ids is not None:
        if not supplier_ids:
            return {}
        query = query.where(Supplier.id.in_(list(supplier_ids)))
    suppliers = list(db.scalars(query.order_by(Supplier.id).with_for_update(skip_locked=supplier_ids is None)))
    live = [s for s in suppliers if getattr(s, "archived_at", None) is None]
    ids = [s.id for s in live]
    last = lambda events: dict(db.execute(select(SupplierInteraction.supplier_id, func.max(SupplierInteraction.created_at)).where(
        SupplierInteraction.supplier_id.in_(ids), SupplierInteraction.event.in_(events)).group_by(SupplierInteraction.supplier_id)).all()) if ids else {}
    contacts, stage_changes, hot_changes = last(INTERACTION_EVENTS), last(STAGE_EVENTS), last(HOT_PROGRESS_EVENTS)
    documents = list(db.scalars(select(SupplierDocument).where(SupplierDocument.supplier_id.in_(ids)))) if ids else []
    future_tasks = {t.supplier_id for t in db.scalars(select(SupplierTask).where(SupplierTask.supplier_id.in_(ids)))
                    if (t.data or {}).get("status") == "pendente" and (t.data or {}).get("due_date") and t.data["due_date"] >= today.isoformat()} if ids else set()
    items = automation_items(db, [str(s.id) for s in suppliers] if supplier_ids is not None else None, organization_id, now)
    linked_future = linked_future_actions(db, [str(i) for i in ids], today)

    desired = {}
    for supplier in live:
        for spec in supplier_specs(supplier, now, today, settings, contacts, stage_changes, hot_changes, documents, future_tasks, linked_future):
            desired[spec.key] = spec

    open_items = {item_key(a.details): a for a in items if a.status in OPEN}
    latest = {}
    for a in items:
        key = item_key(a.details)
        latest[key] = max(latest.get(key, aware(a.created_at)), aware(a.created_at))
    known = {str(s.id): s for s in suppliers}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({s.responsible_user_id for s in suppliers})))} if suppliers else {}
    stats = {"created": 0, "updated": 0, "resolved": 0}

    for key, activity in open_items.items():
        spec = desired.get(key)
        if spec:
            stats["updated"] += update_item(db, activity, spec)
            continue
        supplier = known.get(key[0])
        if supplier is None and supplier_ids is not None:
            continue  # fora do recorte desta avaliação
        if supplier is None:
            reason, status = "Fornecedor excluído", "cancelled"
        elif getattr(supplier, "archived_at", None):
            reason, status = "Fornecedor arquivado", "cancelled"
        else:
            reason, status = resolution_reason(activity, contacts.get(supplier.id)), "done"
        resolve(db, activity, status, reason)
        stats["resolved"] += 1
    for key, spec in desired.items():
        if key in open_items:
            continue
        previous = latest.get(key)
        if previous and spec.reference and previous >= aware(spec.reference):
            continue  # já houve um item neste episódio (encerrado por alguém); não insistir
        if previous and spec.source == Source.DOCUMENT_EXPIRING:
            continue  # cada limite de validade avisa uma única vez
        owner = users.get(spec.supplier.responsible_user_id)
        if owner is None:
            continue
        try:
            with db.begin_nested():
                create_item(db, owner, spec, now)
            stats["created"] += 1
        except IntegrityError:
            pass  # outra avaliação criou o mesmo episódio ao mesmo tempo
    return stats


def supplier_specs(s, now, today, settings, contacts, stage_changes, hot_changes, documents, future_tasks, linked_future):
    data, sid = s.data or {}, s.id
    created = aware(s.created_at) or now
    last_contact = max(filter(None, [aware(contacts.get(sid)), created]))
    idle_days = (now - last_contact).days
    when = last_contact.astimezone(ZONE).strftime("%d/%m")
    due = business_day(today)
    specs = []
    if data.get("next_action"):
        due_date, due_at = next_action_due(data)
        specs.append(Spec(Source.NEXT_ACTION, s, data["next_action"][:240], f"Próxima ação de {s.name}.", due_date, due_at,
                          no_deadline=not (due_date or due_at), reference=aware(hot_changes.get(sid)) or created,
                          extra={"mirror": mirror_of(data)}))
    if s.stage in DORMANT_STAGES:
        return specs
    if idle_days >= settings.supplier_followup_inactive_days:
        specs.append(Spec(Source.INACTIVE, s, f"{s.name} está há {idle_days} dias sem interação"[:240],
                          f"Última interação registrada em {when}. Registre o contato ou crie um follow-up.", due, reference=last_contact))
    if s.stage == WAITING_REPLY_STAGE and idle_days >= settings.supplier_waiting_reply_days:
        specs.append(Spec(Source.WAITING_REPLY, s, f"Cobrar retorno — {s.name}"[:240],
                          f"Aguardando retorno desde {when}. Registre a resposta do fornecedor para concluir.", due, reference=last_contact))
    future_next = bool(data.get("next_action") and data.get("next_action_date") and data["next_action_date"] >= today.isoformat())
    if s.score == HOT_SCORE and not (future_next or sid in future_tasks or str(sid) in linked_future):
        specs.append(Spec(Source.HOT_NO_NEXT, s, f"{s.name}: fornecedor quente sem próxima ação"[:240],
                          "Defina a próxima ação ou agende uma reunião.", due,
                          reference=max(filter(None, [aware(hot_changes.get(sid)), created]))))
    own_docs = [d for d in documents if d.supplier_id == sid and (d.data or {}).get("status") != REPLACED_DOCUMENT_STATUS]
    reached = max(filter(None, [aware(stage_changes.get(sid)), created]))
    if (s.stage in REGISTRATION_REQUIRED_STAGES and (now - reached).days >= settings.supplier_registration_grace_days
            and not any((d.data or {}).get("category") == REGISTRATION_CATEGORY for d in own_docs)):
        specs.append(Spec(Source.MISSING_REGISTRATION, s, f"{s.name}: ficha cadastral pendente"[:240],
                          "A etapa atual exige a ficha cadastral. Anexe o documento na categoria “Ficha cadastral”.", due, reference=reached))
    for doc in own_docs:
        spec = document_spec(s, doc, today, settings)
        if spec:
            specs.append(spec)
    return specs


def document_spec(s, doc, today, settings):
    data = doc.data or {}
    try:
        valid = date.fromisoformat(data.get("valid_until") or "")
    except ValueError:
        return None
    days = (valid - today).days
    limits = sorted(set(settings.supplier_document_warning_days))
    limit = next((t for t in limits if days <= t), None)
    if limit is None:
        return None
    name = data.get("description") or data.get("original_name") or data.get("category") or "Documento"
    title = (f"{name} de {s.name} vence em {days} dias" if days > 0 else f"{name} de {s.name} vence hoje" if days == 0
             else f"{name} de {s.name} venceu em {valid.strftime('%d/%m/%Y')}")
    return Spec(Source.DOCUMENT_EXPIRING, s, title[:240], f"Validade: {valid.strftime('%d/%m/%Y')}. Atualize o documento ou registre a renovação.",
                valid, document_key=f"{doc.id.hex}:{limit}:{valid.strftime('%y%m%d')}",
                extra={"document_id": str(doc.id), "limit_days": limit, "valid_until": valid.isoformat()})


def next_action_due(data):
    try:
        day = date.fromisoformat(data.get("next_action_date") or "")
    except ValueError:
        return None, None
    at = data.get("next_action_time") or ""
    if at:
        try:
            return None, datetime.combine(day, time.fromisoformat(at), ZONE)
        except ValueError:
            pass
    return day, None


def mirror_of(data):
    return {"title": data.get("next_action") or "", "date": data.get("next_action_date"), "time": data.get("next_action_time") or ""}


def resolution_reason(activity, last_contact):
    source = activity.details.get("source_type")
    if source in (Source.INACTIVE, Source.WAITING_REPLY) and last_contact and aware(last_contact) >= aware(activity.created_at):
        return "Retorno registrado" if source == Source.WAITING_REPLY else "Nova interação registrada"
    return {Source.HOT_NO_NEXT: "Próxima ação definida", Source.MISSING_REGISTRATION: "Ficha cadastral anexada ou etapa alterada",
            Source.DOCUMENT_EXPIRING: "Documento atualizado ou substituído", Source.NEXT_ACTION: "Próxima ação concluída ou removida no fornecedor",
            Source.WAITING_REPLY: "Fornecedor saiu de “Aguardando retorno”"}.get(source, "Condição deixou de existir")


# --------------------------------------------------------------------------------------------- consultas em lote

def automation_items(db, supplier_ids, organization_id, now):
    """Itens abertos + histórico recente (para não recriar episódios encerrados)."""
    query = select(Activity).where(is_automation(), or_(Activity.status.in_(OPEN), Activity.created_at >= now - timedelta(days=400)))
    if organization_id:
        query = query.where(Activity.organization_id == organization_id)
    if supplier_ids is not None:
        query = query.where(Activity.details["supplier_id"].as_string().in_(supplier_ids))
    return list(db.scalars(query.with_for_update()))


def linked_future_actions(db, supplier_ids, today):
    """Reuniões e tarefas abertas ligadas ao fornecedor que já representam a próxima ação."""
    if not supplier_ids:
        return set()
    start = datetime.combine(today, time.min, ZONE)
    rows = db.execute(select(Activity.details, Activity.due_date, Activity.due_at).where(
        Activity.details["supplier_id"].as_string().in_(supplier_ids), Activity.approval == "published",
        Activity.status.in_(OPEN), func.coalesce(Activity.details["automation"].as_boolean(), False).is_(False),
        or_(Activity.due_date >= today, Activity.due_at >= start)))
    return {details.get("supplier_id") for details, *_ in rows}


# --------------------------------------------------------------------------------------------- criação e ciclo de vida

def create_item(db, owner, spec, now):
    from app.services.planner_hub import container
    meeting, run = container(db, owner)
    rule = RULES[spec.source]
    # Mesmo episódio (mesma referência) → mesma chave: o índice único do banco barra duplicata concorrente.
    stamp = spec.document_key or (aware(spec.reference) or now).isoformat()
    local_id = f"auto:{rule.code}:{spec.supplier.id.hex}:{hashlib.sha1(stamp.encode()).hexdigest()[:12]}"
    activity = Activity(organization_id=spec.supplier.organization_id, meeting_id=meeting.id, analysis_run_id=run.id,
                        proposal_local_id=local_id, creator_id=owner.id, assignee_user_id=owner.id, kind="task",
                        title=spec.title, description=spec.description, approval="published", status="todo",
                        due_date=spec.due_date, due_at=spec.due_at, timezone="America/Sao_Paulo",
                        no_deadline_accepted=spec.no_deadline, details=details_for(spec))
    db.add(activity)
    db.flush()
    db.add(ActivityAudit(organization_id=activity.organization_id, activity_id=activity.id, meeting_id=meeting.id, actor_id=None,
                         action="auto_created", reason=f"Follow-up automático: {rule.category}", changes={"source_type": spec.source, "supplier_id": str(spec.supplier.id)}))
    sync_alerts(db, activity)
    return activity


def details_for(spec):
    rule = RULES[spec.source]
    return {"planner_kind": "followup", "automation": True, "source_type": spec.source, "category": rule.category,
            "origin": "automacao", "priority": rule.priority, "supplier_id": str(spec.supplier.id), "supplier_name": spec.supplier.name,
            "document_key": spec.document_key or None, "suggest_meeting": rule.suggest_meeting, **spec.extra}


def update_item(db, activity, spec):
    """Mantém o item aberto alinhado ao fornecedor (título, prazo, responsável). Retorna 1 se mudou."""
    owner = spec.supplier.responsible_user_id
    wanted = {"title": spec.title, "due_date": spec.due_date, "due_at": spec.due_at, "assignee_user_id": owner}
    if spec.source not in (Source.NEXT_ACTION, Source.DOCUMENT_EXPIRING):
        wanted.pop("due_date"); wanted.pop("due_at")  # alertas mantêm o prazo do dia em que nasceram
    if spec.source == Source.INACTIVE:
        wanted.pop("title")  # o título registra quantos dias havia no momento do alerta; não muda todo dia
    changed = {k: v for k, v in wanted.items() if (aware(getattr(activity, k)) if k == "due_at" else getattr(activity, k)) != (aware(v) if k == "due_at" else v)}
    details = {**activity.details, **details_for(spec)}
    if not changed and details == activity.details:
        return 0
    before = {k: str(getattr(activity, k)) for k in changed}
    for key, value in changed.items():
        setattr(activity, key, value)
    if spec.source == Source.NEXT_ACTION:
        activity.no_deadline_accepted = spec.no_deadline
    activity.details = details
    if {"due_date", "due_at", "assignee_user_id"} & changed.keys():
        activity.deadline_version += 1
    activity.version += 1
    if changed:
        db.add(ActivityAudit(organization_id=activity.organization_id, activity_id=activity.id, meeting_id=activity.meeting_id, actor_id=None,
                             action="auto_updated", reason="Atualizado a partir do fornecedor" + (" (novo responsável)" if "assignee_user_id" in changed else ""),
                             changes={"before": before, "after": {k: str(v) for k, v in changed.items()}}))
    sync_alerts(db, activity)
    return 1


def resolve(db, activity, status, reason, actor=None):
    activity.status = status
    activity.completed_at = datetime.now(timezone.utc) if status == "done" else None
    activity.details = {**activity.details, "resolution": reason}
    activity.version += 1
    db.add(ActivityAudit(organization_id=activity.organization_id, activity_id=activity.id, meeting_id=activity.meeting_id,
                         actor_id=actor.id if actor else None, action="auto_resolved", reason=reason, changes={"status": status}))
    sync_alerts(db, activity)


def ready(db):
    """O CRM funciona mesmo onde o módulo de reuniões/Planner ainda não foi migrado."""
    return inspect(db.connection()).has_table("activities")  # mesma conexão da transação em curso


def refresh_supplier(db, supplier):
    """Reavalia um fornecedor após uma ação na tela (interação, próxima ação, documento, etapa, responsável…)."""
    if not ready(db):
        return {}
    db.flush()
    return evaluate(db, supplier_ids=[supplier.id], organization_id=supplier.organization_id)


def close_for_deleted_supplier(db, supplier, actor):
    """Exclusão definitiva: itens abertos são cancelados (histórico preservado, sem FK com o fornecedor)."""
    if not ready(db):
        return 0
    rows = automation_items(db, [str(supplier.id)], supplier.organization_id, datetime.now(timezone.utc))
    count = 0
    for activity in rows:
        if activity.status in OPEN:
            resolve(db, activity, "cancelled", "Fornecedor excluído", actor)
            count += 1
    return count


def on_planner_item_closed(db, activity, actor):
    """Concluir a próxima ação no Planner conclui a próxima ação do fornecedor (se ainda for a mesma)."""
    details = activity.details or {}
    if details.get("source_type") != Source.NEXT_ACTION or activity.status not in ("done", "cancelled"):
        return
    from app.services import suppliers as supplier_service
    try:
        supplier_id = uuid.UUID(str(details.get("supplier_id")))
    except ValueError:
        return
    supplier = db.scalar(select(Supplier).where(Supplier.id == supplier_id, Supplier.organization_id == activity.organization_id).with_for_update())
    if supplier is None or mirror_of(supplier.data or {}) != details.get("mirror"):
        return
    supplier.data = {**supplier.data, "next_action": "", "next_action_date": None, "next_action_time": ""}
    supplier_service.audit(db, supplier, actor, "next_action_changed", {"next_action": "", "origin": "planner", "activity_id": str(activity.id)})
    supplier_service.touch(supplier)


# --------------------------------------------------------------------------------------------- leitura (Kanban, drawer, painel)

def upcoming(db, user, suppliers, now=None):
    """Próxima ação, próximo follow-up e próxima reunião de cada fornecedor (consultas agregadas)."""
    now = now or datetime.now(timezone.utc)
    today = local_today(now)
    ids = [str(s.id) for s in suppliers]
    result = {sid: {"next_action": None, "followup": None, "meeting": None, "card": None} for sid in ids}
    if not ids:
        return result
    planner = ready(db)
    for s in suppliers:
        data = s.data or {}
        if data.get("next_action"):
            result[str(s.id)]["next_action"] = {"title": data["next_action"], "date": data.get("next_action_date"), "time": data.get("next_action_time") or "",
                                                "overdue": bool(data.get("next_action_date") and data["next_action_date"] < today.isoformat())}
    for task in db.scalars(select(SupplierTask).where(SupplierTask.supplier_id.in_([s.id for s in suppliers]))):
        data = task.data or {}
        if data.get("status") != "pendente":
            continue
        entry = {"source": "supplier_task", "id": str(task.id), "title": data.get("title"), "date": data.get("due_date"), "time": "",
                 "overdue": bool(data.get("due_date") and data["due_date"] < today.isoformat())}
        keep_earliest(result[str(task.supplier_id)], "followup", entry)
    query = activity_query(user).where(Activity.details["supplier_id"].as_string().in_(ids), Activity.approval == "published", Activity.status.in_(OPEN))
    for a in (db.scalars(query) if planner else []):
        details = a.details or {}
        sid = details.get("supplier_id")
        if sid not in result:
            continue
        day = a.due_date or (aware(a.due_at).astimezone(ZoneInfo(a.timezone)).date() if a.due_at else None)
        entry = {"source": "activity", "id": str(a.id), "activity_id": str(a.id), "version": a.version, "title": a.title,
                 "date": day.isoformat() if day else None, "time": aware(a.due_at).astimezone(ZoneInfo(a.timezone)).strftime("%H:%M") if a.due_at else "",
                 "category": details.get("category"), "source_type": details.get("source_type"),
                 "overdue": bool(day and day < today)}
        if details.get("planner_kind") == "meeting":
            if day and day >= today:
                keep_earliest(result[sid], "meeting", {**entry, "meeting_id": str(a.meeting_id)})
        elif details.get("source_type") == Source.NEXT_ACTION:
            if result[sid]["next_action"]:
                result[sid]["next_action"].update(activity_id=str(a.id), version=a.version)
        else:
            keep_earliest(result[sid], "followup", entry)
    for sid, block in result.items():
        options = [(k, v) for k, v in (("next", block["next_action"]), ("followup", block["followup"]), ("meeting", block["meeting"])) if v]
        if options:
            kind, entry = min(options, key=lambda kv: (not kv[1].get("overdue"), kv[1].get("date") or "9999-99-99", kv[1].get("time") or ""))
            block["card"] = {"kind": kind, **entry}
    return result


def keep_earliest(block, slot, entry):
    current = block[slot]
    rank = lambda e: (e.get("date") or "9999-99-99", e.get("time") or "")
    if current is None or rank(entry) < rank(current):
        block[slot] = entry


def summary_counts(db, user):
    counts = {}
    for details in db.scalars(select(Activity.details).where(Activity.id.in_(
            activity_query(user).where(is_automation(), Activity.status.in_(OPEN)).with_only_columns(Activity.id)))):
        source = (details or {}).get("source_type")
        counts[source] = counts.get(source, 0) + 1
    return {"suppliers_inactive": counts.get(Source.INACTIVE, 0), "hot_no_next": counts.get(Source.HOT_NO_NEXT, 0),
            "filters": {"suppliers_inactive": Source.INACTIVE, "hot_no_next": Source.HOT_NO_NEXT}}  # filtro ?source= do Planner
