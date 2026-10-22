# Reuniões, Cards, Alertas e Planner — implementação em staging

## Estado em 16/10/2026

**Atualização posterior:** mock READ AI disponibilizado no dashboard oficial para gestores da organização, por arquivo privado e endpoint autenticado independente do banco. Servidor local reiniciado e rota confirmada; não houve migração oficial. Sete cards de demonstração são somente leitura, não tarefas publicadas; não entram em indicadores operacionais nem alertas. A visualização apresenta apenas o mock quando as tabelas operacionais não estão disponíveis. Datas 16/09 e 24/09 confirmadas, responsável interno pendente. Para reproduzir: `python -m scripts.publish_meeting_demo --transcript "C:/Users/PW/Downloads/Transcrição READ AI.txt"` (idempotente). Testes do módulo: 28 aprovados. Não confundir esta publicação visual com a homologação do pipeline completo abaixo.

Implementação funcional inicial, **ainda não homologada integralmente conforme a especificação**. Código na pasta oficial `C:\Users\PW\Documents\PRM`. Migração aditiva `20261016_0009` aplicada somente em `prm_pipeline_staging`; `prm_mvp` e catálogos publicados não foram alterados. Nenhum serviço existente foi reiniciado, nenhum push/deploy foi realizado.

As páginas existentes mantêm seus templates, tokens, logos e estilos. As novas seções usam CSS com escopo `meeting-module`. Cards e Meus alertas substituem seus placeholders; Reuniões e Planner entram na navegação; o calendário aparece como seção adicional da Visão geral. Não houve revisão visual automatizada em navegador nesta etapa.

## O que funciona

- Reuniões privadas por organização/curador, entrada textual/TXT UTF-8 e upload privado de áudio. Revisões imutáveis com hash, segmentos e origem; correções geram outra revisão.
- Participantes distintos por nome exato, falantes desconhecidos sem identidade inventada. Confirmação manual de nomes, tipo interno/externo e vínculo com usuário ativo.
- Contrato fechado `config/meetings/extraction.schema.json`, versão 2.0, validação de citações/participantes/dependências e ciclos. Prompt versionado; nenhuma ferramenta de execução é oferecida ao modelo.
- Adaptador Anthropic com consentimento textual, contagem de tokens, limite de contexto e diagnóstico. Respostas inválidas não são publicadas. Não foi executada chamada real de IA nesta etapa.
- Jobs persistidos por etapa, chave idempotente, lease, lock, retry limitado e cancelamento que impede etapas posteriores. Execução abandonada exige retry explícito, evitando cobrança silenciosa. Geração de cards usa JSON validado sem nova chamada de IA.
- Cards de tarefas/eventos com responsável pendente, atribuição individual/em lote, controle de versão, checklist, evidências, edição, aprovação/rejeição e publicação explícita. Lote de atribuição/publicação transacional; links exigem autenticação. Alteração de card aprovado volta à revisão.
- Exportação autorizada JSON/CSV sem transcrição nem citações por padrão; CSV com BOM e neutralização de fórmulas. Impressão/PDF via navegador limitada à seleção visível na página.
- Agenda mensal de sete colunas, até três atividades por dia e botão para expandir, apresentação mobile, filtros, camada opcional de propostas e lista separada sem data. Remarcação pelo formulário do card, não por arraste nesta versão.
- Indicadores apenas de tarefas abertas publicadas: Em dia (8+ dias), Atenção (3–7), Priorizar (0–2), Vencida. Instante vencido hoje é diferente de data sem horário ainda no prazo. Onze intervalos no histograma; rascunhos e sem prazo fora do denominador.
- Alertas internos por responsável e versão de prazo; GET não cria notificações. Conclusão/cancelamento/remarcação resolve avisos anteriores. Salvar prazo inalterado não gera nova versão de notificações. Não há envio de e-mail, convite externo ou integração com calendário externo.

## Exemplo READ AI

Original privado: `C:\Users\PW\Downloads\Transcrição READ AI.txt`, SHA-256 `e87dc87ecdf6e8d5bbc6dbc92996aaeaecdbcded3915acaa1b05696e41bec9f1`. Não incluído no Git.

