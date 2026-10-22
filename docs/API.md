# API

## Cards de teste (22/10/2026)

`GET /api/v1/planner/activities?include_tests=true` inclui exemplos `simulation=true` e `interactive_test=true`, preservando isolamento organizacional e visibilidade do vendedor. Cards utiliza essa opção; overview/calendário/alertas continuam exclusivamente operacionais. Consulta individual e `/assign` aceitam esses exemplos, mantendo CSRF, versão, auditoria e validação do destinatário. `/review` e `/publish` recusam simulações com 409. Nenhum payload de edição pode retirar as marcas de teste. Prazo serializado como `band: simulation`, sem bucket ou notificação.

## Digitalização em lote por pastas (21/10/2026)

`POST /api/v1/digitalizacao/lotes` mantém `arquivo` (ZIP), `delimitador` e CSRF e acrescenta `identificacao` (`csv`, padrão para clientes antigos; ou `folder`), `empresa` (obrigatória para `folder`: choice/portwell/sag) e `pasta_raiz` (relativa ao ZIP, opcional). CSV dentro do ZIP é opcional em `folder`, obrigatório em `csv`. Não há leitura de caminho local/rede enviado pelo usuário.

Resposta reutiliza a prévia/ID/fila atual. Itens por pasta incluem `identification`, `folder`, `assets` (nome, papel, bytes, indicação `analyze`, caminho interno relativo) e `warnings`. Estado inicial `pending` ou `invalid`; não agenda IA. Nomes inseguros/ZIP estruturalmente inválido/CSV incompatível retornam 422; falhas locais do produto aparecem na prévia. Iniciar, reprocessar, histórico e downloads continuam nos endpoints existentes, com isolamento por dono/organização. Nenhum endpoint de escrita WooCommerce foi habilitado. Ver [operação e limites](DATASHEETS_EM_LOTE.md).

## Documentos WooCommerce: contrato candidato (21/10/2026)

O serviço `app/services/store_document_update.py` prepara `PUT /wp-json/wc/v3/products/{id}` com apenas `meta_data: [{id, key: "_wcda_arquivos", value: lista_original_mais_novos}]`. O ID deve ser o metadado existente observado por GET. Documentos novos reais: `label`, `url`, `filename`, `filesize`; não há ID de arquivo observado nesse contrato.

**Não é um novo endpoint de escrita do PRM nem uma liberação de produção.** A CLI `scripts/preview_wcda_update.py` faz GET e mostra o Dry Run; o fluxo PUT/GET é exercitado somente com mocks. Documentos permanecem bloqueados no cadastro em lote. A futura homologação exige loja/SKU e documento explicitamente autorizados, além de backup/journal e inspeção do frontend. Ver [contrato, payload e rollback](WCDA_HOMOLOGACAO.md).

## Cards: atribuição e alertas operacionais (21/10/2026)

- `GET /api/v1/planner/users`: usuários ativos da organização para gestores/desenvolvedores; vendedor recebe apenas a própria conta. Cada opção retorna `id`, `name`, `role`, sem e-mail/senha.
- `POST /api/v1/planner/assign`: `{items: [{id, version}], assignee_user_id, reason}`; CSRF obrigatório, lote transacional, usuário ativo da mesma organização e permissões de atribuição. A interface usa o mesmo endpoint para um card ou seleção em lote. Conflito de versão: 409; destinatário inelegível/permissão: 403.
- `GET /api/v1/planner/alerts`: apenas alertas não resolvidos do destinatário atual em cards reais publicados abertos, com prazo/fuso e classificação atual; GET não agenda avisos. Simulações excluídas. Worker atualiza persistência a cada minuto; atribuição/publicação também sincronizam.
- `POST /api/v1/planner/alerts/{id}/read`: marca o aviso próprio como lido, com CSRF.

Ver `CARDS_E_ALERTAS.md`. A atribuição de um rascunho não equivale a aprovação/publicação; não gera cobrança até a publicação explícita.

## Níveis de acesso e criação de contas (21/10/2026)

Papéis: `desenvolvedor`, `gestor`, `vendedor`. Desenvolvedor e gestor têm as mesmas permissões; referências antigas a “gestor” neste documento abrangem ambos. Restrições de organização e titularidade permanecem.

