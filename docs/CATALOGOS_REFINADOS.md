# Catálogos refinados — base publicada em 09/10/2026

## Estado vigente: apenas a nova análise no dashboard

A nomenclatura dos atributos agora é padronizada entre as quatro fontes pelo dicionário versionado: `ATR_USB` → Portas USB, `ATR_COM` → Portas Seriais COM, além de IP, comunicação, IO, dimensões e campos elétricos com escopos distintos. A matriz usa códigos canônicos e mantém os nomes/valores originais visíveis. Auditoria, contrato e limites em [NORMALIZACAO_ATRIBUTOS.md](NORMALIZACAO_ATRIBUTOS.md); execução mais recente e publicação em [STATUS.md](STATUS.md). Novas importações pelo pipeline refinado recebem essas regras automaticamente.

Os grupos agora são navegáveis: clicar em famílias compartilhadas, não localizadas ou classificação pendente abre os respectivos produtos, com filtros por fonte/família e 100 itens por página. Há também filtro de todos os alertas de qualidade. “Escolher produtos próprios para comparar” fixa o concorrente como referência e abre nossas empresas na mesma família; é possível pesquisar em todo o portfólio próprio. Não são candidatos homologados nem resultado fuzzy recalculado.

Selecionar de 2 a 8 produtos abre `/comparacao-atual`, com preços/características/pendências lado a lado, preservando atributos repetidos, unidades e escopos. A referência acompanha a navegação; outros checkboxes pertencem à página atual. Preços ocultos são restritos a gestores. O snapshot/organização/visibilidade são validados; seleção obsoleta é recusada, sem buscar dados antigos. Não há gravação de aprovação. **124 testes aprovados**, além de smoke SQL/HTML em staging/oficial; nenhum banco ou catálogo foi alterado por esta funcionalidade.

O operador definiu os novos imports como referência definitiva da fotografia atual e pediu retirar os painéis antigos. Visão geral, Comparador e Importações agora consultam **somente** o snapshot publicado da organização; consultas/templates antigos foram removidos dessas páginas. Dados anteriores foram preservados, não excluídos. Sem snapshot atual, há indisponibilidade, nunca fallback para análises antigas.

Os novos gráficos usam as 3.741 ofertas próprias publicadas/visíveis (991 Portwell + 2.750 Choice): ECO 2.207 registros em famílias compartilhadas, 4.629 não localizadas e 1.109 pendentes, denominador 7.945 (**27,8% compartilhadas**); Dimensional 20.419 compartilhadas, 22.584 não localizadas e 34.962 pendentes, denominador 77.965 (**26,2%**). Família desconhecida não conta como compartilhada. Percentuais arredondados individualmente podem somar 100,1%. Presença de família não confirma equivalência técnica; ausência no recorte não confirma ausência no portfólio completo.

`current_analysis.py` gera o mesmo contrato para HTML e `/api/v1/dashboard/summary` (schema 2), sem preços, caminhos locais ou payloads brutos. Estado técnico: `not_assessed`, cobertura estrita `null`. As seções abaixo registram a primeira publicação; **não há mais seus painéis históricos abaixo da fotografia atual**. Catálogo/comparação direta anteriores continuam acessíveis explicitamente fora dessas páginas.

Verificação desta atualização: **121 testes aprovados, três avisos**; smokes em staging e oficial validaram sete páginas HTML e a API do resumo atual, ausência de painéis anteriores, escopo da organização e reconciliação de dados. Publicação oficial reconfirmada idempotentemente, sem recarregar ou excluir registros. Carregar o código atualizado no processo HTTP para visualizar a mudança; não foi realizado deploy remoto nem reinício de processo existente.

Implementação por fases da especificação `especificacao_pipeline_catalogos_prm.md`, versão 1.0 de 09/10/2026, lida integralmente. O operador confirmou publicar a nova fotografia após os testes. **Entrega de base/auditoria implementada; motor técnico, cobertura e governança de revisão ainda não concluídos.** Não confundir ingestão validada com dados técnicos homologados.

## Fontes e decisões

Os quatro arquivos recebidos são a referência da nova análise. Os CSVs próprios são **parciais**: ausência não significa descontinuação nem que a empresa não comercializa a linha. IDs WooCommerce têm namespace por empresa; SKU vazio não elimina o produto. Dimensional é identificada por SKU, não `product_id`, URL ou EAN. Marca/vendedor/fabricante continuam conceitos separados; ELFIN e NEW ELFIN SRL compartilham alias de busca, não confirmação de fabricante.

