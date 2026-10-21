"""Observed WCDA shapes, public synthetic URLs only. All PUT requests are mocked."""
from copy import deepcopy
import json

import httpx
import pytest

from app.services.store_document_update import (
    KEY, prepare_document_update, preview, simulate_update, verify_document_update,
    rollback_payload, known_media_document,
)


@pytest.fixture
def product():
    # Preserve real shape including Portwell's empty filesize and unknown extension fields.
    return {"id": 5546, "sku": "315003000084", "name": "Produto preservado",
            "description": "Descrição", "images": [{"id": 9}], "regular_price": "125.50",
            "meta_data": [{"id": 88345, "key": KEY, "value": [
                {"label": "Datasheet", "url": "https://legacy.example.test/uploads/painel.pdf",
                 "filename": "painel.pdf", "filesize": "", "custom": {"preserve": [1, "x"]}},
                {"label": "Manual", "url": "https://example.test/manual.pdf", "filename": "manual.pdf", "filesize": "1.09 MB"}]},
                {"id": 999, "key": "private_other_plugin", "value": {"untouched": True}}]}


@pytest.fixture
def addition():
    return {"label": "Desenho 3D", "url": "https://example.test/desenho.zip", "filename": "desenho.zip", "filesize": "635.3 KB"}


def plan(product, additions):
    return prepare_document_update('portwell', 'https://portwell.com.br', product, product['sku'], additions)


class Shop:
    def __init__(self, product, behavior='ok'):
        self.product=deepcopy(product);self.calls=[];self.behavior=behavior

    def handle(self, request):
        self.calls.append(request)
        assert request.url.path == '/wp-json/wc/v3/products/5546'
        assert 'authorization' not in request.headers
        if request.method=='GET':
            return httpx.Response(200,json=deepcopy(self.product))
        assert request.method=='PUT'
        payload=json.loads(request.content)
        assert set(payload)=={'meta_data'} and len(payload['meta_data'])==1
        update=payload['meta_data'][0]
        assert set(update)=={'id','key','value'} and update['id']==88345 and update['key']==KEY
        assert update['value']
        if self.behavior not in ('ignored','error'):
            self.product['meta_data'][0]['value']=update['value']
        if self.behavior=='other_changed': self.product['meta_data'][1]['value']='unexpected'
        if self.behavior=='timeout': raise httpx.ReadTimeout('SECRET echoed',request=request)
        return httpx.Response(403 if self.behavior=='error' else 200,json={'message':'SECRET echoed'})


def test_append_preserves_unknown_fields_empty_size_old_url_order(product, addition):
    before=deepcopy(product);new=plan(product,[addition]);view=preview(new)
    field=new.payload['meta_data'][0]
    assert field['value']==before['meta_data'][0]['value']+[addition]
    assert product==before
    assert view['action']=='append' and view['added']==1 and view['writes_allowed'] is False
    assert 'private_other_plugin' not in json.dumps(view)
    assert not view['payload_is_exact'] and view['redacted_paths']
    assert field['value'][0]['filesize']==''
    product['meta_data'][0]['value'].clear()
    assert len(new.before['meta_data'][0]['value'])==2
    copy=new.payload;copy['meta_data'].clear()
    assert len(new.payload['meta_data'])==1


def test_no_additions_is_read_only_not_empty_put(product):
    new=plan(product,[]);shop=Shop(product)
    result=simulate_update(new,transport=httpx.MockTransport(shop.handle))
    assert result['status']=='no_op' and not result['put_sent']
    assert [r.method for r in shop.calls]==['GET']
    assert preview(new)['payload']['meta_data'][0]['value']


def test_identical_url_and_four_fields_dedup_with_extra_fields(product, addition):
    existing={k:v for k,v in product['meta_data'][0]['value'][1].items()}
    new=plan(product,[existing,addition,addition])
    assert new.added==1 and new.duplicates==2
    assert len(new.payload['meta_data'][0]['value'])==3


@pytest.mark.parametrize('field',['label','filename','filesize'])
def test_same_url_conflicting_metadata_blocks(product,field):
    candidate=deepcopy(product['meta_data'][0]['value'][1])
    candidate[field]='2 KB' if field=='filesize' else 'Different'
    with pytest.raises(ValueError,match='divergentes'):plan(product,[candidate])


@pytest.mark.parametrize('field',['label','filename'])
def test_same_name_new_url_requires_content_reconciliation(product,addition,field):
    addition[field]=product['meta_data'][0]['value'][1][field]
    with pytest.raises(ValueError,match='reconciliação|comprovado'):plan(product,[addition])


@pytest.mark.parametrize('fault',['empty','duplicate','no_id','string','absent'])
def test_invalid_metadata_never_builds_destructive_payload(product,addition,fault):
    if fault=='empty':product['meta_data'][0]['value']=[]
    if fault=='duplicate':product['meta_data'].append(deepcopy(product['meta_data'][0]))
    if fault=='no_id':product['meta_data'][0].pop('id')
    if fault=='string':product['meta_data'][0]['value']='a:1:{serialized}'
    if fault=='absent':product['meta_data'].pop(0)
    with pytest.raises(ValueError):plan(product,[addition])