`GET /contas/criar/{role}` apresenta formulário administrativo; `POST` recebe `name`, `email`, `password` (6–1024 caracteres) e `csrf_token`. `{role}` aceita somente os três papéis. Sessão de gestor/desenvolvedor obrigatória, organização obtida do usuário autenticado, senha Argon2; sucesso 303, falta de autenticação no POST 401, proibição/CSRF 403, conflito 409, entrada inválida 422. Não é um endpoint público de autoinscrição.

Vendedor acessa APIs de produtos, filtros, comparações e planner com as restrições de titularidade existentes. APIs operacionais (dashboard/execuções, digitalização, lotes e lojas) retornam 403. Procedência dos arquivos importados é retirada das respostas de detalhes/comparações para vendedor. Mais informações em `NIVEIS_DE_ACESSO.md`.

## Cadastro via API — staging

Prefixo `/api/v1/cadastro-api`. Gestor da organização configurada; escopo por dono
do lote. POSTs exigem CSRF. Escopo: somente imagens e `_wcda_arquivos` de produtos existentes; dados comerciais ficam no fluxo CSV.

- `POST /`: multipart `empresa`, `arquivos` (ZIP), `identificacao` (`csv` padrão ou `folder`),
  `planilha` (CSV/XLSX/XLSM; obrigatória só em `csv`), `pasta_raiz` opcional.
  Persiste e enfileira prévia somente leitura.
- `GET /`: histórico dos últimos 100 lotes do usuário.
- `GET /{id}`: estados, arquivos identificados, quantidades existentes, Dry Run de arquivos, bloqueios, aprovação, auditoria, avisos/erros.
- `POST /{id}/aprovar`: JSON opcional `{"skus": [...], "replace_main": [...]}`; sem corpo aprova todos os prontos. Registra o hash do Dry Run, sem enfileirar nem autorizar escrita.
- `POST /{id}/confirmar`: somente itens aprovados com o mesmo hash, origem/SKU de staging autorizados.
- `POST /{id}/reprocessar`: refaz prévia dos erros, não repete uploads automaticamente.
- `GET /{id}/relatorio`: CSV sanitizado com imagens a enviar, documentos a incluir, bloqueios e aprovação.
- `GET /{id}/dry-run`: JSON do lote, sem caminhos locais nem credenciais.

Worker separado: `scripts/store_registration_worker.py`. As três URLs atuais estão
bloqueadas para escrita. Procedimento e limitações: [CADASTRO_API_STAGING.md](CADASTRO_API_STAGING.md).

## Integrações WooCommerce / WordPress — somente leitura remota

- `GET /api/v1/integracoes/lojas`: último diagnóstico de Choice, SAG e Portwell.
- `POST /api/v1/integracoes/lojas/{company}/testar`: executa somente GET nas APIs
  remotas e registra resultado sanitizado local. `company`: `choice`, `sag`, `portwell`.
- Exige sessão `gestor` vinculada ao `PRM_STORE_ORGANIZATION_ID`; POST exige CSRF.
  A prévia WooCommerce existente também respeita esse vínculo.
- Retorno separa `woocommerce` e `wordpress`, `authenticated`, `attempted`,
  permissões declaradas, status de mídia e `checked_at`. Nenhuma credencial ou
  conteúdo de produto é devolvido no diagnóstico.
- `not_configured` não é tentativa de autenticação; `public_endpoint` não comprova
  chave válida; identidade WordPress confirmada não comprova upload permitido.

Configuração, resultados reais e investigação de `wcda_arquivos`:
[INTEGRACOES_LOJAS.md](INTEGRACOES_LOJAS.md).

## Geração de Datasheets em Lote

Prefixo `/api/v1/digitalizacao/lotes`. Sessão obrigatória; lotes privados por
organização e usuário criador. POSTs exigem `X-CSRF-Token`. Não altera os endpoints
individuais de Digitalização nem publica produtos.

