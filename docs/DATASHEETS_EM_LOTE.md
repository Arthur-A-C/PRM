# Geração de Datasheets em Lote

Implementação de 20/10/2026. Acesso: **Digitalização → Geração em Lote**, ou
`/digitalizacao/lotes`. Exige sessão PRM. Cada usuário consulta apenas os próprios
lotes, dentro da sua organização; conhecer um identificador não concede acesso.
O fluxo individual e os templates Portwell, Choice e SAG foram preservados.

## Identificação pelo nome da pasta (21/10/2026)

Na mesma tela, selecione **Utilizar nome da pasta como código CIGAM/SKU**, escolha
Choice, Portwell ou SAG e envie um ZIP local. **CSV não é obrigatório nesse modo.**
Nenhuma pasta de rede é consultada e não se recebe caminho do disco do servidor.

```text
importacao.zip
├── Produtos/                     # opcional; também aceita SKUs diretamente na raiz
│   ├── 119002000072/
│   │   ├── datasheet.pdf
│   │   ├── Fotos/principal.png
│   │   ├── manual.pdf
│   │   └── desenho.step
│   └── 00119002000073/
│       └── fabricante.pdf
└── complemento.csv               # opcional
```

- A raiz automática reconhece `Produtos/` ou `Products/`. Para outra estrutura,
  indique **Pasta raiz dentro do ZIP**, por exemplo `Meu lote/Produtos`; nunca `Z:`.
  Os filhos imediatos dessa raiz são os produtos. Subpastas pertencem ao produto,
  não viram SKUs adicionais. Pastas vazias explícitas no ZIP aparecem inválidas.
- O SKU é o nome original, sem conversão numérica, remoção de zeros ou trim.
  Nomes inseguros são recusados; SKUs repetidos, inclusive diferenças apenas de
  maiúsculas, não são processados. Arquivos soltos fora dos produtos são recusados.
- Um CSV opcional usa `codigo` obrigatório e `nome`, `empresa`, `descricao`,
  `categoria`, `observacoes`, `datasheet_original` opcionais. As linhas precisam
  corresponder a pastas pelo código **exato**, incluindo zeros/maiúsculas. Código
  sem pasta, linha duplicada ou empresa divergente bloqueiam a importação; não há
  substituição silenciosa do SKU. Pastas sem linha no CSV continuam elegíveis.
- Sem nome complementar, o gerador usa o SKU como referência/modelo e sinaliza
  revisão humana; não inventa um nome técnico. A análise gera descrição e
  especificações a partir das fontes pelo pipeline existente.
- O PDF principal é identificado pelo nome exato do SKU, padrão datasheet/ficha
  técnica, ou por ser o único PDF. Empate/ausência exige `datasheet_original` no
  CSV (caminho completo no ZIP ou relativo à pasta do produto), sempre dentro do
  mesmo SKU. Não escolhemos arbitrariamente entre PDFs candidatos.
- PDFs, JPG/JPEG, PNG e WebP são validados e enviados ao gerador existente. Limite
  por produto: 5 PDFs, 20 imagens e 60 MiB; mantidos limites globais do ZIP e PDF
  de até 100 páginas. Imagens exigem formato real compatível e até 40 megapixels.
- ZIP/RAR/7Z, STEP/STP, DWG/DXF são aceitos como documentos auxiliares: ficam
  preservados, não são descompactados nem enviados à IA. Outras extensões são
  recusadas. Isso **não** homologa os formatos de upload na loja.
- A prévia apresenta pasta, SKU, fontes, papéis, tamanhos, avisos e erros. Não
  chama IA nem inicia a fila automaticamente. Somente **Iniciar produtos válidos**
  confirma o processamento pago. Arquivos inválidos em um produto não impedem os
  demais; problemas estruturais/de segurança no ZIP/CSV bloqueiam o lote.
- O download mantém os PDFs/relatórios anteriores e acrescenta, por empresa/SKU,
  `analysis.json` quando gerado e `fontes/` com os arquivos originais. Os arquivos
  são preservados mesmo se a geração falhar. Não contém credenciais.

O modo **Utilizar CSV do CIGAM** continua com as mesmas regras anteriores,
inclusive lotes com empresas diferentes. Clientes antigos da API, que não enviam
`identificacao`, continuam nesse modo. Não houve migração da fila ou dos catálogos.

### Limite de integração com a loja

