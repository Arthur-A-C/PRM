"""Follow-up automático de fornecedores: regras, idempotência, resolução, responsável, isolamento e Planner."""
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import get_db_session
from app.dependencies import get_current_auth, require_module_access
from app.models import Organization, User
from app.models.meetings import MEETING_TABLES, Activity, ActivityAlert, ActivityAudit
from app.models.suppliers import AI_MODELS, AUDIT_MODELS, MODELS, Supplier, SupplierDocument, SupplierInteraction, SupplierTask
from app.routers import meetings as planner_routes, suppliers as supplier_routes
from app.services import planner_hub
from app.services.security import hash_secret
from app.services.supplier_followups import OPEN, RULES, Source, business_day, evaluate, upcoming

NOW = datetime.now(timezone.utc)
TODAY = NOW.astimezone(ZoneInfo("America/Sao_Paulo")).date()
SETTINGS = Settings(_env_file=None)
H = {"X-CSRF-Token": "csrf"}


@pytest.fixture
def w(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Organization.__table__.create(engine); User.__table__.create(engine)
    for table in MEETING_TABLES:
        table.create(engine)
    for model in (*MODELS, *AI_MODELS, *AUDIT_MODELS):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        org, other = Organization(name="Org"), Organization(name="Outra"); db.add_all([org, other]); db.flush()
        ana = User(organization_id=org.id, name="Ana", email="a@x.test", password_hash="x", role="gestor", active=True)
        bruno = User(organization_id=org.id, name="Bruno", email="b@x.test", password_hash="x", role="vendedor", active=True)
        zed = User(organization_id=other.id, name="Zed", email="z@x.test", password_hash="x", role="gestor", active=True)
        db.add_all([ana, bruno, zed]); db.commit()
        ns = SimpleNamespace(db=db, org=org, other=other, ana=ana, bruno=bruno, zed=zed, tmp=tmp_path)
        yield ns
    engine.dispose()


def supplier(w, name="Portwell", owner=None, days_old=10, stage="contato_inicial", score="morno", org=None, **data):
    s = Supplier(organization_id=(org or w.org).id, responsible_user_id=(owner or w.ana).id, name=name, stage=stage, score=score,
                 data=data, created_at=NOW - timedelta(days=days_old))
    w.db.add(s); w.db.commit()
    return s


def interaction(w, s, days_ago, event="interaction_created"):
    w.db.add(SupplierInteraction(supplier_id=s.id, organization_id=s.organization_id, actor_id=s.responsible_user_id, event=event,
                                 data={}, created_at=NOW - timedelta(days=days_ago)))
    w.db.commit()


def items(w, source=None, open_only=True):
    rows = w.db.scalars(select(Activity)).all()
    return [a for a in rows if a.details.get("automation") and (source is None or a.details["source_type"] == source)
            and (not open_only or a.status in OPEN)]


def run(w, now=NOW):
    stats = evaluate(w.db, now=now, settings=SETTINGS); w.db.commit()
    return stats


def client(w, user):
    app = FastAPI()
    app.include_router(supplier_routes.router, dependencies=[Depends(require_module_access)])
    app.include_router(planner_routes.router)
    state = SimpleNamespace(user=user)
    app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(user=state.user, login_session=SimpleNamespace(csrf_hash=hash_secret("csrf")))
    app.dependency_overrides[get_db_session] = lambda: w.db
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, supplier_storage_dir=str(w.tmp / "docs"))
    return TestClient(app), state


def test_inactive_alert_is_idempotent_and_resolved_by_new_interaction(w):
    s = supplier(w)
    interaction(w, s, 4)
    run(w); run(w); run(w)  # 1 + 2: repetir não duplica
    [alert] = items(w, Source.INACTIVE)
    assert "Portwell está há 4 dias sem interação" in alert.title and alert.assignee_user_id == w.ana.id
    assert alert.due_date == business_day(TODAY) and alert.approval == "published"
    assert alert.details["category"] == RULES[Source.INACTIVE].category
    alerts = w.db.scalars(select(ActivityAlert).where(ActivityAlert.activity_id == alert.id, ActivityAlert.resolved.is_(False))).all()
    assert len(alerts) == 1 and alerts[0].recipient_id == w.ana.id  # um único alerta em Meus alertas
    # 3: nova interação pela API resolve na hora, sem esperar o worker; histórico preservado.
    api, _ = client(w, w.ana)
    assert api.post(f"/api/v1/fornecedores/{s.id}/interactions", json={"summary": "Ligação feita"}).status_code == 403  # 13: CSRF
    assert api.post(f"/api/v1/fornecedores/{s.id}/interactions", headers=H, json={"summary": "Ligação feita"}).status_code == 200
    assert items(w, Source.INACTIVE) == []
    closed = w.db.get(Activity, alert.id)
    assert closed.status == "done" and closed.details["resolution"] == "Nova interação registrada"
    assert w.db.scalar(select(ActivityAudit).where(ActivityAudit.activity_id == alert.id, ActivityAudit.action == "auto_resolved"))
    assert not w.db.scalars(select(ActivityAlert).where(ActivityAlert.activity_id == alert.id, ActivityAlert.resolved.is_(False))).all()
    run(w)
    assert items(w, Source.INACTIVE) == []  # o mesmo episódio não volta


