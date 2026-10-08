"""Confirma configuração da chamada sem acessar a API externa."""
from types import SimpleNamespace

from app.services import datasheet_claude


def test_opus_55_uses_medium_effort_and_supported_tool_choice(monkeypatch):
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
        "choice", "Produto Teste", {}, model="claude-opus-5-5", client=fake_client, revisoes=0,
    )
    assert result.dados == data
    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_config"] == {"effort": "medium"}
    assert captured["tool_choice"] == {"type": "auto"}
    assert "temperature" not in captured
