# Status do projeto

## Cadastro via API: escopo exclusivo de arquivos — 21/10/2026

- **Escopo corrigido:** o módulo só adiciona imagens e documentos WCDA a produtos existentes. Nome, descrições, categorias, atributos, SKU, preço, estoque, status e demais metadados continuam no fluxo CSV. O mapeamento comercial `prepare_content` foi removido do plano de publicação via API; os serviços de descrição, datasheet e CSV (`registration_description`, `registration_woo_csv` etc.) não foram alterados. Versões anteriores copiadas no scratchpad.
- Reaproveitados do trabalho anterior (Codex + etapa de hoje): CSV opcional, SKU pelo nome da pasta/SKU.zip com zeros preservados, ZIP da Geração em Lote, validação de manifesto (SKU/empresa/caminho/hash, arquivo não declarado bloqueia), fila, lease, snapshot privado, isolamento por organização/dono, interface de Dry Run.
- Plano de arquivos (`file_plan`): imagens `upload`/`already_linked` (identidade `prm-<sha256>` no URL)/`duplicate_in_package`/`conflict` (mesmo nome sem identidade, bloqueia); principal atual preservada, troca só com `replace_main` aprovado e a antiga permanece na galeria. Documentos: `add`/`already_linked`/`conflict` (label/arquivo já no WCDA); formatos sem upload homologado (.step/.dwg/.rar…) listados em `ignored`. Modos WCDA: `append`, `first_inclusion` (campo existente e vazio, rollback para `[]`) e `blocked` (ausente, duplicado ou não-lista).
- Executor de staging (`StagingPublisher.execute`): exige aprovação do `dry_run_sha256` exato, Dry Run sem bloqueios e política (`PRM_PUBLISH_*`; as três lojas atuais seguem bloqueadas). Antes de enviar, busca a mídia na biblioteca pela identidade de hash, depois faz upload e um único PUT restrito a `images` + `_wcda_arquivos` (entrada `label/url/filename/filesize` com URL e nome reais retornados pelo WordPress). Por fim relê o produto e confere imagens, documentos e hash de todos os campos comerciais e outros metadados. Falha parcial preserva uploads no journal; recusa explícita permite reenvio; resposta perdida só é aceita pela identidade na biblioteca ou por releitura idêntica. Mudança concorrente antes do PUT aborta sem gravar. Plano de recuperação no journal restaura só as duas chaves e nunca exclui mídia.
- Aprovação individual (`skus`) ou em lote, opt-in `replace_main`, tabela `audit` (preview, aprovação, fila, uploads, PUT, verificação, erro) exibida por item. Confirmação sem aprovação é recusada.
- **Dry Run real Choice 119002000072** (somente GET, 2 requisições, fila isolada): produto 16321, estado `review`. Imagem: `119002000072_variante.jpg` → principal (produto sem imagens). WCDA meta 194572 vazio → primeira inclusão de Datasheet (90.8 KB), Datasheet do fabricante (224.2 KB) e Desenho 3D (2.84 MB). Nenhum campo comercial no plano. Gravação bloqueada: `PRM_PUBLISH_ENABLED=false` e host de produção.
- Verificação: **448 testes aprovados**, 3 avisos conhecidos; 37 testes no novo escopo, com loja simulada Woo+WP (mocks), sem rede. Edge headless 1440/390 px sem overflow/erros. Nenhum POST/PUT/DELETE real, upload ou IA paga. Pendente: staging autorizado, verificação de reconhecimento do plugin WCDA no frontend e autorização explícita para produção.

## Digitalização em Lote sem CSV — 21/10/2026

- Adaptados o parser, upload, fila, worker, ZIP de saída e interface existentes; sem novo pipeline. Identificação por pasta com empresa selecionada, SKU textual exato (zeros preservados), raiz opcional e CSV complementar por correspondência exata. Modo CSV anterior mantido e padrão da API para clientes antigos.
- Prévia de produtos e inventário antes de iniciar, validação de nomes/duplicidades/pastas vazias/extensões/arquivos. PDFs e imagens entram no gerador individual já utilizado pelos lotes; documentos auxiliares 3D/compactados preservados, sem análise ou extração. Downloads incluem análise JSON e fontes por SKU além dos resultados/relatórios anteriores.
- Sem acesso à unidade Z:, leitura de pasta de rede, IA paga, alteração nos bancos de catálogo ou chamadas às lojas nesta etapa. Publicação WooCommerce continua bloqueada; não foi habilitada opção de escrita. Serviço WCDA e fallback Playwright preservados. A homologação Choice SKU 119002000072 continua aguardando arquivos reais gerados e Dry Run específico.
- Operação e limitações em [DATASHEETS_EM_LOTE.md](DATASHEETS_EM_LOTE.md). Reiniciar servidor e worker de lotes para carregar o backend atualizado; nenhum worker pago foi iniciado automaticamente.
- Verificação: **411 testes aprovados**, 3 avisos conhecidos AnyIO/openpyxl. Inclui 63 testes de lote, geração real de PDF nas três marcas com IA simulada nos dois modos, identificação/arquivos/CSV complementar/isolamento. Navegador headless: 1440/768/390/320 px, claro/escuro, sem overflow nem erros de JavaScript; formulário e inventário testados com mocks.

## `_wcda_arquivos`: contrato candidato e Dry Run — 21/10/2026

- Nova auditoria autenticada somente GET: Choice produto 6260/meta 92930 (1 documento), SAG 5667/meta 103183 (4), Portwell 5546/meta 88345 (1), todos HTTP 200. Nas três lojas: lista de objetos `label/url/filename/filesize`. Portwell preserva URL legada e tamanho vazio; Choice tem SKU provisório `codmaterialaqui`, não selecionado para teste.
- Implementado serviço puro de adição preservando lista/ordem/campos originais, deduplicação conservadora, payload apenas do metadado escolhido, prévia sanitizada com hashes, releitura e plano de rollback. Simulador GET/PUT/GET aceita exclusivamente MockTransport; não há liberação de escrita em produção por variável de ambiente.
- CLI `scripts/preview_wcda_update.py` consulta por SKU exato ou ID e apresenta o corpo proposto. Executada realmente para Portwell 5546: `no_op`, nenhuma adição, payload exato sem redactions. Falta documento novo real e autorização específica de loja/SKU para a homologação.
- A orientação da SPLComunic não comprova gravação nem reconhecimento pelo plugin. Não houve PUT, upload, alteração no banco PRM, remoção do Playwright ou mudança de credenciais nesta etapa. Execução real, journal/backup pré-escrita e verificação pública do plugin seguem pendentes; cadastro em lote mantém documentos bloqueados.
- Estrutura, payload real de inspeção, limites, procedimento controlado, rollback e perguntas à SPL: [WCDA_HOMOLOGACAO.md](WCDA_HOMOLOGACAO.md).
- Validação final: **384 testes aprovados**, incluindo 36 do novo serviço; 3 avisos conhecidos (AnyIO/openpyxl). `git diff --check` sem erros de whitespace. Os PUTs dos testes usam mocks, sem acesso às lojas.

## Cards reais, atribuição e alertas — 21/10/2026

- Ativado o módulo persistente no `prm_mvp`: revisão `20261021_0011` (tabelas de reuniões/cards/alertas + merge). Contagens de organizações, usuários e ofertas verificadas antes/depois e preservadas. Nenhum dado copiado do staging, usuário fictício ou card de teste criado no oficial: zero cards/alertas na ativação.
- Atribuição individual diretamente em cada card, além da atribuição em lote existente. Desenvolvedor/gestor seleciona qualquer usuário ativo da mesma organização, com nome e nível (desenvolvedor, gestor, vendedor). Backend mantém CSRF, escopo organizacional, bloqueio de usuário inativo, controle de versão e auditoria. Vendedor continua sem autorização para atribuir a outra pessoa.
- Cards publicados abertos geram alerta de atribuição e, conforme o prazo, proximidade (até 7 dias), hoje ou atraso. Troca de responsável/prazo resolve avisos anteriores; conclusão/cancelamento/inativação encerra avisos; reabertura reativa os elegíveis sem duplicação. Rascunhos e simulações não notificam. Alertas exclusivos do destinatário em `/alertas`, sem e-mail ou WhatsApp.
- Painel de demonstração removido das páginas operacionais (Cards, Planner e Visão geral); arquivos e endpoint restrito do exemplo preservados, sem exclusão. `details.simulation` excluído das consultas operacionais e da geração/listagem de alertas, inclusive para administradores.
- Cards padronizados em 32rem, grade responsiva, ações alinhadas ao rodapé, títulos extensos abreviados com acesso completo pelo detalhe; impressão sem altura fixa. Identidade visual preservada.
- Servidor local recarregado na porta 8000; worker exclusivo `python -m scripts.meeting_worker --stage alerts` iniciado e trava advisory confirmada. Ciclo de 60s, sem chamadas IA/lojas. Processo de alertas separado: após reiniciar o computador, iniciar novamente conforme `docs/CARDS_E_ALERTAS.md`.
- Validação: **348 testes aprovados, 3 avisos**; `node --check` aprovado. Edge isolado com mocks: 24 atribuições, 1440/768/390/320 px, claro/escuro, seis cards sempre com 512px de altura, sem overflow horizontal e sem erros JS. Não houve atribuição fictícia no banco oficial para testar notificações.
- Pendência anterior de migração de reuniões resolvida nesta etapa. A extração IA de reuniões continua sendo uma etapa separada, com consentimento e worker próprios; nenhuma análise foi disparada automaticamente. Guia: `docs/CARDS_E_ALERTAS.md`.

## Níveis de acesso — 21/10/2026

- Implementados `desenvolvedor`, `gestor` (mesmas permissões nesta etapa) e `vendedor` (catálogos/características, reuniões/cards, planner e alertas). Navegação filtrada, redirecionamento inicial do vendedor para catálogos, guard de módulos no backend e procedência de importação restrita. Digitalização, lotes, integração WooCommerce, importações e gestão negados ao vendedor também por acesso direto.
- Três formulários administrativos em `/contas/criar/desenvolvedor`, `/contas/criar/gestor`, `/contas/criar/vendedor`, acessíveis em Gestão. Exigem gestor/desenvolvedor, sessão e CSRF; sem autoinscrição pública privilegiada. Organização herdada do administrador, senhas Argon2, e-mails únicos. Nenhum usuário de teste criado no banco oficial.
- Auditoria `prm_mvp`: somente duas contas ativas e uma organização. IDs `47074f89-6177-416a-a766-34fc6c6ae7d3` e `eb7d404d-08ce-466a-a718-7f536c949db8` promovidos explicitamente de gestor para desenvolvedor; senhas, IDs, organizações e sessões preservados. Constraint e promoção na mesma transação.
- Banco antes em `20261009_0008`, agora em `20261021_0010`. Migração de reuniões `20261016_0009` não executada; merge `20261021_0011` prepara um único head futuro. Não executar upgrade genérico sem considerar essa pendência. Script de auditoria/aplicação: `scripts/configure_access_levels.py`.
- Servidor antigo em 8000 confirmado com 404 nas novas rotas e reiniciado com autorização do usuário. Novo servidor respondeu 200 no login e 303 para login nas três páginas sem sessão. Não houve publicação externa, alteração nas lojas ou remoção do Playwright. `.env` não foi modificado nesta etapa.
- Estado anterior preservado: arquivos não commitados de front-end, reuniões, digitalização e APIs. Integrações das lojas já autenticadas na etapa anterior, mas escrita de documentos `_wcda_arquivos` segue sem homologação; a investigação REST/interpretação pendente não é considerada cadastro completo. Autorização de níveis não libera escrita em produção.
- Guia: `docs/NIVEIS_DE_ACESSO.md`. Suíte: 342 testes aprovados, 3 avisos (depreciação do portal AnyIO e estilos de planilhas). Validações de criação e permissões em banco temporário; formulários reais exigem login do operador.

