# Remoção de arquivos de produtos

Acesso: **Digitalização → Remoção de arquivos** (`/digitalizacao/remocao-arquivos`), gestores e
desenvolvedores da organização configurada. Worker: `scripts/store_removal_worker.py`.

Desvincula imagens e/ou documentos de produtos **existentes**, localizados pelo SKU exato.
Nenhum arquivo é excluído da biblioteca de mídia (nunca há DELETE). Nome, descrições,
categorias, atributos, preço, estoque, SKU, status e demais metadados nunca são enviados e são
conferidos por hash depois de cada gravação.

## Modos

| Modo | Desvincula | Preserva | Gravação |
|---|---|---|---|
| Remover tudo | principal, galeria e `_wcda_arquivos` | dados comerciais | WooCommerce `PUT images: []` + `meta_data` WCDA `[]` |
| Remover fotos da galeria | galeria | principal e documentos | WooCommerce `PUT images: [{id: principal}]` |
| Remover documentos | `_wcda_arquivos` | imagens | WooCommerce `PUT meta_data` WCDA `[]` |
| Remover foto principal | principal | galeria e documentos | WordPress `POST wp/v2/product/{id} featured_media: 0` |

**Por que a foto principal usa a API do WordPress:** a API WooCommerce
(`set_product_images`) sempre transforma `images[0]` em imagem principal. Enviar só a galeria
promoveria a primeira foto. `featured_media: 0` remove apenas a referência à principal e não
toca na galeria. Na leitura, a principal vem de `featured_media`: quando é 0, o `wc/v3` lista a
galeria a partir da posição 0, e o PRM não a confunde com principal. O Dry Run avisa que a
loja exibirá a imagem padrão no lugar da principal.

## Fluxo

1. Empresa, modo e SKUs (colados e/ou CSV/XLSX com coluna SKU; zeros preservados, repetidos
   unificados).
2. **Gerar Dry Run** (somente GET): SKU, ID, principal, galeria, documentos WCDA, o que será
   desvinculado e preservado, estado atual × proposto, gravações previstas, bloqueios e avisos.
   Estados: pronto, nada a remover, SKU inexistente (nada criado), bloqueado, erro.
3. **Aprovar** (selecionados ou todos): registra o hash exato do Dry Run.
4. **Executar aprovados**: enfileira. O worker confere a política/liberação, consome a liberação
   de uso único, relê o produto (alteração concorrente → nada é gravado), verifica permissões
   (capacidades e `Allow`), grava e relê: estado esperado e campos protegidos.
