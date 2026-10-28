// Dashboard: resumo a partir de endpoints de leitura existentes. Nenhuma escrita; dados renderizados como texto.
(() => {
  "use strict";
  const root = document.querySelector("[data-overview]");
  if (!root) return;
  const get = url => fetch(url, {credentials: "same-origin", cache: "no-store"}).then(r => r.ok ? r.json() : Promise.reject(r.status));
  const el = (tag, text, className) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (className) n.className = className; return n; };
  const now = Date.now();
  const when = value => {
    const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const diff = Math.round((now - date.getTime()) / 60000);
    if (diff >= 0 && diff < 60) return diff <= 1 ? "agora" : `há ${diff} min`;
    if (diff >= 0 && diff < 1440) return `há ${Math.round(diff / 60)} h`;
    return date.toLocaleDateString("pt-BR", {day: "2-digit", month: "short"}).replace(".", "");
  };
  const COMPANY = {choice: "Choice", sag: "SAG", portwell: "Portwell"};
  const REMOVAL_MODE = {main: "foto principal", gallery: "galeria", documents: "documentos", all: "tudo"};
  const RUN_STATUS = {draft: ["Rascunho", ""], approved: ["Aprovado", "is-info"], validated: ["Validado", "is-ok"]};
  const block = name => root.querySelector(`[data-overview-block="${name}"] [data-body]`);
  const empty = (target, text, action) => {
    const box = el("div", null, "prm-empty"); box.append(el("p", text));
    if (action) { const a = el("a", action[0], "prm-btn prm-btn-sm"); a.href = action[1]; box.append(a); }
    target.replaceChildren(box);
  };
  const hide = name => root.querySelector(`[data-overview-block="${name}"]`)?.setAttribute("hidden", "");
  const list = rows => {
    const ul = el("ul", null, "prm-overview-list");
    rows.forEach(({badge, badgeClass, title, meta, href}) => {
      const li = el("li"), main = href ? el("a", title) : el("span", title);
      if (href) main.href = href;
      if (badge) li.append(el("span", badge, "prm-badge " + (badgeClass || "")));
      li.append(main); if (meta) li.append(el("small", meta)); ul.append(li);
    });
    return ul;
  };
  const kpis = root.querySelector("[data-overview-kpis]");
  const kpi = (index, value, detail, href, tone) => {
    const tile = kpis.children[index]; if (!tile) return;
    const card = href ? el("a", null, "prm-kpi") : el("div", null, "prm-kpi");
    if (href) card.href = href;
    if (tone) card.classList.add(tone);
    card.append(el("span", tile.querySelector("span").textContent), el("strong", value), el("small", detail || " "));
    tile.replaceWith(card);
  };

  Promise.allSettled([
    get("/api/v1/planner/activities/overview"), get("/api/v1/planner/alerts"), get("/api/v1/fornecedores"),
    get("/api/v1/fornecedores/config"), get("/api/v1/operations/overview"), get("/api/v1/cadastro-api"),
    get("/api/v1/remocao-arquivos"), get("/api/v1/planner/summary"),
  ]).then(([planner, alerts, suppliers, supplierConfig, operations, registrations, removals, execution]) => {
    const value = result => result.status === "fulfilled" ? result.value : null;
    const [p, a, s, sc, o, r, m, ex] = [planner, alerts, suppliers, supplierConfig, operations, registrations, removals, execution].map(value);

    // Indicadores
    if (p) kpi(0, String(p.denominator), p.bands.overdue.count ? `${p.bands.overdue.count} vencida(s)` : "Nenhuma vencida", "/planner", p.bands.overdue.count ? "is-alert" : "");
    else kpi(0, "—", "Sem acesso", null);
    const alertItems = a ? a.items : [];
    if (a) kpi(1, String(alertItems.length), alertItems.length ? `${alertItems.filter(x => !x.read_at).length} não lido(s)` : "Nada pendente", "/alertas", alertItems.length ? "is-warn" : "");
    else kpi(1, "—", "Sem acesso", null);
    const today = new Date().toISOString().slice(0, 10);
    const supplierItems = s ? s.items : [];
    const overdue = supplierItems.filter(x => x.data?.next_action_date && x.data.next_action_date < today).length;
    if (s) kpi(2, String(supplierItems.length), overdue ? `${overdue} follow-up(s) vencido(s)` : "Follow-ups em dia", "/fornecedores", overdue ? "is-warn" : "");
    else kpi(2, "—", "Sem acesso", null);
    const runs = o && Array.isArray(o.items) ? o.items : [];
    if (o) kpi(3, String(runs.length), runs.length ? `${runs.filter(x => x.status === "validated").length} validada(s)` : "Nenhuma execução registrada", "/digitalizacao");
    else kpi(3, "—", "Sem acesso", null);
    const weekAgo = now / 1000 - 7 * 86400;
    const regWeek = (r ? r.items : []).filter(x => x.created >= weekAgo).length, remWeek = (m ? m.items : []).filter(x => x.created >= weekAgo).length;
    if (r || m) kpi(4, String(regWeek + remWeek), `cadastro ${regWeek} · remoção ${remWeek}`, "/digitalizacao/cadastro-api");
    else kpi(4, "—", "Sem acesso", null);

    // Atividades recentes: lotes de cadastro e remoção, execuções e reuniões, do mais novo ao mais antigo.
    const recent = [
      ...(r ? r.items : []).map(x => ({at: x.created * 1000, badge: "Cadastro", badgeClass: "is-info", title: `${COMPANY[x.company] || x.company} · lote de arquivos`, href: `/digitalizacao/cadastro-api?lote=${encodeURIComponent(x.id)}`})),
      ...(m ? m.items : []).map(x => ({at: x.created * 1000, badge: "Remoção", badgeClass: "is-warn", title: `${COMPANY[x.company] || x.company} · ${REMOVAL_MODE[x.mode] || x.mode}`, href: `/digitalizacao/remocao-arquivos?lote=${encodeURIComponent(x.id)}`})),
      ...runs.map(x => ({at: Date.parse(x.created_at), badge: "Digitalização", badgeClass: "", title: x.name || x.sku || "Execução", href: "/digitalizacao"})),
    ].filter(x => !Number.isNaN(x.at)).sort((x, y) => y.at - x.at).slice(0, 6).map(x => ({...x, meta: when(x.at / 1000)}));
    if (!r && !m && !o) hide("recent");
    else if (recent.length) block("recent").replaceChildren(list(recent));
    else empty(block("recent"), "Nenhuma atividade recente.");

    // Fornecedores por etapa
    if (!s) hide("suppliers");
    else if (!supplierItems.length) empty(block("suppliers"), "Nenhum fornecedor cadastrado.", ["Criar fornecedor", "/fornecedores"]);
    else {
      const stages = sc?.stages || {}, counts = {};
      supplierItems.forEach(x => { counts[x.stage] = (counts[x.stage] || 0) + 1; });
      const max = Math.max(...Object.values(counts));
      const bars = el("ul", null, "prm-overview-bars");
      Object.entries(stages).filter(([key]) => counts[key]).forEach(([key, label]) => {
        const li = el("li"), bar = el("span", null, "prm-overview-bar"), fill = el("i");
        fill.style.width = `${Math.max(8, Math.round(100 * counts[key] / max))}%`; bar.append(fill);
        li.append(el("span", label), bar, el("strong", String(counts[key]))); bars.append(li);
      });
      const noAction = supplierItems.filter(x => !x.data?.next_action).length;
      const foot = el("p", `${noAction} sem próxima ação · ${overdue} com follow-up vencido`, "prm-overview-muted");
      block("suppliers").replaceChildren(bars, foot);
    }

    // Execução no Planner: cada número abre o Planner já filtrado.
    if (!ex) hide("execution");
    else {
      const grid = el("div", null, "prm-exec-grid");
      const source = key => "/planner?source=" + encodeURIComponent((ex.filters || {})[key] || "");
      [["Reuniões hoje", ex.meetings_today, "/planner?type=meeting&period=today", ""],
       ["Tarefas vencidas", ex.overdue_tasks, "/planner?type=task&due=overdue", "is-alert"],
       ["Cards para revisar", ex.cards_review, "/planner?view=revisao", "is-warn"],
       ["Follow-ups vencidos", ex.followups_overdue ?? ex.followups, "/planner?type=followup&due=overdue", "is-alert"],
       ["Follow-ups de hoje", ex.followups_today ?? 0, "/planner?type=followup&period=today", "is-warn"],
       ["Fornecedores sem interação", ex.suppliers_inactive ?? 0, source("suppliers_inactive"), "is-warn"],
       ["Quentes sem próxima ação", ex.hot_no_next ?? 0, source("hot_no_next"), "is-alert"]].forEach(([label, count, href, tone]) => {
        const a = el("a", null, "prm-exec-tile" + (count && tone ? " " + tone : "")); a.href = href;
        a.append(el("strong", String(count)), el("span", label)); grid.append(a);
      });
      const foot = el("p", "Inclui os follow-ups automáticos dos fornecedores.", "prm-overview-muted");
      block("execution").replaceChildren(grid, foot);
    }

    // Alertas
    if (!a) hide("alerts");
    else if (!alertItems.length) empty(block("alerts"), "Nenhum alerta pendente.");
    else block("alerts").replaceChildren(list(alertItems.slice(0, 5).map(x => ({badge: x.read_at ? "Lido" : "Novo", badgeClass: x.read_at ? "" : "is-warn", title: x.title, meta: x.due_date ? `prazo ${new Date(x.due_date + "T12:00:00").toLocaleDateString("pt-BR")}` : "", href: "/alertas"}))));

    // Digitalização
    if (!o) hide("digitalization");
    else {
      const body = block("digitalization"), parts = [];
      if (runs.length) parts.push(list(runs.slice(0, 3).map(x => ({badge: (RUN_STATUS[x.status] || [x.status])[0], badgeClass: (RUN_STATUS[x.status] || [])[1], title: x.name || x.sku, meta: `${COMPANY[x.company] || x.company} · ${when(x.created_at)}`, href: "/digitalizacao"}))));
      else { const box = el("div", null, "prm-empty"); box.append(el("p", o.status === "storage_misconfigured" ? "Armazenamento da digitalização não configurado." : "Nenhuma execução registrada.")); parts.push(box); }
      const links = el("p", null, "prm-overview-links");
      [["Resolução de imagens", "/digitalizacao/resolucao-imagens"], ["Cadastro via API", "/digitalizacao/cadastro-api"], ["Remoção", "/digitalizacao/remocao-arquivos"]].forEach(([t, h]) => { const x = el("a", t); x.href = h; links.append(x); });
      body.replaceChildren(...parts, links);
    }
  });
})();
