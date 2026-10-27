# Arquitetura

## Visão consolidada — 27/10/2026

O PRM permanece um monólito modular FastAPI/Jinja2. Routers tratam HTTP, services concentram regras e integrações, models/repositories persistem no PostgreSQL e quatro workers processam cadastro, remoção, datasheets e alertas. Filas e journals operacionais baseados em SQLite vivem em volumes/diretórios compartilhados apenas entre a API e seu worker correspondente.

```text
Navegador -> gateway/FastAPI -> routers -> services -> PostgreSQL
                                      |-> filas SQLite -> workers
                                      |-> WooCommerce/WordPress (fluxos autorizados)
                                      |-> Anthropic (módulos configurados)
```

Módulos funcionais atuais:

- identidade: autenticação, sessões, CSRF, usuários, organizações e níveis de acesso;
- reuniões: transcrição, planner, cards, responsáveis, alertas e pauta semanal;
- digitalização: produto individual, lotes, datasheets, resolução de imagens e SVG;
- lojas: diagnóstico, cadastro, publicação e remoção com Dry Run, backup, auditoria e releitura;
- catálogos: importação, ofertas, origem interna/concorrente, publicação, snapshots, comparador e visão geral;
- fornecedores: Kanban, ficha, contatos, tarefas, documentos, histórico, responsável e enriquecimento opcional por IA;
- operações: health checks, auditorias e painéis de atividade.

As URLs existentes e a separação por organização são contratos. A consolidação não moveu arquivos nem alterou schema apenas por estética.

## Fluxo oficial de catálogos

```text
CSV/XLS/XLSX
  -> prévia e mapeamento
  -> CatalogImport / ImportRow
  -> Offer + observações, preços, atributos e enriquecimentos
  -> revisão/publicação explícita
  -> RefinedCatalogRun + RefinedCatalogItem (snapshot oficial)
  -> Catálogos / Comparador / Visão Geral
```

`Company.company_type` distingue nossa base (`nossa`) da concorrência. A identidade da oferta inclui a empresa de origem, portanto SKUs iguais de Choice, Portwell e concorrentes não colidem. Um snapshot anterior é arquivado somente quando a nova publicação é válida; a publicação exige dados internos e concorrentes e usa controle de versão para impedir aprovação obsoleta.

## Decisões de manutenção

- Os serviços críticos de digitalização e lojas permanecem separados; seus nomes semelhantes representam etapas de negócio distintas.
- Datasheets, reuniões e fornecedores mantêm clientes/configurações Anthropic independentes. Uma futura fábrica compartilhada pode centralizar timeout, retry e sanitização, mas não deve misturar prompts, modelos ou métricas.
- Routers grandes (`meetings`, `supplier_ai`) e services grandes (`store_file_removal`, `store_registration_jobs`, `supplier_ai`, `weekly_agenda`) são candidatos a extração gradual, sempre mantendo URLs e testes de contrato.
- Overlays funcionais antigos permanecem documentados até haver comparação comprovada da configuração Compose e plano de rollback.

## Decisão vigente

Monólito modular FastAPI no mesmo domínio da interface Jinja2. PostgreSQL é o único armazenamento operacional. Não há Redis, Node.js, IA ou n8n no caminho crítico.

## Módulos atuais

Desde 09/10/2026, a análise atual usa snapshots refinados separados das ofertas legadas, descritos em [CATALOGOS_REFINADOS.md](CATALOGOS_REFINADOS.md). `refined_catalog.py` ingere/audita os quatro adaptadores em streaming; `refined_catalog_database.py` persiste/publica por organização. A migração `20261009_0008` adiciona três tabelas sem modificar ofertas antigas. Cadastros e evidências de atributos ficam em JSONB; variantes/resoluções técnicas relacionais e o novo motor ainda estão pendentes. `/catalogos` lê o snapshot publicado; `view=legacy` preserva o fluxo anterior. As seções antigas abaixo descrevem a arquitetura legada e não significam que a comparação Dimensional foi homologada.

- `app/config.py`: configuração tipada, com `.env` local e prefixo `PRM_`.
- `app/db.py`: criação tardia do engine PostgreSQL e sessões curtas por requisição.
- `app/models/`: modelo relacional SQLAlchemy.
- `app/services/`: autenticação, senhas e tokens sem dependência da camada HTTP.
- `app/services/catalog_import.py`: leitura XLSX sequencial, prévia validada e publicação transacional.
- `app/services/catalog_treatment.py`: tratamento determinístico de futuros dados brutos e leitura segura dos campos das planilhas já tratadas.
- `app/repositories/catalog.py`: consultas, filtros, ordenação com empresas próprias primeiro e prévia do comparador.
- `app/repositories/comparisons.py`: persistência ordenada de comparações exploratórias.
- `app/services/catalog_matching.py`: normalização, recuperação por índice invertido e pontuação lexical sem serviço externo.
- `app/repositories/matching.py`: cobertura global, pares sugeridos e análise de preços da execução mais recente.
- `app/services/catalog_gaps.py` e `app/repositories/matching.py`: agregação de ofertas concorrentes sem candidato em sinais de marca e família, com exemplos e paginação, sem persistência ou migração adicional.
- `app/routers/`: API versionada, health checks e páginas HTML.
- `migrations/`: evolução aditiva do esquema por Alembic.
- `scripts/`: entrada operacional explícita para Windows.
- `scripts/import_pipeline_enrichment.py`: prévia e publicação dos atributos tratados, associados por empresa e código externo.
- `app/services/dimensional_csv.py`, `scripts/import_dimensional_staging.py` e `app/services/dimensional_dashboard.py`: leitura CSV incremental, carga atômica no PostgreSQL de staging e consulta somente leitura de sua reconciliação na visão geral. O banco oficial não recebe ofertas Dimensional nessa etapa.

