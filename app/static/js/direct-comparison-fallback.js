(() => {
  const status = document.querySelector("#direct-status");
  const content = document.querySelector("#direct-content");
  const cards = document.querySelector("#direct-products");
  const matrix = document.querySelector("#direct-matrix");
  const reference = document.querySelector("#direct-reference");
  const ids = [...new Set(new URLSearchParams(location.search).getAll("offer"))];
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const fields = [
    ["brand", "Marca/fabricante"], ["manufacturer_code", "Código do fabricante"],
    ["reference", "Referência/modelo"], ["category", "Categoria"],
    ["subcategory", "Subcategoria"], ["application", "Aplicação"],
    ["unit", "Unidade"], ["supplier", "Fornecedor"],
    ["country", "País de origem"], ["availability", "Disponibilidade"],
    ["stock_quantity", "Quantidade em estoque"], ["description", "Descrição declarada"],
  ];
  const modalities = [["venda", "Venda"], ["pix", "Pix"], ["cartao", "Cartão"]];
  const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

  function element(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined && text !== null) item.textContent = String(text);
    if (className) item.className = className;
    return item;
  }

  function latestPrices(product) {
    const result = {};
    for (const row of product.prices || []) {
      if (!(row.modality in result)) result[row.modality] = row.state === "valido" ? Number(row.amount) : null;
    }
    return result;
  }

  function render(products) {
    const selectedReference = reference.value;
    cards.replaceChildren();
    const referenceProduct = products.find((item) => item.id === selectedReference);
    const referencePrices = referenceProduct ? latestPrices(referenceProduct) : {};
    for (const product of products) {
      const card = element("article", null, `comparison-card company-${product.company.code}`);
      const heading = element("div", product.company.name, "product-company");
      if (product.company.type === "nossa") heading.append(element("span", "Nossa empresa", "company-focus-badge"));
      if (product.id === selectedReference) heading.append(element("span", "Referência", "reference-badge"));
      card.append(heading, element("h2", product.name));
      const code = element("p", `Código: ${product.external_code}`);
      card.append(code);
      const prices = latestPrices(product);
      const list = element("div", null, "price-comparison-list");
      for (const [key, label] of modalities) {
        const row = element("div", null, "price-comparison");
        const value = prices[key];
        row.append(element("span", `${label}: ${Number.isFinite(value) && value > 0 ? currency.format(value) : "Não informado"}`));
        const base = referencePrices[key];
        if (Number.isFinite(value) && value > 0 && Number.isFinite(base) && base > 0) {
          const percent = ((value - base) / base * 100).toFixed(1);
          row.append(element("small", `${Number(percent) >= 0 ? "+" : ""}${percent}% frente à referência`, "price-difference"));
        }
        list.append(row);
      }
      card.append(list);
      const detailLink = element("a", "Detalhes e origem");
      detailLink.href = `/api/v1/products/${encodeURIComponent(product.id)}`;
      detailLink.target = "_blank";
      detailLink.rel = "noopener";
      card.append(detailLink);
      cards.append(card);
    }
    const head = element("thead");
    const headingRow = element("tr");
    headingRow.append(element("th", "Característica"));
    for (const product of products) headingRow.append(element("th", `${product.company.name} · ${product.external_code}`));
    head.append(headingRow);
    const body = element("tbody");
    for (const [key, label] of fields) {
      const row = element("tr");
      row.append(element("th", label));
      for (const product of products) {
        const value = product[key];
        row.append(element("td", value === null || value === undefined || value === "" ? "Não informado" : value));
      }
      body.append(row);
    }
    matrix.replaceChildren(head, body);
    content.hidden = false;
    status.textContent = `${products.length} produtos em comparação. Nossas empresas aparecem primeiro.`;
  }

  async function start() {
    if (ids.length < 2 || ids.length > 8 || ids.some((id) => !uuid.test(id))) {
      status.textContent = "Selecione entre 2 e 8 produtos válidos no catálogo.";
      return;
    }
    try {
      const currentRoute = await fetch("/comparacao-direta", { credentials: "same-origin" });
      if (currentRoute.status === 422) {
        location.replace(`/comparacao-direta${location.search}`);
        return;
      }
      if (currentRoute.redirected && new URL(currentRoute.url).pathname === "/login") {
        location.replace("/login");
        return;
      }
      const responses = await Promise.all(ids.map((id) => fetch(`/api/v1/products/${encodeURIComponent(id)}`, { credentials: "same-origin" })));
      if (responses.some((response) => response.status === 401)) {
        location.replace("/login");
        return;
      }
      if (responses.some((response) => !response.ok)) {
        status.textContent = "Um dos produtos não está mais disponível. Volte ao catálogo e limpe a seleção.";
        return;
      }
      const products = await Promise.all(responses.map((response) => response.json()));
      products.sort((a, b) => (a.company.type === "nossa" ? 0 : 1) - (b.company.type === "nossa" ? 0 : 1)
        || a.company.name.localeCompare(b.company.name, "pt-BR") || a.name.localeCompare(b.name, "pt-BR"));
      for (const product of products) {
        const option = element("option", `${product.company.name} · ${product.external_code} · ${product.name}`);
        option.value = product.id;
        reference.append(option);
      }
      reference.addEventListener("change", () => render(products));
      render(products);
    } catch {
      status.textContent = "Não foi possível carregar a comparação. Confira a conexão e tente novamente.";
    }
  }

  start();
})();
