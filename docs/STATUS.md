# Status do projeto

Atualizado em: 2026-09-24 (America/Sao_Paulo)

O marco inicial `0.1.0` está resumido em [`docs/ENTREGA_0_1.md`](ENTREGA_0_1.md). O repositório de código é `https://github.com/Arthur-A-C/PRM`; esta pasta `C:\PRM` acompanha `origin/main`. Arquivos de configuração local, planilhas e backups são ignorados pelo Git.

Em 24/09/2026, o tratamento dos três catálogos, o comparador `lexical-v1.3`, as melhorias do dashboard e esta documentação foram publicados em `origin/main`. As planilhas e o backup permaneceram apenas no ambiente local.

## Fase atual

- **Fase 0 — Inspeção: concluída.** Arquivos e banco foram inventariados antes das alterações.
- **Fase 1 — Fundação: concluída.** Conexão, migrações, autenticação, sessão, CSRF, páginas protegidas, API e logout foram validados no PostgreSQL real. Há um gestor permanente criado pelo operador.
- **Fase 2 — Dados: núcleo XLSX e enriquecimento concluídos.** Os três lotes reais estão publicados e reconciliados. As três saídas tratadas foram associadas às ofertas sem substituir as fontes brutas. Importações futuras recebem tratamento local antes da comparação; enriquecimento externo completo requer nova saída tratada. CSV, upload web e job com progresso permanecem no backlog.
- **Fase 3 — Exploração: em andamento.** Dashboard, catálogo paginado e correspondência automática integral operam com dados reais. Revisão humana, painel lateral e gráficos adicionais são as próximas entregas.

## Regra de foco das empresas

- `company_type = nossa` é a regra central de prioridade; nomes específicos não são usados para ordenar.
- Portwell e Choice Tech aparecem antes das concorrentes em menus, filtros, indicadores, listas, catálogo e comparador.
- A ordenação continua válida quando novas empresas forem cadastradas: primeiro todas as empresas próprias, depois as demais, e nome em ordem alfabética dentro de cada grupo.
- O critério e sua motivação estão registrados em `docs/decisions/0002-prioridade-empresas-proprias.md`.

## Ambiente e banco verificados

- Python 3.14.7 em `.venv`; `pip check` sem dependências quebradas.
- PostgreSQL 18.6 em `127.0.0.1:5432`, banco `prm_mvp`, usuário de aplicação `prm_app`.
- Migração atual: `20260923_0007`; 20 tabelas públicas.
- `GET /api/v1/health/ready` retorna HTTP 200 com banco disponível.
- `.env` existe localmente e está ignorado; nenhum segredo foi registrado em logs ou documentos.
- A política local bloqueia execução direta de `.ps1`; os comandos equivalentes por `.venv\Scripts\python.exe -m ...` funcionam.
- O Git fornecido pelo GitHub Desktop não está no `PATH`, mas seu executável está disponível. O primeiro commit local (`86589ee`, 23/09/2026) foi publicado em `origin/main` pelo operador. A pasta de teste `PRM-git` foi removida em 23/09/2026.
- Backup anterior à migração 0003: `data/backups/prm_mvp_20260922_134439.dump`, 24.481.003 bytes, formato custom/gzip e inventário de 91 entradas validado com `pg_restore --list`.
- Backup anterior à migração 0004: `data/backups/prm_mvp_20260922_152540.dump`, 24.487.679 bytes, SHA-256 `d2c5ad575cb37da52ac05047baa8ff552f7ab6d911a3f3ff88f229cf3b217717` e 107 entradas validadas.
- Backup anterior à migração 0005: `data/backups/prm_mvp_20260922_155755.dump`, 24.497.125 bytes, SHA-256 `5ec6d8544670e66c40850cc08e16dd96bf1e0f2e8bd9f8cb696246d884425443` e 127 entradas validadas.
- Backup anterior à migração 0006: `data/backups/prm_mvp_20260922_163117.dump`, 24.574.218 bytes, SHA-256 `99bf75f5cb896ca0e2601768cb9417df22b37d08da85877ad117090a9a2baa49` e 147 entradas validadas.
- Backup anterior à migração 0007: `data/backups/prm_mvp_20260923_150939.dump`, 24.634.582 bytes, SHA-256 `7dd9ac098cbcdf97b8fe9cc88b484bbe7ae2eb2cda67bef68b7316ac394bea8a`, inventário validado por `pg_restore --list`.

