# Backlog

## Fase 1 — concluída tecnicamente

- [x] `.env` local configurado sem registrar a senha.
- [x] Banco inicialmente vazio inspecionado; migrações aplicadas e índices conferidos.
- [x] Login, sessão, páginas autenticadas, API e logout validados com usuário temporário removido após o teste.
- [x] Operador criou o primeiro gestor permanente pelo prompt local.

## Fase 2 — dados (em andamento)

- [x] Modelar importações, linhas brutas, marcas, categorias sugeridas, ofertas, observações e preços em nova migração.
- [x] Implementar prévia XLSX, limites de arquivo/linhas e parser decimal brasileiro.
- [x] Implementar publicação transacional e proteção por hash contra reimportação idêntica.
- [x] Executar as migrações e os três lotes no PostgreSQL real; reconciliar contagens persistidas e repetir um lote para provar idempotência integrada.
- [x] Associar as três planilhas previamente tratadas às ofertas existentes sem substituir fontes brutas, com proveniência e hash.
- [x] Tratar automaticamente novos dados brutos antes do pareamento e permitir publicar novas saídas tratadas por empresa/código.
- [ ] Ampliar o tratamento bruto automático para famílias e atributos específicos mediante amostras revisadas; o enriquecimento externo completo ainda requer uma saída tratada.
- [ ] Adicionar fluxo CSV e jobs persistidos com progresso.
- Criar tela de histórico/qualidade e modelo CSV para Portwell/Choice Tech.

## Fase 3 — exploração (em andamento)

- [x] Dashboard com indicadores, empresas, qualidade, disponibilidade e principais marcas.
- [x] Dashboard com cobertura do tratamento por empresa, funil concorrente, distribuição de sugestões pelo portfólio próprio e até três destaques nominais de preço.
- [x] Catálogo paginado de 24/48, busca, filtros por empresa/marca/disponibilidade e preços por modalidade.
- [x] API de detalhes com arquivo, aba, linha e SHA-256 de origem.
- [ ] Painel lateral de detalhes na interface.
- [x] Seleção persistida de 2–4 ofertas (entrega anterior, depois substituída na interface pela análise integral).
- [x] Comparador exploratório com empresas próprias primeiro e persistência `nao_avaliado`.
- [x] Referência explícita, diferença percentual por modalidade compatível e matriz técnica sem equivalência automática.
- [x] Estrutura relacional de definições e valores de atributos com evidência, método e revisão.
- [x] Correspondência automática integral, versionada e auditável entre concorrentes e portfólio próprio.
- [x] Cadastro auditável de aliases de marca e consolidação revisada de `ELFIN`/`NEW ELFIN SRL` com valor bruto preservado.
- [x] Gráfico de cobertura competitiva e posição nominal de preços.
- [x] Comparador `lexical-v1.3` usa família, modelo e atributos tratados; divergências críticas bloqueiam sugestão forte.
- [ ] Interface para sugerir, revisar e administrar novos aliases de marca.
- [ ] Fluxo humano de revisão da equivalência e edição dos atributos.
- [ ] Matriz de requisitos técnicos e fluxo humano de equivalência sugerida/confirmada/rejeitada.
- [ ] Gráficos locais Chart.js e contagens de facetas ignorando a própria faceta.

## Fases seguintes

- Fase 4: cards versionados, ACL, comentários e HTML offline autorizado.
- Fase 5: tarefas, worker PostgreSQL, alertas idempotentes e visão do gestor.
- Fase 6: regressão, desempenho, serviço Windows, backup/restauração e operação.
