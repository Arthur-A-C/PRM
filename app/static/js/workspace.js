/* Shell compartilhado: relógio operacional, contexto da Digitalização e menu.
   Somente apresentação; sem gravações, credenciais ou requisições externas. */
(() => {
  'use strict';

  /* Operational Clock — horário de Brasília, alinhado ao segundo, sem layout shift
     (dígitos tabulares e largura fixa). Pausa com a aba oculta. */
  const clock = document.querySelector('[data-workspace-clock]');
  if (clock) {
    const hm = clock.querySelector('[data-clock-hm]');
    const sec = clock.querySelector('[data-clock-s]');
    const dateLabel = document.querySelector('[data-workspace-date]');
    const zone = 'America/Sao_Paulo';
    const parts = new Intl.DateTimeFormat('pt-BR', { timeZone: zone, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
    const weekday = new Intl.DateTimeFormat('pt-BR', { timeZone: zone, weekday: 'long' });
    const day = new Intl.DateTimeFormat('pt-BR', { timeZone: zone, day: '2-digit', month: 'short', year: 'numeric' });
    let timer = null;
    let lastMinute = '';
    let lastDate = '';
    const tick = () => {
      const now = new Date();
      const p = Object.fromEntries(parts.formatToParts(now).map(part => [part.type, part.value]));
      const minute = `${p.hour}:${p.minute}`;
      clock.dateTime = now.toISOString();
      if (hm && minute !== lastMinute) { hm.textContent = minute; lastMinute = minute; }
      if (sec) sec.textContent = ':' + p.second;
      if (!hm) clock.textContent = `${minute}:${p.second}`;
      const date = `${weekday.format(now)} · ${day.format(now).replace(/\./g, '').replace(/ de /g, ' ')}`.toUpperCase();
      if (dateLabel && date !== lastDate) { dateLabel.textContent = date; lastDate = date; }
    };
    const stop = () => { if (timer) { clearTimeout(timer); timer = null; } };
    const schedule = () => { stop(); tick(); timer = window.setTimeout(schedule, 1000 - (Date.now() % 1000) + 5); };
    schedule();
    document.addEventListener('visibilitychange', () => (document.hidden ? stop() : schedule()));
    window.addEventListener('pagehide', stop);
  }

  const inspector = document.querySelector('[data-workspace-inspector]');
  inspector?.addEventListener('click', () => {
    const space = document.querySelector('.digitalizacao-workspace');
    const hidden = space.classList.toggle('context-is-hidden');
    inspector.setAttribute('aria-expanded', String(!hidden));
    inspector.textContent = hidden ? 'Mostrar contexto do produto' : 'Recolher contexto do produto';
  });
  // Enhanced mobile menu: make the opened navigation immediately keyboard reachable.
  const menu = document.querySelector('[data-prm-nav-toggle]');
  menu?.addEventListener('click', () => {
    if (document.body.classList.contains('nav-open')) document.querySelector('.sidebar nav a')?.focus();
  });
  document.querySelector('.sidebar')?.addEventListener('keydown', event => {
    if (event.key === 'Escape' && matchMedia('(max-width: 600px)').matches) menu?.focus();
  });
})();
