(() => {
  "use strict";

  const navToggle = document.querySelector("[data-prm-nav-toggle]");
  const sidebar = document.querySelector(".sidebar");
  const closeNav = () => {
    document.body.classList.remove("nav-open");
    navToggle?.setAttribute("aria-expanded", "false");
    navToggle?.setAttribute("aria-label", "Abrir menu");
  };

  navToggle?.addEventListener("click", () => {
    const open = !document.body.classList.contains("nav-open");
    document.body.classList.toggle("nav-open", open);
    navToggle.setAttribute("aria-expanded", String(open));
    navToggle.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
  });
  document.addEventListener("click", (event) => {
    if (document.body.classList.contains("nav-open") &&
        !sidebar?.contains(event.target) && !navToggle?.contains(event.target)) closeNav();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeNav();
  });
  window.matchMedia("(min-width: 601px)").addEventListener("change", closeNav);

  const themeButtons = Array.from(document.querySelectorAll("[data-prm-theme-toggle]"));
  const refreshThemeLabels = () => {
    const dark = document.documentElement.dataset.theme === "dark";
    themeButtons.forEach((button) => {
      button.setAttribute("aria-label", dark ? "Ativar tema claro" : "Ativar tema escuro");
      button.setAttribute("aria-pressed", String(dark));
      const label = button.querySelector("[data-prm-theme-label]");
      if (label) label.textContent = dark ? "Tema claro" : "Tema escuro";
    });
  };
  themeButtons.forEach((button) => button.addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("prm-theme", theme); } catch (_) { /* preferência opcional */ }
    refreshThemeLabels();
  }));
  refreshThemeLabels();

  const compact = document.querySelector("[data-prm-sidebar-compact]");
  const shell = document.querySelector(".app-shell");
  const refreshCompact = () => {
    const isCompact = Boolean(shell?.classList.contains("sidebar-is-compact"));
    compact?.setAttribute("aria-expanded", String(!isCompact));
    compact?.setAttribute("aria-label", isCompact ? "Expandir navegação" : "Recolher navegação");
    const label = compact?.querySelector(".sidebar-compact-label");
    if (label) label.textContent = isCompact ? "Expandir" : "Recolher";
  };
  try { if (localStorage.getItem("prm-sidebar") === "compact") shell?.classList.add("sidebar-is-compact"); } catch (_) { /* preferência opcional */ }
  compact?.addEventListener("click", () => {
    const isCompact = shell.classList.toggle("sidebar-is-compact");
    try { localStorage.setItem("prm-sidebar", isCompact ? "compact" : "expanded"); } catch (_) { /* preferência opcional */ }
    refreshCompact();
  });
  refreshCompact();

  const company = document.getElementById("digitalizacao-empresa");
  const cards = Array.from(document.querySelectorAll("[data-company-select]"));
  if (company && cards.length) {
    const updateCards = () => cards.forEach((card) => {
      card.setAttribute("aria-pressed", String(card.dataset.companySelect === company.value));
    });
    cards.forEach((card) => card.addEventListener("click", () => {
      company.value = card.dataset.companySelect;
      company.dispatchEvent(new Event("change", { bubbles: true }));
      updateCards();
    }));
    company.addEventListener("change", updateCards);
    updateCards();
  }
})();

