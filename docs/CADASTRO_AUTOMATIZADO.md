# Cadastro automatizado — estado operacional

Atualizado em 08/10/2026. A implementação está na página já existente de **Digitalização**, restrita a usuários `gestor` autenticados, com CSRF. O objetivo desta etapa local é preparar e revisar dados sem alterar lojas ou ERP.

## Fontes auditadas

O arquivo `exports_woocommerce_choice_sag_portwell.zip` foi recebido em Downloads e copiado para `data/imports/` (ignorado pelo Git). O original não foi modificado. Seu SHA-256 é `844690755b70b314cb7a331d5c1b0265c28e7b8317d49395bed83bdda87bc32f`.

| Loja | Arquivo no ZIP | SKUs | Colunas | Blocos de atributos | Linhas com colunas finais ausentes | Nomes com global/local divergente |
|---|---|---:|---:|---:|---:|---:|
| Choice | `export_woocommerce_choice.csv` | 2.714 | 116 | 15 | 350 | 4 |
| SAG | `export_woocommerce_sag.csv` | 298 | 104 | 16 | 100 | 0 |
| Portwell | `export_woocommerce_portwell.csv` | 1.018 | 133 | 18 | 0 | 1 |

Os blocos do export podem exceder 15, mas o limite é **por produto novo**. Produtos já cadastrados com 16 ou 18 atributos não são truncados. Quando uma linha de lote antigo tem menos células que o cabeçalho, apenas a cauda é completada com células vazias; o campo existente nunca é deslocado. Se houver colunas extras ou SKU duplicado no export, a leitura falha. O export da empresa é escolhido automaticamente pelo código `choice`, `sag` ou `portwell`; um CSV enviado manualmente substitui a referência local naquela operação. O ZIP pode ser configurado por `PRM_WOO_EXPORTS_ZIP` no ambiente do servidor.

Ambiguidades global/local encontradas: Choice — `Campo de visão`, `Faixa de medição`, `I/Os configuráveis`, `Resolução`; Portwell — `Corrente nominal`. A grafia canônica é lida do próprio export, mas não se atribui flag global para um novo uso desses nomes sem conferência. A prévia de planilha usa os nomes observados no export da empresa para normalizar atributos.

## Fluxo disponível agora

Na Digitalização, selecione a empresa, SKU e nome técnico, envie os documentos e rode a análise. Na seção **Cadastro automatizado**, revise título comercial, categorias, atributos JSON e descrições. É possível gerar uma descrição HTML fundamentada nos dados extraídos, consultar o SKU na loja em modo somente leitura, fazer prévia de uma planilha de lote, descobrir arquivos por SKU, baixar CSV WooCommerce, arquivo CIGAM e pacote ZIP real.

O CSV usa cabeçalhos reais do export, não índices. Para SKU existente, parte da linha integral e preserva campos comerciais e metadados não alterados; para SKU novo, cria rascunho. A geração do CSV requer a caixa de aprovação marcada, mas **baixar o arquivo não publica nem importa o produto**. O cabeçalho `X-PRM-Review-Warnings` informa quantos avisos precisam de revisão. A planilha CIGAM deixa campos desconhecidos em branco e sinaliza a contagem. O ZIP contém manifesto, documentos enviados e imagens realmente processadas.

O serviço de consulta WooCommerce usa variáveis de ambiente por empresa: `PRM_WOO_CHOICE_URL`, `PRM_WOO_CHOICE_KEY`, `PRM_WOO_CHOICE_SECRET` (trocar `CHOICE` por `SAG` ou `PORTWELL`). Não colocar segredos no navegador, no Git ou nesta documentação. Sem credenciais, a prévia ao vivo retorna erro de configuração e as exportações locais continuam disponíveis. A consulta é GET; não há POST, PUT ou DELETE nesta etapa.

## Limites e próxima fase

- Integração de criação/atualização WooCommerce, envio de mídia e documentos `wcda_arquivos`, confirmação pós-gravação, publicação, idempotência e rollback: **não implementados**. A automação Playwright recebida cobre Choice/SAG, mas seus seletores e regras ainda precisam de validação em ambientes de teste; Portwell requer mapeamento próprio.
- O padrão oficial de assinatura Portwell, o comportamento atual do metadado `_hide_product_price` e equivalências ambíguas de atributos/categorias precisam ser confirmados na loja. Novos produtos não recebem esse metadado automaticamente e não são publicados.
- A prévia de planilha não inicia cadastro em lote. Faltam fila persistente, aprovação por item, dry-run de 3–5 produtos, retomada, histórico exportável e relatório de mudanças antes/depois. Não executar lote real até essa fase.
- O modelo CIGAM é exportado em XLSX, mas não há método documentado de escrita no ERP. Nenhuma escrita CIGAM deve ser improvisada.
- A descrição é determinística a partir dos dados disponíveis; ainda não há um serviço Claude específico validado. A análise Qwen/datasheet existente permanece intacta.
- O ZIP baixa os arquivos enviados na sessão; a associação persistente e o uso do mesmo pacote em um upload futuro ainda faltam.

Primeiro teste seguro: usar um SKU fictício e documentos de teste, manter a aprovação de CSV desmarcada durante a revisão, conferir a prévia e as exportações locais. Antes de qualquer cadastro real, validar as credenciais em staging da loja, revisar os campos, o orçamento e os arquivos; solicitar autorização explícita para o primeiro grupo de 3–5 produtos. A suíte local foi executada com `.\.venv\Scripts\python.exe -B -m pytest -q`: **69 testes aprovados, 3 avisos**. Nenhum banco ou loja recebeu escrita.
