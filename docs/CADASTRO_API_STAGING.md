# Cadastro via API — arquivos de produtos existentes (staging)

Data: 20/10/2026. **Não substitui ainda o Playwright em produção.**
Atualizado em 21/10/2026: escopo exclusivo de imagens e documentos `_wcda_arquivos`
de produtos já cadastrados; dados comerciais seguem no fluxo CSV. Executor
implementado para staging e testado com mocks; as três lojas atuais seguem bloqueadas.

## Auditoria real, somente leitura

`scripts/audit_store_contract.py` consultou o banco e até cinco produtos por loja:

- Organização única encontrada: **Organização PRM**,
  `8cbaed7f-d92d-463c-8045-10bc86b6b160`.
- Portwell (`portwell`) e Choice (`choice-tech`) estão vinculadas a esse UUID.
  Eco também pertence à organização; não recebe integração de cadastro.
- Não existe registro `Company` da SAG no banco auditado. Nenhum registro ou
  vínculo foi criado silenciosamente.
- `app/services/bootstrap.py:ensure_reference_data` cria/localiza a organização
  pelo `PRM_ORGANIZATION_NAME` e vincula as empresas de referência a ela.
  O UUID não é o ID de empresa, usuário, loja WordPress ou produto.

Para liberar a UI aos gestores dessa organização, o operador deve preencher:

```dotenv
PRM_STORE_ORGANIZATION_ID=8cbaed7f-d92d-463c-8045-10bc86b6b160
```

O agente não alterou o `.env`. Confirmar que a SAG será administrada pela mesma
organização antes de configurar suas credenciais nesse escopo. Instalações com
outras organizações não devem reutilizar esse UUID. Lotes são isolados por
organização **e proprietário**; todas as operações exigem gestor e as mutações,
CSRF. O worker também confere organização e origem antes de cada item.

### `_wcda_arquivos`

Estrutura observada em entradas não vazias de Choice e SAG:

```json
[
  {
    "label": "<texto>",
    "url": "<URL do documento>",
    "filename": "<texto>",
    "filesize": "<texto>"
  }
]
```

- Choice: quatro dos cinco produtos amostrados expuseram o campo, com 1–3 entradas.
- SAG: cinco produtos com uma entrada cada.
- Portwell: cinco listas vazias; não foi possível inferir estrutura de entradas.
- Nas entradas inspecionadas, não apareceu `attachment_id` ou outro ID de mídia.
  `filesize` é texto na amostra, não necessariamente bytes numéricos.
- O retorno WooCommerce contém o ID da **metadata**, que não deve ser confundido
  com ID de mídia. Nenhum desses IDs foi usado para gravação.
- O plugin PHP/snippet de salvamento não está no repositório. O formulário
  `wcda_arquivos[index][label]` do Playwright não comprova o contrato persistido.
- Nenhuma atualização de metadata foi tentada. Portanto: **não está confirmado
  que `_wcda_arquivos` possa ser gravado diretamente pelo WooCommerce REST**.

Dependência para concluir: fornecer plugin/snippet que registra e salva o metabox,
confirmar schema/validação e testar em staging. Se o contrato não for exposto,
propor endpoint específico autenticado com `edit_post(product_id)`, whitelist de
campos, validação dos attachments/MIME, merge preservando documentos anteriores,
idempotência, controle de versão e releitura. Nenhum plugin foi instalado.

## Fluxo implementado

Acesso: **Digitalização → Cadastro via API — prévia e homologação**,
`/digitalizacao/cadastro-api`.

1. Selecionar Choice, SAG ou Portwell.
2. Importar CSV/XLSX/XLSM com coluna SKU/Código/CIGAM; CSV de uma coluna sem
   cabeçalho também é aceito. Códigos textuais preservam zeros iniciais, duplicatas
   são eliminadas e notação científica é rejeitada.
3. Selecionar ZIP contendo pastas nomeadas exatamente pelo SKU:

```text
arquivos.zip
├── 00123/
│   ├── 00123_variante.png
│   ├── 00123_foto2.jpg
│   ├── 00123_Datasheet.pdf
│   └── 00123_Manual de instalação.zip
└── ABC-9/
    ├── Fotos/
    │   ├── produto.png
    │   └── front.png
    └── Desenho 3D.zip
```

4. O worker localiza a pasta/SKU exatos e consulta a loja. Produto inexistente não
   é criado. Mostra arquivos, quantidades já cadastradas, warnings e erros.
5. Itens sem bloqueios ficam `review`; conflitos ou WCDA incompatível ficam
   `blocked`. Aprovar o Dry Run e só então confirmar, com política de staging
   habilitada para a origem e o SKU exatos.
6. Acompanhar pelo polling, sair/voltar pelo histórico e baixar relatório CSV.
   Erro de um item não impede a prévia dos demais.
