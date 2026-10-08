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
