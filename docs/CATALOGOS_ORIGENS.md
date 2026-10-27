# Catálogos — Nossa base e Concorrência

Implementação de 27/10/2026 no worktree `PRM-remocao-cargos`.

## Modelo e identidade

Reutiliza `Company.company_type`: `nossa` corresponde a `source_group=internal`;
`concorrente` corresponde a `source_group=competitor`. Não há tabela paralela de
concorrentes nem duas identidades para a mesma empresa. `Offer.company_id` identifica
a origem em ambos os casos. A organização é validada no backend em cada operação.

A chave existente `UNIQUE(company_id, external_code)` separa SKUs iguais de Choice,
Portwell, SAG e cada concorrente. Empresas têm identidade própria por organização.
Não há união por nome, SKU global ou promoção automática de concorrentes a internos.
O cadastro de concorrente nunca permite escolher `company_type=nossa`.

## Uso

1. Abra `/catalogos` e expanda **Importar catálogo · Nossa base / Concorrência**.
2. Escolha o grupo e uma empresa ativa da organização. Gestor/desenvolvedor pode
   criar um concorrente pelo nome e site opcional. Empresas internas vêm do cadastro
   existente; não são criadas por este fluxo.
3. Envie CSV, XLSX ou XLS. Limite padrão: **50 MiB**, configurável por
   `PRM_CATALOG_UPLOAD_MIB` (1 a 100). Até `PRM_MAX_IMPORT_ROWS` linhas, padrão 50.000.
4. Se houver várias abas, escolha uma e leia novamente. Informe a linha do cabeçalho.
5. Confira o mapeamento sugerido. SKU/código e nome são obrigatórios; preço não é.
   Cada coluna é mapeada uma vez; colunas não selecionadas são ignoradas.
6. Prepare a prévia: novos, atualizados, sem mudança/ignorados e erros. Confira a
   amostra e as primeiras 100 linhas com erros. Nada é publicado nesta etapa.
7. Confirme explicitamente. Linhas inválidas não são publicadas. Escolha adicionar
   e atualizar, somente adicionar, ou somente atualizar. Não há exclusão em massa.

CSV aceita UTF-8/BOM e separador vírgula, ponto e vírgula ou tabulação. Excel usa
`openpyxl`/`xlrd`, sem executar fórmulas ou macros; valores calculados previamente
podem ser lidos. Para preservar zeros à esquerda, mantenha SKU como **texto** no Excel.
Preços reutilizam o parser do PRM (BRL/decimal); Pix, cartão e venda são modalidades
distintas. Zero mantém a regra anterior de preço não informado. Disponibilidade
normalizada conserva o texto original.

## Catálogo e comparações

- `/catalogos`: análise publicada existente, com filtro de origem e identificação
  Nossa base/Concorrência. Links dos produtos próprios direcionam aos concorrentes
  e vice-versa. Nenhum snapshot é substituído pela importação operacional.
- `/catalogos?view=legacy`: **catálogo cadastrado**, incluindo novas importações e
  ofertas históricas preservadas. Filtre origem e empresas, selecione 2–8 produtos
  e abra a comparação direta. O link de conclusão abre esta tela na origem importada.
- API de produtos aceita `source_group=internal|competitor`, combinado com `company`.
- Comparador automático existente continua restringindo os lados por `company_type`.
  A comparação manual interna continua disponível, sem rotular outra empresa própria
  como concorrente. Novos imports não recalculam automaticamente execuções históricas.

## Persistência, permissões e segurança

Correção CSRF de 27/10/2026: o frontend lê `input[name="csrf_token"]` do template
a cada chamada, como Cadastro via API, e envia `X-CSRF-Token` com
`credentials: same-origin` e `cache: no-store`. Não lê cookie por nome fixo:
o ambiente ativo usa `prm_docker_csrf`. O template já usa a configuração do servidor.
O helper é comum à leitura, prévia, confirmação e criação de concorrente.
19 testes Python e 1 JS passaram para esta correção. Asset `20261027-csrf`.
Overlay adicional `compose.catalogos-csrf.yaml`, imagem `prm:catalog-csrf-20261027`;
rollback desta correção remove somente esse último overlay e recria apenas `api`.

Modelos reutilizados: Company, Offer, CatalogImport, ImportRow, OfferObservation,
OfferPrice, Brand/BrandAlias, Category, OfferEnrichment. **Sem migration**.
O histórico registra grupo, origem, nome do arquivo, usuário, data, contagens e status;
novas importações guardam a origem também no `mapping` para conservar sua identificação.

Importar/criar concorrente/consultar histórico exige gestor ou desenvolvedor.
Mutações exigem CSRF. O backend confere origem, tipo, empresa ativa e organização,
independentemente do formulário. O upload usa chunks e diretório temporário removido
em sucesso ou erro. O arquivo não é publicado em `static` nem acessado por URL externa.
Limites de linhas, colunas e tamanho descompactado restringem Excel.

Prévia inclui uma impressão dos dados, opções e estado atual da origem. Mudanças
entre prévia e confirmação exigem nova prévia (409). Publicações pelo serviço existente
serializam por empresa. A transação reverte alterações em falha; erros de validação
antes de publicar não criam um registro de importação. Arquivo com o mesmo SHA-256
na mesma origem mantém a idempotência existente: não é importado novamente, mesmo
mudando o mapeamento; revise o arquivo antes de uma nova importação.