## Front-end — reformulação das telas de trabalho, 20/10/2026

- Nova camada `app/static/css/prm-ui.css` (tokens `--cc-*`, claro/escuro): botões, campos, selects, uploads, tabelas, progresso, alertas, selos, skeleton, toasts, diálogos e login. Aplicada via `.prm-ui` no `<main>` de todas as páginas fora do dashboard e em `.meeting-module`. O dashboard (Visão geral/Comparador/Importações) não foi alterado.
- Digitalização reescrita em 8 etapas com stepper fixo, estado por etapa e progresso no painel de contexto: produto, imagens, datasheet do fornecedor, especificações extraídas, análise com Claude, revisão, geração e pacote, mais cadastro automatizado. Novos cartões de fotos (principal, mover, girar, remover, ampliar), arrastar e soltar também para PDF/3D, editor de especificações com estados de extração, painel de progresso com tempo decorrido na análise e na geração, revisão estruturada (modelo, categoria, subtítulo, introdução, destaques, características, especificações, dimensões, tabelas, aplicações, uso das imagens, conferência, alertas e dados não encontrados) com aba do JSON editável, e cartão de sucesso do datasheet.
- Regras da Digitalização e do login removidas de `app.css`, `design-system.css`, `prm-v2.css`, `prm-dark.css` e `workspace.css`; `digitalizacao.css` é agora a única fonte e carrega depois de `prm-ui.css` (bloco `page_css` de `base.html`).
- Geração em Lote, Integrações WooCommerce e Cadastro via API redesenhadas no mesmo sistema; status do lote em selos.
- Preservados: todos os IDs, `name` e `data-*` dos templates, endpoints, campos de FormData e cabeçalhos (comparação automática antes/depois). JavaScript alterado apenas na apresentação (`digitalizacao.js`, `datasheet-batches.js`).
- A análise da página usa Claude (o `app/services/qwen.py` não é importado). A extração do PDF é local e sem tradução; a interface não exibe "tradução concluída". As etapas mostradas durante a análise/geração são indicativas; o tempo decorrido é real.
- Verificação: 314 testes; inspeção no Edge headless em 1920/1440/1366/1280/1024/768/390 px, temas claro e escuro, sem rolagem horizontal nem erros de JS; fluxo completo da Digitalização exercitado com APIs interceptadas no navegador (dados fictícios, nenhuma chamada real). Catálogo legado conferido com dados fictícios renderizados pelo template real.

## Organização das integrações — configuração local, 20/10/2026

- Consulta somente leitura ao banco `prm_mvp`: tabela `organizations`, modelo `Organization` em `app/models/identity.py`, contém apenas `Organização PRM`, ID `8cbaed7f-d92d-463c-8045-10bc86b6b160`.
- Os dois usuários ativos são gestores e pertencem a essa organização; as três sessões vigentes também pertencem a ela. Sem acesso ao cookie do navegador não se identifica qual dessas sessões é a do operador, mas não há ambiguidade de organização.
- Configurado apenas `PRM_STORE_ORGANIZATION_ID` no `.env` local, ignorado pelo Git. Validado carregamento e autorização para ambos os usuários, sem revelar credenciais.
- Choice, SAG e Portwell compartilham o vínculo de autorização da organização, com configurações e credenciais independentes por loja. Nenhuma organização ou Company criada; o cadastro de Company da SAG permanece uma questão separada.
- Nenhuma chamada às lojas, escrita no banco, upload ou publicação realizada nesta etapa. Configuração não libera escrita em produção nem substitui homologação.

## Cadastro via API — staging e contrato de documentos pendente, 20/10/2026

- Implementados intake CSV/XLSX/XLSM de SKUs + ZIP de pastas, prévia remota por SKU exato, inventário de arquivos/quantidades existentes, confirmação, fila persistente SQLite, worker em subprocesso, histórico e relatório CSV. Tela `/digitalizacao/cadastro-api`, link em Digitalização. Sem frontend Flask ou automação de navegador para este fluxo.
- Publicador de imagens implementado/testado com mocks: POST mídia, PUT restrito a imagens, principal existente preservada, journal por hash/origem/organização/SKU, releitura, detecção de alteração concorrente, tratamento de resposta incerta e reprocessamento sem retry cego. Produção hard-blocked nas três URLs atuais; execução real requer OUTRA origem de staging e SKU único explicitamente configurados.
- Documentos identificados com labels do legado; PDFs gerados pelo PRM podem entrar no ZIP sem regeração. Qualquer item com documentos fica bloqueado antes de upload enquanto falta contrato PHP de `_wcda_arquivos`. Não há alegação de cadastro completo de documentos.
- Auditoria GET de até cinco produtos/loja: entradas de Choice/SAG têm `label`, `url`, `filename`, `filesize` (strings); sem ID de mídia visível. Amostra Portwell: cinco listas vazias. Plugin/snippet não encontrado no repositório; escrita não testada, armazenamento interno não confirmado.
- Auditoria SELECT do banco: organização única `Organização PRM`, UUID `8cbaed7f-d92d-463c-8045-10bc86b6b160`, com Choice/Portwell/Eco. SAG não cadastrada como Company; nenhum vínculo criado automaticamente. UUID documentado para configuração pelo operador, `.env` preservado.
- Testes: **314 aprovados, 3 avisos** na suíte completa final; `node --check` aprovado e rotas confirmadas no OpenAPI. Uploads/atualizações de teste exclusivamente simulados. A rodada anterior revelou contaminação de variável de ambiente em teste legado: pytest exibiu Consumer Key (não Consumer Secret); teste isolado e comparação redigida para não exibir valores. Nenhuma credencial copiada para documentação ou código.
- Regras de nomes/pastas/labels reaproveitadas, com bloqueios explícitos para ambiguidade e formatos não homologados. Deduplicação cobre envios registrados pelo PRM; acervo anterior com nomes diferentes exige inventário/hashes confiáveis. Sem garantia de CAS atômico no WooCommerce; homologação deve impedir edições concorrentes.
- Nenhum upload/PUT real, alteração no banco oficial, migração, deploy, remoção Playwright, commit ou push. Worker não deixado executando. Documentado em `docs/CADASTRO_API_STAGING.md`; README/API/CHANGELOG/.env.example atualizados.
- Pendências para concluir: obter PHP do plugin, confirmar organização da SAG, fornecer URL/SKU staging, homologar tipos/tamanhos e persistência de documentos, resolver deduplicação de acervo antigo e concorrência no servidor, testar UI em navegador e fluxo staging real. Não desativar Playwright antes desses gates.

## Integrações REST — senhas corrigidas, 20/10/2026 às 13:57 (São Paulo)

- Reexecutado `scripts/check_store_connections.py` com credenciais atualizadas: WooCommerce e WordPress autenticados com HTTP 200 em Choice, SAG e Portwell (6/6). WooCommerce com controle anônimo recusado; WordPress com identidade válida e leitura de mídia em contexto edit permitida nas três.
- Todas as contas WordPress declararam `read`, `upload_files`, `edit_products` e `manage_woocommerce`. Isso não comprova escrita pela chave WooCommerce nem upload efetivo/formatos MIME permitidos.
- `_wcda_arquivos` novamente encontrado como lista na amostra de um produto por loja. Contrato de atualização ainda não homologado.
- Nenhum produto, arquivo ou configuração das lojas foi modificado. Playwright preservado. `.env` não foi alterado pelo agente; segredos não foram exibidos.
- `PRM_STORE_ORGANIZATION_ID` continua vazio: falta vincular a organização para usar a interface. Execução CLI não grava o histórico da tela. Próxima etapa de escrita/upload depende de autorização e homologação específica.

## Integrações REST — teste autenticado real em 20/10/2026

- Após preenchimento do `.env` pelo usuário, executado `scripts/check_store_connections.py`: WooCommerce Choice, SAG e Portwell autenticados, HTTP 200 no GET protegido de produtos e controle anônimo recusado. Somente leitura confirmada; escrita não testada.
- WordPress das três lojas retornou HTTP 401. Diagnóstico complementar GET-only `scripts/check_wordpress_auth.py` confirmou código `incorrect_password` nas três. Necessário conferir usuário e senha de aplicativo de cada site; nenhum segredo foi impresso ou alterado.
- `_wcda_arquivos` apareceu como lista em `meta_data` na amostra de um produto por loja. Valores não expostos. Presença em leitura não comprova schema de gravação, armazenamento interno ou suporte a atualização.
- `PRM_STORE_ORGANIZATION_ID` ainda não configurado; a interface permanece bloqueada de forma segura até vincular a organização autorizada. Testes CLI não gravam histórico da interface.
- Homologação parcial: WooCommerce 3/3, WordPress 0/3. Nenhum upload, escrita de produto, exclusão ou instalação nas lojas. Próximo passo: corrigir senhas de aplicativo e repetir testes; manter Playwright.

## Geração de Datasheets em Lote — 20/10/2026

- Especificação `ae62b017-36f1-496e-b5fb-ded7f525799c/Pasted text.txt` lida integralmente. Implementados upload ZIP/CSV, pré-validação por produto, vínculo exato de PDFs, fila persistente, worker separado, progresso, histórico privado, downloads individuais/ZIP e reprocessamento de falhas. Página `/digitalizacao/lotes`, acessível pela Digitalização.
- Reutilizados serviço Claude, prompts, validações e motores PDF atuais. Geração individual, `.env`, banco oficial/staging e catálogos não foram modificados. Não há integração/publicação automática no WooCommerce.
- Fila SQLite local em `data/datasheet_batches`, adequada a um servidor; não depende de migração das reuniões. Transações de reivindicação, limite global de concorrência, subprocesso por produto, watchdog/timeout, lease e rejeição de resultados atrasados. Interrupções incertas exigem reprocessamento explícito; 429/5xx têm backoff limitado. Retry pode repetir custos, conforme guia.
- Segurança: validação do nome original do ZIP (incluindo normalização Windows), sem `extractall`, bloqueio de traversal/links/extensões, limites de descompressão, PDF e CSV, CSRF e escopo organização/proprietário. Retenção explícita com simulação, preservando lotes ativos e histórico.
- Verificação: suíte completa **265 testes aprovados** (3 avisos de dependências/planilhas); após adicionar contrato da nova página e reforçar testes de acesso/início, **60 testes direcionados aprovados** (1 aviso de depreciação). Geração pelo motor real das três marcas com IA simulada. JS validado por `node --check`.
- Smoke visual/browser isolado: **8 combinações aprovadas**, claro/escuro em 1440/768/390/320 px; tabela, histórico, progresso, reprocessamento habilitado e escape de conteúdo verificados, sem overflow global/erros JS. Evidências locais: `data/exports/batch-visual-1792500553326`. Nenhum dado de teste foi publicado no PRM.
- Operação: reiniciar web e executar `.\.venv\Scripts\python.exe scripts/datasheet_batch_worker.py` em terminal separado. Worker não foi deixado em execução. Limites/configuração e arquivos alterados em `docs/DATASHEETS_EM_LOTE.md`; `.env.example`, README, API e changelog atualizados.
- Homologação pendente: lote real com API paga, carga representativa e configuração de serviço Windows caso desejada. Nenhuma chamada paga, implantação em produção, commit ou push realizados. Não há garantia de cobrança exatamente uma vez em falhas de rede; conferir antes de reprocessar.

## Digitalização: retorno ao fluxo completo com Sonnet — 19/10/2026

