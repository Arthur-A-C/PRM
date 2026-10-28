from types import SimpleNamespace
import uuid
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.config import Settings,get_settings
from app.db import get_db_session
from app.dependencies import get_current_auth, require_module_access
from app.models.suppliers import (AI_MODELS, AUDIT_MODELS, MODELS, Supplier, SupplierAIRun,
                                  SupplierContact, SupplierDeletionAudit, SupplierDocument,
                                  SupplierInteraction, SupplierTask)
from app.routers import suppliers as routes
from app.services.security import hash_secret
from test_store_removal_production import people

H={'X-CSRF-Token':'csrf'}
@pytest.fixture
def setup(people,tmp_path):
    for model in MODELS:model.__table__.create(people.engine)
    for model in (*AI_MODELS,*AUDIT_MODELS):model.__table__.create(people.engine)
    app=FastAPI();app.include_router(routes.router,dependencies=[Depends(require_module_access)])
    state=SimpleNamespace(user=people.users['vera'])
    app.dependency_overrides[get_current_auth]=lambda:SimpleNamespace(user=state.user,login_session=SimpleNamespace(csrf_hash=hash_secret('csrf')))
    def db():
        with people.session() as session:yield session
    app.dependency_overrides[get_db_session]=db
    app.dependency_overrides[get_settings]=lambda:Settings(_env_file=None,supplier_storage_dir=str(tmp_path/'docs'))
    with TestClient(app) as client:yield SimpleNamespace(client=client,state=state,people=people,tmp=tmp_path)

def create(s,**values):
    r=s.client.post('/api/v1/fornecedores',headers=H,json={'name':'Fornecedor 001','cnpj':'00.001.002/0001-03',**values})
    assert r.status_code==200,r.text
    return r.json()

def update(s,item,**values):
    return s.client.put('/api/v1/fornecedores/'+item['id'],headers=H,json={**item['data'],'name':item['name'],
        'stage':item['stage'],'score':item['score'],'responsible_user_id':item['responsible_user_id'],**values})

def test_owner_create_edit_stage_score_next_action_history_filters(setup):
    s=setup;item=create(s);assert item['responsible_user_id']==str(s.state.user.id)
    r=update(s,item,stage='negociacao',score='quente',next_action='Cobrar contrato',next_action_date='2026-10-30',city='São Paulo')
    assert r.status_code==200,r.text
    got=s.client.get('/api/v1/fornecedores/'+item['id']).json()
    assert got['data']['cnpj']=='00.001.002/0001-03'
    assert {'supplier_created','stage_changed','score_changed','next_action_changed'}<={x['event'] for x in got['history']}
    rows=s.client.get('/api/v1/fornecedores?stage=negociacao&score=quente&city=Paulo&q=001').json()
    assert rows['columns']['negociacao']==[item['id']]
    assert not s.client.get('/api/v1/fornecedores?q=missing').json()['items']

def test_owner_contacts_interactions_tasks_documents(setup):
    s=setup;item=create(s,primary_contact='Inicial');url='/api/v1/fornecedores/'+item['id']
    c=s.client.post(url+'/contacts',headers=H,json={'name':'Comercial','is_primary':True});assert c.status_code==200,c.text
    assert s.client.put(url+'/contacts/'+c.json()['id'],headers=H,json={'name':'Atualizado','is_primary':True}).status_code==200
    assert s.client.post(url+'/interactions',headers=H,json={'summary':'Contato realizado','type':'WhatsApp'}).status_code==200
    t=s.client.post(url+'/tasks',headers=H,json={'title':'Cobrar ficha','due_date':'2026-10-30'});assert t.status_code==200,t.text
    assert s.client.put(url+'/tasks/'+t.json()['id'],headers=H,json={'title':'Cobrar ficha','status':'concluida'}).status_code==200
    doc=s.client.post(url+'/documents',headers=H,data={'category':'Contratos'},files={'file':('contrato.pdf',b'%PDF-1.4 teste','application/pdf')})
    assert doc.status_code==200,doc.text
    d=doc.json();assert 'path' not in d['data'] and len(d['data']['sha256'])==64
    assert s.client.put(url+'/documents/'+d['id'],headers=H,json={'category':'Ficha cadastral','valid_until':'2027-01-01'}).status_code==200
    assert s.client.get(url+'/documents/'+d['id']+'/download').content==b'%PDF-1.4 teste'
    got=s.client.get(url).json();assert sum(c['data']['is_primary'] for c in got['contacts'])==1
    assert got['tasks'][0]['data']['completed_at']

@pytest.mark.parametrize('actor',['ana','dev'])
def test_managers_access_own_org(setup,actor):
    item=create(setup);setup.state.user=setup.people.users[actor]
    assert update(setup,item,score='frio').status_code==200
    item2=create(setup,responsible_user_id=str(setup.people.users['vera'].id))
    assert item2['responsible_user_id']==str(setup.people.users['vera'].id)

