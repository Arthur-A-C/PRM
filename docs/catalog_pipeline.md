# Pipeline de normalização — implantação por fases

Atualização de 09/10/2026: a [nova fotografia refinada](CATALOGOS_REFINADOS.md) foi auditada/importada em staging e publicada no banco oficial em tabelas de snapshots separadas, por confirmação do operador. Ela passa a ser a base atual da análise, sem excluir os dados deste documento. O estado e os comandos abaixo são históricos da implementação anterior; não representam as contagens atuais nem devem ser usados para sobrescrever a nova base. Comparação técnica da nova fotografia ainda não foi homologada.

Estado em 25/09/2026: **subfase de auditoria e regressões em staging; não publicado**. A fase 1 da especificação ainda depende das migrações base. Esta implementação usa como especificação `PRM_PIPELINE_NORMALIZACAO_PROMPT_CODEX.md` recebido do operador. O pipeline legado e os catálogos publicados permanecem ativos e inalterados.

O staging atual é de **arquivos e relatório**, não um banco clonado. A conta `prm_app` não possui `CREATEDB`, e `prm_pipeline_staging` não existe. Um administrador deve provisionar um PostgreSQL staging separado antes de testar migrações/jobs persistentes; não apontar comandos de staging para `prm_mvp`.

## Executar a auditoria

Na pasta oficial `C:\Users\PW\Documents\PRM`, com o ambiente virtual existente:

```powershell
.venv\Scripts\python.exe -B -m scripts.audit_catalog_pipeline --imports data/imports --json data/analysis/staging/audit_20260925.json
.venv\Scripts\python.exe -B -m pytest tests/test_pipeline_audit.py tests/test_pipeline_audit_cases.py tests/test_pipeline_semantics.py -q
```

O comando somente lê os XLSX; não executa importação, migração ou SQL. O relatório fica fora do Git em `data/analysis/staging/`. A tela **Importações e qualidade** mostra essa reconciliação apenas a gestores, marcada como staging. Se os arquivos forem atualizados, use outro nome de relatório, recalcule hashes e contagens e atualize os testes do lote; não force as novas planilhas a reproduzirem as contagens antigas.

## Resultado do lote auditado

| Empresa | Bruto | Tratado | Códigos distintos | Nota |
|---|---:|---:|---:|---|
| Choice | 16.894 | 16.894 | 16.894 | Cabeçalho bruto na linha 3 |
| Portwell | 10.960 | 10.960 | 10.957 | Três códigos com duas ocorrências; rodapé bruto na linha 10.963 |
| Eco | 7.945 | 7.945 | 7.945 | Código alfanumérico preservado |

Total de 35.799 linhas de produtos **por camada**. As multiplicidades dos códigos entre bruto e tratado são idênticas. A linha adicional do bruto Portwell contém `Nenhum filtro aplicado`, sem código, e não é produto. Os seis hashes SHA-256 coincidem com a seção 14 da especificação. Este resultado verifica reconciliação, não homologação técnica de todas as linhas.

Nos três pares Portwell (`311006000015`, `312001000032`, `317010000010`) diferem `Preço Compra` e `Índice MK`; o relatório guarda linhas e nomes de campos divergentes, **não os custos**. Na Eco há 612 zeros em Pix e 612 em cartão; disponibilidade declarada: 1.670 em estoque, 6.221 fora de estoque e 54 BackOrder. Zero não foi convertido em gratuito e BackOrder não implica prazo.

## Correções semânticas em staging

`app/services/catalog_semantics.py` é um módulo puro e determinístico para propostas com evidência: CPU e sufixo, formato Box/Panel PC, RAM instalada versus máximo, discos, USB/COM, entrada do equipamento versus fonte fornecida, contatos/bobina de contator e papel de kit/acessório. `assess_pair` bloqueia função de fonte versus UPS e não promove correspondência lexical a equivalência. Os testes cobrem exemplos críticos e desconhecidos. O módulo **ainda não substitui** os campos `offer_enrichments` nem o algoritmo `lexical-v1.3` publicados; o dashboard deixa isso explícito.

## Próximos gates antes da publicação

1. Criar migrações não destrutivas para fonte/lote/ocorrência, afirmações tipadas, pendências, revisão humana e revisões publicadas. Os três pares Portwell devem preservar ambos os valores comerciais, sem escolher preço.
2. Executar ingestão de staging em banco PostgreSQL separado, com backup validado, jobs retomáveis e idempotência por hash, adaptador e versão de regras. Importação parcial não exclui ausentes.
3. Completar regressões com os registros reais de Eco/Choice/Portwell, incluindo conflitos de entrada/corrente, escopos de IP e RAM, modelos e preço zero. Nenhuma equivalência automática nos conflitos críticos.
4. Homologar amostra estratificada de pelo menos 150 registros por responsável técnico, separar treino/validação e medir precisão/recall somente contra rótulos aprovados.
5. Só então ligar filtros canônicos, revisão, comparação explicável e publicação atômica ao dashboard principal. Rollback deve restaurar revisões e comparações coerentes.

Até esses gates, os números de staging não representam uma nova revisão publicada, e nenhuma decisão comercial deve depender das propostas do parser. Pendências de negócio incluem autoridade para produtos de segurança, política de exportação completa/parcial, data/moeda/unidade de preço Eco e qual ocorrência Portwell é vigente.