Digitalização em Lote não tinha opção de escrita WooCommerce e **continua sem
publicação automática**. Esta adaptação não libera upload, criação de produto ou
edição de metadados. O cadastro via API separado e o serviço WCDA existente
continuam com seus bloqueios de produção e Dry Run. O pacote preserva as fontes
para a próxima revisão; não é autorização de atualização nem payload final.
Antes de conectar a publicação completa, confirmar SKU exato/único existente,
preservar preço/estoque/status/metadados e imagens/documentos, preparar backup e
compor o Dry Run com o WCDA, conforme [homologação](WCDA_HOMOLOGACAO.md).
Playwright permanece disponível. Não há gravação habilitada por selecionar o modo pastas.

## Operação local

Na raiz oficial do projeto, reinicie o servidor da forma habitual para carregar as
novas rotas. Abra outro terminal PowerShell e mantenha o worker executando:

```powershell
.\.venv\Scripts\python.exe scripts/datasheet_batch_worker.py
```

Não é necessário instalar dependências adicionais às que o gerador já utiliza.
Não há migração do PostgreSQL. Web e worker precisam compartilhar a mesma pasta
local, permissões de arquivos e configurações `PRM_BATCH_*`. O worker lê o `.env`;
reinicie-o após trocar a chave/configuração. O modelo é registrado no lote ao
iniciar ou reprocessar. Não há fallback automático para outro modelo.

1. Escolha identificação por pastas (CSV opcional) ou por CSV (modelo na página).
2. Selecione a empresa no modo pastas; envie ZIP e delimitador do CSV, se houver. Esta etapa não faz chamadas à IA.
3. Confira a tabela: itens inválidos não impedem os válidos.
4. Clique em **Iniciar produtos válidos** e confirme o uso da API paga.
5. A página consulta o progresso a cada cinco segundos; é possível sair e voltar.
6. Baixe PDFs individuais ou ZIP com relatórios. Revise resultados sinalizados.

O worker não é iniciado automaticamente pelo servidor. Se estiver parado, itens
continuam na fila, persistidos. Para consumir no máximo um item:

```powershell
.\.venv\Scripts\python.exe scripts/datasheet_batch_worker.py --once
```

`Ctrl+C` interrompe novas retiradas da fila e aguarda os produtos em execução,
limitados pelo timeout. Encerramento forçado é tratado pelo lease/watchdog.

Nenhum worker permanente, geração real paga ou deploy é iniciado pela implantação
do código. Em operação contínua, configure o comando acima no gerenciador de
serviços da instalação; não o publique como endpoint HTTP.

## Arquivos de entrada

Formato legado quando **Utilizar CSV do CIGAM** está selecionado:

```text
importacao.zip
├── produtos.csv
└── datasheets/
    ├── 10001.pdf
    ├── 10002.pdf
    └── 10003.pdf
```

```csv
codigo,nome,empresa,datasheet_original,descricao,categoria,observacoes
10001,Controle Remoto EX,SAG,datasheets/10001.pdf,,Controle,
10002,Computador Industrial,PORTWELL,datasheets/10002.pdf,,Box PC,
10003,Equipamento Industrial,CHOICE,datasheets/10003.pdf,,Automação,
```

- `codigo`, `nome`, `empresa` são obrigatórios. Código é texto: zeros à esquerda são
  preservados. Não use nomes reservados ou caracteres inválidos para arquivos Windows.
- UTF-8 com ou sem BOM. Delimitadores: vírgula, ponto e vírgula ou tabulação.
  Campos contendo o delimitador devem ser colocados entre aspas, conforme CSV.
- Empresa ignora maiúsculas/minúsculas; apenas Choice, SAG e Portwell.
- `datasheet_original` é opcional. Sem ele, o nome-base do PDF deve ser exatamente
  o código, ignorando maiúsculas/minúsculas. Não se usa fuzzy ou correspondência
  parcial: `10001` não encontra `100010` nem `manual-10001`. Dois candidatos exigem
  caminho explícito.
- Duplicatas código/empresa invalidam todas as linhas envolvidas; o mesmo código
  em empresas diferentes é permitido.
- Somente um CSV e arquivos PDF no ZIP. PDF protegido, ilegível, vazio ou com mais
  de 100 páginas é inválido. A leitura estrutural não comprova precisão técnica;
  ausência de informações continua sujeita às pendências do pipeline.