7. Reprocessar refaz a prévia de itens com erro; exige nova confirmação. Não
   reenfileira concluídos, bloqueados ou estados incertos de interrupção.

### Escopo: somente arquivos (21/10/2026)

O módulo **não altera dados comerciais**. Nome, descrição completa e resumida,
categorias, atributos, SKU, preço, estoque, status e demais metadados continuam no
fluxo CSV do PRM. A API grava apenas `images` e o metadado `_wcda_arquivos` de um
produto **existente**; SKU inexistente bloqueia o item e nada é criado.

Entrada no modo **Utilizar nome da pasta** (planilha opcional): SKU exato da pasta
ou de `SKU.zip`, zeros iniciais preservados. Formatos aceitos:

- pacote validado da Digitalização (`SKU/manifest.json`, `Fotos/`, PDFs, 3D): manifesto
  `validated` com mesmo SKU/CIGAM/empresa, caminhos relativos e SHA-256 conferidos;
  arquivo não declarado bloqueia;
- ZIP da Geração em Lote: `EMPRESA/SKU.pdf` vira `SKU_Datasheet.pdf`, `fontes/` só é
  inventariada, relatórios CSV são ignorados.

Dry Run por item (`GET /api/v1/cadastro-api/{lote}/dry-run` e tabela da tela):

- `images.actions`: `upload`, `already_linked` (o URL vinculado contém a identidade
  `prm-<sha256>` dos mesmos bytes), `duplicate_in_package`, `conflict` (mesmo nome
  sem identidade: bloqueia). Ordem final mostrada; IDs só existem após upload;
- imagem principal: preservada por padrão. A nova principal só substitui a atual com
  aprovação explícita `replace_main`; a anterior vai para a galeria, nunca é removida;
- `documents`: modo `append` (preserva lista e ordem), `first_inclusion` (metadado
  existente e vazio; rollback restaura `[]`) ou `blocked` (ausente, duplicado ou não
  lista). Ações `add`, `already_linked`, `conflict` (label/arquivo já cadastrados em
  outra URL). Entrada `label/url/filename/filesize`, `url` nula até o upload;
  `filesize` no formato observado (`90.8 KB`, `2.84 MB`);
- `ignored`: formatos sem upload homologado (.step, .dwg, .dxf, .rar, .7z) e, em
  pacotes antigos que ainda trazem o datasheet original do fornecedor junto ao datasheet
  gerado, o original (nunca publicado). Dry Runs preparados antes dessa regra que ainda
  incluam o original não podem receber liberação nem ser executados: refazer a prévia;
- `rollback`, `dependencies`, `write_gate`, `blockers`, `dry_run_sha256`.

Aprovação: `POST /api/v1/cadastro-api/{lote}/aprovar` com `{"skus": [...]}` (individual)
ou sem corpo (todos os prontos) e `"replace_main": [...]` opcional. Registra o hash do
Dry Run; não enfileira nem autoriza escrita. `confirmar` só aceita itens aprovados com
o mesmo hash e com a política de staging válida.

Execução (somente staging autorizado; testada com mocks):

1. Relê o produto pelo SKU e compara o snapshot (imagens + WCDA) com a prévia.
2. Para cada arquivo: journal por hash; se o journal não confirma, busca a mídia na
   biblioteca WordPress pela identidade `prm-<sha16>`; só então faz upload com nome
   `prm-<sha256>.jpg` (imagens) ou `<nome>_prm-<sha16>.pdf/.zip` (documentos).
3. Relê o produto; alteração concorrente aborta sem PUT e preserva a mídia enviada.
4. Um único PUT com `images` e/ou `meta_data:[{id,key:_wcda_arquivos,value}]`.
5. Releitura: IDs das imagens, lista WCDA e hash de todos os campos comerciais e
   demais metadados devem coincidir. Senão: erro, sem retry, plano de recuperação.

Falhas: upload recusado (HTTP ≠ 201) pode ser reenviado após nova aprovação; resposta
perdida só é resolvida pela identidade na biblioteca; PUT sem resposta só é aceito se
a releitura for idêntica ao esperado. Recuperação registrada no journal restaura só
`images` e `_wcda_arquivos` anteriores e **nunca exclui mídia** da biblioteca. Toda
etapa grava na tabela `audit` (exibida por item).

### Homologação em produção com liberação de uso único (21/10/2026)

Sem staging disponível, a única gravação em produção possível é a de
`HOMOLOGATION_TARGETS` em `app/services/store_publish_grant.py`:
**Choice, `https://choicetech.com.br`, SKU `119002000072`, produto `16321`**. Ampliar
essa lista é decisão de revisão de código. `PublishSettings` continua igual; sem
liberação, as três lojas seguem bloqueadas.