## Isolamento da Dimensional

`prm_mvp` continua sendo o banco operacional. `prm_pipeline_staging` foi inicializado a partir de backup verificado e contém, além da base existente, o lote Dimensional. O importador exige que a configuração principal aponte para `prm_mvp`, troca **somente o nome do banco** para `prm_pipeline_staging`, valida o hash fixado do CSV e usa uma transação para todos os 77.965 SKUs. Repetição do mesmo hash é idempotente. Uma nova revisão da mesma empresa é recusada até existir fluxo de atualização/revisão.

O esquema atual foi reutilizado sem migração: `catalog_imports` guarda origem/hash, `import_rows` preserva os 20 campos e linhas físicas, `offers` guarda a identidade empresa+SKU, `offer_observations` registra disponibilidade declarada sem quantidade confiável e `offer_prices` separa preço anunciado de referência. Moeda `XXX`, data nula e unidade ausente impedem interpretação como condição comercial conhecida. As 3.790 afirmações técnicas continuam **propostas de simulação**, sem resolução/homologação persistida. O painel de staging não se mistura aos filtros, preços comparáveis ou métricas de cobertura oficiais.

## Fluxo de autenticação

O login valida o hash Argon2 e cria token e CSRF aleatórios. Somente SHA-256 desses segredos é persistido. O navegador recebe o token de sessão em cookie HttpOnly, SameSite=Lax; o cookie deve usar `Secure=true` quando servido por HTTPS. Logout revoga a sessão no banco e valida CSRF. Não há senha padrão.

## Limites atuais

As entidades de catálogo estão na migração `20260922_0002`. O importador mantém a linha bruta em JSONB, mas campos usados em filtros e preços ficam normalizados. A transação só torna o lote visível após concluir; o mesmo hash por empresa é único. O processo web inicia sem banco para permitir `live`, mas rotas persistentes retornam indisponibilidade até `PRM_DATABASE_URL` ser configurada.

A migração `20260922_0003` adiciona comparações e itens. O status inicial é sempre `nao_avaliado`; salvar uma seleção não declara equivalência. A ordem dos itens persistidos já coloca empresas próprias antes das demais.

A migração `20260922_0004` adiciona a oferta de referência à comparação e as tabelas `attribute_definitions` e `offer_attributes`. Valores tipados, unidade, evidência, método e revisão ficam normalizados; ausência permanece nula. A matriz também apresenta campos declarados diretamente no catálogo, mas não os promove a especificações certificadas.

A migração `20260922_0005` adiciona `catalog_match_runs` e `catalog_matches`. Cada execução registra versão e parâmetros; cada candidato preserva pontuação, ordem, fatores explicativos e estado de revisão. O processamento é local e usa índice invertido para evitar o produto cartesiano completo entre catálogos.

A migração `20260922_0006` adiciona `brand_aliases`, com origem e estado de revisão por organização. O importador resolve aliases antes de criar marcas e preserva o texto original em `offers.brand_raw`. O matcher usa a marca canônica na pontuação; a API expõe separadamente os nomes canônico e bruto para auditoria. A primeira consolidação revisada unifica `NEW ELFIN SRL` em `ELFIN` sem alterar a origem declarada das ofertas.

A migração `20260923_0007` adiciona `offer_enrichments`. A oferta mantém sua fonte e preços originais; o enriquecimento guarda família, modelo, códigos de busca, atributos e proveniência separadamente. A importação bruta trata cada oferta nova ou alterada na mesma transação, antes de disparar a correspondência. Uma planilha externa já tratada pode substituir somente essa camada por código externo, com validação de cobertura e SHA-256. O matcher `lexical-v1.3` utiliza os sinais tratados de ambas as partes, registra motivos e penaliza incompatibilidades técnicas críticas. Não executamos scripts externos do ZIP nem importamos seus cruzamentos previamente calculados.

O dashboard agrega `offer_enrichments` por empresa sobre o recorte analítico e separa a origem `pipeline` do tratamento de regra. O relatório da última execução agrupa apenas relações principais `confirmado`/`sugerido` pelas empresas próprias; o funil mantém candidatos separados da cobertura forte. Até três pares fortes são carregados com preços para destaque, reutilizando o cálculo nominal do comparador e sem declarar margem quando as modalidades diferem.

O relatório de lacunas lê a mesma execução concluída do pareador. Oferta concorrente ativa e não excluída só entra se não tiver par principal em estado `candidato`, `sugerido` ou `confirmado`; uma relação rejeitada não a retira do universo a investigar. A marca é comparada pelo ID canônico e a família por rótulo tratado exato, com ambas as dimensões contadas separadamente. A consulta é somente de leitura e sempre limitada à organização autenticada. A interface oferece grupos principais, todas as opções em seletores e listagem paginada por grupo. Um grupo sem marca ou família correspondente não é uma lacuna confirmada: qualidade de cadastro, classificação e falso negativo do matcher ainda exigem revisão.

A busca do catálogo combina termos com E e campos com OU, escapando caracteres especiais de `ILIKE`; consulta tanto campos originais quanto marca canônica e enriquecimento tratado por subconsultas correlacionadas. O filtro de família usa `offer_enrichments.family_group`. Preço usa a modalidade válida mais recente para filtrar, sempre com escopo da organização e sem alterar dados. A página HTML e a API compartilham `CatalogFilters` e `list_offers`; 100 itens é o padrão, com limite máximo opcional de 200.
