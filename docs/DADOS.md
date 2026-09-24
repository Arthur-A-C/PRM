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

## Saídas tratadas recebidas em 23/09/2026

Os três arquivos `Produtos-Choice.xlsx`, `Produtos-Portwell.xlsx` e `Produtos-ECO.xlsx`, recebidos junto de `PRM_Pipeline.zip`, foram inspecionados sem executar código do ZIP. As saídas foram copiadas, com hash conferido, para `data/imports/treated/` (pasta local ignorada pelo Git). Os arquivos brutos já publicados, preços, linhas de auditoria e descrições originais foram preservados. A planilha Eco tratada não contém a descrição bruta; substituí-la integralmente faria perder esse dado. Seus resultados de cruzamento pré-calculados também não são importados, pois cobrem apenas a Choice, enquanto a aplicação compara todas as empresas próprias.

| Saída tratada | Aba | Linhas | SHA-256 | Ofertas associadas |
|---|---|---:|---|---:|
| Choice | `Base_PRM` | 16.894 | `43c77a20f1aa556ac4f2641c020fec587921ef69359dc5ee2512d816f1392c82` | 16.886 |
| Portwell | `Base_PRM` | 10.960 | `cd52a69ed6b1cb9462a13e747cb8a41fa2d3a9ec3024fdce38a09dda0a1b0b63` | 10.955 |
| Eco | `Base_ECO` | 7.945 | `9b4f2b4edd0c83870c8bc8ae7e4712cac1b0b9d0551b1db05f7ca98b5e4d179d` | 7.945 |

A migração `20260923_0007` adicionou `offer_enrichments`, uma camada por oferta com família/grupo, modelo, título normalizado, códigos de busca, atributos técnicos, confiança e proveniência (arquivo, SHA-256, linha). A associação exige ao menos 90% dos códigos da saída presentes na empresa selecionada. As oito linhas Choice sem nome, duas linhas Portwell inválidas e três duplicidades Portwell não criam ofertas novas. A relação é sempre por empresa + código externo, nunca por posição de linha.

O importador bruto cria ou atualiza automaticamente um tratamento determinístico e conservador antes de recalcular o comparador. Ele extrai apenas sinais verificáveis do texto disponível, incluindo família, modelo, tensão e grau IP; não inventa especificações ausentes. Se a saída tratada for publicada, seus campos substituem o tratamento de regra para a mesma oferta, mantendo os campos brutos e preços intactos. Uma reimportação que altera somente preço conserva o enriquecimento; mudança de conteúdo relevante invalida o enriquecimento anterior e aplica novamente as regras locais até que uma nova saída tratada seja publicada. O comando de publicação é `python -m scripts.import_pipeline_enrichment --company <codigo> --commit`; a prévia omite `--commit`.

O ZIP contém etapas externas de enriquecimento e cruzamento, inclusive dependências e acesso a fontes fora da aplicação. Seus métodos determinísticos pertinentes foram adaptados; raspagem externa, arquivos `pickle` e o cruzamento Choice-only do ZIP não são executados nem necessários no fluxo operacional. Para obter a mesma riqueza de atributos em catálogos futuros, produza uma nova saída tratada e publique-a pelo comando acima. O fallback automático de texto bruto é propositalmente menos completo.

## Correspondência automática integral

O algoritmo local `lexical-v1.3` prepara nomes, descrições, marcas canônicas, referências, códigos do fabricante e os sinais tratados. Um índice invertido recupera candidatos que compartilham termos informativos; a pontuação combina modelo/código, termos do nome, similaridade textual, cobertura, marca, família e atributos compatíveis. Conflitos em atributos críticos impedem sugestão forte. Medidas e padrões genéricos como tensão, dimensão, decibéis, grau IP, CAT5E e AWG não são identificadores de modelo.

- Pontuação a partir de `0,68` e ao menos um modelo/código compartilhado: `sugerido`, ainda sujeito a revisão humana.
- Pontuação entre `0,38` e `0,68`: `candidato`, separado da cobertura principal.
- Abaixo de `0,38`: nenhuma relação persistida.
- Só `confirmado` e `sugerido` entram na porcentagem principal de cobertura; candidatos aparecem em indicador separado.
- Uma nova execução não apaga o histórico anterior.
- Na análise automática, nosso preço preferencial é a base: `(preço concorrente - preço nosso) / preço nosso * 100`. Positivo indica nosso preço abaixo do concorrente; negativo, acima. Se as modalidades diferirem, o resultado é explicitamente nominal.

Os números da execução atual ficam em `STATUS.md`. Resultados são algorítmicos, não equivalências humanas confirmadas.
