# Arquitetura

## Decisão vigente

Monólito modular FastAPI no mesmo domínio da interface Jinja2. PostgreSQL é o único armazenamento operacional. Não há Redis, Node.js, IA ou n8n no caminho crítico.

## Módulos atuais

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
- `app/routers/`: API versionada, health checks e páginas HTML.
- `migrations/`: evolução aditiva do esquema por Alembic.
- `scripts/`: entrada operacional explícita para Windows.
- `scripts/import_pipeline_enrichment.py`: prévia e publicação dos atributos tratados, associados por empresa e código externo.

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
