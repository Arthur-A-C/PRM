# Dados

## Fonte inicial

`data/imports/produtos_ecoautomacao.xlsx`, aba `Produtos`, é a fonte autoritativa inicial. O arquivo real não é versionado nem modificado pela aplicação.

- SHA-256 conferido: `1dbb6be1da1f7f89746638ff3214070e2ad9f6ff949321623a8b4cb393ccca5d`.
- 7.945 linhas de produto e oito campos: `Codigo`, `Nome`, `link`, `Marca`, `Preco_pix`, `Preco_cartao`, `Estoque`, `Descricao`.
- 7.945 códigos e URLs distintos; 169 marcas e uma descrição ausentes.
- 7.333 preços positivos e 612 zeros em cada modalidade.
- Disponibilidade: 1.670 `Em estoque`, 6.221 `Fora de estoque`, 54 `https://schema.org/BackOrder`.

## Regras já confirmadas para a Fase 2

- A empresa ofertante é Eco Automação; marca/fabricante é outro conceito.
- Código permanece texto e a chave natural é empresa + código externo.
- Preço zero é preservado no bruto e normalizado como não informado, nunca grátis.
- `BackOrder` será `sob_encomenda`, mantendo o texto bruto.
- A linha Excel 2, código `4574`, permanece na auditoria e terá exclusão analítica reversível.
- Texto limpo é separado do original; conteúdo da planilha nunca é HTML confiável.
- Data observada começa desconhecida e BRL só é gravado como escolha do operador.
- Contagens com relações multivaloradas usarão ofertas distintas. Facetas combinarão OU dentro da mesma faceta e E entre facetas; a contagem de uma faceta ignora apenas ela mesma.

## Cadastros iniciais

O comando do primeiro gestor cria Eco Automação, Portwell e Choice Tech. Conforme esclarecido pelo operador em 22/09/2026, Portwell e Choice Tech são empresas `nossa`; Eco Automação é `concorrente`. Os três arquivos reais foram publicados após prévia e migração da Fase 2.

### Prioridade de apresentação

Empresas com `company_type=nossa` aparecem sempre antes das demais em menus, filtros, listas, dashboard e comparador. Dentro de cada grupo, a ordem é alfabética. A regra usa o tipo cadastrado, portanto novas empresas próprias herdam o destaque e novas concorrentes ficam no grupo “Outras empresas”. Isso altera somente apresentação/ordenação, nunca contagens ou resultados dos filtros.

## Novos catálogos recebidos

### Portwell

- Arquivo: `produtos-portwell.xlsx`.
- SHA-256: `083f0f2b290f0316feb2410ab5b471b784c96b961bf6dfab49e828b6a69b74b9`.
- Aba `Export`, cabeçalho na linha 1, 10.961 linhas brutas.
- 10.955 ofertas publicáveis e seis linhas rejeitadas: três códigos repetidos e três linhas sem nome; uma destas também não tem código.
- Duplicidades: `311006000015` (linhas 7498/7499), `312001000032` (10430/10431) e `317010000010` (10868/10869).
- Entre as ofertas publicáveis: 10.788 preços de venda positivos, 167 não informados, 529 com estoque positivo e 10.426 com estoque zero/não positivo.

### Choice Tech

- Arquivo: `produtos-choice.xlsx`.
- SHA-256: `e5a2eb368f6d40749fd63a6988c48f05552d608f6aed39918146c70036b2eab3`.
- Aba `Sheet1`, cabeçalho detectado na linha 3, 16.894 linhas brutas.
- 16.886 ofertas publicáveis e oito linhas rejeitadas por nome ausente.
- Entre as ofertas publicáveis: 14.805 preços de venda positivos, 2.081 não informados, 3.117 com estoque positivo e 13.769 com estoque zero/não positivo.

### Mapeamento ERP de Portwell/Choice

| Origem | Destino |
|---|---|
| `Cód. Material` | código externo textual |
| `Descrição Material` | nome original |
| `Cód. Fábrica` / `Referência Material` | código do fabricante / referência |
| `Fabricante` | marca normalizada e valor bruto |
| `Desc. Grupo` / `Desc. Subgrupo` | categoria sugerida / subcategoria bruta |
| `Aplicação Material` | descrição/aplicação declarada |
| `Estoque Atual` | quantidade e disponibilidade normalizada |
| `Preço Venda` | preço na modalidade `venda` |
| `UN`, `Fornecedor`, `País` | unidade e campos de origem preservados |

BRL é configuração do operador, não conteúdo comprovado da planilha. `Data Cadastro` não é tratada como data da observação de preço/estoque. Linhas inválidas e duplicadas são preservadas na auditoria, mas não viram ofertas.

## Semântica do comparador

- A referência de preço é sempre escolha explícita do usuário e precisa pertencer ao conjunto comparado.
- A diferença é `(preço da oferta - preço da referência) / preço da referência * 100`, somente com valor positivo e dentro da mesma modalidade.
- Venda, Pix e cartão nunca são convertidos entre si. Ausente continua “não informado”; não vira zero.
- A matriz inicial inclui campos declarados dos catálogos. Atributos normalizados mantêm valor tipado, unidade, evidência, método e estado de revisão.
- “Igual” descreve igualdade textual/numérica do campo; não significa produto equivalente. Unidades numéricas conflitantes são “incompatíveis” e não são convertidas automaticamente.

## Marcas canônicas e aliases

A migração `20260922_0006` introduziu `brand_aliases`. A importação consulta esse cadastro antes de criar uma marca, e a correspondência compara o nome canônico. O valor declarado na fonte continua em `offers.brand_raw`, portanto a consolidação não apaga evidência.

O primeiro caso revisado consolida `ELFIN` e `NEW ELFIN SRL` sob a marca canônica `ELFIN`: 14 ofertas vieram como `ELFIN` e 447 como `NEW ELFIN SRL`. O banco passou de 420 para 419 marcas canônicas e possui 2 aliases revisados. Novas variantes devem ser cadastradas explicitamente; similaridade textual isolada não funde marcas automaticamente.

## Correspondência automática integral

O algoritmo local `lexical-v1.2.1` prepara nomes, descrições, marcas canônicas, referências e códigos do fabricante. Um índice invertido recupera somente candidatos que compartilham termos informativos; a pontuação combina modelo/código, termos do nome, similaridade textual, cobertura e marca. Medidas e características genéricas como tensão, dimensão, decibéis e grau IP são removidas da lista de identificadores de modelo.

- Pontuação a partir de `0,68` e ao menos um modelo/código compartilhado: `sugerido`, ainda sujeito a revisão humana.
- Pontuação entre `0,38` e `0,68`: `candidato`, separado da cobertura principal.
- Abaixo de `0,38`: nenhuma relação persistida.
- Só `confirmado` e `sugerido` entram na porcentagem principal de cobertura; candidatos aparecem em indicador separado.
- Uma nova execução não apaga o histórico anterior.
- Na análise automática, nosso preço preferencial é a base: `(preço concorrente - preço nosso) / preço nosso * 100`. Positivo indica nosso preço abaixo do concorrente; negativo, acima. Se as modalidades diferirem, o resultado é explicitamente nominal.

Execução Eco `lexical-v1.2.1`: 7.944 produtos analisados contra 27.841 ofertas próprias; 9 sugestões fortes (0,11%), 304 candidatos adicionais e 7.631 sem candidato acima do limiar. Esses números refletem o algoritmo, não equivalências humanas confirmadas.