- Emitida apenas pela CLI local `scripts/homologation_grant.py` (nunca pela web), com
  confirmação literal `AUTORIZO <finalidade> <sku>`. Exige item aprovado, sem bloqueios,
  e o `dry_run_sha256` exato armazenado; uma liberação ativa por alvo/finalidade.
- Finalidades: `publish` (envio aprovado) e `rollback` (recuperação). Validade de 1 a
  120 minutos (padrão 30). Revogável (`revoke`) enquanto não usada.
- Consumo atômico (`issued → consumed`) **antes do primeiro upload**: falha, retry ou
  segunda execução exigem nova liberação. Dois workers não consomem a mesma.
- O executor revalida loja/origem/SKU/produto/hash/finalidade, exige o produto
  existente (nunca cria) e grava pelo usuário da senha de aplicativo WordPress.
- Antes de qualquer upload verifica, só por leitura: `users/me` com `upload_files`,
  `edit_products`, `edit_published_products`, `edit_others_products`; `OPTIONS` com
  `PUT` em `products/16321` e `POST` em `media`. Faltando algo, nada é enviado.
- Falha parcial: uploads confirmados ficam no journal e são reaproveitados; resposta
  perdida é resolvida pela identidade `prm-<sha16>` no título/URL da mídia. Sem duplicatas.
- Execução do item autorizado: `scripts/store_registration_worker.py --once --batch <lote> --sku 119002000072`
  reivindica somente esse item; outros lotes pendentes não são tocados.
- Verificação pós-PUT estrita para todos os campos comerciais e metadados, exceto os
  reescritos pelo WordPress/plugins a cada salvamento (`_yoast_indexnow_last_ping`,
  `_edit_lock`, `_edit_last`, `_oembed_*`). Sem compare-and-swap no servidor: alteração
  externa entre a última leitura e o PUT é detectada depois, como erro com recuperação.
- Recuperação: `scripts/store_registration_rollback.py` com liberação `rollback` restaura
  só `images` e `_wcda_arquivos` anteriores, apenas se o produto estiver exatamente no
  estado pós-publicação registrado; nunca exclui mídia. Tudo vai para a tabela `audit`.

Para reutilizar um datasheet do próprio PRM, baixe o PDF já gerado (individual ou
lote) e coloque-o como `SKU/SKU_Datasheet.pdf`. Não existe outro gerador nem uma
segunda chamada à IA. Nesta entrega a seleção ocorre pelo ZIP; não há seletor
automático dos rascunhos privados de outros módulos/usuários.

## Regras do script original

- Pasta com nome exato do SKU, comparação sem diferenciar caixa; múltiplas pastas
  são erro, nunca seleção arbitrária.
- `_variante`/`_variant` como principal; sem ela, menor número de imagem
  `_fotoN`, `_foto_N`, `_N`, ` N` ou `-N`. Restantes ordenadas numericamente.
- Em `Fotos/`, fotos terminadas em `front` viram galeria; a última não-front,
  em ordem de nome, é principal, conforme o legado. Se houver várias não-front,
  a prévia avisa. Mais de uma variante é bloqueada para decisão.
- Datasheet, Manual, Desenho 3D e Certificado: uma ocorrência usa o nome da
  categoria; várias usam descrição sem prefixo SKU, com labels únicos.
- Arquivos de download são inventariados mesmo quando o formato não é homologado.
- SVG/GIF identificados pelo legado não são enviados: permanecem bloqueados na
  validação de imagem. Não contornar segurança do WordPress.
- Manifesto validado do PRM, quando usado pelo serviço de planejamento, tem
  precedência sobre heurísticas. O ZIP de entrada desta tela não aceita manifesto
  externo como autorização.

## Gravação segura e limitações

`StagingPublisher` é separado dos clientes de leitura existentes. Não foi adicionado
PUT/POST aos métodos de diagnóstico. Antes de abrir uma chamada de escrita:

- `PRM_PUBLISH_ENABLED` deve ser true, por padrão false;
- origem HTTPS deve coincidir exatamente com `PRM_PUBLISH_STAGING_ORIGIN`;
- SKU deve coincidir com `PRM_PUBLISH_STAGING_SKU`;
- **choicetech.com.br, sagloja.devsplcomunic.com.br e portwell.com.br são bloqueados
  mesmo com a flag habilitada**. O endereço atual SAG é tratado como loja em uso,
  apesar do nome de desenvolvimento.

Upload multipart no WordPress; PUT WooCommerce restrito a `images` e ao metadado
`_wcda_arquivos` existente. Principal existente é preservada (troca só com
`replace_main` aprovado); novas imagens são anexadas à galeria. Sem principal, a
primeira imagem classificada vira principal. Nome, descrições, preço, estoque,
categorias, atributos, status e outros metadados não entram no payload e são
conferidos por hash na releitura.