| Origem | Recebidos/aceitos | Visão pública | Registros com atributos extraídos | Observações de atributos |
|---|---:|---:|---:|---:|
| Portwell | 1.033 | 991 | 1.020 | 7.907 |
| Choice | 2.750 | 2.750 | 2.746 | 21.367 |
| ECO | 7.945 | 7.945 | 7.924 | 39.162 |
| Dimensional | 77.965 | 77.965 | 53.250 | 431.580 |
| Total | 89.693 | 89.651 | 64.940 | 500.016 |

Nenhum registro ficou em quarentena neste lote. “Com atributos” conta também observações extraídas de campos auxiliares; não corresponde apenas a `ATR_*` ECO ou `especificacoes` Dimensional, nem comprova suficiência para comparar. Na ECO, representações redundantes correlacionadas são conservadas na evidência sem contar como confirmação independente.

Hashes confirmados iguais aos da especificação (Dimensional recebida sem `(1)` no nome):

```text
Portwell     4a2f7a175f56fe59780462f2ff2f57915761e927184e1b2eeee4e89aa3526872
Choice       790fe42694b91bb60f1849dc02c1fbfd68a43b114fc8daa8eb8aa1b6ce35536d
ECO          4a1772d67da35d58239f9900f19ae3ce8040375965307ed948d968bcc56ee060
Dimensional  8ad7e0e63e265aa6ebfd34b06a530dc000177c11602c2a6920e80add3e211528
```

Arquivos originais em Downloads permanecem intactos. Cópias byte a byte estão em `data/imports/refined/<SHA256>/<nome original>`, ignoradas pelo Git. Não foi necessário apagar/substituir as antigas planilhas: elas pertencem ao histórico, enquanto o novo snapshot determina a base analítica atual. As rotinas legadas de enriquecimento NÃO devem ser executadas para “atualizar” essa fotografia, pois sua chave histórica é diferente do ID WooCommerce.

## Execução e armazenamento

Execução publicada: `6028d33f8d7aad1e5b085ab7`, regras `refined-base-v1`. Saídas em `data/analysis/staging/refined/6028d33f8d7aad1e5b085ab7/`:

- `run_manifest.json`, `policy.json`, `data_profile.json`, `summary.json`, `summary.md`: hashes, políticas, contagens e fases.
- `raw_records.jsonl`, `quarantine.jsonl`: payload bruto, posição, linhas físicas, tipos de célula Excel e problemas de leitura. O arquivo original arquivado é a evidência byte a byte.
- `own_items.jsonl`, `competitor_items.jsonl`: identidades estáveis, títulos, classificações propostas, observações comerciais e pendências.
- `attribute_observations.jsonl`: bruto/normalizado, estado, escopo e evidência por origem/lote/chave/campo/trecho. Sem descarte de atributos novos.
- `quality_issues.csv`, `taxonomy_unmapped.csv`: alertas e campos/categorias sem mapeamento; células potencialmente executáveis são protegidas nos CSVs, não nos JSONL canônicos.
- `legacy_eco_audit.csv`: cruzamento antigo isolado, sem criar itens próprios a partir de referências ausentes.
- `competitor_coverage.csv`: **515.460 linhas** (85.910 concorrentes × seis escopos), todas `not_assessed`, com busca não concluída. Não representa matching executado nem cobertura zero.

Os arquivos são publicados somente depois de completos, reconciliados e hashados. `latest.json` identifica a última execução válida; `published.json` é um ponteiro opcional de publicação de arquivos. **O dashboard usa a publicação SQL da organização**, não um arquivo global. Falhas de geração/publicação não substituem o snapshot anterior. Reexecução do mesmo conteúdo e versão é idempotente. Arquivo `.building` interrompido é reprocessado do início: não há checkpoint por item.

A migração aditiva `20261009_0008` criou em ambos os bancos:

- `refined_catalog_runs`: versões, manifestos e estado de publicação por organização.
- `refined_catalog_raw`: ocorrências brutas por execução/origem/posição.
- `refined_catalog_items`: cadastro normalizado por execução/UUID, chave única por origem e atributos/evidências em JSONB.

