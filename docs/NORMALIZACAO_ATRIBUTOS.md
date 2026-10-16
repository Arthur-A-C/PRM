# Normalização de atributos entre empresas

## Regra vigente de sistema operacional e indicadores — 14/10/2026

Por decisão do usuário, presença e suporte passam a equivaler por **família de SO**. `Suporta Linux, Suporta Windows` equivale a `Windows 10 IoT | Linux`, inclusive quando outra observação repete apenas `Windows 10 IoT`. A união das famílias elimina repetições e conflitos puramente lexicais; versões, edições e instalação são preservadas nas evidências, mas não decidem igualdade deste atributo. Esta regra substitui a distinção de escopos de SO descrita nas etapas históricas abaixo. Negação explícita, ausência de SO e valores não reconhecidos continuam distintos/pendentes.

Política `os-families-v2`, implementada em `operating_system.py`, integra a identidade do snapshot. O reprocessamento recalcula qualidade, famílias e indicadores de atributos compostos. A API de resumo inclui `attribute_analysis`. O gráfico de SO conta concorrentes com conjunto de famílias de SO igual ao de pelo menos um produto próprio **visível e da mesma família de produto**. Mostra percentual sobre todo o catálogo e sobre os comparáveis, com desconhecidos/sem candidato próprio/sem informação discriminados. É igualdade de um atributo, não equivalência integral do produto. Os gráficos antigos de famílias continuam com seu significado original.

Memória, armazenamento e USB também têm seus indicadores de interpretação recalculados: produtos cujos componentes foram interpretados sobre os produtos que informam o atributo. Isso não exige ficha completa nem significa equivalência. Snapshots históricos e dados originais permanecem preservados.

## Visão composta vigente

A tela usa `display_rows`, construída por `app/services/comparison_details.py`, sem modificar o snapshot. Memória e armazenamento unem seus campos de capacidade/tipo numa linha, com detalhes comparáveis dentro das células. Tecnologia, formato, frequência, slots, capacidade informada e limite máximo têm significados independentes. A expressão `até 64 GB` não informa a quantidade instalada. Intervalos e quantidades por módulo não são somados automaticamente. Campos sem parser permanecem visíveis e não interpretados; observações conflitantes nunca são promovidas a equivalentes.

Todos os demais códigos canônicos também aparecem numa linha por característica com detalhes por escopo/unidade. USB possui detalhes de quantidade por versão, geração e conector; SO mantém escopos dentro da mesma linha. Tensões de entrada/saída/bobina continuam características distintas. Memória de controlador não se une à RAM.

Cada detalhe é comparado ao primeiro produto. O resumo prioriza conflitos, depois diferenças; coincidências acompanhadas de dados faltantes/não interpretados geram **Correspondência parcial**. Igual/Equivalente requer coincidência em todos os detalhes presentes na comparação. Isso não homologa equivalência global do produto. O exemplo USB anteriormente marcado Equivalente passa a parcial na visão composta quando faltam geração/conector, e mantém igualdade na quantidade por versão. Os dados originais de cada célula continuam acessíveis em “Dados originais e origem”.

## Termos e descrições USB

`app/services/usb_comparison.py` interpreta grupos completos de quantidade e versão (`2x USB 2.0`), geração opcional e conector opcional. O dicionário reconhece Type/Tipo, Gen/Generation/Geração, `x`/`×`, espaços e ordem das portas. Grupos repetidos podem ser somados quando as observações não têm conflito registrado.

`2x USB 2.0, 4x USB 3.2` equivale, nas quantidades/versões descritas, a `2 x USB 2.0 Type-A, 4 x USB 3.2 Gen2 Type-A`. A tela informa que geração e conector não descritos na referência continuam não confirmados. Gerações/conectores explicitamente diferentes impedem equivalência; texto residual como OTG, interno, alternativas ou limites impede interpretação automática. O parser não infere equivalência de versões USB distintas. Atua sobre os valores do snapshot em tempo de comparação, preservando banco e originais.

## Comparação visual — 14/10/2026

A matriz usa o primeiro produto como referência, mantendo Portwell/Choice primeiro. Cada característica informa igualdade literal, equivalência após normalização, diferença de valor, dados insuficientes ou conflito. Equivalência de um atributo não confirma equivalência do produto. Capacidades simples usam unidades explícitas (SI/IEC); `1 TB = 1000 GB`, enquanto `1 TiB = 1024 GiB`. Ausência, alternativas e escopos incompatíveis impedem conclusões automáticas.

Memória e tipo de memória aparecem sob uma categoria, com subcampos separados; armazenamento segue o mesmo padrão. Memória sem contexto não é convertida em RAM; memórias de PLC permanecem independentes. Sistema operacional aparece em uma linha única e cada valor mantém o escopo de suporte, instalação, opcionalidade ou não informado. A consolidação acontece na leitura do snapshot, sem sobrescrever observações ou exigir nova importação. Auditoria: `python -m scripts.audit_comparison_fields`.

