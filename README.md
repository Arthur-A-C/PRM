# PRM

Product Relationship Manager: aplicação interna do grupo SAG para inteligência de catálogos, digitalização de produtos, operações de arquivos nas lojas e colaboração da equipe. Reúne Choice Tech, Portwell e SAG, com análise de concorrentes como Eco Automação e Dimensional.

## Estado atual — 23/10/2026

A base de código revisada é o commit `179c702`, que inclui os PRs de remoção em produção e pauta semanal. A versão declarada da API ainda é `0.1.0`; o [marco da primeira entrega](docs/ENTREGA_0_1.md) é um registro histórico, não o escopo completo atual. Consulte [Status](docs/STATUS.md) para evidências e limites e [Backlog](docs/BACKLOG.md) para pendências.

**Implementado não significa implantado:** a migração mais recente no repositório é `20261023_0014`. A revisão aplicada no servidor, os workers ativos e a habilitação das lojas precisam ser conferidos no ambiente de destino.

## Funcionalidades implementadas

| Área | Escopo e documentação |
|---|---|
| Catálogos atuais | [Snapshots refinados](docs/CATALOGOS_REFINADOS.md) de Portwell, Choice, Eco e Dimensional, busca, filtros, procedência, qualidade e histórico preservado |
| Comparação | Seleção de 2–8 produtos, matriz de preços e características, [normalização de atributos](docs/NORMALIZACAO_ATRIBUTOS.md) e interpretação de memória, armazenamento, USB e sistema operacional |
| Dashboard | Centro operacional com filtros, indicadores de digitalização e inteligência do portfólio baseada no snapshot atual; [workspace visual](docs/WORKSPACE_VISUAL.md) |
| Digitalização | Datasheets por empresa, [lotes por pastas SKU/CIGAM ou CSV](docs/DATASHEETS_EM_LOTE.md), inventário, fila persistente e exportação de PDFs, análises e fontes |
| Arquivos e imagens | Envio de pastas pelo navegador com progresso/retomada; [resolução de imagens](docs/RESOLUCAO_IMAGENS.md) para 1500 × 1500 px com backup e restauração |
| Cadastro e lojas | Fluxo CSV de dados comerciais; [diagnóstico WooCommerce/WordPress](docs/INTEGRACOES_LOJAS.md), [cadastro via API de arquivos](docs/CADASTRO_API_STAGING.md) e [publicação em lote](docs/PUBLICACAO_EM_LOTE.md) com Dry Run, aprovação e releitura |
| Remoção | [Desvinculação de fotos/documentos](docs/REMOCAO_ARQUIVOS.md) com permissões por loja, backup verificado, auditoria e restauração; não exclui a mídia da biblioteca |
| Colaboração | [Reuniões e Planner](docs/REUNIOES_PLANNER.md), revisão e comentários em cards, atribuição e [alertas internos](docs/CARDS_E_ALERTAS.md) |
| Pauta semanal | [GitHub + Planner](docs/PAUTA_SEMANAL.md), situação baseada em evidências, redação opcional por IA, edição, aprovação, histórico, PDF e agendamento pelo worker de alertas |
| Acesso | [Contas e perfis](docs/NIVEIS_DE_ACESSO.md), sessões, isolamento por organização e acesso restrito do vendedor; remoção possui regras distintas para gestor e desenvolvedor |

A base refinada publicada em 09/10/2026 registrou **89.693 registros e 500.016 observações de atributos**. São contagens históricas da carga documentada, não uma consulta ao banco nesta revisão. Dashboard e comparador usam o snapshot atual; o pareador legado `lexical-v1.3`, importações XLSX e enriquecimento do pipeline permanecem no código e no histórico.

**Matching técnico e cobertura competitiva da base refinada ainda dependem de homologação.** Coincidências de atributos ou presença na mesma família não confirmam equivalência comercial. O funil legado não deve ser interpretado como resultado da nova base.

A escrita de arquivos nas lojas depende das liberações do respectivo fluxo e da homologação descrita nos guias, incluindo o reconhecimento dos [documentos WCDA](docs/WCDA_HOMOLOGACAO.md). Remoção em produção tem trava própria, HTTPS, permissões e confirmações; sua implementação não comprova ativação em uma loja.

## Arquitetura e execução

Backend Python/FastAPI, SQLAlchemy e PostgreSQL, migrações Alembic, interface Jinja2 com CSS/JavaScript e API `/api/v1`. Há filas persistentes e workers separados para os fluxos operacionais; iniciar apenas o servidor web não inicia todos os processamentos.

O [ambiente Docker](docs/DOCKER.md) usa a porta **8001** por padrão, PostgreSQL e volumes isolados, com serviços para cadastro, remoção, datasheets e alertas. Não migra automaticamente os dados Windows nem faz deploy de produção. Consulte os [resultados históricos da infraestrutura](docs/INFRA_STATUS.md) e o [fluxo de colaboração](CONTRIBUTING.md).

## Executar localmente no Windows

Requisitos: Python 3.14, PostgreSQL e acesso à pasta do projeto. O banco operacional é PostgreSQL; o pgAdmin é apenas uma ferramenta de administração. Catálogos e comparação não exigem chave de IA nem n8n. Recursos de geração/análise por IA exigem configuração própria; áudio local usa dependências e modelos separados, conforme os guias dos módulos.

No PowerShell, a partir da raiz do repositório:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite **somente o `.env` local** com a URL e a senha do seu banco. Não compartilhe nem publique esse arquivo. Em um ambiente novo, crie o banco e o usuário PostgreSQL antes da migração; em um ambiente existente, confira a URL para reutilizar o banco correto.

