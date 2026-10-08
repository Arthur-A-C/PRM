# Dimensional — auditoria e simulação inicial

## Carga persistente em staging (28/09/2026)

O banco `prm_pipeline_staging` foi criado pelo operador e confirmado vazio. O backup verificado do `prm_mvp` foi restaurado nele para preservar a base comparativa. A importação do CSV foi concluída **apenas no staging**: 77.965 ofertas por SKU, 77.965 linhas de origem, 77.965 observações e 155.930 preços brutos de modalidades `anunciado`/`referencia_anunciada`. O lote é `380250f8-e8a7-4daf-9453-8bf80c3846a2`; SHA-256 `8ad7e0e63e265aa6ebfd34b06a530dc000177c11602c2a6920e80add3e211528`. Há 582 linhas com alertas. A segunda execução foi idempotente. O `prm_mvp` permaneceu com as mesmas 35.786 ofertas e três empresas.

Comandos executados na pasta oficial:

```powershell
.venv\Scripts\python.exe -B -m scripts.check_staging
.venv\Scripts\python.exe -B -m scripts.restore_staging --backup data/backups/prm_mvp_20260928_141836.dump --sha256 4470551b59efaebf108e8199e6c1c1785dd8bb8b2aece4b87580ab353ea848dc
.venv\Scripts\python.exe -B -m scripts.import_dimensional_staging --commit
.venv\Scripts\python.exe -B -m scripts.check_staging
```

`restore_staging` exige banco de nome exato e vazio, verifica o hash e usa restauração em transação única; não deve ser repetido depois da carga. `import_dimensional_staging` deriva exclusivamente a URL do banco de staging e rejeita outro lote para a mesma empresa sem fluxo de revisão. A carga também é atômica, mas não tem checkpoint/retomada parcial; uma falha exige corrigir a causa e reexecutar desde o início. Não use os registros de preço como comparáveis: `XXX` significa moeda desconhecida, não BRL, e data/unidade comercial seguem ausentes. O estoque sentinela ficou somente na linha bruta, sem quantidade normalizada confiável.

O dashboard oficial mostra a contagem real do staging ao lado da auditoria, com a produção separada. Este painel não habilita a Dimensional nos filtros comerciais nem aprova equivalências. Testes: 60 aprovados; smoke autenticado passou.

## Visibilidade na visão geral (28/09/2026)

O dashboard oficial lê os dois relatórios de staging e os exibe em um painel separado dos indicadores publicados. A quantidade de ofertas Dimensional no banco vem do resumo SQL real: neste momento é **0**, apesar dos 77.965 SKUs auditados. A API e os filtros comerciais continuam refletindo apenas as três empresas publicadas. A alteração foi validada por 59 testes e smoke autenticado; não houve escrita de ofertas ou matches Dimensional no `prm_mvp`.

Foi criado backup preventivo `data/backups/prm_mvp_20260928_141836.dump`, SHA-256 `4470551b59efaebf108e8199e6c1c1785dd8bb8b2aece4b87580ab353ea848dc`. Antes de promover a fonte, é preciso disponibilizar staging PostgreSQL, testar importação persistente/rollback, revisar amostra técnica e confirmar os campos comerciais pendentes. A exibição do relatório no dashboard não é homologação do catálogo.

Atualizado em 28/09/2026. A fonte Dimensional está **em staging**, não no catálogo publicado. Portwell, Choice e Eco permanecem inalteradas. Esta etapa segue `PRM_DIMENSIONAL_IMPLEMENTACAO_CODEX.md` recebido do operador e a arquitetura existente; não houve acesso ao site, downloads de PDFs/imagens ou uso de IA.

## Fonte e comandos executáveis

O original `C:\Users\PW\Downloads\produtos_dimensional.csv` foi copiado, sem alteração, para `data/imports/produtos_dimensional.csv` (ignorado pelo Git). Tamanho **140.518.094 bytes** e SHA-256 **`8ad7e0e63e265aa6ebfd34b06a530dc000177c11602c2a6920e80add3e211528`** foram confirmados no original e na cópia.

No PowerShell, a partir da pasta oficial do projeto:

```powershell
.venv\Scripts\python.exe -B -m scripts.audit_dimensional --csv data/imports/produtos_dimensional.csv --json data/analysis/staging/dimensional_audit.json
.venv\Scripts\python.exe -B -m scripts.stage_dimensional --csv data/imports/produtos_dimensional.csv --json data/analysis/staging/dimensional_simulation.json
.venv\Scripts\python.exe -B -m pytest tests/test_dimensional_csv.py tests/test_dimensional_semantics.py tests/test_dimensional_stage.py tests/test_dimensional_dashboard.py -q
```