- `GET /modelo.csv`: modelo UTF-8 com BOM.
- `POST /`: multipart `arquivo` (ZIP) e `delimitador` (`,`, `;` ou tab); retorna validação por produto, sem IA.
- `GET /`: últimos 100 lotes do usuário.
- `GET /{id}`: itens, erros, contagens, modelo e progresso.
- `POST /{id}/iniciar`: enfileira apenas válidos; geração ocorre no worker.
- `POST /{id}/reprocessar`: somente itens com erro, preservando concluídos/revisão.
- `GET /{id}/produtos/{item}/pdf`: PDF individual disponível.
- `GET /{id}/download`: ZIP por empresa, relatório e erros.

Estados dos itens: `pending`, `invalid`, `queued`, `running`, `done`, `review`,
`error`. Lotes com arquivos removidos pela retenção: `expired`.
Contrato operacional, limites e worker em [DATASHEETS_EM_LOTE.md](DATASHEETS_EM_LOTE.md).

## Demonstração READ AI (sem API de IA)

`GET /api/v1/meeting-demo`: sessão de gestor da organização do artefato obrigatório, `Cache-Control: private, no-store`. Retorna `available`, `simulation`, datas, contagem de segmentos e sete cards com citações. Organização diferente recebe `available:false`; vendedor recebe 403. Endpoint independente da migração operacional, sem escrita no banco. Publicação administrativa local via `python -m scripts.publish_meeting_demo --transcript <TXT>`; valida hash exato e nunca substitui outro artefato silenciosamente.

## Reuniões e Planner — 16/10/2026 (staging)

Continuação: `POST /api/v1/planner/review` recebe `{items:[{id,version}],decision:"approved"|"rejected"|"draft",reason}`; até 100 IDs distintos, lote atômico, curador/gestor. `POST /api/v1/planner/activities/{id}/comments` recebe `{request_id:"UUID",text:"..."}`; até 2.000 caracteres, autor deve acessar o card. Retry com mesma chave/autor/card é idempotente; reutilizar chave com outro texto retorna 409. Comentários aparecem no histórico sem modificar a atividade.

Prefixo `/api/v1/planner`. Todas as rotas exigem sessão e escopo da organização; mutações exigem `X-CSRF-Token`. Sem migração, o módulo retorna 503. Contratos completos dos corpos no OpenAPI da aplicação.

- `GET /users`: usuários ativos elegíveis para atribuição (gestor: organização; vendedor: próprio usuário).
- `GET/POST /meetings`, `GET /meetings/{id}`; `PATCH /meetings/{id}/metadata` e `/participants` com versão esperada.
- `POST /meetings/{id}/transcripts`, `/txt`, `/audio`, `/transcriptions`, `/analyses`: entrada/revisão e enfileiramento. Análise externa exige consentimento explícito; áudio não é enviado ao provedor.
- `GET /audio/{id}`: player privado, com autorização da reunião e suporte a ranges.
- `POST /runs/{id}/cancel`, `/retry`, `/cards/build`: etapas separadas, sem refazer análise para gerar cards.
- `GET /activities`: paginação `offset/limit` (100 padrão, 200 máximo), filtros `assignee/status/meeting/partner/mine/approval/owner/opportunity/band/bucket/undated`.
- `GET /activities/overview`: faixas e histograma com denominador explícito. `GET /activities/calendar?start=AAAA-MM-DD&end=AAAA-MM-DD`: fim exclusivo, máximo 62 dias; `include_proposals=true` inclui rascunhos/aprovados datados, sem alterar indicadores.
- `GET/PATCH /activities/{id}` e `POST /activities/{id}/review`: edição com `version/reason`, aprovação/rejeição; conflito retorna 409.
- `POST /assign`: `{items:[{id,version}],assignee_user_id,reason}`; até 100 itens, lote atômico e autorização por item. `POST /publish`: `{items:[{id,version}]}`; só cards aprovados com usuário ativo e prazo/aceite sem prazo, eventos exigem data.
- `POST /export`: `{ids:[...],format:"json"|"csv"}`; acesso validado por card. JSON `card_export_schema_version=1.0`, `exported_at`, `count`, `cards`; evidências/transcrição excluídas. CSV neutraliza fórmulas.
- `GET /alerts`, `POST /alerts/{id}/read`: somente destinatário, sem geração de alerta no GET.

Os caminhos acima são relativos ao prefixo. Guia, evidências e limitações: [REUNIOES_PLANNER.md](REUNIOES_PLANNER.md).

## Indicadores de atributos — 14/10/2026

