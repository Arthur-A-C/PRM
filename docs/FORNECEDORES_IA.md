# Fornecedores — Preencher com IA (27/10/2026)

Fluxo obrigatório: **fonte → extração → prévia → revisão humana → selecionar campos → aplicar à ficha**.
A análise nunca grava no fornecedor. Só `POST …/ai/aplicar` grava, e somente as escolhas revisadas.

## Configuração (independente da IA de reuniões/datasheets)

| Variável | Padrão | Uso |
|---|---|---|
| `PRM_SUPPLIER_AI_API_KEY` | vazio | Chave Anthropic própria desta funcionalidade (recomendado). Só no backend. |
| `PRM_SUPPLIER_AI_MODEL` | vazio | ID do modelo. Recomendado `claude-haiku-5-5` (Haiku atual; ID confirmado na documentação da API). Nenhum ID fica no código. |
| `PRM_SUPPLIER_AI_TIMEOUT_SECONDS` | 60 | Timeout por chamada. |
| `PRM_SUPPLIER_AI_MAX_RETRIES` | 2 | Retentativas do SDK (429/5xx/conexão). |
| `PRM_SUPPLIER_AI_ALLOW_SHARED_KEY` | false | `true` = sem chave própria, usa `ANTHROPIC_API_KEY` (mesma conta/faturamento da IA de datasheets). Desligado por padrão. |
| `PRM_SUPPLIER_AI_EFFORT` | low | `effort` enviado ao modelo; vazio = não envia (modelos sem suporte). |
| Limites | ver `.env.example` | máx. páginas (12), bytes/página (1,5 MB), texto/página (12 000), caracteres enviados (60 000), tempo total de coleta (45 s), páginas de documento (30), imagens (4), análises/usuário/hora (30), cache (60 min). |

Sem modelo ou sem chave, o botão informa "IA de fornecedores não configurada" e os endpoints devolvem 503. O fornecedor continua funcionando normalmente.

SDK instalado: `anthropic==1.8.0`. As constantes de modelo desta versão ainda listam apenas `claude-haiku-4-5`, mas o parâmetro `model` aceita qualquer string; `claude-haiku-5-5` é o Haiku atual na documentação da API. Se a conta não tiver acesso a ele, troque somente `PRM_SUPPLIER_AI_MODEL` (ex.: `claude-haiku-4-5`, nesse caso use `PRM_SUPPLIER_AI_EFFORT=` vazio).

## Uso

`/fornecedores` → abrir fornecedor → **✨ Preencher com IA** → escolher:

- **Ler ficha cadastral**: documento já anexado (pastas) ou novo arquivo (salvo em *Ficha cadastral* antes da análise).
- **Buscar no site oficial**: usa o campo Site ou a URL informada.
- **Combinar ficha + site**: as duas fontes; divergências aparecem como conflito.

Também em **Documentos → 📁 Ficha cadastral → arquivo → ✨ Ler com IA**.
Novo fornecedor: o formulário inicial aceita **Site oficial**; depois de criar, use *Preencher com IA*.
(Criar a ficha diretamente a partir da busca fica como próxima etapa.)

## Leitura de ficha

Extração local primeiro (sem OCR quando há texto): PDF (PyMuPDF, por página), DOCX (XML do documento),
XLSX (openpyxl, por aba), XLS (xlrd), CSV/TXT. PDF escaneado (sem texto) e PNG/JPG vão como imagem reduzida
(máx. 1568 px, até 4 páginas) para a visão do modelo; esses valores ficam com confiança no máximo média e
nunca pré-selecionados, pois a evidência não é verificável automaticamente. Upload passou a aceitar `.xls`.

## Busca no site e proteção SSRF (`app/services/supplier_web.py`)

- Somente `http`/`https`, portas 80/443, sem usuário/senha na URL; sem esquema → tenta HTTPS e só então HTTP.
- Bloqueados: localhost, nomes de rede interna (`.local`, `.internal`, nomes sem ponto…), IP literal ou resolvido em
  loopback, RFC1918, link-local/metadata (169.254.169.254), CGNAT, multicast, reservados, IPv6 local e IPv4 mapeado.
  Basta um endereço privado na resposta DNS para bloquear.
- Dupla checagem: antes de cada requisição (início, redirect, link) e **no momento da conexão** (backend httpcore
  que conecta somente ao IP validado — sem janela de DNS rebinding; TLS continua validando o nome).