- Parser: 111 segmentos, 18 de falantes desconhecidos; dois segmentos em 55:22 preservam IDs distintos.
- Datas confirmadas pelo usuário: reunião em **16/09/2026**, próxima reunião em **24/09/2026**. Horário 15h permanece candidato, não confirmado; duração de 40 minutos é estimativa.
- Reunião de staging: `3bf48a11-683a-4bd7-8517-e4aadca9fd66`.
- Sete propostas **simuladas e identificadas como exemplo**, não resultado de chamada real ao Claude: configurador condicional, proposta integrada, oferta de documentação API, consulta ao CTO, materiais/cases, convite e um evento.
- Zero responsáveis internos atribuídos, zero publicações, zero alertas. Não foram criados usuários de teste nem escolhidos responsáveis automaticamente. O gestor existente de staging é apenas curador do registro.
- Para visualizar o evento: abrir Planner, setembro de 2026, marcar “Mostrar propostas datadas”. Os indicadores continuam zerados até publicação de tarefas revisadas.

## Operação e configuração

Executar comandos na raiz real do projeto. O worker usa `PRM_DATABASE_URL` do ambiente, **não escolhe staging automaticamente**. Antes de iniciar um worker/servidor de homologação, usar uma configuração apontando para `prm_pipeline_staging`, sem substituir inadvertidamente o `.env` oficial.

```powershell
.venv/Scripts/python.exe -m scripts.meeting_admin inspect --target staging
.venv/Scripts/python.exe -m scripts.meeting_admin migrate --target staging
.venv/Scripts/python.exe -m scripts.meeting_admin seed-example --target staging --transcript "C:/Users/PW/Downloads/Transcrição READ AI.txt"
.venv/Scripts/python.exe -m scripts.check_meetings_staging
```

Se houver mais de um gestor, `seed-example` exige `--actor UUID`; nenhuma conta é criada. Repetir a importação do exemplo não duplica a reunião. O simulador da API permanece desabilitado por padrão (`PRM_MEETING_ENABLE_FIXTURE=false`) e aceita somente o hash exato da fixture.

Workers, com banco explicitamente configurado:

```powershell
.venv/Scripts/python.exe -m scripts.meeting_worker --stage text
.venv/Scripts/python.exe -m scripts.meeting_worker --stage transcription
.venv/Scripts/python.exe -m scripts.meeting_worker --stage alerts
```

`text` processa análise e geração de cards. `--once` executa uma passagem. PostgreSQL usa advisory lock para evitar dois workers da mesma classe. Não foram instalados serviços de inicialização automática.

Definir `PRM_MEETING_AI_MODEL` com ID válido na conta e `ANTHROPIC_API_KEY` pelo mecanismo existente. O modelo de reuniões não herda implicitamente `DATASHEET_MODEL`. A chave não aparece em logs/documentação. O `.env` existente foi preservado. Os limites ficam em `.env.example`: texto 2 MiB, áudio 250 MiB/4 horas, contexto 100 mil tokens, timeout de ASR 4 horas e memória 4096 MiB.

Scripts independentes: `scripts.transcribe_audio`, `scripts.analyze_transcript`, `scripts.build_cards`; consultar `--help` para entradas. Funções compartilhadas com backend em `meeting_asr.py`, `meeting_pipeline.py`, `meeting_activities.py`.

### Áudio local

Bibliotecas nativas isoladas em `.venv-asr`, sem alterar o ambiente principal:

```powershell
.venv/Scripts/python.exe -m venv .venv-asr
.venv-asr/Scripts/python.exe -m pip install --only-binary=:all: -r requirements-asr.txt
.venv-asr/Scripts/python.exe -m scripts.provision_asr --model small
.venv-asr/Scripts/python.exe -m scripts.transcribe_audio CAMINHO_DO_AUDIO
```