## Arquivos principais

- `app/services/catalog_origin.py`, `catalog_table.py`, `catalog_import.py`.
- `app/routers/catalog_imports.py`, `catalog.py`, `pages.py`; `app/main.py`, `config.py`.
- `app/repositories/catalog.py`, `app/services/refined_catalog_database.py`.
- `app/templates/_catalog_import.html`, `_refined_catalog.html`, `_current_comparison.html`, `shell.html`.
- `app/static/js/catalog-import.js`.
- `tests/test_catalog_origin_import.py`, `tests/js/catalog-import.test.cjs`.
- `requirements.txt` (`xlrd` para XLS), `.env.example`, documentação e overlay da API.

Não houve importação real, alteração em loja, alteração de credenciais, commit, push
ou merge. Os dados e o design system existente foram preservados.

## Validação e publicação

- Suíte completa na imagem isolada, sem rede: **880 passed, 28 skipped**. Ignorados
  dependem principalmente de fixtures privadas; os testes JS não rodam na imagem sem Node.
- Após ajustes finais: **39 testes Python relacionados passed**, incluindo importação,
  filtros, tipos de origem, snapshots/isolamento, comparação e design system.
- `node --test tests/js/catalog-import.test.cjs`: **1 passed**. DOM/API simulados;
  não houve sessão de navegador autenticada nem importação de arquivo real.
- `node --check app/static/js/catalog-import.js` e `git diff --check`: aprovados.
- Imagem final: `prm:catalog-origin-test`, manifesto
  `sha256:c5aa06c7f2c9c52cef0b2c920924dd729c4470cd424d06a77fa910dec7c1f600`.
- Overlay `compose.catalogos-origens.yaml` adicionado **após os overlays ativos**,
  incluindo `compose.design-system.yaml`. Somente serviço `api` recriado com
  `up -d --no-deps --no-build --pull never --wait api`. ID novo: `62aa8eedd940`.
- Demais containers conservaram IDs. Nenhuma migration ou importação executada no deploy.
- Teste em `http://localhost:8001/catalogos`. Use **Ctrl+F5** e uma conta gestora ou
  desenvolvedora para acessar a importação.

Rollback: reaplicar os mesmos arquivos Compose ativos, retirando apenas
`compose.catalogos-origens.yaml`, e recriar somente `api` com `--no-deps`.
Isso restaura `prm:design-system-20261026b`; não remove dados nem volumes. Não executar
`down -v`. Alterações funcionais anteriores e o checkout original não foram sobrescritos.

## Publicação da base oficial (Offer → snapshot) — 27/10/2026

A importação grava em `Offer` e **nunca publica sozinha**. Comparador, Visão geral e Importações leem apenas o snapshot
publicado (`RefinedCatalogRun`/`RefinedCatalogItem`). A ponte é explícita e revisada (`app/services/catalog_publication.py`):

1. `/importacoes` (ou `/catalogos`, `/comparador`) → painel **Base oficial de comparação** (gestor/desenvolvedor).
2. **Revisar análise para publicação** (`POST /api/v1/catalog-imports/publication/preview`): gera a prévia em memória,
   sem gravar, com contagens por empresa (Nossa base × Concorrência) e um hash de todo o conteúdo (`version`).
3. **Publicar base atual / Atualizar análise publicada** (`POST /api/v1/catalog-imports/publication` com `version`).

- Lê `Offer` ativos e não excluídos das empresas ativas da organização, preços (`OfferPrice`), atributos revisados
  (`OfferAttribute`) e de enriquecimento por regra (`OfferEnrichment.attributes`), marca canônica e linha original.
- Normalização/famílias reutilizam `refined_catalog.normalize_record`. Origens: `portwell`, `choice`, `sag`, `eco`,
  `dimensional` quando o código da empresa corresponde; demais empresas recebem código curto estável. Empresas internas
  (`nossa`) nunca são concorrentes entre si; exige ao menos uma interna e uma concorrente.
- Consistência: lock consultivo por organização (o mesmo tomado pelas importações e criação de concorrentes), `version`
  da prévia conferida sob o lock (importação nova entre prévia e confirmação ⇒ 409) e reconferida após gerar os itens.
  A nova execução é ativada na mesma transação que arquiva a anterior: qualquer falha faz rollback e a anterior segue válida.
  Base inalterada ⇒ idempotente (retorna a execução vigente).
- Auditoria no manifesto (`audit`): usuário (id e nome), organização, data/hora, quantidade interna e concorrente,
  empresas incluídas e lotes de importação de origem. Execuções anteriores ficam como `archived`.
- Situação nas páginas (`publication_status`) usa só agregados (≈0,1 s); a captura completa (≈8 s + ≈7 s de
  normalização para ~19 mil ofertas) roda apenas na prévia e na publicação. Sem migração.

Painéis do dashboard, catálogo publicado e comparação passaram a usar o registro de origens do snapshot (nomes e
grupos), não códigos fixos. O mapa de atividades/digitalização da Visão geral aparece mesmo sem snapshot de catálogo.
