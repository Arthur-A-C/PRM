"""Novo fornecedor com IA: analysis before the Supplier exists, creation only after review (no real Anthropic/network)."""
import io
import uuid

import pytest
from sqlalchemy import func, select

from app.models.suppliers import Supplier, SupplierAIRun, SupplierContact, SupplierDocument, SupplierInteraction
from app.routers import supplier_ai as ai_routes
from app.services import suppliers as supplier_service
from test_supplier_ai import (H, SECRET, FakeAI, empty, fv, setup, site_extraction)  # noqa: F401  (fixture)
from test_store_removal_production import people  # noqa: F401

API = '/api/v1/fornecedores'
FICHA = 'Ficha cadastral\nRazao social;Portwell Comercio Ltda\nCNPJ;11.222.333/0001-81\nTelefone;+55 47 1111-1111\nE-mail;fiscal@portwell.example\n'


def counts(s):
    with s.people.session() as db:
        return {m.__name__: db.scalar(select(func.count()).select_from(m)) for m in (Supplier, SupplierContact, SupplierDocument, SupplierInteraction)}


def analyze(s, url='', ficha=None, name='ficha.csv'):
    files = {'file': (name, ficha.encode('utf-8') if isinstance(ficha, str) else ficha, 'text/csv')} if ficha is not None else None
    return s.client.post(API + '/ai/analisar', headers=H, data={'url': url}, files=files)


def ficha_extraction():
    data = empty()
    data['company']['legal_name'] = [fv('Portwell Comercio Ltda', 'D1')]
    data['company']['tax_id'] = [fv('11.222.333/0001-81', 'D1')]
    data['phones'] = [{**fv('+55 47 1111-1111', 'D1'), 'kind': 'phone'}]
    data['emails'] = [{**fv('fiscal@portwell.example', 'D1'), 'kind': 'financial'}]
    return data


def value_of(preview, key, index=0):
    field = next(f for f in preview['fields'] if f['key'] == key)
    return field['suggestions'][index]['value']


def body(preview, **extra):
    fields = {f['key']: {'value': f['suggestions'][f['preselect'] if f['preselect'] is not None else 0]['value'],
                         'choice': f['preselect'] if f['preselect'] is not None else 0} for f in preview['fields']}
    return {'run_id': preview['run_id'], 'name': preview['defaults']['name'] or 'Fornecedor', 'fields': fields, **extra}


def pending_files(s):
    return [p for p in (s.tmp / 'docs').rglob('*') if p.is_file() and '_pendentes' in p.parts]


def test_site_only_analysis_creates_nothing(setup):
    s = setup; before = counts(s)
    r = analyze(s, 'https://www.sihovision.com/')
    assert r.status_code == 200, r.text
    p = r.json()
    assert p['mode'] == 'new' and p['source']['type'] == 'website' and p['document'] is None
    assert p['defaults'] == {'name': 'Sihovision', 'stage': next(iter(supplier_service.STAGES)), 'score': 'morno',
                             'responsible_user_id': str(s.state.user.id), 'website': 'https://www.sihovision.com/'}
    assert value_of(p, 'legal_name') == 'Shenzhen Shinho Electronic Technology Co., Limited'
    email = next(f for f in p['fields'] if f['key'] == 'email')['suggestions'][0]
    assert email['source'] == 'https://www.sihovision.com/' and email['evidence']
    assert counts(s) == before
    with s.people.session() as db:
        run = db.scalar(select(SupplierAIRun))
        assert run.supplier_id is None and run.status == 'ok' and run.actor_id == s.state.user.id


def test_ficha_only_and_combined_show_divergence(setup):
    s = setup
    s.state.fake.result = ficha_extraction()
    p = analyze(s, ficha=FICHA).json()
    assert p['source']['type'] == 'supplier_document' and p['document']['original_name'] == 'ficha.csv'
    cnpj = next(f for f in p['fields'] if f['key'] == 'cnpj')['suggestions'][0]
    assert cnpj['source_type'] == 'supplier_document' and cnpj['source'] == 'ficha.csv'
    assert len(pending_files(s)) == 1 and counts(s)['Supplier'] == 0
    combined = site_extraction(); combined['phones'].append({**fv('+55 47 1111-1111', 'D1'), 'kind': 'phone'})
    s.state.fake.result = combined
    p = analyze(s, 'https://www.sihovision.com/', FICHA).json()
    phone = next(f for f in p['fields'] if f['key'] == 'phone')
    assert p['source']['type'] == 'combined' and phone['status'] == 'conflict' and phone['preselect'] is None
    assert {x['source_type'] for x in phone['suggestions']} == {'website', 'supplier_document'}


