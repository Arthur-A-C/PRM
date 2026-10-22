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
5. Progresso, concluídos/ignorados/erros por SKU, **Pausar**/**Cancelar fila** entre produtos,
   **Refazer Dry Run de erros** (itens concluídos nunca se repetem), **Relatório CSV** e JSON.

## Produção e liberações

A política `PRM_PUBLISH_*` não mudou: nas três lojas atuais, executar exige liberação de uso único
por loja, SKU, produto, **modo** e hash do Dry Run, emitida pela CLI e restrita a
`HOMOLOGATION_TARGETS` (hoje só Choice/119002000072/16321):

```powershell
.\.venv\Scripts\python.exe scripts/homologation_grant.py issue-removal --batch <lote> --sku 119002000072 --minutes 30 --confirm "AUTORIZO remover 119002000072"
.\.venv\Scripts\python.exe scripts/store_removal_worker.py --once --batch <lote> --sku 119002000072
```

## Recuperação

O journal guarda o estado anterior (principal, galeria e WCDA) antes de gravar. Restaurar exige que
o produto esteja exatamente no estado pós-remoção e, em produção, liberação própria:

```powershell
.\.venv\Scripts\python.exe scripts/homologation_grant.py issue-removal --batch <lote> --sku 119002000072 --restore --confirm "AUTORIZO restaurar 119002000072"
.\.venv\Scripts\python.exe scripts/store_removal_restore.py --batch <lote> --sku 119002000072
```

Resposta perdida é decidida pela releitura; recusa explícita confirmada como "nada mudou" pode
ser repetida após nova aprovação; envio sem confirmação nunca é repetido às cegas.

A automação Playwright antiga (`arquivos-prm/automação cadastro/Remover_fotos/remover.py`)
permanece como referência/fallback autorizado e não é executada pelo PRM.