- Todos os caminhos são relativos, com `/`. Caminhos absolutos, `..`, barras
  invertidas, links, arquivos especiais, extensões extras, criptografia e
  compressão excessiva são rejeitados. Não se executa `extractall`.

## Arquitetura e custo

Reutiliza `gerar_datasheet_com_claude`, prompts e `validate_analysis`, os motores
`datasheet_choice`, `datasheet_sag`, `datasheet_portwell` e o núcleo ReportLab.
Dados do CSV entram como cadastro, categoria e observações, não como fatos
comprovados. Os anexos originais continuam sendo a referência técnica.

Como já há armazenamento local para digitalizações e a fila de reuniões depende
de migração específica, este módulo utiliza SQLite transacional independente,
em `data/datasheet_batches/queue.sqlite3`, junto aos arquivos privados dos lotes.
Não altera `prm_mvp`, staging, catálogos publicados ou a fila de reuniões.

O worker reivindica um item em transação `BEGIN IMMEDIATE`, respeitando o limite
global de itens em execução na mesma fila. Cada produto roda em subprocesso com
timeout, identificador de tentativa e watchdog próprio. Resultados de tentativas
expiradas não podem substituir resultados atuais. A fila não é um `BackgroundTask`
em memória e o servidor web não precisa ficar com a requisição aberta.

- Concorrência padrão: **1 produto**, com no máximo uma chamada à IA por produto
  naquele instante. O pipeline pode fazer geração e revisões sequenciais.
- Sonnet segue o fluxo individual, inclusive até duas revisões: até três chamadas
  por tentativa. Timeout de produto inclui todo esse trabalho.
- Retry somente para HTTP 429 e 500/502/503/504, com backoff 15s/30s (limite 300s).
  Padrão de até três tentativas por item; retries internos do SDK são desativados
  neste fluxo para não multiplicar tentativas.
- Retry refaz a tentativa e **pode gerar custo adicional**, inclusive quando a falha
  ocorreu na revisão. Configure `PRM_BATCH_MAX_ATTEMPTS=1` para não tentar novamente.
- Timeout, falha de conexão com resultado incerto, erro de contrato e interrupção
  não são reenviados automaticamente. Após expirar o lease (timeout + 60 segundos),
  um worker ativo sinaliza o item como erro para conferência.
- Não é possível garantir exatamente uma cobrança quando há perda de conexão ou
  queda abrupta. O operador deve conferir antes de reprocessar.
- Pendências ou avisos do motor tornam o PDF **Requer revisão**. Não há aprovação
  automática nem publicação no catálogo/WooCommerce.
- **Reprocessar falhas** só reenfileira itens `error`; não toca concluídos, itens em
  revisão ou inválidos. Corrija CSV/PDF e envie novo lote para erros de entrada ou
  para solicitar explicitamente uma nova geração de um resultado concluído.

## Persistência, exportação e retenção

Cada lote recebe um UUID próprio; originais são armazenados por ID interno, não
por caminho fornecido pelo usuário. Cada tentativa tem pasta própria, PDF e JSON
de análise. As mensagens públicas de erro não contêm respostas cruas do provedor.
Logs identificam lote, item, tentativa e estado, nunca chave ou documento completo.
O worker armazena fontes privadas: mantenha permissões restritas no diretório.

ZIP de saída:

```text
CHOICE/10003.pdf
PORTWELL/10002.pdf
SAG/10001.pdf
relatorio_processamento.csv
erros.csv
```

Relatórios UTF-8 com BOM incluem código, produto, empresa, status, arquivo e erro.
`erros.csv` inclui também itens inválidos e resultados que requerem revisão.
Valores iniciados com caracteres de fórmula são escapados para abertura em planilhas.
Downloads durante processamento representam os resultados disponíveis naquele instante.

Histórico apresenta os **100 lotes mais recentes** do usuário; URLs diretas continuam
funcionando para lotes anteriores. A limpeza é explícita, não roda ao abrir a página:

```powershell
# Simulação: lista candidatos, não apaga
.\.venv\Scripts\python.exe scripts/datasheet_batch_worker.py --cleanup
# Remove arquivos de lotes inativos vencidos; preserva metadados/histórico
.\.venv\Scripts\python.exe scripts/datasheet_batch_worker.py --cleanup --apply
```