As observações de atributos estão no JSONB do cadastro, não em novas tabelas relacionais de variantes/resoluções. Estas entidades da especificação fazem parte das próximas fases. Carga SQL inteira em transação; publicação em outra transação, com bloqueio por organização e índice que permite um único snapshot publicado. Reversão analítica: republicar uma execução anterior íntegra; não apagar tabelas/histórico. A migração bloqueia downgrade destrutivo. O ID de execução de arquivos é global; esta implementação é para a organização PRM atual e recusa reutilização por outra organização, em vez de compartilhar dados.

No `prm_pipeline_staging`: 89.693 novos cadastros, 89.693 ocorrências brutas, 500.016 observações; reexecução SQL idempotente. No `prm_mvp`: mesmos números e execução publicada. As tabelas legadas permanecem com **35.786 ofertas, três empresas e três lotes**: Choice 16.886, Portwell 10.955, ECO 7.945. No staging permanecem também as 77.965 ofertas Dimensional anteriores (113.751 ofertas legadas no total). Nenhum cadastro WooCommerce/CIGAM, usuário, senha ou configuração `.env` foi alterado.

Backup preventivo: `data/backups/prm_mvp_20261009_123811.dump`, 29.427.943 bytes, SHA-256 `04c5c08b8293a5f0b7fcdac6f9a4a112f324755a5d662f1b69c6508b1853eb77`. `pg_restore --list` validou inventário com 172 linhas; restauração de recuperação desse backup não foi executada.

## O que muda na interface

- `/catalogos` abre a fotografia refinada publicada, com **100 registros por página**, nossas empresas primeiro, pesquisa por título, origem e família proposta; gestores podem incluir itens próprios ocultos/não publicados. Características brutas/estados ficam expansíveis por produto. Preços próprios configurados como ocultos aparecem apenas para gestores nessa nova visão.
- `/catalogos?view=legacy` preserva filtros avançados e seleção/comparação direta anteriores. Esses recursos ainda trabalham com as ofertas históricas: não usam automaticamente o novo UUID canônico. Filtros de preço/marca e seleção direta na nova visão são pendências de integração, não recursos concluídos.
- Visão geral, Comparador e Importações mostram a nova base, qualidade e distribuição por família, separadas de indicadores/pareamentos históricos. Contagens não são produtos técnicos únicos, demanda ou aprovação de substituição. Não há novo percentual de cobertura estrita enquanto o motor não tiver sido executado/validado.
- O código precisa estar carregado no processo HTTP: se o servidor estiver ativo sem reload, reiniciá-lo pelo procedimento normal. Os smokes usaram a aplicação carregada com o código atual, não comprovam atualização de um processo antigo nem deploy remoto.

## Diagnóstico e limites da normalização

750 linhas Portwell e 350 Choice têm cauda ausente, preenchida após validar campos estruturais; cabeçalhos e larguras originais foram registrados. 36 SKUs Choice vazios e o placeholder `codmaterialaqui` foram preservados. O título não é usado para deduplicar.

29 velocidades Ethernet Portwell conflitantes e 39 listas USB exatamente iguais ao caso da especificação foram sinalizadas. Encontrados ainda dois casos USB adicionais: SKUs `317005000012` e `317006000014`. Na Choice há oito conectores RJ45 em protocolo; protocolo fica desconhecido. Potências com separador ambíguo conservam o original e a proposta baseada no título, sem correção automática. Memória/alcance usam contexto e unidade, e os sinais negativos são preservados. `P002212` ECO conserva o modelo truncado; ao todo, 384 modelos ECO apresentam parênteses desequilibrados e precisam de revisão.

Dimensional: 112 GTINs inválidos, 31 preços zero, 65.600 alertas de estoque sentinela; **todas** as quantidades continuam não confiáveis, inclusive 100/10/1. 32 ocorrências de unidade incompatível com seção transversal foram sinalizadas. Especificações/descrições podem conter observações divergentes: são preservadas, não resolvidas por prioridade silenciosa. Resíduos incluem texto livre sem formato chave/valor, não significam perda do original.

Famílias pendentes: Portwell 438, Choice 913, ECO 1.109, Dimensional 34.962. A maioria dos nomes de atributo ainda não tem parser tipado homologado: observações sem mapeamento Portwell 7.256, Choice 21.163, ECO 38.809, Dimensional 430.113. Esse backlog aparece em `taxonomy_unmapped.csv`. `known` significa valor observado, não validação técnica. Escopo não declarado continua `unspecified`. Não foram implementadas conversões gerais de unidades, resolução de variantes, fabricante confirmado ou prioridade universal de evidências.

