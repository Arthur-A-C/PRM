# Digitalização e Publicação em Lote

Data: 21/10/2026. Acesso: **Digitalização → Publicação em lote** (`/digitalizacao/publicacao-lote`),
somente gestores/desenvolvedores da organização configurada.

Fluxo único: importar um ZIP com pastas por SKU, gerar os datasheets, revisar o Dry Run e
publicar **somente imagens e documentos** em produtos WooCommerce já existentes.
**Não gera nome comercial, descrições, categorias, atributos nem CSV** — esses dados continuam
no fluxo atual. Os módulos de descrição/CSV, Digitalização individual, Geração em Lote e
Cadastro via API continuam disponíveis e inalterados no uso.

## Arquitetura

Orquestrador fino (`app/services/batch_publication.py`) sobre dois pipelines existentes:

```text
ZIP (pastas = SKU)
  └─ BatchStore.create (Geração em Lote, modo pasta, zeros preservados)
       └─ datasheet_batch_worker → produce(): IA só após "Processar"; datasheet PT + analysis.json
            └─ Pipelines.package(): pacote validado em memória (manifesto + SHA-256)
                 Fotos/<SKU>_variante.jpg, <SKU>_fotoN.jpg (process_image 1200 px),
                 <SKU>_Datasheet.pdf (gerado), 3D/manuais/certificados (_document_name),
                 datasheet_dados.json — SEM o datasheet do fornecedor
                 └─ Jobs.create (Cadastro via API, em memória; sem download/reenvio)
                      └─ store_registration_worker → Dry Run → aprovação → liberação/política
                           → upload WP + PUT images/_wcda_arquivos → releitura e auditoria
```

Reaproveitados sem duplicação: intake e fila da Geração em Lote, regras legadas de nomes
(`prepare_files`), `process_image`, nomes de documentos da Digitalização, validação de
manifesto/hash, identificação por SKU, Dry Run de arquivos, aprovação, liberação de uso único,
journal, auditoria e rollback. Novas tabelas `pipelines`/`pipeline_items` no SQLite do
Cadastro via API ligam lote de geração, SKU e lote de publicação.

O datasheet original do fornecedor é enviado à IA como fonte e permanece no armazenamento do
lote (`data/datasheet_batches/<lote>/`); nunca entra no pacote, no manifesto nem na loja.

## Etapas na interface

1. **Importação** — empresa (Choice, SAG, Portwell) e ZIP; prévia por SKU, sem IA.
2. **Processamento** — "Processar" (todos ou selecionados), "Pausar" (itens na fila voltam a
   aguardar; o item em execução termina), "Reprocessar erros". Itens concluídos nunca são
   reenviados à IA.
3. **Revisão** — "Gerar Dry Run": cria internamente o lote de publicação; o worker consulta a
   loja só com leitura. SKU inexistente vira **Aguardando cadastro por CSV**.
4. **Aprovação** — individual (selecionados) ou em lote; opção explícita por SKU para trocar a
   imagem principal existente.
5. **Publicação** — "Publicar aprovados" só enfileira; a gravação depende da política de staging
   ou de liberação de homologação. Lojas atuais seguem bloqueadas.
6. **Verificação** — releitura de imagens, WCDA e campos protegidos; log por produto.

"Retomar pendentes" refaz o Dry Run de itens com erro ou aguardando cadastro, sem reimportar nem
regerar; uploads já confirmados são reaproveitados pela identidade `prm-<sha>` (mesmo conteúdo
em outro produto também não é reenviado). "Exportar ZIP" gera o mesmo pacote para backup/uso
externo. Um erro em um produto não interrompe os demais.

Tabela: SKU, empresa, pasta, quantidade de imagens e documentos (sem o datasheet do
fornecedor), status de processamento, datasheet (link para o PDF) e WooCommerce, erros e
pendências; filtros por etapa, situação e SKU; histórico filtrável por empresa.

## Workers

```powershell
.\.venv\Scripts\python.exe scripts/datasheet_batch_worker.py        # geração (IA)
.\.venv\Scripts\python.exe scripts/store_registration_worker.py     # Dry Run e publicação
```

Ambos persistem a fila; podem ser parados e reiniciados. Para uma publicação controlada,
usar `store_registration_worker.py --once --batch <lote de publicação> --sku <SKU>`.

## Autorização para vários SKUs

`scripts/homologation_grant.py issue-scope --batch <lote> --sku A --sku B --max-items N
--minutes M --confirm "AUTORIZO publish <n> itens"` cria uma liberação de uso único **por SKU**
sob um escopo comum: tudo ou nada, limite declarado (máximo 50), validade de até 120 minutos,
cada liberação consumida e auditada individualmente. Todo SKU continua tendo de pertencer a
`HOMOLOGATION_TARGETS`, hoje **apenas Choice/119002000072/16321**; o escopo nunca amplia esse
alvo. Ampliar a lista é decisão de revisão de código, não de configuração.

## Limites

- Sem compare-and-swap no WooCommerce: alteração externa entre a última leitura e o PUT é
  detectada na releitura (erro e recuperação).
- Formatos sem upload homologado (.step, .dwg, .dxf, .rar, .7z soltos) ficam no pacote e no
  Dry Run como ignorados.
- Imagens são reprocessadas (JPEG 1200 px, qualidade 90), como na Digitalização individual.