- Redirects manuais (máx. 5), cada destino revalidado. Sem cookies, credenciais, proxy do ambiente ou cabeçalhos internos.
- Só o mesmo site (domínio inicial e subdomínios). Redes sociais são registradas, nunca visitadas.
- Prioriza home, Contact, About, Company, Locations, Sales, Support, Impressum; limites de páginas, bytes e tempo.

## Extração determinística antes da IA

`mailto:`, `tel:`, links de WhatsApp, JSON-LD schema.org (Organization/LocalBusiness: legalName, name,
telephone, email, address, sameAs), metatags, rodapé (enviado uma vez) e links sociais. Viram sugestões de
alta confiança sem IA e são enviados ao modelo como achados. Ao modelo vai apenas texto limpo (sem HTML/scripts).

## Haiku como extrator

`output_config.format` com JSON Schema **plano** (`API_SCHEMA`: lista `values` com `field` enumerado + `contacts` + `social_links`), convertido localmente para `SCHEMA` (`unflatten`) e validado com `jsonschema` nos dois formatos. O schema aninhado original (uma lista por campo) é recusado pela API com 400 "The compiled grammar is too large". Falhas do provedor são registradas no log e em `supplier_ai_runs.data.diagnostic` (status, tipo, request id, mensagem sem segredos); o usuário vê apenas a mensagem genérica.
Cada valor: `value`, `source_id`, `evidence` (trecho literal), `confidence` (high/medium/low). Campos são listas,
para que fontes divergentes apareçam todas. O prompt proíbe conhecimento externo, adivinhação, CNPJ derivado,
contatos/pessoas/endereços inventados e trata o conteúdo das fontes como dado, não instrução.

Depois da IA, o servidor **descarta** todo valor cuja evidência não esteja literalmente na fonte citada (ou cujo
e-mail/telefone/ID não esteja nela). O total descartado aparece na revisão. CNPJ só para Brasil (ou CNPJ válido);
empresa estrangeira → "Registro empresarial (exterior)"; estado estrangeiro → "Estado/província" (UF só BR).

## Evidência

Cada sugestão guarda `source_type` (`website`/`supplier_document`), `source` (URL ou nome do arquivo),
`document_id`, `page` (número da página do PDF ou nome da aba), `evidence` (≤ 300 caracteres), `verified`, `origin`
(`deterministic`/`ai`). Guardado em `supplier_ai_runs.data` (não no fornecedor).

## Revisão, conflitos e aplicação

- Pré-selecionados apenas campos vazios na ficha, com confiança alta, evidência verificada e sem alerta.
- Valor existente: "Atual / Encontrado" com **Manter atual** (padrão), **Substituir**, **Adicionar como novo contato**
  (e-mail/telefone) ou **Adicionar ao final** (observações). Nada é sobrescrito sem escolha explícita.
- Fontes divergentes (ficha × site): status "Fontes divergentes — escolha"; sem escolha nada é aplicado.
- Contatos: cada e-mail (geral/comercial/financeiro) e cada pessoa vira sugestão separada de `SupplierContact`;
  duplicados (mesmo e-mail/telefone) aparecem desabilitados e são ignorados na aplicação.
- O cliente envia apenas `run_id` + chave + índice da sugestão: valores vêm da prévia armazenada no servidor.
- Concorrência: a prévia guarda os valores atuais; ao aplicar, se algum campo selecionado mudou desde a análise,
  retorna 409 e nada é aplicado. Prévia vale 24 h e só pode ser aplicada uma vez.
- Histórico: evento `ai_fields_applied` — "Dados cadastrais atualizados com auxílio de IA. Fonte: site oficial
  (domínio). N campo(s) aplicado(s). Responsável: nome." Sem chave, prompt ou conteúdo das fontes.

## Auditoria, cache, custo e falhas

Tabela `supplier_ai_runs` (migration `20261027_0016`, aditiva): quem, quando, modelo, tipo de fonte,
documento/domínio, hash da fonte, páginas lidas, tokens de entrada/saída (`usage`), sugestões, campos aplicados.
Prompt completo não é armazenado. Cache: mesmo fornecedor + mesmo hash do conteúdo coletado + mesmo modelo em até
60 min reaproveita a extração (o site é sempre recoletado; conteúdo mudou ⇒ nova chamada).
Falha/timeout/indisponibilidade/JSON inválido: 502 "Não foi possível analisar esta fonte. Nenhum dado foi alterado.",
execução registrada como `failed`, botão permite tentar de novo. Logs registram só o tipo do erro.