- A pedido do usuário, `.env` local configurado com `DATASHEET_MODEL=claude-sonnet-5-5`. Autenticação e presença exata do modelo confirmadas pela listagem da API, sem geração paga.
- Revertidos o uso obrigatório da ferramenta e o bloco de concisão adicionados na última tentativa com Haiku. Sonnet usa o prompt editorial completo existente, `tool_choice=auto`, esforço médio, limite de saída de 32.000 tokens e até duas revisões visuais. Isso permite até três chamadas de geração; não representa previsão de consumo.
- Preservados validação de especificações, rejeição de respostas truncadas, diagnóstico por etapa e regeneração após correções. Sem alterações no banco ou layout. 13 testes direcionados aprovados com clientes simulados/motor local; geração real ainda precisa ser testada após reiniciar o servidor.

## Digitalização: resposta Haiku truncada — 19/10/2026

- Haiku passa a usar `tool_choice` obrigatório para `entregar_datasheet`, evitando texto livre antes do JSON. Prompt 2026-10-19.2 pede resposta concisa sem tabelas duplicadas ou transcrição de catálogos, preservando especificações relevantes.
- Mantidos 16.000 tokens de saída, modelo configurado e uma revisão visual; sem retry de truncamento ou aumento automático de custo. Erro distingue análise inicial de revisão visual e rejeita JSON parcial.
- 12 testes direcionados aprovados (cliente simulado e motor local), incluindo truncamento nas duas etapas sem renderizar a resposta parcial. Nenhuma chamada paga ou alteração no banco/.env. Necessário reiniciar o servidor e validar com o anexo real; correção reduz o risco, não garante que qualquer catálogo caiba no limite.

## CLI extrair_e_identificar — 19/10/2026

- Implementada sobre o motor atual, conforme autorização do usuário: extração PyMuPDF+smask, filtros, trim, pHash mantendo maior resolução, inventário F1/F2, desenho vetorial heurístico, seleção Haiku sem coordenadas, validação JSON Schema, até duas correções e geração local com até duas tentativas de paginação.
- CLI separada, sem trocar a integração web, banco ou `.env`. Pastas únicas em `trabalho/` ignoradas no Git. `--somente-extrair` disponível. Sem chamadas pagas nesta implementação. Exemplo estrutural sintético, com `--exemplo` opcional; ZIP de referência não fornecido.
- 14 testes direcionados aprovados; extração real local inspecionada. União vetorial ampla detectada na auditoria foi restringida para evitar página inteira como foto. Revisão humana obrigatória; não há remoção de logos OCR/inpaint neste escopo. Guia: [EXTRAIR_E_IDENTIFICAR.md](EXTRAIR_E_IDENTIFICAR.md).

## Haiku: prompt e contrato de especificações — 19/10/2026

- Prompt compacto específico para modelos com `haiku` no ID, priorizando extração das tabelas técnicas antes do texto comercial. Preservadas regras de fontes, configurações, marcas, imagens e pendências.
- Schema por requisição exige `especificacoes` no completo, fixa nome/nível solicitados e define seção `{secao}` ou linha `{chave, valor}`. Validador rejeita tipos/linhas inválidas; não insere especificações fictícias nem lista vazia como correção automática.
- Haiku: limite de saída 16.000 tokens, sem `output_config.effort`, uma revisão visual por padrão (geração + revisão); Opus mantém 32.000 e duas revisões. Sem fallback automático para Opus ou retry adicional de correção. Limite de tokens não é previsão de gasto.
- Corrigido retorno de revisão com `revisao_ok=true` e conteúdo alterado: PDF é regenerado com as correções, evitando entregar a versão anterior. **10 testes direcionados aprovados**, sem chamadas pagas. `.env`, banco e identidade dos PDFs preservados. Reiniciar servidor para carregar alterações; geração real com o PDF do usuário ainda não validada.

## Diretrizes editoriais para datasheets — 19/10/2026

- Texto do operador em `319c57d8-b9f5-4f6b-a256-30acb9da0bc6/Pasted text.txt` lido integralmente e adaptado ao prompt `app/services/datasheet_prompt.py`, versão `2026-10-19.1`. Reforçados inventário/conferência, identidade técnica, configuração ausente como opções, organização/legendas das vistas, conectores por painel, dados instalados versus capacidade e revisão de todas as prévias.
- Mantido contrato `entregar_datasheet` e motor local; instruções de shell/pastas do texto não são executadas pelo modelo. Etiquetas seguem a empresa selecionada (sem marca Portwell aplicada a Choice/SAG). Sem inventar certificações ou dados elétricos. Etiquetas em perspectiva/texturas não suportadas devem ser pendências, não sucesso alegado.
- Schema comunicado ao Claude passa a declarar tags de até 48 caracteres, features de até 95 e coordenadas entre 0 e 1. Isso é contrato de geração, não garantia de validação geométrica completa pelo motor.
- **4 testes direcionados aprovados**, incluindo cliente Claude simulado e geração de datasheets. Nenhuma chamada real, alteração do `.env`, modelo configurado, banco ou layout dos PDFs. ID `claude-opus-5-5` não foi validado contra a API; teste mock não comprova disponibilidade. Servidor precisa recarregar o módulo Python para usar o prompt novo.

## Visual da página Cards — 16/10/2026

- Alteração exclusivamente de apresentação em `/cards`, inspirada no Industrial Command Center: cabeçalho, contexto da reunião, quatro indicadores derivados dos mesmos sete cards, destaque da data prevista e quadro responsivo com evidências expansíveis. Cores, tipografia, superfícies e temas reutilizam tokens existentes.
- CSS dedicado `cards-page.css` carregado somente em Cards; variantes do template/JS condicionadas a `cards-showcase`. Visão geral, Planner e demais páginas mantêm apresentação anterior. Dados, endpoints, permissões, ações, publicação, mock e banco inalterados.
- **38 testes direcionados aprovados**; cinco novos testes verificam isolamento visual e preservação de hooks. Navegador local: oito combinações (1440/768/390/320 px, claro/escuro), sete cards, contagens 7/6/1/7, detalhes expansíveis, sem overflow horizontal nem exceções JS. Capturas desktop escuro e mobile claro inspecionadas.
- Evidências privadas em `data/exports/cards-visual-20261016/`; script `scripts/cards_visual_smoke.cjs` usa HTML renderizado e respostas mock, sem sessão real ou escrita no banco. Nenhum reinício necessário: mudanças em templates/assets.

## Mock READ AI publicado no dashboard — 16/10/2026

- Validação final: **210 testes aprovados**, três avisos preexistentes, em 50,01 s. Sintaxe JavaScript e diff aprovados.
- A pedido do usuário, publicado painel **Mock — transcrição READ AI** na Visão geral, Cards e Planner. Sete cards determinísticos com citações/checklists/pendências; seis ações e um evento em 24/09/2026, reunião-base 16/09/2026. Horário 15h candidato, responsáveis PRM pendentes. Não é resposta de API real nem publicação operacional de tarefas.
- Fonte exata validada por SHA-256; 111 segmentos. Artefato privado `data/meetings/read-ai-dashboard-demo.json`, ignorado pelo Git, autenticado por `GET /api/v1/meeting-demo`, restrito a gestores da organização configurada. Sem transcrição integral exposta. Publicador idempotente `scripts.publish_meeting_demo --transcript <TXT>`; repetição preserva sete cards.
- **Zero chamadas de IA, zero escritas no banco, zero alertas/convites**. Banco oficial sem migração nova; controles operacionais ainda não migrados ficam ocultos nas páginas com o mock para não atrapalhar a demonstração.
- Servidor local PRM da pasta oficial reiniciado na porta 8000, mantendo host 127.0.0.1; rota nova confirmada no OpenAPI. Nenhum push/deploy remoto. Testes do módulo: **28 aprovados**, incluindo isolamento organizacional, autorização e contrato real da fixture; JS e diff sem erros.

## Continuação: revisão em lote e comentários — 16/10/2026

- Verificação final: **208 testes aprovados**, três avisos preexistentes, em 50,20 s; JavaScript e `git diff --check` sem erros. Inspeção somente leitura confirma oficial `prm_mvp` em `20261009_0008`, sem tabelas do módulo novo; modelo de reuniões ainda não configurado.
- Estado anterior confirmado: **206 testes aprovados**, três avisos preexistentes; código local ainda sem commit/deploy. Nenhuma alteração no oficial nesta continuação.
- Cards agora têm aprovação, rejeição e devolução à revisão em lote, com trava ordenada, versão esperada, limite de 100 IDs distintos e rollback integral em caso de erro/permissão/conflito.
- Comentários internos independentes da edição, permitidos ao curador/gestor ou executor autorizado; idempotência por UUID/autor/card, sem mudar status/aprovação/prazo. Campos não salvos permanecem intactos ao comentar. Conteúdo mostrado como texto, inclusive marcação HTML.
- **26 testes do módulo aprovados**, incluindo atomicidade, versão antiga, retry de comentário, isolamento e ausência de efeitos na atividade. Sintaxe JavaScript aprovada. Sem migração nova, publicação de tarefas ou notificações externas.
- Próximos itens: homologação visual, mesclar/dividir, retenção, contrato Claude real e demais pendências em [REUNIOES_PLANNER.md](REUNIOES_PLANNER.md). Responsáveis do exemplo permanecem pendentes.

## Reuniões → Cards → Alertas → Planner — 16/10/2026 (staging)

- Implementação inicial das páginas, API autenticada, revisões/evidências, schema 2.0, jobs por etapa, atribuição individual/em lote, revisão/publicação, exportação e calendário mensal adicional na dashboard. Estilos existentes preservados; homologação visual ainda pendente.
- Migração aditiva `20261016_0009` aplicada **somente em `prm_pipeline_staging`**. Oficial `prm_mvp`, catálogos, `.env`, usuários e serviços atuais preservados; sem push/deploy/reinício.
- READ AI: 111 segmentos, sete propostas **simuladas** em rascunho. Datas confirmadas: 16/09/2026 e 24/09/2026; 15h permanece candidato. Responsáveis pendentes, nenhuma conta fictícia, zero publicação/alertas.
- Suíte geral: **205 aprovados** antes da última adição; módulo final: **24 aprovados**. Oito rotas verificadas no PostgreSQL staging em transação somente leitura; JS sem erro de sintaxe. Teste real local ASR `small` CPU/int8: 20,178 s de voz sintética em 6,106 s, cinco segmentos. Ambiente `.venv-asr` isolado; PyAV fixado em 16.1.0 após incompatibilidade real com 19.
- **Não é aceite integral:** faltam homologação visual/concorrente, contrato Claude real (modelo de reuniões não configurado), chunking, mesclar/dividir, retenção/exclusão, arraste e demais lacunas listadas em [REUNIOES_PLANNER.md](REUNIOES_PLANNER.md). Workers não iniciados permanentemente. Próxima sessão deve partir desse documento, sem reimportar catálogos nem publicar os rascunhos automaticamente.

## Logos individuais Portwell · Choice · SAG — 15/10/2026

- Fontes salvas pelo operador: `data/imports/logos-novas.png.png` (lockup) e `data/imports/portwell-nova.png.png` (Portwell oficial isolada). Originais inalterados.
- `scripts/extract_brand_logos.py` separa as marcas pelos traços verticais, converte luminância em alfa (transparência real, antisserrilhado preservado) e gera `app/static/brand/{portwell,choice,sag}.png` + `brand.css` (proporções). A Portwell vem do arquivo isolado, porque no lockup ela aparece comprimida na horizontal; a altura relativa entre as marcas segue o lockup.
- Logos pretas no tema claro e claras no escuro (CSS `filter`), sempre claras na sidebar e no painel escuro do login. Aplicadas no header, sidebar, login, seletores da Digitalização, distribuição do dashboard e comparação direta estática; o `brand-lockup.png` antigo não é mais referenciado nas páginas.
- Layout, cores e gráficos da dashboard inalterados. **182 testes aprovados**; conferência visual em 1440/390 px nos dois temas, sem overflow nem erros de JavaScript.
- Regenerar: `python -m scripts.extract_brand_logos --source <lockup> --portwell <portwell oficial>` e incrementar `brand_version` em `_brand_logos.html`.

