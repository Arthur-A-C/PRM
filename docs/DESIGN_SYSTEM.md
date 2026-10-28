# Design system do PRM — 26/10/2026

Fonte única: `app/static/css/prm-system.css`, carregada **por último** em `base.html`. Ela redefine os tokens
`--cc-*` (que todas as camadas antigas já usam) e normaliza os componentes compartilhados. Não reescreve módulos.
Para uma tela nova, use as classes abaixo e evite CSS próprio com cores fixas.

## Tokens (refinados em 27/10/2026)
| Uso | Token (alias curto) | Claro | Escuro |
|---|---|---|---|
| Fundo geral | `--cc-bg` (`--surface-page`) | #f4f5f7 | #0c1117 |
| Superfície | `--cc-surface` / `-2` / `-3` (`--surface-1/2/3`) | #fff / #f8f9fb / #eef0f3 | #131a23 / #18202b / #1f2834 |
| Borda | `--cc-line` / `--cc-line-strong` (`--border-1/2`) | #e5e8ec / #d2d7de | #252f3c / #344152 |
| Texto | `--cc-ink` / `-2` / `-3` (`--text-1/2/3`) | #121a25 / #3c4655 / #636d7c | #e7ecf2 / #b7c1cd / #8e9aa9 |
| Destaque | `--cc-primary` (`--accent`, `-hover`, `-soft`, `--accent-ring`) | #2a56c6 | #6d97f2 |
| Sucesso / aviso / erro | `--cc-ok` / `--cc-warn` / `--cc-alert` (`--success/--warning/--danger`, + `-soft`) | #1b7a48 / #8f5600 / #bb2f2a | #5fcb8b / #eab35a / #f48a86 |

A cor de destaque é reservada para ação primária, item selecionado, foco e estado importante; filtros, ações
secundárias e listas usam neutros. Os aliases (`--space-1..7` = 4/8/12/16/24/32/48px, `--radius-sm/md/lg/pill`,
`--surface-*`, `--text-*`, `--accent*`) apontam para os mesmos valores dos tokens `--cc-*`.

Tipografia (sans do sistema, Segoe UI) em tokens compostos: `--type-page` 22px/650, `--type-section` 16px/650,
`--type-card` 14,5px/650, `--type-body` 14px, `--type-secondary` 13px, `--type-label` 13px/600,
`--type-helper` 12px, `--type-caption` 11px/600 em caixa alta. Corpo de produto em 14px (densidade SaaS).
Controles com 36px de altura (`--ui-control-h`), 30px na versão compacta. Raio 12/8/6px; sem sombra em superfícies
estáticas, `--cc-shadow-lift` só para drawers, diálogos, popovers, toasts e barras flutuantes.

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

## Padrões de produto (27/10/2026)
- **Painel lateral de formulário (28/10/2026):** criar/editar/confirmar abre em `<dialog class="prm-sheet">` à direita,
  no padrão do drawer de fornecedores (cantos 18px à esquerda, sombra lateral, overlay). Estrutura:
  `.prm-sheet-head` (rótulo, título, subtítulo, ×) · `.prm-sheet-body` (seções `.prm-sheet-section`, erro `.prm-sheet-error`)
  · `.prm-sheet-foot` fixo (Cancelar + ação principal; perigo com `.prm-btn-danger` e variante `.is-danger`). Tamanhos
  `.is-narrow` / padrão / `.is-wide`. `ui.js` (`PRM.sheet`) dá clique fora, foco no primeiro campo, `[data-sheet-close]`
  e `PRM.sheet.ask` / `PRM.sheet.confirm` no lugar de `prompt()` / `confirm()`. ESC e foco preso vêm do `<dialog>` nativo.
- **Quando usar cada diálogo (28/10/2026):** formulário com vários campos → painel lateral (`.prm-sheet`); ação simples →
  confirmação compacta (`PRM.sheet.confirm`, `.is-compact`: cartão no canto superior direito, folha inferior no
  celular); ação destrutiva ou envio real à loja → `danger: true` (botão vermelho) ou painel `.is-danger` com frase
  digitada. A confirmação diz o que será feito (`title`/`text`), quantos itens (`details: [[rótulo, valor]]`,
  renderizado em `.prm-sheet-facts`) e as consequências (`warnings`, `.prm-sheet-warnings`). Formulário curto:
  `PRM.sheet.form({fields:[{name,label,type,required,min,max}], size:"panel"})` com erro ao lado do campo
  (`.prm-field-error`, `aria-invalid`). Proteções do `PRM.sheet` em todo `.prm-sheet`: não fecha (ESC, clique fora, ×,
  Cancelar) enquanto houver `[aria-busy="true"]`; com campo alterado pede “Descartar alterações?”
  (`data-sheet-guard="off"` desliga); devolve o foco a quem abriu (ou ao resumo do menu que se fechou). `alert()`,
  `confirm()` e `prompt()` nativos só existem como reserva quando `PRM.sheet` não está carregado (testes de JS).
