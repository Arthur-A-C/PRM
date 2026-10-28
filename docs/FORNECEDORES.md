# Fornecedores — MVP em 26/10/2026

## Follow-up automático — 28/10/2026

Regras em `app/services/supplier_followups.py` (constantes e `Source`), prazos em `app/config.py`
(`PRM_SUPPLIER_FOLLOWUP_INACTIVE_DAYS=3`, `PRM_SUPPLIER_WAITING_REPLY_DAYS=5`, `PRM_SUPPLIER_DOCUMENT_WARNING_DAYS=[30,7,0]`,
`PRM_SUPPLIER_REGISTRATION_GRACE_DAYS=2`). Avaliadas a cada ciclo do **worker de alertas existente**
(`scripts/meeting_worker.py --stage alerts`) e, para o fornecedor afetado, logo após cada ação na tela.

| Regra (`source_type`) | Quando | Item no Planner | Resolve quando |
|---|---|---|---|
| `supplier_inactive` | ativo, fora de Congelado/Descartado, ≥ 3 dias sem interação registrada | alerta “X está há N dias sem interação” | nova interação |
| `supplier_hot_no_next` | score Quente sem próxima ação futura (próxima ação, tarefa do fornecedor ou item ligado no Planner) | alerta de prioridade alta; sugere “Agendar reunião” (não cria) | próxima ação definida |
| `supplier_waiting_reply` | etapa Aguardando retorno e ≥ 5 dias sem interação | follow-up “Cobrar retorno — X” | retorno registrado (interação) ou saída da etapa |
| `supplier_missing_registration` | etapa em `REGISTRATION_REQUIRED_STAGES` há ≥ 2 dias sem documento “Ficha cadastral” | alerta | ficha anexada ou etapa alterada |
| `supplier_document_expiring` | documento com validade em ≤ 30, ≤ 7 dias ou vencido | alerta por limite (uma vez cada) | documento atualizado/substituído |
| `supplier_next_action` | próxima ação definida no fornecedor (data e horário opcionais) | item único espelhado | próxima ação concluída/removida; concluir no Planner limpa a do fornecedor |

- **Modelo:** `Activity` publicada (Follow-up), ancorada no registro “Planner · itens avulsos”, com
  `details.automation`, `source_type`, `supplier_id`. Sem migração. Alerta em Meus alertas pelo `sync_alerts`
  (um alerta por item automático).
- **Idempotência:** um item aberto por fornecedor + regra (+ documento/limite/validade); avaliação trava as linhas do
  fornecedor; `proposal_local_id` = chave do episódio (índice único do banco); episódio encerrado por alguém não é recriado
  até a condição recomeçar.
- **Responsável:** tudo pertence ao responsável atual; ao trocar, itens abertos e alertas acompanham. Reuniões não mudam.
- **Arquivados:** fora da avaliação; itens abertos são cancelados (histórico mantido). **Exclusão:** itens abertos
  cancelados com “Fornecedor excluído”; nada referencia o fornecedor por chave estrangeira.
- **Tela:** drawer com “Próximos passos” (próxima ação, próximo follow-up, próxima reunião; Concluir/Reagendar/Abrir no
  Planner); Kanban com “Próxima: … · Hoje” ou “Reunião: … · 31/10 10:30”; Meus alertas com categoria e ações; Dashboard
  com sem interação, quentes sem próxima ação, follow-ups vencidos e de hoje (abrem o Planner filtrado).

## Arquivar, restaurar e excluir definitivamente — 27/10/2026

