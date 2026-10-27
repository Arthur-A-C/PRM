# Design system do PRM — 26/10/2026

Fonte única: `app/static/css/prm-system.css`, carregada **por último** em `base.html`. Ela redefine os tokens
`--cc-*` (que todas as camadas antigas já usam) e normaliza os componentes compartilhados. Não reescreve módulos.
Para uma tela nova, use as classes abaixo e evite CSS próprio com cores fixas.

## Tokens
| Uso | Token | Claro | Escuro |
|---|---|---|---|
| Fundo geral | `--cc-bg` | #f3f5f8 | #0b1118 |
| Superfície | `--cc-surface` / `-2` / `-3` | #fff / #f7f9fb / #edf1f5 | #121a24 / #17212c / #1d2935 |
| Borda | `--cc-line` / `--cc-line-strong` | #e2e7ed / #cdd5de | #243241 / #334558 |
| Texto | `--cc-ink` / `-2` / `-3` | #0f1c2b / #3a4859 / #5b6a7b | #e8eef4 / #b6c3d0 / #93a3b4 |
| Ação | `--cc-primary` (+ `-hover`, `-soft`) | #0a5ccf | #5b9cf0 |
| Sucesso / aviso / erro | `--cc-ok` / `--cc-warn` / `--cc-alert` (+ `-soft`) | #157a44 / #8a5300 / #b4232f | #62d08f / #f0b54f / #ff8a93 |

Tipografia (sans do sistema, Segoe UI): título da página 24px (`--ds-text-title`), seção 17px (`--ui-text-lg`),
corpo 15px (`--ui-text-base`), tabelas/notas 14px (`--ui-text-md`), labels 13px (`--ui-text-sm`), selos 12px
(`--ui-text-xs`). Rótulos pequenos em caixa alta com tracking leve, sem fonte monoespaçada (ela fica para código).
Espaçamento em múltiplos de 4px (`--ui-space-*`); raio 12/8/6px; sombra única leve (`--cc-shadow`) e uma de
elevação para drawers, toasts e barras flutuantes (`--cc-shadow-lift`).

## Componentes
- **Botões:** `.button-primary` (ação principal, um por área), `.button-secondary`/`.prm-btn` (alternativas),
  `.prm-btn-danger` (remover/excluir), `.prm-btn-ghost` (ações pequenas), `.prm-btn-sm`. Sem sombra nem deslocamento.
- **Campos:** `.prm-form` (grade automática), `.prm-field`, `fieldset`/`legend`, `.prm-form-group-title`,
  ajuda em `<small>`, erro em `.prm-field-error` + `aria-invalid="true"`.
- **Selos de estado:** `.prm-badge` com `.is-ok/.is-warn/.is-alert/.is-info/.is-busy`; sempre com texto
  (a cor só reforça). `.prm-pill` continua válido.
- **Estado vazio:** `.prm-empty` (texto + ação opcional). **Indicadores:** `.prm-kpis` + `.prm-kpi`.
- **Etapas:** `<ol class="prm-steps">`. **Abas de módulo:** `.prm-tabs` (ex.: `_digitalization_tabs.html`).
- **Barra de ações:** `.prm-toolbar` + `.prm-toolbar-spacer`. **Ajuda recolhível:** `<details class="prm-help">`.
- **Tabelas:** `.table-scroll > table`; tabelas largas recebem `min-width` e rolam na horizontal.
- **Drawer:** `.prm-drawer` (dialog lateral). Modais continuam em `<dialog>`.
- **Feedback (JS, `ui.js`):** `PRM.toast(mensagem, "success"|"info"|"warning"|"error")` e
  `PRM.busy(botão, "Salvando…")` (devolve a função que restaura). Envio nativo de formulário marca o botão como
  "Enviando…/Carregando…" automaticamente (exceto `method="dialog"`, `target` e `data-prm-no-busy`).

## Navegação
Menu agrupado em `shell.html` (Operação, Relacionamento, Gestão, Dados, Administração), apenas com os itens que o
backend já libera para o cargo (`nav_items`); subpáginas de Digitalização e a Pauta Semanal aparecem só para
gestor/desenvolvedor. Página nova sem grupo cai em "Outros" e nunca some do menu. Cabeçalho: breadcrumb, título,
subtítulo por página (`page_subtitles`), relógio compacto, tema e usuário.

Testes: `tests/test_design_system.py` (menu por cargo, cabeçalho, abas, IDs únicos, tokens) e
`tests/js/store-registration.test.cjs` (selos de status).