def test_hot_without_next_action_and_next_action_resolves(w):
    s = supplier(w, "Atlas", score="quente")
    interaction(w, s, 0)
    run(w); run(w)
    [hot] = items(w, Source.HOT_NO_NEXT)
    assert hot.details["priority"] == "alta" and hot.details["suggest_meeting"] is True
    api, _ = client(w, w.ana)
    later = (TODAY + timedelta(days=2)).isoformat()
    response = api.patch(f"/api/v1/fornecedores/{s.id}", headers=H, json={"next_action": "Cobrar proposta", "next_action_date": later, "next_action_time": "10:00"})
    assert response.status_code == 200, response.text
    assert items(w, Source.HOT_NO_NEXT) == []
    # 6 (próxima ação → Planner): um único item, atualizado ao mudar e resolvido ao concluir.
    [mirror] = items(w, Source.NEXT_ACTION)
    assert mirror.title == "Cobrar proposta" and mirror.due_at is not None and mirror.due_at.hour == 10
    api.patch(f"/api/v1/fornecedores/{s.id}", headers=H, json={"next_action": "Cobrar proposta revisada", "next_action_date": later})
    run(w)
    [same] = items(w, Source.NEXT_ACTION)
    assert same.id == mirror.id and same.title == "Cobrar proposta revisada"
    api.patch(f"/api/v1/fornecedores/{s.id}", headers=H, json={"next_action": "", "next_action_date": None})
    assert items(w, Source.NEXT_ACTION) == [] and w.db.get(Activity, mirror.id).status == "done"
    assert len(items(w, Source.NEXT_ACTION, open_only=False)) == 1
    w.db.get(Activity, hot.id).created_at = NOW - timedelta(minutes=5); w.db.commit()  # SQLite grava o horário em segundos
    run(w)
    assert len(items(w, Source.HOT_NO_NEXT)) == 1  # sem próxima ação de novo: novo episódio


def test_waiting_reply_creates_single_followup_and_reply_completes(w):
    s = supplier(w, "Delta", stage="aguardando", owner=w.bruno)
    interaction(w, s, 6)
    run(w); run(w)
    [follow] = items(w, Source.WAITING_REPLY)
    assert follow.title == "Cobrar retorno — Delta" and follow.assignee_user_id == w.bruno.id and follow.details["planner_kind"] == "followup"
    # 15/16: Planner recebe o item como Follow-up, vinculado ao fornecedor, e os filtros o encontram.
    feed = planner_hub.feed(w.db, w.bruno, TODAY, TODAY + timedelta(days=7))["items"]
    entry = next(i for i in feed if i["activity_id"] == str(follow.id))
    assert entry["type"] == "followup" and entry["supplier_id"] == str(s.id) and entry["source_type"] == Source.WAITING_REPLY
    assert entry["assignee_user_id"] == str(w.bruno.id) and entry["category"] == "Follow-up"
    assert planner_hub.summary(w.db, w.bruno)["suppliers_inactive"] == 1
    interaction(w, s, -0.01)  # retorno registrado depois da cobrança
    run(w)
    done = w.db.get(Activity, follow.id)
    assert done.status == "done" and done.details["resolution"] == "Retorno registrado"


def test_archived_and_dormant_are_ignored_and_open_items_closed_on_archive(w):
    s = supplier(w, "Arquivada")
    interaction(w, s, 9)
    frozen = supplier(w, "Congelada", stage="congelado")
    run(w)
    assert [a.details["supplier_name"] for a in items(w, Source.INACTIVE)] == ["Arquivada"]
    s.archived_at = NOW; w.db.commit()
    run(w)
    assert items(w) == [] and w.db.scalars(select(Activity)).all()  # cancelados, não apagados
    assert all(a.status == "cancelled" for a in items(w, open_only=False))
    assert frozen.id  # congelado nunca gerou cobrança


def test_responsible_change_moves_open_followups(w):
    s = supplier(w, "Kemper", stage="aguardando")
    interaction(w, s, 7)
    run(w)
    api, _ = client(w, w.ana)
    assert api.patch(f"/api/v1/fornecedores/{s.id}", headers=H, json={"responsible_user_id": str(w.bruno.id)}).status_code == 200
    assert {a.assignee_user_id for a in items(w)} == {w.bruno.id}
    assert w.db.scalars(select(ActivityAlert).where(ActivityAlert.recipient_id == w.bruno.id, ActivityAlert.resolved.is_(False))).all()
    assert not w.db.scalars(select(ActivityAlert).where(ActivityAlert.recipient_id == w.ana.id, ActivityAlert.resolved.is_(False))).all()


