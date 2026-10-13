# Normalização de atributos entre empresas

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