def test_create_after_preview_with_contacts_ficha_history_and_run_link(setup):
    s = setup
    combined = site_extraction(); combined['phones'].append({**fv('+55 47 1111-1111', 'D1'), 'kind': 'phone'})
    s.state.fake.result = combined
    raw = FICHA.encode()
    p = analyze(s, 'https://www.sihovision.com/', raw).json()
    phone = next(f for f in p['fields'] if f['key'] == 'phone')
    site_index = next(i for i, x in enumerate(phone['suggestions']) if x['source_type'] == 'website')
    other = 1 - site_index
    data = body(p, contacts=[c['id'] for c in p['contacts'] if c['name'] == 'John Smith'], social=[x['id'] for x in p['social']],
                also_contacts=[{'key': 'phone', 'choice': other}])
    data['fields']['phone'] = {'value': phone['suggestions'][site_index]['value'], 'choice': site_index}
    data['fields']['trade_name'] = {'value': 'Sihovision Brasil', 'choice': 0}  # edited by the user
    data['fields']['segment'] = {'value': 'Displays industriais', 'choice': None}  # typed manually
    r = s.client.post(API + '/ai/criar', headers=H, json=data)
    assert r.status_code == 200, r.text
    created = r.json()['id']
    with s.people.session() as db:
        supplier = db.get(Supplier, uuid.UUID(created))
        assert supplier.responsible_user_id == s.state.user.id and supplier.stage == next(iter(supplier_service.STAGES)) and supplier.score == 'morno'
        assert supplier.data['legal_name'] == 'Shenzhen Shinho Electronic Technology Co., Limited' and supplier.data['trade_name'] == 'Sihovision Brasil'
        assert 'LinkedIn: https://www.linkedin.com/company/sihovision' in supplier.data['social_links']
        contacts = [c.data for c in db.scalars(select(SupplierContact).where(SupplierContact.supplier_id == supplier.id))]
        assert {c['name'] for c in contacts} == {'John Smith', 'Telefone'} and sum(c['is_primary'] for c in contacts) == 1
        doc = db.scalar(select(SupplierDocument).where(SupplierDocument.supplier_id == supplier.id))
        assert doc.data['category'] == 'Ficha cadastral' and doc.data['original_name'] == 'ficha.csv' and doc.data['size'] == len(raw)
        assert doc.data['sha256'] == __import__('hashlib').sha256(raw).hexdigest() and doc.actor_id == s.state.user.id and doc.organization_id == supplier.organization_id
        history = db.scalar(select(SupplierInteraction).where(SupplierInteraction.supplier_id == supplier.id))
        assert history.event == 'supplier_created_ai' and 'ficha cadastral + site oficial' in history.data['description']
        assert '1 editado(s) manualmente' in history.data['description'] and '2 contato(s)' in history.data['description']
        origins = {f['key']: f['origin'] for f in history.data['fields']}
        assert origins['trade_name'] == 'editado' and origins['segment'] == 'manual' and origins['legal_name'] == 'ia'
        run = db.scalar(select(SupplierAIRun).where(SupplierAIRun.id == uuid.UUID(p['run_id'])))
        assert run.supplier_id == supplier.id and run.status == 'applied' and run.data['created']['document_attached']
    assert not pending_files(s)
    download = s.client.get(f'{API}/{created}/documents/{doc.id}/download')
    assert download.status_code == 200 and download.content == raw
    card = s.client.get(API).json()
    assert created in card['columns'][next(iter(supplier_service.STAGES))]  # born as a Kanban card
    assert s.client.post(API + '/ai/criar', headers=H, json=data).status_code == 409  # a preview is used once


def test_cancel_creates_nothing_and_removes_pending_ficha(setup):
    s = setup; s.state.fake.result = ficha_extraction()
    p = analyze(s, ficha=FICHA).json()
    assert len(pending_files(s)) == 1
    assert s.client.post(API + '/ai/descartar', headers=H, json={'run_id': p['run_id']}).status_code == 200
    assert not pending_files(s) and counts(s)['Supplier'] == 0
    assert s.client.post(API + '/ai/criar', headers=H, json=body(p)).status_code == 409


@pytest.mark.parametrize('field,existing', [('cnpj', {'cnpj': '11222333000181'}),
                                            ('company_registration', {'company_registration': 'BR-9988-77'}),
                                            ('website', {'website': 'http://sihovision.com/en'})])