Releitura confirma sequência de IDs e preservação de `_wcda_arquivos`. Snapshot de
SKU, ID, imagens e campo de documentos é conferido antes e imediatamente antes do
PUT. Isso detecta alterações concorrentes comuns, **não é compare-and-swap atômico
no servidor**: staging deve ficar sem editores concorrentes. Produção requer
contrato servidor/controle concorrente homologado.

Deduplicação:

- SHA-256 dos bytes e journal persistente por organização/origem/SKU;
- arquivos idênticos do mesmo produto reutilizam o ID de upload já confirmado;
- mesmo nome já associado na loja bloqueia a prévia para reconciliação;
- não se presume igualdade de conteúdo de arquivos antigos com nomes diferentes;
  deduplicação completa de todo o acervo anterior requer inventário confiável de
  hashes/IDs. Não se baixam URLs arbitrárias para tentar inferi-la;
- registra `sending` **antes** de POST/PUT. Resposta perdida impede retry cego;
  uploads incertos exigem revisão manual. Atualização cuja resposta se perdeu pode
  ser confirmada pela releitura da sequência desejada;
- não há exclusão automática de mídia órfã. Ela deve ser reconciliada manualmente.

## Worker e persistência

```powershell
.\.venv\Scripts\python.exe scripts/store_registration_worker.py
# Uma tarefa, para diagnóstico controlado
.\.venv\Scripts\python.exe scripts/store_registration_worker.py --once
```

SQLite e arquivos privados ficam em `data/store_publish`, ignorados no Git.
Fila reivindicada transacionalmente, um item global por vez, resultados e journal
persistem após reinício. Cada tarefa roda em subprocesso com watchdog de 900s.
Após lease de 3600s, trabalho abandonado vira `uncertain` quando o worker consultar
a fila; não é repetido automaticamente. A UI não executa tarefas longas.

Configuração em `.env.example`:

```dotenv
PRM_PUBLISH_ENABLED=false
PRM_PUBLISH_STAGING_ORIGIN=
PRM_PUBLISH_STAGING_SKU=
PRM_PUBLISH_STORAGE_DIR=data/store_publish
PRM_PUBLISH_MAX_FILE_MIB=20
```

Não ligar o worker de homologação com credenciais/destino errados. Para staging,
usar instância isolada do PRM com suas credenciais de staging, não apontar a
instalação operacional para um clone sem planejamento.

Limites locais: planilha 5 MiB/1000 linhas; ZIP 100 MiB compactado/500 MiB
descompactado/3000 entradas; arquivo 20 MiB; 20 imagens/produto, 40 milhões de
pixels/imagem. Paths relativos, sem traversal, links ou criptografia. Erros no
upload são sanitizados; não há retry HTTP automático.

**Esses limites são do PRM, não limites comprovados das lojas.** Aceitação efetiva
de JPEG/PNG/WebP/PDF/ZIP, limites PHP/servidor, regras para arquivos 3D e políticas
de plugins ainda precisam de teste autorizado em staging. Nenhum formato foi
enviado às lojas reais.

Limitações operacionais: servidor único/disco local; histórico mostra últimos
100 lotes; não há rotina de limpeza automática nesta fila. Upload de ZIP rejeitado
remove a própria pasta de extração (desde 21/10/2026); pastas antigas desse tipo
devem ser revisadas no procedimento de retenção, sem apagar pastas ativas. Não expor esse intake diretamente à internet
sem limites no proxy e análise de malware.

## Roteiro de homologação

1. Obter plugin/snippet e contrato de `_wcda_arquivos`.
2. Fornecer URL de clone staging e SKU descartável de teste com backup.
3. Configurar credenciais e organização corretas em instância PRM isolada.
4. Primeiro fazer prévia com flag false. Conferir arquivos, principal e existentes.
5. Habilitar origem/SKU de staging e confirmar apenas lote de imagens. Conferir
   resultado e repetir o lote para validar deduplicação.
6. Testar arquivos maiores, MIME bloqueado, 401/403/429, resposta perdida,
   interrupção e alteração concorrente sem duplicar ou excluir mídia.
7. Finalizar adapter de documentos conforme plugin; confirmar preservação,
   labels, URL/ID e tamanho esperado, além da exibição na página pública.
8. Homologar lotes mistos e relatório. Só depois autorizar política de produção,
   ampliar SKUs e decidir desativação do Playwright.

## Arquivos

Novos serviços `store_publish.py`, `store_registration_jobs.py`; router
`store_registration.py`; worker `scripts/store_registration_worker.py`; auditoria
`scripts/audit_store_contract.py`; template `store_registration.html`, CSS/JS
`store-registration.*`; `tests/test_store_publish.py`.

Ampliados: `store_registration_plan.py`, main/rotas de páginas, base/shell,
Digitalização (link), `.env.example`, `.gitignore`, testes de template e documentação.
Nenhum código Playwright removido. Nenhuma migração ou escrita no banco oficial.
