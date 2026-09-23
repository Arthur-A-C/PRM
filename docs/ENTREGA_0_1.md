# Primeira entrega — PRM 0.1.0

Marco documentado em 23/09/2026. Repositório: [Arthur-A-C/PRM](https://github.com/Arthur-A-C/PRM). Esta página é um retrato da implementação inicial; [STATUS.md](STATUS.md) acompanha a evolução posterior.

## Escopo entregue

| Área | Implementação disponível |
|---|---|
| Fundação | FastAPI, interface Jinja2, PostgreSQL, configuração por `.env`, migrações Alembic `0001` a `0006` |
| Acesso | Gestor individual, senha Argon2, sessão por cookie HttpOnly, proteção CSRF e logout |
| Dados | Importação XLSX com prévia, publicação transacional, rastreio de arquivo/linha, tratamento de linhas rejeitadas e reimportação idempotente |
| Exploração | Dashboard, catálogo paginado, busca, filtros, detalhes e empresas próprias em primeiro plano |
| Comparação | Análise integral do catálogo concorrente, candidatos pontuados, motivos auditáveis, cobertura e referência de preço próprio |
| Marcas | Marca canônica e aliases; `ELFIN` e `NEW ELFIN SRL` consolidadas com o valor original preservado |

O fluxo principal é **planilha → prévia → publicação → ofertas consultáveis → análise de correspondência → revisão futura**. Uma publicação nova aciona o recálculo das correspondências dos concorrentes. O modelo permite persistir comparações exploratórias, mas salvar uma comparação não confirma equivalência.

## Evidência da instalação local

Em 23/09/2026, o banco `prm_mvp` respondeu em PostgreSQL 18.6 com a migração `20260922_0006` aplicada e 19 tabelas públicas. Os três lotes publicados somavam:

| Empresa | Papel | Ofertas |
|---|---|---:|
| Choice Tech | Nossa | 16.886 |
| Portwell | Nossa | 10.955 |
| Eco Automação | Concorrente | 7.945 |
| **Total** |  | **35.786** |

Havia 35.800 linhas brutas, 14 rejeitadas, 43.731 registros de preço, 419 marcas canônicas e 2 aliases. Uma oferta Eco de teste permanece armazenada para auditoria e é excluída das análises; por isso, 7.944 ofertas Eco entram no pareamento.

A execução vigente `lexical-v1.2.1` encontrou 9 sugestões fortes (0,11% de cobertura), 304 candidatos adicionais e 7.631 produtos sem candidato acima do limiar. São resultados do algoritmo, sem confirmações humanas. Os números completos e as regras estão em [Dados](DADOS.md) e [Status](STATUS.md).

## Validação e limites

Em 23/09/2026, `pytest -q` passou com **17 testes**; a conexão e a revisão do banco foram confirmadas por `scripts.check_database`, e as contagens por `scripts.reconcile_catalogs`. O teste autenticado de páginas e API já havia sido executado na etapa de implementação, inclusive para o alias ELFIN. Os dois avisos dos testes são de depreciação em dependências, sem falha funcional observada.

Ainda faltam a revisão humana de equivalência, a interface para administrar aliases, upload web/CSV, processamento assíncrono com progresso e ensaio de restauração do backup. Comparações entre `venda`, `pix` e `cartao` indicam diferença nominal; as condições comerciais não são normalizadas.

## Reproduzir e continuar

Siga o [README](../README.md) para preparar o ambiente, executar migrações, importar as planilhas e rodar os testes. O repositório contém código e documentação; não contém o `.env`, os XLSX, o conteúdo do PostgreSQL ou os dumps locais. Consulte o [Backlog](BACKLOG.md) antes de iniciar a próxima fase e atualize [STATUS.md](STATUS.md) ao concluir cada etapa.
