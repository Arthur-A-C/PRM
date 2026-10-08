(() => {
  const storageKey = "prm.comparison.offer_ids.v1";
  const maximum = 8;
  const checkboxes = [...document.querySelectorAll("[data-compare-offer]")];
  const bar = document.querySelector("[data-compare-bar]");
  if (!bar && checkboxes.length === 0) return;

  const count = document.querySelector("[data-compare-count]");
  const link = document.querySelector("[data-compare-link]");
  const message = document.querySelector("[data-compare-message]");
  const clear = document.querySelector("[data-compare-clear]");

  function readSelection() {
    try {
      const parsed = JSON.parse(localStorage.getItem(storageKey) || "[]");
      return Array.isArray(parsed)
        ? [...new Set(parsed.filter((value) => typeof value === "string"))].slice(0, maximum)
        : [];
    } catch {
      return [];
    }
  }

  let selected = readSelection();

  function writeSelection() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(selected));
    } catch {
      message.textContent = "Não foi possível guardar a seleção entre páginas neste navegador.";
    }
  }

  function update() {
    const selectedSet = new Set(selected);
    checkboxes.forEach((checkbox) => {
      checkbox.checked = selectedSet.has(checkbox.value);
    });
    if (!bar) return;
    bar.classList.toggle("has-selection", selected.length > 0);
    count.textContent = String(selected.length);
    const canCompare = selected.length >= 2;
    const parameters = new URLSearchParams();
    selected.forEach((offerId) => parameters.append("offer", offerId));
    link.href = canCompare ? `/static/direct-comparison.html?${parameters.toString()}` : "/static/direct-comparison.html";
    link.classList.toggle("is-disabled", !canCompare);
    link.setAttribute("aria-disabled", canCompare ? "false" : "true");
  }

  checkboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      message.textContent = "";
      if (checkbox.checked) {
        if (selected.length >= maximum) {
          checkbox.checked = false;
          message.textContent = "A comparação direta aceita no máximo 8 produtos.";
          return;
        }
        if (!selected.includes(checkbox.value)) selected.push(checkbox.value);
      } else {
        selected = selected.filter((offerId) => offerId !== checkbox.value);
      }
      writeSelection();
      update();
    });
  });

  clear?.addEventListener("click", () => {
    selected = [];
    message.textContent = "Seleção limpa.";
    writeSelection();
    update();
  });

  link?.addEventListener("click", (event) => {
    if (selected.length < 2) {
      event.preventDefault();
      message.textContent = "Selecione pelo menos 2 ofertas.";
    }
  });

  update();
})();