// Feedback compartilhado do design system: PRM.toast(mensagem, tipo) e PRM.busy(botão, rótulo).
// Tipos: "success" | "info" | "warning" | "error". Mensagens são texto (nunca HTML).
(() => {
  "use strict";
  const PRM = window.PRM = window.PRM || {};
  let region = null;
  const icons = { success: "M20 6 9 17l-5-5", error: "M12 8v5m0 3h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
                  warning: "M12 8v5m0 3h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z", info: "M12 16v-4m0-4h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z" };
  PRM.toast = (message, kind = "info", { timeout = kind === "error" ? 9000 : 4500 } = {}) => {
    if (!message) return null;
    if (!region) {
      region = document.createElement("div");
      region.className = "prm-toasts";
      region.setAttribute("role", "status");
      region.setAttribute("aria-live", "polite");
      document.body.append(region);
    }
    const item = document.createElement("div");
    item.className = `prm-toast is-${icons[kind] ? kind : "info"}`;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("fill", "none"); svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2"); svg.setAttribute("stroke-linecap", "round"); svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path"); path.setAttribute("d", icons[kind] || icons.info); svg.append(path);
    const text = document.createElement("span"); text.textContent = String(message);
    const close = document.createElement("button"); close.type = "button"; close.className = "prm-toast-close"; close.textContent = "×"; close.setAttribute("aria-label", "Fechar aviso");
    item.append(svg, text, close);
    const leave = () => { item.classList.add("is-leaving"); setTimeout(() => item.remove(), 220); };
    close.addEventListener("click", leave);
    region.append(item);
    if (timeout) setTimeout(leave, timeout);
    return item;
  };
  // Marca um botão como ocupado (desabilitado, spinner, rótulo temporário) e devolve a função que o restaura.
  PRM.busy = (button, label = "Processando…") => {
    if (!button) return () => {};
    const previous = { html: button.innerHTML, disabled: button.disabled };
    button.disabled = true; button.setAttribute("aria-busy", "true");
    const span = button.querySelector("span"); if (span) span.textContent = label; else button.textContent = label;
    return () => { button.innerHTML = previous.html; button.disabled = previous.disabled; button.removeAttribute("aria-busy"); };
  };
  // Envio nativo (página recarrega): o botão mostra "Enviando…" e fica bloqueado contra duplo clique.
  // Formulários tratados por JS chamam preventDefault e não são tocados.
  document.addEventListener("submit", (event) => {
    const form = event.target;
    setTimeout(() => {
      if (event.defaultPrevented || !(form instanceof HTMLFormElement) || form.dataset.prmNoBusy !== undefined) return;
      if (form.method === "dialog" || (form.target && form.target !== "_self")) return;  // não navega: nada a bloquear
      const button = event.submitter || form.querySelector('button[type="submit"], button:not([type])');
      const restore = PRM.busy(button, form.method.toLowerCase() === "get" ? "Carregando…" : "Enviando…");
      window.addEventListener("pageshow", restore, {once: true});  // volta pelo histórico: botão liberado
    }, 0);
  });
})();