`GET /api/v1/dashboard/summary` mantém schema 2 e acrescenta `attribute_analysis` (null para snapshots anteriores). `sources` informa contagens de interpretação de memória/armazenamento/USB e reconhecimento de SO. `competitors` informa `total`, `with_os`, `missing_os`, `equivalent`, `different`, `inconclusive`, `equivalent_percent_total` e `equivalent_percent_assessed` (null sem comparáveis). O escopo `os_attribute_same_family_own_public` compara somente o conjunto de famílias de SO com produtos próprios visíveis da mesma família de produto. Não representa cobertura técnica integral; `strict_coverage_percent` continua null. Política: `os-families-v2`.

## Atributos canônicos da base refinada

As observações persistidas no snapshot atual incluem `attribute_code`, `canonical_label`, `mapping_version`, `normalized_value`, `value_type`, `unit`, `configuration_scope`, `knowledge_state`, `raw_name`, `raw_value` e evidências. A matriz HTML `/comparacao-atual` alinha código/escopo/unidade, não nomes brutos. Contrato e aliases: [NORMALIZACAO_ATRIBUTOS.md](NORMALIZACAO_ATRIBUTOS.md). Nenhum endpoint legado passa a operar automaticamente sobre esses snapshots; o resumo do dashboard continua no schema 2. Normalização de campo não significa equivalência do produto.

## Fotografia refinada de 09/10/2026

Navegação de comparação atual (HTML autenticado): `/catalogos?source=eco|dimensional&group=shared|not_found|review` filtra os grupos dos gráficos. `group=quality_review` lista qualquer registro com alerta de qualidade. `source=own` restringe a Portwell/Choice. Grupos dos gráficos são sinais de família, não equivalência; `review` filtra família desconhecida, não todos os alertas.

`reference=UUID&run_id=RUN` mantém um produto de referência ao escolher candidatos no catálogo. `/comparacao-atual?run_id=RUN&item=UUID&item=UUID` aceita de 2 a 8 UUIDs distintos do snapshot vigente, valida escopo/visibilidade e mostra matriz exploratória. IDs ausentes/inacessíveis: 404; seleção inválida ou snapshot alterado: 422. Só gestores acessam itens internos/preços ocultos. Rotas GET não persistem decisão de equivalência. Seleções usam UUIDs canônicos, não IDs de ofertas legadas.

A nova base publicada é exibida em `/catalogos` (HTML autenticado), usando os snapshots `refined_catalog_*` da organização, com 100 itens por página. Parâmetros: `source` (`portwell`, `choice`, `eco`, `dimensional`), `family`, `q` (título), `page`, `internal=1` (somente gestor). `/catalogos?view=legacy` abre a base anterior. Visão geral, Comparador e Importações distinguem a fotografia nova de indicadores históricos.

`GET /api/v1/dashboard/summary` usa exclusivamente o snapshot oficial da organização e retorna **schema_version=2**, `status`, `run_id`, `accepted`, `public`, `own_public`, `sources`, `competitors`, `technical_status` e `strict_coverage_percent`. `competitors` contém distribuição por família: `total`, `shared_family`, `family_not_found`, `family_pending` e percentuais com todos os registros no denominador. Não significa equivalência. Sem snapshot, retorna `status=no_current_snapshot`, `run_id=null`, sem indicadores antigos. Clientes do contrato anterior do resumo precisam migrar.

Os demais endpoints `/api/v1` de ofertas/comparação **continuam sendo contratos legados**, não os novos UUIDs canônicos. Não enviar IDs do snapshot para comparação direta legada. Nova comparação técnica/coverage API está pendente. Operação e limites: [CATALOGOS_REFINADOS.md](CATALOGOS_REFINADOS.md).

Base versionada: `/api/v1`.

## Endpoints implementados