## PRM 4.0 — Industrial Command Center — 15/10/2026

- Skills: `ui-ux-pro-max` (em `.claude/skills/`) usada para direção visual (estilo Data-Dense Dashboard, densidade, motion, checklist de acessibilidade); `frontend-design` **não está instalada** (o comando `/plugin` não está disponível neste ambiente). Paletas dos gráficos validadas com o validador da skill `dataviz` nos dois temas.
- Dashboard reorganizado: barra operacional (empresa, período, status, atualizar, nova digitalização), linha de status da base publicada, centro de operações e inteligência de portfólio. Gráficos em SVG próprio, sem dependência externa (ECharts não foi adicionado). Componentes e decisões em [COMMAND_CENTER.md](COMMAND_CENTER.md).
- Dados operacionais reais: `app/services/operations_overview.py` + `GET /api/v1/operations/overview` (somente gestores, mesma regra das execuções). Lê `PRM_PRODUCT_STORAGE_ROOT/_runs/*/record.json`: rascunho (análise + datasheet), aprovação e pacote validado; não expõe caminhos nem a análise. **CSV, WooCommerce e falhas não têm registro persistido** e aparecem como tal. Nesta máquina ainda não existem execuções: os painéis exibem estados vazios, sem números inventados.
- Shell: Operational Clock (Intl, America/Sao_Paulo, sem layout shift, pausa com aba oculta), sidebar compacta com tooltips e ícones dedicados, chip do usuário, tema com ícones sol/lua. Tokens legados `--prm-*`/`--ops-*` passam a resolver para `--cc-*`; regras escuras obsoletas removidas de `workspace.css`.
- Testes: **181 aprovados**, três avisos preexistentes (3 novos para o serviço/endpoint). Inspeção visual em Edge headless sobre `scripts.workspace_preview` (snapshot publicado + fixture sintética de execuções **fora do repositório**): 1440/1366/768/390 px, claro/escuro, sem overflow horizontal nem erros de JavaScript; 15 verificações de interação (filtros, KPI→tabela, período, séries, atualização, abas por teclado, sidebar compacta) aprovadas. `scripts/workspace_visual_smoke.cjs` não foi reexecutado (porta 8871 ocupada por uma prévia anterior).
- Pendências: novas logos (Portwell e lockup) não estão no disco — salvar os arquivos para substituição; login e páginas de catálogo receberam apenas os tokens; sem push/deploy nem reinício do servidor.

## Central operacional e workspace visual — 15/10/2026

- Dashboard reformulado: contexto por empresa, pesquisa no catálogo, quatro indicadores reais, cards próprios prioritários, gráfico ECO/Dimensional com navegação por grupos e abas de panorama, atributos e qualidade. Números e análises do snapshot **`74f1f8e8300912677e8f49f4`** preservados; sem misturar histórico ou transformar proximidade por família em equivalência técnica.
- Estrutura compartilhada com sidebar/header, ícones SVG, relógio, densidade, temas claro/escuro e responsividade. Logos originais mantidas; proporção SAG corrigida nos novos cards. Digitalização ganha etapas fixas em desktop, contexto recolhível e componentes coerentes; IDs, análise, aprovação, datasheet, pacote, cadastro e integrações preservados.
- SAG sem catálogo e Claude/WooCommerce sem telemetria exibem estados explícitos; nenhuma fila/métrica/status fictício. Sem alteração de banco, fontes, arquivos de produto, `.env`, endpoints ou permissões. Pasta oficial: `C:\Users\PW\Documents\PRM`; alterações anteriores preservadas.
- **178 testes aprovados**, três avisos preexistentes. Smoke SQL/HTML/API no oficial: **14 rotas aprovadas**, **89.693 registros / 500.016 observações**, isolamento reconciliado. Navegador: **20 combinações / 296 verificações** de dashboard e Digitalização, temas claro/escuro, larguras 1440/1280/768/390/320, filtros, abas, menu, contexto e galeria. Persistência do tema conferida; capturas inspecionadas, sem transbordamento da página nos estados testados.
- Evidências locais: `data/exports/visual-workspace-20261015/`. Sem chamadas pagas/geração real de novos PDFs/publicação WooCommerce; homologação operacional autenticada continua recomendada. Sem push/deploy remoto ou reinício do servidor PRM existente.
- Arquivos, conceito, reprodução e limites: [WORKSPACE_VISUAL.md](WORKSPACE_VISUAL.md). Próximas evoluções dependem de endpoints reais para fila, atividade e saúde das integrações. Recarregar o navegador; reiniciar o servidor apenas se estiver com templates em cache ou apontando para outra pasta.

## SO por família e recálculo das análises — 14/10/2026

- Regra solicitada: presença/suporte de Windows/Linux equivalem por família de SO, independentemente de versão/edição/instalação. Listas sobrepostas são unidas; os textos originais permanecem intactos. Exemplo `Suporta Linux, Suporta Windows` versus `Windows 10 IoT | Linux; Windows 10 IoT` agora resulta em **Equivalente**. Negação/ausência explícita e dados desconhecidos não viram suporte.
- Novo snapshot **`74f1f8e8300912677e8f49f4`**, `refined-base-v3`, política `os-families-v2`, processamento **77,833 s**. **89.693 produtos / 500.016 observações / zero quarentena**. Os conflitos ECO caíram de **40 para 28**, resolvendo 12 observações de listas de SO. Demais conflitos: Portwell 70, Choice 6, Dimensional 30.026. Nenhuma alteração em originais/preços/famílias.
- API e páginas de Visão geral, Comparador e Importações passam a incluir `attribute_analysis`: interpretação de memória, armazenamento e USB e gráfico de SO. Denominadores explícitos; somente referências próprias visíveis da mesma família de produto. **SO ECO:** 10 produtos informam o atributo, 7 equivalentes, 3 inconclusivos, 7.935 sem informação; 0,09% do catálogo e 100% dos 7 comparáveis. **Dimensional:** 1 equivalente, 77.964 sem informação; menos de 0,01% do catálogo e 100% do único comparável. Não são percentuais de equivalência integral do produto.
- Interpretação dos atributos mapeados (interpretados/presentes): Portwell memória **364/364**, armazenamento **433/443**, USB **226/368**; Choice armazenamento **5/5**; ECO memória **4/17**, armazenamento **1/9**, USB **8/11**; Dimensional armazenamento **1/1**. Desconhecidos e campos sem mapeamento permanecem no painel de qualidade. Isso mede interpretação dos campos presentes, não completude ou homologação técnica.
- Gráficos de famílias recalculados: ECO **27,8%** e Dimensional **26,2%**, sem mudança porque os dados de classificação são os mesmos. Cobertura técnica integral permanece não avaliada; nenhum percentual antigo é reapresentado como equivalência atual.
- Backup `prm_mvp_20261014_141509.dump` (214.119.629 bytes), hash `97120cb909b40366f737b204e63da105d3728de07880920519a1fca5e593d1b2`; inventário pg_restore validado (188 linhas), restauração não executada. **Snapshot publicado em staging e depois no prm_mvp**, ponteiro de arquivos atualizado. Smoke de **14 rotas HTML/API nos dois bancos aprovado**, com recálculo independente dos indicadores de SO a partir das observações SQL e reconciliação dos denominadores. Histórico preservado: 35.786 ofertas legadas no oficial, 113.751 no staging. Nenhum push/deploy remoto ou reinício do processo HTTP existente; recarregar/reiniciar se não houver reload automático.
- Testes: **172 aprovados na suíte completa**, três avisos existentes; após ajuste adicional de negações/famílias e painel sem dados, **24 testes direcionados aprovados**. Comparação, pipeline, denominadores e ausência de dados cobertos. Sem push ou reinício do servidor.

## Características compostas em uma única linha — 14/10/2026

- Tela atual passa a usar `display_rows`: uma linha por característica canônica. **Memória** reúne capacidade e tipo, extraindo tecnologia DDR/LPDDR/GDDR, formato DIMM/SO-DIMM, frequência/taxa, slots explícitos e capacidade máxima. **Armazenamento** reúne capacidade, SSD/HDD/eMMC, interface SATA/mSATA, protocolo NVMe, barramento PCIe e formato M.2/polegadas. Valores originais ficam acessíveis em cada célula.
- Exemplo do usuário coberto: `8GB` + `DDR5 SODIMM` versus `2 x SO-DIMM DDR5 4800 MHz (até 64 GB)` resulta em **Correspondência parcial**: tecnologia/formato coincidem, capacidade informada de 8 GB não é comparada como igual ao máximo de 64 GB; frequência, slots e capacidade instalada não informados ficam identificados por detalhe.
- Todos os outros atributos também usam uma linha por característica, com detalhes separados por escopo/unidade e referência explícita nos casos diferentes/insuficientes/conflitantes. USB detalha quantidades por versão, geração e conector; o exemplo anterior agora apresenta correspondência parcial no resumo quando geração/conector faltam, mantendo a igualdade nas quantidades. Sistema operacional mantém suporte/instalação/opcionalidade dentro da mesma célula.
- Resumo por característica: conflito tem prioridade; diferença explícita resulta em Diferente; coincidência com lacunas resulta em Correspondência parcial; coincidência em todos os detalhes informados resulta em Igual/Equivalente. Não há confirmação automática de substituição do produto. Memórias de controlador continuam separadas e memória sem contexto não ganha inferência de RAM.
- Parsing conservador preserva resíduos como detalhe não interpretado; intervalos, alternativas e `2 x 8GB` não viram capacidade instalada presumida. Não altera banco, arquivos importados ou snapshot publicado `7012207d20150b0e098afe2b` (89.693 produtos / 500.016 observações). Sem reimportação, push ou reinício do servidor.
- **168 testes aprovados, três avisos existentes**. Smoke de 14 rotas HTML/API com dados oficiais aprovado, contagens/isolamento reconciliados. Regressões novas cobrem imagem enviada, armazenamento combinado/separado, capacidade máxima, intervalos/módulos, dados ausentes, conflitos, controlador e detalhes USB. HTML renderizado validado; inspeção visual no navegador não executada nesta etapa. Reiniciar o processo caso não haja reload automático.

## Equivalência de descrições USB — 14/10/2026

- Caso enviado: `2x USB 2.0, 4x USB 3.2` e `2 x USB 2.0 Type-A, 4 x USB 3.2 Gen2 Type-A` agora recebem **Equivalente** na comparação atual. Mensagem explicita que quantidades/versões coincidem, mas geração/conector ausentes de uma fonte permanecem não confirmados.
- Parser e dicionário de termos em `app/services/usb_comparison.py`: espaços, `x`/`×`, Type/Tipo e Gen/Generation/Geração; ordem de grupos e grupos repetidos da mesma versão. Comparação usa quantidade por versão e associação de portas que respeita detalhes explicitados nos dois lados.
- Diferenças explícitas de quantidade, versão, geração ou conector resultam em Diferente. Descrições incompletas, intervalos, alternativas, OTG/localização não interpretados permanecem insuficientes. Conflitos já registrados e escopos incompatíveis continuam protegidos. Não se presume equivalência entre USB 3.0/3.1/3.2 por rebranding nem se apagam evidências originais.
- **40 testes direcionados aprovados**, incluindo 20 casos novos USB e integração da imagem enviada à matriz. Normalização aplicada em tempo de comparação, disponível também para novos snapshots; não exige reimportação ou alteração do banco. Sem push ou reinício do servidor.

## Comparação por atributo e categorias agrupadas — 14/10/2026

