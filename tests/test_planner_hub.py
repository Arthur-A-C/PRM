"""Planner como centro operacional: criação direta, agenda unificada, fornecedor → Planner e permissões."""
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import get_db_session
from app.dependencies import get_current_auth
from app.main import app
from app.models import Organization, User
from app.models.meetings import MEETING_TABLES, Activity, ActivityAlert, Meeting, MeetingRun
from app.models.suppliers import Supplier, SupplierInteraction, SupplierTask
from app.routers.meetings import PlannerItemInput, ScheduleInput, meetings as list_meetings, meeting_detail, metadata, MetadataInput
from app.services import planner_hub
from app.services.meeting_pipeline import add_revision, analysis_context, build_cards, enqueue
from app.services.meeting_activities import publish, edit_activity
from app.services.security import hash_secret

TODAY = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
TEXT = '48:46 - Luis Gustavo\nVou enviar a proposta amanhã\n\n55:22 - Luiz Portwell\nBeleza.\n'


@pytest.fixture
def world():
    engine = create_engine('sqlite://', connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Organization.__table__.create(engine); User.__table__.create(engine)
    for table in MEETING_TABLES:
        table.create(engine)
    for model in (Supplier, SupplierTask, SupplierInteraction):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        org, other = Organization(name='Org'), Organization(name='Outra'); db.add_all([org, other]); db.flush()
        manager = User(organization_id=org.id, name='Gestora', email='g@example.test', password_hash='x', role='gestor', active=True)
        seller = User(organization_id=org.id, name='Vendedor', email='v@example.test', password_hash='x', role='vendedor', active=True)
        outsider = User(organization_id=other.id, name='Fora', email='f@example.test', password_hash='x', role='gestor', active=True)
        db.add_all([manager, seller, outsider]); db.flush()
        mine = Supplier(organization_id=org.id, responsible_user_id=manager.id, name='Atlas Automação', data={'next_action': 'Cobrar ficha', 'next_action_date': (TODAY - timedelta(days=2)).isoformat()})
        sellers = Supplier(organization_id=org.id, responsible_user_id=seller.id, name='Delta Válvulas', data={})
        db.add_all([mine, sellers]); db.commit()
        yield SimpleNamespace(db=db, org=org, manager=manager, seller=seller, outsider=outsider, supplier=mine, seller_supplier=sellers)
    engine.dispose()


def item(**values):
    return PlannerItemInput(**{'type': 'task', 'title': 'Enviar proposta revisada', **values})


def feed(w, user, days=31):
    return planner_hub.feed(w.db, user, TODAY - timedelta(days=1), TODAY + timedelta(days=days))['items']


def test_task_created_in_planner_is_published_with_alert_and_hidden_container(world):
    w = world
    result = planner_hub.create_item(w.db, w.manager, item(date=TODAY, assignee_user_id=w.seller.id, priority='alta')); w.db.commit()
    row = w.db.get(Activity, uuid.UUID(result['activity_id']))
    assert row.approval == 'published' and row.kind == 'task' and row.details['planner_kind'] == 'task' and row.details['priority'] == 'alta'
    container = w.db.get(Meeting, row.meeting_id)
    assert container.metadata_confirmed == {'planner_container': True}
    assert w.db.scalars(select(ActivityAlert).where(ActivityAlert.activity_id == row.id)).all()
    # Um segundo item reutiliza o mesmo registro de origem; ele nunca aparece como reunião.
    planner_hub.create_item(w.db, w.manager, item(title='Outra tarefa', date=TODAY)); w.db.commit()
    assert w.db.scalars(select(MeetingRun).where(MeetingRun.key == planner_hub.CONTAINER_KEY)).all().__len__() == 1
    assert list_meetings(SimpleNamespace(user=w.manager), w.db)['items'] == []
    entries = [i for i in feed(w, w.manager) if i['source'] == 'activity']
    assert {i['type'] for i in entries} == {'task'} and all(i['meeting_id'] is None for i in entries)
    with pytest.raises(HTTPException) as missing:
        planner_hub.create_item(w.db, w.manager, item(title='Sem prazo'))
    assert missing.value.status_code == 422


def test_card_goes_to_review_and_counts_as_pending(world):
    w = world
    result = planner_hub.create_item(w.db, w.manager, item(type='card', title='Avaliar novo sensor')); w.db.commit()
    row = w.db.get(Activity, uuid.UUID(result['activity_id']))
    assert row.approval == 'draft' and planner_hub.summary(w.db, w.manager)['cards_review'] == 1
    assert next(i for i in feed(w, w.manager) if i['id'] == str(row.id))['type'] == 'card'


def test_meeting_reuses_meeting_model_and_reschedule_updates_agenda(world):
    w = world
    result = planner_hub.create_item(w.db, w.manager, item(type='meeting', title='Alinhamento com Atlas', date=TODAY, time=datetime.strptime('14:30', '%H:%M').time(),
                                                           duration_minutes=45, participants=['Ana', 'joao@atlas.example'], location='https://meet.example/abc',
                                                           supplier_id=w.supplier.id, description='Levar amostras')); w.db.commit()
    meeting = w.db.get(Meeting, uuid.UUID(result['meeting_id']))
    event = w.db.get(Activity, uuid.UUID(result['activity_id']))
    assert meeting.partner == 'Atlas Automação' and meeting.meeting_date == TODAY
    assert meeting.metadata_confirmed['schedule']['participants'] == ['Ana', 'joao@atlas.example']
    assert event.kind == 'event' and event.approval == 'published' and event.meeting_id == meeting.id
    assert event.due_at.hour == 14 and event.end_at - event.due_at == timedelta(minutes=45)
    assert w.db.scalar(select(SupplierInteraction).where(SupplierInteraction.event == 'meeting_scheduled')).data['meeting_id'] == str(meeting.id)
    entry = next(i for i in feed(w, w.manager) if i['id'] == str(event.id))
    assert entry['type'] == 'meeting' and entry['open'] == 'meeting' and entry['supplier_name'] == 'Atlas Automação' and entry['meeting_id'] == str(meeting.id)
    detail = meeting_detail(meeting.id, SimpleNamespace(user=w.manager), w.db)
    assert detail['event_activity_id'] == str(event.id) and detail['metadata']['schedule']['location'] == 'https://meet.example/abc'
    assert [m['id'] for m in list_meetings(SimpleNamespace(user=w.manager), w.db)['items']] == [str(meeting.id)]
    # Reagendar: reunião e item da agenda mudam juntos; versão antiga é recusada.
    moved = ScheduleInput(version=meeting.version, title='Alinhamento remarcado', date=TODAY + timedelta(days=3), time=datetime.strptime('09:00', '%H:%M').time(),
                          duration_minutes=30, reason='Fornecedor pediu para remarcar')
    deadline_version = event.deadline_version
    planner_hub.reschedule(w.db, w.manager, meeting, moved); w.db.commit()
    assert meeting.meeting_date == TODAY + timedelta(days=3) and event.title == 'Alinhamento remarcado' and event.deadline_version == deadline_version + 1
    with pytest.raises(HTTPException) as stale:
        planner_hub.reschedule(w.db, w.manager, meeting, moved)
    assert stale.value.status_code == 409
    # Confirmar metadados da reunião (fluxo de IA) preserva o agendamento.
    metadata(meeting.id, MetadataInput(version=meeting.version, meeting_date=meeting.meeting_date, reason='Confirmação humana'), SimpleNamespace(user=w.manager), w.db)
    assert w.db.get(Meeting, meeting.id).metadata_confirmed['schedule']['time'] == '09:00'


def test_meeting_ai_cards_still_flow_and_appear_in_planner(world):
    w = world
    result = planner_hub.create_item(w.db, w.manager, item(type='meeting', title='Reunião com transcrição', date=TODAY)); w.db.commit()
    meeting = w.db.get(Meeting, uuid.UUID(result['meeting_id']))
    revision = add_revision(w.db, meeting, w.manager.id, TEXT)
    run = enqueue(w.db, meeting, 'analysis', analysis_context(meeting, revision, Settings(_env_file=None)), revision_id=revision.id)
    run.state, run.result = 'succeeded', {"schema_version": "2.0", "summary": "Proposta", "proposals": [{"local_id": "p1", "kind": "task", "commitment_type": "explicit",
        "title": "Enviar proposta", "description": "", "owner_participant_id": meeting.participants[0]["id"],
        "due": {"precision": "unknown", "origin": "not_stated", "needs_review": True}, "priority": None, "checklist": [], "depends_on_local_ids": [],
        "ambiguities": [], "evidence": [{"segment_id": revision.segments[0]["id"], "quote": "Vou enviar a proposta amanhã", "supports": ["action", "owner"]}]}],
        "decisions": [], "context_notes": [], "warnings": []}
    w.db.commit()
    card_id = uuid.UUID(build_cards(w.db, run)['ids'][0]); w.db.commit()
    card = w.db.get(Activity, card_id)
    assert card.approval == 'draft' and planner_hub.summary(w.db, w.manager)['cards_review'] == 1
    card.assignee_user_id, card.due_date, card.approval = w.manager.id, TODAY + timedelta(days=2), 'approved'; w.db.commit()
    publish(w.db, w.manager, [SimpleNamespace(id=card.id, version=card.version)]); w.db.commit()
    entry = next(i for i in feed(w, w.manager) if i['id'] == str(card.id))
    assert entry['type'] == 'card' and entry['approval'] == 'published' and entry['meeting_title'] == 'Reunião com transcrição'


def test_followups_and_next_action_from_supplier_appear(world):
    w = world
    result = planner_hub.create_item(w.db, w.manager, item(type='followup', title='Validar amostra', date=TODAY + timedelta(days=1), supplier_id=w.supplier.id)); w.db.commit()
    task = w.db.get(SupplierTask, uuid.UUID(result['task_id']))
    assert task.data['status'] == 'pendente' and task.data['origin'] == 'planner'
    items = {i['key']: i for i in feed(w, w.manager)}
    assert items[f'supplier-task:{task.id}']['type'] == 'followup'
    next_action = items[f'supplier-next:{w.supplier.id}']
    assert next_action['overdue'] and next_action['title'] == 'Cobrar ficha'
    assert planner_hub.summary(w.db, w.manager)['followups'] == 1  # vencido; o de amanhã ainda não conta
    with pytest.raises(HTTPException):
        planner_hub.create_item(w.db, w.manager, item(type='followup', title='Sem fornecedor'))


def test_permissions_scope_and_tenant_isolation(world):
    w = world
    with pytest.raises(HTTPException) as other_assignee:
        planner_hub.create_item(w.db, w.seller, item(date=TODAY, assignee_user_id=w.manager.id))
    assert other_assignee.value.status_code == 403
    with pytest.raises(HTTPException) as foreign_supplier:
        planner_hub.create_item(w.db, w.seller, item(type='meeting', date=TODAY, supplier_id=w.supplier.id))
    assert foreign_supplier.value.status_code == 404
    planner_hub.create_item(w.db, w.seller, item(type='meeting', title='Visita Delta', date=TODAY, supplier_id=w.seller_supplier.id)); w.db.commit()
    seller_view = feed(w, w.seller)
    assert {i['supplier_name'] for i in seller_view if i['supplier_name']} == {'Delta Válvulas'}  # não vê o fornecedor da gestora
    assert feed(w, w.outsider) == []


def test_priority_edit_and_api_requires_csrf(world):
    w = world
    result = planner_hub.create_item(w.db, w.manager, item(date=TODAY)); w.db.commit()
    row = w.db.get(Activity, uuid.UUID(result['activity_id']))
    from app.routers.meetings import EditInput
    edit_activity(w.db, w.manager, row, EditInput(version=row.version, reason='Reprioridade', priority='baixa')); w.db.commit()
    assert row.details['priority'] == 'baixa'
    auth = SimpleNamespace(user=w.manager, login_session=SimpleNamespace(csrf_hash=hash_secret('csrf-test')))
    app.dependency_overrides[get_db_session] = lambda: w.db
    app.dependency_overrides[get_current_auth] = lambda: auth
    try:
        with TestClient(app) as client:
            payload = {'type': 'task', 'title': 'Via API', 'date': TODAY.isoformat()}
            assert client.post('/api/v1/planner/items', json=payload).status_code == 403
            created = client.post('/api/v1/planner/items', json=payload, headers={'X-CSRF-Token': 'csrf-test'})
            assert created.status_code == 200, created.text
            assert client.post('/api/v1/planner/items', json={**payload, 'type': 'invalid'}, headers={'X-CSRF-Token': 'csrf-test'}).status_code == 422
            span = client.get(f'/api/v1/planner/feed?start={TODAY.isoformat()}&end={(TODAY + timedelta(days=200)).isoformat()}')
            assert span.status_code == 422
            data = client.get(f'/api/v1/planner/feed?start={TODAY.isoformat()}&end={(TODAY + timedelta(days=1)).isoformat()}').json()
            assert any(i['title'] == 'Via API' for i in data['items'])
            assert set(client.get('/api/v1/planner/summary').json()) >= {'meetings_today', 'overdue_tasks', 'cards_review', 'followups'}
    finally:
        app.dependency_overrides.clear()