- **Arquivar (recomendado):** menu `⋯` do drawer → **Arquivar fornecedor**, com motivo opcional. `POST /api/v1/fornecedores/{id}/archive` grava `archived_at`/`archived_by`; etapa, responsável, score, contatos, interações, tarefas, documentos, histórico e execuções de IA ficam intactos. O card sai do Kanban padrão e não pode ser arrastado; o drawer mostra “Arquivado”. Mesmas permissões de edição (responsável ou gestor/desenvolvedor). Arquivar de novo retorna 409.
- **Filtro Situação:** `Ativos` (padrão), `Arquivados`, `Todos` (`?archive_status=active|archived|all`). Kanban e contadores refletem a lista carregada pelo filtro. A detecção de duplicidade do “Novo fornecedor com IA” continua considerando arquivados.
- **Restaurar:** fornecedor arquivado → **Restaurar fornecedor** (`POST .../restore`). Volta para a mesma etapa em que estava (não existe etapa “arquivado”).
- **Excluir definitivamente:** item destrutivo separado, visível só para **gestor/desenvolvedor** (`DELETE /api/v1/fornecedores/{id}`; demais papéis recebem 403). Exige digitar exatamente o nome do fornecedor (422 caso contrário). Remove o fornecedor e seus contatos, interações/histórico, tarefas e registros de documentos numa única transação, sem erro de FK. Fornecedor de outra organização ou já excluído: 404. Fornecedores arquivados podem ser excluídos.
- **Concorrência:** arquivar, restaurar e excluir enviam o `updated_at` exibido (`expected_updated_at`). Toda alteração do fornecedor ou de contatos, interações, tarefas, documentos e aplicação de IA atualiza esse carimbo; se outra pessoa alterou algo depois da abertura, a API retorna 409 (“Reabra o cadastro e confirme novamente”) e nada é arquivado/excluído. CSRF obrigatório (403 sem token).
- **Documentos/quarentena:** antes de apagar as linhas, a pasta física do fornecedor é movida para `<PRM_SUPPLIER_STORAGE_DIR>/_deleted/<org>/<fornecedor>/<carimbo>`. Nada é apagado; o caminho fica fora da árvore servida pelo endpoint de download (que passa a responder 404). Se qualquer passo falhar antes do commit, a transação é desfeita e a pasta volta ao lugar original. Limpeza da quarentena é manual e fora do PRM.
- **IA:** `supplier_ai_runs` não são apagados; ficam com `supplier_id` vazio, status `supplier_deleted` e data de exclusão no JSON, sempre com a organização original. Não entram no cache, não podem ser aplicados nem reutilizados em “Novo fornecedor com IA” (409).
- **Auditoria:** arquivamento (`supplier_archived`, com usuário, data e motivo) e restauração (`supplier_restored`) ficam no histórico do fornecedor. A exclusão grava `supplier_deletion_audits`, que sobrevive ao fornecedor: id e nome anteriores, organização, usuário, data, etapa, se estava arquivado, motivo, quantidades removidas (contatos, tarefas, documentos, histórico), execuções de IA desvinculadas, arquivos físicos, caminho relativo da quarentena e id/categoria/SHA-256 dos documentos (sem nomes ou conteúdo).
- Migração `20261027_0018_supplier_archive_delete` (após `0017`): colunas `suppliers.archived_at` (indexada) e `archived_by` (FK `users`, `SET NULL`) e tabela `supplier_deletion_audits`. Ainda não aplicada em produção.

## Experiência CRM contextual — 27/10/2026

- O Kanban permanece visível e o detalhe abre em drawer direito de 55% da tela, responsivo até largura total no celular. O fornecedor aberto fica em `?fornecedor=<id>` e é reaberto após refresh.
- Cabeçalho compacto com etapa, responsável, score e ações de interação, tarefa, documento e IA. Próxima ação ganhou destaque e sinalização discreta de atraso.
- Visão geral exibe valores em modo de leitura. Cada campo abre editor inline com Salvar/Cancelar; score, etapa e responsável usam os endpoints rápidos existentes, com restauração visual em falha. O formulário grande de edição foi removido.
- Contatos, interações e tarefas usam composers compactos dentro da aba atual. Timeline agrupa eventos por data e tipo; tarefas mantêm conclusão e edição rápidas.
- Documentos continuam organizados nas categorias existentes, com download, edição, leitura por IA em Ficha cadastral e upload por botão ou arraste para a área documental.
- Cadastro manual pede apenas nome, site, registro opcional, responsável, etapa e score; depois de criar abre o mesmo drawer. O fluxo “Novo fornecedor com IA” também termina nesse drawer, sem alteração do prompt ou backend.
- Acessibilidade: dialog identificado, estado de carregamento, Esc/backdrop/X, restauração de foco, contenção de Tab e labels nos controles. Feedback usa mensagem viva/toast; não foi adicionado `alert()`.
- Nenhum endpoint, model, migration, permissão ou regra de Supplier foi alterado. Exclusão de contatos continua indisponível porque a API atual não define contrato de exclusão/auditoria.
- Validação focada: 29 testes JavaScript e 68 testes Python de fornecedores/IA/design aprovados, sem rede externa ou IA real. Sem commit, push ou deploy nesta etapa.

