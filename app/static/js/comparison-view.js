// Comparação lado a lado: filtro visual das características (Todas, Diferenças, Iguais, Sem dado).
// Só mostra/oculta linhas já renderizadas pelo servidor; não altera dados nem faz requisições.
(() => {
  'use strict';
  const root = document.querySelector('[data-cmp]');
  if (!root) return;
  const buttons = [...root.querySelectorAll('[data-cmp-filter]')];
  const rows = [...root.querySelectorAll('tr[data-cmp-row]')];
  const status = root.querySelector('[data-cmp-status]');
  const empty = root.querySelector('[data-cmp-empty]');
  const names = { diff: 'com diferença', equal: 'iguais', missing: 'sem dado' };

  function apply(filter) {
    let shown = 0;
    rows.forEach(row => {
      const tags = row.dataset.cmpRow.split(' ');
      const visible = filter === 'all' || tags.includes(filter);
      row.hidden = !visible;
      if (visible && row.dataset.cmpRow !== 'meta') shown += 1;
    });
    root.querySelectorAll('tbody').forEach(body => {
      const own = [...body.querySelectorAll('tr[data-cmp-row]')];
      body.hidden = own.length > 0 && own.every(row => row.hidden);
    });
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.cmpFilter === filter)));
    const total = rows.filter(row => row.dataset.cmpRow !== 'meta').length;
    if (status) status.textContent = filter === 'all' ? '' : `${shown} de ${total} características ${names[filter]}`;
    if (empty) empty.hidden = filter === 'all' || shown > 0;
  }

  buttons.forEach(b => b.addEventListener('click', () => apply(b.dataset.cmpFilter)));
})();
