import io
from copy import deepcopy
from types import SimpleNamespace

import pytest
import pymupdf
from PIL import Image, ImageDraw

from extrair_e_identificar import (extract, valid_bbox, background, trim, tool_schema,
                                   validation_errors, assemble, identify, manufacturer_terms)


def photo(size=(600,400)):
    im=Image.new('RGBA',size,(255,255,255,0))
    draw=ImageDraw.Draw(im)
    draw.rectangle((size[0]*.1,size[1]*.1,size[0]*.9,size[1]*.9),fill=(50,80,100,255))
    draw.ellipse((size[0]*.2,size[1]*.2,size[0]*.5,size[1]*.6),fill='red')
    return im


def png(im):
    buf=io.BytesIO();im.save(buf,format='PNG');return buf.getvalue()


def test_extraction_mask_dedup_and_largest(tmp_path):
    pdf=tmp_path/'source.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_image(pymupdf.Rect(30,30,330,230),stream=png(photo()))
        doc.save(pdf)
    large=tmp_path/'large.png';photo((1200,800)).save(large)
    small=tmp_path/'small.png';photo((100,100)).save(small)
    mono=tmp_path/'mask.png';Image.new('RGB',(300,300),'red').save(mono)
    inventory,_=extract(pdf,[large,small,mono],tmp_path/'result')
    assert len(inventory)==1
    assert inventory[0]['largura']>900
    assert inventory[0]['fundo']=='transparente'
    assert Image.open(tmp_path/'result/fotos/F1.png').mode=='RGBA'


def test_bbox_background_and_manufacturer():
    assert not valid_bbox([1,1,-1,-1],pymupdf.Rect(0,0,600,800))
    assert not valid_bbox([0,0,0,0],pymupdf.Rect(0,0,600,800))
    assert background(photo())=='transparente'
    assert background(Image.new('RGB',(200,200),'white'))=='branco_liso'
    assert trim(photo()).width<600
    assert manufacturer_terms(['www.vendor-example.com contato@vendor-example.com.br'])==['vendor-example']


def data():
    return {'modelo':'Teste','nivel':'completo','categoria':'Industrial','subtitulo':'Produto',
            'tags':['a','b','c','d'],'features':[],'descricao':['Descrição'],
            'especificacoes':[{'chave':'USB','valor':'2'}], 'pendencias':[],
            'imagens':[{'id':'F1','papel':'capa','legenda':'Perspectiva'}]}


def test_schema_rejects_model_coordinates_and_unknown_ids():
    tool=tool_schema('Teste',['F1'])
    good=data();assert not validation_errors(good,tool,['vendor'])
    for change in [{'recorte':[0,0,1,1]},{'arquivo':'evil.png'},{'id':'F999'}]:
        bad=deepcopy(good);bad['imagens'][0].update(change)
        assert validation_errors(bad,tool,['vendor'])
    bad=deepcopy(good);bad['tags'][0]='a'*49
    assert validation_errors(bad,tool,[])
    bad=deepcopy(good);bad['descricao']=['Vendor produto']
    assert validation_errors(bad,tool,['vendor'])
    inventory=[{'id':'F1','arquivo':'F1.png','fundo':'transparente'}]
    final=assemble(good,inventory)
    assert final['imagens'][0]['remover_fundo'] is True
    assert final['imagens'][0]['marcas']==[] and 'id' not in final['imagens'][0]


def test_retry_only_json_and_errors(tmp_path):
    pdf=tmp_path/'p.pdf';pdf.write_bytes(b'%PDF-test')
    (tmp_path/'fotos').mkdir();photo().save(tmp_path/'fotos/F1.png')
    inventory=[{'id':'F1','arquivo':'F1.png','largura':600,'altura':400,'pagina':1}]
    calls=[]
    def create(**kw):
        calls.append(deepcopy(kw));value=data()
        if len(calls)==1:value['imagens'][0]['recorte']=[0,0,1,1]
        return SimpleNamespace(stop_reason='tool_use',content=[SimpleNamespace(type='tool_use',name='emitir_datasheet',input=value)])
    result,count=identify(pdf,inventory,tmp_path,'Teste','choice','',[],SimpleNamespace(messages=SimpleNamespace(create=create)),'haiku')
    assert count==2 and result==data()
    assert calls[0]['tool_choice']=={'type':'tool','name':'emitir_datasheet'}
    assert isinstance(calls[1]['messages'][0]['content'],str)
    assert 'base64' not in calls[1]['messages'][0]['content']