```powershell
.\.venv\Scripts\python.exe -m scripts.check_database
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.create_manager
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`scripts.check_database` confirma a conexão inclusive antes da primeira migração. `scripts.create_manager` é interativo e deve ser executado somente para criar um novo gestor. Abra `http://127.0.0.1:8000` para entrar. A API interativa fica em `http://127.0.0.1:8000/docs`.

Se sua política do PowerShell permitir, há atalhos em `scripts/*.ps1`. Os comandos acima funcionam sem executar arquivos `.ps1`.

## Carregar os catálogos

Para a base atual, siga o fluxo de snapshots em [Catálogos refinados](docs/CATALOGOS_REFINADOS.md). Os comandos abaixo pertencem ao fluxo XLSX e ao enriquecimento legado; não publicam nem homologam automaticamente o snapshot refinado.

Os arquivos originais são dados locais e não acompanham o repositório. Coloque em `data/imports/` os arquivos `produtos_ecoautomacao.xlsx`, `produtos-portwell.xlsx` e `produtos-choice.xlsx`. Para cada empresa, faça a prévia antes da publicação:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_catalog --company eco-automacao
.\.venv\Scripts\python.exe -m scripts.import_catalog --company eco-automacao --commit
```

Repita com `--company portwell` e `--company choice-tech`. A publicação nova recalcula as correspondências dos concorrentes. Se precisar executar essa análise separadamente:

```powershell
.\.venv\Scripts\python.exe -m scripts.analyze_catalog_matches --company eco-automacao --commit
```

Sem `--commit`, esses comandos fazem uma prévia e não gravam o lote ou uma nova análise. Detalhes sobre formato, regras e contagens das planilhas estão em [Dados](docs/DADOS.md).

Para aproveitar arquivos já tratados pelo pipeline, mantenha os XLSX originais em `data/imports/` e coloque `Produtos-Choice.xlsx`, `Produtos-Portwell.xlsx` e `Produtos-ECO.xlsx` em `data/imports/treated/`. Após publicar os lotes originais, execute a prévia e a associação por código externo:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_pipeline_enrichment --company choice-tech
.\.venv\Scripts\python.exe -m scripts.import_pipeline_enrichment --company choice-tech --commit --skip-matching
.\.venv\Scripts\python.exe -m scripts.import_pipeline_enrichment --company portwell --commit --skip-matching
.\.venv\Scripts\python.exe -m scripts.import_pipeline_enrichment --company eco-automacao --commit
```

O último comando recalcula a análise; sem `--commit`, a operação é apenas uma prévia. Para qualquer importação futura de dados brutos, o tratamento automático ocorre antes da comparação. Quando houver uma nova saída tratada do pipeline, publique-a com esse mesmo comando para incorporar seus atributos adicionais. O ZIP externo não é executado pela aplicação; veja os limites em [Dados](docs/DADOS.md).

## Verificações

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m scripts.reconcile_catalogs
```

A CI configurada verifica dependências, compilação/importação, pytest, build Docker, migrações, health, persistência e segredos. O registro de 22/10/2026 do PR #4 informa **630 testes aprovados, 26 ignorados e 1 aviso**; esse resultado antecede a integração da pauta semanal e não valida sozinho o commit atual.

Na revisão local de 23/10/2026, os **243 arquivos Python** de aplicação, scripts, Docker, migrações e testes foram analisados sintaticamente sem erros; existem **52 arquivos de testes**. A suíte não foi executada: o checkout não tinha `.env`/`.venv`, o Python disponível era 3.15 sem pytest e o daemon Docker estava indisponível. Banco, interface e implantação não foram validados nessa revisão. O ambiente de referência do projeto e da CI é Python 3.14.

Use `alembic heads` para consultar a revisão disponível (`20261023_0014`) e `alembic current` para a revisão efetivamente aplicada. A reconciliação acima pertence ao catálogo legado; para snapshots atuais, siga as verificações do guia de catálogos refinados.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Primeira entrega](docs/ENTREGA_0_1.md) | Escopo, evidências e limites do marco `0.1.0` |
| [Status](docs/STATUS.md) | Estado atual, contagens, verificações e próxima tarefa |
| [Arquitetura](docs/ARQUITETURA.md) | Módulos e decisões de persistência |
| [API](docs/API.md) | Rotas, autenticação e semântica das respostas |
| [Dados](docs/DADOS.md) | Fontes, importação, marcas e correspondência |
| [Comparação normalizada](docs/COMPARACAO_NORMALIZADA.md) | Auditoria dos novos CSVs/XLSX, metodologia, limites e regeneração do retrato |
| [Operação no Windows](docs/OPERACAO_WINDOWS.md) | Execução local, backup e limites de implantação |
| [Backlog](docs/BACKLOG.md) | Implementações e pendências por módulo |
| [Changelog](CHANGELOG.md) | Histórico funcional da versão |
| [Especificação original](PRM_ESPECIFICACAO_CODEX.md) | Objetivo e fases planejadas |

## Versionamento e dados locais

O código, as migrações, os testes e a documentação são versionados no GitHub. O [.gitignore](.gitignore) exclui `.env`, `.venv`, planilhas em `data/imports/`, exports e backups. O banco PostgreSQL também é local e não é recriado ao clonar o repositório. Antes de publicar uma alteração, confira os arquivos selecionados para o commit; mantenha `docs/STATUS.md` atualizado para facilitar a continuidade entre sessões.
