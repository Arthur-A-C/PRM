# API

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
