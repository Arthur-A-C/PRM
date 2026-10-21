import copy
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.config import Settings, get_settings
from app.db import get_db_session
from app.dependencies import get_current_auth
from app.models import Organization, User
from app.models.meetings import MEETING_TABLES, Meeting, TranscriptRevision, MeetingRun, Activity, ActivityAlert, ActivityAudit
from app.schemas.meetings import validate_extraction, Extraction, Due
from app.services.meeting_transcripts import parse_transcript, digest
from app.services.meeting_pipeline import add_revision, enqueue, analysis_context, build_cards
from app.services.meeting_fixture import read_ai_example, READ_AI_HASH
from app.services.meeting_worker import process_next
from app.services.meeting_activities import get_activity, get_meeting, publish, serialize, sync_alerts, export_cards
from app.services.meeting_deadlines import deadline, overview
from app.services.security import hash_secret
from app.routers.meetings import Selection
from app.routers.meetings import EditInput, calendar
from app.services.meeting_activities import edit_activity

TEXT = '48:46 - Luis Gustavo Borges Matias\nMas eu vou perguntar também para o nosso CTO aqui\n\n55:22 - Luiz Portwell\nBeleza.\n\n55:22 - Falante não identificado\nOk.\n'


def extraction(segments, participants):
    return {"schema_version": "2.0", "summary": "Consultar CTO", "proposals": [{"local_id": "cto", "kind": "task",
        "commitment_type": "explicit", "title": "Consultar o CTO", "description": "Verificar integração",
        "owner_participant_id": participants[0]["id"], "due": {"precision": "unknown", "origin": "not_stated", "needs_review": True},
        "priority": None, "checklist": [], "depends_on_local_ids": [], "ambiguities": ["Sem prazo"],
        "evidence": [{"segment_id": segments[0]["id"], "quote": "eu vou perguntar também para o nosso CTO", "supports": ["action", "owner"]}]}],
        "decisions": [], "context_notes": [], "warnings": []}


