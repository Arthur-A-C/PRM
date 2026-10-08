(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) =>
    Array.from(root.querySelectorAll(selector));

  const elements = {
    empresa: $("#digitalizacao-empresa"),
    codigo: $("#digitalizacao-codigo"),
    produto: $("#digitalizacao-produto"),

    imagensInput: $("#digitalizacao-imagens"),
    imagensContainer: $("#digitalizacao-images"),
    imageCount: $("#image-count"),
    imageFormat: $("#image-format"),
    imageSize: $("#image-size"),
    imageQuality: $("#image-quality"),
    dropzone: $(".digitalizacao-dropzone"),

    supplierDatasheet: $("#supplier-datasheet"),
    supplierDatasheetName: $("#supplier-datasheet-name"),

    drawing3d: $("#drawing-3d"),
    drawing3dName: $("#drawing-3d-name"),

    specs: $("#digitalizacao-specs"),
    extractionStatus: $("#digitalizacao-extraction-status"),

    analisar: $("#digitalizacao-analisar"),

    review: $("#digitalizacao-review"),
    reviewContent: $("#digitalizacao-review-content"),
    gerarDatasheet: $("#digitalizacao-gerar-datasheet"),
    aprovar: $("#digitalizacao-aprovar"),
    previewPages: $("#digitalizacao-preview-pages"),
    datasheetStatus: $("#digitalizacao-datasheet-status"),
    datasheetResult: $("#digitalizacao-datasheet-result"),
    datasheetDownload: $("#digitalizacao-datasheet-download"),

    packageCode: $("#package-code"),
    packageDatasheet: $("#package-datasheet"),
    package3d: $("#package-3d"),
    packageTree: $(".digitalizacao-tree"),

    gerar: $("#digitalizacao-gerar"),
  };

  const state = {
    images: [],
    supplierDatasheet: null,
    drawing3d: null,
    analyzed: false,
    datasheetGenerated: false,
    analysisResult: null,
    datasheetUrl: null,
    datasheetFilename: null,
    runId: null,
    finalized: false,
    approved: false,
    extractingSpecs: false,
    extractedSpecs: "",
    lastExtractionKey: null,
  };

  function currentCode() {
    return String(elements.codigo?.value || "");
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return "0 B";
    }

    const units = ["B", "KB", "MB", "GB"];

    const index = Math.min(
      Math.floor(Math.log(bytes) / Math.log(1024)),
      units.length - 1
    );

    return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${
      units[index]
    }`;
  }

  function fileExtension(file) {
    if (!file?.name || !file.name.includes(".")) {
      return "";
    }

    return file.name.split(".").pop().toLowerCase();
  }

  function imageOutputName(index) {
    return `${index + 1}.jpg`;
  }

  function revokeImageUrl(image) {
    if (image?.url) {
      URL.revokeObjectURL(image.url);
    }
  }

  function createImageState(file) {
    return {
      id: crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`,
      file,
      url: URL.createObjectURL(file),
      rotation: 0,
    };
  }

  function isAcceptedImage(file) {
    return (
      file &&
      (file.type === "image/jpeg" ||
        file.type === "image/png" ||
        /\.(jpe?g|png)$/i.test(file.name))
    );
  }

  function clearGeneratedDatasheet() {
    if (state.datasheetUrl) {
      URL.revokeObjectURL(state.datasheetUrl);
    }

    state.datasheetUrl = null;
    state.datasheetFilename = null;
    state.datasheetGenerated = false;
    state.runId = null;
    state.finalized = false;
    state.approved = false;
    if (elements.previewPages) elements.previewPages.replaceChildren();
    state.images.forEach((image) => { image.processedUrl = null; });
    window.dispatchEvent(new CustomEvent("prm:digitalizacao-run", { detail: { status: "invalidated" } }));

    if (elements.datasheetResult) {
      elements.datasheetResult.hidden = true;
    }

    if (elements.datasheetDownload) {
      elements.datasheetDownload.removeAttribute("href");
      elements.datasheetDownload.removeAttribute("download");
    }
  }

  function invalidateAnalysis() {
    if (!state.analyzed && !state.analysisResult) {
      return;
    }

    state.analyzed = false;
    state.analysisResult = null;
    clearGeneratedDatasheet();

    if (elements.datasheetStatus) {
      elements.datasheetStatus.textContent =
        "Os dados foram alterados. Faça uma nova análise com Claude antes de gerar o datasheet.";
    }

    if (elements.review) {
      elements.review.hidden = true;
    }
  }

  function addImages(files) {
    const accepted = Array.from(files || []).filter(isAcceptedImage);

    if (!accepted.length) {
      showMessage(
        "Selecione imagens JPG, JPEG ou PNG.",
        "warning",
        elements.imagensContainer
      );

      return;
    }

    accepted.forEach((file) => {
      state.images.push(createImageState(file));
    });

    invalidateAnalysis();
    renderImages();
    updatePageState();
  }

  function setMainImage(id) {
    const index = state.images.findIndex((image) => image.id === id);

    if (index <= 0) {
      return;
    }

    const [selected] = state.images.splice(index, 1);

    state.images.unshift(selected);

    invalidateAnalysis();
    renderImages();
    updatePageState();
  }

  function moveImage(id, direction) {
    const index = state.images.findIndex((image) => image.id === id);

    if (index === -1) {
      return;
    }

    const target = index + direction;

    if (target < 0 || target >= state.images.length) {
      return;
    }

    [state.images[index], state.images[target]] = [
      state.images[target],
      state.images[index],
    ];

    invalidateAnalysis();
    renderImages();
    updatePageState();
  }

  function rotateImage(id, degrees) {
    const image = state.images.find((item) => item.id === id);

    if (!image) {
      return;
    }

    image.rotation = (image.rotation + degrees) % 360;

    if (image.rotation < 0) {
      image.rotation += 360;
    }

    invalidateAnalysis();
    renderImages();
    updatePageState();
  }

  function removeImage(id) {
    const index = state.images.findIndex((image) => image.id === id);

    if (index === -1) {
      return;
    }

    revokeImageUrl(state.images[index]);

    state.images.splice(index, 1);

    invalidateAnalysis();
    renderImages();
    updatePageState();
  }

  function actionButton(label, handler, ariaLabel = "") {
    const button = document.createElement("button");

    button.type = "button";
    button.textContent = label;

    if (ariaLabel) {
      button.setAttribute("aria-label", ariaLabel);
    }

    button.addEventListener("click", handler);

    return button;
  }

  function renderImages() {
    if (!elements.imagensContainer) {
      return;
    }

    elements.imagensContainer.innerHTML = "";

    if (!state.images.length) {
      const empty = document.createElement("div");

      empty.className = "digitalizacao-empty";
      empty.textContent = "Nenhuma foto adicionada.";

      elements.imagensContainer.appendChild(empty);

      if (elements.imageCount) {
        elements.imageCount.textContent = "0";
      }

      updatePackageTree();
      return;
    }

    state.images.forEach((image, index) => {
      const card = document.createElement("article");

      card.className = `digitalizacao-image-card${
        index === 0 ? " is-main" : ""
      }`;

      card.dataset.imageId = image.id;

      if (index === 0) {
        const badge = document.createElement("span");

        badge.className = "digitalizacao-image-badge";
        badge.textContent = "Principal";

        card.appendChild(badge);
      }

      const preview = document.createElement("div");
      preview.className = "digitalizacao-image-preview";

      const img = document.createElement("img");

      img.src = image.processedUrl || image.url;
      img.alt = `Prévia de ${image.file.name}`;
      img.style.transform = image.processedUrl ? "none" : `rotate(${image.rotation}deg)`;
      img.style.transition = "transform .18s ease";

      preview.appendChild(img);

      const meta = document.createElement("div");
      meta.className = "digitalizacao-image-meta";

      const title = document.createElement("strong");
      title.textContent = imageOutputName(index);

      const detail = document.createElement("small");

      detail.textContent =
        `${image.file.name} · ` +
        `${formatBytes(image.file.size)} · ` +
        `rotação ${image.rotation}°`;

      meta.append(title, detail);

      const actions = document.createElement("div");
      actions.className = "digitalizacao-image-actions";

      if (index !== 0) {
        actions.appendChild(
          actionButton(
            "Tornar principal",
            () => setMainImage(image.id)
          )
        );
      }

      if (index > 0) {
        actions.appendChild(
          actionButton(
            "←",
            () => moveImage(image.id, -1),
            "Mover para a esquerda"
          )
        );
      }

      if (index < state.images.length - 1) {
        actions.appendChild(
          actionButton(
            "→",
            () => moveImage(image.id, 1),
            "Mover para a direita"
          )
        );
      }

      actions.appendChild(
        actionButton(
          "↺",
          () => rotateImage(image.id, -90),
          "Girar 90 graus para a esquerda"
        )
      );

      actions.appendChild(
        actionButton(
          "↻",
          () => rotateImage(image.id, 90),
          "Girar 90 graus para a direita"
        )
      );

      const remove = actionButton(
        "Remover",
        () => removeImage(image.id)
      );

      remove.classList.add("danger-action");
      actions.appendChild(remove);

      card.append(preview, meta, actions);
      elements.imagensContainer.appendChild(card);
    });

    if (elements.imageCount) {
      elements.imageCount.textContent = String(state.images.length);
    }

    updatePackageTree();
  }

  function setFileCardState(input, hasFile) {
    const card = input?.closest(".digitalizacao-upload-card");

    if (!card) {
      return;
    }

    card.classList.toggle("has-file", Boolean(hasFile));
  }

  function extractionKey() {
    const file = state.supplierDatasheet;

    if (!file) {
      return "";
    }

    return [
      file.name,
      file.size,
      currentCode(),
      elements.produto?.value.trim() || "",
    ].join("|");
  }

  async function extractSupplierDatasheet(force = false) {
    const file = state.supplierDatasheet;

    if (!file || state.extractingSpecs) {
      return;
    }

    const codigo = currentCode();
    const nome = elements.produto?.value.trim() || "";

    if (!elements.codigo?.value.trim() || !nome) {
      if (elements.extractionStatus) {
        elements.extractionStatus.textContent =
          "Preencha o código e o nome do produto para extrair o PDF automaticamente.";
      }

      return;
    }

    const key = extractionKey();

    if (!force && key && state.lastExtractionKey === key) {
      return;
    }

    state.extractingSpecs = true;
    updateButtons();

    if (elements.extractionStatus) {
      elements.extractionStatus.textContent =
        "Extraindo o texto do PDF... Isso pode levar alguns segundos.";
    }

    try {
      const formData = new FormData();

      formData.append("codigo", codigo);
      formData.append("nome", nome);
      formData.append("datasheet", file);

      const response = await fetch(
        "/api/v1/digitalizacao/extrair-especificacoes",
        {
          method: "POST",
          headers: { "X-CSRF-Token": document.querySelector('input[name="csrf_token"]')?.value || "" },
          body: formData,
        }
      );

      let result = null;

      try {
        result = await response.json();
      } catch (_) {
        result = null;
      }

      if (!response.ok) {
        throw new Error(
          result?.detail ||
            "Não foi possível extrair as especificações do PDF."
        );
      }

      const extractedText = String(result?.text || "").trim();

      if (!extractedText) {
        throw new Error(
          "Não foi possível encontrar texto no PDF."
        );
      }

      const currentText = elements.specs?.value.trim() || "";

      let finalText = extractedText;

      if (currentText && !state.extractedSpecs) {
        finalText =
          `${extractedText}\n\n` +
          `INFORMAÇÕES ADICIONAIS INSERIDAS MANUALMENTE\n` +
          `${currentText}`;
      }

      state.extractedSpecs = extractedText;
      state.lastExtractionKey = key;

      if (elements.specs) {
        elements.specs.value = finalText;
      }

      invalidateAnalysis();

      if (elements.extractionStatus) {
        elements.extractionStatus.textContent =
          "✓ Texto do datasheet extraído. Revise e edite antes de analisar com Claude.";
      }

      showMessage(
        "Texto do PDF extraído com sucesso.",
        "success",
        elements.specs?.parentElement
      );

      updatePageState();

    } catch (error) {
      console.error(error);

      state.lastExtractionKey = null;

      if (elements.extractionStatus) {
        elements.extractionStatus.textContent =
          `Falha na extração: ${
            error.message || "erro desconhecido"
          }`;
      }

      showMessage(
        error.message ||
          "Erro ao extrair texto do PDF.",
        "warning",
        elements.specs?.parentElement
      );

    } finally {
      state.extractingSpecs = false;
      updateButtons();
    }
  }

  async function handleDatasheetChange() {
    const file =
      elements.supplierDatasheet?.files?.[0] || null;

    state.supplierDatasheet = file;
    state.extractedSpecs = "";
    state.lastExtractionKey = null;

    invalidateAnalysis();

    if (elements.supplierDatasheetName) {
      elements.supplierDatasheetName.textContent = file
        ? `${file.name} · ${formatBytes(file.size)}`
        : "Nenhum arquivo selecionado";
    }

    setFileCardState(
      elements.supplierDatasheet,
      file
    );

    if (!file && elements.extractionStatus) {
      elements.extractionStatus.textContent =
        "Ao selecionar um PDF, o sistema extrairá todo o texto e preencherá este campo automaticamente.";
    }

    updatePageState();

    if (file) {
      await extractSupplierDatasheet(true);
    }
  }

  function handleDrawing3dChange() {
    const file =
      elements.drawing3d?.files?.[0] || null;

    state.drawing3d = file;
    invalidateAnalysis();

    if (elements.drawing3dName) {
      elements.drawing3dName.textContent = file
        ? `${file.name} · ${formatBytes(file.size)}`
        : "Nenhum arquivo selecionado";
    }

    setFileCardState(
      elements.drawing3d,
      file
    );

    updatePageState();
  }

  function packageItem(icon, name, detail) {
    const li = document.createElement("li");

    const iconSpan = document.createElement("span");
    iconSpan.textContent = icon;

    const nameSpan = document.createElement("span");
    nameSpan.textContent = name;

    const small = document.createElement("small");
    small.textContent = detail;

    li.append(
      iconSpan,
      nameSpan,
      small
    );

    return li;
  }

  function updatePackageTree() {
    const code = currentCode() || "CODIGO";

    if (elements.packageCode) {
      elements.packageCode.textContent = `${code}/`;
    }

    if (elements.packageDatasheet) {
      elements.packageDatasheet.textContent =
        `${code}_Datasheet.pdf`;
    }

    if (elements.package3d) {
      const ext = fileExtension(state.drawing3d);

      elements.package3d.textContent = ext
        ? `${code}_Desenho_3D.${ext}`
        : `${code}_Desenho_3D`;
    }

    if (!elements.packageTree) {
      return;
    }

    const list = $("ul", elements.packageTree);

    if (!list) {
      return;
    }

    list.innerHTML = "";

    list.appendChild(
      packageItem(
        "📄",
        `${code}_Datasheet.pdf`,
        "Datasheet final"
      )
    );

    if (state.drawing3d) {
      const ext = fileExtension(state.drawing3d);

      list.appendChild(
        packageItem(
          "◈",
          `${code}_Desenho_3D${ext ? `.${ext}` : ""}`,
          "Desenho 3D"
        )
      );
    } else {
      list.appendChild(
        packageItem(
          "◈",
          `${code}_Desenho_3D`,
          "Aguardando arquivo 3D"
        )
      );
    }

    if (state.images.length) {
      state.images.forEach((_, index) => {
        list.appendChild(
          packageItem(
            "▧",
            imageOutputName(index),
            index === 0
              ? "Foto principal"
              : "Galeria"
          )
        );
      });
    } else {
      list.appendChild(
        packageItem(
          "▧",
          "1.jpg",
          "Aguardando foto principal"
        )
      );
    }
  }

  function updateSourceStates() {
    const map = {
      datasheet: Boolean(state.supplierDatasheet),

      specs: Boolean(
        elements.specs?.value.trim()
      ),

      images: state.images.length > 0,
    };

    Object.entries(map).forEach(
      ([key, ready]) => {
        const item = $(
          `[data-source="${key}"]`
        );

        if (!item) {
          return;
        }

        item.classList.toggle(
          "is-ready",
          ready
        );

        item.classList.toggle(
          "is-missing",
          !ready
        );

        item.textContent = ready
          ? "✓"
          : "○";
      }
    );
  }

  function updateProgress() {
    const steps =
      $$(".digitalizacao-step");

    const step1Complete = Boolean(
      elements.empresa?.value &&
      elements.codigo?.value.trim() &&
      elements.produto?.value.trim()
    );

    const step2Complete =
      state.images.length > 0 || Boolean(state.runId && state.datasheetGenerated);

    const step3Complete = Boolean(
      state.supplierDatasheet ||
      elements.specs?.value.trim() ||
      state.datasheetGenerated
    );

    const completion = [
      step1Complete,
      step2Complete,
      step3Complete,
      state.finalized,
    ];

    steps.forEach((step, index) => {
      step.classList.toggle(
        "is-complete",
        Boolean(completion[index])
      );

      const previousComplete =
        index === 0 ||
        completion
          .slice(0, index)
          .every(Boolean);

      step.classList.toggle(
        "is-active",
        previousComplete &&
        !completion[index]
      );
    });
  }

  function updateButtons() {
    if (elements.analisar) {
      const hasSpecs =
        Boolean(elements.specs?.value.trim());

      elements.analisar.disabled = Boolean(
        state.extractingSpecs ||
        !elements.codigo?.value.trim() ||
        !elements.produto?.value.trim() ||
        !elements.empresa?.value ||
        !hasSpecs
      );
    }

    if (elements.gerarDatasheet) {
      elements.gerarDatasheet.disabled = !state.analyzed || !state.images.length;
    }

    if (elements.gerar) {
      elements.gerar.disabled = !state.approved || state.finalized;
      if (elements.aprovar) elements.aprovar.disabled = !state.datasheetGenerated || state.approved;
    }
  }

  function updatePageState() {
    updatePackageTree();
    updateSourceStates();
    updateProgress();
    updateButtons();
  }

  function createReviewField(
    label,
    value,
    options = {}
  ) {
    const div =
      document.createElement("div");

    div.className =
      "digitalizacao-review-field";

    if (options.wide) {
      div.classList.add("is-wide");
    }

    if (!value) {
      div.classList.add("is-missing");
    }

    const span =
      document.createElement("span");

    span.textContent = label;

    const strong =
      document.createElement("strong");

    strong.textContent =
      value || "Não informado";

    div.append(span, strong);

    return div;
  }

  async function analyzeWithClaude() {
    if (!elements.analisar) {
      return;
    }

    const specsText =
      elements.specs?.value.trim() || "";

    if (!specsText && !state.supplierDatasheet && !state.images.length) {
      showMessage(
        "Envie um PDF, fotos ou informe as especificações antes de analisar o produto.",
        "warning",
        elements.analisar?.parentElement
      );
      return;
    }

    const originalText =
      elements.analisar.textContent;

    try {
      elements.analisar.disabled = true;

      elements.analisar.textContent =
        "Analisando com Claude...";

      const formData =
        new FormData();

      formData.append(
        "empresa",
        elements.empresa?.value || ""
      );

      formData.append(
        "codigo",
        currentCode()
      );

      formData.append(
        "nome",
        elements.produto?.value.trim() ||
        currentCode()
      );

      formData.append(
        "informacoes_adicionais",
        specsText
      );
      formData.append("configuracao", $("#digitalizacao-configuracao")?.value || "");
      formData.append("opcionais", $("#digitalizacao-opcionais")?.value || "");
      formData.append("nivel", $("#digitalizacao-nivel")?.value || "completo");
      if (state.supplierDatasheet) formData.append("datasheet", state.supplierDatasheet);
      state.images.forEach((image) => formData.append("imagens", image.file));

      const response = await fetch(
        "/api/v1/digitalizacao/analisar",
        {
          method: "POST",
          headers: { "X-CSRF-Token": document.querySelector('input[name="csrf_token"]')?.value || "" },
          body: formData,
        }
      );

      const result =
        await response.json();

      if (!response.ok) {
        throw new Error(
          result.detail ||
          "Não foi possível analisar o produto."
        );
      }

      clearGeneratedDatasheet();

      state.analysisResult =
        result.data;

      state.analyzed = true;

      state.claudeWarnings = result.avisos || [];
      state.claudePendencias = result.pendencias || [];
      renderClaudeReview(result.data);

      if (elements.datasheetStatus) {
        elements.datasheetStatus.textContent =
          "Análise concluída. Revise os dados antes de gerar o datasheet.";
      }

      updatePageState();

    } catch (error) {
      console.error(error);

      state.analysisResult = null;
      state.analyzed = false;

      showMessage(
        error.message ||
        "Erro durante a análise com Claude.",
        "warning",
        elements.analisar?.parentElement
      );

      updatePageState();

    } finally {
      elements.analisar.textContent =
        originalText;

      updateButtons();
    }
  }

  function renderClaudeReview(data) {
    if (
      !elements.review ||
      !elements.reviewContent
    ) {
      return;
    }

    elements.reviewContent.replaceChildren();
    const summary = document.createElement("p");
    summary.textContent = `${data.modelo || ""} · ${data.categoria || ""} · ${data.subtitulo || ""}`;
    elements.reviewContent.append(summary);
    const pending = [...(data.pendencias || []), ...(state.claudeWarnings || [])];
    if (pending.length) {
      const list = document.createElement("ul");
      pending.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        list.append(li);
      });
      elements.reviewContent.append(list);
    }
    const label = document.createElement("label");
    label.textContent = "Dados técnicos estruturados (revise e edite o JSON antes de gerar o PDF)";
    const editor = document.createElement("textarea");
    editor.id = "digitalizacao-json-editor";
    editor.rows = 18;
    editor.style.width = "100%";
    editor.value = JSON.stringify(data, null, 2);
    editor.addEventListener("input", () => {
      clearGeneratedDatasheet();
      updateButtons();
    });
    label.append(editor);
    elements.reviewContent.append(label);
    elements.review.hidden = false;
    elements.review.scrollIntoView({ behavior: "smooth", block: "start" });
    return;

    elements.reviewContent.innerHTML =
      "";

    const grid =
      document.createElement("div");

    grid.className =
      "digitalizacao-review-grid";

    grid.append(
      createReviewField(
        "Modelo",
        data?.model || ""
      ),

      createReviewField(
        "Categoria",
        data?.categoria || ""
      ),

      createReviewField(
        "Subtítulo",
        data?.subtitulo || "",
        { wide: true }
      ),

      createReviewField(
        "Introdução",
        data?.intro || "",
        { wide: true }
      )
    );

    elements.reviewContent.appendChild(
      grid
    );

    if (
      Array.isArray(data?.tags) &&
      data.tags.length
    ) {
      const section =
        document.createElement("div");

      section.className =
        "digitalizacao-review-section";

      const title =
        document.createElement("h3");

      title.textContent =
        "Destaques";

      const list =
        document.createElement("ul");

      data.tags.forEach((tag) => {
        const li =
          document.createElement("li");

        li.textContent = tag;

        list.appendChild(li);
      });

      section.append(
        title,
        list
      );

      elements.reviewContent.appendChild(
        section
      );
    }

    if (
      Array.isArray(data?.features) &&
      data.features.length
    ) {
      const section =
        document.createElement("div");

      section.className =
        "digitalizacao-review-section";

      const title =
        document.createElement("h3");

      title.textContent =
        "Características";

      const list =
        document.createElement("ul");

      data.features.forEach(
        (feature) => {
          const li =
            document.createElement("li");

          li.textContent = feature;

          list.appendChild(li);
        }
      );

      section.append(
        title,
        list
      );

      elements.reviewContent.appendChild(
        section
      );
    }

    if (
      Array.isArray(data?.specs) &&
      data.specs.length
    ) {
      const section =
        document.createElement("div");

      section.className =
        "digitalizacao-review-section";

      const title =
        document.createElement("h3");

      title.textContent =
        "Especificações técnicas";

      section.appendChild(
        title
      );

      data.specs.forEach(
        (specSection) => {
          const sectionTitle =
            document.createElement("strong");

          sectionTitle.textContent =
            specSection?.secao ||
            "Especificações";

          section.appendChild(
            sectionTitle
          );

          const list =
            document.createElement("ul");

          (
            specSection?.itens || []
          ).forEach((item) => {
            const li =
              document.createElement("li");

            const campo =
              item?.campo || "Campo";

            const valor =
              item?.valor ||
              "Não informado";

            li.textContent =
              `${campo}: ${valor}`;

            list.appendChild(li);
          });

          section.appendChild(
            list
          );
        }
      );

      elements.reviewContent.appendChild(
        section
      );
    }

    if (
      Array.isArray(data?.beneficios) &&
      data.beneficios.length
    ) {
      const section =
        document.createElement("div");

      section.className =
        "digitalizacao-review-section";

      const title =
        document.createElement("h3");

      title.textContent =
        "Benefícios";

      const list =
        document.createElement("ul");

      data.beneficios.forEach(
        (item) => {
          const li =
            document.createElement("li");

          li.textContent =
            `${item?.titulo || ""} ${
              item?.descricao || ""
            }`.trim();

          list.appendChild(li);
        }
      );

      section.append(
        title,
        list
      );

      elements.reviewContent.appendChild(
        section
      );
    }

    if (
      Array.isArray(data?.aplicacoes) &&
      data.aplicacoes.length
    ) {
      const section =
        document.createElement("div");

      section.className =
        "digitalizacao-review-section";

      const title =
        document.createElement("h3");

      title.textContent =
        "Aplicações";

      const list =
        document.createElement("ul");

      data.aplicacoes.forEach(
        (item) => {
          const li =
            document.createElement("li");

          li.textContent =
            `${item?.titulo || ""} ${
              item?.descricao || ""
            }`.trim();

          list.appendChild(li);
        }
      );

      section.append(
        title,
        list
      );

      elements.reviewContent.appendChild(
        section
      );
    }

    if (
      Array.isArray(data?.alertas) &&
      data.alertas.length
    ) {
      const alert =
        document.createElement("div");

      alert.className =
        "digitalizacao-message is-warning";

      alert.textContent =
        `Revisar: ${
          data.alertas.join(" · ")
        }`;

      elements.reviewContent.appendChild(
        alert
      );
    }

    if (
      Array.isArray(data?.nao_informado) &&
      data.nao_informado.length
    ) {
      const missing =
        document.createElement("div");

      missing.className =
        "digitalizacao-message is-warning";

      missing.textContent =
        `Não informado: ${
          data.nao_informado.join(" · ")
        }`;

      elements.reviewContent.appendChild(
        missing
      );
    }

    elements.review.hidden = false;

    elements.review.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  function showMessage(
    text,
    type = "success",
    container = null
  ) {
    const parent =
      container ||
      elements.gerar?.parentElement ||
      document.body;

    const old = $(
      ".digitalizacao-message[data-runtime-message]",
      parent
    );

    if (old) {
      old.remove();
    }

    const message =
      document.createElement("div");

    message.className =
      `digitalizacao-message is-${type}`;

    message.dataset.runtimeMessage =
      "true";

    message.textContent = text;

    parent.appendChild(message);

    window.setTimeout(() => {
      if (message.isConnected) {
        message.remove();
      }
    }, 7000);
  }

  async function handleGenerateDatasheet() {
    if (!state.analyzed) {
      showMessage(
        "Analise o produto antes de gerar o datasheet.",
        "warning",
        elements.review
      );

      return;
    }

    if (!state.analysisResult) {
      showMessage(
        "Nenhum resultado da análise foi encontrado.",
        "warning",
        elements.review
      );

      return;
    }

    const editor = $("#digitalizacao-json-editor");
    if (editor) {
      try {
        state.analysisResult = JSON.parse(editor.value);
      } catch (_) {
        showMessage("O JSON editado está inválido.", "warning", elements.review);
        return;
      }
    }

    const originalText =
      elements.gerarDatasheet?.textContent ||
      "Gerar Datasheet";

    try {
      if (elements.gerarDatasheet) {
        elements.gerarDatasheet.disabled = true;
        elements.gerarDatasheet.textContent =
          "Gerando Datasheet...";
      }

      if (elements.datasheetStatus) {
        elements.datasheetStatus.textContent =
          "Gerando PDF. Aguarde a conclusão do processamento.";
      }

      const formData = new FormData();

      formData.append(
        "empresa",
        elements.empresa?.value || ""
      );

      formData.append(
        "codigo",
        currentCode()
      );

      formData.append(
        "analysis_json",
        JSON.stringify(state.analysisResult)
      );

      formData.append("nome", elements.produto?.value.trim() || "");
      formData.append("rotations_json", JSON.stringify(state.images.map((image) => image.rotation)));
      formData.append("size", elements.imageSize?.value || "1200");
      formData.append("quality", elements.imageQuality?.value || "90");
      if (state.supplierDatasheet) formData.append("datasheet", state.supplierDatasheet);

      state.images.forEach((image) => {
        formData.append(
          "imagens",
          image.file
        );
      });

      const response = await fetch(
        "/api/v1/digitalizacao/gerar-datasheet",
        {
          method: "POST",
          headers: { "X-CSRF-Token": document.querySelector('input[name="csrf_token"]')?.value || "" },
          body: formData,
        }
      );

      if (!response.ok) {
        let detail =
          "Não foi possível gerar o datasheet.";

        try {
          const errorData =
            await response.json();

          detail =
            errorData.detail || detail;
        } catch (_) {
          // resposta sem JSON
        }

        throw new Error(detail);
      }

      clearGeneratedDatasheet();
      state.runId = response.headers.get("X-PRM-Run-ID");
      if (!state.runId) throw new Error("Servidor não retornou o identificador do datasheet salvo.");
      state.datasheetUrl = `/api/v1/digitalizacao/execucoes/${state.runId}/datasheet`;
      state.images.forEach((image, index) => {
        image.processedUrl = `/api/v1/digitalizacao/execucoes/${state.runId}/fotos/${index + 1}`;
      });
      renderImages();

      const disposition =
        response.headers.get(
          "content-disposition"
        ) || "";

      const filenameMatch =
        disposition.match(
          /filename="?([^";]+)"?/i
        );

      state.datasheetFilename =
        filenameMatch?.[1] ||
        `${currentCode()}_Datasheet.pdf`;

      state.datasheetGenerated = true;
      state.finalized = false;
      state.approved = false;
      window.dispatchEvent(new CustomEvent("prm:digitalizacao-run", { detail: { status: "draft", runId: state.runId } }));
      await loadDraftPreview();

      if (elements.datasheetDownload) {
        elements.datasheetDownload.href =
          state.datasheetUrl;

        elements.datasheetDownload.download =
          state.datasheetFilename;
      }

      if (elements.datasheetResult) {
        elements.datasheetResult.hidden =
          false;
      }

      if (elements.datasheetStatus) {
        elements.datasheetStatus.textContent =
          `Datasheet gerado com sucesso: ${state.datasheetFilename}`;
      }

      showMessage(
        "Datasheet gerado com sucesso. Use o botão para baixar e revisar o PDF.",
        "success",
        elements.review
      );

      updatePageState();

    } catch (error) {
      console.error(error);

      clearGeneratedDatasheet();

      if (elements.datasheetStatus) {
        elements.datasheetStatus.textContent =
          "Falha ao gerar o datasheet.";
      }

      showMessage(
        error.message ||
        "Erro durante a geração do datasheet.",
        "warning",
        elements.review
      );

      updatePageState();

    } finally {
      if (elements.gerarDatasheet) {
        elements.gerarDatasheet.textContent =
          originalText;
      }

      updateButtons();
    }
  }

  async function loadDraftPreview(record = null) {
    if (!state.runId || !elements.previewPages) return;
    if (!record) {
      const response = await fetch(`/api/v1/digitalizacao/execucoes/${state.runId}`);
      if (!response.ok) throw new Error("Não foi possível recuperar as prévias do PDF.");
      record = await response.json();
    }
    elements.previewPages.replaceChildren();
    for (let index = 1; index <= (record.preview_count || 0); index += 1) {
      const link = document.createElement("a");
      link.href = state.datasheetUrl;
      link.target = "_blank";
      const image = document.createElement("img");
      image.src = `/api/v1/digitalizacao/execucoes/${state.runId}/previas/${index}`;
      image.alt = `Página ${index} do datasheet`;
      image.style.maxWidth = "100%";
      link.append(image);
      elements.previewPages.append(link);
    }
    const problems = [...(record.pending || []), ...(record.warnings || [])];
    if (problems.length) {
      const list = document.createElement("ul");
      problems.forEach((text) => { const item = document.createElement("li"); item.textContent = text; list.append(item); });
      elements.previewPages.append(list);
    }
    state.approved = record.status === "approved" || record.status === "validated";
    updateButtons();
  }

  async function approveDatasheet() {
    if (!state.runId) return;
    const response = await fetch(`/api/v1/digitalizacao/execucoes/${state.runId}`);
    if (!response.ok) throw new Error("Rascunho não encontrado.");
    const record = await response.json();
    const pending = record.pending || [];
    if (pending.length && !window.confirm(`Há ${pending.length} pendência(s) técnica(s). Confirma que revisou todas e deseja aprovar?`)) return;
    const form = new FormData();
    form.append("acknowledge_pending", String(pending.length > 0));
    const approval = await fetch(`/api/v1/digitalizacao/execucoes/${state.runId}/aprovar`, {
      method: "POST", headers: { "X-CSRF-Token": document.querySelector('input[name="csrf_token"]')?.value || "" }, body: form,
    });
    const result = await approval.json();
    if (!approval.ok) throw new Error(result.detail || "Falha ao aprovar datasheet.");
    state.approved = true;
    if (elements.datasheetStatus) elements.datasheetStatus.textContent = "Datasheet aprovado. Você pode criar a pasta do produto.";
    updateButtons();
  }

  function packageManifest() {
    const code = currentCode();

    return {
      empresa:
        elements.empresa?.value || "",

      codigo: code,

      produto:
        elements.produto?.value.trim() ||
        "",

      analysis:
        state.analysisResult,

      image_processing: {
        format:
          elements.imageFormat?.value ||
          "jpg",

        size:
          elements.imageSize?.value ||
          "1200",

        quality: Number(
          elements.imageQuality?.value ||
          90
        ),
      },

      images: state.images.map(
        (image, index) => ({
          original_name:
            image.file.name,

          output_name:
            imageOutputName(index),

          main:
            index === 0,

          rotation:
            image.rotation,

          size_bytes:
            image.file.size,
        })
      ),

      supplier_datasheet:
        state.supplierDatasheet
          ? {
              original_name:
                state.supplierDatasheet.name,

              output_name:
                `${code}_Datasheet.pdf`,

              size_bytes:
                state.supplierDatasheet.size,
            }
          : null,

      drawing_3d:
        state.drawing3d
          ? {
              original_name:
                state.drawing3d.name,

              output_name:
                `${code}_Desenho_3D.${fileExtension(
                  state.drawing3d
                )}`,

              size_bytes:
                state.drawing3d.size,
            }
          : null,

      specifications:
        elements.specs?.value.trim() ||
        "",
    };
  }

  function handleGeneratePackage() {
    if (window.prmRegistration?.finalizePackage) {
      window.prmRegistration.finalizePackage();
    } else {
      showMessage("Serviço de pacote indisponível.", "warning");
    }
  }

  function installDragAndDrop() {
    if (!elements.dropzone) {
      return;
    }

    [
      "dragenter",
      "dragover",
    ].forEach((eventName) => {
      elements.dropzone.addEventListener(
        eventName,
        (event) => {
          event.preventDefault();

          elements.dropzone.classList.add(
            "is-dragging"
          );
        }
      );
    });

    [
      "dragleave",
      "drop",
    ].forEach((eventName) => {
      elements.dropzone.addEventListener(
        eventName,
        (event) => {
          event.preventDefault();

          elements.dropzone.classList.remove(
            "is-dragging"
          );
        }
      );
    });

    elements.dropzone.addEventListener(
      "drop",
      (event) => {
        addImages(
          event.dataTransfer?.files
        );
      }
    );
  }

  function bindEvents() {
    elements.imagensInput?.addEventListener(
      "change",
      (event) => {
        addImages(
          event.target.files
        );

        event.target.value =
          "";
      }
    );

    elements.supplierDatasheet?.addEventListener(
      "change",
      handleDatasheetChange
    );

    elements.drawing3d?.addEventListener(
      "change",
      handleDrawing3dChange
    );

    [
      elements.empresa,
      elements.codigo,
      elements.produto,
      elements.specs,
      elements.imageFormat,
      elements.imageSize,
      elements.imageQuality,
    ]
      .filter(Boolean)
      .forEach((element) => {
        element.addEventListener(
          "input",
          () => {
            invalidateAnalysis();
            updatePageState();
          }
        );

        element.addEventListener(
          "change",
          () => {
            invalidateAnalysis();
            updatePageState();
          }
        );
      });

    elements.codigo?.addEventListener(
      "blur",
      () => {
        if (
          elements.codigo.value.trim()
        ) {
          if (elements.codigo.value !== elements.codigo.value.trim()) {
            showMessage("Remova os espaços nas extremidades do Código CIGAM; o PRM não altera o código automaticamente.", "warning");
          }
        }

        updatePageState();

        if (state.supplierDatasheet) {
          extractSupplierDatasheet();
        }
      }
    );

    elements.produto?.addEventListener(
      "blur",
      () => {
        if (state.supplierDatasheet) {
          extractSupplierDatasheet();
        }
      }
    );

    elements.analisar?.addEventListener(
      "click",
      analyzeWithClaude
    );

    elements.gerarDatasheet?.addEventListener(
      "click",
      handleGenerateDatasheet
    );
    elements.aprovar?.addEventListener("click", () => {
      approveDatasheet().catch((error) => showMessage(error.message, "warning", elements.review));
    });

    elements.gerar?.addEventListener(
      "click",
      handleGeneratePackage
    );

    installDragAndDrop();

    window.addEventListener(
      "beforeunload",
      () => {
        state.images.forEach(
          revokeImageUrl
        );

        if (state.datasheetUrl) {
          URL.revokeObjectURL(
            state.datasheetUrl
          );
        }
      }
    );
  }

  window.prmDigitalizacao = {
    snapshot: () => ({
      company: elements.empresa?.value || "",
      sku: elements.codigo?.value || "",
      technicalName: elements.produto?.value.trim() || "",
      analysis: state.analysisResult,
      images: state.images.map((image) => ({ file: image.file, rotation: image.rotation })),
      generatedDatasheet: state.datasheetUrl
        ? { url: state.datasheetUrl, filename: state.datasheetFilename }
        : null,
      runId: state.runId,
      sourceDatasheet: state.supplierDatasheet,
      drawing3d: state.drawing3d,
      imageSize: elements.imageSize?.value || "1200",
      imageQuality: Number(elements.imageQuality?.value || 90),
    }),
    restoreRun: (record) => {
      if (!record || !record.run_id || !record.analysis) return;
      elements.empresa.value = record.company;
      document.querySelectorAll("[data-company-select]").forEach((card) => {
        card.setAttribute("aria-pressed", String(card.dataset.companySelect === record.company));
      });
      elements.codigo.value = record.sku;
      elements.produto.value = record.name;
      state.analysisResult = record.analysis;
      state.analyzed = true;
      state.runId = record.run_id;
      state.finalized = record.status === "validated";
      state.approved = record.status === "approved" || record.status === "validated";
      state.datasheetGenerated = true;
      state.datasheetUrl = `/api/v1/digitalizacao/execucoes/${record.run_id}/datasheet`;
      state.datasheetFilename = `${record.sku}_Datasheet.pdf`;
      if (elements.datasheetDownload) {
        elements.datasheetDownload.href = state.datasheetUrl;
        elements.datasheetDownload.download = state.datasheetFilename;
      }
      if (elements.datasheetResult) elements.datasheetResult.hidden = false;
      if (elements.datasheetStatus) elements.datasheetStatus.textContent = "Datasheet salvo no servidor; revise antes de prosseguir.";
      loadDraftPreview(record).catch((error) => showMessage(error.message, "warning", elements.review));
      updatePageState();
    },
    markFinalized: (value) => { state.finalized = Boolean(value); updatePageState(); },
    invalidateForFiles: () => { invalidateAnalysis(); updatePageState(); },
  };

  bindEvents();

  renderImages();

  updatePageState();
})();
