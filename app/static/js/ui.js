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