## API

| Método | Caminho | Efeito |
|---|---|---|
| GET | `/api/v1/fornecedores/{id}/ai/status` | IA configurada? |
| POST | `/api/v1/fornecedores/{id}/ai/analisar-site` `{url?}` | prévia |
| POST | `/api/v1/fornecedores/{id}/ai/analisar-documento` `{document_id}` | prévia |
| POST | `/api/v1/fornecedores/{id}/ai/analisar-combinado` `{document_id, url?}` | prévia |
| GET | `/api/v1/fornecedores/{id}/ai/execucoes/{run_id}` | reabrir prévia |
| POST | `/api/v1/fornecedores/{id}/ai/aplicar` `{run_id, fields:[{key,choice,action}], contacts:[id], social:[id]}` | grava o selecionado |

Mesmas regras do módulo: `services/suppliers.scope` (organização; vendedor só nos fornecedores de que é responsável;
gestor/desenvolvedor na organização), CSRF em todos os POST, 404 para fornecedor/documento/execução de outro escopo.

## Implantação

1. Backup do PostgreSQL. 2. Imagem nova. 3. `alembic upgrade head` (cria só `supplier_ai_runs`).
4. Definir `PRM_SUPPLIER_AI_API_KEY` e `PRM_SUPPLIER_AI_MODEL=claude-haiku-5-5` no `.env` do servidor.
5. Acrescentar `compose.fornecedores-ia.yaml` após os overlays atuais e recriar somente a API.
   A API precisa de saída para a internet (Anthropic e sites); o overlay adiciona a rede `ingress`.
Rollback: retirar o overlay e voltar a imagem anterior; a tabela nova pode permanecer.

Novos campos opcionais na ficha: país, registro empresarial (exterior), estado/província, celular, WhatsApp,
e-mail comercial, e-mail financeiro, produtos/linhas, moeda, redes sociais.

## Novo fornecedor com IA (cadastro já preenchido)

`/fornecedores` → **✨ Novo fornecedor com IA** (ao lado de **+ Novo fornecedor**, que continua). Modal em etapas:
1. **Fontes**: ficha cadastral (PDF, DOCX, XLSX, XLS, CSV, PNG, JPG) e/ou site oficial → **Analisar e preencher**.
2. **Revisar**: ficha completa editável (empresa, endereço, contato, comercial), com fonte de cada sugestão
   ("Encontrado em: site/página" ou "ficha.pdf — página N"), divergências ficha × site para escolher (e-mail/telefone
   podem virar contato também), contatos e redes com caixas de seleção, responsável, etapa inicial e score inicial.
3. **Cadastrar fornecedor**: cria o card já preenchido na etapa escolhida.

- Nada é criado na análise: o run fica em `supplier_ai_runs` com `supplier_id` vazio (migração `20261027_0017`) e a
  ficha enviada fica em `<PRM_SUPPLIER_STORAGE_DIR>/<org>/_pendentes/` (fechar o modal descarta; sobras expiram em 24 h).
- `POST /api/v1/fornecedores/ai/analisar` (multipart `file`, `url`) → prévia + `duplicates`; `POST …/ai/criar` (escolhas e
  edições; valores revalidados no servidor: e-mail, telefone, URL http/https, CNPJ, tamanhos, responsável, etapa, score);
  `POST …/ai/descartar`.
- Duplicidade na mesma organização: CNPJ, registro exterior e domínio do site bloqueiam (409); nome normalizado
  (sem sufixos como Ltda/Limited) avisa e permite continuar. Rechecada dentro de lock na criação; se o equivalente foi
  criado depois da análise: "Este fornecedor foi cadastrado enquanto você revisava a análise."
- Criação em uma transação: Supplier + contatos (primeiro como principal) + ficha anexada em Documentos › Ficha cadastral
  (nome, MIME, tamanho, SHA-256, quem enviou e quando) + histórico `supplier_created_ai` (fontes, campos aplicados e
  editados manualmente, contatos, responsável) + vínculo do run. Falha ⇒ rollback e a ficha volta para pendentes.
- A origem de cada campo fica registrada: `ia`, `editado` (valor sugerido alterado) ou `manual`.