def test_other_owner_and_org_cannot_access_or_mutate(setup):
    s=setup;s.state.user=s.people.users['ana'];item=create(s);s.state.user=s.people.users['vera'];url='/api/v1/fornecedores/'+item['id']
    for actor in ('vera','fora'):
        s.state.user=s.people.users[actor]
        assert s.client.get(url).status_code==404
        assert update(s,item,score='quente').status_code==404
        for endpoint,body in [('contacts',{'name':'X'}),('interactions',{'summary':'X'}),('tasks',{'title':'X'})]:
            assert s.client.post(url+'/'+endpoint,headers=H,json=body).status_code==404
        assert s.client.post(url+'/documents',headers=H,files={'file':('a.pdf',b'%PDF-1.4')}).status_code==404
        assert not s.client.get('/api/v1/fornecedores').json()['items']

def test_assignment_and_csrf(setup):
    s=setup
    assert s.client.post('/api/v1/fornecedores',json={'name':'X'}).status_code==403
    assert s.client.post('/api/v1/fornecedores',headers=H,json={'name':'X','responsible_user_id':str(s.people.users['ana'].id)}).status_code==403
    s.state.user=s.people.users['dev']
    assert s.client.post('/api/v1/fornecedores',headers=H,json={'name':'X','responsible_user_id':str(s.people.users['fora'].id)}).status_code==422
    with s.people.session() as db:
        u=db.get(type(s.people.users['vera']),s.people.users['vera'].id);u.active=False;db.commit()
    assert s.client.post('/api/v1/fornecedores',headers=H,json={'name':'X','responsible_user_id':str(s.people.users['vera'].id)}).status_code==422

def test_document_security_and_child_scope(setup):
    s=setup;a=create(s);b=create(s,name='Outra');url='/api/v1/fornecedores/'+a['id']
    for name,raw in [('../outside.pdf',b'%PDF-1.4'),('bad.pdf',b'executable'),('bad.html',b'<script>')]:
        assert s.client.post(url+'/documents',headers=H,files={'file':(name,raw)}).status_code==422
    doc=s.client.post(url+'/documents',headers=H,files={'file':('ok.pdf',b'%PDF-1.4')}).json()
    assert s.client.get('/api/v1/fornecedores/'+b['id']+'/documents/'+doc['id']+'/download').status_code==404
    s.state.user=s.people.users['fora']
    assert s.client.get(url+'/documents/'+doc['id']+'/download').status_code==404
    assert len(list((s.tmp/'docs').rglob('*.*')))==0  # stored paths use only UUIDs, no user filenames

def test_anonymous_denied():
    app=FastAPI();app.include_router(routes.router)
    def denied():
        from fastapi import HTTPException
        raise HTTPException(401,'Login necessário')
    app.dependency_overrides[get_current_auth]=denied
    app.dependency_overrides[get_db_session]=lambda:None
    with TestClient(app) as c:assert c.get('/api/v1/fornecedores').status_code==401