- Estado inicial conferido: árvore Git limpa, projeto oficial em `C:\Users\PW\Documents\PRM`; snapshot publicado `7012207d20150b0e098afe2b`, 89.693 produtos / 500.016 observações. Auditoria SQL somente leitura, reproduzível com `python -m scripts.audit_comparison_fields`.
- Matriz atual exibe **Igual**, **Equivalente**, **Diferente**, **Dados insuficientes** ou **Conferir conflito** por produto/atributo. Referência é o primeiro produto ordenado (empresas próprias primeiro). Igual indica mesmo valor observado; equivalente indica igualdade após normalização de escrita/unidade/capacidade explícita. Listas diferentes, alternativas, ausência, escopos incompatíveis e conflitos não viram equivalência presumida. Indicadores não homologam a substituição do produto inteiro.
- Viabilidade: Portwell tem **253 produtos com memória + tipo de memória**, **360 com armazenamento + tipo de armazenamento**. Implementado agrupamento visual, preservando subcampos capacidade e tecnologia. Memória de controlador/trabalho/carga continua independente; memória sem contexto é identificada e não convertida automaticamente em RAM. Fontes contêm Flash-EPROM, FRAM, GDDR6X, suportes e alternativas: juntar tudo em um valor único perderia significado técnico.
- Sistema operacional: **364 observações Portwell** (192 suportado / 172 sem escopo), **16 ECO** e **1 Dimensional** sem escopo. A duplicação vinha da separação por escopo apesar do mesmo código `compute.os`. Agora há uma única linha/categoria de SO, preservando escopo por observação. Suporte a Windows não equivale automaticamente a Windows instalado; versões/edições distintas continuam distintas.
- Mudança aplicada na leitura/apresentação do snapshot: dados brutos, identificadores, publicação, histórico e importações preservados; nenhuma migração/reimportação necessária. CSS versionado para atualizar os indicadores visuais. Não houve push, deploy remoto ou reinício do servidor; recarregar/reiniciar se o processo existente não usa reload.
- Validação: **139 testes aprovados na suíte completa, três avisos existentes**; depois, dois cenários adicionais de unidades/renderização passaram junto aos testes da comparação (**9 aprovados**). Cobertos igualdade, capacidade SI/IEC, três produtos, ausência, conflitos, unidades, agrupamento sem perda, SO consolidado e escape HTML. Smoke de 14 rotas HTML/API com dados do oficial aprovado, contagens e isolamento reconciliados. Validação de HTML pelo cliente local; inspeção visual em navegador não executada nesta etapa.

## Atributos concorrentes normalizados e publicados — 09/10/2026

- Auditoria reproduzida sobre as quatro fontes definitivas e **500.016 observações**; identificadas 19 observações ECO `ATR_USB`/`ATR_COM`. Dicionário declarativo com **54 códigos e 86 aliases**, regras `refined-base-v2`, dicionário `attributes-v3`. Portwell/Choice continuam primeiro e orientam a apresentação.
- `ATR_USB` → **Portas USB**, `ATR_COM` → **Portas Seriais COM**. IP, comunicação, IO, dimensões, material, cor e campos elétricos também padronizados. Entrada/saída/bobina/nominal/sem escopo permanecem distintos; memória depende da família e proteção genérica exige IP explícito. Sem fuzzy inseguro nem equivalência técnica automática.
- Escalares conhecidos e completos convertidos com Decimal; polos/IO como inteiros. Deduplicação e conflitos respeitam código/escopo/unidade. Matriz compara códigos canônicos e exibe origem e valor padronizado; catálogo preserva os brutos visíveis; dashboard mostra mapeados/não mapeados. Importações futuras **pelo pipeline refinado** recebem as regras; importadores legados não substituem a base atual.
- Snapshot final **`7012207d20150b0e098afe2b`** gerado em **76,671 s**, reconciliado/publicado primeiro em `prm_pipeline_staging`, depois **publicado no `prm_mvp`**. **89.693 registros, 500.016 atributos, zero quarentena**; públicos 89.651. Hashes e arquivos originais preservados, sem exclusão/sobrescrita de ofertas; oficial permanece com 35.786 ofertas legadas, staging com 113.751. Snapshot anterior arquivado; intermediários de desenvolvimento não publicados no oficial.
- Atributos com código mapeado: **176.454 (35,3%)**, antes 2.675. Portwell **6.897/7.907**, Choice **10.868/21.367**, ECO **24.412/39.162**, Dimensional **134.277/431.580**. Restam **323.562 observações não mapeadas**. Mapeamento de campo não é suficiência técnica/aprovação. Alertas conflitantes: Portwell 70, Choice 6, ECO 40, Dimensional 30.026; aliases também expõem divergências antes separadas por nomes. Famílias e seus gráficos não foram alterados; cobertura técnica continua não avaliada.
- **135 testes aprovados, três avisos existentes**. Smokes SQL/HTML/API aprovados nos dois bancos (14 rotas), aliases USB/COM reais conferidos no banco e reconciliação de grupos/isolamento mantida. Auditoria CLI validada em Windows, inclusive caracteres fora de cp1252.
- Backup preventivo `data/backups/prm_mvp_20261009_140626.dump` (**119.974.173 bytes**), SHA-256 `711e4c777dbaa2797516ac33bb54c8d1e722225f2b353503058d7f05dfd77700`, inventário pg_restore validado (188 linhas); restauração completa não executada. Sem mudança de `.env`, push, deploy remoto ou reinício do servidor existente. Reiniciar o servidor caso não haja reload automático.
- Contrato, limites, comandos e retomada em [NORMALIZACAO_ATRIBUTOS.md](NORMALIZACAO_ATRIBUTOS.md). Próximos passos: ampliar aliases com evidência, parsers de intervalos/configuração, perfis técnicos, candidatos e revisão humana; não usar apenas semelhança de família/nome para homologar produtos ou diferenças de preço.

## Navegação por grupos e comparação atual — 09/10/2026

- Os três grupos do dashboard agora têm links para listas filtradas: `shared` (família presente nas nossas empresas), `not_found` (família não localizada na base própria) e `review` (classificação pendente). Contagens dos filtros reconciliadas com os gráficos em ECO/Dimensional; desconhecidos não são tratados como equivalentes nem como lacunas definitivas. Filtro adicional `quality_review` lista alertas de qualidade de qualquer origem.
- Cada produto pode abrir o portfólio próprio na mesma família, com referência fixada, ou permitir pesquisa em todas as nossas empresas. Quando não há família/candidato, a interface permite investigação manual sem inventar correspondência. Nossas empresas continuam primeiro e a paginação mantém 100 registros.
- Seleção manual de 2 a 8 produtos da base atual abre `/comparacao-atual`: preços visíveis, características, escopos/unidades e conflitos lado a lado. Preços internos só para gestores. Referência permanece na navegação/paginação; seleção de checkboxes é da página atual. Ainda é comparação exploratória, não confirmação técnica.
- Acesso restrito ao snapshot publicado da organização; UUIDs ausentes ou inacessíveis retornam 404, seleção inválida/base alterada retornam 422. Não consulta ofertas/comparações legadas nem grava decisões ou altera dados.
- **124 testes aprovados, três avisos**; smoke em staging e oficial validou filtros, referência, comparação e rejeições de seleções inválidas/obsoletas. Qualidade adicional conferida no oficial. Código local atualizado; reiniciar servidor se não houver reload. Sem push/deploy remoto.

## Dashboard somente com a base atual — 09/10/2026

- Novos imports definidos pelo operador como referência definitiva da análise vigente. Visão geral, Comparador e Importações não consultam nem exibem indicadores, pareamentos, preços, retratos ou auditorias anteriores. Código dos painéis antigos removido dessas páginas; dados históricos preservados no banco.
- Snapshot oficial: `6028d33f8d7aad1e5b085ab7`, **89.693 registros / 500.016 observações**; visão pública 89.651 e portfólio próprio visível **3.741** (Portwell 991, Choice 2.750). Sem recarga desnecessária nem exclusão de dados.
- Gráficos novos por família proposta: ECO 2.207/7.945 em famílias próprias visíveis (**27,8%**), 4.629 em famílias não localizadas e 1.109 pendentes; Dimensional 20.419/77.965 (**26,2%**), 22.584 não localizadas e 34.962 pendentes. Desconhecidos ficam no denominador e nunca contam como compartilhados. **Não é equivalência técnica nem ausência comercial comprovada.**
- `/api/v1/dashboard/summary`: **schema_version=2**, `run_id`, fontes, contagens atuais e comparação por família. Sem snapshot: `no_current_snapshot`; páginas não fazem fallback para histórico. Demais contratos legados permanecem fora dos painéis atuais.
- **121 testes aprovados, três avisos.** Reconciliação SQL e oito rotas (sete HTML e API) aprovadas em staging e oficial; autenticação simulada somente no diagnóstico. Histórico oficial continua em 35.786 ofertas. Regressões conferem que contexto antigo não aparece nas três páginas. Publicação oficial reconfirmada pelo fluxo idempotente.
- Código local pronto para carregar no servidor; sem push/deploy remoto ou reinício de processo HTTP existente. Comparação técnica, preços comparáveis e revisão de conflitos continuam pendentes. Operação em [CATALOGOS_REFINADOS.md](CATALOGOS_REFINADOS.md).

## Nova base refinada publicada — 09/10/2026

- Especificação `especificacao_pipeline_catalogos_prm.md` lida integralmente; operador confirmou publicação após os testes. **Fase de base/auditoria entregue; comparação técnica e oportunidades novas ainda pendentes.**
- Novos arquivos reconciliados por hash: Portwell **1.033**, Choice **2.750**, ECO **7.945**, Dimensional **77.965**; **89.693 aceitos, zero quarentena, 500.016 observações de atributos**. Visão pública: 89.651 registros (42 próprios ficam apenas na visão interna). Cópias imutáveis por hash em `data/imports/refined/`; antigos imports/tratados preservados.
- Execução `6028d33f8d7aad1e5b085ab7`, regras `refined-base-v1`, saídas em `data/analysis/staging/refined/<RUN>/`. Migração aditiva `20261009_0008`: tabelas `refined_catalog_runs`, `refined_catalog_raw`, `refined_catalog_items`, carregadas/reconciliadas em `prm_pipeline_staging` e **publicadas no prm_mvp**. Catálogos próprios parciais; cruzamento ECO isolado; ausência não significa descontinuação/lacuna definitiva.
- Dashboard, Comparador e Importações mostram a nova fotografia/qualidade/famílias. `/catalogos` passa à nova base, 100 por página e Portwell/Choice primeiro; `/catalogos?view=legacy` mantém filtros avançados e comparação direta anteriores. A nova cobertura técnica é **não avaliada**, não 0%; indicadores/pareamentos abaixo do novo painel estão explicitamente marcados como históricos.
- Nenhuma oferta antiga foi sobrescrita/excluída: oficial segue com **35.786 ofertas legadas e três lotes**; staging, 113.751 e quatro lotes. Backup preventivo `prm_mvp_20261009_123811.dump`, SHA-256 `04c5c08b8293a5f0b7fcdac6f9a4a112f324755a5d662f1b69c6508b1853eb77`, inventário validado. Nenhuma escrita WooCommerce/CIGAM, alteração `.env`, push ou deploy remoto.
- **115 testes aprovados, três avisos**; regressões reais, segurança da nova interface e smokes de sete páginas + reconciliação SQL passaram nos dois bancos. Idempotência de arquivos e carga staging confirmada. Execução de normalização: 73,132 s; sem IA/rede externa. Detalhes, contratos, comandos e pendências em [CATALOGOS_REFINADOS.md](CATALOGOS_REFINADOS.md).
- Próximo ponto de retomada: taxonomia/parsers tipados (há muitos não mapeados), perfis e candidatos, revisão técnica, cobertura/oportunidades e incrementalidade fina. Retomada de arquivos ainda reprocessa o lote; sem checkpoint/lock de geração. A nova visão ainda não tem os filtros avançados/seleção direta legados. Carregar o código atualizado/reiniciar o servidor se necessário; os testes não comprovam reload de processo antigo.

## Refinamento do tema escuro — 09/10/2026

