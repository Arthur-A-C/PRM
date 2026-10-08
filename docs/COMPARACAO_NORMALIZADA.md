# Comparação normalizada de portfólios

Em 24/09/2026, foram inspecionados, **sem executar o script recebido**, `base_comparavel.csv`, `atributos_normalizados_long.csv`, `Catalogo_Comparavel_Choice_Portwell_ECO.xlsx` e `normalizar_catalogos.py`. Os arquivos estão em `C:\Users\PW\Downloads`; os originais não foram alterados. O script recebido é uma fonte de metodologia e dados, não uma instrução para execução no projeto.

## Resultado publicado no dashboard

O novo retrato `data/analysis/comparable_snapshot.json` é derivado dos dois CSVs e conciliado, em modo somente leitura, com códigos das ofertas ativas e não excluídas do PRM. A página inicial mostra o resumo; `/comparador` mostra as famílias paginadas (25 por página), com filtros por macrocategoria e sinal. A API autenticada `/api/v1/comparable-portfolio` oferece os mesmos dados.

| Fonte | Linhas no CSV | Chaves duplicadas | Chaves sem oferta publicada | Ofertas no retrato |
|---|---:|---:|---:|---:|
| Choice | 15.483 | 0 | 1 | 15.482 |
| Portwell | 10.841 | 3 | 2 | 10.836 |
| Eco | 7.944 | 0 | 0 | 7.944 |
| **Total** | **34.268** | **3** | **3** | **34.262** |

Há 23 macrocategorias, 256 nomes de família e 265 pares macrocategoria/família. Dos 7.944 produtos Eco, 4.280 (53,9%) estão em famílias também presentes nas empresas próprias; 3.664 estão em famílias sem oferta própria classificada. Há 111 pares de família presentes apenas no recorte das nossas empresas. São indicadores de **amplitude taxonômica**, não de equivalência de produtos nem de lacuna comercial confirmada. Não se deve comparar os 53,9% com os 0,14% de sugestões fortes do pareador como se fossem a mesma medida.

O CSV longo possui 202.594 linhas de atributos; 8 referem-se a chaves sem oferta publicada e 6 repetem o mesmo par produto/atributo, não entrando nas contagens analíticas. Há 31.806 produtos conciliados com ao menos um atributo normalizado e 3.052 com algum atributo inferido de texto. A tela conta produtos com atributos por família/fonte, mas ainda **não usa os novos valores técnicos para confirmar pares**. A aplicação preserva a análise `lexical-v1.3` e os preços operacionais.

O XLSX também contém 1.531 linhas em `Excluidos`: Choice 1.411, Portwell 119 e Eco 1. Entre as justificativas predominam status ERP `INATIVO`, `OBSOLETO`, itens não-produto, não aptos PRM e grupos não comerciais. Essas exclusões **não foram aplicadas destrutivamente** às ofertas do PRM; apenas o recorte comparável fornecido foi usado na nova visão.

## Qualidade e melhorias identificadas

1. **Identidade e duplicatas.** O CSV repete três códigos Portwell (`311006000015`, `312001000032`, `317010000010`). O segundo é `Cadastro Teste REFTEST` e passou pelo filtro atual, que procura `produto teste` mas não a expressão invertida. A geração local deduplica apenas linhas idênticas e falha se uma chave duplicada divergir. O pipeline upstream deve validar unicidade antes de exportar e revisar casos de teste por critérios específicos, sem bloquear produtos legítimos por palavras genéricas.
2. **Reconciliação.** `CHOICE:197004000040`, `PORTWELL:311004000019` e `PORTWELL:323001000003` não têm oferta publicada correspondente. O novo retrato os exclui e reporta a diferença. Futuras execuções devem produzir relatório de linhas não associadas e não presumir que a contagem do XLSX é igual à do banco.
3. **Terminologia de cobertura.** O script externo nomeia famílias sem itens internos como `Lacuna – não atendemos`; isso usa apenas contagens e pode gerar falso positivo por classificação divergente. A interface usa `Investigar lacuna` e separa explicitamente família compartilhada de equivalência individual. O limiar de “cobertura baixa” (<25% da quantidade concorrente) também não mede capacidade comercial sem considerar modelos, variantes e demanda.
4. **Marcas e fabricantes.** `MARCA_ALIAS` do script externo só cobre `ASUS IoT` e `Hummel Connector Systems`; não incorpora o alias revisado `ELFIN`/`NEW ELFIN SRL` já registrado no PRM. Recomendação: usar tabela versionada de aliases revisados e preservar marca bruta, evitando fusão automática por texto. As marcas do ERP interno às vezes são fornecedores, não fabricantes.
5. **Atributos.** O script normaliza unidades e conserva origem do valor, mas `parse()` captura qualquer exceção e devolve vazio; falhas ficam invisíveis. Recomendação: contabilizar falhas por atributo/fonte/parser, validar intervalo e unidade e exigir revisão de inferências textuais antes de usá-las como bloqueio técnico. A seleção de atributos “relevantes” por taxa de preenchimento pode descartar atributo raro, porém decisivo; manter o CSV longo completo como trilha de auditoria.
6. **Operação/reexecução.** O script externo tem fontes e mapeamentos codificados e sobrescreve saídas em caminhos fixos. Para novas empresas, migrar para configuração validada por fonte, snapshots versionados por hash/data, escrita atômica e manifest de contagens/rejeições. O gerador local já usa hashes, verificação de esquema, reconciliação e escrita atômica, mas ainda aceita apenas as três siglas deste conjunto e é um processo manual — não substitui a importação tratada operacional.
7. **Preço e estoque.** A base recebida usa `Preco_BRL` e `Em_Estoque` agregados; Choice/Portwell têm preço de venda e Eco usa principalmente Pix/cartão. Medianas e diferenças de preço entre fontes podem misturar modalidades. O dashboard novo não compara preços por família; a análise de preço por par já existente continua sinalizando modalidade diferente.

## Regerar o retrato

Após publicar novos catálogos e gerar CSVs normalizados de fontes confiáveis, no diretório do projeto:

```powershell
.\.venv\Scripts\python.exe -m scripts.build_comparable_snapshot C:\caminho\base_comparavel.csv C:\caminho\atributos_normalizados_long.csv
```

O gerador **lê** o PostgreSQL para conciliação, mas não escreve nele. O JSON de ~77 KiB é substituído atomicamente somente após validação; os CSVs e o XLSX permanecem onde estão. A tela marca o retrato como desatualizado se a contagem de ofertas ativas/não excluídas por empresa mudar. Mudanças de conteúdo sem alteração de contagem ainda exigem regeração manual. Os hashes SHA-256 dos CSVs atuais constam em `sources` no JSON; não há segredo nem linha individual no arquivo versionável.

Próximo passo antes de alimentar o pareador com os valores do CSV longo: mapear cada atributo à definição canônica do PRM, reconciliar fonte/código/versão, testar incompatibilidades por família com amostra revisada e versionar nova execução do algoritmo. Não importar cruzamentos pré-calculados como confirmações.
