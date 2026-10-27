"""Offer → revisão → publicação explícita → RefinedCatalogRun/Item → Comparador / Visão geral (sqlite, sem dados reais)."""
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select, text

from app.db import get_db_session
from app.config import Settings, get_settings
from app.dependencies import get_current_auth, require_module_access
from app.models.refined_catalog import RefinedCatalogItem, RefinedCatalogRaw, RefinedCatalogRun
from app.routers import catalog_imports
from app.services import catalog_publication as publication
from app.services.current_analysis import summarize_current
from app.services.refined_catalog_database import current_items, database_manifest, list_refined_items, source_registry
from app.services.security import hash_secret
from test_catalog_origin_import import catalog_db, preview  # noqa: F401  (fixture + helper)
from app.services.catalog_import import publish_catalog

H = {'X-CSRF-Token': 'csrf'}


@pytest.fixture
def pub(catalog_db):
    s = catalog_db
    engine = s.db.get_bind()
    for model in (RefinedCatalogRun, RefinedCatalogItem, RefinedCatalogRaw):
        model.__table__.create(engine)
    with engine.begin() as conn:  # sqlite ignores postgresql_where: recreate the real partial unique index
        conn.execute(text('DROP INDEX uq_refined_published_org'))
        conn.execute(text("CREATE UNIQUE INDEX uq_refined_published_org ON refined_catalog_runs (organization_id) WHERE status = 'published'"))
    app = FastAPI(); app.include_router(catalog_imports.router, dependencies=[Depends(require_module_access)])
    auth = SimpleNamespace(user=s.user, login_session=SimpleNamespace(csrf_hash=hash_secret('csrf')))
    app.dependency_overrides[get_current_auth] = lambda: auth
    app.dependency_overrides[get_db_session] = lambda: s.db
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    s.web, s.auth, s.tmp = TestClient(app), auth, None
    return s


def load(s, tmp_path, code, name='Produto', sku='001', price='1.250,00'):
    company = s.companies[code]
    path = tmp_path / f'{code}-{sku}.csv'
    path.write_text(f'SKU;Nome;Preco;Marca\n{sku};{name};{price};Marca {code}\n', encoding='utf-8-sig')
    from app.services.catalog_table import read_table, mapped_preview, suggest_mapping
    table = read_table(path)
    mapping = suggest_mapping(table['headers'])
    result = publish_catalog(s.db, mapped_preview(path, company.code, table, mapping), company)
    s.db.commit()
    return result


def runs(s):
    return {r.id: r.status for r in s.db.scalars(select(RefinedCatalogRun))}


def publish_via_api(s):
    preview_response = s.web.post('/api/v1/catalog-imports/publication/preview', headers=H)
    assert preview_response.status_code == 200, preview_response.text
    body = preview_response.json()
    confirm = s.web.post('/api/v1/catalog-imports/publication', headers=H, json={'version': body['version']})
    return body, confirm


def render(title, manifest, status, role='gestor'):
    env = Environment(loader=FileSystemLoader('app/templates'), autoescape=select_autoescape(['html']))
    return env.get_template('shell.html').render(
        title=title, user={'name': 'Gestor', 'role': role}, nav_items=[('Visão geral', '/')], active_path='/',
        refined_analysis=manifest, current_analysis=summarize_current(manifest), catalog_publication=status,
        analysis_sources=source_registry(manifest), url_for=lambda endpoint, path: '/static' + path, csrf_token='t',
        is_manager=role in ('gestor', 'desenvolvedor'))


def test_empty_catalog_cannot_publish_and_overview_says_so(pub):
    status = publication.publication_status(pub.db, pub.org.id)
    assert (status['internal'], status['competitor'], status['can_publish'], status['pending'], status['run_id']) == (0, 0, False, False, None)
    body, confirm = publish_via_api(pub)
    assert body['can_publish'] is False and confirm.status_code == 409
    assert runs(pub) == {}
    html = render('Visão geral', None, status)
    assert 'Nenhum catálogo importado' in html and 'data-cc-heatmap' in html


def test_import_never_publishes_and_offers_without_snapshot_are_reported(pub, tmp_path):
    load(pub, tmp_path, 'portwell'); load(pub, tmp_path, 'rival', 'Rival')
    assert runs(pub) == {} and database_manifest(pub.db, pub.org.id) is None
    status = publication.publication_status(pub.db, pub.org.id)
    assert (status['internal'], status['competitor'], status['can_publish'], status['pending']) == (1, 1, True, True)
    overview = render('Visão geral', None, status)
    assert 'Há produtos importados, mas a base ainda não foi publicada.' in overview and '/importacoes#publicacao' in overview
    assert 'data-cc-heatmap' in overview  # activity map does not depend on the catalog snapshot
    seller = render('Visão geral', None, status, role='vendedor')
    assert 'Solicite a um gestor' in seller and 'Revisar e publicar base' not in seller
    comparator = render('Comparador', None, status)
    assert 'Base atual indisponível' in comparator and 'id="publicacao"' in comparator