def test_strong_duplicates_block_creation(setup, field, existing):
    s = setup
    old = s.client.post(API, headers=H, json={'name': 'Já existe', **existing}).json()
    with s.people.session() as db:  # registered long before the analysis (sqlite timestamps have 1 s resolution)
        from datetime import datetime, timedelta, timezone
        db.get(Supplier, uuid.UUID(old['id'])).created_at = datetime.now(timezone.utc) - timedelta(hours=1); db.commit()
    result = site_extraction()
    result['company']['tax_id'] = [fv('11.222.333/0001-81', 'S2', 'CNPJ 11.222.333/0001-81')] if field == 'cnpj' else []
    s.state.site.pages['/contact-us/'] = (200, s.state.site.pages['/contact-us/'][1].replace('</body>', '<p>CNPJ 11.222.333/0001-81</p></body>'))
    s.state.fake.result = result
    p = analyze(s, 'https://www.sihovision.com/').json()
    data = body(p)
    if field == 'company_registration':
        data['fields']['company_registration'] = {'value': 'br 9988 77', 'choice': None}
    if field == 'website':
        assert any(d['strong'] and 'dominio' in d['reasons'] for d in p['duplicates'])
    r = s.client.post(API + '/ai/criar', headers=H, json=data)
    assert r.status_code == 409 and r.json()['detail']['can_continue'] is False
    assert r.json()['detail']['message'] == 'Possível fornecedor já cadastrado.'
    assert r.json()['detail']['duplicates'][0]['name'] == 'Já existe' and counts(s)['Supplier'] == 1


def test_name_similarity_warns_and_can_continue(setup):
    s = setup
    s.client.post(API, headers=H, json={'name': 'Sihovision Ltda.'})
    p = analyze(s, 'https://www.sihovision.com/').json()
    assert p['duplicates'][0]['reasons'] == ['nome'] and not p['duplicates'][0]['strong']
    r = s.client.post(API + '/ai/criar', headers=H, json=body(p))
    assert r.status_code == 409 and r.json()['detail']['can_continue'] is True
    assert s.client.post(API + '/ai/criar', headers=H, json=body(p, allow_name_duplicate=True)).status_code == 200
    assert counts(s)['Supplier'] == 2


def test_supplier_created_by_someone_else_while_reviewing(setup):
    s = setup
    p = analyze(s, 'https://www.sihovision.com/').json()
    assert p['duplicates'] == []
    other = s.state.user; s.state.user = s.people.users['ana']
    s.client.post(API, headers=H, json={'name': 'Cadastro paralelo', 'website': 'https://sihovision.com'})
    s.state.user = other
    r = s.client.post(API + '/ai/criar', headers=H, json=body(p))
    assert r.status_code == 409 and r.json()['detail']['message'] == 'Este fornecedor foi cadastrado enquanto você revisava a análise.'


def test_organization_isolation_and_permissions(setup):
    s = setup
    p = analyze(s, 'https://www.sihovision.com/').json()
    for actor in ('fora', 'ana'):  # other organization; other person (even a manager) cannot use someone else's preview
        s.state.user = s.people.users[actor]
        assert s.client.post(API + '/ai/criar', headers=H, json=body(p)).status_code == 404
        assert s.client.post(API + '/ai/descartar', headers=H, json={'run_id': p['run_id']}).status_code == 404
    s.state.user = s.people.users['fora']
    s.client.post(API, headers=H, json={'name': 'Sihovision', 'website': 'https://sihovision.com'})
    s.state.user = s.people.users['vera']
    assert analyze(s, 'https://www.sihovision.com/').json()['duplicates'] == []  # other org's supplier is not visible
    assert s.client.post(API + '/ai/analisar', data={'url': 'https://www.sihovision.com/'}).status_code == 403  # CSRF
    r = s.client.post(API + '/ai/criar', headers=H, json=body(p, responsible_user_id=str(s.people.users['ana'].id)))
    assert r.status_code == 403  # seller cannot assign another responsible
    assert s.client.post(API + '/ai/criar', headers=H, json=body(p, stage='inexistente')).status_code == 422


def test_manager_assigns_responsible_of_same_org_only(setup):
    s = setup; s.state.user = s.people.users['dev']
    p = analyze(s, 'https://www.sihovision.com/').json()
    assert s.client.post(API + '/ai/criar', headers=H, json=body(p, responsible_user_id=str(s.people.users['fora'].id))).status_code == 422
    r = s.client.post(API + '/ai/criar', headers=H, json=body(p, responsible_user_id=str(s.people.users['vera'].id), stage='tratativa', score='quente'))
    assert r.status_code == 200
    with s.people.session() as db:
        created = db.get(Supplier, uuid.UUID(r.json()['id']))
        assert (created.responsible_user_id, created.stage, created.score) == (s.people.users['vera'].id, 'tratativa', 'quente')