@pytest.mark.parametrize('fault',['empty','file','url','signed','http','media_id','missing','size'])
def test_new_documents_require_real_complete_values(product,addition,fault):
    if fault=='empty':addition['label']=''
    if fault=='file':addition['filename']='../file.pdf'
    if fault=='url':addition['url']='https://user:SECRET@example.test/doc.pdf'
    if fault=='signed':addition['url']+='?token=SECRET'
    if fault=='http':addition['url']='http://example.test/doc.pdf'
    if fault=='media_id':addition['id']=45
    if fault=='missing':addition.pop('filesize')
    if fault=='size':addition['filesize']=''
    with pytest.raises(ValueError) as error:plan(product,[addition])
    assert 'SECRET' not in str(error.value)


def test_sensitive_preview_redaction_does_not_mutate_payload(product,addition):
    product['meta_data'][0]['value'][0]['url']='https://user:PRIVATE@example.test/doc?token=SECRET#fragment'
    new=plan(product,[addition]);view=preview(new)
    assert 'PRIVATE' not in json.dumps(view) and 'SECRET' not in json.dumps(view)
    assert not view['payload_is_exact']
    assert 'SECRET' in new.payload['meta_data'][0]['value'][0]['url']
    assert 'SECRET' not in repr(new)


def test_exact_preview_with_observed_four_fields_only(product,addition):
    product['meta_data'][0]['value'][0].pop('custom')
    new=plan(product,[addition]);view=preview(new)
    assert view['payload_is_exact'] and view['payload']==new.payload and not view['redacted_paths']


def test_transport_gate_blocks_even_production_enabled(product,addition):
    new=plan(product,[addition])
    for transport in (None,object()):
        with pytest.raises(ValueError,match='bloqueada'):simulate_update(new,transport=transport)


@pytest.mark.parametrize('behavior',['ok','ignored','error','timeout','other_changed'])
def test_put_get_verification_not_status_only_and_no_retry(product,addition,behavior):
    new=plan(product,[addition]);shop=Shop(product,behavior)
    result=simulate_update(new,transport=httpx.MockTransport(shop.handle))
    assert [r.method for r in shop.calls]==['GET','PUT','GET']
    assert result['status']==('rest_verified' if behavior=='ok' else 'reconciliation_required')
    assert 'SECRET' not in json.dumps(result)
    assert result['verification']['frontend_verified'] is False
    assert result['verification']['plugin_recognition']=='not_verified'
    if behavior=='timeout':assert result['verification']['metadata_persisted']


def test_concurrent_change_prevents_put(product,addition):
    new=plan(product,[addition]);shop=Shop(product)
    shop.product['meta_data'][0]['value'][0]['label']='Concurrent edit'
    with pytest.raises(ValueError,match='alterado'):simulate_update(new,transport=httpx.MockTransport(shop.handle))
    assert [r.method for r in shop.calls]==['GET']


def test_exact_identity_and_rollback_preserve_previous_state(product,addition):
    new=plan(product,[addition]);shop=Shop(product)
    simulate_update(new,transport=httpx.MockTransport(shop.handle))
    rollback=rollback_payload(new,shop.product)
    assert rollback=={'meta_data':[product['meta_data'][0]]}
    shop.product['meta_data'][0]['value'].append(addition)
    with pytest.raises(ValueError,match='divergente'):rollback_payload(new,shop.product)
    observed=deepcopy(product);observed['sku']='OTHER'
    assert not verify_document_update(new,observed)['verified']


def test_media_id_resolves_to_source_url_not_invented_wcda_id(addition):
    result=known_media_document(addition['label'],addition['filename'],addition['filesize'],{'id':123,'source_url':addition['url']})
    assert result==addition and 'id' not in result
    with pytest.raises(ValueError):known_media_document('label','name.pdf','1 KB',{'source_url':addition['url']})


def test_exact_sku_required(product,addition):
    with pytest.raises(ValueError,match='SKU'):prepare_document_update('portwell','https://portwell.com.br',product,'wrong',[addition])


@pytest.mark.parametrize('company,product_id,sku,meta_id,sizes',[
    ('choice',6260,'codmaterialaqui',92930,['421.1 KB']),
    ('sag',5667,'230010000099',103183,['635.3 KB','1.09 MB','86.7 KB','1.22 MB']),
    ('portwell',5546,'315003000084',88345,['']),
])
def test_three_observed_store_shapes(company,product_id,sku,meta_id,sizes,addition):
    # IDs, counts and field types observed through GET; file names/URLs are synthetic.
    original={'id':product_id,'sku':sku,'meta_data':[{'id':meta_id,'key':KEY,'value':[
        {'label':f'Documento {i}','url':f'https://example.test/{i}.pdf',
         'filename':f'{i}.pdf','filesize':size} for i,size in enumerate(sizes)]}]}
    new=prepare_document_update(company,'https://example.test',original,sku,[addition])
    observed=deepcopy(original)
    calls=[]
    def handler(request):
        calls.append(request.method)
        assert request.url.path==f'/wp-json/wc/v3/products/{product_id}'
        if request.method=='PUT':
            body=json.loads(request.content)
            assert set(body)=={'meta_data'} and body['meta_data'][0]['id']==meta_id
            observed['meta_data']=body['meta_data']
        return httpx.Response(200,json=observed)
    result=simulate_update(new,transport=httpx.MockTransport(handler))
    assert result['status']=='rest_verified' and calls==['GET','PUT','GET']
    assert observed['meta_data'][0]['value'][:-1]==original['meta_data'][0]['value']
    assert rollback_payload(new,observed)=={'meta_data':original['meta_data']}