def test_publication_creates_snapshot_used_by_comparator_with_audit(pub, tmp_path):
    load(pub, tmp_path, 'portwell', 'IPC Fanless i5', 'PW-1', '2.500,00')
    load(pub, tmp_path, 'choice', 'Painel Touch 10', 'CH-1', '900,00')
    load(pub, tmp_path, 'rival', 'Computador industrial i5', 'RV-1', '2.300,00')
    body, confirm = publish_via_api(pub)
    assert confirm.status_code == 200, confirm.text
    assert body['can_publish'] and body['audit']['internal_count'] == 2 and body['audit']['competitor_count'] == 1
    manifest = database_manifest(pub.db, pub.org.id)
    assert manifest['origin'] == 'registered_catalog' and manifest['run_id'] == confirm.json()['run_id']
    registry = source_registry(manifest)
    assert list(registry)[:2] == ['choice', 'portwell'] and registry['portwell']['kind'] == 'own'
    rival = next(code for code, c in registry.items() if c['kind'] == 'competitor')
    assert registry[rival]['name'] == 'rival' and rival.startswith('c')
    audit = manifest['audit']
    assert audit['user_id'] == str(pub.user.id) and audit['user_name'] == 'Gestor' and audit['organization_id'] == str(pub.org.id)
    assert audit['published_at'] and (audit['internal_count'], audit['competitor_count']) == (2, 1)
    assert {c['name'] for c in audit['companies']} == {'portwell', 'choice', 'rival'} and len(audit['import_ids']) == 3
    assert pub.db.scalar(select(func.count()).select_from(RefinedCatalogItem)) == 3
    # Comparador / catálogo: produtos, empresas, concorrentes, preços, marcas, busca e filtros.
    own = list_refined_items(pub.db, pub.org.id, source_group='internal')
    rivals = list_refined_items(pub.db, pub.org.id, source_group='competitor')
    assert own['total'] == 2 and rivals['total'] == 1 and rivals['items'][0]['source_group'] == 'competitor'
    assert list_refined_items(pub.db, pub.org.id, search='fanless')['total'] == 1
    assert list_refined_items(pub.db, pub.org.id, source=rival)['total'] == 1
    item = rivals['items'][0]
    assert item['commercial']['prices'] and item['brand_claimed'] == 'Marca rival'
    pair = current_items(pub.db, pub.org.id, [uuid.UUID(own['items'][0]['item_id']), uuid.UUID(item['item_id'])])
    assert {p['source_name'] for p in pair} >= {'rival'} and {p['source_group'] for p in pair} == {'internal', 'competitor'}
    summary = summarize_current(manifest)
    assert [c['source'] for c in summary['competitors']] == [rival] and summary['own_public'] == 2
    status = publication.publication_status(pub.db, pub.org.id)
    assert status['pending'] is False and status['registered'] and status['run_id'] == manifest['run_id']
    for title in ('Comparador', 'Visão geral', 'Importações e qualidade'):
        html = render(title, manifest, status)
        assert 'Base atual indisponível' not in html and 'data-operations' in html and 'rival' in html
        families = json.loads(html.split('id="ops-families">')[1].split('</script>')[0])
        assert families['own'] == ['choice', 'portwell'] and families['rivals'] == [rival] and families['totals'] == {'group': 2, rival: 1}
    overview = render('Visão geral', manifest, status)
    assert 'Base publicada' in overview and '2 produtos da nossa base' in overview


def test_own_companies_are_never_competitors_of_each_other(pub, tmp_path):
    load(pub, tmp_path, 'portwell'); load(pub, tmp_path, 'choice', sku='002'); load(pub, tmp_path, 'sag', sku='003')
    body, confirm = publish_via_api(pub)
    assert body['can_publish'] is False and confirm.status_code == 409 and runs(pub) == {}
    load(pub, tmp_path, 'rival2', 'Concorrente')
    assert publish_via_api(pub)[1].status_code == 200
    summary = summarize_current(database_manifest(pub.db, pub.org.id))
    assert len(summary['competitors']) == 1 and {s['kind'] for s in summary['sources']} == {'own', 'competitor'}
    assert sum(s['kind'] == 'own' for s in summary['sources']) == 3


def test_update_replaces_snapshot_and_unchanged_base_is_idempotent(pub, tmp_path):
    load(pub, tmp_path, 'portwell'); load(pub, tmp_path, 'rival', 'Rival')
    first = publish_via_api(pub)[1].json()['run_id']
    again = publish_via_api(pub)[1]
    assert again.status_code == 200 and again.json()['run_id'] == first and len(runs(pub)) == 1
    load(pub, tmp_path, 'portwell', 'Novo produto', 'PW-2')
    assert publication.publication_status(pub.db, pub.org.id)['pending'] is True
    second = publish_via_api(pub)[1].json()['run_id']
    assert runs(pub) == {first: 'archived', second: 'published'}
    assert list_refined_items(pub.db, pub.org.id, source_group='internal')['total'] == 2


