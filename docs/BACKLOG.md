# Backlog

Atualizado em **23/10/2026**, com base no código até `179c702`. Itens marcados representam implementação no repositório; implantação e homologação dependem das evidências em [STATUS.md](STATUS.md). As fases da especificação original permanecem como referência histórica.

## Catálogos, dados e comparação

- [x] Importação XLSX auditável, prévia, validação, idempotência e enriquecimento legado por empresa/código.
- [x] Pareador legado `lexical-v1.3`, aliases de marca e análises históricas preservados.
- [x] Snapshots refinados para Choice, Portwell, Eco e Dimensional, com evidências, conflitos, qualidade e separação do histórico.
- [x] Dashboard e comparador baseados no snapshot atual, sem reutilizar resultados do pareador legado como cobertura atual.
- [x] Busca, filtros, paginação e seleção de 2–8 produtos para comparação direta.
- [x] Dicionário canônico de atributos e comparação por característica, incluindo USB, memória, armazenamento e sistema operacional.
- [ ] Homologar matching técnico da base refinada: taxonomia, perfis por família, recuperação de candidatos, atributos críticos e validação estratificada por responsável técnico.
- [ ] Entregar cobertura estrita/ampliada e oportunidades com evidências; revisar falsos sinais de lacuna e falsos negativos antes de uso comercial.
- [ ] Implementar revisão humana versionada de equivalência sugerida/confirmada/rejeitada e matriz de requisitos técnicos.
- [ ] Ampliar parsers e fontes mediante amostras revisadas; generalizar configuração de empresas e manifesto de qualidade upstream.
- [ ] Administrar aliases de marca pela interface e permitir revisão de atributos.
- [ ] Completar catálogo complementar, estados `not_seen_in_latest_batch` e importação de decisões.
- [ ] Evoluir a importação de catálogos com fluxo CSV genérico, jobs e progresso; os CSVs especializados e filas de datasheets/cadastro já existentes não concluem esse item.
- [ ] Implementar painel lateral de detalhes e contagens de facetas independentes do próprio filtro; reavaliar a antiga proposta de Chart.js frente aos gráficos atuais.

Referências: [Catálogos refinados](CATALOGOS_REFINADOS.md), [Normalização](NORMALIZACAO_ATRIBUTOS.md), [Dados](DADOS.md).

## Digitalização, imagens e lojas

- [x] Datasheets individuais e em lote por empresa; entrada por pastas SKU/CIGAM, ZIP e modo CSV/PDFs, inventário e exportações.
- [x] Envio de pastas/arquivos pelo navegador, com progresso, cancelamento e retomada.
- [x] Resolução de imagens com backup de originais e restauração.
- [x] Cadastro comercial por CSV e diagnósticos autenticados WooCommerce/WordPress somente leitura.
- [x] Publicação de imagens/documentos em produtos existentes com Dry Run, aprovação, journal e releitura.
- [x] Remoção com backup verificado, permissões por loja, liberações de uso único, auditoria e restauração.
- [x] Autonomia do desenvolvedor na remoção; gestor continua sujeito a outro aprovador e permissões por loja.
- [ ] Homologar escrita de arquivos e reconhecimento WCDA no frontend em ambiente/SKU autorizado, com recuperação verificada.
- [ ] Confirmar implantação e configuração dos workers e liberações por fluxo no servidor de destino; código disponível não comprova loja habilitada.
- [ ] Concluir revisão técnica/visual de datasheets com arquivos reais e registrar limites de edição das imagens.

Referências: [Datasheets](DATASHEETS_EM_LOTE.md), [Publicação](PUBLICACAO_EM_LOTE.md), [WCDA](WCDA_HOMOLOGACAO.md), [Remoção](REMOCAO_ARQUIVOS.md).

## Reuniões, Cards, Planner e pauta semanal

- [x] Pipeline textual/áudio local, jobs persistentes, propostas com evidências e publicação transacional de cards.
- [x] Revisão em lote, controle de versão, comentários internos e atribuição de responsáveis.
- [x] Planner, calendário e alertas internos idempotentes por atribuição/prazo.
- [x] Pauta semanal com GitHub/Planner, evidências de situação, edição humana preservada, aprovação, histórico e PDF.
- [x] Agendamento da pauta pelo worker de alertas e redação opcional por IA com validação e fallback por regras.
- [ ] Validar o fluxo completo de reuniões com material real revisado, acessibilidade, concorrência PostgreSQL e casos adversariais de áudio.
- [ ] Homologar contrato real de IA com modelo configurado e medir qualidade; implementar divisão/consolidação de textos acima do limite.
- [ ] Mesclar/dividir propostas e completar interação de arraste acessível com recuperação de conflitos.
- [ ] Implementar retenção/exclusão autorizada de originais, paginação de revisões/segmentos e reutilização de ASR entre jobs.
- [ ] Completar fixtures distribuídas, contrato formal de exportação e avaliar HTML offline autorizado previsto na especificação original.
- [ ] Confirmar aplicação da migração final, acesso ao GitHub, configuração da pauta, worker de alertas e geração agendada no destino.
- [ ] Manter `PRM_DEPLOYED_COMMIT` coerente com a implantação; sem essa evidência, a pauta não deve marcar código como implantado.

Referências: [Reuniões](REUNIOES_PLANNER.md), [Cards e alertas](CARDS_E_ALERTAS.md), [Pauta semanal](PAUTA_SEMANAL.md).

## Acesso, infraestrutura e operação

- [x] Login, sessões, CSRF, isolamento organizacional e perfis desenvolvedor/gestor/vendedor.
- [x] Criação administrativa de contas e restrição de módulos por perfil.
- [x] Docker isolado, volumes persistentes e serviços de cadastro, remoção, datasheets e alertas.
- [x] CI com testes, build, migrações, health, persistência e varredura de segredos; sem deploy automático.
- [x] Migração `20261023_0014` unifica os ramos de remoção e pauta semanal.
- [ ] Preparar este checkout com Python 3.14 e dependências ou Docker e executar a suíte da base integrada; registrar falhas/skips sem reutilizar números históricos como resultado atual.
- [ ] Conferir revisão aplicada e saúde do servidor, filas e workers antes da próxima implantação.
- [ ] Verificar enforcement real das proteções da main; arquivos de configuração e auditorias históricas não comprovam o estado atual no GitHub.
- [ ] Completar aceite operacional de backup/restauração, desempenho e inicialização automática no ambiente escolhido.

Referências: [Docker](DOCKER.md), [Infraestrutura — registro histórico](INFRA_STATUS.md), [Operação Windows](OPERACAO_WINDOWS.md), [Colaboração](../CONTRIBUTING.md).
