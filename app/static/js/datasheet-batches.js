(() => {
  "use strict";
  const root = document.getElementById("batch-page");
  if (!root) return;
  const api = "/api/v1/digitalizacao/lotes";
  const $ = id => document.getElementById(id);
  const labels = {pending:"Pendente",queued:"Na fila",running:"Processando",done:"Concluído",
    review:"Requer revisão",error:"Erro",invalid:"Inválido",finished:"Finalizado",expired:"Arquivos expirados"};
  let selected = new URLSearchParams(location.search).get("lote"), busy = false;
  function identificationMode() {
    const folders = $("batch-identification").value === "folder";
    $("batch-company-field").hidden = $("batch-root-field").hidden = !folders;
    $("batch-company").required = folders;
    $("batch-company").disabled = $("batch-root").disabled = !folders;
    $("batch-identification-help").textContent = folders
      ? "CSV opcional dentro do ZIP: codigo deve ser idêntico à pasta. Complementos: nome, empresa, descricao, categoria, observacoes e datasheet_original. Zeros à esquerda são preservados."
      : "Inclua exatamente um CSV com codigo, nome e empresa e os PDFs referenciados, como no fluxo anterior.";
  }
  $("batch-identification").addEventListener("change", identificationMode);
  identificationMode();
  function message(text) { $("batch-message").textContent = text; }
  async function request(url, options = {}) {
    const response = await fetch(url, {credentials:"same-origin", cache:"no-store", ...options});
    if (!response.ok) {
      let error; try { error = await response.json(); } catch (_) {}
      throw new Error(typeof error?.detail === "string" ? error.detail : `Falha HTTP ${response.status}`);
    }
    return response.json();
  }
  function cell(row, text) {
    const td = document.createElement("td"); td.textContent = text; row.append(td); return td;
  }
  const tones = {done:"is-ok",finished:"is-ok",review:"is-warn",error:"is-alert",invalid:"is-alert",
    running:"is-info is-busy",queued:"is-info",expired:""};
  function pill(td, state) {
    const span = document.createElement("span");
    span.className = `prm-pill ${tones[state] || ""}`.trim();
    span.textContent = td.textContent;
    td.replaceChildren(span);
  }
  function link(parent, text, href) {
    const a = document.createElement("a"); a.textContent = text; a.href = href; parent.append(a);
  }
  function render(data) {
    selected = data.id;
    history.replaceState(null, "", "?lote=" + encodeURIComponent(selected));
    $("batch-current").hidden = false;
    $("batch-title").textContent = `Lote ${data.id}`;
    const c = data.counts;
    $("batch-summary").textContent = `Total: ${data.total} · Concluídos: ${c.done||0} · Revisão: ${c.review||0} · Processando: ${c.running||0} · Pendentes/fila: ${(c.pending||0)+(c.queued||0)} · Erros: ${c.error||0} · Ignorados: ${c.invalid||0} · ${data.progress}% finalizado`;
    $("batch-progress").value = data.progress;
    $("batch-model").textContent = `Modelo do processamento: ${data.model || "será registrado ao iniciar"} · ${labels[data.state]}`;
    const active = ["running","queued","expired"].includes(data.state);
    $("batch-start").disabled = busy || active || !c.pending;
    $("batch-retry").disabled = busy || active || !c.error;
    $("batch-download").href = `${api}/${selected}/download`;
    $("batch-download").hidden = data.state === "expired";
    $("batch-products").replaceChildren();
    data.items.forEach(item => {
      const row = document.createElement("tr");
      [item.codigo,item.nome,item.empresa.toUpperCase(),item.pdf || "—",labels[item.state]].forEach(v => cell(row,v));
      pill(row.lastChild, item.state);
      const detail = cell(row,item.error || "Validado");
      if (item.folder) {
        const note = document.createElement("p"); note.textContent = `Pasta: ${item.folder}`; detail.append(note);
      }
      (item.warnings || []).forEach(text => {
        const note = document.createElement("p"); note.textContent = text; detail.append(note);
      });
      if (item.assets?.length) {
        const inventory = document.createElement("details"), title = document.createElement("summary");
        title.textContent = `${item.assets.length} arquivo(s) identificado(s)`; inventory.append(title);
        const list = document.createElement("ul");
        item.assets.forEach(asset => {
          const entry = document.createElement("li");
          entry.textContent = `${asset.name} · ${asset.role} · ${asset.bytes} bytes · ${asset.analyze ? "Análise" : "Preservado sem análise"}`;
          list.append(entry);
        });
        inventory.append(list); detail.append(inventory);
      }
      if (item.technical) {
        const el = document.createElement("details"), summary = document.createElement("summary");
        summary.textContent = "Detalhes técnicos"; el.append(summary);
        const code = document.createElement("code"); code.textContent = `${item.technical} · Tentativas: ${item.attempts}`;
        el.append(code); detail.append(el);
      }
      const result = cell(row,"");
      if (item.download) link(result,"Baixar PDF",`${api}/${selected}/produtos/${item.id}/pdf`);
      $("batch-products").append(row);
    });
  }
  async function loadHistory() {
    const data = await request(api);
    $("batch-history").replaceChildren();
    data.items.forEach(item => {
      const row = document.createElement("tr");
      [item.id + " · " + new Date(item.created*1000).toLocaleString("pt-BR"),item.total,
        item.counts.done||0,item.counts.review||0,(item.counts.error||0)+(item.counts.invalid||0),labels[item.state]].forEach(v => cell(row,v));
      pill(row.lastChild, item.state);
      const actions = cell(row,""), button = document.createElement("button");
      button.type = "button"; button.textContent = "Consultar";
      button.addEventListener("click", () => request(`${api}/${item.id}`).then(render).catch(e => message(e.message)));
      actions.append(button);
      if (item.state !== "expired") link(actions," Baixar ZIP",`${api}/${item.id}/download`);
      $("batch-history").append(row);
    });
  }
  const headers = () => ({"X-CSRF-Token":document.querySelector('input[name="csrf_token"]')?.value || ""});
  $("batch-upload").addEventListener("submit", async event => {
    event.preventDefault(); if (busy) return; busy = true;
    const button = event.target.querySelector("button"); button.disabled = true;
    message("Validando arquivos… nenhuma chamada de IA nesta etapa.");
    try {
      render(await request(api,{method:"POST",headers:headers(),body:new FormData(event.target)}));
      message("Validação concluída. Confira os itens antes de iniciar."); await loadHistory();
    } catch (e) { message(e.message); }
    finally { busy = false; button.disabled = false; if (selected) request(`${api}/${selected}`).then(render).catch(e=>message(e.message)); }
  });
  async function queue(action) {
    if (busy || !selected || !confirm("Esta ação usa a API de IA configurada e pode gerar custos. Continuar?")) return;
    busy = true; $("batch-start").disabled = $("batch-retry").disabled = true;
    try { const data = await request(`${api}/${selected}/${action}`,{method:"POST",headers:headers()}); busy=false; render(data); await loadHistory(); }
    catch(e) { message(e.message); } finally { busy=false; }
  }
  $("batch-start").addEventListener("click",()=>queue("iniciar"));
  $("batch-retry").addEventListener("click",()=>queue("reprocessar"));
  $("batch-refresh").addEventListener("click",()=>loadHistory().catch(e=>message(e.message)));
  async function refresh() {
    try { if (selected && !busy) render(await request(`${api}/${selected}`)); await loadHistory(); }
    catch(e) { message(e.message); }
  }
  async function poll() {
    if (!document.hidden) await refresh();
    setTimeout(poll, 5000);
  }
  poll();
})();