def test_failed_publication_keeps_previous_snapshot(pub, tmp_path, monkeypatch):
    load(pub, tmp_path, 'portwell'); load(pub, tmp_path, 'rival', 'Rival')
    first = publish_via_api(pub)[1].json()['run_id']
    load(pub, tmp_path, 'portwell', 'Outro', 'PW-9')
    version = publication.capture(pub.db, pub.org.id)[1]
    monkeypatch.setattr(publication, 'activate_run', lambda *a: (_ for _ in ()).throw(ValueError('Contagem SQL não reconciliada')))
    response = pub.web.post('/api/v1/catalog-imports/publication', headers=H, json={'version': version})
    assert response.status_code == 409
    assert runs(pub) == {first: 'published'} and database_manifest(pub.db, pub.org.id)['run_id'] == first
    assert pub.db.scalar(select(func.count()).select_from(RefinedCatalogItem)) == 2


def test_import_between_review_and_confirmation_blocks_inconsistent_snapshot(pub, tmp_path):
    load(pub, tmp_path, 'portwell'); load(pub, tmp_path, 'rival', 'Rival')
    version = pub.web.post('/api/v1/catalog-imports/publication/preview', headers=H).json()['version']
    load(pub, tmp_path, 'rival', 'Rival alterado')  # new import after the review
    response = pub.web.post('/api/v1/catalog-imports/publication', headers=H, json={'version': version})
    assert response.status_code == 409 and 'mudou' in response.json()['detail'] and runs(pub) == {}


def test_organization_isolation(pub, tmp_path):
    load(pub, tmp_path, 'portwell'); load(pub, tmp_path, 'rival', 'Rival'); load(pub, tmp_path, 'outside', 'Fora', 'X-1')
    publish_via_api(pub)
    manifest = database_manifest(pub.db, pub.org.id)
    assert 'outside' not in {c['name'] for c in manifest['audit']['companies']}
    assert database_manifest(pub.db, pub.other.id) is None
    assert publication.publication_status(pub.db, pub.other.id)['internal'] == 1  # other org sees only its own offer
    outside_offer = next(r['id'] for r in publication.capture(pub.db, pub.other.id)[0]['records'])
    with pytest.raises(LookupError):
        current_items(pub.db, pub.org.id, [uuid.UUID(outside_offer)])


def test_permissions_and_csrf(pub, tmp_path):
    load(pub, tmp_path, 'portwell'); load(pub, tmp_path, 'rival', 'Rival')
    assert pub.web.post('/api/v1/catalog-imports/publication/preview').status_code == 403
    version = pub.web.post('/api/v1/catalog-imports/publication/preview', headers=H).json()['version']
    assert pub.web.post('/api/v1/catalog-imports/publication', json={'version': version}).status_code == 403
    pub.auth.user.role = 'vendedor'
    for response in (pub.web.get('/api/v1/catalog-imports/publication'),
                     pub.web.post('/api/v1/catalog-imports/publication/preview', headers=H),
                     pub.web.post('/api/v1/catalog-imports/publication', headers=H, json={'version': version})):
        assert response.status_code == 403
    assert runs(pub) == {}


def test_enrichment_attributes_reach_the_comparator(pub, tmp_path):
    from app.models import Offer, OfferEnrichment
    load(pub, tmp_path, 'portwell', 'Fonte 19V', 'PW-F'); load(pub, tmp_path, 'rival', 'Fonte 12V', 'RV-F')
    for offer in pub.db.scalars(select(Offer)):
        enrichment = pub.db.scalar(select(OfferEnrichment).where(OfferEnrichment.offer_id == offer.id))
        values = {'tensao': '19 V' if offer.external_code == 'PW-F' else '12 V', 'protecao_ip': 'IP65'}
        if enrichment is None:
            pub.db.add(OfferEnrichment(offer_id=offer.id, source='regra', content_sha256='0' * 64, attributes=values))
        else:
            enrichment.attributes = values
    pub.db.commit()
    assert publish_via_api(pub)[1].status_code == 200
    items = list_refined_items(pub.db, pub.org.id)['items']
    observed = {i['record_key']: {(a['raw_name'], a['raw_value']) for a in i['attribute_observations']} for i in items}
    assert ('tensao', '19 V') in observed['PW-F'] and ('protecao ip', 'IP65') in observed['RV-F']
    assert all(i['attribute_count'] >= 2 for i in items)


def test_cheap_status_does_not_capture_every_offer(pub, tmp_path, monkeypatch):
    load(pub, tmp_path, 'portwell'); load(pub, tmp_path, 'rival', 'Rival')
    monkeypatch.setattr(publication, 'capture', lambda *a: pytest.fail('page render must not capture the whole catalog'))
    assert publication.publication_status(pub.db, pub.org.id)['can_publish'] is True
