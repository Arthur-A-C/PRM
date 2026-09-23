# Changelog

## Documentação do marco 0.1.0 — 2026-09-23

- README ampliado para apresentar a aplicação, preparar o ambiente Windows, importar catálogos, verificar o banco e localizar a documentação técnica.
- Retrato da primeira entrega registrado em `docs/ENTREGA_0_1.md`; `docs/STATUS.md` atualizado para continuidade após a publicação no GitHub.

## 0.1.0 — 2026-09-22

- Inventário do ambiente e reconciliação da planilha Eco Automação.
- Fundação FastAPI com configuração por ambiente, health checks e shell visual responsivo.
- Modelos e migração inicial para organizações, usuários, sessões e empresas.
- Login individual com hash Argon2, token de sessão armazenado somente como hash, cookie HttpOnly e proteção CSRF no logout.
- Scripts PowerShell para migração, criação segura do primeiro gestor e execução local.
- Testes iniciais de segurança, liveness, readiness e página de login.
- Migração `20260922_0002` para marcas, categorias sugeridas, importações, linhas brutas, ofertas, observações e preços normalizados.
- Importador XLSX com detecção de cabeçalho, limites de segurança, prévia, três mapeamentos reais e publicação transacional/idempotente.
- Classificação corrigida: Portwell e Choice Tech são empresas próprias; Eco Automação é concorrente.
- Tratamento explícito de preço zero, BackOrder, estoque numérico, códigos repetidos e resíduos HTML.
- Migrações aplicadas ao PostgreSQL 18.6 e três lotes publicados/reconciliados: 35.800 linhas brutas e 35.786 ofertas.
- Reimportação Eco validada como idempotente, sem crescimento de lotes, ofertas, linhas ou observações.
- Dashboard real, catálogo paginado, filtros combináveis, detalhes com origem e APIs autenticadas.
- Smoke test autenticado de dashboard, catálogo, APIs, sessão e logout contra o PostgreSQL real.
- Empresas próprias priorizadas no dashboard, opções, catálogo e comparador; concorrentes agrupadas depois.
- Seleção de 2–4 ofertas persistida no navegador e comparador exploratório com modalidades explícitas.
- Migração `20260922_0003` e API para salvar/consultar comparações com status inicial `nao_avaliado`.
- Backup PostgreSQL custom válido criado e inspecionado antes da migração `0003`.
- Migração `20260922_0004` para referência persistida de preço e atributos técnicos normalizados com origem/revisão.
- Referência de comparação escolhida explicitamente, barras relativas e diferença percentual somente na mesma modalidade e com referência positiva.
- Matriz técnica alinhada por oferta, preservando estados igual, diferente, não informado e incompatível sem inferir equivalência.
- Novo backup custom validado antes da migração `0004`.
- Migração `20260922_0005` para execuções versionadas e candidatos auditáveis de correspondência entre catálogos.
- Seleção manual de 2–4 produtos substituída na interface por análise automática integral do catálogo concorrente.
- Algoritmo `lexical-v1.1` com índice invertido, códigos/modelos, similaridade de nome, marca e filtros contra medidas genéricas.
- Dashboard e comparador agora exibem gráfico de cobertura, candidatos, sugestões fortes e análise nominal de preços.
- Publicações novas pelo importador recalculam automaticamente as correspondências; `--skip-matching` permite operação excepcional.
- Migração `20260922_0006` para aliases de marca auditáveis, com origem, revisão e nome bruto preservado nas ofertas.
- `ELFIN` e `NEW ELFIN SRL` consolidadas sob a marca canônica `ELFIN`; importador, API, interface e relatório passam a usar a mesma resolução.
- Matcher `lexical-v1.2.1` passa a comparar marcas canônicas e exige modelo/código compartilhado para sugestões fortes, evitando promover coincidências apenas pelo nome da marca e descrição genérica.
