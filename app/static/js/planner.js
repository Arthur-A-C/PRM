/* Planner — centro operacional. Agenda unificada (tarefas, reuniões, cards e follow-ups de fornecedores),
   criação direta e detalhe contextual. Revisão de cards, reuniões/transcrições e o diálogo de atividade continuam
   em meetings.js; os dois scripts conversam por eventos (prm:open-activity, prm:open-meeting, prm:planner-*). */
(() => {
  'use strict';
  const root = document.querySelector('[data-planner-hub]');
  if (!root) return;
  const base = '/api/v1/planner', csrf = document.querySelector('input[name=csrf_token]')?.value || '';
  const q = (s, scope = root) => scope.querySelector(s), qa = (s, scope = root) => [...scope.querySelectorAll(s)];
  const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined && text !== null) node.textContent = text; if (cls) node.className = cls; return node; };
  const TYPE = {task: 'Tarefa', meeting: 'Reunião', card: 'Card', followup: 'Follow-up'};
  const STATUS = {todo: 'A fazer', in_progress: 'Em andamento', waiting_external: 'Aguardando parceiro', blocked: 'Bloqueada', done: 'Concluída', cancelled: 'Cancelada'};
  const APPROVAL = {draft: 'Em revisão', approved: 'Aprovado', rejected: 'Rejeitado', published: 'Publicado'};
  const PRIORITY = {alta: 'Alta', normal: 'Normal', baixa: 'Baixa'};
  const BANDS = {on_time: 'Em dia', attention: 'Atenção', prioritize: 'Priorizar', overdue: 'Vencidas'};
  const HINT = {
    task: 'A tarefa entra publicada na agenda e gera alertas para o responsável.',
    meeting: 'A reunião aparece na agenda no horário marcado. Depois dela, envie a transcrição na própria reunião para gerar cards com IA.',
    card: 'O card fica em “Revisão de cards” até ser aprovado e publicado; só então entra na agenda.',
    followup: 'Follow-up é uma tarefa do fornecedor: aparece aqui e na ficha dele.',
  };
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en', {timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(new Date()).map(p => [p.type, p.value]));
  const today = `${parts.year}-${parts.month}-${parts.day}`;
  const addDays = (key, n) => { const [y, m, d] = key.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10); };
  const shortDate = key => { const [y, m, d] = key.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d, 12)).toLocaleDateString('pt-BR', {weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'UTC'}); };
  const fullDate = key => key ? key.split('-').reverse().join('/') : 'Sem data';
  const clock = item => item.start ? new Date(item.start).toLocaleTimeString('pt-BR', {timeZone: item.timezone || 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit'}) : '';
  let users = [], suppliers = [], items = [], range = ['', ''], type = 'all', source = '', layout = 'list', month = today.slice(0, 7), drawerKey = null, lastFocus = null, loadTimer;
  const userName = id => users.find(u => u.id === id)?.name || (id ? 'Usuário' : 'Sem responsável');
  const isOpen = item => !['done', 'cancelled'].includes(item.status);
  const message = (text, tone = '') => { const box = q('[data-planner-message]'); box.textContent = text; box.dataset.tone = tone; };

  async function api(path, options = {}) {
    const response = await fetch(path.startsWith('/api/') ? path : base + path, {credentials: 'same-origin', cache: 'no-store', ...options,
      headers: {'X-CSRF-Token': csrf, ...(options.body && !(options.body instanceof FormData) ? {'Content-Type': 'application/json'} : {}), ...options.headers}});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Dados inválidos; confira os campos e as permissões.');
    return data;
  }
  const get = path => api(path);
  const send = (path, method, payload) => api(path, {method, body: JSON.stringify(payload)});

  /* ---------- Visões (abas) ---------- */
  const tabs = qa('[data-pl-view]');
  function setView(view, push = true) {
    if (!tabs.some(t => t.dataset.plView === view)) view = 'agenda';
    tabs.forEach(tab => { const on = tab.dataset.plView === view; tab.setAttribute('aria-selected', String(on)); tab.tabIndex = on ? 0 : -1; });
    qa('[data-pl-pane]').forEach(pane => { pane.hidden = pane.dataset.plPane !== view; });
    if (push) { const url = new URL(location.href); if (view === 'agenda') url.searchParams.delete('view'); else url.searchParams.set('view', view); history.replaceState(null, '', url); }
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => setView(tab.dataset.plView));
    tab.addEventListener('keydown', event => {
      const next = {ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1}[event.key];
      if (next === undefined) return;
      event.preventDefault(); const target = tabs[(next + tabs.length) % tabs.length]; setView(target.dataset.plView); target.focus();
    });
  });

  /* ---------- Agenda ---------- */
  const filters = q('[data-pl-filters]');
  function periodRange() {
    const period = filters.elements.period.value;
    if (period === 'today') return [today, addDays(today, 1)];
    if (period === 'week') return [today, addDays(today, 7)];
    const [y, m] = month.split('-').map(Number);
    return [`${month}-01`, new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 10)];
  }
  function schedule() { clearTimeout(loadTimer); loadTimer = setTimeout(() => load().catch(error => message(error.message, 'error')), 60); }
  async function load() {
    range = periodRange();
    filters.elements.month.value = month;
    q('[data-pl-month-field]').hidden = filters.elements.period.value !== 'month';
    const data = await get(`/feed?start=${range[0]}&end=${range[1]}`);
    items = data.items;
    render();
  }
  function matches(item, ignoreType = false) {
    const f = filters.elements;
    if (!ignoreType && type !== 'all' && item.type !== type) return false;
    if (source && item.source_type !== source) return false;  // ex.: Dashboard → “Sem interação”
    if (f.assignee.value && item.assignee_user_id !== f.assignee.value) return false;
    if (f.status.value === 'open' ? !isOpen(item) : f.status.value && item.status !== f.status.value) return false;
    if (f.priority.value && (item.priority || 'normal') !== f.priority.value) return false;
    if (f.supplier.value && item.supplier_id !== f.supplier.value) return false;
    if (!f.proposals.checked && ['draft', 'approved'].includes(item.approval)) return false;
    if (item.approval === 'rejected') return false;
    return true;
  }
  const late = item => item.overdue && isOpen(item) && item.type !== 'meeting';
  function groupOf(item) {
    if (!item.date) return 'undated';
    if (late(item) && item.date < today) return 'late';
    if (item.date < today) return 'past';
    if (item.date === today) return 'today';
    if (item.date === addDays(today, 1)) return 'tomorrow';
    if (item.date <= addDays(today, 7)) return 'week';
    return 'later';
  }
  const GROUPS = [['late', 'Atrasados'], ['today', 'Hoje'], ['tomorrow', 'Amanhã'], ['week', 'Próximos 7 dias'], ['later', 'Mais adiante'], ['undated', 'Sem data'], ['past', 'Anteriores']];

  function chip(text, tone = '') { return el('span', text, ('mt-chip ' + tone).trim()); }
  function row(item, showDate) {
    const article = el('article', null, `pl-item is-${item.type}${isOpen(item) ? '' : ' is-closed'}${late(item) ? ' is-late' : ''}`);
    const main = el('button', null, 'pl-item-main'); main.type = 'button';
    main.setAttribute('aria-label', `${TYPE[item.type]}: ${item.title}`);
    const when = el('span', null, 'pl-item-when');
    if (showDate && item.date) when.append(el('strong', shortDate(item.date)));
    when.append(el('span', clock(item) || (item.date ? 'Dia todo' : '—')));
    const body = el('span', null, 'pl-item-body');
    const head = el('span', null, 'pl-item-title'); head.append(el('span', null, `pl-type-dot is-${item.type}`), el('strong', item.title));
    const meta = [item.category || TYPE[item.type], userName(item.assignee_user_id), item.supplier_name, item.meeting_title && item.type !== 'meeting' ? 'Reunião: ' + item.meeting_title : null].filter(Boolean).join(' · ');
    body.append(head, el('small', meta));
    const chips = el('span', null, 'mt-chips pl-item-chips');
    if (late(item)) chips.append(chip('Atrasado', 'is-alert'));
    if (item.priority === 'alta') chips.append(chip('Prioridade alta', 'is-warn'));
    if (['draft', 'approved'].includes(item.approval)) chips.append(chip(APPROVAL[item.approval], 'is-info'));
    if (item.status !== 'todo' && STATUS[item.status] && !(item.source === 'meeting')) chips.append(chip(STATUS[item.status], item.status === 'done' ? 'is-ok' : item.status === 'blocked' ? 'is-alert' : ''));
    main.append(when, body, chips);
    main.addEventListener('click', () => openItem(item));
    article.append(main);
    return article;
  }
  function render() {
    const scoped = items.filter(item => matches(item, true));
    qa('[data-pl-type-count]').forEach(node => { const key = node.dataset.plTypeCount; node.textContent = key === 'all' ? scoped.length : scoped.filter(i => i.type === key).length; });
    const visible = scoped.filter(item => type === 'all' || item.type === type);
    const count = key => visible.filter(i => groupOf(i) === key).length;
    const summary = q('[data-pl-summary]');
    const sourceChip = source ? (() => { const b = el('button', null, 'pl-summary-item pl-source-chip'); b.type = 'button'; b.append(el('span', 'Filtro: ' + (items.find(i => i.source_type === source)?.category || 'origem automática')), el('strong', '×')); b.setAttribute('aria-label', 'Remover filtro de origem'); b.addEventListener('click', () => { source = ''; const url = new URL(location.href); url.searchParams.delete('source'); history.replaceState(null, '', url); render(); }); return b; })() : null;
    summary.replaceChildren(...(sourceChip ? [sourceChip] : []), ...[['late', 'Atrasados', 'is-alert'], ['today', 'Hoje', ''], ['week', 'Próximos 7 dias', ''], ['undated', 'Sem data', '']].map(([key, label, tone]) => {
      const n = key === 'week' ? count('tomorrow') + count('week') : count(key);
      const b = el('button', null, `pl-summary-item ${n && tone ? tone : ''}`.trim()); b.type = 'button';
      b.append(el('strong', String(n)), el('span', label));
      b.addEventListener('click', () => { setLayout('list'); q(`[data-pl-group="${key === 'week' ? 'tomorrow' : key}"]`)?.scrollIntoView({behavior: 'smooth', block: 'start'}); });
      return b;
    }));
    if (layout === 'calendar') return renderCalendar(visible);
    const list = q('[data-pl-list]');
    if (!visible.length) {
      const empty = el('div', null, 'prm-empty');
      empty.append(el('strong', items.length ? 'Nada neste filtro.' : 'Agenda vazia neste período.'), el('p', items.length ? 'Ajuste os filtros ou o período para ver outros itens.' : 'Crie uma tarefa, agende uma reunião ou registre um follow-up de fornecedor.'));
      const actions = el('div', null, 'prm-empty-actions'); const add = el('button', '+ Novo item', 'cc-btn cc-btn-primary'); add.type = 'button'; add.addEventListener('click', () => openCreate('task')); actions.append(add); empty.append(actions);
      list.replaceChildren(empty); return;
    }
    list.replaceChildren(...GROUPS.map(([key, label]) => {
      const rows = visible.filter(i => groupOf(i) === key);
      if (!rows.length) return null;
      const section = el(key === 'past' ? 'details' : 'section', null, `pl-group is-${key}`); section.dataset.plGroup = key;
      const title = el(key === 'past' ? 'summary' : 'h3', null, 'pl-group-title'); title.append(el('span', label), el('b', String(rows.length), 'pl-count'));
      section.append(title, ...rows.map(item => row(item, !['today'].includes(key))));
      return section;
    }).filter(Boolean));
  }
  function renderCalendar(visible) {
    const calendar = q('[data-pl-calendar]'); calendar.replaceChildren();
    ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'].forEach(d => calendar.append(el('div', d, 'mt-weekday')));
    const [y, m] = month.split('-').map(Number), first = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7, last = new Date(Date.UTC(y, m, 0)).getUTCDate();
    for (let i = 0; i < first; i++) calendar.append(el('div', '', 'mt-day is-padding'));
    for (let day = 1; day <= last; day++) {
      const key = `${month}-${String(day).padStart(2, '0')}`, cell = el('section', null, 'mt-day' + (key === today ? ' is-today' : ''));
      cell.setAttribute('aria-label', fullDate(key)); cell.append(el('strong', String(day)));
      const rows = visible.filter(i => i.date === key);
      const draw = all => {
        cell.querySelectorAll('button').forEach(b => b.remove());
        rows.slice(0, all ? rows.length : 3).forEach(item => {
          const b = el('button', `${clock(item) ? clock(item) + ' · ' : ''}${item.title}`, `pl-cal-item is-${item.type}${isOpen(item) ? '' : ' is-closed'}`); b.type = 'button';
          b.title = `${TYPE[item.type]} · ${userName(item.assignee_user_id)}${item.supplier_name ? ' · ' + item.supplier_name : ''}`;
          b.addEventListener('click', () => openItem(item)); cell.append(b);
        });
        if (!all && rows.length > 3) { const more = el('button', `+${rows.length - 3}`, 'pl-cal-more'); more.type = 'button'; more.addEventListener('click', () => draw(true)); cell.append(more); }
      };
      draw(false); calendar.append(cell);
    }
  }
  function setLayout(next) {
    if (next === 'calendar' && filters.elements.period.value !== 'month') { filters.elements.period.value = 'month'; layout = next; schedule(); }
    layout = next;
    qa('[data-pl-layout]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.plLayout === layout)));
    q('[data-pl-list]').hidden = layout !== 'list'; q('[data-pl-calendar]').hidden = layout !== 'calendar';
    render();
  }
  qa('[data-pl-layout]').forEach(b => b.addEventListener('click', () => setLayout(b.dataset.plLayout)));
  qa('[data-pl-type]').forEach(b => b.addEventListener('click', () => {
    type = b.dataset.plType; qa('[data-pl-type]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); render();
  }));
  filters.addEventListener('change', event => { if (['period', 'month'].includes(event.target.name)) { if (event.target.name === 'month' && /^\d{4}-\d{2}$/.test(event.target.value)) month = event.target.value; schedule(); } else render(); });
  filters.addEventListener('submit', event => event.preventDefault());
  qa('[data-pl-month-step]').forEach(b => b.addEventListener('click', () => {
    const [y, m] = month.split('-').map(Number); month = new Date(Date.UTC(y, m - 1 + Number(b.dataset.plMonthStep), 1)).toISOString().slice(0, 7);
    filters.elements.period.value = 'month'; schedule();
  }));
  q('[data-pl-month-today]').addEventListener('click', () => { month = today.slice(0, 7); filters.elements.period.value = 'month'; schedule(); if (layout === 'list') setTimeout(() => q('[data-pl-group="today"]')?.scrollIntoView({behavior: 'smooth', block: 'start'}), 300); });

  /* ---------- Detalhe contextual ---------- */
  const drawer = q('[data-pl-drawer]'), backdrop = q('[data-pl-backdrop]'), drawerBody = q('[data-pl-drawer-body]'), meetingDetail = q('[data-meeting-detail]');
  function openDrawer(kind, title, key, keepDetail = false) {
    if (drawer.hidden) lastFocus = document.activeElement;
    drawerKey = key; drawer.hidden = false; backdrop.hidden = false; document.body.classList.add('pl-drawer-open');
    q('[data-pl-drawer-kind]').textContent = kind; q('[data-pl-drawer-title]').textContent = title;
    drawerBody.replaceChildren(el('div', 'Carregando…', 'prm-loading'));
    if (!keepDetail) { meetingDetail.hidden = true; meetingDetail.replaceChildren(); }
    drawer.focus();
  }
  function closeDrawer() {
    drawer.hidden = true; backdrop.hidden = true; drawerKey = null; document.body.classList.remove('pl-drawer-open');
    const url = new URL(location.href); ['meeting', 'segment'].forEach(k => url.searchParams.delete(k)); history.replaceState(null, '', url);
    lastFocus?.focus?.();
  }
  q('[data-pl-drawer-close]').addEventListener('click', closeDrawer);
  backdrop.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !drawer.hidden && !document.querySelector('dialog[open]')) closeDrawer(); });

  function section(title, ...children) { const node = el('section', null, 'pl-drawer-section'); node.append(el('h3', title), ...children); return node; }
  function facts(pairs) {
    const dl = el('dl', null, 'pl-facts');
    pairs.filter(([, value]) => value !== null && value !== undefined && value !== '').forEach(([label, value]) => {
      const box = el('div'); box.append(el('dt', label)); const dd = el('dd'); if (value instanceof Node) dd.append(value); else dd.textContent = value; box.append(dd); dl.append(box);
    });
    return dl;
  }
  const link = (text, href, external = false) => { const a = el('a', text); a.href = href; if (external) { a.target = '_blank'; a.rel = 'noopener noreferrer'; } return a; };

  function openItem(item) {
    if (item.open === 'activity') document.dispatchEvent(new CustomEvent('prm:open-activity', {detail: {id: item.activity_id}}));
    else if (item.open === 'meeting') openMeetingDrawer(item.meeting_id).catch(error => message(error.message, 'error'));
    else openSupplierDrawer(item);
  }

  async function openMeetingDrawer(id, renderedByMeetings = false) {
    openDrawer('Reunião', 'Reunião', 'meeting:' + id, renderedByMeetings);
    const url = new URL(location.href); url.searchParams.set('meeting', id); history.replaceState(null, '', url);
    let m;
    try { m = await get('/meetings/' + id); } catch (error) { drawerBody.replaceChildren(el('p', error.message, 'pl-drawer-error')); return; }
    if (drawerKey !== 'meeting:' + id) return;
    const s = m.metadata?.schedule || null;
    q('[data-pl-drawer-title]').textContent = m.title;
    q('[data-pl-drawer-kind]').textContent = s ? 'Reunião agendada' : 'Reunião importada';
    const event = m.event_activity_id ? await get('/activities/' + m.event_activity_id).catch(() => null) : null;
    const when = [m.meeting_date ? fullDate(m.meeting_date) : 'Data a confirmar', s?.time, s?.duration_minutes ? `${s.duration_minutes} min` : null].filter(Boolean).join(' · ');
    const place = s?.location ? (/^https?:\/\//i.test(s.location) ? link(s.location, s.location, true) : s.location) : null;
    const supplier = m.metadata?.supplier_id ? link(m.metadata.supplier_name || 'Abrir fornecedor', '/fornecedores?fornecedor=' + encodeURIComponent(m.metadata.supplier_id)) : (m.partner || null);
    const status = event ? (STATUS[event.status] === 'A fazer' ? 'Agendada' : STATUS[event.status]) : 'Registrada';
    const blocks = [section('Dados', facts([['Quando', when], ['Situação', status], ['Responsável', s?.responsible_user_id ? userName(s.responsible_user_id) : event ? userName(event.assignee_user_id) : null],
      ['Participantes', (s?.participants || []).join(', ') || (m.participants || []).map(p => p.display_name || p.name).join(', ') || null], ['Fornecedor', supplier], ['Local ou link', place], ['Observações', s?.notes || null]]))];
    if (event) blocks.push(scheduleEditor(m, event, s));
    const cards = el('div', null, 'pl-mini-list'); cards.append(el('div', 'Carregando cards…', 'prm-loading'));
    const reviewLink = el('button', 'Revisar em “Revisão de cards”', 'cc-btn'); reviewLink.type = 'button';
    reviewLink.addEventListener('click', () => { closeDrawer(); const url = new URL(location.href); url.searchParams.set('meeting', id); history.replaceState(null, '', url); setView('revisao'); document.dispatchEvent(new CustomEvent('prm:planner-refresh')); });
    blocks.push(section('Cards sugeridos', cards, reviewLink));
    if (event?.history?.length) blocks.push(section('Histórico', ...event.history.slice(0, 20).map(h => el('p', `${new Date(h.at).toLocaleString('pt-BR')} · ${h.reason}`, 'pl-history'))));
    blocks.push(section('Transcrição e análise', el('p', m.revisions.length ? 'Revisões da transcrição, análise com IA e evidências logo abaixo. A análise sugere cards, que você revisa antes de publicar.' : 'Depois da reunião, cole a transcrição, envie o TXT ou o áudio. Em seguida use “Analisar com Claude” para sugerir cards.', 'cc-caption'), transcriptForm(m)));
    drawerBody.replaceChildren(...blocks);
    get('/activities?meeting=' + encodeURIComponent(id) + '&limit=100').then(result => {
      const rows = result.items.filter(a => a.details?.planner_kind !== 'meeting');
      cards.replaceChildren(...(rows.length ? rows.map(a => { const b = el('button', null, 'pl-mini-item'); b.type = 'button'; b.append(el('span', a.title), chip(APPROVAL[a.approval] || a.approval, a.approval === 'published' ? 'is-ok' : 'is-info')); b.addEventListener('click', () => document.dispatchEvent(new CustomEvent('prm:open-activity', {detail: {id: a.id}}))); return b; }) : [el('p', 'Nenhum card ainda. Eles aparecem depois da análise da transcrição.', 'cc-caption')]));
    }).catch(error => cards.replaceChildren(el('p', error.message, 'cc-caption')));
    if (!renderedByMeetings) document.dispatchEvent(new CustomEvent('prm:open-meeting', {detail: {id}}));
    else meetingDetail.hidden = false;
  }
  function transcriptForm(m) {
    const box = el('details', null, 'pl-edit'); if (!m.revisions.length) box.open = true;
    box.append(el('summary', m.revisions.length ? 'Enviar nova transcrição' : 'Adicionar transcrição'));
    const form = el('form', null, 'pl-edit-form');
    const text = el('textarea'); text.name = 'text'; text.rows = 4; text.placeholder = 'Cole aqui a transcrição (00:00 - Nome, depois o texto)';
    const txt = el('input'); txt.type = 'file'; txt.name = 'txt'; txt.accept = '.txt,text/plain';
    const audio = el('input'); audio.type = 'file'; audio.name = 'audio'; audio.accept = '.wav,.mp3,.m4a,.flac,.ogg,.opus,.webm';
    const wrap = (label, input) => { const l = el('label', label); l.append(input); return l; };
    form.append(wrap('Transcrição colada', text), wrap('ou arquivo TXT (UTF-8)', txt), wrap('ou áudio', audio));
    const submit = el('button', 'Enviar', 'cc-btn cc-btn-primary'); submit.type = 'submit'; form.append(submit);
    const status = el('p', null, 'pl-edit-status'); status.setAttribute('role', 'status'); form.append(status);
    form.addEventListener('submit', async e => {
      e.preventDefault(); status.textContent = '';
      const chosen = [text.value.trim() ? 'text' : null, txt.files[0] ? 'txt' : null, audio.files[0] ? 'audio' : null].filter(Boolean);
      if (chosen.length !== 1) { status.textContent = 'Escolha uma entrada: texto colado, TXT ou áudio.'; return; }
      submit.disabled = true;
      try {
        if (chosen[0] === 'text') await send(`/meetings/${m.id}/transcripts`, 'POST', {text: text.value, reason: 'Transcrição enviada pelo Planner'});
        else { const data = new FormData(); data.set('file', txt.files[0] || audio.files[0]); await api(`/meetings/${m.id}/${chosen[0]}`, {method: 'POST', body: data}); }
        message(chosen[0] === 'audio' ? 'Áudio enviado. Use “Transcrever e analisar” na reunião.' : 'Transcrição salva. Use “Analisar com Claude” para sugerir cards.', 'success');
        await openMeetingDrawer(m.id);
      } catch (error) { status.textContent = error.message; } finally { submit.disabled = false; }
    });
    box.append(form);
    return box;
  }
  function scheduleEditor(m, event, s) {
    const box = el('details', null, 'pl-edit');
    box.append(el('summary', 'Editar ou reagendar'));
    const form = el('form', null, 'pl-edit-form');
    const field = (label, name, value, kind = 'input', extra = {}) => {
      const {options = [], ...props} = extra;  // "options" é somente leitura em <select>
      const wrap = el('label', label); const input = el(kind); input.name = name; Object.assign(input, props);
      if (kind === 'select') options.forEach(([v, t]) => input.add(new Option(t, v)));
      input.value = value ?? ''; wrap.append(input); form.append(wrap); return input;
    };
    field('Assunto', 'title', m.title, 'input', {required: true, minLength: 3, maxLength: 240});
    field('Data', 'date', m.meeting_date, 'input', {type: 'date', required: true});
    field('Hora', 'time', s?.time || '', 'input', {type: 'time'});
    field('Duração (min)', 'duration_minutes', s?.duration_minutes || '', 'input', {type: 'number', min: 5, max: 720, step: 5});
    field('Responsável', 'assignee_user_id', event.assignee_user_id, 'select', {options: users.map(u => [u.id, u.name])});
    field('Situação', 'status', ['done', 'cancelled'].includes(event.status) ? event.status : 'todo', 'select', {options: [['todo', 'Agendada'], ['done', 'Realizada'], ['cancelled', 'Cancelada']]});
    field('Participantes (um por linha)', 'participants', (s?.participants || []).join('\n'), 'textarea', {rows: 2});
    field('Local ou link', 'location', s?.location || '', 'input', {maxLength: 500});
    field('Observações', 'description', s?.notes || '', 'textarea', {rows: 2});
    field('Motivo da alteração', 'reason', '', 'input', {required: true, minLength: 3, placeholder: 'Ex.: fornecedor pediu para remarcar'});
    const save = el('button', 'Salvar alterações', 'cc-btn cc-btn-primary'); save.type = 'submit'; form.append(save);
    const status = el('p', null, 'pl-edit-status'); status.setAttribute('role', 'status'); form.append(status);
    form.addEventListener('submit', async e => {
      e.preventDefault(); if (!form.reportValidity()) return; save.disabled = true;
      const v = Object.fromEntries(new FormData(form));
      try {
        await send(`/meetings/${m.id}/schedule`, 'PATCH', {version: m.version, title: v.title, date: v.date, time: v.time || null,
          duration_minutes: v.duration_minutes ? Number(v.duration_minutes) : null, assignee_user_id: v.assignee_user_id || null, status: v.status,
          participants: splitList(v.participants), location: v.location, description: v.description, priority: event.details?.priority || 'normal', reason: v.reason});
        message('Reunião atualizada na agenda.', 'success'); await load(); await openMeetingDrawer(m.id);
      } catch (error) { status.textContent = error.message; } finally { save.disabled = false; }
    });
    box.append(form);
    return box;
  }
  function openSupplierDrawer(item) {
    openDrawer(item.source === 'supplier_next' ? 'Próxima ação do fornecedor' : 'Follow-up de fornecedor', item.title, item.key);
    const supplierLink = link(item.supplier_name || 'Abrir fornecedor', '/fornecedores?fornecedor=' + encodeURIComponent(item.supplier_id));
    const blocks = [section('Dados', facts([['Fornecedor', supplierLink], ['Prazo', item.date ? fullDate(item.date) : 'Sem prazo'], ['Responsável', userName(item.assignee_user_id)],
      ['Prioridade', PRIORITY[item.priority] || 'Normal'], ['Situação', isOpen(item) ? (late(item) ? 'Atrasado' : 'Em aberto') : 'Concluído'], ['Descrição', item.description || null]]))];
    const actions = el('div', null, 'pl-drawer-actions');
    if (item.source === 'supplier_task' && isOpen(item)) {
      const done = el('button', 'Concluir', 'cc-btn cc-btn-primary'); done.type = 'button';
      done.addEventListener('click', async () => {
        done.disabled = true;
        try {
          const t = item.task || {};
          await send(`/api/v1/fornecedores/${item.supplier_id}/tasks/${item.id}`, 'PUT', {title: t.title || item.title, description: t.description || '', assignee_user_id: item.assignee_user_id,
            due_date: t.due_date || null, priority: t.priority || 'normal', status: 'concluida'});
          message('Follow-up concluído.', 'success'); closeDrawer(); await load();
        } catch (error) { message(error.message, 'error'); done.disabled = false; }
      });
      actions.append(done);
    }
    actions.append(link('Abrir fornecedor', '/fornecedores?fornecedor=' + encodeURIComponent(item.supplier_id)));
    if (item.source === 'supplier_next') blocks.push(el('p', 'A próxima ação é editada e concluída na ficha do fornecedor.', 'cc-caption'));
    drawerBody.replaceChildren(...blocks, actions);
  }
  document.addEventListener('prm:meeting-opened', event => { if (drawerKey !== 'meeting:' + event.detail.id) openMeetingDrawer(event.detail.id, true).catch(error => message(error.message, 'error')); else meetingDetail.hidden = false; });
  document.addEventListener('prm:open-meeting-drawer', event => openMeetingDrawer(event.detail.id).catch(error => message(error.message, 'error')));
  document.addEventListener('prm:planner-changed', () => { schedule(); counters(); });

  /* ---------- Criação direta ---------- */
  const dialog = q('#pl-create'), form = q('[data-pl-create-form]');
  const splitList = value => String(value || '').split(/[\n;,]+/).map(v => v.trim()).filter(Boolean).slice(0, 30);
  function applyType() {
    const kind = form.elements.type.value;
    qa('[data-pl-only]', form).forEach(node => { node.hidden = node.dataset.plOnly !== kind; });
    q('[data-pl-type-hint]', form).textContent = HINT[kind];
    q('[data-pl-create-title]', form).textContent = {task: 'Nova tarefa', meeting: 'Nova reunião', card: 'Novo card', followup: 'Novo follow-up'}[kind];
    q('[data-pl-create-submit]', form).textContent = {task: 'Criar tarefa', meeting: 'Agendar reunião', card: 'Criar card', followup: 'Criar follow-up'}[kind];
    q('[data-pl-title-label]', form).textContent = kind === 'meeting' ? 'Assunto' : 'Título';
    q('[data-pl-notes-label]', form).textContent = kind === 'meeting' ? 'Observações' : 'Descrição';
    q('[data-pl-supplier-label]', form).replaceChildren(document.createTextNode('Fornecedor '), el('small', kind === 'followup' ? 'obrigatório' : 'opcional'));
    form.elements.supplier_id.required = kind === 'followup';
    form.elements.date.required = kind === 'meeting';
  }
  function openCreate(kind = 'task', preset = {}) {
    q('.pl-new')?.removeAttribute('open');
    form.reset(); q('[data-pl-create-error]', form).textContent = '';
    form.elements.type.value = kind;
    form.elements.date.value = kind === 'card' ? '' : today;
    if (preset.supplier || filters.elements.supplier.value) form.elements.supplier_id.value = preset.supplier || filters.elements.supplier.value;
    applyType(); dialog.showModal(); form.elements.title.focus();
  }
  qa('[data-pl-new]').forEach(b => b.addEventListener('click', () => openCreate(b.dataset.plNew)));
  qa('input[name=type]', form).forEach(input => input.addEventListener('change', applyType));
  q('[data-pl-create-close]', form).addEventListener('click', () => window.PRM?.sheet ? window.PRM.sheet.requestClose(dialog) : dialog.close());
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const error = q('[data-pl-create-error]', form), submit = q('[data-pl-create-submit]', form), v = Object.fromEntries(new FormData(form)), kind = v.type;
    error.textContent = '';
    if (!v.title || v.title.trim().length < 3) { error.textContent = 'Informe um título com pelo menos 3 caracteres.'; return; }
    if (kind === 'meeting' && !v.date) { error.textContent = 'Reunião precisa de data.'; return; }
    if (kind === 'followup' && !v.supplier_id) { error.textContent = 'Escolha o fornecedor do follow-up.'; return; }
    if (kind === 'task' && !v.date && !form.elements.no_deadline_accepted.checked) { error.textContent = 'Informe a data ou marque “Sem prazo”.'; return; }
    if (v.time && !v.date) { error.textContent = 'Horário exige data.'; return; }
    submit.disabled = true; submit.setAttribute('aria-busy', 'true'); form.setAttribute('aria-busy', 'true');
    try {
      const result = await send('/items', 'POST', {type: kind, title: v.title.trim(), description: v.description || '', assignee_user_id: v.assignee_user_id || null,
        supplier_id: v.supplier_id || null, priority: v.priority || 'normal', date: v.date || null, time: v.time || null,
        duration_minutes: kind === 'meeting' && v.time ? Number(v.duration_minutes) : null, participants: kind === 'meeting' ? splitList(v.participants) : [],
        location: kind === 'meeting' ? v.location || '' : '', no_deadline_accepted: kind === 'task' && form.elements.no_deadline_accepted.checked});
      dialog.close();
      message(kind === 'card' ? 'Card criado. Ele está em “Revisão de cards” até ser publicado.' : `${TYPE[kind]} criada. Já aparece na agenda.`.replace('Follow-up criada', 'Follow-up criado'), 'success');
      if (v.date && (v.date < range[0] || v.date >= range[1]) && filters.elements.period.value === 'month') month = v.date.slice(0, 7);
      await load(); counters(); document.dispatchEvent(new CustomEvent('prm:planner-refresh'));
      if (kind === 'meeting' && result.meeting_id) openMeetingDrawer(result.meeting_id).catch(() => {});
    } catch (e) { error.textContent = e.message; error.scrollIntoView({block: 'nearest'}); } finally { submit.disabled = false; submit.removeAttribute('aria-busy'); form.removeAttribute('aria-busy'); }
  });

  /* ---------- Contadores, indicadores e dados de apoio ---------- */
  async function counters() {
    const [summary, alerts, overview] = await Promise.allSettled([get('/summary'), get('/alerts'), get('/activities/overview')]);
    const review = q('[data-pl-review-count]');
    if (summary.status === 'fulfilled') { review.textContent = summary.value.cards_review; review.hidden = !summary.value.cards_review; }
    const alertCount = q('[data-pl-alert-count]');
    if (alerts.status === 'fulfilled') { const unread = alerts.value.items.filter(a => !a.read_at).length; alertCount.textContent = unread; alertCount.hidden = !unread; }
    if (overview.status === 'fulfilled') {
      const o = overview.value;
      q('[data-pl-bands]').replaceChildren(...Object.entries(o.bands).map(([key, value]) => { const box = el('div', null, 'mt-deadline'); box.dataset.band = key; box.append(el('span', BANDS[key] || key), el('strong', String(value.count)), el('small', value.percent.toLocaleString('pt-BR') + '%')); return box; }));
      q('[data-pl-bands-scope]').textContent = `${o.denominator} tarefas abertas com prazo · ${o.no_deadline} sem prazo aceito · ${o.unconfirmed} com prazo a confirmar`;
    }
  }
  async function init() {
    const params = new URLSearchParams(location.search);
    setView(params.get('view') || 'agenda', false);
    if (/^supplier_[a-z_]+$/.test(params.get('source') || '')) source = params.get('source');
    if (TYPE[params.get('type')]) { type = params.get('type'); qa('[data-pl-type]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.plType === type))); }
    if (['today', 'week', 'month'].includes(params.get('period'))) filters.elements.period.value = params.get('period');
    if (/^\d{4}-\d{2}$/.test(params.get('month') || '')) month = params.get('month');
    const [people, supplierList] = await Promise.allSettled([get('/users'), get('/api/v1/fornecedores')]);
    if (people.status === 'fulfilled') users = people.value.items;
    if (supplierList.status === 'fulfilled') {
      suppliers = supplierList.value.items.map(s => ({id: s.id, name: s.name})).sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
      qa('[data-pl-suppliers]').forEach(select => { const first = select.options[0]; select.replaceChildren(first); suppliers.forEach(s => select.add(new Option(s.name, s.id))); });
    }
    if (params.get('supplier')) filters.elements.supplier.value = params.get('supplier');
    if (params.get('mine') === '1' && people.status === 'fulfilled') { const me = people.value.current_user_id; const select = filters.elements.assignee; if (![...select.options].some(o => o.value === me)) select.add(new Option(userName(me), me)); select.value = me; }
    await load();
    counters().catch(() => {});
    if (params.get('due') === 'overdue') q('[data-pl-group="late"]')?.scrollIntoView({block: 'start'});
    if (params.get('meeting')) openMeetingDrawer(params.get('meeting')).catch(error => message(error.message, 'error'));
    if (TYPE[params.get('new')]) openCreate(params.get('new'), {supplier: params.get('supplier')});
  }
  init().catch(error => message(error.message, 'error'));
})();
