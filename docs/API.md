# API

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
| `GET /api/v1/comparisons/preview` | sessão | comparação exploratória de 2–4 ofertas, preços e matriz técnica |
| `POST /api/v1/comparisons` | sessão + `X-CSRF-Token` | salva comparação e referência opcional como `nao_avaliado` |
| `GET /api/v1/comparisons/{uuid}` | autor ou gestor | recupera comparação persistida |
| `GET /api/v1/catalog-matches` | sessão | última análise integral, cobertura, candidatos e preços; aceita `company` e `limit` |

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

`GET /api/v1/products` aceita `q`, múltiplos `company`, múltiplos `brand`, múltiplos `availability`, `modality`, `price_min`, `price_max`, `page` e `page_size` (24 ou 48). Valores da mesma faceta usam OU; facetas diferentes são combinadas com E. Faixa de preço só é aplicada quando a modalidade é explícita. Exclusões analíticas ficam fora por padrão e somente gestor pode solicitar `include_excluded=true`.

Empresas próprias precedem as demais nas respostas ordenadas. A prévia aceita parâmetros repetidos `offer` e o parâmetro opcional `reference`, que obrigatoriamente deve ser uma das ofertas. O `POST` usa os campos `offer_ids` e `reference_offer_id`. A diferença percentual só existe quando a oferta e a referência têm preço positivo na mesma modalidade; nunca é chamada de margem e nunca confirma equivalência automaticamente.

`GET /api/v1/catalog-matches` é o fluxo principal da interface. `summary.coverage_percent` considera apenas relações `confirmado` ou `sugerido`; candidatos de menor confiança aparecem separadamente em `candidate_percent`. A análise de preço usa nosso preço preferencial como base. Quando as modalidades diferem, a resposta marca `same_modality=false`: o percentual é nominal e não representa margem ou igualdade de condições.

Nos objetos `competitor` e `own` dessa resposta, `brand` é a marca canônica resolvida pelo cadastro de aliases e `brand_raw` é o valor original da planilha. Por exemplo, uma oferta Choice declarada como `NEW ELFIN SRL` retorna `brand: "ELFIN"` e `brand_raw: "NEW ELFIN SRL"`. O motivo `brand_equal` compara as formas canônicas.