Os dois primeiros comandos leem o CSV incrementalmente com `utf-8-sig`, `newline=''` e o parser CSV padrão. Gravam relatórios JSON de forma atômica sob `data/analysis/staging/`, fora do Git; **não abrem transação no PostgreSQL**. Reexecutar o mesmo lote não cria ofertas nem alertas. O adaptador rejeita cabeçalho obrigatório ausente ou duplicado, preserva colunas novas e não usa nome de arquivo, URL, product_id ou EAN como identidade da oferta: a chave proposta é `dimensional` + fonte `dimensional-csv` + `sku`.

## Reconciliação do lote

| Medida | Resultado |
|---|---:|
| Registros CSV / SKUs distintos | 77.965 / 77.965 |
| Linhas físicas / campos | 261.622 / 20 |
| product_id distintos / grupos repetidos | 77.957 / 3 |
| Marcas / caminhos de categoria / domínios | 210 / 117 / 9 |
| EANs vazios / inválidos / grupos compartilhados | 12.448 / 112 / 777 |
| NCMs vazios / inválidos / URLs em NCM | 13.631 / 126 / 122 |
| Referências em notação científica / iguais ao SKU | 320 / 9.703 |
| Fórmulas textuais `_xlfn` | 6 |
| Preços atuais zero / preços positivos | 31 / 77.934 |
| Especificações vazias / somente mídia-relatório | 40.527 / 2.454 |

Os três grupos de `product_id` repetido são `1053625` (7 SKUs), `197090` (2) e `238948` (2). Mesmo EAN válido aparece em itens distintos: `7909492067382` ocorre em 108 SKUs. Há **284 rótulos brutos** de especificações; 280 rótulos após normalização simples de caixa/acentos, motivo pelo qual as duas contagens não devem ser confundidas.

Estoque bruto: 65.600 × `99999`, 5.213 × `100`, 5.007 × `10`, 2.113 × `1` e 32 × `0`. A disponibilidade declarada é preservada, mas a quantidade confiável permanece **desconhecida para todos os 77.965 SKUs** até validação do contrato da fonte. `preco` é anunciado e `preco_de` é referência anunciada, nunca Pix/cartão. Os 31 zeros não entram em ranking; moeda, unidade de venda e data da coleta continuam desconhecidas.

## Resultado técnico da simulação

O adaptador e `app/services/dimensional_semantics.py` geraram **3.790 afirmações propostas**, com trecho literal no campo de origem e zero evidências sem correspondência. Há 9.576 propostas nas famílias prioritárias; os demais 68.368 registros ficam explicitamente sem perfil técnico v1. Isso **não é acurácia nem homologação**. Nenhuma oferta ou equivalência Dimensional foi publicada no banco oficial.

Casos críticos mantidos como conflito: seis tamanhos de calçado contaminados por dados da página, uma fita com comprimento/tensão/referência divergentes, 36 propostas de bobina divergente (incluindo `435197`), 21 propostas de modelo de switch divergente (incluindo `1267587`), uma contagem RJ45 conflitante e 29 declarações de seção de cabo com unidade dimensional inadequada. Os totais são *candidatos* gerados por regra, não erros técnicos individualmente homologados.

O SKU `1298390` é proposto como computador industrial Panel PC com 4 GB, tela 15", 24 V DC e SO não incluído com evidência da descrição; `878767` não é promovido a computador apenas pela categoria IHM. Blocos `1302674`/`1302675` são acessórios. No `1401334`, a fórmula permanece inválida e a entrada 100–240 V AC é proposta exclusivamente pela descrição. URL no NCM de `243665` vira candidata a documento, sem se tornar NCM. Nada é baixado automaticamente.

A aba **Importações e qualidade** mostra somente a gestores estes relatórios em staging, separados dos indicadores publicados. Não foi adicionada a Dimensional aos filtros comerciais ainda: fazê-lo antes da revisão criaria uma falsa impressão de que os 77.965 produtos já foram homologados no banco oficial.

## Antes da publicação

O banco publicado permanece com 3 empresas, 3 lotes, 35.786 ofertas e migração `20260923_0007`. O staging já existe, foi restaurado e recebeu a carga bruta transacional descrita acima. Ainda faltam ingestão retomável por checkpoint, revisão humana, validação de comparação Dimensional × Choice/Portwell, publicação/rollback de revisão e decisões comerciais antes de escrever no `prm_mvp`.

Ficam pendentes confirmação de moeda, data da coleta, unidade de venda, semântica dos estoques sentinela, completude do recorte, herança de variantes e aprovador de conflitos técnicos. Após a homologação de amostra estratificada (~200 SKUs), persistência/revisão de evidências e teste de rollback, os filtros, cards e comparador poderão passar a mostrar Dimensional como catálogo publicado. Até lá, **nenhum match cruzado ou cobertura negativa foi afirmado**.
