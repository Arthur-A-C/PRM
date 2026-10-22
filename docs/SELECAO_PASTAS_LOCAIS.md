# Seleção de pastas e arquivos do computador do usuário

O PRM roda num servidor (Windows + Docker, `http://192.168.0.199:<porta>`). Cada usuário (Kauê,
Arthur, Daniel) usa o navegador do próprio computador. Um caminho como `C:\Users\Arthur\Fotos`
existe só no computador do Arthur e o servidor não consegue abri-lo. Por isso, todo módulo que
precisa de arquivos recebe-os **pelo navegador**: o usuário escolhe a pasta, o navegador envia
cópias ao servidor e o resultado volta como download. Nada é gravado no computador do usuário.

## Onde aparece

| Módulo | Página | O que selecionar |
|---|---|---|
| Resolução de imagens | Digitalização → Resolução de imagens | Pasta com fotos (JPG, JPEG, PNG, WEBP), com subpastas |
| Geração de datasheets em lote | Digitalização → Geração em lote | Pasta do lote (uma subpasta por CIGAM/SKU) |
| Publicação em lote | Publicação em Lote | Pasta do lote (uma subpasta por CIGAM/SKU) |
| Cadastro via API | Cadastro via API | Pasta do lote, ou a pasta de um SKU (vale como `SKU.zip`) |
| Digitalização individual | Digitalização | Fotos: arquivos ou **Selecionar pasta de fotos do computador**; PDF do fabricante, 3D, manuais, certificados e outros documentos já são escolhidos no computador |
| Importação de CSV/XLSX | Cadastro, Remoção de arquivos e demais formulários | Os campos de arquivo já abrem o seletor do computador |

Nos módulos de lote, o envio de um ZIP continua funcionando. A pasta é só uma alternativa que
dispensa compactar.

## Como usar (Chrome ou Edge, em qualquer computador da rede)

1. Abra o PRM pelo endereço do servidor e entre com o seu usuário.
2. Na página do módulo, clique em **Selecionar pasta do computador**. Para escolher arquivos
   soltos, use **Selecionar arquivos**.
3. O navegador pede confirmação para "carregar" os arquivos da pasta. Confirme: o envio vai
   para o PRM, nunca para a loja.
4. Confira o resumo: nome da pasta, quantidade, tamanho, subpastas e **ignorados**. Em
   **Prévia dos arquivos** aparecem miniaturas das fotos, a lista com a estrutura relativa e o
   motivo de cada arquivo ignorado (oculto, vazio ou tipo que o módulo não usa).
5. Clique na ação do módulo (**Enviar e ver prévia**, **Importar e validar**…). A barra mostra o
   progresso do envio; **Cancelar envio** interrompe e apaga do servidor o que já chegou.
6. Se a conexão cair ou a página for recarregada, selecione **a mesma pasta** e envie de novo.
   O PRM retoma do último bloco recebido, sem reenviar o que já chegou.
7. Erros aparecem na própria página com o nome do arquivo.
8. Na Resolução de imagens, depois da conversão, use **Baixar imagens convertidas (ZIP)**
   (mesma estrutura de subpastas) ou **Baixar com Backup-fotos**. Para apagar a cópia do
   servidor, use **Descartar arquivos do servidor**. Sem uso, ela expira após 24 horas.

Firefox e Safari permitem **Selecionar arquivos**, mas a seleção de pastas é garantida apenas
no Chrome e no Edge.

## Como funciona

1. `POST /api/v1/envios` registra o envio: perfil (`imagens` ou `lote`), nome da pasta e lista
   de `{caminho relativo, tamanho}`. O nome da pasta escolhida é removido dos caminhos.
2. Cada arquivo segue em blocos (padrão 8 MiB), três arquivos por vez:
   `PUT /api/v1/envios/{id}/arquivos/{indice}?inicio=<byte>`. Se o servidor já tiver outra
   quantidade, responde `409` com `recebido` e o navegador continua dali. Falhas de rede são
   tentadas de novo com espera crescente.
