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