| Método e rota | Autenticação | Resultado |
|---|---|---|
| `GET /api/v1/health/live` | não | `{"status":"ok"}` se o processo responde |
| `GET /api/v1/health/ready` | não | estado sanitizado da dependência PostgreSQL |
| `POST /api/v1/auth/login` | não | autentica JSON, cria sessão e retorna o usuário |
| `GET /api/v1/auth/me` | sessão | dados mínimos do usuário atual |
| `POST /api/v1/auth/logout` | sessão + cabeçalho `X-CSRF-Token` | revoga a sessão |
| `GET /api/v1/dashboard/summary` | sessão | indicadores, empresas, disponibilidade e marcas |
| `GET /api/v1/filters/options` | sessão | empresas, marcas, disponibilidades e modalidades |
| `GET /api/v1/products` | sessão | ofertas paginadas e filtradas |
| `GET /api/v1/products/{uuid}` | sessão | detalhes, preços e origem da oferta |
| `GET /api/v1/comparisons/preview` | sessão | comparação exploratória de 2–8 ofertas, preços e matriz técnica |
| `POST /api/v1/comparisons` | sessão + `X-CSRF-Token` | salva comparação e referência opcional como `nao_avaliado` |
| `GET /api/v1/comparisons/{uuid}` | autor ou gestor | recupera comparação persistida |
| `GET /api/v1/catalog-matches` | sessão | última análise integral, cobertura, candidatos e preços; aceita `company` e `limit` |
| `GET /api/v1/catalog-gaps` | sessão | possíveis lacunas da última análise, agrupadas por marca e família; aceita `company`, `gap_type`, `gap_key` e `page` |
| `GET /api/v1/comparable-portfolio` | sessão | amplitude taxonômica do retrato CSV, com `macro`, `signal` e `page` |

Exemplo de login (sem credenciais reais):

```json
{"email":"gestor@exemplo.local","password":"senha-definida-localmente"}
```

Cookies de sessão são HttpOnly; tokens, hashes e detalhes de conexão nunca aparecem na resposta. O logout por API recebe o cabeçalho `X-CSRF-Token`; o formulário HTML envia o campo oculto equivalente.

## Estados HTTP

- `401`: credenciais ou sessão inválidas.
- `403`: CSRF inválido ou permissão insuficiente.
- `404`: recurso/rota desconhecida.
- `422`: corpo inválido.
- `503`: configuração ou conexão de banco indisponível em rota persistente.

## Filtros de produtos

`GET /api/v1/products` aceita `q`, múltiplos `company`, múltiplos `brand`, múltiplos `availability`, `family_group`, `modality`, `price_min`, `price_max`, `page` e `page_size`. O padrão é **100 produtos por página**; também são aceitos 24, 48 e 200. Valores da mesma faceta usam OU; facetas diferentes são combinadas com E. Até oito termos separados por espaço em `q` precisam aparecer todos, mas podem estar em campos diferentes. A busca inclui código, nome, marca canônica/bruta, descrição, aplicação, categoria e título/família/modelo tratados; `%` e `_` são texto literal, não curingas. `GET /api/v1/filters/options` lista `family_groups` disponíveis.

Selecionar somente `modality` retorna ofertas com preço válido nessa modalidade. Com `modality` vazia (“Todas”), `price_min` e `price_max` aceitam qualquer uma das modalidades `venda`, `pix` ou `cartao`, desde que **a mesma modalidade** satisfaça ambos os limites. Sem faixa e sem modalidade, produtos sem preço continuam visíveis. Os limites devem ser não negativos e `price_min <= price_max`; caso contrário, a API devolve 422. Filtros em branco não restringem os resultados. Exclusões analíticas ficam fora por padrão e somente gestor pode solicitar `include_excluded=true`. A página HTML aceita vírgula decimal no preço; a API usa número decimal JSON/query padrão.

Empresas próprias precedem as demais nas respostas ordenadas. A prévia aceita de 2 a 8 parâmetros repetidos `offer` e o parâmetro opcional `reference`, que obrigatoriamente deve ser uma das ofertas. A página HTML `/comparacao-direta` usa os mesmos parâmetros; o catálogo oferece seleção persistida entre páginas no navegador. O botão abre primeiro `/static/direct-comparison.html`, que funciona com um processo web ainda não reiniciado e redireciona para `/comparacao-direta` quando a rota estiver ativa. A versão estática usa a API de detalhes para preços e características declaradas; a rota completa acrescenta o enriquecimento do pipeline. O `POST` usa os campos `offer_ids` e `reference_offer_id`. A diferença percentual só existe quando a oferta e a referência têm preço positivo na mesma modalidade; nunca é chamada de margem e nunca confirma equivalência automaticamente. A matriz técnica da rota completa inclui campos do catálogo, atributos estruturados revisáveis e características do enriquecimento do pipeline, com origem distinguível.