## Catálogos publicados e reconciliados

| Empresa | Tipo | Linhas brutas | Ofertas | Rejeitadas | Observação |
|---|---|---:|---:|---:|---|
| Choice Tech | nossa | 16.894 | 16.886 | 8 | nome ausente |
| Portwell | nossa | 10.961 | 10.955 | 6 | 3 códigos repetidos e 3 linhas sem nome; uma também sem código |
| Eco Automação | concorrente | 7.945 | 7.945 | 0 | código `4574` preservado e excluído analiticamente |
| **Total** |  | **35.800** | **35.786** | **14** | todas as linhas permanecem auditáveis |

Contagens persistidas: 3 lotes, 35.786 observações, 43.731 registros de preço, 419 marcas canônicas, 2 aliases de marca e 67 categorias sugeridas. Disponibilidade e preços reconciliam com as prévias documentadas em `DADOS.md`.

A reimportação do XLSX Eco retornou o mesmo `import_id` com `idempotent=true`. Permaneceram exatamente 3 lotes, 35.786 ofertas, 35.800 linhas, 35.786 observações e 43.731 preços.

As saídas tratadas `Produtos-Choice.xlsx`, `Produtos-Portwell.xlsx` e `Produtos-ECO.xlsx` foram copiadas para `data/imports/treated/` com SHA-256 conferido. `offer_enrichments` contém 35.786 registros: Choice 16.886, Portwell 10.955 e Eco 7.945. A associação por empresa/código externo ignorou apenas linhas inválidas ou duplicadas dos XLSX tratados. Os originais, registros de preço, lotes e observações ficaram inalterados. As planilhas locais são ignoradas pelo Git; detalhes e hashes estão em `DADOS.md`.

## Exploração implementada

- Dashboard real: 35.785 ofertas no recorte analítico, 3 empresas, 419 marcas canônicas e 92,0% com ao menos uma modalidade de preço válida. Todas as 35.785 ofertas do recorte têm enriquecimento publicado pelo pipeline; a oferta Eco excluída também tem enriquecimento, mas não entra no dashboard.
- Choice Tech e Portwell aparecem antes da análise concorrente, com total tratado por empresa: Choice 16.886, Portwell 10.955 e Eco 7.944 no recorte. O percentual e a origem do tratamento aparecem nas versões HTML e API.
- Qualidade no recorte: 168 ofertas sem marca e 2.859 sem preço válido; o registro Eco excluído não entra nesses indicadores.
- Catálogo paginado em 24/48 itens, com busca, filtros combináveis, faixa por modalidade e origem auditável.
- O comparador principal deixou de exigir seleção manual e analisa o catálogo concorrente completo contra todas as ofertas das empresas próprias.
- O algoritmo local `lexical-v1.3` usa índice invertido, códigos/modelos, nome, marca canônica, descrição, família e atributos tratados; versão, limiares, pontuação e motivos ficam auditáveis. Conflitos técnicos críticos impedem sugestão forte.
- A migração `0006` criou aliases de marca revisáveis. `ELFIN` e `NEW ELFIN SRL` agora apontam para a marca canônica `ELFIN`, enquanto os valores brutos das 14 e 447 ofertas continuam preservados.
- Execução vigente Eco `lexical-v1.3` (`c73639ef-78ba-4683-8e0d-236a9ecfeda4`): 7.944 produtos contra 27.841 ofertas próprias; 11 sugestões fortes (0,14%), 467 produtos com candidato principal e 897 pares persistidos. Não há confirmações humanas.
- Uma sugestão forte agora exige pontuação mínima e ao menos um modelo/código compartilhado. Igualdade de marca melhora a pontuação, mas não promove sozinha produtos parecidos.
- Histórico preservado: 6 execuções e 4.063 pares candidatos no total; cada recálculo insere uma execução auditável e até 3 pares por produto concorrente.
- Dashboard e página de análise exibem gráfico de cobertura. O dashboard agora separa 11 sugestões fortes, 456 candidatos e 7.477 produtos Eco sem candidato; distribui as sugestões fortes entre Choice (11) e Portwell (0). Nossas empresas e produtos aparecem primeiro nos pares e listas.
- O dashboard mostra até três sugestões fortes com preços de ambos os lados; comparação entre modalidades distintas é explicitamente nominal. A lista integral e os motivos continuam no comparador.
- A análise usa nosso preço preferencial como base para indicar `acima`, `abaixo` ou `igual`. Modalidades diferentes recebem alerta explícito de comparação nominal, não margem.
- Novas publicações pelo importador disparam o recálculo de todas as concorrentes, salvo `--skip-matching` explícito.
- Comparações podem ser salvas com estado inicial `nao_avaliado`; vendedor acessa as próprias e gestor pode consultar todas da organização.
- Ofertas excluídas analiticamente não podem ser comparadas ou salvas por vendedor.
- APIs autenticadas para dashboard, opções, produtos, prévia, criação e consulta de comparações.

