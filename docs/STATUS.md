# Status do projeto

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