// Painel lateral de formulário (<dialog class="prm-sheet">), no padrão do drawer de fornecedores.
// O <dialog> nativo já dá ESC, foco preso e camada superior; aqui entram clique fora, foco no primeiro campo e retorno
// do foco, botões [data-sheet-close], proteção contra fechar durante envio ([aria-busy]) ou com alterações não salvas,
// e PRM.sheet.confirm / ask / form, que substituem confirm()/prompt() por confirmações compactas ou painéis.
(() => {
  "use strict";
  const PRM = window.PRM = window.PRM || {};
  const FIELD = 'input:not([type="hidden"]):not([disabled]):not([type="radio"]), select:not([disabled]), textarea:not([disabled])';
  const outside = (dialog, event) => {
    const box = dialog.getBoundingClientRect();
    return event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom;
  };
  // Últimos elementos focados fora dos painéis: o foco volta para quem abriu (o showModal já move o foco antes de sabermos).
  const recent = [];
  document.addEventListener("focusin", event => { recent.unshift(event.target); recent.length = Math.min(recent.length, 8); }, true);
  const busy = dialog => dialog.matches('[aria-busy="true"]') || Boolean(dialog.querySelector('[aria-busy="true"]'));
  const focusFirst = dialog => {
    const body = dialog.querySelector(".prm-sheet-body");
    const target = dialog.querySelector("[autofocus]") || body?.querySelector(FIELD);
    if (target && !body?.contains(document.activeElement)) target.focus({preventScroll: true});
  };
  // Fechamento pedido pela pessoa (ESC, clique fora, ×, Cancelar): respeita envio em andamento e alterações não salvas.
  const requestClose = async (dialog, reason = "cancel") => {
    if (!dialog.open || busy(dialog)) return false;
    if (dialog.dataset.sheetDirty === "1" && dialog.dataset.sheetGuard !== "off") {
      const discard = await PRM.sheet.confirm({title: "Descartar alterações?", text: "O que foi preenchido neste painel ainda não foi salvo.", confirm: "Descartar", danger: true});
      if (!discard) return false;
    }
    dialog.close(reason);
    return true;
  };
  const watch = dialog => {
    if (dialog.dataset.sheetReady) return;
    dialog.dataset.sheetReady = "1";
    let opener = null;
    new MutationObserver(() => {
      if (!dialog.open) return;
      opener = recent.find(element => element !== document.body && element.isConnected && !dialog.contains(element)) || opener;
      dialog.dataset.sheetDirty = "";
      requestAnimationFrame(() => focusFirst(dialog));
    }).observe(dialog, {attributes: true, attributeFilter: ["open"]});
    dialog.addEventListener("close", () => {  // devolve o foco a quem abriu, se ele ainda existir
      if (!opener || !opener.isConnected || !(document.activeElement === document.body || dialog.contains(document.activeElement))) return;
      opener.focus({preventScroll: true});
      // Item de menu que se fechou ao abrir o painel: o foco vai para o resumo do menu.
      if (document.activeElement !== opener) opener.closest("details")?.querySelector(":scope > summary")?.focus({preventScroll: true});
    });
    ["input", "change"].forEach(type => dialog.addEventListener(type, event => { if (event.isTrusted && event.target.closest?.("form")) dialog.dataset.sheetDirty = "1"; }));
    dialog.addEventListener("submit", () => { dialog.dataset.sheetDirty = ""; }, true);  // salvar = intenção registrada
    // ESC tratado na tecla: o navegador nem sempre deixa cancelar o evento "cancel" sem interação recente.
    dialog.addEventListener("keydown", event => { if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); event.stopPropagation(); requestClose(dialog); } });
    dialog.addEventListener("cancel", event => { event.preventDefault(); requestClose(dialog); });  // outros pedidos de fechamento
    let pressedOutside = false;  // só fecha se o clique começou e terminou fora (seleção de texto não fecha)
    dialog.addEventListener("mousedown", event => { pressedOutside = event.target === dialog && outside(dialog, event); });
    dialog.addEventListener("click", event => {
      if (event.target === dialog && pressedOutside && outside(dialog, event)) requestClose(dialog, "backdrop");
      else if (event.target.closest("[data-sheet-close]")) { event.preventDefault(); requestClose(dialog); }
    });
  };

  // Confirmação/motivo/formulário curto. Compacto por padrão (cartão no canto direito); size: "panel" usa o painel inteiro.
  let promptDialog = null;
  const build = () => {
    promptDialog = document.createElement("dialog");
    promptDialog.className = "prm-sheet prm-sheet-ask";
    promptDialog.setAttribute("aria-labelledby", "prm-ask-title");
    promptDialog.dataset.sheetGuard = "off";
    promptDialog.innerHTML = '<form class="prm-sheet-frame prm-ui" novalidate><header class="prm-sheet-head"><div><p class="prm-sheet-kicker" data-ask-kicker></p>'
      + '<h2 id="prm-ask-title" data-ask-title></h2><p class="prm-sheet-sub" data-ask-sub></p></div>'
      + '<button type="button" class="prm-sheet-close" data-sheet-close aria-label="Fechar">×</button></header>'
      + '<div class="prm-sheet-body"><p data-ask-text></p><dl class="prm-sheet-facts" data-ask-details></dl><ul class="prm-sheet-warnings" data-ask-warnings></ul>'
      + '<div class="prm-sheet-fields" data-ask-fields></div><p class="prm-sheet-error" role="alert" data-ask-error></p></div>'
      + '<footer class="prm-sheet-foot"><button type="button" class="button-secondary" data-sheet-close>Cancelar</button><button type="submit" class="button-primary" data-ask-ok>Confirmar</button></footer></form>';
    document.body.append(promptDialog);
    watch(promptDialog);
  };
  const open = ({title, text = "", subtitle = "", kicker = "", details = [], warnings = [], fields = [], confirm = "Confirmar", danger = false, size = "compact"}) => {
    if (!promptDialog) build();
    const q = selector => promptDialog.querySelector(selector), set = (selector, value) => { q(selector).textContent = value; q(selector).hidden = !value; };
    set("[data-ask-title]", title); set("[data-ask-sub]", subtitle); set("[data-ask-kicker]", kicker || (danger ? "Atenção" : "")); set("[data-ask-text]", text);
    const facts = q("[data-ask-details]"); facts.replaceChildren();
    details.filter(([, value]) => value !== null && value !== undefined && value !== "").forEach(([label, value]) => {
      const row = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = label; dd.textContent = String(value); row.append(dt, dd); facts.append(row);
    });
    facts.hidden = !facts.children.length;
    const notes = q("[data-ask-warnings]"); notes.replaceChildren(...warnings.filter(Boolean).map(text => { const li = document.createElement("li"); li.textContent = text; return li; }));
    notes.hidden = !notes.children.length;
    const host = q("[data-ask-fields]"); host.replaceChildren();
    const inputs = fields.map(spec => {
      const label = document.createElement("label"), caption = document.createElement("span"), input = document.createElement(spec.type === "textarea" ? "textarea" : "input");
      caption.textContent = spec.label + (spec.required ? "" : " (opcional)");
      input.name = spec.name; input.value = spec.value || ""; if (spec.type && spec.type !== "textarea") input.type = spec.type;
      if (spec.type === "textarea") input.rows = spec.rows || 4; if (spec.placeholder) input.placeholder = spec.placeholder;
      input.maxLength = spec.max || 1000; input.autocomplete = "off";
      const error = document.createElement("small"); error.className = "prm-field-error"; error.setAttribute("aria-live", "polite");
      label.append(caption, input, error); host.append(label);
      return {spec, input, error};
    });
    host.hidden = !inputs.length;
    q("[data-ask-error]").textContent = ""; q("[data-ask-ok]").textContent = confirm;
    q("[data-ask-ok]").classList.toggle("prm-btn-danger", danger);
    promptDialog.classList.toggle("is-danger", danger);
    promptDialog.classList.toggle("is-compact", size === "compact");
    promptDialog.classList.toggle("is-narrow", size !== "compact");
    promptDialog.returnValue = "";
    return new Promise(resolve => {
      const form = q("form");
      const finish = result => { form.removeEventListener("submit", submit); promptDialog.removeEventListener("close", closed); resolve(result); };
      const submit = event => {
        event.preventDefault();
        let first = null;
        inputs.forEach(({spec, input, error}) => {
          const value = input.value.trim(), min = spec.min ?? (spec.required ? 1 : 0);
          const problem = spec.required && value.length < Math.max(min, 1) ? (min > 1 ? `Informe pelo menos ${min} caracteres.` : "Campo obrigatório.")
            : spec.type === "url" && value && !/^https?:\/\/\S+\.\S+/.test(value) ? "Use um endereço completo, com http:// ou https://." : "";
          error.textContent = problem; input.setAttribute("aria-invalid", String(Boolean(problem)));
          if (problem && !first) first = input;
        });
        if (first) { first.focus(); return; }
        promptDialog.close("ok");
        finish(inputs.length ? Object.fromEntries(inputs.map(({spec, input}) => [spec.name, input.value.trim()])) : true);
      };
      const closed = () => { if (promptDialog.returnValue !== "ok") finish(inputs.length ? null : false); };
      form.addEventListener("submit", submit);
      promptDialog.addEventListener("close", closed);
      promptDialog.showModal();
      if (!inputs.length) requestAnimationFrame(() => q("[data-ask-ok]").focus());
    });
  };
  PRM.sheet = {
    enhance: (root = document) => root.querySelectorAll("dialog.prm-sheet").forEach(watch),
    requestClose,                                                               // fechar como se fosse a pessoa (com as proteções)
    confirm: options => open(options),                                          // true/false
    form: options => open(options),                                             // {campo: valor} ou null
    ask: ({label, min = 3, ...options}) => open({...options, fields: [{name: "value", label, type: "textarea", required: true, min}]})
      .then(values => values ? values.value : null),                            // texto ou null
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => PRM.sheet.enhance());
  else PRM.sheet.enhance();
})();