3. `POST /api/v1/envios/{id}/concluir` exige todos os arquivos completos.
4. O módulo usa o envio:
   - **Lotes** recebem `envio=<id>` no lugar do campo ZIP. O servidor monta o mesmo ZIP que o
     usuário enviaria (pasta selecionada = raiz) e chama o fluxo existente sem alterá-lo. Depois
     que o lote é criado, a área do envio é apagada.
   - **Resolução de imagens** converte a cópia em `/api/v1/imagens/envios/{id}/…` com o mesmo
     código da conversão em pasta (backup verificado, registro, retomada) e entrega o ZIP em
     `/resultado.zip`.
5. `GET /api/v1/envios/{id}` mostra o progresso por arquivo. `DELETE` cancela e apaga.

## Segurança e isolamento

- **Usuário autenticado**: só gestores e desenvolvedores. Toda alteração exige o token CSRF da
  sessão (`X-CSRF-Token`).
- **Isolamento**: cada envio fica em `data/uploads/<organização>/<usuário>/<id>/` e só o dono o
  vê. Outro usuário recebe `404`, mesma resposta de um envio inexistente. O mesmo vale para as
  tarefas da Resolução de imagens.
- **Sem caminhos do servidor**: o navegador envia apenas caminhos relativos. São recusados `..`,
  `.`, caminhos absolutos, letras de unidade, `\\servidor`, caracteres inválidos no Windows,
  nomes reservados (`CON`, `LPT1`…), nomes repetidos que diferem só em maiúsculas, e qualquer
  destino que, depois de resolvido, saia da área do envio. As respostas mostram o nome da pasta
  escolhida, nunca o caminho interno do servidor.
- **Conteúdo**: as extensões aceitas dependem do módulo (as mesmas que os parsers de lote
  aceitam). Cada arquivo só é aceito quando os primeiros bytes correspondem à extensão: um
  executável renomeado para `.jpg` é recusado. Os parsers de lote mantêm as próprias validações
  de ZIP.
- **Limites** (variáveis `PRM_*` no `.env`; o módulo de lote mantém também o seu próprio limite):

  | Variável | Padrão | Efeito |
  |---|---|---|
  | `PRM_UPLOAD_STORAGE_DIR` | `data/uploads` | Área temporária dos envios |
  | `PRM_UPLOAD_MAX_MIB` | `2048` | Total por envio |
  | `PRM_UPLOAD_MAX_FILE_MIB` | `200` | Por arquivo |
  | `PRM_UPLOAD_MAX_FILES` | `5000` | Arquivos por envio |
  | `PRM_UPLOAD_CHUNK_MIB` | `8` | Tamanho máximo de um bloco (o `nginx` aceita até 1024 MiB por requisição) |
  | `PRM_UPLOAD_RETENTION_HOURS` | `24` | Envios sem uso são apagados |
  | `PRM_UPLOAD_MAX_OPEN` | `10` | Envios em aberto por usuário |

  Antes de aceitar, o servidor confere se há espaço livre para o dobro do envio.
- **Pasta do servidor (opcional)**: a Resolução de imagens só oferece o modo "Pasta no servidor
  do PRM (avançado)" quando `PRM_IMAGE_TOOL_ROOTS` está definido. Sem a variável, esse modo fica
  desligado: antes, o padrão era a pasta do usuário do servidor. O `compose.yaml` já define
  `/mnt/prm-fotos`, então nada muda no Docker.

## Docker

Nenhuma alteração em `compose.yaml`, volumes ou dados. A área `data/uploads` é temporária e fica
dentro do contêiner (`/app/data`, de propriedade do usuário `prm`). Se o contêiner for recriado,
os envios em andamento se perdem e basta enviar de novo. O ZIP de resultado é baixado pelo
navegador.

## Testes

- `tests/test_local_uploads.py`: caminhos, conteúdo, limites, blocos, retomada, envio paralelo,
  isolamento por usuário e organização, ZIP para os lotes, expiração, API com CSRF, lote criado
  a partir de pasta e conversão de imagens com download.
- Teste manual no navegador (Edge headless, pela API real): seleção de pasta com subpastas e
  arquivos ignorados, envio limitado a 400 KB/s, interrupção em 20% e retomada do mesmo envio,
  prévia, conversão, ZIP 1500 × 1500 com estrutura preservada, descarte, e lote de datasheets a
  partir da pasta.
