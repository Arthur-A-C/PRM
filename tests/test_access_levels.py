import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.config import get_settings
from app.db import get_db_session
from app.dependencies import get_current_auth
from app.models import Organization, User, Company
from app.routers import pages
from app.services.access import api_allowed, visible_navigation, public_product_data
from app.services.security import hash_secret, verify_password


@pytest.fixture
def accounts(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    for model in (Organization, User, Company):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        org=Organization(name='Access tests'); db.add(org); db.flush()
        user=User(name='Admin', email='admin@example.test', role='desenvolvedor',
                  organization_id=org.id, password_hash='unused', active=True)
        db.add(user); db.commit()
        auth=SimpleNamespace(user=user, login_session=SimpleNamespace(csrf_hash=hash_secret('csrf-test')))
        app.dependency_overrides[get_current_auth]=lambda:auth
        app.dependency_overrides[get_db_session]=lambda:db
        monkeypatch.setattr(pages,'get_engine',lambda:engine)
        monkeypatch.setattr(pages,'find_auth_context',lambda *args:auth)
        with TestClient(app) as client:
            client.cookies.set(get_settings().session_cookie_name,'test-session')
            client.cookies.set(get_settings().csrf_cookie_name,'csrf-test')
            yield client,db,auth
        app.dependency_overrides.clear()
    engine.dispose()


@pytest.mark.parametrize('creator', ['desenvolvedor','gestor'])
@pytest.mark.parametrize('role', ['desenvolvedor','gestor','vendedor'])
def test_account_creation_organization_hash_and_no_secret_response(accounts, creator, role):
    client,db,auth=accounts;auth.user.role=creator
    url='/contas/criar/'+role
    assert client.get(url).status_code==200
    response=client.post(url,data={'name':'New user','email':' NEW@EXAMPLE.TEST ',
        'password':'safe-test-password','csrf_token':'csrf-test','organization_id':str(uuid.uuid4()),'role':'invented'},follow_redirects=False)
    assert response.status_code==303
    new=db.scalar(select(User).where(User.email=='new@example.test'))
    assert new.role==role and new.organization_id==auth.user.organization_id
    assert verify_password(new.password_hash,'safe-test-password')
    assert 'safe-test-password' not in response.text and new.password_hash not in response.text


def test_invalid_duplicate_csrf(accounts):
    client,db,auth=accounts;url='/contas/criar/gestor'
    fields={'name':'New','email':'new@example.test','password':'123456','csrf_token':'wrong'}
    assert client.post(url,data=fields).status_code==403
    fields['csrf_token']='csrf-test';fields['password']='short'
    response=client.post(url,data=fields)
    assert response.status_code==422 and 'short' not in response.text
    fields['password']='123456'
    assert client.post(url,data=fields,follow_redirects=False).status_code==303
    assert client.post(url,data=fields).status_code==409
    assert client.post('/contas/criar/root',data=fields).status_code==422


@pytest.mark.parametrize('path', ['/digitalizacao','/digitalizacao/lotes','/digitalizacao/cadastro-api',
    '/integracoes-woocommerce','/importacoes','/gestao','/contas/criar/desenvolvedor',
    '/contas/criar/gestor','/contas/criar/vendedor'])
def test_seller_page_access_denied(accounts,path):
    client,db,auth=accounts;auth.user.role='vendedor'
    assert client.get(path).status_code==403


@pytest.mark.parametrize('method,path', [('GET','/api/v1/integracoes/lojas'),
    ('GET','/api/v1/cadastro-api'),('GET','/api/v1/digitalizacao/lotes'),
    ('GET','/api/v1/digitalizacao/lotes/modelo.csv'),('GET','/api/v1/dashboard/summary'),
    ('GET','/api/v1/comparable-portfolio'),('POST','/api/v1/digitalizacao/analisar'),
    ('POST','/api/v1/digitalizacao/extrair-especificacoes'),
    ('POST','/contas/criar/desenvolvedor')])
def test_seller_api_denied_even_with_csrf(accounts,method,path):
    client,db,auth=accounts;auth.user.role='vendedor'
    data={'name':'X','email':'x@example.test','password':'123456','csrf_token':'csrf-test'}
    assert client.request(method,path,data=data,headers={'X-CSRF-Token':'csrf-test'}).status_code==403


def test_navigation_and_seller_redirect(accounts):
    client,db,auth=accounts;auth.user.role='vendedor'
    response=client.get('/',follow_redirects=False)
    assert response.status_code==303 and response.headers['location']=='/catalogos'
    # Cards e Reuniões saíram da navegação; os links antigos abrem o Planner.
    redirect=client.get('/cards?activity=abc',follow_redirects=False)
    assert redirect.status_code==303 and redirect.headers['location']=='/planner?activity=abc'
    assert client.get('/reunioes',follow_redirects=False).headers['location']=='/planner?view=reunioes'
    response=client.get('/cards')
    assert response.status_code==200
    for href in ('href="/digitalizacao"','href="/importacoes"','href="/gestao"','href="/integracoes-woocommerce"','href="/reunioes"','href="/cards"'):
        assert href not in response.text
    assert 'href="/planner"' in response.text and 'href="/catalogos"' in response.text and 'data-planner-hub' in response.text
    assert client.get('/catalogos?internal=1').status_code==403


def test_anonymous_account_page_redirect(accounts):
    client,db,auth=accounts;client.cookies.clear()
    assert client.get('/contas/criar/desenvolvedor',follow_redirects=False).status_code==303
    app.dependency_overrides.pop(get_current_auth)
    response=client.post('/contas/criar/gestor', data={'name':'X','email':'x@example.test','password':'123456'})
    assert response.status_code==401


def test_module_matrix_and_provenance():
    for role in ('desenvolvedor','gestor'):
        assert api_allowed(role,'/api/v1/digitalizacao/analisar')
        assert visible_navigation(role,pages.NAV_ITEMS)==pages.NAV_ITEMS
    assert not api_allowed('unknown','/api/v1/products')
    assert api_allowed('vendedor','/api/v1/products')
    assert api_allowed('vendedor','/api/v1/planner/activities/calendar')
    assert not api_allowed('vendedor','/api/v1/planner-unsafe')
    data={'items':[{'name':'Product','source':{'filename':'secret-import.xlsx'},'prices':[{'amount':1}]}]}
    assert public_product_data(data)=={'items':[{'name':'Product','prices':[{'amount':1}]}]}
    assert data['items'][0]['source']