- `app/static/css/prm-dark.css` concentra a paleta e os componentes escuros; removidas as regras antigas redundantes de `prm-v2.css`. O tema claro mantém os próprios tokens.
- Corrigidos contrastes de navegação, cards, inputs, selects, alertas, tabelas e áreas de Digitalização. Fotos e PDF não são invertidos; as logos pretas mantêm superfície branca. Filtros, textareas e botões de cadastro também receberam ajustes responsivos compartilhados.
- Inspeção visual local em login real e prévias Jinja sintéticas de dashboard, catálogo e Digitalização a 320/390/768/1024/1440 px, em temas claro e escuro; revisão, upload, PDF, cadastro, tabela e modal conferidos. Em 390 px, a Digitalização não produz rolagem horizontal. Alternância e persistência após recarga verificadas no navegador.
- Pendente: validação visual autenticada com dados reais e documentos de produto; detalhes e critérios em [REDESIGN_2_0.md](REDESIGN_2_0.md). Nenhum dado, serviço externo, backend, deploy ou push foi alterado.
- Suíte automatizada: **95 testes aprovados, 3 avisos**. Pares principais de texto/superfície passam de 5,7:1; borda de input e botão preenchido foram ajustados para pelo menos 3:1 contra a superfície adjacente.

## Correção das logos — 08/10/2026

- Portwell, Choice e SAG agora têm enquadramentos individuais nos cards da Digitalização, feitos com SVG `viewBox` sobre a imagem original intacta. O recorte anterior por `background-position` variava com a largura do card e mostrava partes das marcas vizinhas.
- A composição conjunta do login, cabeçalho e comparação direta usa o mesmo enquadramento centralizado. A versão do CSS foi atualizada para evitar cache do estilo antigo.
- Capturas locais de desktop (1366 px) e celular (390 px) confirmaram as três marcas completas e ausência de rolagem horizontal; foram acrescentados testes de regressão para os recortes.
- Suíte completa após a correção: **94 testes aprovados, 3 avisos**.

## Atualização de 08/10/2026 — redesign 2.0 da interface

- Nova camada visual `app/static/css/prm-v2.css` aplicada ao shell existente: navegação compacta, cabeçalho, login, dashboard, formulários, tabelas e componentes responsivos. Tema claro/escuro e preferência de navegação são locais ao navegador.
- A Digitalização ganhou resumo contextual, etapas navegáveis, prévia de foto e visualizador de PDF por página. Os IDs e endpoints do fluxo de análise, aprovação e geração foram preservados.
- A identidade mantém Portwell, Choice e SAG em primeiro plano, com acentos dos temas locais de datasheet. Nenhum dado, banco, loja ou serviço externo foi alterado por esta etapa; não houve deploy ou push.
- Verificações: `node --check` dos dois scripts alterados; suíte completa com **92 testes aprovados, 3 avisos**. Captura local de login em largura real de 390 e 360 CSS px; em 360 px não houve rolagem horizontal. A revisão visual autenticada da Digitalização com dados reais continua pendente.
- Escopo, referências e limitações estão em [REDESIGN_2_0.md](REDESIGN_2_0.md).

## Atualização de 08/10/2026 — Digitalização persistente antes do WooCommerce

- A etapa de arquivos agora é real: fotos ordenadas/processadas no backend, PDF Choice/SAG/Portwell salvo em rascunho persistente, pasta física por empresa e Código CIGAM literal, manifesto com caminhos e hashes, ZIP validado e recuperação por ID após recarga. A imagem principal é indicada pelo manifesto, não por ordem alfabética. A pasta-base `PRM_PRODUCT_STORAGE_ROOT` é configurável; padrão local `data/products/`, ignorado pelo Git.
- A finalização é atômica por pasta temporária, bloqueia sobrescrita e oferece nova versão somente após confirmação. O CSV WooCommerce e a descrição ficam bloqueados até o pacote estar validado; antes de gerar CSV o backend confere novamente hashes dos arquivos e conteúdo do ZIP. Nenhuma escrita WooCommerce ou CIGAM foi realizada.
- Novos endpoints autenticados em `app/routers/digitalizacao.py` criam/consultam a execução, entregam PDF/fotos/ZIP e finalizam a pasta. O frontend guarda o ID e pode recuperá-lo após atualizar a página. A ordem das rotas foi corrigida para que o catch-all HTML não intercepte os novos GETs da API.
- Verificações e detalhes operacionais em [DIGITALIZACAO_PRODUTO.md](DIGITALIZACAO_PRODUTO.md). Pendências: teste em compartilhamento de rede real, política de retenção de rascunhos, validação visual em celular e fase posterior de escrita WooCommerce/Playwright com confirmação específica.
- Suíte completa após a mudança: **86 testes aprovados, 3 avisos**; JavaScript de Digitalização e cadastro passou em `node --check`. Os testes de integração usam armazenamento temporário e credenciais simuladas. Nenhuma pasta de produto real, banco ou loja foi alterada durante os testes.


## Atualização de 08/10/2026 — redesign visual do PRM

- A identidade visual foi renovada **no frontend existente**, sem criar dashboard separado nem alterar backend, banco ou integrações. O design system em `app/static/css/design-system.css` centraliza paleta industrial (azul petróleo/grafite), superfícies, bordas, sombras, estados de foco, transições, responsividade e preferência por movimento reduzido. Login, sidebar, cabeçalho, indicadores, cards, filtros, tabelas, comparações e Digitalização receberam o novo acabamento.
- A imagem original com Portwell, Choice e SAG foi copiada sem modificação para `app/static/brand-lockup.png` e aparece no cabeçalho, no login e na comparação direta estática. O SHA-256 da cópia corresponde ao arquivo de Downloads. Os cards de seleção na Digitalização exibem nomes/símbolos tipográficos; a imagem oficial permanece intacta.
- A Digitalização mantém seus IDs, eventos e endpoints. Foram adicionados cards sincronizados com o seletor de empresa, estados de carregamento, refinamento do stepper, upload, imagens e seção de cadastro. A navegação móvel tem botão, fechamento por clique externo/Escape e `aria-expanded`.
- Verificações: `node --check` em `ui.js` e `registration.js`; **70 testes aprovados, 3 avisos**, inclusive assets HTTP, login e templates. Capturas locais do login em Edge headless, nas larguras 1440 e 500 px, foram inspecionadas; os arquivos estão em `data/exports/`, ignorados pelo Git. A largura de 390 px não foi conclusiva por limite mínimo da janela headless, portanto uma checagem em aparelho real ainda é recomendada. Nenhum deploy ou push foi realizado.


## Atualização de 08/10/2026 — cadastro automatizado na Digitalização (implementação local)

- A pasta oficial continua `C:\Users\PW\Documents\PRM`. O ZIP recebido com **todos os exports** de Choice, SAG e Portwell foi copiado sem alterar o original para `data/imports/exports_woocommerce_choice_sag_portwell.zip` (ignorado pelo Git); SHA-256: `844690755b70b314cb7a331d5c1b0265c28e7b8317d49395bed83bdda87bc32f`.
- Auditoria dos exports: Choice 2.714 SKUs, 116 colunas, 15 blocos de atributo e 350 linhas de lotes antigos sem colunas finais; SAG 298 SKUs, 104 colunas, 16 blocos e 100 linhas sem quatro colunas finais; Portwell 1.018 SKUs, 133 colunas e 18 blocos. A leitura completa preserva o cabeçalho mais amplo e preenche somente as células finais ausentes. Há nomes de atributo com indicação global/local divergente (Choice: 4; Portwell: 1); novos atributos afetados exigem revisão. Registros existentes com mais de 15 atributos são preservados, mas o limite impede acrescentar outros.
- Na página existente de Digitalização, foi adicionada a seção **Cadastro automatizado** e endpoints protegidos para modelo central validado, descrição determinística fundamentada, prévia de planilha em lote, descoberta de arquivos, consulta WooCommerce somente leitura, CSV Woo por cabeçalho da empresa, XLSX CIGAM e pacote ZIP real com imagens processadas. O export padrão é selecionado pelo código da empresa no ZIP; upload manual de export mais recente continua opcional.
- CSV de produto existente parte da linha original e preserva ID, preço, imagens, metadados e campos não aprovados; produto novo sai como rascunho. Avisos de revisão são expostos sem impedir o download do CSV. O metadado `_hide_product_price` **não é ativado para novos produtos** até validação na loja. Nenhum CSV foi importado em loja real.
- A planilha CIGAM recebida é um modelo de 16 colunas com apenas um exemplo; campos sem origem no modelo central permanecem vazios e são sinalizados. O script Flask/Playwright recebido foi auditado; somente a descoberta/classificação segura de arquivos foi adaptada ao FastAPI. Nenhuma automação de upload nem escrita Woo/ERP está ativada.
- Testes específicos de cadastro: **9 aprovados**. Suíte completa: **69 aprovados, 3 avisos**. Não foi aplicada migração, nem alterado `prm_mvp`, `prm_pipeline_staging`, WooCommerce ou CIGAM. Mais detalhes, configuração e pendências em [CADASTRO_AUTOMATIZADO.md](CADASTRO_AUTOMATIZADO.md).


## Atualização de 01/10/2026 — política de senha e gestor

- Por solicitação do operador, o mínimo de senha do PRM passou de 12 para **6 caracteres** em `app/services/security.py`; os fluxos interativos de cadastro e o teste de segurança foram atualizados. O hash Argon2 e as demais regras de autenticação não mudaram. Essa redução vale para todas as contas novas e diminui a resistência a tentativas de adivinhação; é recomendado usar senhas longas mesmo com o mínimo reduzido.
- O usuário `kaue.borges@choicetech.com.br` foi criado no `prm_mvp` como `gestor` ativo (maior perfil de acesso da aplicação). A senha não foi gravada em código, documentação ou saída do terminal; o banco guarda apenas o hash. Essa função não concede privilégios de administrador do Windows ou do PostgreSQL.
- Verificação SQL confirmou o usuário ativo com perfil `gestor`. Suíte completa: **60 testes aprovados, 3 avisos**.

## Atualização de 28/09/2026 — PostgreSQL de staging e carga Dimensional

- O novo banco `prm_pipeline_staging` foi confirmado vazio e isolado. O backup SHA-256 `4470551b59efaebf108e8199e6c1c1785dd8bb8b2aece4b87580ab353ea848dc` do `prm_mvp` foi restaurado nele, sem limpar nem sobrescrever dados preexistentes. Esquema: 20 tabelas, revisão `20260923_0007`; linha de base: 35.786 ofertas.
- A carga CSV Dimensional entrou **somente no staging**, em uma transação: 77.965 ofertas distintas por SKU, 77.965 linhas brutas auditáveis, 77.965 observações e 155.930 registros de preço anunciado/referência; total do staging: 113.751 ofertas. O lote `380250f8-e8a7-4daf-9453-8bf80c3846a2` guarda hash, origem e 582 linhas com alertas. São 77.934 preços anunciados positivos e 31 sem valor positivo. Reexecutar o lote retornou `idempotent=true`, sem duplicar registros.
- A ingestão preserva `product_id`, EAN, NCM, textos e linhas físicas no JSON de origem; usa empresa+SKU como identidade da oferta. Estoque numérico permanece nulo/não confiável. A moeda `XXX` indica desconhecida; `anunciado` e `referencia_anunciada` não equivalem a Pix, cartão ou preço comercial comparável. A data da observação permanece nula.
- A visão geral e Importações e qualidade consultam as contagens do staging em modo somente leitura, exibindo-as separadas da produção e da simulação inicial. O painel reconcilia o hash e a contagem com a auditoria local. Não há equivalências homologadas nem matching Dimensional publicado.
- O `prm_mvp` foi reconciliado após a carga: segue com 3 empresas, 3 lotes e 35.786 ofertas; Portwell, Choice e Eco não foram alteradas. **A Dimensional ainda não aparece nos filtros comerciais oficiais.**
- Suíte completa: **60 aprovados, 3 avisos**. Smoke autenticado com PostgreSQL real passou; o teste de idempotência e a reconciliação SQL do staging também passaram. Scripts operacionais e limitações em [DIMENSIONAL.md](DIMENSIONAL.md).
- Próxima fase: persistir afirmações técnicas com estado de revisão e conflito, revisar amostra estratificada, validar moeda/data/unidade/estoque, testar rollback de uma revisão e só então promover para `prm_mvp` e habilitar comparação/cobertura. O importador atual é atômico e idempotente para este lote, mas **ainda não é retomável por checkpoint**.