## Evolução CRM / Kanban — 26/10/2026

- Drag-and-drop nativo no desktop, contadores por coluna, atualização otimista com reversão em erro. Novo PATCH parcial preserva ficha e registra os eventos existentes; expected_stage retorna 409 quando outra pessoa moveu o card. Mesmo scope, CSRF e validação de responsável do módulo original. Seletor de etapa mantido para teclado/mobile.
- Cards compactos; drawer lateral com fundo do Kanban visível, fechamento por botão/backdrop/Escape; score/etapa/responsável inline. Formulário inicial com apenas nome, CNPJ, responsável, etapa, score e contato principal. Ficha agrupada em empresa/endereço/comercial/condições.
- Contatos em cards; categorias documentais com aspecto de pastas e contagens; timeline com rótulos legíveis; tarefas com conclusão rápida; próxima ação destacada e reagendamento. Filtros rápidos meus/vencidos/sem próxima ação, sem reload completo.
- Modelos/migration/permissões/upload existentes preservados. Não há nova migration. Arraste de documentos não incluído: usar o upload autenticado já existente. Sem automações ou integração Planner/alertas.
- Arquivos desta etapa: routers/suppliers.py (PATCH), static/js/suppliers.js, static/css/suppliers.css, templates/suppliers.html, tests/test_suppliers.py, tests/js/suppliers.test.cjs e suppliers-ui.test.cjs; overlay compose.fornecedores-crm.yaml.
- Testes: 45 Python (fornecedores + pauta semanal), 5 JavaScript (incluindo DOM/API simulados), build Docker e diff check passaram. Testes não usaram lojas nem fornecedores reais. Não houve inspeção visual em navegador real; Playwright Node indisponível. Não executada suíte completa novamente nesta etapa de UX (última completa do MVP: 857/28).
- Imagem testada prm:fornecedores-crm-test, manifest 651b330fff06247775f9d1ad425f98671eb2e6e2b68bb90c422b6c714a6f4cb1. Overlay adicionado após todos os anteriores; somente API. Rollback: retirar apenas compose.fornecedores-crm.yaml e recriar API na imagem anterior prm:fornecedores-test. Sem push/merge.

Checkout: `C:\Users\PW\Documents\PRM-remocao-cargos`, branch `fix/remocao-autorizacao-cargos`. Trabalho anterior preservado. Sem commit/push/merge.

## Acesso

Todos os usuários ativos dos cargos existentes podem criar. Vendedor é responsável por padrão e só acessa seus próprios fornecedores; outro responsável retorna 404 inclusive para documentos/contatos/tarefas. Gestores e desenvolvedores gerenciam todos da própria organização e escolhem responsável ativo dela. A regra central `services/suppliers.scope` protege leitura e mutações. CSRF obrigatório em todas as escritas. A atribuição a outra organização ou usuário inativo é recusada.

## Uso

`/fornecedores`: Kanban horizontal com dez etapas configuradas em `services/suppliers.py`, score manual, responsável, última interação, próxima ação e prazo. Botão **+ Novo fornecedor** abre formulário; ao salvar abre detalhe e registra supplier_created. Movimentação por seletor de etapa no formulário de edição (drag-and-drop fica para evolução).

Detalhe: Visão Geral, Histórico, Contatos, Tarefas, Documentos, Ficha cadastral, Contratos, Observações. Contatos podem ser editados e um marcado como principal. Tarefas internas têm responsável, prazo, prioridade e conclusão. A primeira pendente aparece no card quando não existe próxima ação explicitamente preenchida.

Busca por nome/CNPJ, responsável, etapa, score, categoria/segmento, cidade e UF. CNPJ é string, sem remoção de zeros/formatação.

## Persistência

Migration Alembic aditiva `20261026_0015`, após `20261023_0014`: suppliers, supplier_contacts, supplier_interactions, supplier_tasks, supplier_documents. Modelos Supplier/Contact/Interaction/Task/Document. Identidades, organização, responsável, etapa e score são colunas relacionais indexadas; ficha e dados complementares validados por schemas Pydantic ficam em JSON. Timeline inclui eventos de sistema e interações; não altera Activity ou tabelas de reuniões.