@pytest.mark.parametrize('key,value', [('email', 'nao-e-email'), ('phone', 'abc'), ('website', 'javascript:alert(1)'),
                                       ('website', 'ftp://x.com'), ('cnpj', '11.222.333/0001-82'), ('uf', 'SPX'), ('legal_name', 'x' * 4001)])
def test_backend_revalidates_edited_values(setup, key, value):
    s = setup
    p = analyze(s, 'https://www.sihovision.com/').json()
    data = body(p); data['fields'][key] = {'value': value, 'choice': None}
    assert s.client.post(API + '/ai/criar', headers=H, json=data).status_code == 422
    assert counts(s)['Supplier'] == 0


def test_unknown_field_choice_and_contact_ids_are_rejected(setup):
    s = setup
    p = analyze(s, 'https://www.sihovision.com/').json()
    for patch in ({'fields': {'is_admin': {'value': '1'}}}, {'fields': {'legal_name': {'value': 'x', 'choice': 9}}},
                  {'contacts': ['c999']}, {'social': ['s999']}, {'also_contacts': [{'key': 'legal_name', 'choice': 0}]}):
        assert s.client.post(API + '/ai/criar', headers=H, json={**body(p), **patch}).status_code == 422
    assert counts(s)['Supplier'] == 0


def test_ssrf_still_blocked_and_nothing_created(setup):
    s = setup
    for bad in ('http://127.0.0.1/', 'http://169.254.169.254/', 'file:///etc/passwd'):
        assert analyze(s, bad).status_code == 422
    assert counts(s)['Supplier'] == 0 and not s.state.fake.calls


def test_anthropic_failure_creates_nothing_and_drops_pending_ficha(setup):
    s = setup
    s.state.fake = FakeAI(error=ConnectionError('down ' + SECRET))
    r = analyze(s, 'https://www.sihovision.com/', FICHA)
    assert r.status_code == 502 and SECRET not in r.text
    assert counts(s)['Supplier'] == 0 and not pending_files(s)


def test_creation_error_rolls_back_everything(setup, monkeypatch):
    s = setup; s.state.fake.result = ficha_extraction()
    p = analyze(s, ficha=FICHA).json()
    def boom(*args, **kwargs):
        raise RuntimeError('falha simulada no histórico')
    monkeypatch.setattr(ai_routes.service, 'audit', boom)
    with pytest.raises(RuntimeError):
        s.client.post(API + '/ai/criar', headers=H, json=body(p, contacts=[c['id'] for c in p['contacts']]))
    assert counts(s) == {'Supplier': 0, 'SupplierContact': 0, 'SupplierDocument': 0, 'SupplierInteraction': 0}
    assert len(pending_files(s)) == 1  # ficha stays with the pending analysis
    with s.people.session() as db:
        assert db.get(SupplierAIRun, uuid.UUID(p['run_id'])).status == 'ok'
    monkeypatch.undo()
    assert s.client.post(API + '/ai/criar', headers=H, json=body(p)).status_code == 200  # retry works


def test_requires_a_source_and_existing_flow_still_works(setup):
    s = setup
    assert s.client.post(API + '/ai/analisar', headers=H, data={'url': ''}).status_code == 422
    item = s.client.post(API, headers=H, json={'name': 'Sihovision', 'website': 'https://www.sihovision.com/'}).json()
    p = s.client.post(f"{API}/{item['id']}/ai/analisar-site", headers=H, json={}).json()  # Preencher com IA preserved
    assert s.client.post(f"{API}/{item['id']}/ai/aplicar", headers=H, json={'run_id': p['run_id'], 'fields': [{'key': 'legal_name', 'choice': 0}]}).status_code == 200


def test_migration_0017_makes_supplier_optional(people):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    from app.models.suppliers import MODELS
    for model in MODELS:
        model.__table__.create(people.engine)
    load = lambda name: (lambda spec: (spec.loader.exec_module(m := importlib.util.module_from_spec(spec)), m)[1])(
        importlib.util.spec_from_file_location(name, Path('migrations/versions') / name))
    m16, m17 = load('20261027_0016_supplier_ai_runs.py'), load('20261027_0017_supplier_ai_runs_optional_supplier.py')
    assert m17.down_revision == m16.revision
    with people.engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            m16.upgrade(); m17.upgrade()
            assert next(c for c in inspect(connection).get_columns('supplier_ai_runs') if c['name'] == 'supplier_id')['nullable'] is True
            m17.downgrade()
            assert next(c for c in inspect(connection).get_columns('supplier_ai_runs') if c['name'] == 'supplier_id')['nullable'] is False
