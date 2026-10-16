/* PRM Command Center — dashboard only.
   Reads embedded JSON and the read-only /api/v1/operations/overview endpoint.
   Never writes, never invents values: untracked stages are shown as untracked. */
(() => {
  'use strict';
  const root = document.querySelector('[data-operations]');
  if (!root) return;

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const number = new Intl.NumberFormat('pt-BR');
  const decimal = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const ZONE = 'America/Sao_Paulo';
  const dayKeyFormat = new Intl.DateTimeFormat('en-CA', { timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit' });
  const shortDay = new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC', day: '2-digit', month: 'short' });
  const longDay = new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC', weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' });
  const stamp = new Intl.DateTimeFormat('pt-BR', { timeZone: ZONE, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  const clockTime = new Intl.DateTimeFormat('pt-BR', { timeZone: ZONE, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const relative = new Intl.RelativeTimeFormat('pt-BR', { numeric: 'auto' });
  const COMPANY_NAMES = { all: 'Grupo', portwell: 'Portwell', choice: 'Choice', sag: 'SAG', eco: 'ECO Automação', dimensional: 'Dimensional' };
  const OPS_COMPANIES = ['portwell', 'choice', 'sag'];
  const $ = (selector, scope = root) => scope.querySelector(selector);
  const $$ = (selector, scope = root) => [...scope.querySelectorAll(selector)];
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  };
  const svgEl = (tag, attrs = {}) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    return node;
  };
  const readJson = id => { try { return JSON.parse(document.getElementById(id).textContent); } catch (_) { return null; } };
  const put = (selector, value) => { const node = $(selector); if (node) node.textContent = value; };
  const icon = name => {
    const template = { check: 'm5 12 4 4L19 6', file: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5', package: 'm12 3 8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9', alert: 'M12 3 2.5 20h19zM12 10v4.5m0 3h.01', clock: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17M12 7.5V12l3 2', copy: 'M9 9h11v11H9zM5 15H4V4h11v1', arrow: 'M4 12h16m-6-6 6 6-6 6' }[name] || 'M12 4v16';
    const svg = svgEl('svg', { viewBox: '0 0 24 24', class: 'workspace-icon', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' });
    svg.append(svgEl('path', { d: template }));
    return svg;
  };

  /* ---------- Toasts ---------- */
  const toasts = $('[data-cc-toasts]');
  const toast = (message, kind = 'info') => {
    if (!toasts) return;
    const item = el('div', 'cc-toast is-' + kind, message);
    toasts.append(item);
    window.setTimeout(() => { item.classList.add('is-leaving'); window.setTimeout(() => item.remove(), 260); }, 3600);
  };

  /* ---------- Tooltip ---------- */
  const tooltip = $('#cc-tooltip');
  const tipParts = tooltip && { value: $('[data-tip-value]', tooltip), title: $('[data-tip-title]', tooltip), note: $('[data-tip-note]', tooltip) };
  let tipTarget = null;
  const placeTip = (x, y) => {
    const box = tooltip.getBoundingClientRect();
    const left = Math.min(Math.max(8, x - box.width / 2), window.innerWidth - box.width - 8);
    const top = y - box.height - 14 < 8 ? y + 18 : y - box.height - 14;
    tooltip.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
  };
  const showTip = (target, x, y, content) => {
    if (!tooltip) return;
    tipTarget = target;
    const data = content || { value: target.dataset.tipValue, title: target.dataset.tipTitle, note: target.dataset.tipNote };
    tipParts.value.textContent = data.value || '';
    tipParts.title.textContent = data.title || '';
    tipParts.note.textContent = data.note || '';
    tooltip.hidden = false;
    if (x === undefined) { const rect = target.getBoundingClientRect(); x = rect.left + rect.width / 2; y = rect.top; }
    placeTip(x, y);
  };
  const hideTip = () => { if (tooltip) { tooltip.hidden = true; tipTarget = null; } };
  root.addEventListener('pointermove', event => {
    const target = event.target.closest?.('[data-tip-title]');
    if (target && root.contains(target)) showTip(target, event.clientX, event.clientY);
    else if (tipTarget && tipTarget.dataset.tipTitle && tipTarget !== document.activeElement) hideTip();
  });
  root.addEventListener('focusin', event => { if (event.target.matches?.('[data-tip-title]')) showTip(event.target); });
  root.addEventListener('focusout', event => { if (event.target === tipTarget) hideTip(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') hideTip(); });
  window.addEventListener('scroll', hideTip, { passive: true });

  /* ---------- Tabs ---------- */
  const tabs = $$('[data-ops-view]');
  const showView = (view, focus = false) => {
    if (!tabs.some(t => t.dataset.opsView === view)) view = 'overview';
    tabs.forEach(tab => {
      const active = tab.dataset.opsView === view;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focus) tab.focus();
    });
    $$('[data-ops-pane]').forEach(pane => { pane.hidden = pane.dataset.opsPane !== view; });
    hideTip();
    if (view === 'overview') requestAnimationFrame(renderEvolution);
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => showView(tab.dataset.opsView));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (i + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (i + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); showView(tabs[next].dataset.opsView, true); }
    });
  });

  /* ---------- Competitive map ---------- */
  const competitors = $$('[data-ops-competitor]');
  const showCompetitor = source => {
    competitors.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.opsCompetitor === source)));
    $$('[data-ops-competitor-panel]').forEach(panel => { panel.hidden = panel.dataset.opsCompetitorPanel !== source; });
    $$('[data-cc-coverage-row]').forEach(row => row.classList.toggle('is-active', row.dataset.ccCoverageRow === source));
  };
  competitors.forEach(button => button.addEventListener('click', () => showCompetitor(button.dataset.opsCompetitor)));
  if (competitors.length) showCompetitor(competitors[0].dataset.opsCompetitor);

  /* ---------- Family butterfly ---------- */
  const familyPanel = $('[data-cc-families]');
  const familyData = readJson('ops-families');
  const proximityLabels = { core: 'Foco próximo', adjacent: 'Adjacente', distant: 'Distante', undecided: 'Pendente' };
  const rivalNames = { eco: 'ECO', dimensional: 'Dimensional' };
  let familyRival = familyPanel?.querySelector('[data-cc-family-rival][aria-pressed="true"]')?.dataset.ccFamilyRival || 'eco';
  let showAllFamilies = false;
  function renderFamilies(rival = familyRival) {
    if (!familyPanel || !familyData) return;
    familyRival = rival;
    $$('[data-cc-family-rival]', familyPanel).forEach(b => b.setAttribute('aria-pressed', String(b.dataset.ccFamilyRival === rival)));
    put('[data-cc-family-rival-label]', rivalNames[rival] || rival);
    const proximity = $('[data-cc-family-proximity]', familyPanel).value;
    const sort = $('[data-cc-family-sort]', familyPanel).value;
    const totals = familyData.totals || {};
    let rows = Object.entries(familyData.families || {}).filter(([id]) => id !== 'unknown').map(([id, family]) => {
      const c = family.counts || {};
      const group = Number(c.portwell || 0) + Number(c.choice || 0);
      const other = Number(c[rival] || 0);
      return { id, label: family.label || id, proximity: family.proximity || 'undecided', group, other,
        groupShare: totals.group ? 100 * group / totals.group : 0, otherShare: totals[rival] ? 100 * other / totals[rival] : 0 };
    }).filter(r => (r.group || r.other) && (!proximity || r.proximity === proximity));
    const key = { group: r => r.groupShare, rival: r => r.otherShare, gap: r => Math.abs(r.groupShare - r.otherShare) }[sort] || (r => Math.max(r.groupShare, r.otherShare));
    rows.sort((a, b) => key(b) - key(a) || a.label.localeCompare(b.label, 'pt-BR'));
    const totalRows = rows.length;
    if (!showAllFamilies) rows = rows.slice(0, 10);
    const scale = Math.max(1, ...rows.map(r => Math.max(r.groupShare, r.otherShare)));
    const chart = $('[data-cc-family-chart]', familyPanel);
    chart.replaceChildren();
    if (!rows.length) chart.append(el('p', 'cc-caption', 'Nenhuma família corresponde ao filtro selecionado.'));
    rows.forEach((row, index) => {
      const item = el('div', 'cc-bf-row');
      item.setAttribute('role', 'listitem');
      item.style.setProperty('--i', index);
      item.setAttribute('aria-label', `${row.label}: grupo ${decimal.format(row.groupShare)}% (${number.format(row.group)} registros), ${rivalNames[rival]} ${decimal.format(row.otherShare)}% (${number.format(row.other)} registros)`);
      const side = (cls, share, count, title) => {
        const wrap = el('div', 'cc-bf-side ' + cls);
        const bar = el('span', 'cc-bf-bar');
        bar.style.setProperty('--w', (100 * share / scale) + '%');
        bar.tabIndex = 0;
        bar.dataset.tipTitle = `${title} · ${row.label}`;
        bar.dataset.tipValue = decimal.format(share) + '%';
        bar.dataset.tipNote = `${number.format(count)} registros`;
        wrap.append(bar, el('span', 'cc-bf-value', share ? decimal.format(share) + '%' : '—'));
        return wrap;
      };
      const label = el('div', 'cc-bf-label');
      label.append(el('span', '', row.label), el('small', 'prox-' + row.proximity, proximityLabels[row.proximity] || 'Pendente'));
      item.append(side('is-group', row.groupShare, row.group, 'Grupo'), label, side('is-rival', row.otherShare, row.other, rivalNames[rival]));
      chart.append(item);
    });
    const more = $('[data-cc-family-more]', familyPanel);
    if (more) {
      more.hidden = totalRows <= 10;
      more.setAttribute('aria-expanded', String(showAllFamilies));
      more.textContent = showAllFamilies ? 'Mostrar as 10 principais' : `Mostrar todas as famílias (${totalRows})`;
    }
    put('[data-cc-family-status]', `${rows.length} de ${totalRows} famílias · escala até ${decimal.format(scale)}%`);
  }
  if (familyPanel) {
    $$('[data-cc-family-rival]', familyPanel).forEach(b => b.addEventListener('click', () => renderFamilies(b.dataset.ccFamilyRival)));
    $('[data-cc-family-proximity]', familyPanel)?.addEventListener('change', () => renderFamilies());
    $('[data-cc-family-sort]', familyPanel)?.addEventListener('change', () => renderFamilies());
    $('[data-cc-family-more]', familyPanel)?.addEventListener('click', () => { showAllFamilies = !showAllFamilies; renderFamilies(); });
    renderFamilies();
  }

  /* ---------- Catalog context (snapshot KPIs) ---------- */
  const catalog = readJson('ops-data');
  const company = $('[data-ops-company]');
  const setMeter = (key, part, whole) => {
    const meter = $(`[data-ops-meter="${key}"] i`);
    const share = whole ? 100 * part / whole : 0;
    if (meter) meter.style.setProperty('--w', share + '%');
    put(`[data-ops-meter-label="${key}"]`, whole ? decimal.format(share) + '%' : '—');
  };
  const applyCatalogContext = source => {
    if (!catalog || !catalog.sources) return;
    const rows = source === 'all' ? catalog.sources : catalog.sources.filter(s => s.code === source);
    const sum = field => rows.reduce((t, r) => t + Number(r[field] || 0), 0);
    const total = field => rows.length ? number.format(sum(field)) : '—';
    put('[data-ops-total]', total('accepted'));
    put('[data-ops-attributes]', total('with_attributes'));
    put('[data-ops-pending]', total('unknown_family'));
    $$('[data-count]').forEach(node => { delete node.dataset.countFinal; });
    setMeter('public', sum('public'), sum('accepted'));
    setMeter('attributes', sum('with_attributes'), sum('accepted'));
    setMeter('pending', sum('unknown_family'), sum('accepted'));
    put('[data-ops-scope]', source === 'all' ? 'Quatro fontes · fotografia atual' : COMPANY_NAMES[source] + (rows.length ? ' · dados importados' : ' · sem catálogo nesta base'));
    put('[data-ops-context-message]', source === 'sag'
      ? 'SAG participa do workspace de digitalização; nenhum catálogo SAG integra esta fotografia.'
      : source === 'all' ? 'Selecione uma empresa para filtrar indicadores, operações e busca.'
      : `Contexto: ${COMPANY_NAMES[source]}. Indicadores e operações seguem a seleção; os painéis comparativos usam Portwell e Choice como referência.`);
    $$('[data-ops-company-card]').forEach(card => card.setAttribute('aria-pressed', String(card.dataset.opsCompanyCard === source)));
    const scope = $('[data-ops-search-source]');
    if (scope) scope.value = source === 'all' || source === 'sag' ? '' : source;
    const link = $('[data-ops-pending-link]');
    if (link) link.href = source === 'sag' ? '/digitalizacao' : '/catalogos?family=unknown' + (source === 'all' ? '' : '&source=' + encodeURIComponent(source));
    if (source === 'eco' || source === 'dimensional') { showCompetitor(source); renderFamilies(source); }
  };

  /* ---------- Operations data model ---------- */
  let operations = readJson('ops-runs') || { status: 'unavailable', items: [] };
  const state = { company: 'all', period: '30', status: 'all', search: '', sort: 'updated', direction: -1, limit: 10, series: new Set(['created', 'approved', 'validated']) };
  const dayKey = iso => dayKeyFormat.format(new Date(iso));
  const keyToDate = key => new Date(key + 'T00:00:00Z');
  const addDays = (key, delta) => { const d = keyToDate(key); d.setUTCDate(d.getUTCDate() + delta); return d.toISOString().slice(0, 10); };
  const todayKey = () => dayKeyFormat.format(new Date());
  const ago = iso => {
    const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
    const units = [['year', 31536000], ['month', 2592000], ['day', 86400], ['hour', 3600], ['minute', 60]];
    for (const [unit, size] of units) if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
    return 'agora';
  };
  const updatedAt = item => [item.validated_at, item.approved_at, item.created_at].filter(Boolean).sort().at(-1);
  const needsAttention = item => item.status === 'approved' || item.status === 'draft';
  const hasPending = item => item.pending > 0 && !item.pending_acknowledged && item.status === 'draft';
  const periodStart = () => state.period === 'all' ? null : addDays(todayKey(), -(Number(state.period) - 1));
  const inPeriod = iso => { const start = periodStart(); return !start || (iso && dayKey(iso) >= start); };
  const companyItems = () => (operations.items || []).filter(item => state.company === 'all' || item.company === state.company);
  const statusMatch = item => state.status === 'all' || (state.status === 'attention' ? hasPending(item) : item.status === state.status);
  const periodItems = () => companyItems().filter(item => inPeriod(item.created_at));
  const events = items => items.flatMap(item => [
    { type: 'created', at: item.created_at, item },
    item.approved_at ? { type: 'approved', at: item.approved_at, item } : null,
    item.validated_at ? { type: 'validated', at: item.validated_at, item } : null,
  ].filter(Boolean));
  const buckets = () => {
    const end = todayKey();
    let start = periodStart();
    if (!start) {
      const first = companyItems().map(i => dayKey(i.created_at)).sort()[0];
      start = first && first < end ? first : addDays(end, -29);
    }
    const days = Math.round((keyToDate(end) - keyToDate(start)) / 86400000) + 1;
    const weekly = days > 120;
    const list = [];
    if (weekly) {
      const startDate = keyToDate(start);
      const monday = addDays(start, -((startDate.getUTCDay() + 6) % 7));
      for (let key = monday; key <= end; key = addDays(key, 7)) list.push({ key, end: addDays(key, 6), created: 0, approved: 0, validated: 0 });
    } else {
      for (let key = start; key <= end; key = addDays(key, 1)) list.push({ key, end: key, created: 0, approved: 0, validated: 0 });
    }
    return { list, weekly };
  };
  const bucketise = items => {
    const { list, weekly } = buckets();
    events(items).forEach(event => {
      const key = dayKey(event.at);
      const bucket = list.find(b => key >= b.key && key <= b.end);
      if (bucket) bucket[event.type] += 1;
    });
    return { list, weekly };
  };

  /* ---------- Empty / restricted messaging ---------- */
  const opsMessage = () => {
    if (operations.status === 'restricted') return { title: 'Indicadores operacionais restritos', text: 'As execuções de digitalização são visíveis apenas para gestores.' };
    if (operations.status === 'storage_misconfigured') return { title: 'Armazenamento indisponível', text: 'A pasta de produtos configurada não é válida. Verifique PRM_PRODUCT_STORAGE_ROOT.' };
    if (operations.status === 'unavailable') return { title: 'Dados operacionais indisponíveis', text: 'Não foi possível carregar os registros de digitalização nesta página.' };
    if (state.company === 'eco' || state.company === 'dimensional') return { title: 'Sem operações para concorrentes', text: 'A digitalização atende Portwell, Choice e SAG. Os demais painéis seguem o catálogo selecionado.' };
    if (!(operations.items || []).length) return { title: 'Nenhuma digitalização registrada ainda', text: 'Assim que um datasheet for gerado no workspace, ele aparecerá aqui com etapas, datas e pendências.' };
    return null;
  };
  const opsUnknown = () => ['restricted', 'unavailable', 'storage_misconfigured'].includes(operations.status) || state.company === 'eco' || state.company === 'dimensional';
  const emptyBlock = (message, withAction = true) => {
    const box = el('div', 'cc-empty-state');
    box.append(el('strong', '', message.title), el('p', '', message.text));
    if (withAction && operations.status !== 'restricted') {
      const action = el('a', 'cc-link', 'Abrir Digitalização');
      action.href = '/digitalizacao';
      box.append(action);
    }
    return box;
  };

  /* ---------- KPIs + sparklines ---------- */
  const spark = (svg, values) => {
    svg.replaceChildren();
    const max = Math.max(...values, 0);
    if (!values.length || !max) { svg.append(svgEl('line', { x1: 0, y1: 26, x2: 100, y2: 26, class: 'cc-spark-base' })); return; }
    const step = values.length > 1 ? 100 / (values.length - 1) : 100;
    const points = values.map((v, i) => [i * step, 25 - (v / max) * 21]);
    const line = points.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(2) + ' ' + p[1].toFixed(2)).join(' ');
    svg.append(svgEl('path', { d: `${line} L100 27 L0 27 Z`, class: 'cc-spark-area' }), svgEl('path', { d: line, class: 'cc-spark-line', 'vector-effect': 'non-scaling-stroke' }));
    const last = points.at(-1);
    svg.append(svgEl('circle', { cx: last[0], cy: last[1], r: 1.8, class: 'cc-spark-dot', 'vector-effect': 'non-scaling-stroke' }));
  };
  function renderKpis(items, series) {
    const values = {
      validated: items.filter(i => i.status === 'validated').length,
      draft: items.filter(i => i.status === 'draft').length,
      approved: items.filter(i => i.status === 'approved').length,
      datasheets: items.length,
      packages: items.reduce((t, i) => t + (i.status === 'validated' ? Number(i.package_version || 1) : 0), 0),
      attention: items.filter(hasPending).length,
    };
    const lines = { validated: 'validated', draft: 'created', approved: 'approved', datasheets: 'created', packages: 'validated', attention: 'created' };
    $$('[data-cc-kpi]').forEach(card => {
      const key = card.dataset.ccKpi;
      const value = $('[data-cc-kpi-value]', card);
      value.textContent = opsUnknown() ? '—' : number.format(values[key]);
      card.classList.toggle('is-selected', state.status === key);
      spark($('[data-cc-spark]', card), series.list.map(b => b[lines[key]]));
    });
    put('[data-cc-tab-count="overview"]', number.format(items.length));
  }

  /* ---------- Evolution chart ---------- */
  const SERIES = [
    { key: 'created', label: 'Datasheets gerados', cls: 'ser-created' },
    { key: 'approved', label: 'Aprovações', cls: 'ser-approved' },
    { key: 'validated', label: 'Pacotes validados', cls: 'ser-validated' },
  ];
  const monotonePath = points => {
    if (points.length < 2) return points.length ? `M${points[0][0]} ${points[0][1]}` : '';
    const n = points.length, dx = [], m = [], t = [];
    for (let i = 0; i < n - 1; i++) { dx[i] = points[i + 1][0] - points[i][0]; m[i] = (points[i + 1][1] - points[i][1]) / dx[i]; }
    t[0] = m[0]; t[n - 1] = m[n - 2];
    for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2;
    for (let i = 0; i < n - 1; i++) {
      if (m[i] === 0) { t[i] = 0; t[i + 1] = 0; continue; }
      const a = t[i] / m[i], b = t[i + 1] / m[i], s = a * a + b * b;
      if (s > 9) { const k = 3 / Math.sqrt(s); t[i] = k * a * m[i]; t[i + 1] = k * b * m[i]; }
    }
    let d = `M${points[0][0].toFixed(1)} ${points[0][1].toFixed(1)}`;
    for (let i = 0; i < n - 1; i++) {
      const h = dx[i] / 3;
      d += ` C${(points[i][0] + h).toFixed(1)} ${(points[i][1] + t[i] * h).toFixed(1)} ${(points[i + 1][0] - h).toFixed(1)} ${(points[i + 1][1] - t[i + 1] * h).toFixed(1)} ${points[i + 1][0].toFixed(1)} ${points[i + 1][1].toFixed(1)}`;
    }
    return d;
  };
  let evolutionData = null;
  function renderEvolution() {
    const host = $('[data-cc-evolution]');
    if (!host || !evolutionData || host.offsetParent === null) return;
    const { list, weekly } = evolutionData;
    const message = opsMessage();
    const active = SERIES.filter(s => state.series.has(s.key));
    const totals = Object.fromEntries(SERIES.map(s => [s.key, list.reduce((t, b) => t + b[s.key], 0)]));
    const totalBox = $('[data-cc-evolution-total]');
    totalBox.replaceChildren();
    SERIES.forEach(s => {
      const chip = el('span', 'cc-evo-stat' + (state.series.has(s.key) ? '' : ' is-off'));
      chip.append(el('i', s.cls), el('strong', '', number.format(totals[s.key])), el('small', '', s.label));
      totalBox.append(chip);
    });
    const tbody = $('[data-cc-evolution-table]');
    tbody.replaceChildren();
    list.filter(b => b.created || b.approved || b.validated).forEach(b => {
      const tr = el('tr');
      tr.append(el('th', '', weekly ? `Semana de ${shortDay.format(keyToDate(b.key))}` : shortDay.format(keyToDate(b.key))), el('td', '', b.created), el('td', '', b.approved), el('td', '', b.validated));
      tr.firstChild.scope = 'row';
      tbody.append(tr);
    });
    host.replaceChildren();
    const allZero = !list.some(b => b.created || b.approved || b.validated);
    if (message || allZero) {
      host.append(emptyBlock(message || { title: 'Sem etapas registradas no período', text: 'Amplie o período ou ajuste os filtros de empresa e status.' }, !!message));
      host.classList.add('is-empty');
      return;
    }
    host.classList.remove('is-empty');
    const width = Math.max(280, host.clientWidth), height = Math.max(200, host.clientHeight || 240);
    const pad = { top: 14, right: 12, bottom: 26, left: 34 };
    const iw = width - pad.left - pad.right, ih = height - pad.top - pad.bottom;
    const cumulative = {};
    SERIES.forEach(s => { let run = 0; cumulative[s.key] = list.map(b => (run += b[s.key])); });
    const max = Math.max(1, ...active.map(s => cumulative[s.key].at(-1)));
    const niceMax = max <= 4 ? max : Math.ceil(max / 4) * 4;
    const x = i => pad.left + (list.length > 1 ? (i / (list.length - 1)) * iw : iw / 2);
    const y = v => pad.top + ih - (v / niceMax) * ih;
    const svg = svgEl('svg', { viewBox: `0 0 ${width} ${height}`, width, height, class: 'cc-evo-svg' });
    const ticks = niceMax <= 4 ? niceMax : 4;
    for (let i = 0; i <= ticks; i++) {
      const value = Math.round((niceMax / ticks) * i);
      svg.append(svgEl('line', { x1: pad.left, x2: width - pad.right, y1: y(value), y2: y(value), class: 'cc-grid-line' }));
      const label = svgEl('text', { x: pad.left - 8, y: y(value) + 3.5, class: 'cc-axis-text', 'text-anchor': 'end' });
      label.textContent = number.format(value);
      svg.append(label);
    }
    const minGap = 84;
    const labelled = [];
    list.forEach((_, i) => {
      const last = i === list.length - 1;
      if (last) { while (labelled.length && x(i) - x(labelled.at(-1)) < minGap) labelled.pop(); labelled.push(i); }
      else if (!labelled.length || x(i) - x(labelled.at(-1)) >= minGap) labelled.push(i);
    });
    labelled.forEach(i => {
      const b = list[i];
      const label = svgEl('text', { x: x(i), y: height - 6, class: 'cc-axis-text', 'text-anchor': i === 0 ? 'start' : i === list.length - 1 ? 'end' : 'middle' });
      label.textContent = shortDay.format(keyToDate(b.key)).replace('.', '');
      svg.append(label);
    });
    active.forEach(s => {
      const points = cumulative[s.key].map((v, i) => [x(i), y(v)]);
      const line = monotonePath(points);
      svg.append(svgEl('path', { d: `${line} L${points.at(-1)[0].toFixed(1)} ${y(0)} L${points[0][0].toFixed(1)} ${y(0)} Z`, class: 'cc-evo-area ' + s.cls }));
      svg.append(svgEl('path', { d: line, class: 'cc-evo-line ' + s.cls }));
      const last = points.at(-1);
      svg.append(svgEl('circle', { cx: last[0], cy: last[1], r: 4, class: 'cc-evo-dot ' + s.cls }));
    });
    const cross = svgEl('line', { x1: 0, x2: 0, y1: pad.top, y2: pad.top + ih, class: 'cc-crosshair', visibility: 'hidden' });
    const markers = active.map(s => svgEl('circle', { r: 4.5, class: 'cc-evo-dot ' + s.cls, visibility: 'hidden' }));
    svg.append(cross, ...markers);
    const overlay = svgEl('rect', { x: pad.left, y: pad.top, width: iw, height: ih, fill: 'transparent', class: 'cc-evo-hit' });
    svg.append(overlay);
    host.append(svg);
    host.tabIndex = 0;
    let focusIndex = list.length - 1;
    const showIndex = (i, clientX, clientY) => {
      focusIndex = Math.max(0, Math.min(list.length - 1, i));
      const b = list[focusIndex];
      cross.setAttribute('x1', x(focusIndex)); cross.setAttribute('x2', x(focusIndex)); cross.setAttribute('visibility', 'visible');
      markers.forEach((m, k) => { m.setAttribute('cx', x(focusIndex)); m.setAttribute('cy', y(cumulative[active[k].key][focusIndex])); m.setAttribute('visibility', 'visible'); });
      const rect = host.getBoundingClientRect();
      const title = weekly ? `Semana de ${shortDay.format(keyToDate(b.key))}` : longDay.format(keyToDate(b.key));
      showTip(host, clientX ?? rect.left + (x(focusIndex) / width) * rect.width, clientY ?? rect.top + 20, {
        value: active.map(s => `${s.label.split(' ')[0]} ${cumulative[s.key][focusIndex]}`).join(' · '), title,
        note: 'acumulado no período · ' + (weekly ? 'na semana: ' : 'no dia: ') + active.map(s => `${b[s.key]}`).join(' / '),
      });
    };
    const clear = () => { cross.setAttribute('visibility', 'hidden'); markers.forEach(m => m.setAttribute('visibility', 'hidden')); hideTip(); };
    overlay.addEventListener('pointermove', event => {
      const rect = svg.getBoundingClientRect();
      const px = ((event.clientX - rect.left) / rect.width) * width;
      showIndex(Math.round(((px - pad.left) / iw) * (list.length - 1)), event.clientX, event.clientY);
    });
    overlay.addEventListener('pointerleave', clear);
    host.onkeydown = event => {
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); showIndex(focusIndex + (event.key === 'ArrowRight' ? 1 : -1)); }
      if (event.key === 'Escape') clear();
    };
    host.onfocus = () => showIndex(focusIndex);
    host.onblur = clear;
    host.setAttribute('aria-label', `Etapas acumuladas no período, ${weekly ? 'por semana' : 'por dia'}: ${SERIES.map(s => `${s.label} ${totals[s.key]}`).join(', ')}. Use as setas para navegar.`);
  }
  $$('[data-cc-series]').forEach(button => button.addEventListener('click', () => {
    const key = button.dataset.ccSeries;
    if (state.series.has(key) && state.series.size === 1) { toast('Mantenha ao menos uma série visível.'); return; }
    state.series.has(key) ? state.series.delete(key) : state.series.add(key);
    button.setAttribute('aria-pressed', String(state.series.has(key)));
    renderEvolution();
  }));
  if ('ResizeObserver' in window) {
    let frame = 0;
    const host = $('[data-cc-evolution]');
    if (host) new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(renderEvolution); }).observe(host);
  }

  /* ---------- Attention queue ---------- */
  const runLink = item => '/digitalizacao?execucao=' + encodeURIComponent(item.run_id);
  function renderAttention(items) {
    const list = $('[data-cc-attention]');
    list.replaceChildren();
    const message = opsMessage();
    const queue = items.filter(needsAttention).map(item => ({
      item,
      kind: hasPending(item) ? 'pending' : item.status === 'draft' ? 'review' : 'package',
      since: item.status === 'approved' ? item.approved_at || item.created_at : item.created_at,
    })).sort((a, b) => (a.kind === 'pending' ? -1 : 0) - (b.kind === 'pending' ? -1 : 0) || a.since.localeCompare(b.since));
    put('[data-cc-attention-count]', opsUnknown() ? '—' : number.format(queue.length));
    if (message) { list.append(emptyBlock(message)); return; }
    if (operations.unreadable) {
      const li = el('li', 'cc-queue-item q-info');
      li.append(icon('alert'), el('span', 'cc-queue-copy'));
      li.lastChild.append(el('strong', '', `${operations.unreadable} registro(s) ilegível(is)`), el('small', '', 'Arquivos record.json inválidos foram ignorados.'));
      list.append(li);
    }
    if (!queue.length) {
      const ok = el('li', 'cc-queue-clear');
      ok.append(icon('check'), el('span', '', 'Nada aguardando ação com os filtros atuais.'));
      list.append(ok);
      return;
    }
    const labels = { pending: ['Datasheet com pendências', 'Revisar e aprovar'], review: ['Aguardando revisão', 'Revisar datasheet'], package: ['Aprovado · falta pacote', 'Gerar pacote'] };
    queue.slice(0, 6).forEach(({ item, kind, since }) => {
      const li = el('li', 'cc-queue-item q-' + kind);
      const copy = el('span', 'cc-queue-copy');
      const meta = el('small');
      meta.append(el('span', 'cc-co-chip co-' + item.company, COMPANY_NAMES[item.company]), el('code', '', item.sku), document.createTextNode(' · ' + ago(since)));
      copy.append(el('strong', '', labels[kind][0] + (kind === 'pending' ? ` (${item.pending})` : '')), el('span', 'cc-queue-name', item.name), meta);
      const action = el('a', 'cc-queue-action', labels[kind][1]);
      action.href = runLink(item);
      action.append(icon('arrow'));
      li.append(icon(kind === 'package' ? 'package' : kind === 'pending' ? 'alert' : 'file'), copy, action);
      list.append(li);
    });
    if (queue.length > 6) {
      const more = el('li', 'cc-queue-more');
      const button = el('button', 'cc-link', `Ver todas as ${queue.length} na tabela`);
      button.type = 'button';
      button.addEventListener('click', () => { focusTable(); });
      more.append(button);
      list.append(more);
    }
  }

  /* ---------- Pipeline ---------- */
  function renderPipeline(items) {
    const message = opsMessage();
    const total = items.length;
    const approved = items.filter(i => i.status !== 'draft').length;
    const validated = items.filter(i => i.status === 'validated').length;
    const waiting = { approved: items.filter(i => i.status === 'draft').length, validated: items.filter(i => i.status === 'approved').length };
    const values = { created: total, analysis: total, datasheet: total, approved, validated };
    const bottleneck = message ? null : waiting.approved >= waiting.validated ? (waiting.approved ? 'approved' : null) : 'validated';
    $$('[data-cc-stage]').forEach(step => {
      const key = step.dataset.ccStage;
      const tracked = key in values;
      step.classList.toggle('is-untracked', !tracked);
      step.classList.toggle('is-bottleneck', key === bottleneck);
      $('[data-cc-stage-value]', step).textContent = !tracked || opsUnknown() ? '—' : number.format(values[key]);
      if (tracked && waiting[key] && !message) $('[data-cc-stage-note]', step).textContent = `${number.format(waiting[key])} aguardando`;
      else if (tracked) $('[data-cc-stage-note]', step).textContent = { created: 'execuções no período', analysis: 'análise técnica salva', datasheet: 'PDF gerado', approved: 'revisão humana', validated: 'pasta CIGAM validada' }[key];
      $('.cc-flow-bar i', step).style.setProperty('--w', tracked && total && !message ? (100 * values[key] / total) + '%' : '0%');
    });
    put('[data-cc-bottleneck]', bottleneck ? `Gargalo: ${bottleneck === 'approved' ? 'aprovação' : 'pacote'} · ${number.format(waiting[bottleneck])}` : message ? 'Sem dados' : 'Sem gargalos');
    const tag = $('[data-cc-bottleneck]');
    if (tag) tag.classList.toggle('is-alert', Boolean(bottleneck));
  }

  /* ---------- Heatmap (12 weeks, Mon→Sun) ---------- */
  function renderHeatmap(items) {
    const host = $('[data-cc-heatmap]');
    host.replaceChildren();
    const message = opsMessage();
    const end = todayKey();
    const endDate = keyToDate(end);
    const startMonday = addDays(end, -((endDate.getUTCDay() + 6) % 7) - 7 * 11);
    const counts = new Map();
    events(items).forEach(e => { const k = dayKey(e.at); counts.set(k, (counts.get(k) || 0) + 1); });
    const max = Math.max(0, ...[...counts.entries()].filter(([k]) => k >= startMonday && k <= end).map(([, v]) => v));
    const level = v => !v ? 0 : max <= 5 ? Math.min(5, v) : Math.min(5, Math.ceil((v / max) * 5));
    const days = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
    const grid = el('div', 'cc-heat-grid');
    days.forEach((d, i) => { const label = el('span', 'cc-heat-day', i % 2 ? '' : d); grid.append(label); });
    let total = 0;
    for (let w = 0; w < 12; w++) {
      for (let d = 0; d < 7; d++) {
        const key = addDays(startMonday, w * 7 + d);
        const v = key > end ? null : counts.get(key) || 0;
        const cell = el('span', 'cc-heat-cell ' + (v === null ? 'is-future' : 'h' + level(v)));
        cell.style.gridColumn = String(w + 2);
        cell.style.gridRow = String(d + 1);
        if (v !== null) {
          total += v;
          cell.dataset.tipTitle = longDay.format(keyToDate(key));
          cell.dataset.tipValue = `${v} ${v === 1 ? 'evento' : 'eventos'}`;
          cell.dataset.tipNote = 'datasheets, aprovações e pacotes';
          if (v) cell.tabIndex = 0;
        }
        grid.append(cell);
      }
    }
    host.append(grid);
    if (message) host.append(emptyBlock(message, false));
    put('[data-cc-heat-total]', message ? 'Sem dados' : `${number.format(total)} eventos`);
    host.setAttribute('aria-label', `Mapa de calor: ${total} eventos nas últimas 12 semanas.`);
  }

  /* ---------- Distribution (runs per company) ---------- */
  function renderDistribution() {
    const items = (operations.items || []).filter(i => inPeriod(i.created_at) && statusMatch(i));
    const per = Object.fromEntries(OPS_COMPANIES.map(c => [c, items.filter(i => i.company === c).length]));
    const max = Math.max(1, ...Object.values(per));
    OPS_COMPANIES.forEach(c => {
      put(`[data-cc-dist-runs="${c}"]`, operations.status === 'ok' || operations.status === 'no_runs' ? number.format(per[c]) : '—');
      $(`[data-cc-dist-runs-bar="${c}"]`)?.style.setProperty('--w', (100 * per[c] / max) + '%');
    });
  }

  /* ---------- Recent products table ---------- */
  const stageInfo = item => item.status === 'validated'
    ? { label: 'Concluído', cls: 'is-done', detail: `Pacote v${item.package_version || 1}` }
    : item.status === 'approved' ? { label: 'Pacote pendente', cls: 'is-progress', detail: 'Aprovado' }
    : hasPending(item) ? { label: 'Com pendências', cls: 'is-alert', detail: `${item.pending} pendência(s)` }
    : { label: 'Em revisão', cls: 'is-review', detail: 'Datasheet gerado' };
  const stageRank = { draft: 0, approved: 1, validated: 2 };
  function renderRecent(items) {
    const body = $('[data-cc-recent]');
    body.replaceChildren();
    const message = opsMessage();
    const query = state.search.trim().toLocaleLowerCase('pt-BR');
    let rows = items.filter(i => !query || i.sku.toLocaleLowerCase('pt-BR').includes(query) || i.name.toLocaleLowerCase('pt-BR').includes(query));
    const value = { company: i => COMPANY_NAMES[i.company], sku: i => i.sku, name: i => i.name, stage: i => stageRank[i.status], updated: i => updatedAt(i) };
    rows.sort((a, b) => { const va = value[state.sort](a), vb = value[state.sort](b); return (va > vb ? 1 : va < vb ? -1 : 0) * state.direction; });
    $$('[data-cc-sort]').forEach(button => button.closest('th').setAttribute('aria-sort', button.dataset.ccSort === state.sort ? (state.direction > 0 ? 'ascending' : 'descending') : 'none'));
    if (message || !rows.length) {
      const tr = el('tr', 'cc-empty-row');
      const td = el('td');
      td.colSpan = 6;
      td.append(emptyBlock(message || { title: 'Nenhum produto corresponde aos filtros', text: 'Ajuste período, status, empresa ou a busca da tabela.' }, !!message));
      tr.append(td);
      body.append(tr);
    }
    rows.slice(0, state.limit).forEach(item => {
      const tr = el('tr');
      const info = stageInfo(item);
      const companyCell = el('td');
      companyCell.append(el('span', 'cc-co-chip co-' + item.company, COMPANY_NAMES[item.company]));
      const skuCell = el('td', 'cc-sku-cell');
      const copy = el('button', 'cc-copy');
      copy.type = 'button';
      copy.setAttribute('aria-label', `Copiar código CIGAM ${item.sku}`);
      copy.append(el('code', '', item.sku), icon('copy'));
      copy.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(item.sku); toast(`Código ${item.sku} copiado.`, 'ok'); copy.classList.add('is-copied'); window.setTimeout(() => copy.classList.remove('is-copied'), 1200); }
        catch (_) { toast('Não foi possível copiar automaticamente; selecione o código.', 'error'); }
      });
      skuCell.append(copy);
      const nameCell = el('td', 'cc-name-cell');
      nameCell.append(el('span', '', item.name), el('small', '', `${item.image_count} foto(s)${item.warnings ? ` · ${item.warnings} aviso(s)` : ''}`));
      const stageCell = el('td');
      const badge = el('span', 'cc-badge ' + info.cls, info.label);
      stageCell.append(badge, el('small', '', info.detail));
      const updated = updatedAt(item);
      const timeCell = el('td', 'cc-time-cell');
      const time = el('time', '', ago(updated));
      time.dateTime = updated;
      time.title = stamp.format(new Date(updated));
      timeCell.append(time, el('small', '', stamp.format(new Date(updated))));
      const actionCell = el('td', 'cc-row-actions');
      const open = el('a', 'cc-row-action', 'Abrir');
      open.href = runLink(item);
      open.setAttribute('aria-label', `Abrir digitalização ${item.sku}`);
      open.append(icon('arrow'));
      actionCell.append(open);
      tr.append(companyCell, skuCell, nameCell, stageCell, timeCell, actionCell);
      body.append(tr);
    });
    const more = $('[data-cc-recent-more]');
    if (more) { more.hidden = rows.length <= state.limit; more.textContent = `Mostrar mais (${rows.length - state.limit})`; }
    put('[data-cc-recent-status]', message ? '' : `${Math.min(rows.length, state.limit)} de ${rows.length} execuções`);
  }
  $$('[data-cc-sort]').forEach(button => button.addEventListener('click', () => {
    const key = button.dataset.ccSort;
    state.direction = state.sort === key ? -state.direction : key === 'updated' ? -1 : 1;
    state.sort = key;
    render();
  }));
  $('[data-cc-recent-search]')?.addEventListener('input', event => { state.search = event.target.value; state.limit = 10; render(); });
  $('[data-cc-recent-more]')?.addEventListener('click', () => { state.limit += 10; render(); });
  const focusTable = () => { const table = $('.cc-recent-table'); table?.scrollIntoView({ behavior: reduceMotion.matches ? 'auto' : 'smooth', block: 'center' }); $('[data-cc-recent-search]')?.focus({ preventScroll: true }); };

  /* ---------- Feed ---------- */
  function renderFeed(items) {
    const list = $('[data-cc-feed]');
    list.replaceChildren();
    const message = opsMessage();
    if (message) { list.append(emptyBlock(message, false)); return; }
    const recent = events(items).filter(e => inPeriod(e.at)).sort((a, b) => b.at.localeCompare(a.at)).slice(0, 9);
    if (!recent.length) { list.append(emptyBlock({ title: 'Sem eventos no período', text: 'Amplie o período para ver o histórico.' }, false)); return; }
    const copy = { created: ['Datasheet gerado', 'Análise técnica salva com o PDF', 'file'], approved: ['Datasheet aprovado', 'Revisão humana concluída', 'check'], validated: ['Pacote validado', 'Pasta CIGAM e ZIP conferidos', 'package'] };
    recent.forEach(event => {
      const [title, detail, iconName] = copy[event.type];
      const li = el('li', 'cc-feed-item is-' + event.type);
      const body = el('div', 'cc-feed-body');
      const meta = el('small');
      meta.append(el('span', 'cc-co-chip co-' + event.item.company, COMPANY_NAMES[event.item.company]), el('code', '', event.item.sku));
      body.append(el('strong', '', title + (event.type === 'validated' && event.item.package_version ? ` · v${event.item.package_version}` : '')), el('span', '', `${event.item.name} — ${detail}`), meta);
      const time = el('time', '', ago(event.at));
      time.dateTime = event.at;
      time.title = stamp.format(new Date(event.at));
      const dot = el('span', 'cc-feed-icon');
      dot.append(icon(iconName));
      li.append(dot, body, time);
      list.append(li);
    });
  }

  /* ---------- Orchestration ---------- */
  const periodLabel = () => state.period === 'all' ? 'todo o histórico' : state.period === '365' ? 'últimos 12 meses' : `últimos ${state.period} dias`;
  function render() {
    const scoped = periodItems();
    const filtered = scoped.filter(statusMatch);
    const series = bucketise(state.company === 'eco' || state.company === 'dimensional' ? [] : filtered);
    evolutionData = series;
    renderKpis(state.company === 'eco' || state.company === 'dimensional' ? [] : scoped, series);
    renderEvolution();
    renderAttention(filtered);
    renderPipeline(state.company === 'eco' || state.company === 'dimensional' ? [] : filtered);
    renderHeatmap(state.company === 'eco' || state.company === 'dimensional' ? [] : companyItems().filter(statusMatch));
    renderDistribution();
    renderRecent(filtered);
    renderFeed(filtered);
    put('[data-cc-period-tag]', state.period === 'all' ? 'Histórico' : state.period === '365' ? '12 meses' : `${state.period} dias`);
    const statusText = { all: '', draft: ' · aguardando revisão', approved: ' · aprovados sem pacote', validated: ' · concluídos', attention: ' · com pendências' }[state.status];
    put('[data-cc-scope]', `Registros persistidos de digitalização · ${periodLabel()} · ${COMPANY_NAMES[state.company]}${statusText}`);
  }
  const flashKpis = () => {
    if (reduceMotion.matches) return;
    $$('.cc-kpi, .cc-mini').forEach(node => { node.classList.remove('is-updated'); void node.offsetWidth; node.classList.add('is-updated'); });
  };
  const selectCompany = source => {
    state.company = source;
    if (company && company.value !== source) company.value = source;
    root.dataset.company = source;
    applyCatalogContext(source);
    state.limit = 10;
    render();
    flashKpis();
  };
  company?.addEventListener('change', () => selectCompany(company.value));
  $$('[data-ops-company-card]').forEach(card => card.addEventListener('click', () => selectCompany(card.dataset.opsCompanyCard === state.company ? 'all' : card.dataset.opsCompanyCard)));
  $('[data-cc-period]')?.addEventListener('change', event => { state.period = event.target.value; state.limit = 10; render(); });
  const statusSelect = $('[data-cc-status]');
  statusSelect?.addEventListener('change', event => { state.status = event.target.value; state.limit = 10; render(); });
  $$('[data-cc-kpi]').forEach(card => card.addEventListener('click', () => {
    const key = card.dataset.ccKpi;
    const target = ['draft', 'approved', 'validated', 'attention'].includes(key) ? key : 'all';
    state.status = state.status === target ? 'all' : target;
    if (statusSelect) statusSelect.value = state.status;
    render();
    if (state.status !== 'all') focusTable();
  }));

  /* Refresh: read-only endpoint; keeps the current frame while loading. */
  const refreshButton = $('[data-cc-refresh]');
  let refreshing = false;
  const refresh = async ({ silent = false } = {}) => {
    if (refreshing || operations.status === 'restricted') { if (!silent && operations.status === 'restricted') toast('Atualização operacional disponível somente para gestores.'); return; }
    refreshing = true;
    root.classList.add('is-refreshing');
    refreshButton?.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch('/api/v1/operations/overview', { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
      if (response.status === 401) throw new Error('Sessão expirada. Entre novamente.');
      if (response.status === 403) { operations = { status: 'restricted', items: [] }; render(); throw new Error('Somente gestores consultam as execuções.'); }
      if (!response.ok) throw new Error('Não foi possível atualizar os dados operacionais.');
      operations = await response.json();
      render();
      put('[data-cc-sync]', `Atualizado às ${clockTime.format(new Date())}`);
      if (!silent) toast(`Dados operacionais atualizados · ${number.format((operations.items || []).length)} execuções.`, 'ok');
    } catch (error) {
      if (!silent) toast(error.message, 'error');
    } finally {
      refreshing = false;
      root.classList.remove('is-refreshing');
      refreshButton?.removeAttribute('aria-busy');
    }
  };
  refreshButton?.addEventListener('click', () => refresh());
  let poll = null;
  const startPolling = () => { if (!poll && operations.status !== 'restricted') poll = window.setInterval(() => refresh({ silent: true }), 300000); };
  const stopPolling = () => { if (poll) { clearInterval(poll); poll = null; } };
  document.addEventListener('visibilitychange', () => (document.hidden ? stopPolling() : startPolling()));
  window.addEventListener('pagehide', stopPolling);

  /* Density */
  const density = $('[data-ops-density]');
  const setDensity = compact => { root.classList.toggle('is-dense', compact); density?.setAttribute('aria-pressed', String(compact)); };
  try { setDensity(localStorage.getItem('prm-density') === 'compact'); } catch (_) { /* opcional */ }
  density?.addEventListener('click', () => {
    const compact = !root.classList.contains('is-dense');
    setDensity(compact);
    try { localStorage.setItem('prm-density', compact ? 'compact' : 'comfortable'); } catch (_) { /* opcional */ }
    requestAnimationFrame(renderEvolution);
  });

  /* Short count-up on first paint; final value is always the rendered text. */
  const countUp = node => {
    const target = Number(node.dataset.count);
    if (!Number.isFinite(target) || reduceMotion.matches || target < 10) return;
    const finalText = node.textContent;
    node.dataset.countFinal = finalText;
    const started = performance.now();
    const step = now => {
      if (node.dataset.countFinal !== finalText) return;
      const progress = Math.min(1, (now - started) / 480);
      node.textContent = progress < 1 ? number.format(Math.round(target * (1 - Math.pow(1 - progress, 3)))) : finalText;
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  showView(root.dataset.initialView);
  selectCompany(company?.value || 'all');
  $$('[data-count]').forEach(countUp);
  startPolling();
  root.classList.add('is-ready');
})();