API `/api/v1/fornecedores`: GET/POST; `/config`; `/{id}` GET/PUT; `/{id}/contacts` POST e `/{id}/contacts/{id}` PUT; interactions POST; tasks POST/PUT; documents POST/PUT e download GET autenticado. Não há exclusão de fornecedor/documento nesta primeira versão.

## Documentos

Categorias: Ficha cadastral, Contratos, Certidões, Tabela de preços, Catálogos, Propostas, Documentos fiscais, Dados bancários, Outros. Contratos permitem início, vencimento, versão e status. Upload de até 20 MiB, PDF/PNG/JPG/XLSX/DOCX/CSV/TXT, assinatura inicial conferida, hash SHA-256 incremental, nome original apenas para exibição. Arquivo físico por UUID, fora de static, separado por organização/fornecedor. Download como anexo com nosniff/no-store. Arquivos inválidos removidos do staging local da requisição. Não há antivírus/OCR nem visualização inline.

Armazenamento `PRM_SUPPLIER_STORAGE_DIR`; no Docker `/app/data/products/suppliers`, subpasta do volume persistente já existente. Nenhuma pasta de produto anterior alterada. Backups precisam incluir este volume junto ao PostgreSQL.

## Evolução

SupplierTask possui identificador e referência estável ao Supplier para futura integração explícita com Activity/Planner. Sem score automático, notificações, e-mail/WhatsApp ou criação de cards de reunião. Preenchimento cadastral com IA (somente prévia + aplicação revisada): `docs/FORNECEDORES_IA.md`. Próximas etapas: paginação para bases grandes, drag-and-drop, antivírus, controle de versões concorrentes da ficha e integração com alertas mediante escopo separado.

## Arquivos

Novos: models/suppliers.py, services/suppliers.py, routers/suppliers.py, templates/suppliers.html, static/js/suppliers.js, static/css/suppliers.css, migration 0015, tests/test_suppliers.py e tests/js/suppliers.test.cjs. Integrações pontuais: models/__init__, main.py, config.py, services/access.py, routers/pages.py e templates/shell.html.

## Validação e implantação concluídas

- Suíte completa em container sem rede: **857 passaram, 28 ignorados**, 1 aviso de depreciação. Dois testes JavaScript passaram. Migration também exercitada em banco SQLite temporário (upgrade/downgrade preserva users); única cabeça Alembic confirmada.
- Teste de histórico Alembic em test_weekly_agenda.py ajustado para exigir uma única cabeça e presença do merge 0014, sem fixar esse merge como última migration para sempre. Nenhuma funcionalidade de reuniões modificada.
- Backup PostgreSQL privado: `C:\Users\PW\Documents\PRM-deploy-backups\suppliers-20261026\prm_docker.dump` (121811 bytes, pg_restore --list validado). Não versionado.
- Aplicada migration `20261026_0015` no banco Docker `prm_docker`; cinco tabelas verificadas vazias, sem dados fictícios.
- API atualizada para `prm:fornecedores-test`, imagem testada `sha256:8eedd15382aa9d2f17301d7dab1a19dec2cac69895a6e1174901c0e5aa30d22c`. Novo container `029a31f0b7a3`; todos os outros containers mantiveram seus IDs. Estado reiniciando do alerts no projeto separado prm-kaue é preexistente, não alterado nesta entrega.
- `GET /api/v1/health/ready` 200; fornecedores sem login 401; página redireciona a login; JavaScript 200. Não houve teste visual interativo no navegador autenticado. Testes autenticados e mutações foram feitos apenas com fixtures.
- Ativo em `http://localhost:8001/fornecedores`. Login normal do PRM, sem credencial adicional. Ctrl+F5 se necessário.
- Overlay `compose.fornecedores.yaml` deve permanecer após todos os overlays anteriores registrados nos labels do container. Apenas API mudou. Não reconstruir a partir do checkout original sem integrar os arquivos novos.
- Rollback operacional: usar os mesmos overlays anteriores sem compose.fornecedores.yaml e recriar somente API com imagem anterior `prm:remocao-sem-copia-20261026`. Manter as tabelas novas e documentos; não executar downgrade destrutivo nem restaurar backup sobre dados novos automaticamente.