## Registro anterior de 28/09/2026 — auditoria no dashboard antes da criação do staging

- A visão geral agora mostra, em painel próprio, a auditoria Dimensional de 77.965 SKUs, 77.934 preços anunciados positivos, 3.790 afirmações técnicas propostas e os alertas de EAN, NCM, preço e tensão de bobina. O painel identifica esses resultados como **staging** e mostra separadamente a quantidade de ofertas Dimensional presente de fato no banco oficial.
- O `prm_mvp` foi consultado e reconciliado: Choice 16.886 ofertas, Portwell 10.955, Eco 7.945; 3 lotes, 35.786 ofertas, 35.800 linhas de importação, 35.786 observações e 43.731 preços. Dimensional continua com **zero ofertas publicadas**. Nenhum preço ou match Dimensional foi tratado como equivalente ou comparável no banco.
- Backup preventivo validado: `data/backups/prm_mvp_20260928_141836.dump` (29.426.753 bytes; SHA-256 `4470551b59efaebf108e8199e6c1c1785dd8bb8b2aece4b87580ab353ea848dc`; inventário `pg_restore --list` com 172 linhas). Não foi executada restauração de teste.
- Teste novo protege a separação staging/publicado no dashboard. Suíte completa: **59 aprovados, 3 avisos**. Smoke autenticado com PostgreSQL real passou para dashboard, catálogo, API, comparador e logout. O primeiro pytest no sandbox falhou por permissão em arquivos temporários; repetido fora do sandbox, passou.
- **Publicação de ofertas/atributos/matches no `prm_mvp` não realizada.** O banco `prm_pipeline_staging` ainda não foi disponibilizado à aplicação; a carga CSV persistente, revisão de amostra e rollback não foram implementados/testados. Moeda, data/unidade comercial, semântica dos estoques sentinela e conflitos técnicos continuam pendentes. Publicar os 77.965 SKUs como comparáveis agora contrariaria os critérios de aceite e poderia gerar conclusões comerciais incorretas.
- A alteração do dashboard está nos arquivos locais. Nenhum servidor HTTP foi encontrado escutando nas portas 8000–8002 na verificação; ao iniciar/reiniciar a aplicação, a visão geral carregará o novo painel. Nenhum push Git ou deploy remoto foi realizado.

## Atualização de 28/09/2026 — Dimensional em auditoria e simulação

- O CSV Dimensional recebido (140.518.094 bytes; SHA-256 8ad7e0e63e265aa6ebfd34b06a530dc000177c11602c2a6920e80add3e211528) foi copiado sem alteração para data/imports/produtos_dimensional.csv, fora do Git. O original em Downloads permanece intocado.
- Adaptador CSV v1 em app/services/dimensional_csv.py: leitura streaming com UTF-8 BOM, aspas e descrições multilinha, layout validado, SKU como identidade por empresa/fonte e preços anunciados separados de preço de referência. Auditoria: 77.965 registros/SKUs, 77.957 product_id, 261.622 linhas físicas e 20 campos; três grupos de variantes preservados.
- Simulação em app/services/dimensional_stage.py e regras conservadoras em app/services/dimensional_semantics.py: 3.790 afirmações propostas, zero evidências sem trecho literal, 77.965 saldos confiáveis desconhecidos e zero ofertas/equivalências publicadas. Fórmulas, EAN/NCM inválidos e conflitos de variante/bobina/switch/cabo são sinalizados, não corrigidos por adivinhação.
- Relatórios ignorados pelo Git em data/analysis/staging/dimensional_audit.json e dimensional_simulation.json. A aba Importações e qualidade mostra os números apenas a gestores, com aviso de staging; Dimensional ainda não aparece nos filtros/catálogo publicados.
- Antes/depois do banco publicado: 3 empresas, 3 lotes, 35.786 ofertas, 35.800 linhas de importação, 43.731 preços e migração 20260923_0007; nenhuma gravação foi feita. O banco prm_pipeline_staging ainda não existe e prm_app não pode criá-lo; importação persistente, comparação cruzada, publicação e rollback aguardam staging PostgreSQL e revisão técnica.
- Operação, métricas, casos e decisões pendentes em docs/DIMENSIONAL.md. Testes específicos Dimensional: 15 aprovados; suíte completa: **58 aprovados, 3 avisos de dependências/planilha**, sem falhas.

## Atualização de 25/09/2026 — normalização auditável em staging

- A pasta oficial passou a ser C:\Users\PW\Documents\PRM. A especificação PRM_PIPELINE_NORMALIZACAO_PROMPT_CODEX.md foi lida integralmente; as seis planilhas do lote têm SHA-256 iguais aos informados.
- Auditoria reproduzível em app/services/catalog_audit.py e scripts/audit_catalog_pipeline.py: 35.799 linhas de produto por camada; Choice 16.894, Portwell 10.960, Eco 7.945. O bruto Portwell tem um rodapé adicional na linha 10.963 e três códigos com duas ocorrências divergentes em preço de compra e índice MK. Na Eco, 612 preços zero em cada modalidade e 54 registros BackOrder. Bruto/tratado reconciliam por código e multiplicidade; nenhuma planilha ou registro publicado foi alterado.
- Resultado gerado somente em data/analysis/staging/audit_20260925.json, ignorado pelo Git. A aba Importações e qualidade mostra a reconciliação a gestores, com aviso explícito de staging.
- app/services/catalog_semantics.py contém propostas determinísticas iniciais com evidência e escopo para CPU, PCs, memória, discos, portas, kits, acessórios e contatores; conflitos de fonte/UPS e corrente não são aprovados automaticamente. Ainda não está ligado à revisão publicada.
- 43 testes passaram, incluindo auditoria de integração, regressões sintéticas e registros reais Portwell, Choice e Eco. A primeira execução integral no sandbox falhou por falta de escrita nas planilhas temporárias dos testes; repetida com permissão, passou. Template shell.html compilado.
- Próximas fases: modelo relacional/migração não destrutiva, staging PostgreSQL, jobs retomáveis, revisão e publicação/rollback, comparação explicável e homologação técnica de 150 registros. Detalhes e operação em docs/catalog_pipeline.md. **Nenhum dado do banco foi migrado ou publicado nesta etapa.**
- Pré-condição para a fase PostgreSQL: a conta atual prm_app não tem CREATEDB e o banco prm_pipeline_staging ainda não existe. Não foi tentada migração no banco prm_mvp; um administrador deve provisionar um banco staging separado antes do teste de ingestão persistente.

Atualizado em: 2026-09-28 (America/Sao_Paulo)

O marco inicial `0.1.0` está resumido em [`docs/ENTREGA_0_1.md`](ENTREGA_0_1.md). O repositório de código é `https://github.com/Arthur-A-C/PRM`; a pasta oficial agora é `C:\Users\PW\Documents\PRM` e acompanha `origin/main`. Arquivos de configuração local, planilhas e backups são ignorados pelo Git.

Em 24/09/2026, o tratamento dos três catálogos, o comparador `lexical-v1.3`, as melhorias do dashboard e esta documentação foram publicados em `origin/main`. As planilhas e o backup permaneceram apenas no ambiente local.

A visualização de possíveis lacunas, a pesquisa/filtros do catálogo, o retrato comparável e a comparação direta descritos abaixo estão apenas no diretório de trabalho local; ainda não foram enviados ao GitHub.

## Atualização de 24/09/2026 — prévia remota temporária

- Prévia HTTPS pública de teste ativada via Cloudflare Quick Tunnel para uma instância separada em `127.0.0.1:8002`. URL e expiração atuais ficam somente em `data/exports/public_preview_status.json` (ignorado pelo Git); senha aleatória da prévia é exibida uma vez no terminal e não é gravada. O túnel encerra automaticamente após 120 minutos ou com `scripts.stop_public_preview`.
- A prévia exige HTTP Basic antes do login do PRM; cookies da instância remota têm atributo `Secure` e duração de duas horas. A instância local na 8000/8001 e o banco não foram reconfigurados. Nenhuma porta de entrada foi aberta.
- Teste externo confirmou `401` sem senha, `200` com senha na rota de saúde, redirecionamento ao login do PRM sem sessão e acesso autenticado ao catálogo após login. A conta temporária do smoke foi removida. Existem apenas contas de gestor permanentes no banco; cada colega deve ganhar uma conta individual `vendedor` com `scripts.create_team_tester` e ser desativado ao final com `scripts.deactivate_team_tester`.
- O executável oficial `cloudflared` foi baixado para `data/tools/`, fora do Git, e a assinatura Authenticode da Cloudflare foi validada. **29 testes aprovados** e smoke remoto completo aprovado. Operação e limites em [`OPERACAO_WINDOWS.md`](OPERACAO_WINDOWS.md).

## Correção de 24/09/2026 — link da comparação no processo ativo

- O processo web que escuta em `127.0.0.1:8000` estava carregado antes da criação da rota `/comparacao-direta`: a URL retornava HTTP 404, embora o arquivo JavaScript novo já fosse servido. Tentativa de reiniciar apenas esse processo foi negada pelo Windows; ele não foi encerrado.
- O botão do catálogo aponta agora para `/static/direct-comparison.html`, disponível imediatamente no processo ativo. A página lê os produtos pela API autenticada e mostra preços, referência opcional e características declaradas. Quando a rota Python nova estiver disponível após reinício controlado pelo operador, essa página redireciona automaticamente para a versão completa, que inclui os atributos tratados pelo pipeline.
- Smoke com sessão temporária validou a instância real: página estática HTTP 200, script HTTP 200, produto autenticado HTTP 200 e rota Python ainda HTTP 404. O teste removeu o usuário e a sessão temporários. Os dados e o banco foram preservados. Instrução de reinício em [`OPERACAO_WINDOWS.md`](OPERACAO_WINDOWS.md).

## Atualização de 24/09/2026 — preço e comparação direta

- Corrigido o filtro de preço na aba Catálogos: com “Todas as modalidades”, a faixa seleciona produtos que tenham ao menos um preço válido `venda`, `pix` ou `cartao` dentro de **ambos os limites na mesma modalidade**. Sem faixa, “Todas” continua mostrando também produtos sem preço. API e HTML usam a mesma regra; faixa invertida continua rejeitada.
- Cada card do catálogo agora tem seleção para comparação direta. A seleção de 2 a 8 produtos persiste entre páginas no navegador; a página `/comparacao-direta` mostra empresas próprias primeiro, preços das três modalidades, referência opcional e matriz de características do catálogo mais enriquecimento do pipeline. Comparação direta é exploratória e não confirma equivalência.
- O prévio/API e a persistência de comparações aceitam até 8 produtos. Teste unitário novo e smoke autenticado no PostgreSQL validam filtro geral de preço, seleção, matriz com valores tratados e referência. **27 testes aprovados**, `compileall` e smoke aprovados. Nenhuma migração ou atualização de ofertas/preços foi necessária.

## Atualização de 24/09/2026 — comparação normalizada