- **Planner (28/10/2026):** tipo de item tem cor e forma próprias (`.pl-type-dot`: tarefa = destaque azul, reunião =
  violeta/círculo, card = âmbar, follow-up = verde/losango), sempre junto do nome do tipo. Agenda em lista agrupada
  (Atrasados, Hoje, Amanhã, Próximos 7 dias, Mais adiante, Sem data) ou calendário; detalhe em painel lateral
  (`.pl-drawer`); criação em diálogo único com tipo escolhido no topo.
- **Hierarquia de botões:** um `.button-primary` por área; botões de filtro (`Filtrar`, `Aplicar`, `Pesquisar`) são
  sempre secundários; `.prm-btn-ghost` para ações de contexto; destrutivas separadas (`.prm-btn-danger`/menu `⋯`).
- **Barra de filtros:** busca larga + até 4 selects visíveis + `Mais filtros` (`<details>` com popover) + `Filtrar`.
  Mudar um select já aplica o filtro (Fornecedores). Atalhos rápidos como chips (`aria-pressed`).
- **Ações em lote:** uma barra única (`.mt-bulkbar`) com grupos separados por divisor e exportações em `Exportar ▸`.
- **Estado vazio:** `.prm-empty` com título curto, uma frase de orientação e ações (`.prm-empty-actions`);
  com filtros ativos, oferecer `Limpar filtros` em vez de “criar”.
- **Carregamento:** `.prm-skeleton` (shimmer) para blocos, `.prm-loading` (spinner pequeno + texto) para trechos.
- **Selos:** mesma cor = mesmo significado (ok = em dia/concluído/publicado, warn = atenção/priorizar/hoje,
  alert = vencido/erro, info = aprovado/próximo, neutral = rascunho/sem dado). Em Cards/Alertas: `.mt-chip.is-*`.
- **Kanban:** colunas em trilho neutro com contador, cartão = empresa + score, próxima ação (2 linhas), rodapé com
  responsável (inicial) e prazo (`dd/mm`, vermelho quando vencido). Arrastar continua igual.
- **Fluxos em etapas:** `<ol class="prm-steps">` com `aria-current="step"` e `.is-done` (✓).
- **Guia de andamento (28/10/2026):** macro `_flow_guide.html` + `flow-guide.js`. Cada etapa declara um seletor CSS
  que fica verdadeiro quando ela termina (`data-flow-done`); a atual é a primeira não concluída. Mostra “Etapa X de N”,
  a **Próxima ação** (`data-flow-next`), link “Ir para a etapa” e alertas (`data-flow-alert`, `.is-warn`/`.is-alert`).
  Só lê a página: não faz requisições nem muda as ferramentas. Usado em Resolução de imagens, Cadastro via API,
  Remoção de arquivos, Geração em lote, Publicação em lote e no assistente de importação de catálogos.
- **Comparação lado a lado:** cabeçalho por produto (origem, empresa, título, SKU · família, preço principal em
  destaque, disponibilidade, placar “iguais / diferentes / sem dado” frente à referência), características agrupadas
  e filtro Todas/Diferenças/Iguais/Sem dado (`comparison-view.js`). Selos `.comparison-verdict--*`: igual/equivalente
  = ok, diferente/parcial = âmbar (atenção, nunca “pior”), sem dado = tracejado neutro, conflito = alerta.
  Não há “melhor/pior”: o backend não informa o sentido de cada atributo.
- **Detalhes técnicos:** textos longos de cabeçalho vão para `<details class="prm-help">` (“Como funciona”,
  “O que nunca é alterado”); identificadores de execução ficam em “Detalhes da base”.

## Navegação
Menu agrupado em `shell.html` (Operação, Relacionamento, Gestão, Dados, Administração), apenas com os itens que o
backend já libera para o cargo (`nav_items`); subpáginas de Digitalização e a Pauta Semanal aparecem só para
gestor/desenvolvedor. Página nova sem grupo cai em "Outros" e nunca some do menu. Cabeçalho: breadcrumb, título,
subtítulo por página (`page_subtitles`), relógio compacto, tema e usuário.

Testes: `tests/test_design_system.py` (menu por cargo, cabeçalho, abas, IDs únicos, tokens) e
`tests/js/store-registration.test.cjs` (selos de status).