5. Em produção: veja **Fluxo em produção** abaixo (permissões, quatro olhos, backup e releitura).
6. Progresso, concluídos/ignorados/erros por SKU, **Pausar**/**Cancelar fila** entre produtos,
   **Refazer Dry Run de erros** (itens concluídos nunca se repetem), **Relatório CSV** e JSON.

## Ambientes: homologação e produção

Cada loja (Choice, SAG, Portwell) tem o seu ambiente, visível no painel **Lojas e ambiente**:

| Ambiente | Como libera uma gravação |
|---|---|
| **Homologação** (padrão) | Igual a antes: política de staging `PRM_PUBLISH_*` ou liberação de uso único emitida pela CLI, restrita a `HOMOLOGATION_TARGETS` (hoje só Choice/119002000072/16321). Nada foi ampliado. |
| **Produção** | Ligada por loja na interface por um administrador. **Não autoriza nada sozinha**: cada lote continua exigindo Dry Run, aprovação, confirmação digitada e liberações de uso único emitidas para quem executa. |

Produção só pode existir com **todas** estas condições:

1. `PRM_REMOVAL_PRODUCTION_ALLOWED=true` no ambiente do processo (trava mestra). A API e o worker a
   conferem separadamente: se faltar em qualquer um deles, nenhuma liberação é emitida e nada é gravado.
2. Acesso ao PRM por **HTTPS** para ativar produção, alterar permissões ou quatro olhos, aprovar,
   executar e restaurar em produção. Desativar a produção é permitido também por HTTP (freio de emergência).
3. Teste da loja aprovado na hora da ativação (somente leitura): credenciais, chave WooCommerce,
   capacidades do usuário WordPress (`edit_products`, `edit_published_products`, `edit_others_products`,
   `upload_files`) e upload de mídia permitido (necessário para restaurar a partir do backup).
4. Confirmação digitada `ATIVAR PRODUCAO <LOJA>` por um usuário **desenvolvedor** com permissão de
   administração naquela loja.

## Permissões

Por usuário e por loja, em PostgreSQL (`store_operation_permissions`, migração `20261022_0012`):
**aprovar**, **executar**, **restaurar** e **administrar** (ambiente e permissões;
só para o papel desenvolvedor). Vendedores nunca recebem permissões de remoção. Lotes ficam visíveis
para quem os criou e para quem tem alguma permissão na loja, o que permite a outra pessoa executar.

As permissões são aplicadas na API e de novo no worker, imediatamente antes de gravar: liberação
emitida para alguém que perdeu a permissão, foi desativado ou mudou de organização é recusada.

**Desenvolvedor / Modo Deus** (papel persistido `desenvolvedor`, usuário ativo): tem permissões
operacionais de aprovar, executar e restaurar em sua organização, mesmo sem uma linha de permissões
por loja. Pode conduzir a própria operação; a dispensa de quatro olhos é automática e auditada.
A permissão **administrar** continua explícita por loja; esta mudança não libera ambientes por si só.

**Gestor**: continua dependendo das permissões por loja e de outro usuário autorizado para aprovar
sua execução ou restauração. A aprovação usada é a do Dry Run original. Não existe mais um botão
para desligar quatro olhos globalmente: o endpoint rejeita `ativar: false` com HTTP 422 e registros
antigos de `four_eyes=0` não dispensam gestores. Vendedores e demais perfis não podem operar.

API e worker consultam identidade, organização, perfil ativo e permissão do aprovador. Mudança de
perfil, revogação ou desativação antes da gravação bloqueia a operação. A exceção gera os eventos
`four_eyes_exempted` ao enfileirar (ação, perfil, loja, SKU/hash do Dry Run) e
`four_eyes_exemption_verified` nas verificações do worker. Nenhuma destas regras elimina Dry Run,
aprovação explícita, CSRF, HTTPS, confirmação digitada, backup, verificação ou auditoria.

## Fluxo em produção

1. Criar o lote (empresa, modo e até 500 SKUs) e aguardar o **Dry Run** (somente leitura).
2. **Aprovar** (permissão aprovar): registra o hash exato do Dry Run e quem aprovou.
3. **Executar aprovados** (gestor: outra pessoa aprova; desenvolvedor: pode aprovar sua operação): confirmação `EXECUTAR <N> <LOJA>`. A API
   emite, numa única transação, uma liberação de uso único por item (loja, SKU, produto, modo, hash do
   Dry Run, executor, aprovador), válida por **30 minutos**. Não exige comando no terminal por SKU
   em produção habilitada. As regras restritas de homologação por CLI continuam inalteradas.
4. O worker, um produto por vez, com pausa entre produtos:
   - confere trava mestra, ambiente, permissão atual do executor e quatro olhos;
   - relê o produto (mudou desde o Dry Run → nada é gravado);
   - confere as permissões do usuário WordPress;
   - faz o **backup verificado**: sem backup válido o item fica **Bloqueado** e nada é gravado;
   - consome a liberação e grava somente `images`, `_wcda_arquivos` ou `featured_media`;
   - relê WooCommerce e WordPress até 4 vezes (0, 1, 2 e 4 s). Só marca **Removido e verificado** se a
     loja mostrar exatamente o estado pedido e os campos comerciais intactos. Caso contrário o item
     fica **Incerto: reconferir**, nunca concluído.
5. **Reconferir na loja** (somente leitura) resolve itens incertos: confirma a remoção se ela apareceu,
   devolve o item para aprovação se a loja não mudou ou indica revisão manual se o estado divergir.
6. **Pausar** devolve à aprovação os itens ainda na fila e revoga as liberações não usadas; **Cancelar**
   também revoga. Itens concluídos nunca são repetidos.

## Backup e restauração

Antes de cada remoção o worker baixa cada imagem e documento que será desvinculado (sem enviar
credenciais, somente HTTPS e somente do domínio da loja ou de `PRM_REMOVAL_BACKUP_MEDIA_HOSTS`), valida
o conteúdo (imagem decodificável, assinatura PDF/ZIP, tamanho anunciado), grava com os metadados
(ID da mídia, URL, MIME, título, texto alternativo, entrada WCDA) e o SHA-256 de cada arquivo, e relê
tudo do disco antes de continuar. O backup fica no volume da fila
(`data/store_publish/removal_backups/<org>/<loja>/<SKU>/<hash do Dry Run>/`) e pode ser baixado pelo link
**Baixar backup** de cada item.

**Restaurar** (permissão restaurar, confirmação `RESTAURAR <N> <LOJA>`) só age se o produto estiver
exatamente no estado deixado pela remoção. Os IDs de mídia originais são revinculados; se uma imagem ou
documento tiver sido apagado da biblioteca depois da remoção, a cópia do backup (conferida por SHA-256)
é reenviada e vinculada no lugar. A releitura confirma o resultado.

Mídia nunca é excluída pelo PRM. Backups não expiram sozinhos; o limite total é
`PRM_REMOVAL_BACKUP_MAX_TOTAL_GIB` e, ao atingi-lo, novas remoções são bloqueadas até liberar espaço.

Homologação continua igual pela CLI:

```powershell
.\.venv\Scripts\python.exe scripts/homologation_grant.py issue-removal --batch <lote> --sku 119002000072 --minutes 30 --confirm "AUTORIZO remover 119002000072"
.\.venv\Scripts\python.exe scripts/homologation_grant.py issue-removal --batch <lote> --sku 119002000072 --restore --confirm "AUTORIZO restaurar 119002000072"
.\.venv\Scripts\python.exe scripts/store_removal_restore.py --batch <lote> --sku 119002000072
```

## Auditoria

Cada lote tem o botão **Auditoria**: criação, aprovação, liberação emitida e consumida, permissões
conferidas, backup verificado, envio, confirmação, restauração, reenvio de arquivos e toda
**tentativa bloqueada** (quem, o quê e o motivo). Mudanças de ambiente e permissões ficam em
`ambiente:<loja>` e `permissoes:<loja>`. A auditoria e as respostas nunca contêm credenciais.

## Implantação segura

Sem reconstruir imagens além do necessário e sem reiniciar todos os containers:

1. Confirmar que não há remoção em andamento: nenhum item `running`/`restoring` na página (ou aguardar).
2. Backup do PostgreSQL e do volume `store-publish` (`docker/backup.py` ou procedimento de `docs/DOCKER.md`).
3. Atualizar o código (merge do PR revisado) e aplicar a migração: `docker compose run --rm migrate`.
4. Recriar **somente** `api` e `worker-removal`. Nesta primeira implantação **não** definir
   `PRM_REMOVAL_PRODUCTION_ALLOWED`: produção continua desligada e a homologação segue igual.
5. Conceder o primeiro administrador (uma vez):
   `docker compose run --rm api python scripts/removal_permissions.py grant-admin --email <dev> --companies choice,sag,portwell`.
   Os demais usuários recebem permissões pela interface.
6. HTTPS: publicar o PRM com TLS no gateway e permitir que o uvicorn confie no proxy
   (`FORWARDED_ALLOW_IPS` / `--forwarded-allow-ips` com o endereço do gateway). A página mostra
   "Conexão HTTPS" quando estiver correto.
7. Quando a empresa decidir operar: definir `PRM_REMOVAL_PRODUCTION_ALLOWED=true` em `api` **e**
   `worker-removal` (arquivo de ambiente do servidor, sem credenciais no repositório) e recriar só esses
   dois serviços. Ativar cada loja pela interface, após o teste da loja.

Para voltar atrás: **Desativar produção** na interface (imediato) ou remover a variável e recriar os
dois serviços. Liberações não usadas deixam de valer em ambos os casos.

## Checklist de validação por loja

Para Choice, Portwell e SAG, nesta ordem, com um SKU de teste combinado com o responsável da loja:

- [ ] **Testar conexão** aprovado (credenciais, chave WooCommerce, capacidades e upload de mídia).
- [ ] Dry Run do SKU confere com o painel da loja: principal, galeria e documentos WCDA (Portwell:
      315003005779 → produto 18035, principal 18039).
- [ ] Produção ativada pelo administrador; quatro olhos ativo.
- [ ] Aprovar com um usuário e confirmar que o mesmo usuário **não** consegue executar.
- [ ] Executar com outro usuário, modo **Remover foto principal**; item "Removido e verificado";
      backup baixado e aberto (manifesto e imagem).
- [ ] Conferir no painel WordPress/WooCommerce: principal desvinculada, galeria e dados comerciais intactos,
      mídia ainda na biblioteca.
- [ ] **Restaurar** e conferir no painel que a principal voltou.
- [ ] Repetir com **Remover documentos** em produto com `_wcda_arquivos` e restaurar.
- [ ] Auditoria do lote mostra aprovação, execução, backup, confirmação, restauração e a tentativa bloqueada.
- [ ] Desativar produção (se a operação não continuar no mesmo dia).

## Limitações conhecidas

- A fila, as liberações, o journal, a auditoria e os ambientes ficam no SQLite do volume `store-publish`
  (como antes); permissões ficam no PostgreSQL. Um único worker de remoção por volume (trava de arquivo).
- Lojas com cache agressivo podem levar o item a "Incerto"; "Reconferir" resolve sem regravar.
- Mídia hospedada em CDN de outro domínio exige `PRM_REMOVAL_BACKUP_MEDIA_HOSTS`; sem isso o backup
  bloqueia a remoção.
- Em execução nativa no Windows, caminhos muito longos da pasta de dados podem exceder 260 caracteres;
  no container Linux não há esse limite.
- Restaurar exige que o produto não tenha sido alterado depois da remoção; caso contrário, revisão manual.

A automação Playwright antiga (`arquivos-prm/automação cadastro/Remover_fotos/remover.py`)
permanece como referência/fallback autorizado e não é executada pelo PRM.
