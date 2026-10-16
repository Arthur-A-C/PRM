(() => {
  "use strict";
  const get = (id) => document.getElementById(id);
  const status = get("cadastro-status");
  const preview = get("cadastro-previa");
  if (!status || !window.prmDigitalizacao) return;
  const lastRunKey = "prm:digitalizacao:lastRunId";
  let finalizedRun = null;
  const csrf = () => document.querySelector('input[name="csrf_token"]')?.value || "";
  function notify(message, error = false) {
    status.textContent = message;
    status.classList.toggle("price-warning", error);
  }
  function product() {
    const source = window.prmDigitalizacao.snapshot();
    if (!source.company || !source.sku || !source.technicalName) {
      throw new Error("Informe empresa, código CIGAM/SKU e nome técnico.");
    }
    let attributes = [];
    const raw = get("cadastro-atributos").value.trim();
    if (raw) {
      attributes = JSON.parse(raw);
      if (!Array.isArray(attributes)) throw new Error("Atributos devem formar uma lista JSON.");
    }
    const analysis = source.analysis || {};
    const specs = {};
    (analysis.specs || []).forEach((section) => {
      (section.itens || []).forEach((item) => {
        if (item.campo && item.valor) specs[(section.secao || "Geral") + ": " + item.campo] = item.valor;
      });
    });
    const parts = get("cadastro-categoria").value.split(">").map((item) => item.trim()).filter(Boolean);
    return {
      company: source.company, cigam_code: source.sku, sku: source.sku,
      technical_name: source.technicalName,
      commercial_title: get("cadastro-titulo").value.trim() || source.technicalName,
      supplier: get("cadastro-fornecedor").value.trim() || null,
      model: analysis.model || null,
      category_paths: parts.map((_, index) => parts.slice(0, index + 1).join(" > ")),
      short_description: get("cadastro-descricao-curta").value.trim() || null,
      full_description: get("cadastro-descricao").value.trim() || null,
      features: Array.isArray(analysis.features) ? analysis.features : [],
      specifications: specs,
      benefits: (analysis.beneficios || []).map((item) => [item.titulo, item.descricao].filter(Boolean).join(": ")),
      applications: (analysis.aplicacoes || []).map((item) => [item.titulo, item.descricao].filter(Boolean).join(": ")),
      attributes,
      validation_status: get("cadastro-aprovado").checked ? "approved" : "needs_review",
      warnings: Array.isArray(analysis.alertas) ? analysis.alertas : [],
    };
  }
  async function request(path, body, json = false) {
    const response = await fetch(path.startsWith("/") ? path : "/api/v1/digitalizacao/cadastro/" + path, {
      method: "POST",
      headers: Object.assign({ "X-CSRF-Token": csrf() }, json ? { "Content-Type": "application/json" } : {}),
      body: json ? JSON.stringify(body) : body,
    });
    if (!response.ok) {
      let detail = "HTTP " + response.status;
      try {
        const data = await response.json();
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      } catch (_) { /* non-JSON error */ }
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return response;
  }
  async function run(label, action) {
    status.setAttribute("aria-busy", "true");
    notify(label + ": processando…");
    try { await action(); }
    catch (error) { notify(label + ": " + error.message, true); }
    finally { status.setAttribute("aria-busy", "false"); }
  }
  async function download(response, fallback) {
    const blob = await response.blob();
    const match = (response.headers.get("content-disposition") || "").match(/filename="?([^";]+)"?/i);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = match?.[1] || fallback;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  function setReady(record) {
    finalizedRun = record?.status === "validated" ? record : null;
    if (finalizedRun) window.prmDigitalizacao.markFinalized(true);
    ["cadastro-descricao-gerar", "cadastro-woo-previa", "cadastro-woo-baixar", "cadastro-pacote-baixar", "digitalizacao-baixar-pacote"].forEach((id) => {
      const button = get(id);
      if (button) button.disabled = !finalizedRun;
    });
    const packageStatus = get("digitalizacao-pacote-status");
    if (packageStatus) packageStatus.textContent = finalizedRun
      ? "Pacote validado e salvo em " + finalizedRun.folder_path + ". Versão " + finalizedRun.package_version + "."
      : "Aguardando datasheet revisado e validação da pasta.";
  }
  window.addEventListener("prm:digitalizacao-run", (event) => {
    setReady(null);
    if (event.detail.status === "invalidated") localStorage.removeItem(lastRunKey);
    if (event.detail.runId) {
      localStorage.setItem(lastRunKey, event.detail.runId);
      if (get("digitalizacao-run-id")) get("digitalizacao-run-id").value = event.detail.runId;
    }
  });
  async function restoreLastRun() {
    const linkedRun = new URLSearchParams(window.location.search).get("execucao") || "";
    if (/^[0-9a-f]{32}$/.test(linkedRun)) localStorage.setItem(lastRunKey, linkedRun);
    const runId = localStorage.getItem(lastRunKey);
    if (!runId) return;
    try {
      const response = await fetch(`/api/v1/digitalizacao/execucoes/${encodeURIComponent(runId)}`);
      if (!response.ok) throw new Error("Execução anterior indisponível.");
      const record = await response.json();
      if (get("digitalizacao-run-id")) get("digitalizacao-run-id").value = record.run_id;
      window.prmDigitalizacao.restoreRun(record);
      if (record.manifest?.product) {
        const saved = record.manifest.product;
        if (get("cadastro-titulo")) get("cadastro-titulo").value = saved.commercial_title || "";
        if (get("cadastro-fornecedor")) get("cadastro-fornecedor").value = saved.supplier || "";
        if (get("cadastro-categoria")) get("cadastro-categoria").value = saved.category_paths?.at(-1) || "";
        if (get("cadastro-descricao")) get("cadastro-descricao").value = saved.full_description || "";
        if (get("cadastro-descricao-curta")) get("cadastro-descricao-curta").value = saved.short_description || "";
        if (get("cadastro-atributos")) get("cadastro-atributos").value = JSON.stringify(saved.attributes || [], null, 2);
      }
      if (record.manifest) {
        preview.hidden = false;
        preview.textContent = JSON.stringify(record.manifest, null, 2);
      }
      setReady(record);
      notify(record.status === "validated" ? "Digitalização validada recuperada do servidor." : "Datasheet salvo recuperado; finalize a pasta do produto.");
    } catch (error) {
      localStorage.removeItem(lastRunKey);
      setReady(null);
      notify(error.message, true);
    }
  }
  get("cadastro-descricao-gerar")?.addEventListener("click", () => run("Descrição", async () => {
    if (!finalizedRun) throw new Error("Finalize e valide a digitalização antes da descrição.");
    const result = await (await request("descricao", { product: product(), run_id: finalizedRun.run_id }, true)).json();
    get("cadastro-descricao").value = result.html;
    notify(result.warnings.length ? "Descrição gerada para revisão: " + result.warnings.join(" ") : "Descrição gerada. Revise antes do cadastro.");
  }));
  get("cadastro-lote-previa")?.addEventListener("click", () => run("Prévia do lote", async () => {
    const file = get("cadastro-planilha").files?.[0];
    const company = window.prmDigitalizacao.snapshot().company;
    if (!file || !company) throw new Error("Selecione empresa e planilha.");
    const form = new FormData();
    form.append("empresa", company);
    form.append("arquivo", file);
    if (get("cadastro-export").files?.[0]) form.append("export_file", get("cadastro-export").files[0]);
    const result = await (await request("planilha/previa", form)).json();
    preview.hidden = false;
    preview.textContent = JSON.stringify({
      total_rows: result.total_rows, used_tabs: result.used_tabs,
      duplicate_tabs: result.duplicate_tabs, distinct_products: result.distinct_products,
      repeated_skus: result.repeated_skus, existing_count: result.existing_count,
      new_count: result.new_count, conflicts: result.conflicts, examples: result.examples,
    }, null, 2);
    notify("Prévia gerada. Nenhum produto foi cadastrado; revise conflitos antes de prosseguir.");
  }));
  get("cadastro-arquivos-previa")?.addEventListener("click", () => run("Arquivos", async () => {
    const data = product();
    const result = await (await request("arquivos/previa", { company: data.company, sku: data.sku, run_id: finalizedRun?.run_id || null }, true)).json();
    preview.hidden = false;
    preview.textContent = JSON.stringify(result, null, 2);
    notify(result.found ? "Arquivos localizados para revisão; nenhum upload foi feito." : "Pasta do SKU não encontrada.");
  }));
  get("cadastro-cigam-baixar")?.addEventListener("click", () => run("CIGAM", async () => {
    const template = get("cadastro-cigam-modelo").files?.[0];
    if (!template) throw new Error("Selecione o modelo CIGAM.");
    const form = new FormData();
    form.append("product_json", JSON.stringify(product()));
    form.append("template_file", template);
    const response = await request("cigam/xlsx", form);
    await download(response, "cadastro_cigam.xlsx");
    notify("Arquivo CIGAM gerado; " + response.headers.get("X-PRM-Pending-Fields") + " campos pendentes de revisão.");
  }));
  get("cadastro-woo-previa")?.addEventListener("click", () => run("Prévia WooCommerce", async () => {
    if (!finalizedRun) throw new Error("Finalize e valide a digitalização antes da prévia.");
    const result = await (await request("woocommerce/previa", { product: product(), run_id: finalizedRun.run_id }, true)).json();
    preview.hidden = false;
    preview.textContent = JSON.stringify(result, null, 2);
    notify("Prévia consultada na loja. Nenhum produto foi criado ou alterado.");
  }));
  get("cadastro-woo-baixar")?.addEventListener("click", () => run("WooCommerce CSV", async () => {
    if (!finalizedRun) throw new Error("Finalize e valide a digitalização antes do CSV.");
    const template = get("cadastro-export").files?.[0];
    const form = new FormData();
    form.append("product_json", JSON.stringify(product()));
    form.append("run_id", finalizedRun.run_id);
    if (template) form.append("export_file", template);
    const response = await request("woocommerce/csv", form);
    await download(response, "produto_woo.csv");
    notify("CSV baixado; " + response.headers.get("X-PRM-Review-Warnings") + " avisos para revisão. Nenhum produto foi enviado à loja.");
  }));
  async function finalizePackage() {
    return run("Finalização", async () => {
      const source = window.prmDigitalizacao.snapshot();
      if (!source.runId) throw new Error("Gere e revise o datasheet antes de finalizar.");
      const form = new FormData();
      form.append("run_id", source.runId);
      form.append("product_json", JSON.stringify(product()));
      if (source.sourceDatasheet) form.append("source_datasheet", source.sourceDatasheet);
      if (source.drawing3d) form.append("drawing_3d", source.drawing3d);
      for (const [id, field] of [["digitalizacao-manuais", "manuals"], ["digitalizacao-certificados", "certificates"], ["digitalizacao-outros", "other_files"]]) {
        Array.from(get(id)?.files || []).forEach((file) => form.append(field, file));
      }
      let response;
      try {
        response = await request("/api/v1/digitalizacao/finalizar", form);
      } catch (error) {
        if (error.status !== 409 || !window.confirm("A pasta deste SKU já existe. Criar uma nova versão sem sobrescrever a anterior?")) throw error;
        form.append("new_version", "true");
        response = await request("/api/v1/digitalizacao/finalizar", form);
      }
      const record = await response.json();
      localStorage.setItem(lastRunKey, record.run_id);
      setReady(record);
      preview.hidden = false;
      preview.textContent = JSON.stringify(record.manifest, null, 2);
      notify("Pasta, manifesto e ZIP salvos e validados no servidor. Agora você pode baixar o pacote completo.");
    });
  }
  async function downloadPackage() {
    return run("Pacote completo", async () => {
      if (!finalizedRun) throw new Error("Nenhum pacote validado disponível.");
      const response = await fetch(`/api/v1/digitalizacao/execucoes/${encodeURIComponent(finalizedRun.run_id)}/pacote`);
      if (!response.ok) throw new Error("O pacote salvo não está disponível no servidor.");
      await download(response, finalizedRun.sku + ".zip");
      notify("Pacote validado baixado do armazenamento do servidor.");
    });
  }
  window.prmRegistration = { finalizePackage, downloadPackage };
  get("cadastro-pacote-baixar")?.addEventListener("click", downloadPackage);
  get("digitalizacao-baixar-pacote")?.addEventListener("click", downloadPackage);
  ["digitalizacao-manuais", "digitalizacao-certificados", "digitalizacao-outros"].forEach((id) => {
    get(id)?.addEventListener("change", () => window.prmDigitalizacao.invalidateForFiles());
  });
  get("digitalizacao-recuperar")?.addEventListener("click", () => run("Recuperar execução", async () => {
    const runId = get("digitalizacao-run-id")?.value.trim() || "";
    if (!/^[0-9a-f]{32}$/.test(runId)) throw new Error("Informe um identificador de execução válido.");
    localStorage.setItem(lastRunKey, runId);
    await restoreLastRun();
  }));
  restoreLastRun();
})();
