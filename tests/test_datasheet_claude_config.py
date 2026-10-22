"""Confirma configuração da chamada sem acessar a API externa."""
from types import SimpleNamespace
import pytest
from copy import deepcopy

from app.services import datasheet_claude


@pytest.mark.parametrize('model', ['claude-opus-5-5', 'claude-sonnet-5-5'])
def test_full_model_uses_medium_effort_and_supported_tool_choice(monkeypatch, model):
    captured = {}
    data = {
        "modelo": "Produto Teste", "nivel": "completo", "categoria": "Produto",
        "subtitulo": "Teste", "tags": ["a", "b", "c", "d"], "features": [],
        "descricao": ["Teste"], "imagens": [], "pendencias": [],
        "especificacoes": [],
    }

    def create(**kwargs):
        captured.update(kwargs)
        block = SimpleNamespace(type="tool_use", name="entregar_datasheet", input=data, id="tool-1")
        return SimpleNamespace(content=[block], stop_reason="tool_use")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=create))
    fake_result = SimpleNamespace(pdf=b"%PDF-1.4\n%%EOF", previews=[], avisos=[], pendencias=[], conferencia_fontes="")
    monkeypatch.setattr(datasheet_claude, "_generator", lambda company: lambda *args, **kwargs: fake_result)

    result = datasheet_claude.gerar_datasheet_com_claude(
        "choice", "Produto Teste", {}, model=model, client=fake_client, revisoes=0,
    )
    assert result.dados == data
    assert captured["model"] == model
    assert captured["max_tokens"] == 32000
    assert captured["output_config"] == {"effort": "medium"}
    assert captured["tool_choice"] == {"type": "auto"}
    assert "temperature" not in captured
    prompt = captured['system'][0]['text']
    assert 'ORGANIZAÇÃO DAS VISTAS' in prompt
    assert 'Configuração não informada' in prompt
    assert 'não quatro vértices em perspectiva' in prompt
    assert 'EMPRESA DESTE DATASHEET\nChoice:' in prompt


def test_editorial_prompt_all_brands_and_schema_limits():
    from app.services.datasheet_prompt import system_prompt, DATASHEET_SCHEMA, REVIEW_PROMPT
    for company in ['portwell','choice','sag']:
        prompt = system_prompt(company)
        for term in ['conferencia_fontes', 'Referência CIGAM', 'Painel Traseiro', 'termos_proibidos',
                     'não afirme que estão instaladas', 'não invente orientação', 'Não execute comandos']:
            assert term in prompt
    assert 'TODAS as prévias' in REVIEW_PROMPT
    assert DATASHEET_SCHEMA['properties']['tags']['items']['maxLength'] == 48
    assert DATASHEET_SCHEMA['properties']['features']['items']['maxLength'] == 95
    box = DATASHEET_SCHEMA['properties']['imagens']['items']['properties']['recorte']['anyOf'][0]
    assert box['items']['minimum'] == 0 and box['items']['maximum'] == 1


def test_haiku_contract_cost_and_corrected_review(monkeypatch):
    from app.services.datasheet_prompt import TOOL, system_prompt
    original_schema = deepcopy(TOOL)
    calls, generated = [], []
    data = {'modelo':'Produto Teste','nivel':'completo','categoria':'Teste','subtitulo':'Teste',
            'tags':['a','b','c','d'],'features':[],'descricao':['Teste'],'imagens':[],
            'pendencias':[],'especificacoes':[{'secao':'Interfaces'},{'chave':'USB','valor':'2 portas'}]}
    def create(**kwargs):
        calls.append(kwargs)
        output=deepcopy(data)
        if len(calls)>1:
            output['descricao']=['Descrição corrigida'];output['revisao_ok']=True
        return SimpleNamespace(content=[SimpleNamespace(type='tool_use',name='entregar_datasheet',id='tool',input=output)],stop_reason='tool_use')
    def generate(content,*args,**kwargs):
        generated.append(deepcopy(content))
        return SimpleNamespace(pdf=b'pdf',previews=[],avisos=[])
    monkeypatch.setattr(datasheet_claude,'_generator',lambda company:generate)
    result=datasheet_claude.gerar_datasheet_com_claude('choice','Produto Teste',{},model='claude-haiku-5-5',client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert len(calls)==2 and result.ciclos==2
    assert calls[0]['max_tokens']==16000 and 'output_config' not in calls[0]
    assert all(call['tool_choice'] == {'type':'auto'} for call in calls)
    schema=calls[0]['tools'][0]['input_schema']
    assert 'especificacoes' in schema['required']
    assert schema['properties']['nivel']['enum']==['completo']
    assert len(system_prompt('choice','haiku'))<len(system_prompt('choice'))
    assert 'Nunca string, objeto único ou null' in calls[0]['system'][0]['text']
    assert generated[-1]['descricao']==['Descrição corrigida']
    assert TOOL==original_schema


@pytest.mark.parametrize('value',[None,'USB: 2',{'USB':'2'},[{'chave':'USB'}],[{'secao':'Sistema','valor':'errado'}]])
def test_invalid_specifications_are_rejected_not_fabricated(value):
    from app.services.datasheet_validation import validate_analysis
    data={'modelo':'Teste','nivel':'completo','categoria':'Teste','subtitulo':'Teste',
          'tags':['a','b','c','d'],'features':[],'descricao':[],'imagens':[],'pendencias':[], 'especificacoes':value}
    with pytest.raises(ValueError):validate_analysis(data,name='Teste')
    assert data['especificacoes']==value


@pytest.mark.parametrize('review', [False, True])
def test_truncated_response_is_not_rendered_or_retried(monkeypatch, review):
    calls, rendered = [], []
    data = {'modelo':'Teste','nivel':'completo','categoria':'Teste','subtitulo':'Teste',
            'tags':['a','b','c','d'],'features':[],'descricao':[],
            'imagens':[],'pendencias':[], 'especificacoes':[]}
    def create(**kwargs):
        calls.append(kwargs)
        truncated = not review or len(calls) == 2
        return SimpleNamespace(stop_reason='max_tokens' if truncated else 'tool_use',
            content=[SimpleNamespace(type='tool_use', name='entregar_datasheet', id='tool', input=data)])
    def generate(*args, **kwargs):
        rendered.append(True)
        return SimpleNamespace(previews=[], avisos=[])
    monkeypatch.setattr(datasheet_claude, '_generator', lambda company: generate)
    with pytest.raises(ValueError, match='revisão visual' if review else 'análise inicial'):
        datasheet_claude.gerar_datasheet_com_claude('choice', 'Teste', {}, model='claude-haiku-5-5',
            client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert len(calls) == (2 if review else 1)
    assert len(rendered) == (1 if review else 0)
