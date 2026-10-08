(() => {
  "use strict";
  const get = (id) => document.getElementById(id);
  const status = get("cadastro-status");
  const preview = get("cadastro-previa");
  if (!status || !window.prmDigitalizacao) return;
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
    const response = await fetch("/api/v1/digitalizacao/cadastro/" + path, {
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
      throw new Error(detail);
    }
    return response;
  }
  async function run(label, action) {
    notify(label + ": processando…");
    try { await action(); }
    catch (error) { notify(label + ": " + error.message, true); }
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
  get("cadastro-descricao-gerar")?.addEventListener("click", () => run("Descrição", async () => {
    const result = await (await request("descricao", { product: product() }, true)).json();
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
    const result = await (await request("arquivos/previa", { company: data.company, sku: data.sku }, true)).json();
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
    const result = await (await request("woocommerce/previa", { product: product() }, true)).json();
    preview.hidden = false;
    preview.textContent = JSON.stringify(result, null, 2);
    notify("Prévia consultada na loja. Nenhum produto foi criado ou alterado.");
  }));
  get("cadastro-woo-baixar")?.addEventListener("click", () => run("WooCommerce CSV", async () => {
    const template = get("cadastro-export").files?.[0];
    const form = new FormData();
    form.append("product_json", JSON.stringify(product()));
    if (template) form.append("export_file", template);
    const response = await request("woocommerce/csv", form);
    await download(response, "produto_woo.csv");
    notify("CSV baixado; " + response.headers.get("X-PRM-Review-Warnings") + " avisos para revisão. Nenhum produto foi enviado à loja.");
  }));
  async function downloadPackage() {
    return run("Pacote ZIP", async () => {
      const source = window.prmDigitalizacao.snapshot();
      const form = new FormData();
      form.append("product_json", JSON.stringify(product()));
      source.images.forEach((item) => form.append("images", item.file));
      form.append("rotations_json", JSON.stringify(source.images.map((item) => item.rotation)));
      form.append("size", source.imageSize);
      form.append("quality", String(source.imageQuality));
      if (source.sourceDatasheet) form.append("source_datasheet", source.sourceDatasheet);
      if (source.drawing3d) form.append("drawing_3d", source.drawing3d);
      if (source.generatedDatasheet) {
        const blob = await (await fetch(source.generatedDatasheet.url)).blob();
        form.append("generated_datasheet", blob, source.generatedDatasheet.filename || "datasheet.pdf");
      }
      await download(await request("pacote/zip", form), "pacote.zip");
      notify("ZIP real gerado e baixado; confira o manifesto e os arquivos.");
    });
  }
  window.prmRegistration = { downloadPackage };
  get("cadastro-pacote-baixar")?.addEventListener("click", downloadPackage);
})();
