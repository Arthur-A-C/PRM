# Changelog

## 2026-10-09 — normalização entre empresas

- Dicionário versionado de 54 campos e 86 aliases, incluindo ATR_USB/Portas USB e ATR_COM/Portas Seriais COM; nomes e evidências originais preservados.
- Conversões conservadoras de escalares/unidades e quantidades; deduplicação e divergência respeitam escopo/unidade. Campos ambíguos não ganham significado inventado.
- Matriz passa a alinhar códigos canônicos, não nomes de origem; catálogo mostra nomenclatura/valores padronizados e dashboard apresenta contagens de atributos mapeados/não mapeados.
- Novo snapshot validado primeiro em staging; operação e limites em docs/NORMALIZACAO_ATRIBUTOS.md. Matching técnico continua não avaliado.

## 2026-10-09 — grupos navegáveis e comparação de produtos atuais

- Links dos grupos do dashboard para listas filtradas; conferência adicional por alertas de qualidade.
- Seleção de 2 a 8 produtos e matriz atual de preços/características; referência fixa para escolher candidatos próprios.
- Validação de organização, snapshot e visibilidade; sem reutilizar IDs/matches legados ou confirmar equivalência.

## 2026-10-09 — dashboard exclusivamente atual

- Removidos painéis/consultas de análises antigas de Visão geral, Comparador e Importações, sem excluir histórico do banco.
- Indicadores e gráficos por família derivados apenas do snapshot oficial; sem fallback para dados antigos e sem confundir sobreposição com equivalência.
- API de resumo do dashboard passa ao schema 2 da nova base; regressões e smokes SQL/HTML/API.

## 2026-10-09 — base refinada de catálogos

- Ingestão/auditoria versionada de WooCommerce Portwell/Choice, ECO XLSX e Dimensional CSV; bruto imutável, evidências, conflitos e cruzamentos legados isolados.
- Migração aditiva de snapshots, carga em staging e publicação transacional no oficial preservando ofertas anteriores.
- Nova fotografia e qualidade no dashboard; catálogo atual com 100 registros por página e acesso ao histórico. Comparação técnica nova explicitamente não avaliada.
- Operação, testes, limites e próximas fases em `docs/CATALOGOS_REFINADOS.md`.

## Prévia remota temporária — 2026-09-24

- Acesso HTTPS externo de teste por Cloudflare Quick Tunnel, com prazo de duas horas, sem abertura de porta de entrada.
- Instância separada com senha HTTP Basic adicional, login PRM e cookies `Secure`; scripts de início/parada e de criação/desativação de contas individuais de vendedor.
- Teste remoto ponta a ponta validou as duas barreiras, sessão e catálogo; URL e senha não entram no Git.

## Compatibilidade da comparação direta com servidor antigo — 2026-09-24

- Corrigido o botão que levava a `/comparacao-direta` quando o processo web ativo ainda não tinha carregado essa rota (HTTP 404).
- Página estática de compatibilidade usa a API autenticada para exibir produtos, preços e características imediatamente; após reinício do servidor, redireciona para a comparação completa com dados do pipeline.
- Instância ativa conferida por HTTP; reinício automático foi bloqueado por permissões do Windows e ficou documentado para o operador.

## Filtro de preço e comparação direta — 2026-09-24

- Faixa de preço com “Todas as modalidades” agora busca qualquer preço válido do produto, com mínimo e máximo satisfeitos pela mesma modalidade.
- Catálogo permite selecionar de 2 a 8 produtos entre páginas e abrir comparação direta lado a lado, mantendo empresas próprias em primeiro lugar.
- Nova página mostra preços Venda/Pix/Cartão, referência opcional e matriz técnica com características do catálogo e enriquecimento do pipeline; não confirma equivalência comercial.
- Teste unitário do filtro e smoke autenticado da seleção, preços e matriz aprovados.

## Retrato comparável Choice + Portwell x Eco — 2026-09-24

- CSVs normalizados e XLSX de análise inspecionados sem executar o script recebido; duplicatas, chaves sem oferta publicada e atributos órfãos documentados.
- Novo retrato taxonômico conciliado ao PostgreSQL, com hashes e geração atômica, sem alterar ofertas, preços ou execuções de correspondência.
- Dashboard e comparador mostram amplitude de famílias, atributos disponíveis, filtros e paginação; API autenticada `/api/v1/comparable-portfolio` e testes adicionados.
- Linguagem de “lacuna” tratada como indício; 53,9% de Eco em famílias compartilhadas não é equivalência de produtos. Metodologia em `docs/COMPARACAO_NORMALIZADA.md`.

## Pesquisa e filtros do catálogo — 2026-09-24

- Catálogo HTML e API passam a mostrar 100 produtos por página por padrão; 24, 48 e 200 permanecem disponíveis, com paginação e filtros preservados.
- Busca aceita vários termos em campos diferentes e procura código, nome, fabricante, marca canônica, descrição, aplicação, categoria e sinais tratados como família e modelo; curingas de SQL são tratados como texto literal.
- Interface passa a expor família/segmento, modalidade de preço, preço mínimo/máximo e tamanho da página, além de empresa, marca e disponibilidade; filtros vazios não excluem indevidamente todos os produtos.
- Modalidade selecionada sem faixa mostra apenas ofertas com preço válido nessa modalidade. A faixa também funciona com “Todas as modalidades”, exigindo que um preço da mesma modalidade satisfaça os dois limites.
- Smoke autenticado verifica 100 produtos por página, ausência de duplicação entre páginas, busca e filtros combinados no banco real.

## Sinais de lacunas no comparador — 2026-09-24

- Comparador passa a mostrar possíveis lacunas por marca/fabricante e por família de produto, com contagens, barras, exemplos e abertura da lista paginada dos produtos sem candidato.
- Nova API autenticada `/api/v1/catalog-gaps` disponibiliza os mesmos agrupamentos e filtros por marca ou família.
- Os indicadores distinguem ausência de candidato, ausência de marca no cadastro próprio e ausência de uma classificação de família; nenhuma delas é tratada como equivalência ou lacuna comercial confirmada.
- Testes unitários e smoke no PostgreSQL verificam agrupamento, reconciliação com o funil do pareador, seleção e paginação.

## Dashboard de análises tratadas — 2026-09-24

- Dashboard prioriza Choice Tech e Portwell e mostra ofertas tratadas e enriquecidas pelo pipeline em cada empresa.
- Análise concorrente ganha funil com sugestões fortes, candidatos e produtos sem candidato, além de distribuição das sugestões por empresa própria.
- Até três sugestões fortes exibem nossos preços e os do concorrente, com alerta para comparação nominal entre modalidades distintas.
- API de resumo e relatório de correspondências expõem os agregados necessários; smoke autenticado verifica reconciliação, ordem e novos componentes.

## Tratamento de catálogos — 2026-09-23

- Três planilhas enriquecidas do `PRM_Pipeline` inspecionadas e associadas às 35.786 ofertas sem substituir fontes brutas ou preços.
- Migração `20260923_0007` cria a camada `offer_enrichments`, com família, modelo, atributos e proveniência do tratamento.
- Novas importações brutas passam por tratamento determinístico antes da comparação; saídas tratadas futuras podem ser publicadas com prévia e validação por código.
- Matcher `lexical-v1.3` utiliza características tratadas, penaliza incompatibilidades técnicas e evita padrões genéricos como falso modelo.
- Backup do banco criado antes da migração; testes e documentação operacional atualizados.

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
