# Extração e identificação por IDs

CLI independente `extrair_e_identificar.py`, integrada ao **motor atual** `datasheet_core.py` e geradores Portwell/Choice/SAG. Não altera o botão de Digitalização nem o banco. Não é necessário o `gerar_datasheet.py` externo.

Na raiz do projeto:

```powershell
.venv/Scripts/python.exe extrair_e_identificar.py --pdf fabricante.pdf --nome "WEBS-2412-1235UGW11I" --marca portwell --config "i5-1235U, 8 GB, SSD 240 GB" --fotos "fotos/*.jpg" --fabricante "NomeDoFabricante"
```

Teste sem cobrança:

```powershell
.venv/Scripts/python.exe extrair_e_identificar.py --pdf fabricante.pdf --nome WEBS-2412 --marca portwell --somente-extrair
```

Chave: `ANTHROPIC_API_KEY` do ambiente ou `.env`. Modelo padrão explícito `claude-haiku-5-5`; `--model` permite outro ID. Não muda automaticamente para Opus. Uma chamada inicial e no máximo duas correções, sem retries de transporte. Correções recebem apenas JSON e erros, não reenvio do PDF/fotos. Ferramenta forçada `emitir_datasheet`, validação local: tool use sozinho não garante validade.

Cada execução cria `trabalho/datasheet-<id>/` para preservar arquivos anteriores:

```text
inventario.json
extracao.json
fotos/F1.png ...
resposta-1.json (e correções, se necessárias)
ds.json
out/<modelo>_Datasheet.pdf
out/preview/01.png ...
out/relatorio.json
```

O inventário registra origem/página/bbox, dimensões, fundo e hash perceptual. Máscara alfa é incorporada, nunca exportada sozinha; imagens pequenas (<200 px), quase uniformes, bboxes inválidas e duplicatas são rejeitadas. Duplica por pHash com distância até 4 e proporção próxima, conservando resolução maior. Recortes vetoriais são heurísticos, com 300 DPI e margem de 10 pt; excluem molduras e uniões excessivamente amplas. Verifique se cotas/títulos não foram incluídos indevidamente. Até 20 imagens, priorizadas por área, são enviadas ao modelo.

No retorno do modelo, imagem aceita **somente id/papel/legenda**. Python preenche arquivo/fundo/remoção de fundo, com marcas e textos vazios. Nenhuma coordenada do modelo é aceita. A saída final mantém o schema do motor atual. Fabricante é inferido conservadoramente por URL/e-mail; nome sem domínio exige `--fabricante` (repetível). Campos de auditoria preservam proveniência e não são impressos. Nome encontrado no texto final bloqueia a gravação do PDF.

Sem o exemplo externo, há exemplo estrutural explicitamente fictício no prompt. `--exemplo caminho/ds.json` aceita um exemplo real fornecido pelo operador; não foi alegada equivalência ao ZIP não enviado.

Páginas quase vazias provocam até duas tentativas locais removendo lateral/detalhe; se persistirem, o aviso permanece. Não há garantia de correção de toda paginação. **Logos/textos dentro das fotos não são apagados por este script**, conforme o contrato solicitado de listas vazias: revisão humana obrigatória. Isso não implementa o OCR/inpaint do pedido anterior, substituído por esta CLI.

Validação: 14 testes direcionados aprovados (extração/deduplicação/máscara/schema/retry e motores anteriores). Extração local executada no PDF WEBS-2412 disponível em Downloads; nenhuma chamada paga ou geração real via Haiku realizada. Ambiente testado: Python 3.14; compatibilidade de execução em Python 3.11 não foi testada nesta máquina. Dependências listadas em `requirements.txt`, incluindo ImageHash e jsonschema.