## Testes e verificações

- `python -m compileall -q app scripts tests`: aprovado.
- `python -m pytest -q`: **21 aprovados**; duas advertências de depreciação da combinação FastAPI/Starlette instalada, sem falha funcional.
- Migrações aplicadas transacionalmente; Alembic e inspeção do esquema confirmam a revisão 0007.
- `alembic check` confirma que os modelos SQLAlchemy e o esquema real não têm operações pendentes.
- Smoke autenticado no PostgreSQL real cobre dashboard, catálogo, identidade, gráfico, cobertura integral, ordem das empresas próprias, preços, alias `ELFIN`/`NEW ELFIN SRL` e logout.
- O smoke remove somente seu usuário e sessão temporários. O gestor permanente permanece; a contagem de sessões ativas varia com os logins e o smoke não altera execuções de correspondência.
- `scripts/reconcile_catalogs.py` reproduz as contagens persistidas sem alterar dados e lista empresas próprias primeiro.
- `scripts.smoke_web` passou no PostgreSQL real: dashboard, catálogo, API, análise global, totais de tratamento reconciliados, sugestões por empresa própria, preços e logout. `pip check` passou.
- Consultas medidas anteriormente na máquina atual: dashboard 207 ms; primeira página 79 ms; busca “SIEMENS” 741 ms; filtro empresas próprias+estoque 39 ms; venda entre 100–500 BRL 358 ms. São amostras, não p95 nem promessa de produção.

## Limites conhecidos

- O fluxo humano para confirmar/rejeitar candidatos ainda não foi implementado; portanto a cobertura atual é algorítmica e tem zero confirmações humanas.
- O cadastro e a revisão de novos aliases de marca ainda não têm interface. Novos casos devem entrar de forma controlada na tabela `brand_aliases`; variantes não são fundidas automaticamente apenas por semelhança textual.
- Portwell/Choice usam `venda`, enquanto Eco usa principalmente `pix`/`cartao`. O indicador entre modalidades distintas é nominal e aparece sinalizado; condições comerciais não são inferidas.
- O tratamento automático dos XLSX brutos extrai apenas sinais locais verificáveis. Para a mesma riqueza de atributos das três saídas atuais, é preciso gerar e publicar nova planilha tratada; o ZIP externo não é executado no servidor e seus cruzamentos pré-calculados não são importados.
- CSV, upload web, job persistido/progresso e tela de histórico/qualidade seguem pendentes na Fase 2 complementar.
- Painel lateral de detalhes e Chart.js seguem pendentes na Fase 3.
- A moeda BRL foi escolhida operacionalmente; não é campo declarado nas planilhas. `Data Cadastro` não é tratada como data de observação.
- Serviço Windows, teste de restauração e acesso em rede ainda não foram configurados. O backup foi criado e validado, mas não restaurado em banco separado.

## Próxima tarefa concreta

1. Revisar manualmente as 11 sugestões fortes e uma amostra dos 456 outros produtos com candidato, para calibrar falsos positivos e atributos técnicos críticos.
2. Criar fila de revisão humana para confirmar/rejeitar candidatos, com justificativa e revisor.
3. Criar tela para sugerir, revisar e administrar aliases de marca, e usar atributos revisados para elevar a qualidade do pareamento.
4. Mover o recálculo demorado para job persistido com progresso, mantendo o acionamento automático após importação.
5. Completar painel lateral e a parte complementar de importação/qualidade.