def test_registration_rule_waits_grace_and_resolves_with_document(w):
    fresh = supplier(w, "Nova", stage="documentacao", days_old=0)
    old = supplier(w, "Antiga", stage="documentacao", days_old=10)
    interaction(w, fresh, 0); interaction(w, old, 0)
    run(w)
    assert [a.details["supplier_name"] for a in items(w, Source.MISSING_REGISTRATION)] == ["Antiga"]
    w.db.add(SupplierDocument(supplier_id=old.id, organization_id=old.organization_id, actor_id=w.ana.id, data={"category": "Ficha cadastral", "status": "Vigente"}))
    w.db.commit(); run(w)
    assert items(w, Source.MISSING_REGISTRATION) == []


def test_document_expiry_thresholds_once_each(w):
    s = supplier(w, "Certificada")
    interaction(w, s, 0)
    doc = SupplierDocument(supplier_id=s.id, organization_id=s.organization_id, actor_id=w.ana.id,
                           data={"category": "Certidões", "description": "Certidão", "status": "Vigente", "valid_until": (TODAY + timedelta(days=20)).isoformat()})
    w.db.add(doc); w.db.commit()
    run(w); run(w)
    [first] = items(w, Source.DOCUMENT_EXPIRING)
    assert first.details["limit_days"] == 30 and "vence em 20 dias" in first.title
    doc.data = {**doc.data, "valid_until": (TODAY + timedelta(days=5)).isoformat()}; w.db.commit()
    run(w)
    [second] = items(w, Source.DOCUMENT_EXPIRING)
    assert second.details["limit_days"] == 7 and w.db.get(Activity, first.id).status == "done"
    doc.data = {**doc.data, "status": "Substituído"}; w.db.commit(); run(w)
    assert items(w, Source.DOCUMENT_EXPIRING) == []


def test_organization_isolation_and_planner_scope(w):
    mine = supplier(w, "Minha"); interaction(w, mine, 5)
    theirs = supplier(w, "Deles", owner=w.zed, org=w.other); interaction(w, theirs, 5)
    run(w)
    by_org = {a.organization_id for a in items(w)}
    assert by_org == {w.org.id, w.other.id}
    feed = planner_hub.feed(w.db, w.ana, TODAY, TODAY + timedelta(days=3))["items"]
    assert {i["supplier_name"] for i in feed if i.get("source_type")} == {"Minha"}
    alerts = planner_routes.alerts(SimpleNamespace(user=w.zed), w.db)["items"]
    assert [a["supplier_name"] for a in alerts] == ["Deles"] and alerts[0]["category"] == "Sem interação"
    # Vendedor não abre item de outra organização nem de outro responsável.
    api, state = client(w, w.zed)
    other_item = next(a for a in items(w) if a.organization_id == w.org.id)
    assert api.get(f"/api/v1/planner/activities/{other_item.id}").status_code == 404


def test_delete_still_works_and_closes_open_items(w):
    s = supplier(w, "Excluir"); interaction(w, s, 8)
    run(w)
    [alert] = items(w, Source.INACTIVE)
    api, _ = client(w, w.ana)
    w.db.refresh(s)
    response = api.request("DELETE", f"/api/v1/fornecedores/{s.id}", headers=H,
                           json={"expected_updated_at": s.updated_at.isoformat(), "confirm_name": "Excluir"})
    assert response.status_code == 200, response.text
    kept = w.db.get(Activity, alert.id)
    assert kept.status == "cancelled" and kept.details["resolution"] == "Fornecedor excluído"
    run(w)
    assert items(w) == []


def test_planner_completion_of_next_action_clears_supplier_and_kanban_upcoming(w):
    s = supplier(w, "Vortex", next_action="Enviar amostra", next_action_date=TODAY.isoformat())
    interaction(w, s, 0)
    run(w)
    [mirror] = items(w, Source.NEXT_ACTION)
    block = upcoming(w.db, w.ana, [s])[str(s.id)]
    assert block["card"]["kind"] == "next" and block["next_action"]["activity_id"] == str(mirror.id)
    api, _ = client(w, w.ana)
    response = api.patch(f"/api/v1/planner/activities/{mirror.id}", headers=H, json={"version": mirror.version, "reason": "Feito", "status": "done"})
    assert response.status_code == 200, response.text
    assert w.db.get(Supplier, s.id).data["next_action"] == ""
    run(w)
    assert items(w, Source.NEXT_ACTION) == []