O pipeline refinado aplica o mesmo dicionário a Portwell, Choice, ECO e Dimensional. Portwell e Choice continuam sendo a referência de apresentação. A normalização de campos não comprova equivalência técnica de produtos nem habilita automaticamente análise de preços.

## Contrato

`config/catalogs/attributes.json` formaliza 54 códigos canônicos, seus nomes de apresentação e aliases explícitos. O prefixo `ATR_`, underscores, caixa e acentos são normalizados para busca do alias. Não se usa fuzzy de nomes técnicos: campos ambíguos permanecem não mapeados. O conteúdo e a versão do dicionário integram a política gravada e o identificador da execução. Alterações geram um novo snapshot, sem editar o publicado ou os arquivos originais.

| Origem concorrente | Apresentação canônica | Código |
| --- | --- | --- |
| `ATR_USB` | Portas USB | `ports.usb` |
| `ATR_COM` | Portas Seriais COM | `ports.serial` |
| `ATR_Protecao_IP`, `GRAU PROTECAO` | Proteção IP | `protection.ip` |
| `ATR_Protocolo_de_Comunicacao` | Protocolo de Comunicação | `communication.protocol` |
| `ATR_Corrente_Nominal`, `CORRENTE NOMINAL` | Corrente Nominal | `electrical.current.nominal` |
| `ATR_Entradas_Digitais` | Entradas Digitais | `io.digital.input` |

Cada observação conserva `raw_name`, `raw_value`, evidências, estado de conhecimento, escopo e versão da regra. Campos mapeados recebem `canonical_label` e `mapping_version`; não mapeados usam o nome original. O catálogo e a comparação mostram o nome padronizado junto à origem. A matriz agrupa por código, escopo e unidade; atributos não mapeados mantêm o nome original como discriminador.

## Limites de segurança

- Entrada, saída, bobina, nominal e tensão sem escopo são códigos distintos. Corrente sem escopo não vira corrente nominal. Alimentação não é automaticamente tensão de entrada.
- Memória de computador e memória de PLC continuam distintas. Resolução genérica só vira resolução de tela em famílias de HMI/panel PC; resolução de sensor permanece não interpretada.
- Proteção genérica só recebe código IP quando o valor contém um grau IP explícito. Certificado `CA`, links administrativos e campos genéricos como `Tipo` não são convertidos em características técnicas específicas.
- Escalares completos têm conversões exatas com `Decimal`: A/mA, V/kV, W/kW, Hz/kHz, g/kg e mm/cm/m conforme o campo. `500 mA` e `0,5 A` viram `0.5 A`; `4 POLOS` e `4` viram o inteiro 4. Intervalos, alternativas, unidades ausentes e Vcc/Vca não são adivinhados. Valores brutos permanecem intactos.
- Portas mantêm versões, conectores e alternativas no texto original. `6x COM (RS-232/422/485)` contém uma quantidade explícita de 6 na expressão COM, não três portas. Qualificadores de quantidade não são um total homologado, especialmente quando há outras expressões na mesma descrição. Não se somam listas USB ambíguas.
- Deduplicação ECO e detecção de divergência exigem o mesmo código, escopo e unidade. Diferentes formatos escalares conhecidos não geram conflito; conflitos técnicos existentes não são suprimidos.

## Auditoria e operação

Antes da alteração foram auditadas 500.016 observações nas quatro fontes definitivas. Identificadas 19 observações ECO com os nomes `ATR_USB`/`ATR_COM`, inclusive portas alternativas e conectores internos; não se presumiu uma quantidade total a partir dessas descrições.

Comandos a partir da raiz oficial do projeto:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m scripts.refined_catalogs run --manifest config/catalogs/inputs.example.json
.venv/Scripts/python.exe -m scripts.audit_attribute_aliases --run-id <RUN>
.venv/Scripts/python.exe -m scripts.persist_refined_catalogs --target staging --run-id <RUN> --commit --publish
.venv/Scripts/python.exe -m scripts.smoke_refined_catalogs --target staging --run-id <RUN>
# Somente após testes e autorização de publicação:
.venv/Scripts/python.exe -m scripts.persist_refined_catalogs --target production --run-id <RUN> --commit --publish
.venv/Scripts/python.exe -m scripts.smoke_refined_catalogs --target production --run-id <RUN>
```

O manifesto de exemplo precisa apontar para arquivos existentes. Novas importações executadas pelo pipeline refinado recebem o dicionário automaticamente. Importadores legados continuam históricos e não substituem o snapshot oficial. Categorias de produto continuam propostas pela taxonomia existente; não há nova classificação por fuzzy nem matching técnico nesta entrega.

Regressões cobrem aliases USB/COM/IP/IO, alinhamento da matriz, unidades/quantidades, tensão por contexto, memória por família, campos administrativos, ambiguidades de portas, conflitos e deduplicação por escopo/unidade. Contagens e publicação efetivas devem ser consultadas na entrada mais recente de `docs/STATUS.md`.