O provisionamento baixa pesos públicos; o processamento do áudio é local e não faz download implícito. `PRM_ASR_PYTHON` pode indicar outro Python compatível; sem configuração, o subprocesso encontra `.venv-asr`. CPU/int8, VAD, dois threads, sem diarização. Memória limitada via Windows Job Object ou RLIMIT_AS no Unix. Modelo é reaproveitado dentro de um processo, mas ainda é carregado novamente a cada subprocesso/job.

Teste real autorizado com voz sintética Microsoft Maria Desktop: Windows/Python 3.14, faster-whisper 1.2.1, CTranslate2 4.8.3, **PyAV 16.1.0**, modelo multilingual `small`, CPU/int8. Áudio de **20,178 s**, cinco segmentos, execução **6,106 s**, compromisso/oferta/correção “duas → três” reconhecidos; sem inferir falantes. Corrigidos PyAV 19 (removeu argumento usado pelo faster-whisper) e leitura de acentos do PowerShell 5. Esse teste não valida qualidade em reuniões reais nem performance em quatro horas de áudio. Não houve chamada de IA a partir desse áudio.

Áudio e modelos em `data/meetings/`, ignorado pelo Git, fora de `app/static`; player autenticado. Política configurável de retenção tem parâmetro reservado, mas **nenhuma purga foi implementada/ativada**: arquivos permanecem até procedimento autorizado. Não assumir expiração automática.

## Verificações realizadas

- Continuação concluída com **208 testes aprovados**, três avisos preexistentes, em 50,20 s (26 testes do módulo). Sintaxe JS e diff aprovados. Oficial inspecionado somente leitura, ainda em `20261009_0008`, sem as tabelas novas.
- Suíte geral: **205 testes aprovados**, três avisos preexistentes, antes do último teste de lote; módulo após inclusão do lote: **24 testes aprovados**.
- Oito rotas do módulo aprovadas contra PostgreSQL staging, em transação somente leitura: usuários, reuniões, detalhe, cards, indicadores, alertas, calendário publicado e calendário com propostas.
- Reconciliados sete rascunhos, evento em 24/09, nenhum responsável atribuído/publicação/alerta.
- Testes de tenant/CSRF, conflito de versões, atribuição, atomicidade de lote, idempotência, evidências, schema inválido, prazos/denominadores, fim exclusivo à meia-noite, exportação sem fórmulas e geração sem recobrar IA.
- Sintaxe JavaScript e `git diff --check` aprovados (avisos de conversão LF/CRLF não são erros).

## Pendências para aceite completo e produção

1. Homologação visual/interativa desktop/mobile, keyboard, seek no áudio real e fluxo autenticado completo; suíte ASR adversarial (silêncio/ruído/corrupção/limites/timeout) e corrida concorrente PostgreSQL.
2. Configurar ID de modelo e executar contrato real limitado com consentimento; medir qualidade em reuniões revisadas. Hoje o exemplo é determinístico/simulado. Texto acima do limite é rejeitado sem truncar: chunking com sobreposição/consolidação ainda não implementado.
3. Mesclar/dividir propostas e arraste acessível com restauração em conflito. Revisão, atribuição e publicação em lote já existem. Comentários independentes, idempotentes e autorizados foram adicionados na continuação, com 26 testes do módulo aprovados; não descartam campos não salvos. A suíte geral anterior à continuação passou com 206 testes.
4. Retenção/exclusão autorizada de originais e auditoria correspondente; preservação byte a byte do TXT com BOM além do hash/texto; reutilização do modelo ASR entre jobs.
5. Limitar/paginar revisões/segmentos e agregações em grande volume; detalhes de reuniões ainda carregam todas as revisões. Contagem de tarefas concluídas por período e configuração dos limiares ainda pendentes.
6. Fixtures JSON válidas/inválidas como arquivos distribuídos e contrato formal JSON Schema da exportação (hoje versão 1.0 documentada no payload e testes).
7. Só após homologação: backup verificado, migração aditiva do oficial, configuração dos workers e escolha explícita do curador do exemplo. Não aplicar downgrade destrutivo: a revisão bloqueia drop de tabelas com dados.

Referências técnicas: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [contratos de ferramentas Claude](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools).