- Quatro arquivos recebidos (`base_comparavel.csv`, `atributos_normalizados_long.csv`, XLSX de comparação e `normalizar_catalogos.py`) foram inspecionados; **o script externo não foi executado**. Originais, ofertas, observações, preços e execuções de matching foram preservados.
- O gerador local somente leitura `scripts.build_comparable_snapshot` reconcilia as chaves externas ao banco, valida esquema/duplicatas, registra hashes e publica atomicamente `data/analysis/comparable_snapshot.json` (~77 KiB). O recorte tem Choice 15.482, Portwell 10.836 e Eco 7.944 ofertas, 23 macrocategorias e 265 pares macrocategoria/família.
- Novo painel na visão geral e tabela paginada/filtrável no comparador mostram amplitude de famílias: 4.280 ofertas Eco (53,9%) em famílias também presentes no portfólio próprio; 3.664 em famílias sem classificação própria. Isso **não é equivalência individual**, nem substitui os 11 pares fortes do `lexical-v1.3`.
- Auditoria: três chaves duplicadas Portwell, três chaves sem oferta publicada, oito linhas de atributo sem oferta e seis pares produto/atributo repetidos foram excluídos do retrato; 1.531 linhas constam em `Excluidos` no XLSX, sem exclusão do banco. Detalhes e propostas de melhoria em [`COMPARACAO_NORMALIZADA.md`](COMPARACAO_NORMALIZADA.md).
- API autenticada `/api/v1/comparable-portfolio` disponível. Na conclusão dessa etapa, havia **26 testes aprovados**, `compileall` e smoke autenticado com PostgreSQL real aprovados; o total atual está em “Testes e verificações”. O primeiro pytest no sandbox falhou apenas ao criar diretório temporário; repetição autorizada fora do sandbox passou. Smoke confirmou também o novo painel e a API. Não houve migração nem alteração de dados persistidos, além do usuário temporário do smoke, removido ao final.

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
- Catálogo paginado em **100 itens por padrão** (24, 48 e 200 opcionais), com busca por vários termos em código, nome, marca canônica/bruta, descrição, aplicação, categoria e sinais tratados. Filtros combináveis de empresa, marca, disponibilidade, família/segmento, modalidade e faixa de preço estão expostos na interface e na API; a ordem das empresas próprias é mantida.
- Filtros vazios não restringem o catálogo. A modalidade isolada exige preço válido nela; uma faixa de preço com “Todas” aceita qualquer modalidade válida, mantendo os dois limites no mesmo preço. A paginação preserva os filtros e não repete produtos entre páginas.
- O catálogo permite selecionar de 2 a 8 produtos entre páginas para comparação direta de preços e características tratadas; o comparador automático integral continua independente.
- O comparador principal deixou de exigir seleção manual e analisa o catálogo concorrente completo contra todas as ofertas das empresas próprias.
- O algoritmo local `lexical-v1.3` usa índice invertido, códigos/modelos, nome, marca canônica, descrição, família e atributos tratados; versão, limiares, pontuação e motivos ficam auditáveis. Conflitos técnicos críticos impedem sugestão forte.
- A migração `0006` criou aliases de marca revisáveis. `ELFIN` e `NEW ELFIN SRL` agora apontam para a marca canônica `ELFIN`, enquanto os valores brutos das 14 e 447 ofertas continuam preservados.
- Execução vigente Eco `lexical-v1.3` (`c73639ef-78ba-4683-8e0d-236a9ecfeda4`): 7.944 produtos contra 27.841 ofertas próprias; 11 sugestões fortes (0,14%), 467 produtos com candidato principal e 897 pares persistidos. Não há confirmações humanas.
- Uma sugestão forte agora exige pontuação mínima e ao menos um modelo/código compartilhado. Igualdade de marca melhora a pontuação, mas não promove sozinha produtos parecidos.
- Histórico preservado: 6 execuções e 4.063 pares candidatos no total; cada recálculo insere uma execução auditável e até 3 pares por produto concorrente.
- Dashboard e página de análise exibem gráfico de cobertura. O dashboard agora separa 11 sugestões fortes, 456 candidatos e 7.477 produtos Eco sem candidato; distribui as sugestões fortes entre Choice (11) e Portwell (0). Nossas empresas e produtos aparecem primeiro nos pares e listas.
- O dashboard mostra até três sugestões fortes com preços de ambos os lados; comparação entre modalidades distintas é explicitamente nominal. A lista integral e os motivos continuam no comparador.
- O comparador agora mostra possíveis lacunas da última execução, com marcas sem oferta própria identificada e famílias tratadas com produtos sem candidato; há barras, três exemplos por grupo, seleção de qualquer grupo e listagem paginada de 24 produtos. A API autenticada `/api/v1/catalog-gaps` expõe os mesmos sinais.
- No recorte Eco atual: 7.477 produtos sem candidato; 7.318 desses pertencem a 27 marcas sem oferta própria identificada, e 4.138 pertencem a famílias sem a mesma classificação no portfólio próprio. Há 157 produtos sem marca identificada. As dimensões se sobrepõem, e nenhuma contagem é uma lacuna comercial confirmada.
- A análise usa nosso preço preferencial como base para indicar `acima`, `abaixo` ou `igual`. Modalidades diferentes recebem alerta explícito de comparação nominal, não margem.
- Novas publicações pelo importador disparam o recálculo de todas as concorrentes, salvo `--skip-matching` explícito.
- Comparações podem ser salvas com estado inicial `nao_avaliado`; vendedor acessa as próprias e gestor pode consultar todas da organização.
- Ofertas excluídas analiticamente não podem ser comparadas ou salvas por vendedor.
- APIs autenticadas para dashboard, opções, produtos, prévia, criação e consulta de comparações.

## Testes e verificações

- `python -m compileall -q app scripts tests`: aprovado.
- `.venv\Scripts\python.exe -m pytest -q`: **29 aprovados**; duas advertências de depreciação da combinação FastAPI/Starlette instalada, sem falha funcional. A execução precisou sair do sandbox para acessar o diretório temporário do pytest.
- Migrações aplicadas transacionalmente; Alembic e inspeção do esquema confirmam a revisão 0007.
- `alembic check` confirma que os modelos SQLAlchemy e o esquema real não têm operações pendentes.
- Smoke autenticado no PostgreSQL real cobre dashboard, catálogo, identidade, gráfico, cobertura integral, ordem das empresas próprias, preços, alias `ELFIN`/`NEW ELFIN SRL` e logout.
- O smoke remove somente seu usuário e sessão temporários. O gestor permanente permanece; a contagem de sessões ativas varia com os logins e o smoke não altera execuções de correspondência.
- `scripts/reconcile_catalogs.py` reproduz as contagens persistidas sem alterar dados e lista empresas próprias primeiro.
- `scripts.smoke_web` passou no PostgreSQL real: dashboard, catálogo com páginas de 100, busca por múltiplos termos, família, modalidade, faixa com “Todas”, comparação direta com características tratadas e referência, API, análise global, lacunas e logout. `pip check` passou na verificação anterior.
- Consultas medidas anteriormente na máquina atual: dashboard 207 ms; primeira página 79 ms; busca “SIEMENS” 741 ms; filtro empresas próprias+estoque 39 ms; venda entre 100–500 BRL 358 ms. São amostras, não p95 nem promessa de produção.

## Limites conhecidos

- O fluxo humano para confirmar/rejeitar candidatos ainda não foi implementado; portanto a cobertura atual é algorítmica e tem zero confirmações humanas.
- O cadastro e a revisão de novos aliases de marca ainda não têm interface. Novos casos devem entrar de forma controlada na tabela `brand_aliases`; variantes não são fundidas automaticamente apenas por semelhança textual.
- Portwell/Choice usam `venda`, enquanto Eco usa principalmente `pix`/`cartao`. O indicador entre modalidades distintas é nominal e aparece sinalizado; condições comerciais não são inferidas.
- O tratamento automático dos XLSX brutos extrai apenas sinais locais verificáveis. Para a mesma riqueza de atributos das três saídas atuais, é preciso gerar e publicar nova planilha tratada; o ZIP externo não é executado no servidor e seus cruzamentos pré-calculados não são importados.
- O novo retrato comparável usa CSVs analisados e concilia as ofertas, mas não incorpora os valores do CSV longo ao algoritmo de pares. O alerta de desatualização compara contagens de ofertas; mudanças de conteúdo sem mudança de contagem exigem regeração manual.
- O catálogo Eco não possui aplicação estruturada para a maioria das ofertas; a tela usa família de produto como aproximação. Marcas das nossas empresas às vezes refletem fornecedores em vez de fabricantes. Isso e falsos negativos do matcher podem inflar as possíveis lacunas; a tela não presume que uma marca não é trabalhada nem que um produto equivalente inexiste.
- CSV, upload web, job persistido/progresso e tela de histórico/qualidade seguem pendentes na Fase 2 complementar.
- Painel lateral de detalhes e Chart.js seguem pendentes na Fase 3.
- A moeda BRL foi escolhida operacionalmente; não é campo declarado nas planilhas. `Data Cadastro` não é tratada como data de observação.
- Serviço Windows, teste de restauração e acesso em rede ainda não foram configurados. O backup foi criado e validado, mas não restaurado em banco separado.

## Próxima tarefa concreta

### Digitalização Claude e datasheets — 08/10/2026

- Correção de geração/aprovação: o botão Gerar Datasheet não exige mais foto quando já existe análise técnica. Rascunhos de PDF sem foto podem ser visualizados e aprovados; somente a criação do pacote final requer foto principal. A extração local de texto do PDF não invalida mais uma análise Claude já concluída em paralelo; a seleção posterior de desenho 3D também não descarta a análise, pois ele não é fonte do datasheet. O carregamento de prévias falho não descarta o PDF salvo. O JavaScript recebeu nova versão de cache.

- O pacote `prm-datasheets.zip` foi auditado (README, motor, temas, prompts e testes) e integrado sem alterar dados publicados. O fluxo de Digitalização passou a aceitar PDF e fotos na análise Claude, mantendo geração de PDFs Portwell/Choice/SAG, prévias, pendências, edição do JSON e aprovação humana antes do pacote.
- Corrigido o botão **Analisar produto com Claude**: ele agora habilita com PDF, foto **ou** especificações manuais, além de empresa, código e nome. O JavaScript recebeu nova versão de cache. A extração de texto do PDF é local; não usa Qwen.
- `DATASHEET_MODEL=claude-opus-5-5` foi definido no `.env` local a pedido do usuário. A chamada foi ajustada para `output_config.effort=medium`, `tool_choice=auto` e sem `temperature`, conforme a API do Opus 5.5. Reinicie o servidor para carregar o `.env`. Nenhuma chamada real à API foi feita; não foi possível verificar ainda se a conta tem acesso ao modelo.
- Teste mockado do endpoint com PDF e foto passou; testes do motor do ZIP passaram. A suíte completa passou com **92 testes** (3 avisos de dependências/dados), incluindo PDF sem foto, foto referenciada no JSON Claude e aprovação com pendência, sem chamadas reais à API. O pacote final continua isolado em `data/products` e WooCommerce permanece bloqueado até a validação do pacote.
- Pendente: validar uma chamada real após autorização, conferir visualmente as três marcas e a política de imagens/contatos oficiais, além de testar o fluxo completo na interface com o servidor reiniciado.
- Configuração Opus 5.5 e rotas verificadas com 3 testes simulados adicionais (sem consumo de créditos).

1. Revisar manualmente as 11 sugestões fortes, amostra dos 456 candidatos e principais sinais de lacuna (especialmente marcas cadastradas como fornecedor), para calibrar falsos positivos e negativos.
2. Criar fila de revisão humana para confirmar/rejeitar candidatos e lacunas, com justificativa e revisor.
3. Acrescentar aplicação estruturada quando a fonte a oferecer; manter família apenas como aproximação na Eco.
4. Criar tela para sugerir, revisar e administrar aliases de marca, e usar atributos revisados para elevar a qualidade do pareamento.
5. Mover o recálculo demorado para job persistido com progresso e completar a parte complementar de importação/qualidade.