Retenção padrão: 90 dias após a última atualização, inclusive lotes nunca iniciados.
Lotes com itens na fila ou em processamento nunca são removidos. Após limpeza,
downloads e reprocessamento ficam indisponíveis; é necessário novo upload. Exclusão
por `--apply` é permanente, salvo backup externo. Faça backup **da pasta inteira**,
incluindo SQLite e arquivos, preferencialmente com web/worker parados.

## Configuração

Ver `.env.example`. Variáveis:

| Variável | Padrão | Função |
|---|---:|---|
| `PRM_BATCH_STORAGE_DIR` | `data/datasheet_batches` | Pasta local compartilhada com o worker |
| `PRM_BATCH_UPLOAD_MIB` | 100 | ZIP enviado |
| `PRM_BATCH_EXPANDED_MIB` | 500 | Soma dos arquivos descompactados |
| `PRM_BATCH_MAX_FILES` | 1000 | Entradas no ZIP, incluindo pastas |
| `PRM_BATCH_MAX_PRODUCTS` | 500 | Linhas do CSV |
| `PRM_BATCH_MAX_RATIO` | 200 | Razão máxima de compressão por arquivo |
| `PRM_BATCH_CONCURRENCY` | 1 | Produtos simultâneos na fila |
| `PRM_BATCH_TIMEOUT_SECONDS` | 900 | Tempo por produto |
| `PRM_BATCH_MAX_ATTEMPTS` | 3 | Tentativas para falhas transitórias |
| `PRM_BATCH_RETENTION_DAYS` | 90 | Retenção de lotes inativos |

Limites adicionais: 30 MiB por arquivo, 100 páginas por PDF, 10.000 caracteres por
campo do CSV. Todos os processos devem usar a mesma configuração de concorrência.
SQLite/local disk é adequado ao PRM em **um único servidor**, não a implantação
distribuída ou pastas de rede. Para múltiplos hosts, migrar a fila para PostgreSQL
e armazenamento compartilhado apropriado.

## API

Base `/api/v1/digitalizacao/lotes`, sempre autenticada e limitada ao proprietário.
POSTs exigem `X-CSRF-Token`.

| Método / rota | Ação |
|---|---|
| `GET /modelo.csv` | Modelo de importação |
| `POST /` | Multipart `arquivo` e `delimitador`: importar/validar sem IA |
| `GET /` | Histórico |
| `GET /{id}` | Itens, validação, estados e progresso |
| `POST /{id}/iniciar` | Enfileirar válidos |
| `POST /{id}/reprocessar` | Reenfileirar apenas falhas |
| `GET /{id}/download` | ZIP e relatórios |
| `GET /{id}/produtos/{item}/pdf` | PDF individual |

Rotas-base são registradas sem barra final; FastAPI redireciona quando necessário.

## Arquivos envolvidos

Novos: `app/services/datasheet_batches.py`, `app/routers/datasheet_batches.py`,
`scripts/datasheet_batch_worker.py`, `app/templates/datasheet_batches.html`,
`app/static/js/datasheet-batches.js`, `app/static/css/datasheet-batches.css`,
`tests/test_datasheet_batches.py`, este documento.
Verificação de interface: `scripts/batch_visual_smoke.cjs` (navegador headless,
servidor temporário e endpoints simulados, sem acessar a aplicação real).

Integração: `app/config.py`, `app/main.py`, `app/routers/pages.py`,
`app/templates/base.html`, `app/templates/shell.html`,
`app/templates/digitalizacao.html`, `tests/test_operations_workspace.py`,
`.env.example`, `.gitignore`, `README.md`, `CHANGELOG.md`, `docs/API.md`, `docs/STATUS.md`.
Nenhuma mudança no `.env` real, prompts, serviço individual ou templates PDF.

## Verificação e limites reais

Os testes usam PDFs sintéticos e cliente Anthropic simulado, com geração pelo motor
real das três empresas. Cobrem CSV/BOM/delimitadores, arquivos ausentes/corrompidos,
duplicatas, caminhos, Zip Slip, compressão excessiva, autenticação/CSRF/isolamento,
fila persistida, concorrência, lease expirado, backoff, timeout, reprocessamento,
retenção e ZIP de saída. Consultar `STATUS.md` para o resultado da execução.

Ainda requer homologação com PDFs reais e a API paga, volume representativo e
permissões de disco da instalação. Não foi feito deploy, migração de banco ou
configuração de serviço Windows. Os arquivos dos fabricantes são dados não
confiáveis; a checagem estrutural não substitui antivírus/sandbox de PDF em ambientes
expostos à internet.