@pytest.fixture
def store():
    engine = create_engine('sqlite://', connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Organization.__table__.create(engine); User.__table__.create(engine)
    for table in MEETING_TABLES:
        table.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        org=Organization(name='Test'); other=Organization(name='Other'); db.add_all([org,other]);db.flush()
        owner=User(organization_id=org.id,name='Curador',email='curator@example.test',password_hash='unused',role='gestor',active=True)
        seller=User(organization_id=org.id,name='Executor',email='worker@example.test',password_hash='unused',role='vendedor',active=True)
        outsider=User(organization_id=other.id,name='Outro',email='other@example.test',password_hash='unused',role='gestor',active=True)
        db.add_all([owner,seller,outsider]);db.flush()
        meeting=Meeting(organization_id=org.id,creator_id=owner.id,title='Teste',version=1,participants=[],timezone='America/Sao_Paulo')
        db.add(meeting);db.flush();revision=add_revision(db,meeting,owner.id,TEXT)
        run=enqueue(db,meeting,'analysis',analysis_context(meeting,revision,Settings(_env_file=None)),revision_id=revision.id)
        run.result=extraction(revision.segments,meeting.participants);run.state='succeeded';db.commit()
        yield engine,db,owner,seller,outsider,meeting,revision,run
    engine.dispose()


@pytest.mark.parametrize('role',['desenvolvedor','gestor','vendedor'])
def test_assignment_all_roles_generates_private_alerts(store, role):
    from app.routers.meetings import assignment_batch, AssignmentBatch, alerts, users
    _,db,owner,recipient,outsider,_,_,run=store
    recipient.role=role;owner.role='desenvolvedor';db.commit()
    row=db.get(Activity,uuid.UUID(build_cards(db,run)['ids'][0]))
    row.approval='published';row.assignee_user_id=owner.id;row.due_date=date(2020,1,1);db.commit()
    auth=SimpleNamespace(user=owner)
    directory=users(auth,db)['items']
    assert next(u for u in directory if u['id']==str(recipient.id))['role']==role
    assert not any(u['id']==str(outsider.id) for u in directory)
    assignment_batch(AssignmentBatch(items=[Selection(id=row.id,version=row.version)],
        assignee_user_id=recipient.id,reason='Atribuir ao usuário real'),auth,db)
    received=alerts(SimpleNamespace(user=recipient),db)['items']
    assert {a['kind'] for a in received}=={'assigned','overdue'}
    assert alerts(auth,db)['items']==[]
    count=db.scalar(select(func.count()).select_from(ActivityAlert))
    sync_alerts(db,row);db.commit()
    assert db.scalar(select(func.count()).select_from(ActivityAlert))==count
    assert all(a['activity_id']==str(row.id) for a in received)


def test_deadline_alert_transition_reassign_finish_reopen(store):
    from app.routers.meetings import alerts
    _,db,owner,seller,_,_,_,run=store
    row=db.get(Activity,uuid.UUID(build_cards(db,run)['ids'][0]))
    row.approval='published';row.assignee_user_id=seller.id;row.due_date=date(2026,10,23);db.commit()
    def refresh(day):
        sync_alerts(db,row,datetime(2026,10,day,15,tzinfo=timezone.utc));db.commit()
        return {a.kind for a in db.scalars(select(ActivityAlert).where(ActivityAlert.resolved.is_(False)))}
    assert refresh(21)=={'assigned','soon'}
    assert refresh(23)=={'assigned','today'}
    assert refresh(24)=={'assigned','overdue'}
    size=db.scalar(select(func.count()).select_from(ActivityAlert))
    assert refresh(25)=={'assigned','overdue'}
    assert db.scalar(select(func.count()).select_from(ActivityAlert))==size
    edit_activity(db,owner,row,EditInput(version=row.version,assignee_user_id=owner.id,reason='Troca do responsável'));db.commit()
    assert alerts(SimpleNamespace(user=seller),db)['items']==[]
    row.status='done';assert refresh(25)==set()
    row.status='todo';assert refresh(25)=={'assigned','overdue'}
    owner.active=False;db.flush();assert refresh(25)==set()


def test_simulations_never_appear_or_notify_and_drafts_do_not_notify(store):
    from app.routers.meetings import alerts, activities
    _,db,owner,seller,_,_,_,run=store
    row=db.get(Activity,uuid.UUID(build_cards(db,run)['ids'][0]));row.assignee_user_id=seller.id
    sync_alerts(db,row);db.commit()
    assert db.scalar(select(func.count()).select_from(ActivityAlert))==0
    row.approval='published';row.due_date=date(2020,1,1);sync_alerts(db,row);db.commit()
    assert alerts(SimpleNamespace(user=seller),db)['items']
    row.details={**row.details,'simulation':True};db.commit()
    assert not alerts(SimpleNamespace(user=seller),db)['items']
    assert not activities(SimpleNamespace(user=owner),db)['items']
    with pytest.raises(HTTPException):get_activity(db,owner,row.id)
    sync_alerts(db,row);db.commit()
    assert all(a.resolved for a in db.scalars(select(ActivityAlert)))


def test_assignment_inactive_and_cross_organization_rejected(store):
    _,db,owner,seller,outsider,_,_,run=store
    row=db.get(Activity,uuid.UUID(build_cards(db,run)['ids'][0]));db.commit()
    seller.active=False;db.commit()
    for recipient in (seller,outsider):
        with pytest.raises(HTTPException) as error:
            edit_activity(db,owner,row,EditInput(version=row.version,assignee_user_id=recipient.id,reason='Inválida'))
        assert error.value.status_code==403
        db.rollback()
    assert row.assignee_user_id is None


def test_parser_unknown_distinct_and_duplicate_timestamps():
    segments, people=parse_transcript(TEXT,'rev')
    assert len(segments)==3 and len(people)==2
    assert segments[1]['timestamp']==segments[2]['timestamp']=='55:22'
    assert segments[1]['id']!=segments[2]['id'] and segments[2]['participant_id'] is None
    assert people[0]['name']!=people[1]['name']
    raw,unknown=parse_transcript('Sem timestamp\n\nOutra fala','plain')
    assert len(raw)==2 and not unknown and all(s['start_ms'] is None for s in raw)


@pytest.mark.parametrize('bad', ['owner','quote','cycle','extra','date','duplicate','dependency'])
def test_extraction_rejects_forged_and_inconsistent_data(bad):
    segments,people=parse_transcript(TEXT,'r');raw=extraction(segments,people);p=raw['proposals'][0]
    if bad=='owner': p['owner_participant_id']='invented'
    if bad=='quote': p['evidence'][0]['quote']='Uma citação inventada'
    if bad=='cycle': p['depends_on_local_ids']=['cto']
    if bad=='extra': p['assignee_user_id']='forged'
    if bad=='date': p['due'].update(date='2026-09-24',precision='partial')
    if bad=='duplicate': raw['proposals'].append(copy.deepcopy(p))
    if bad=='dependency': p['depends_on_local_ids']=['nonexistent']
    with pytest.raises(ValueError):validate_extraction(raw,segments,people)


def test_real_read_ai_fixture_if_available():
    path=Path('C:/Users/PW/Downloads/Transcrição READ AI.txt')
    if not path.exists():pytest.skip('Fixture privada não distribuída; informe caminho no ambiente de homologação')
    raw=path.read_bytes();assert digest(raw)==READ_AI_HASH
    segments,people=parse_transcript(raw.decode('utf-8-sig'),'fixture')
    assert len(segments)==111 and sum(s['participant_id'] is None for s in segments)==18
    assert {p['name'] for p in people}=={'Luiz Portwell','Luis Gustavo Borges Matias'}
    assert len({s['id'] for s in segments if s['timestamp']=='55:22'})==2
    result=validate_extraction(read_ai_example(segments),segments,people)
    assert len(result.proposals)==7
    event=next(p for p in result.proposals if p.kind=='event')
    assert event.due.date is None and event.time_candidate=='15:00'
    cto=next(p for p in result.proposals if p.local_id=='cto')
    assert next(p for p in people if p['id']==cto.owner_participant_id)['name']=='Luis Gustavo Borges Matias'
    assert next(p for p in result.proposals if p.local_id=='api').commitment_type=='offer'
    assert not any(p.due.date or p.due.datetime for p in result.proposals)


def test_generator_idempotent_immutable_revision_and_permissions(store):
    _,db,owner,seller,outsider,meeting,revision,run=store
    first=build_cards(db,run);db.commit();row=db.get(Activity,uuid.UUID(first['ids'][0]));row.title='Edição humana';db.commit()
    again=build_cards(db,run);db.commit();assert again['created']==0 and again['already_exists']==1
    assert db.get(Activity,row.id).title=='Edição humana'
    assert row.due_date is None and row.assignee_user_id is None
    for user in [seller,outsider]:
        with pytest.raises(HTTPException):get_activity(db,user,row.id)
    row.assignee_user_id=seller.id;db.commit();assert get_activity(db,seller,row.id)
    with pytest.raises(HTTPException):get_meeting(db,seller,meeting.id)
    assert 'evidence' not in serialize(row)['details']['original']
    assert serialize(row,include_evidence=True)['details']['original']['evidence']
    add_revision(db,meeting,owner.id,'Texto corrigido','manual');db.commit()
    assert db.get(TranscriptRevision,revision.id).original==TEXT


def test_publish_idempotent_alerts_and_transaction_validation(store):
    _,db,owner,seller,_,meeting,revision,run=store
    first=build_cards(db,run);db.commit();row=db.get(Activity,uuid.UUID(first['ids'][0]))
    with pytest.raises(HTTPException):publish(db,owner,[Selection(id=row.id,version=row.version)])
    row.assignee_user_id=seller.id;row.approval='approved';row.no_deadline_accepted=True;db.commit()
    selection=Selection(id=row.id,version=row.version)
    publish(db,owner,[selection]);db.commit();publish(db,owner,[selection]);db.commit()
    assert db.scalar(select(func.count()).select_from(Activity))==1
    assert db.scalar(select(func.count()).select_from(ActivityAlert))==2
    sync_alerts(db,row);db.commit();assert db.scalar(select(func.count()).select_from(ActivityAlert))==2
    row.status='done';sync_alerts(db,row);db.commit()
    assert all(a.resolved for a in db.scalars(select(ActivityAlert)))


@pytest.mark.parametrize('days,expected',[(8,'on_time'),(7,'attention'),(3,'attention'),(2,'prioritize'),(0,'prioritize'),(-1,'overdue')])
def test_deadline_bands(days,expected):
    now=datetime(2026,10,16,14,tzinfo=timezone.utc)
    a=SimpleNamespace(approval='published',status='todo',kind='task',timezone='America/Sao_Paulo',due_date=date(2026,10,16)+timedelta(days=days),due_at=None,no_deadline_accepted=False)
    assert deadline(a,now)['band']==expected
    result=overview([a],now);assert result['denominator']==1 and sum(v['count'] for v in result['bands'].values())==1


def test_deadline_instant_boundary_and_denominators():
    now=datetime(2026,10,16,14,tzinfo=timezone.utc)
    a=SimpleNamespace(approval='published',status='todo',kind='task',timezone='America/Sao_Paulo',due_date=None,due_at=now,no_deadline_accepted=False)
    assert deadline(a,now)['bucket']=='hoje'
    assert deadline(a,now+timedelta(microseconds=1))['bucket']=='venceu hoje'
    a.due_at=None;a.no_deadline_accepted=True
    assert overview([a],now)['denominator']==0 and overview([a],now)['no_deadline']==1
    a.approval='draft';assert overview([a],now)['no_deadline']==0


def test_worker_pipeline_does_not_repeat_api_for_card_retry(store):
    engine,db,owner,_,_,meeting,revision,run=store
    run.state='queued';db.commit();calls=[]
    def provider(context,segments,settings):
        calls.append(True);return extraction(segments,context['participants']),{'input_tokens':123,'output_tokens':50}
    settings=Settings(_env_file=None)
    assert process_next(engine,settings,'analysis',extractor=provider)
    assert process_next(engine,settings,'cards')
    assert not process_next(engine,settings,'analysis',extractor=provider)
    assert len(calls)==1
    db.expire_all();assert db.scalar(select(func.count()).select_from(Activity))==1


def test_csv_neutralizes_formulas_and_export_excludes_evidence(store):
    _,db,_,_,_,_,_,run=store
    first=build_cards(db,run);row=db.get(Activity,uuid.UUID(first['ids'][0]));row.title='=HYPERLINK("bad")';db.flush()
    output=export_cards([row],'csv');assert output.startswith(b'\xef\xbb\xbf') and "'=HYPERLINK" in output.decode('utf-8-sig')
    result=json.loads(export_cards([row],'json'));assert result['count']==1
    assert 'evidence' not in result['cards'][0]['details']['original']


def test_unchanged_deadline_does_not_create_new_alert_generation(store):
    _,db,owner,seller,_,_,_,run=store
    identifier=build_cards(db,run)['ids'][0];db.commit()
    row=db.get(Activity,uuid.UUID(identifier));row.assignee_user_id=seller.id
    row.approval='published';row.no_deadline_accepted=True;db.commit()
    sync_alerts(db,row);db.commit();generation=row.deadline_version
    edit_activity(db,owner,row,EditInput(version=row.version,reason='Ajuste de título',title='Novo título',
        due_date=None,due_at=None,assignee_user_id=seller.id,timezone=row.timezone))
    db.commit()
    assert row.deadline_version==generation
    assert db.scalar(select(func.count()).select_from(ActivityAlert))==2


def test_calendar_draft_layer_and_exclusive_midnight(store):
    _,db,owner,_,_,_,_,run=store
    identifier=build_cards(db,run)['ids'][0];db.commit()
    row=db.get(Activity,uuid.UUID(identifier));row.kind='event'
    row.due_at=datetime(2026,9,24,18,tzinfo=timezone.utc)
    row.end_at=datetime(2026,9,25,3,tzinfo=timezone.utc);db.commit()
    auth=SimpleNamespace(user=owner)
    assert calendar(date(2026,9,1),date(2026,10,1),auth,db)['items']==[]
    result=calendar(date(2026,9,1),date(2026,10,1),auth,db,include_proposals=True)
    assert result['items'][0]['calendar_end']=='2026-09-24'
    assert result['items'][0]['approval']=='draft'


def test_api_csrf_tenant_assignment_and_edit_conflicts(store):
    _,db,owner,seller,outsider,_,_,run=store
    row_id=build_cards(db,run)['ids'][0];db.commit()
    auth=SimpleNamespace(user=owner,login_session=SimpleNamespace(csrf_hash=hash_secret('csrf-test')))
    app.dependency_overrides[get_db_session]=lambda: db
    app.dependency_overrides[get_current_auth]=lambda: auth
    try:
        with TestClient(app) as client:
            assert client.get('/api/v1/planner/activities').status_code==200
            assert client.patch('/api/v1/planner/activities/'+row_id,json={'version':1,'reason':'Teste','status':'done'}).status_code==403
            headers={'X-CSRF-Token':'csrf-test'}
            result=client.patch('/api/v1/planner/activities/'+row_id,headers=headers,json={'version':1,'reason':'Teste atribuição','assignee_user_id':str(seller.id)})
            assert result.status_code==200,result.text
            assert client.patch('/api/v1/planner/activities/'+row_id,headers=headers,json={'version':1,'reason':'Conflito','status':'done'}).status_code==409
            auth.user=outsider
            assert client.get('/api/v1/planner/activities/'+row_id).status_code==404
            assert client.get('/api/v1/planner/activities/overview').json()['denominator']==0
            auth.user=seller
            assert client.get('/api/v1/planner/activities/'+row_id).json()['evidence_access'] is False
            assert client.patch('/api/v1/planner/activities/'+row_id,headers=headers,json={'version':2,'reason':'Tentativa indevida','assignee_user_id':str(owner.id)}).status_code==403
    finally:
        app.dependency_overrides.clear()


def test_batch_assignment_rolls_back_on_invalid_selection(store):
    from app.routers.meetings import assignment_batch, AssignmentBatch
    _,db,owner,seller,_,_,_,run=store
    identifier=uuid.UUID(build_cards(db,run)['ids'][0]);db.commit()
    row=db.get(Activity,identifier);version=row.version
    with pytest.raises(HTTPException):
        assignment_batch(AssignmentBatch(items=[Selection(id=identifier,version=version),
            Selection(id=uuid.UUID('ffffffff-ffff-ffff-ffff-ffffffffffff'),version=1)],
            assignee_user_id=seller.id,reason='Teste de atomicidade'),SimpleNamespace(user=owner),db)
    db.expire_all()
    assert db.get(Activity,identifier).assignee_user_id is None
    assignment_batch(AssignmentBatch(items=[Selection(id=identifier,version=version)],
        assignee_user_id=seller.id,reason='Atribuição autorizada'),SimpleNamespace(user=owner),db)
    assert db.get(Activity,identifier).assignee_user_id == seller.id


def test_batch_review_atomic_and_versioned(store):
    from app.routers.meetings import ReviewBatch, review_batch
    _,db,owner,seller,_,_,_,run=store
    first=uuid.UUID(build_cards(db,run)['ids'][0]);db.commit()
    row=db.get(Activity,first);row.assignee_user_id=seller.id;db.commit()
    version=row.version
    with pytest.raises(HTTPException):
        review_batch(ReviewBatch(items=[Selection(id=first,version=version),
            Selection(id=uuid.UUID('ffffffff-ffff-ffff-ffff-ffffffffffff'),version=1)],
            decision='approved',reason='Revisão em lote'),SimpleNamespace(user=owner),db)
    db.expire_all();assert db.get(Activity,first).approval=='draft'
    result=review_batch(ReviewBatch(items=[Selection(id=first,version=version)],
        decision='approved',reason='Revisão concluída'),SimpleNamespace(user=owner),db)
    assert result['items'][0]['approval']=='approved'
    assert result['items'][0]['version']==version+1
    with pytest.raises(HTTPException) as error:
        review_batch(ReviewBatch(items=[Selection(id=first,version=version)],
            decision='rejected',reason='Versão antiga'),SimpleNamespace(user=owner),db)
    assert error.value.status_code==409
    assert db.get(Activity,first).approval=='approved'


def test_comments_idempotent_scoped_without_activity_changes(store):
    from app.routers.meetings import CommentInput, comment
    _,db,owner,seller,outsider,_,_,run=store
    identifier=uuid.UUID(build_cards(db,run)['ids'][0]);db.commit()
    row=db.get(Activity,identifier);row.assignee_user_id=seller.id;db.commit()
    before=(row.version,row.deadline_version,row.approval,row.status)
    payload=CommentInput(request_id=uuid.uuid4(),text='<script>texto não executável</script>')
    result=comment(identifier,payload,SimpleNamespace(user=seller),db)
    repeat=comment(identifier,payload,SimpleNamespace(user=seller),db)
    assert result['created'] and not repeat['created'] and result['id']==repeat['id']
    assert (row.version,row.deadline_version,row.approval,row.status)==before
    assert db.scalar(select(func.count()).select_from(ActivityAudit).where(ActivityAudit.action=='comment'))==1
    with pytest.raises(HTTPException) as error:
        comment(identifier,payload,SimpleNamespace(user=outsider),db)
    assert error.value.status_code==404
    with pytest.raises(HTTPException) as error:
        comment(identifier,CommentInput(request_id=payload.request_id,text='Outro texto'),SimpleNamespace(user=seller),db)
    assert error.value.status_code==409


def test_demo_is_private_and_does_not_require_meeting_migration(store,tmp_path):
    from app.routers.meeting_demo import demo
    from fastapi import Response
    _,db,owner,seller,outsider,_,_,_=store
    settings=Settings(_env_file=None,meeting_storage_dir=str(tmp_path))
    (tmp_path/'read-ai-dashboard-demo.json').write_text(json.dumps({'organization_id':str(owner.organization_id),
        'simulation':True,'cards':[{'title':'Demonstração'}]}),encoding='utf-8')
    response=Response()
    output=demo(SimpleNamespace(user=owner),settings,response)
    assert output['available'] and 'organization_id' not in output
    assert response.headers['Cache-Control']=='private, no-store'
    assert demo(SimpleNamespace(user=outsider),settings,Response())=={'available':False}
    with pytest.raises(HTTPException):demo(SimpleNamespace(user=seller),settings,Response())
    assert db.scalar(select(func.count()).select_from(Activity))==0


def test_demo_real_transcript_contract():
    from app.services.meeting_demo import build_demo
    path=Path('C:/Users/PW/Downloads/Transcrição READ AI.txt')
    if not path.exists():pytest.skip('Fixture privada não disponível')
    result=build_demo(path.read_bytes(),uuid.uuid4())
    assert result['segment_count']==111 and len(result['cards'])==7
    assert all(card['simulation'] and card['assignee_user_id'] is None for card in result['cards'])
    assert [card['confirmed_date'] for card in result['cards'] if card['kind']=='event']==['2026-09-24']
    with pytest.raises(ValueError):build_demo(b'Transcricao diferente',uuid.uuid4())