def test_migration_matches_models_and_is_additive(people):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    path=Path('migrations/versions/20261026_0015_suppliers.py')
    spec=importlib.util.spec_from_file_location('supplier_migration',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with people.engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            for model in MODELS:
                columns={c['name'] for c in inspect(connection).get_columns(model.__tablename__)}
                expected=set(model.__table__.columns.keys())-({'archived_at','archived_by'} if model is Supplier else set())
                assert columns==expected
            module.downgrade()
            assert 'users' in inspect(connection).get_table_names()

def test_archive_delete_migration_matches_models(people):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    loaded=[]
    for filename in ('20261026_0015_suppliers.py','20261027_0016_supplier_ai_runs.py',
                     '20261027_0017_supplier_ai_runs_optional_supplier.py','20261027_0018_supplier_archive_delete.py'):
        path=Path('migrations/versions')/filename
        spec=importlib.util.spec_from_file_location(filename,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);loaded.append(module)
    with people.engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            for module in loaded:module.upgrade()
            assert {c['name'] for c in inspect(connection).get_columns('suppliers')}==set(Supplier.__table__.columns.keys())
            assert {c['name'] for c in inspect(connection).get_columns('supplier_deletion_audits')}==set(SupplierDeletionAudit.__table__.columns.keys())
            for module in reversed(loaded):module.downgrade()

def test_internal_task_appears_on_card_without_planner(setup):
    s=setup;item=create(s);url='/api/v1/fornecedores/'+item['id']
    s.client.post(url+'/tasks',headers=H,json={'title':'Próximo contato','due_date':'2026-10-30'})
    data=s.client.get('/api/v1/fornecedores').json()['items'][0]['data']
    assert data['next_action']=='Próximo contato' and data['next_action_date']=='2026-10-30'

def test_inline_patch_persists_audit_without_overwriting_profile(setup):
    s=setup;item=create(s,legal_name='Preservada');url='/api/v1/fornecedores/'+item['id']
    r=s.client.patch(url,headers=H,json={'stage':'tratativa','expected_stage':'base_ativa','score':'quente'})
    assert r.status_code==200 and r.json()['data']['legal_name']=='Preservada'
    assert s.client.patch(url,headers=H,json={'stage':'ativo','expected_stage':'base_ativa'}).status_code==409
    assert s.client.patch(url,json={'score':'frio'}).status_code==403
    assert s.client.patch(url,headers=H,json={'responsible_user_id':str(s.people.users['ana'].id)}).status_code==403
    s.state.user=s.people.users['fora']
    assert s.client.patch(url,headers=H,json={'score':'frio'}).status_code==404

def test_archive_hides_from_default_filter_preserves_relations_and_restores(setup):
    s=setup;item=create(s);url='/api/v1/fornecedores/'+item['id']
    s.client.post(url+'/contacts',headers=H,json={'name':'Contato'})
    s.client.post(url+'/tasks',headers=H,json={'title':'Acompanhar'})
    document=s.client.post(url+'/documents',headers=H,data={'category':'Contratos'},files={'file':('contrato.pdf',b'%PDF-1.4 arquivo','application/pdf')}).json()
    current=s.client.get(url).json()
    archived=s.client.post(url+'/archive',headers=H,json={'expected_updated_at':current['updated_at'],'reason':'Relacionamento pausado'})
    assert archived.status_code==200,archived.text
    assert archived.json()['archived_at'] and archived.json()['archived_by']==str(s.state.user.id)
    assert s.client.get('/api/v1/fornecedores').json()['items']==[]
    assert [x['id'] for x in s.client.get('/api/v1/fornecedores?archive_status=archived').json()['items']]==[item['id']]
    assert [x['id'] for x in s.client.get('/api/v1/fornecedores?archive_status=all').json()['items']]==[item['id']]
    detail=s.client.get(url).json()
    assert len(detail['contacts'])==len(detail['tasks'])==len(detail['documents'])==1
    event=next(x for x in detail['history'] if x['event']=='supplier_archived')
    assert event['actor_id']==str(s.state.user.id) and event['data']['reason']=='Relacionamento pausado'
    assert s.client.get(url+'/documents/'+document['id']+'/download').status_code==200
    restored=s.client.post(url+'/restore',headers=H,json={'expected_updated_at':archived.json()['updated_at'],'reason':''})
    assert restored.status_code==200,restored.text
    assert restored.json()['archived_at'] is None and restored.json()['stage']==item['stage']
    assert s.client.get('/api/v1/fornecedores').json()['items'][0]['id']==item['id']
    assert 'supplier_restored' in {x['event'] for x in s.client.get(url).json()['history']}

def test_archive_and_delete_require_csrf_and_current_version(setup):
    s=setup;item=create(s);url='/api/v1/fornecedores/'+item['id']
    assert s.client.post(url+'/archive',json={'expected_updated_at':item['updated_at']}).status_code==403
    changed=s.client.patch(url,headers=H,json={'score':'quente'}).json()
    conflict=s.client.post(url+'/archive',headers=H,json={'expected_updated_at':item['updated_at']})
    assert conflict.status_code==409 and 'alterado por outra pessoa' in conflict.text
    s.state.user=s.people.users['ana']
    assert s.client.request('DELETE',url,json={'expected_updated_at':changed['updated_at'],'confirm_name':item['name']}).status_code==403

def test_permanent_delete_permissions_confirmation_scope_quarantine_ai_and_audit(setup):
    s=setup;item=create(s);url='/api/v1/fornecedores/'+item['id']
    s.client.post(url+'/contacts',headers=H,json={'name':'Contato'})
    s.client.post(url+'/tasks',headers=H,json={'title':'Tarefa'})
    document=s.client.post(url+'/documents',headers=H,files={'file':('ficha.pdf',b'%PDF-1.4 ficha')}).json()
    with s.people.session() as db:
        db.add(SupplierAIRun(organization_id=s.people.org.id,supplier_id=uuid.UUID(item['id']),actor_id=s.state.user.id,
            source_type='website',source_hash='a'*64,model='mock',status='applied',data={'audit':'preservar'}));db.commit()
    current=s.client.get(url).json()
    s.state.user=s.people.users['vera']
    assert s.client.request('DELETE',url,headers=H,json={'expected_updated_at':current['updated_at'],'confirm_name':item['name']}).status_code==403
    s.state.user=s.people.users['fora']
    assert s.client.request('DELETE',url,headers=H,json={'expected_updated_at':current['updated_at'],'confirm_name':item['name']}).status_code==404
    s.state.user=s.people.users['ana']
    assert s.client.request('DELETE',url,headers=H,json={'expected_updated_at':current['updated_at'],'confirm_name':'nome incorreto'}).status_code==422
    result=s.client.request('DELETE',url,headers=H,json={'expected_updated_at':current['updated_at'],'confirm_name':item['name'],'reason':'Duplicado'})
    assert result.status_code==200,result.text
    assert result.json()['counts']=={'contacts':1,'tasks':1,'documents':1,'history':4,'ai_runs_detached':1}
    assert result.json()['document_policy']=='quarantined'
    assert s.client.get(url).status_code==404
    assert s.client.get(url+'/documents/'+document['id']+'/download').status_code==404
    with s.people.session() as db:
        assert db.get(Supplier,uuid.UUID(item['id'])) is None
        for model in (SupplierContact,SupplierTask,SupplierDocument,SupplierInteraction):
            assert db.scalar(select(model).where(model.supplier_id==uuid.UUID(item['id']))) is None
        run=db.scalar(select(SupplierAIRun));assert run and run.supplier_id is None and run.status=='supplier_deleted'
        audit=db.scalar(select(SupplierDeletionAudit));assert audit.actor_id==s.state.user.id and audit.supplier_name==item['name']
        assert audit.data['documents']==1 and audit.data['reason']=='Duplicado' and audit.data['document_policy']=='quarantined'
    assert not (s.tmp/'docs'/str(s.people.org.id)/item['id']).exists()
    assert list((s.tmp/'docs'/'_deleted'/str(s.people.org.id)/item['id']).rglob('ficha.pdf'))==[]  # names are never physical paths
    assert len([p for p in (s.tmp/'docs'/'_deleted').rglob('*') if p.is_file()])==1

def test_stale_delete_after_other_user_edit_returns_409_and_keeps_supplier(setup):
    s=setup;item=create(s);url='/api/v1/fornecedores/'+item['id']
    s.state.user=s.people.users['ana'];opened=s.client.get(url).json()  # A abre o fornecedor
    s.state.user=s.people.users['vera']                                     # B edita (inclusive só um contato)
    assert s.client.post(url+'/contacts',headers=H,json={'name':'Novo contato'}).status_code==200
    s.state.user=s.people.users['ana']
    stale=s.client.request('DELETE',url,headers=H,json={'expected_updated_at':opened['updated_at'],'confirm_name':item['name']})
    assert stale.status_code==409 and 'alterado por outra pessoa' in stale.text
    assert s.client.get(url).status_code==200
    assert s.client.post(url+'/archive',headers=H,json={'expected_updated_at':opened['updated_at']}).status_code==409
    fresh=s.client.get(url).json()
    archived=s.client.post(url+'/archive',headers=H,json={'expected_updated_at':fresh['updated_at']}).json()
    assert s.client.post(url+'/archive',headers=H,json={'expected_updated_at':archived['updated_at']}).status_code==409  # já arquivado
    gone=s.client.request('DELETE',url,headers=H,json={'expected_updated_at':archived['updated_at'],'confirm_name':item['name']})
    assert gone.status_code==200,gone.text  # arquivado pode ser excluído
    with s.people.session() as db:
        audit=db.scalar(select(SupplierDeletionAudit));assert audit.data['was_archived'] is True and audit.data['document_policy']=='no_physical_directory'
    assert s.client.request('DELETE',url,headers=H,json={'expected_updated_at':archived['updated_at'],'confirm_name':item['name']}).status_code==404

def test_delete_failure_after_quarantine_restores_files_and_rows(setup,monkeypatch):
    s=setup;item=create(s);url='/api/v1/fornecedores/'+item['id']
    s.client.post(url+'/documents',headers=H,files={'file':('ficha.pdf',b'%PDF-1.4 ficha')})
    current=s.client.get(url).json();s.state.user=s.people.users['ana']
    def boom(**_):raise RuntimeError('falha simulada na auditoria')
    monkeypatch.setattr(routes,'SupplierDeletionAudit',boom)
    with pytest.raises(RuntimeError):
        s.client.request('DELETE',url,headers=H,json={'expected_updated_at':current['updated_at'],'confirm_name':item['name']})
    after=s.client.get(url);assert after.status_code==200 and len(after.json()['documents'])==1
    assert s.client.get(url+'/documents/'+after.json()['documents'][0]['id']+'/download').status_code==200
    assert not [p for p in (s.tmp/'docs'/'_deleted').rglob('*') if p.is_file()]