`GET /api/v1/catalog-matches` é o fluxo principal da interface. `summary.coverage_percent` considera apenas relações `confirmado` ou `sugerido`; candidatos de menor confiança aparecem separadamente em `candidate_percent`. A análise de preço usa nosso preço preferencial como base. Quando as modalidades diferem, a resposta marca `same_modality=false`: o percentual é nominal e não representa margem ou igualdade de condições.

`GET /api/v1/dashboard/summary` inclui `treated_offers`, `pipeline_offers` e `treatment_percent` no recorte ativo não excluído. Cada item de `company_counts` inclui `treated_count`, `pipeline_count` e `treatment_percent`. A contagem do pipeline refere-se ao enriquecimento publicado em `offer_enrichments`, não ao número de linhas do XLSX original. `GET /api/v1/catalog-matches` inclui `own_portfolio`, com `confirmed`, `suggested` e `strong_count` por empresa própria para a execução selecionada. A soma de `strong_count` corresponde a `summary.coverage_count`, pois considera apenas o par principal de cada produto concorrente.

Nos objetos `competitor` e `own` dessa resposta, `brand` é a marca canônica resolvida pelo cadastro de aliases e `brand_raw` é o valor original da planilha. Por exemplo, uma oferta Choice declarada como `NEW ELFIN SRL` retorna `brand: "ELFIN"` e `brand_raw: "NEW ELFIN SRL"`. O motivo `brand_equal` compara as formas canônicas.

Desde `lexical-v1.3`, os `reasons` da análise podem incluir modelos explícitos compartilhados, grupo de família e atributos técnicos concordantes ou conflitantes. Eles descrevem evidência para revisão, não certificação de equivalência. A API de detalhes de produto ainda apresenta os dados originais; a camada de enriquecimento tem proveniência no banco e é usada pelo pareador, mas não possui endpoint próprio nesta etapa.

`GET /api/v1/catalog-gaps?company=eco-automacao` considera ofertas ativas e não excluídas do concorrente selecionado que não têm candidato, sugestão ou confirmação principal na última execução concluída. `summary.unmatched_total` deve conciliar com `catalog-matches.summary.no_candidate` enquanto o catálogo e a execução estiverem sincronizados. `summary.absent_brand_total` conta esses produtos cuja marca canônica não possui oferta ativa no portfólio próprio; `summary.family_absent_total` conta os que têm família tratada sem a mesma família cadastrada nas nossas ofertas. As duas contagens se sobrepõem e não devem ser somadas. Marcas ausentes ou não identificadas são tratadas separadamente.

`brands` e `families` mostram os oito maiores grupos, com até três exemplos; `brand_options` e `family_options` listam todas as opções para seleção. Para abrir um grupo, informe `gap_type=brand` com `gap_key` igual ao UUID da marca, ou `gap_type=family` com `gap_key` igual ao nome exato da família. `selected.items` traz 24 produtos por página, identificados por UUID/código/nome. Os campos são evidências para investigação, não comprovação de que a empresa não trabalha com uma marca ou de que falta um produto equivalente. A família é aproximação de segmento/aplicação porque o catálogo Eco não possui campo de aplicação estruturado para a maioria das ofertas.

`summary.stale=true` indica importação publicada após a execução de correspondência ou divergência entre o total atual sem candidato e o total da execução. Nesse caso, recalcule o pareamento antes de interpretar os grupos.

`GET /api/v1/comparable-portfolio` retorna `metrics.family_overlap_percent`, contagens de ofertas Eco em famílias compartilhadas ou sem família própria, `snapshot.quality` e a página de 25 famílias. `signal` aceita `sem_familia_propria`, `familia_compartilhada` ou `so_nossas`; `macro` usa o nome exato da macrocategoria. `snapshot.stale` aponta alteração das contagens publicadas desde a geração. O retrato é uma comparação de **famílias**, não de equivalências ou preços, e tem metodologia em [`COMPARACAO_NORMALIZADA.md`](COMPARACAO_NORMALIZADA.md).