## Operação reproduzível e futuras entradas

Na pasta oficial `C:\Users\PW\Documents\PRM`, sem IA/downloads:

```powershell
# Auditoria somente leitura; não importa, publica ou chama API.
.venv\Scripts\python.exe -B -m scripts.refined_catalogs profile --input-dir C:\Users\PW\Downloads

# Alternativa portátil: preparar manifesto seguindo config/catalogs/inputs.example.json.
# Os caminhos relativos são resolvidos contra a raiz oficial do repositório.
.venv\Scripts\python.exe -B -m scripts.refined_catalogs run --manifest data/imports/novo_manifesto.json
# Ou os quatro nomes recebidos nesta entrega:
.venv\Scripts\python.exe -B -m scripts.refined_catalogs run --input-dir C:\Users\PW\Downloads

# Execute para o RUN retornado, não force o ID deste lote em novos arquivos.
.venv\Scripts\python.exe -B -m scripts.persist_refined_catalogs --target staging --run-id RUN --commit --publish
# Depois da revisão, backup e testes, publicação explícita da fotografia oficial:
.venv\Scripts\python.exe -B -m scripts.persist_refined_catalogs --target production --run-id RUN --commit --publish

# Verificação de arquivos sem alterar publicação:
.venv\Scripts\python.exe -B -m scripts.refined_catalogs run --manifest data/imports/novo_manifesto.json --dry-run
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

`run` não grava em PostgreSQL; `persist_refined_catalogs` migra apenas o alvo indicado, verifica hashes e reconcilia a carga. Produção exige lote existente no staging e publicação explícita. Não há substituição silenciosa por hash divergente ou falha de arquivo. Evite duas execuções de arquivos simultâneas para o mesmo lote: a geração `.building` ainda não tem lock por processo. Persistência/publicação SQL tem lock transacional. Novos arquivos com estrutura compatível usam os mesmos adaptadores e preservam colunas extras; erros estruturais ficam em quarentena, e CSV ilegível invalida a execução. Novos esquemas/adaptadores demandam implementação, não dedução automática. A tela legada de upload XLSX não foi convertida para essa CLI; importação refinada é manual/operacional nesta entrega.

Mude `rule_version` ao modificar parsers/taxonomia; o ID de execução usa hashes de entrada e política, não hash automático do código ou versão de dependências. Incrementalidade fina/cache de IA ainda não foi implementada. Segredos seguem `.env` e não são exportados.

## Verificações e próximos gates

- Suíte completa após a integração: **115 testes aprovados, três avisos** (Starlette/AnyIO e estilos ausentes em planilhas antigas), incluindo proteção de conteúdo HTML e restrição de preços ocultos na nova interface.
- Casos reais de Choice, Portwell e ECO passaram; testes sintéticos cobrem namespace, cauda CSV, desalinhamento, atributos dinâmicos, fórmulas, conflitos, preço/GTIN/estoque, publicação/arquivos alterados, idempotência e falha sem perder o ponteiro anterior.
- Smokes SQL/HTML em staging e oficial: reconciliação por origem/atributos, isolamento por organização, 100 itens por página, visão pública/interna, pesquisa vazia, sete URLs HTTP 200. Autenticação foi simulada apenas no processo diagnóstico; não houve alteração do servidor/login nem criação de conta. Não equivale a teste de sessão real no navegador.
- Normalização completa em arquivos: **73,132 s**, Windows 11, Python 3.14.7. Não houve produto cartesiano nem chamadas pagas. Pico de memória/hardware detalhado, retomada por checkpoint e inspeção visual autenticada continuam pendentes.

Próximas fases obrigatórias: detalhar taxonomia e parsers com as filas reais; perfis conservadores por família e recuperação top-k/fallback; comparação direcional com críticos conhecidos; cobertura estrita/ampliada e oportunidades inconclusivas; decisões humanas versionadas, catálogo complementar e estados `not_seen_in_latest_batch`; governança/custos/cache de IA; validação estratificada por responsável técnico. `matches.jsonl`, `coverage_by_family.csv`, `opportunities.csv`, `review_queue.csv` e importação de decisões não foram entregues como se estivessem validados. Nenhuma família tem equivalência automática nova liberada. A especificação completa não está concluída.
