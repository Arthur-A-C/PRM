(() => {
  "use strict";
  const root = document.getElementById("store-integrations");
  if (!root) return;
  const api = "/api/v1/integracoes/lojas";
  const message = text => document.getElementById("store-message").textContent = text;
  async function request(url, options = {}) {
    const response = await fetch(url, {cache:"no-store",credentials:"same-origin",...options});
    let data; try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : `Erro HTTP ${response.status}`);
    return data;
  }
  function render(item) {
    if (!["choice","sag","portwell"].includes(item.company)) return;
    const card = root.querySelector(`[data-store="${item.company}"]`);
    card.querySelector("[data-last-test]").textContent = item.checked_at ? "Último teste: " + new Date(item.checked_at).toLocaleString("pt-BR") : "Último teste: não realizado";
    for (const [apiName,selector] of [["woocommerce","wc"],["wordpress","wp"]]) {
      const result = item[apiName];
      card.querySelector(`[data-${selector}-status]`).textContent =
        `${result.authenticated ? "Autenticação confirmada" : "Autenticação não confirmada"} — ${result.message || "Não testado"}`;
    }
    const list = card.querySelector("[data-permissions]"); list.replaceChildren();
    for (const [name,value] of Object.entries(item.wordpress.permissions || {})) {
      const dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = name; dd.textContent = value === true ? "Declarada pela conta" : value === false ? "Não concedida" : "Não informada";
      list.append(dt,dd);
    }
    card.querySelector("[data-media]").textContent = item.wordpress.media?.message || "";
  }
  root.querySelectorAll("[data-test-store]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true; button.textContent = "Testando…";
    message("Consultando endpoints autenticados de leitura; aguarde.");
    try {
      render(await request(`${api}/${button.dataset.testStore}/testar`,{method:"POST",
        headers:{"X-CSRF-Token":document.querySelector('input[name="csrf_token"]')?.value || ""}}));
      message("Diagnóstico concluído. Confira separadamente a autenticação e as permissões das duas APIs.");
    } catch (error) { message(error.message); }
    finally { button.disabled = false; button.textContent = "Testar conexão"; }
  }));
  request(api).then(data => data.items.forEach(render)).catch(error => message(error.message));
})();
