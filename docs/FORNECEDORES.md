# Fornecedores — MVP em 26/10/2026

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
