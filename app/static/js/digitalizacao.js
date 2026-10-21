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

    specsSection: $("#digitalizacao-especificacoes-etapa"),
    analysisSection: $("#digitalizacao-analise-etapa"),
    geracao: $("#digitalizacao-geracao-etapa"),
  };

  // ---- Apresentação: ícones, estados de carregamento e avisos (sem lógica de negócio) ----
  const ICONS = {
    star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
    left: '<path d="M15 6l-6 6 6 6"/>',
    right: '<path d="M9 6l6 6-6 6"/>',
    rotateLeft: '<path d="M4 4v5h5M4.6 9A8 8 0 1 1 6 17.6"/>',
    rotateRight: '<path d="M20 4v5h-5M19.4 9A8 8 0 1 0 18 17.6"/>',
    trash: '<path d="M4 7h16M10 11v6m4-6v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    zoom: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5M10.5 8v5M8 10.5h5"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6m-6 4h6"/>',
    cube: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12 4 7.5"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="m21 16-5-5-9 9"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    alert: '<path d="M12 3 2.5 20h19zM12 10v4.5m0 3h.01"/>',
    info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5m0-8h.01"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  };

  function icon(name) {
    return `<svg class="prm-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
  }

  function buttonLabel(button) {
    return button?.querySelector("[data-dz-label]") || null;
  }

  function setBusy(button, label) {
    if (!button) return;
    const target = buttonLabel(button);
    if (!button.dataset.idleLabel) button.dataset.idleLabel = target ? target.textContent : button.textContent;
    button.setAttribute("aria-busy", "true");
    button.classList.add("is-busy");
    if (target) target.textContent = label;
    else button.textContent = label;
  }

  function clearBusy(button) {
    if (!button) return;
    const target = buttonLabel(button);
    if (button.dataset.idleLabel) {
      if (target) target.textContent = button.dataset.idleLabel;
      else button.textContent = button.dataset.idleLabel;
      delete button.dataset.idleLabel;
    }
    button.removeAttribute("aria-busy");
    button.classList.remove("is-busy");
  }

  // Painel de progresso indeterminado: mensagens indicativas + tempo real decorrido.
  function startProgress(name) {
    const panel = $(`[data-dz-progress="${name}"]`);
    if (!panel) return () => {};
    const message = $("[data-dz-progress-message]", panel);
    const time = $("[data-dz-progress-time]", panel);
    const steps = $$(".dz-progress-steps li", panel);
    const started = Date.now();
    let index = 0;
    const paint = () => {
      steps.forEach((step, position) => {
        step.classList.toggle("is-done", position < index);
        step.classList.toggle("is-current", position === index);
      });
      if (message && steps[index]) message.textContent = `${steps[index].textContent}…`;
    };
    const tick = () => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      if (time) time.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    };
    panel.hidden = false;
    paint();
    tick();
    const clock = window.setInterval(tick, 1000);
    const rotate = window.setInterval(() => {
      if (index < steps.length - 1) {
        index += 1;
        paint();
      }
    }, 3800);
    return () => {
      window.clearInterval(clock);
      window.clearInterval(rotate);
      panel.hidden = true;
    };
  }

  function toast(text, type = "success") {
    let region = $(".prm-toasts");
    if (!region) {
      region = document.createElement("div");
      region.className = "prm-toasts";
      region.setAttribute("role", "status");
      region.setAttribute("aria-live", "polite");
      document.body.append(region);
    }
    const item = document.createElement("div");
    item.className = `prm-toast is-${type}`;
    item.innerHTML = icon(type === "success" ? "check" : type === "warning" ? "alert" : "info");
    const copy = document.createElement("span");
    copy.textContent = text;
    item.append(copy);
    region.append(item);
    window.setTimeout(() => {
      item.classList.add("is-leaving");
      window.setTimeout(() => item.remove(), 220);
    }, 4200);
  }

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
    savedImageCount: 0,
    extractingSpecs: false,
    extractedSpecs: "",
    lastExtractionKey: null,
    extractionState: "idle",
    recentImageIds: new Set(),
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
    state.savedImageCount = 0;
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
      const image = createImageState(file);
      state.recentImageIds.add(image.id);
      state.images.push(image);
    });

    invalidateAnalysis();
    renderImages();
    updatePageState();
    toast(accepted.length === 1 ? "1 foto adicionada." : `${accepted.length} fotos adicionadas.`);
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

  function actionButton(iconName, handler, ariaLabel, disabled = false) {
    const button = document.createElement("button");

    button.type = "button";
    button.className = "prm-btn prm-btn-icon prm-btn-ghost";
    button.innerHTML = icon(iconName);
    button.setAttribute("aria-label", ariaLabel);
    button.title = ariaLabel;
    button.disabled = disabled;

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
      }${state.recentImageIds.has(image.id) ? " is-new" : ""}`;

      card.dataset.imageId = image.id;

      if (index === 0) {
        const badge = document.createElement("span");

        badge.className = "digitalizacao-image-badge";
        badge.innerHTML = `${icon("star")}<span>Principal</span>`;

        card.appendChild(badge);
      }

      const order = document.createElement("span");
      order.className = "dz-image-order";
      order.textContent = String(index + 1);
      order.setAttribute("aria-hidden", "true");
      card.appendChild(order);

      const preview = document.createElement("button");
      preview.type = "button";
      preview.className = "digitalizacao-image-preview";
      preview.setAttribute("aria-label", `Ampliar foto ${image.file.name}`);
      preview.addEventListener("click", () => {
        const dialog = document.getElementById("digitalizacao-image-dialog");
        const enlarged = document.getElementById("digitalizacao-image-dialog-preview");
        if (!dialog || !enlarged) return;
        enlarged.src = image.processedUrl || image.url;
        enlarged.alt = `Foto ampliada de ${image.file.name}`;
        enlarged.style.transform = image.processedUrl ? "none" : `rotate(${image.rotation}deg)`;
        document.getElementById("digitalizacao-image-dialog-title").textContent = image.file.name;
        dialog.showModal();
      });

      const img = document.createElement("img");

      img.src = image.processedUrl || image.url;
      img.alt = `Prévia de ${image.file.name}`;
      img.style.transform = image.processedUrl ? "none" : `rotate(${image.rotation}deg)`;
      img.style.transition = "transform .18s ease";

      const zoom = document.createElement("span");
      zoom.className = "dz-image-zoom";
      zoom.innerHTML = icon("zoom");

      preview.append(img, zoom);

      const meta = document.createElement("div");
      meta.className = "digitalizacao-image-meta";

      const title = document.createElement("strong");
      title.textContent = imageOutputName(index);

      const name = document.createElement("small");
      name.className = "dz-image-name";
      name.textContent = image.file.name;
      name.title = image.file.name;

      const detail = document.createElement("small");
      detail.textContent = image.rotation
        ? `${formatBytes(image.file.size)} · girada ${image.rotation}°`
        : formatBytes(image.file.size);

      meta.append(title, name, detail);

      const actions = document.createElement("div");
      actions.className = "digitalizacao-image-actions";
      const label = image.file.name;

      actions.append(
        actionButton("star", () => setMainImage(image.id), index === 0 ? "Esta é a foto principal" : `Tornar ${label} a foto principal`, index === 0),
        actionButton("left", () => moveImage(image.id, -1), `Mover ${label} para a esquerda`, index === 0),
        actionButton("right", () => moveImage(image.id, 1), `Mover ${label} para a direita`, index === state.images.length - 1),
        actionButton("rotateLeft", () => rotateImage(image.id, -90), `Girar ${label} 90° para a esquerda`),
        actionButton("rotateRight", () => rotateImage(image.id, 90), `Girar ${label} 90° para a direita`)
      );

      const remove = actionButton("trash", () => removeImage(image.id), `Remover ${label}`);
      remove.classList.add("danger-action", "prm-btn-danger");
      actions.appendChild(remove);

      card.append(preview, meta, actions);
      elements.imagensContainer.appendChild(card);
    });

    state.recentImageIds.clear();

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
    state.extractionState = "loading";
    updateButtons();
    updateExtractionUI();

    if (elements.extractionStatus) {
      elements.extractionStatus.textContent =
        "Extraindo dados do datasheet… Isso pode levar alguns segundos.";
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
      state.extractionState = "done";

      if (elements.specs) {
        elements.specs.value = finalText;
      }

      if (!state.analyzed) invalidateAnalysis();

      if (elements.extractionStatus) {
        elements.extractionStatus.textContent =
          "Especificações prontas para revisão. Revise e edite antes de analisar com Claude.";
      }

      toast("Texto do PDF extraído com sucesso.");

      updatePageState();

    } catch (error) {
      console.error(error);

      state.lastExtractionKey = null;
      state.extractionState = "error";

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
        elements.specsSection
      );

    } finally {
      state.extractingSpecs = false;
      updateButtons();
      updateExtractionUI();
    }
  }

  function updateExtractionUI() {
    const section = elements.specsSection;
    const text = elements.specs?.value.trim() || "";
    const meta = $("[data-dz-spec-meta]");
    if (meta) {
      const lines = text ? text.split(/\n/).length : 0;
      meta.textContent = text
        ? `${text.length.toLocaleString("pt-BR")} caracteres · ${lines.toLocaleString("pt-BR")} ${lines === 1 ? "linha" : "linhas"}`
        : "Vazio";
    }
    if (!section) return;
    let mode = state.extractionState;
    if (mode === "idle" && text) mode = "manual";
    section.dataset.extraction = mode;
    const pill = $("[data-dz-extraction-pill]", section);
    const labels = {
      idle: ["Aguardando PDF", ""],
      manual: ["Texto manual", "is-info"],
      loading: ["Extraindo dados do datasheet…", "is-info is-busy"],
      done: ["Especificações prontas para revisão", "is-ok"],
      error: ["Falha na extração", "is-alert"],
    };
    if (pill) {
      const [label, tone] = labels[mode] || labels.idle;
      pill.className = `prm-pill ${tone}`.trim();
      pill.textContent = label;
    }
    const checks = {
      pdf: Boolean(state.supplierDatasheet),
      text: Boolean(state.extractedSpecs),
      review: Boolean(text) && !state.extractingSpecs,
    };
    Object.entries(checks).forEach(([key, done]) => {
      const item = $(`[data-dz-check="${key}"]`, section);
      if (!item) return;
      item.classList.toggle("is-done", done);
      item.classList.toggle("is-active", key === "text" && state.extractingSpecs);
    });
  }

  async function handleDatasheetChange() {
    const file =
      elements.supplierDatasheet?.files?.[0] || null;

    state.supplierDatasheet = file;
    state.extractedSpecs = "";
    state.lastExtractionKey = null;
    state.extractionState = "idle";

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

  function packageItem(glyph, name, detail) {
    const li = document.createElement("li");

    const iconSpan = document.createElement("span");
    iconSpan.className = "dz-tree-icon";
    iconSpan.innerHTML = icon({ "📄": "file", "◈": "cube", "▧": "image" }[glyph] || "file");
    if (/Aguardando/.test(detail)) li.classList.add("is-pending");

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
      state.datasheetGenerated
    );

    const step4Complete = Boolean(
      (elements.specs?.value.trim() && !state.extractingSpecs) ||
      state.datasheetGenerated
    );

    // Produto, imagens, PDF, especificações, análise, revisão, geração/aprovação, pacote.
    const completion = [
      step1Complete,
      step2Complete,
      step3Complete,
      step4Complete,
      state.analyzed,
      state.analyzed && state.datasheetGenerated,
      state.approved,
      state.finalized,
    ];
    // PDF e texto são fontes alternativas: podem ficar para trás sem bloquear o fluxo.
    const optional = [false, false, true, true, false, false, false, false];
    const lastDone = completion.lastIndexOf(true);
    let active = completion.findIndex((done, index) => !done && (index > lastDone || !optional[index]));
    if (active === -1) active = completion.length;

    steps.forEach((step, index) => {
      const done = Boolean(completion[index]);
      const skipped = !done && optional[index] && index < active;
      step.classList.toggle("is-complete", done);
      step.classList.toggle("is-active", index === active);
      step.classList.toggle("is-skipped", skipped);
      if (index === active) step.setAttribute("aria-current", "step");
      else step.removeAttribute("aria-current");

      const pill = $(`#${step.dataset.stepTarget} [data-dz-step-state]`);
      if (pill) {
        const [label, tone] = done ? ["Concluído", "is-ok"]
          : index === active ? ["Em andamento", "is-info"]
            : skipped ? ["Não enviado", ""] : ["Pendente", ""];
        pill.className = `prm-pill ${tone}`.trim();
        pill.textContent = label;
      }
    });

    const doneCount = completion.filter(Boolean).length;
    $$("[data-dz-progress-fill]").forEach((bar) => {
      bar.style.width = `${(doneCount / completion.length) * 100}%`;
    });
    const label = $("[data-dz-progress-label]");
    if (label) label.textContent = `${doneCount} de ${completion.length} etapas`;
  }

  function updateButtons() {
    if (elements.analisar) {
      const hasSource = Boolean(
        elements.specs?.value.trim() ||
        state.supplierDatasheet ||
        state.images.length
      );

      elements.analisar.disabled = Boolean(
        !elements.codigo?.value.trim() ||
        !elements.produto?.value.trim() ||
        !elements.empresa?.value ||
        !hasSource
      );
    }

    if (elements.gerarDatasheet) {
      elements.gerarDatasheet.disabled = !state.analyzed;
    }

    if (elements.gerar) {
      elements.gerar.disabled = !state.approved || !state.savedImageCount || state.finalized;
    }
    if (elements.aprovar) elements.aprovar.disabled = !state.datasheetGenerated || state.approved;
  }

  function updatePageState() {
    updatePackageTree();
    updateSourceStates();
    updateExtractionUI();
    updateProgress();
    updateButtons();
    updateContext();
  }

  function updateContext() {
    const company = elements.empresa?.value || "";
    const labels = { portwell: "Portwell", choice: "Choice", sag: "SAG" };
    const page = document.querySelector(".digitalizacao-page");
    if (page) page.dataset.company = company;
    const put = (id, value) => { const target = document.getElementById(id); if (target) target.textContent = value; };
    put("context-product-name", elements.produto?.value.trim() || "Novo produto");
    put("context-company", labels[company] || "Não selecionada");
    put("context-code", currentCode() || "—");
    put("context-images", String(state.images.length || state.savedImageCount || 0));
    put("context-source", state.supplierDatasheet ? "Recebido" : "Não enviado");
    let next = "Selecione uma empresa e identifique o produto.";
    if (company && currentCode() && elements.produto?.value.trim()) next = "Envie o material técnico e organize as fotos.";
    if (state.analyzed) next = "Revise os dados técnicos e gere o PDF.";
    if (state.datasheetGenerated) next = "Confira as páginas e aprove o datasheet.";
    if (state.approved) next = state.savedImageCount ? "Crie a pasta CIGAM e valide o pacote." : "Adicione uma foto principal antes de finalizar o pacote.";
    if (state.finalized) next = "Pacote validado. Revise a preparação do cadastro.";
    put("context-next-action", next);
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

    if (options.full) {
      div.classList.add("is-full");
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

    let stopProgress = () => {};

    try {
      elements.analisar.disabled = true;

      setBusy(elements.analisar, "Analisando produto…");
      if (elements.analysisSection) elements.analysisSection.dataset.analysis = "running";
      stopProgress = startProgress("analysis");

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

      if (elements.analysisSection) elements.analysisSection.dataset.analysis = "done";
      toast("Análise concluída. Revise os dados estruturados.");
      updatePageState();

    } catch (error) {
      console.error(error);

      state.analysisResult = null;
      state.analyzed = false;
      if (elements.analysisSection) elements.analysisSection.dataset.analysis = "error";

      showMessage(
        error.message ||
        "Erro durante a análise com Claude.",
        "warning",
        elements.analysisSection
      );

      updatePageState();

    } finally {
      stopProgress();
      clearBusy(elements.analisar);

      updateButtons();
    }
  }

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  const asList = (value) => (Array.isArray(value) ? value.filter((item) => item !== null && item !== undefined && item !== "") : []);
  const asText = (value) => (typeof value === "string" ? value.trim() : "");

  // Linhas {secao} abrem um grupo; linhas {chave, valor} pertencem ao grupo aberto.
  function groupRows(rows) {
    const groups = [];
    let current = null;
    asList(rows).forEach((row) => {
      if (!row || typeof row !== "object") return;
      if (row.secao && !row.chave && !row.valor) {
        current = { title: String(row.secao), rows: [] };
        groups.push(current);
        return;
      }
      if (!current || (row.secao && row.secao !== current.title)) {
        current = { title: row.secao ? String(row.secao) : "Geral", rows: [] };
        groups.push(current);
      }
      current.rows.push([String(row.chave ?? row.campo ?? ""), String(row.valor ?? "")]);
    });
    return groups.filter((group) => group.rows.length);
  }

  function reviewSection(title, count, options = {}) {
    const section = el("section", `dz-rsec${options.wide ? " is-wide" : ""}${options.tone ? ` is-${options.tone}` : ""}`);
    const head = el("header", "dz-rsec-head");
    head.append(el("h4", "", title));
    if (count !== undefined && count !== null) head.append(el("span", "dz-rsec-count", String(count)));
    section.append(head);
    return section;
  }

  function pairList(pairs) {
    const list = el("dl", "dz-pairs");
    asList(pairs).forEach((pair) => {
      const [term, description] = Array.isArray(pair) ? pair : [pair?.titulo, pair?.descricao];
      const row = el("div");
      row.append(el("dt", "", String(term ?? "")), el("dd", "", String(description ?? "")));
      list.append(row);
    });
    return list;
  }

  function keyValueTable(rows) {
    const table = el("table", "dz-kv");
    const body = el("tbody");
    rows.forEach(([key, value]) => {
      const tr = el("tr");
      tr.append(el("th", "", key), el("td", "", value || "Não informado"));
      if (!value) tr.classList.add("is-missing");
      body.append(tr);
    });
    table.append(body);
    return table;
  }

  function gridTable(header, lines) {
    const wrap = el("div", "dz-table-wrap");
    const table = el("table", "dz-grid-table");
    if (asList(header).length) {
      const thead = el("thead");
      const tr = el("tr");
      header.forEach((cell) => tr.append(el("th", "", String(cell))));
      thead.append(tr);
      table.append(thead);
    }
    const body = el("tbody");
    asList(lines).forEach((line) => {
      const tr = el("tr");
      asList(line).forEach((cell) => tr.append(el("td", "", String(cell))));
      body.append(tr);
    });
    table.append(body);
    wrap.append(table);
    return wrap;
  }

  function renderStructuredReview(container, data) {
    container.replaceChildren();
    const missing = [];
    const note = (label, present) => { if (!present) missing.push(label); };

    // Identificação
    const summary = el("div", "dz-review-summary");
    summary.append(
      createReviewField("Modelo", asText(data.modelo) || asText(data.model), { wide: true }),
      createReviewField("Categoria", asText(data.categoria)),
      createReviewField("Nível", asText(data.nivel)),
      createReviewField("Subtítulo", asText(data.subtitulo), { full: true })
    );
    note("Modelo", asText(data.modelo) || asText(data.model));
    note("Categoria", asText(data.categoria));
    note("Subtítulo", asText(data.subtitulo));
    container.append(summary);

    const grid = el("div", "dz-review-sections");

    const intro = asList(data.descricao).length ? asList(data.descricao) : (asText(data.intro) ? [asText(data.intro)] : []);
    note("Introdução", intro.length);
    if (intro.length) {
      const section = reviewSection("Introdução", null, { wide: true });
      intro.forEach((paragraph) => section.append(el("p", "dz-rsec-text", String(paragraph))));
      grid.append(section);
    }

    const tags = asList(data.tags);
    note("Destaques", tags.length);
    if (tags.length) {
      const section = reviewSection("Destaques", tags.length);
      const chips = el("div", "dz-chips");
      tags.forEach((tag) => chips.append(el("span", "dz-chip", String(tag))));
      section.append(chips);
      grid.append(section);
    }

    const features = asList(data.features);
    note("Características", features.length || asList(data.caracteristicas).length);
    if (features.length) {
      const section = reviewSection("Características", features.length);
      const list = el("ul", "dz-checks");
      features.forEach((feature) => list.append(el("li", "", String(feature))));
      section.append(list);
      grid.append(section);
    }

    if (asList(data.caracteristicas).length) {
      const section = reviewSection(asText(data.titulo_caracteristicas) || "Características e benefícios", asList(data.caracteristicas).length, { wide: true });
      section.append(pairList(data.caracteristicas));
      grid.append(section);
    }

    if (asList(data.beneficios).length) {
      const section = reviewSection("Benefícios", asList(data.beneficios).length, { wide: true });
      section.append(pairList(data.beneficios));
      grid.append(section);
    }

    const specGroups = groupRows(data.especificacoes);
    asList(data.specs).forEach((group) => {
      const rows = asList(group?.itens).map((item) => [String(item?.campo ?? ""), String(item?.valor ?? "")]);
      if (rows.length) specGroups.push({ title: String(group?.secao || "Especificações"), rows });
    });
    note("Especificações", specGroups.length);
    if (specGroups.length) {
      const total = specGroups.reduce((sum, group) => sum + group.rows.length, 0);
      const section = reviewSection("Especificações técnicas", total, { wide: true });
      const groups = el("div", "dz-spec-groups");
      specGroups.forEach((group) => {
        const block = el("div", "dz-spec-group");
        block.append(el("h5", "", group.title), keyValueTable(group.rows));
        groups.append(block);
      });
      section.append(groups);
      grid.append(section);
    }

    const dimensions = groupRows(data.dimensoes);
    if (dimensions.length) {
      const section = reviewSection("Dimensões", dimensions.reduce((sum, group) => sum + group.rows.length, 0));
      dimensions.forEach((group) => {
        if (dimensions.length > 1) section.append(el("h5", "dz-subhead", group.title));
        section.append(keyValueTable(group.rows));
      });
      grid.append(section);
    }

    asList(data.conectores).forEach((group) => {
      if (!asList(group?.itens).length) return;
      const section = reviewSection(asText(group.grupo) || "Conectores", asList(group.itens).length);
      section.append(pairList(group.itens));
      grid.append(section);
    });

    asList(data.tabelas).forEach((table) => {
      if (!asList(table?.linhas).length) return;
      const section = reviewSection(asText(table.titulo) || "Tabela", asList(table.linhas).length, { wide: true });
      section.append(gridTable(table.cabecalho, table.linhas));
      if (asText(table.nota)) section.append(el("p", "dz-rsec-note", table.nota));
      grid.append(section);
    });

    if (asList(data.pedido?.linhas).length) {
      const section = reviewSection("Informações para pedido", asList(data.pedido.linhas).length, { wide: true });
      section.append(gridTable(data.pedido.cabecalho, data.pedido.linhas));
      grid.append(section);
    }

    const applications = asList(data.aplicacoes);
    note("Aplicações", applications.length);
    if (applications.length) {
      const section = reviewSection("Aplicações", applications.length);
      section.append(pairList(applications));
      grid.append(section);
    }

    [["acessorios", "Acessórios"], ["notas", "Notas"]].forEach(([key, title]) => {
      if (!asList(data[key]).length) return;
      const section = reviewSection(title, asList(data[key]).length);
      section.append(pairList(data[key]));
      grid.append(section);
    });

    const images = asList(data.imagens).filter((item) => item && item.papel !== "descartar");
    if (images.length) {
      const section = reviewSection("Uso das imagens", images.length);
      const list = el("ul", "dz-image-roles");
      images.forEach((item) => {
        const li = el("li");
        li.append(el("code", "", String(item.arquivo || "")), el("span", "dz-chip", String(item.papel || "")));
        if (asText(item.legenda)) li.append(el("small", "", item.legenda));
        list.append(li);
      });
      section.append(list);
      grid.append(section);
    }

    if (asText(data.conferencia_fontes) || asList(data.termos_proibidos).length) {
      const section = reviewSection("Conferência das fontes", null, { wide: true });
      if (asText(data.conferencia_fontes)) section.append(el("p", "dz-rsec-text", data.conferencia_fontes));
      if (asList(data.termos_proibidos).length) {
        section.append(el("h5", "dz-subhead", "Termos que não aparecem no conteúdo comercial"));
        const chips = el("div", "dz-chips");
        asList(data.termos_proibidos).forEach((term) => chips.append(el("span", "dz-chip is-muted", String(term))));
        section.append(chips);
      }
      grid.append(section);
    }

    const notFound = [...missing, ...asList(data.nao_informado).map(String)];
    if (notFound.length) {
      const section = reviewSection("Dados não encontrados", notFound.length, { wide: true, tone: "muted" });
      section.append(el("p", "dz-rsec-note", "Seções que a análise não preencheu. Complete no JSON técnico se a informação existir na fonte."));
      const chips = el("div", "dz-chips");
      notFound.forEach((item) => chips.append(el("span", "dz-chip is-muted", item)));
      section.append(chips);
      grid.append(section);
    }

    container.append(grid);
  }

  function renderClaudeReview(data, options = {}) {
    if (
      !elements.review ||
      !elements.reviewContent
    ) {
      return;
    }

    elements.reviewContent.replaceChildren();

    const alerts = [...asList(data.pendencias), ...asList(data.alertas), ...(state.claudeWarnings || [])].map(String);
    const issues = el("div", `dz-issues${alerts.length ? " is-warn" : " is-ok"}`);
    const issuesHead = el("div", "dz-issues-head");
    issuesHead.innerHTML = icon(alerts.length ? "alert" : "check");
    issuesHead.append(el("strong", "", alerts.length
      ? `${alerts.length} ${alerts.length === 1 ? "alerta para revisar" : "alertas para revisar"}`
      : "Nenhum alerta registrado pela análise"));
    issues.append(issuesHead);
    if (alerts.length) {
      const list = el("ul");
      alerts.forEach((item) => list.append(el("li", "", item)));
      issues.append(list);
    }

    const tabs = el("div", "dz-tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Formato da revisão");
    const structuredPanel = el("div", "dz-tabpanel");
    const jsonPanel = el("div", "dz-tabpanel");
    structuredPanel.id = "dz-review-structured";
    jsonPanel.id = "dz-review-json";
    const tabButtons = [["Visão estruturada", structuredPanel], ["JSON técnico (editável)", jsonPanel]].map(([label, panel], index) => {
      const button = el("button", "dz-tab", label);
      button.type = "button";
      button.id = `${panel.id}-tab`;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", panel.id);
      button.setAttribute("aria-selected", String(index === 0));
      button.tabIndex = index === 0 ? 0 : -1;
      panel.setAttribute("role", "tabpanel");
      panel.setAttribute("aria-labelledby", button.id);
      panel.hidden = index !== 0;
      return button;
    });
    const select = (target) => {
      tabButtons.forEach((button) => {
        const active = button === target;
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
        document.getElementById(button.getAttribute("aria-controls")).hidden = !active;
      });
    };
    tabButtons.forEach((button, index) => {
      button.addEventListener("click", () => select(button));
      button.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
        const next = tabButtons[(index + (event.key === "ArrowRight" ? 1 : -1) + tabButtons.length) % tabButtons.length];
        select(next);
        next.focus();
      });
    });
    tabs.append(...tabButtons);

    const validity = el("span", "prm-pill is-ok", "JSON válido");
    const label = document.createElement("label");
    label.className = "dz-json-label";
    label.htmlFor = "digitalizacao-json-editor";
    label.textContent = "Dados técnicos estruturados — o PDF é gerado a partir deste JSON";
    const editor = document.createElement("textarea");
    editor.id = "digitalizacao-json-editor";
    editor.rows = 22;
    editor.spellcheck = false;
    editor.value = JSON.stringify(data, null, 2);
    let rerender = 0;
    editor.addEventListener("input", () => {
      clearGeneratedDatasheet();
      updateButtons();
      window.clearTimeout(rerender);
      rerender = window.setTimeout(() => {
        try {
          const parsed = JSON.parse(editor.value);
          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("not an object");
          renderStructuredReview(structuredPanel, parsed);
          validity.className = "prm-pill is-ok";
          validity.textContent = "JSON válido";
        } catch (_) {
          validity.className = "prm-pill is-alert";
          validity.textContent = "JSON inválido";
        }
      }, 350);
    });
    const jsonHead = el("div", "dz-json-head");
    jsonHead.append(label, validity);
    jsonPanel.append(jsonHead, editor);

    renderStructuredReview(structuredPanel, data);
    elements.reviewContent.append(issues, tabs, structuredPanel, jsonPanel);
    elements.review.hidden = false;
    if (options.scroll !== false) {
      elements.review.scrollIntoView({ behavior: "smooth", block: "start" });
    }
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

    message.setAttribute("role", type === "warning" ? "alert" : "status");
    message.innerHTML = icon(type === "success" ? "check" : type === "warning" ? "alert" : "info");
    const copy = document.createElement("span");
    copy.textContent = text;
    message.append(copy);

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

    let stopProgress = () => {};

    try {
      if (elements.gerarDatasheet) {
        elements.gerarDatasheet.disabled = true;
        setBusy(elements.gerarDatasheet, "Gerando datasheet…");
      }
      if (elements.geracao) elements.geracao.dataset.generation = "running";
      stopProgress = startProgress("generation");

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
      state.savedImageCount = state.images.length;
      window.dispatchEvent(new CustomEvent("prm:digitalizacao-run", { detail: { status: "draft", runId: state.runId } }));
      try {
        await loadDraftPreview();
      } catch (previewError) {
        showMessage(previewError.message, "warning", elements.geracao || elements.review);
      }

      showDatasheetResult();

      if (elements.datasheetStatus) {
        elements.datasheetStatus.textContent =
          `Datasheet gerado com sucesso: ${state.datasheetFilename}`;
      }

      if (elements.geracao) elements.geracao.dataset.generation = "done";
      toast("Datasheet gerado. Confira as páginas antes de aprovar.");

      updatePageState();

    } catch (error) {
      console.error(error);

      clearGeneratedDatasheet();
      if (elements.geracao) elements.geracao.dataset.generation = "error";

      if (elements.datasheetStatus) {
        elements.datasheetStatus.textContent =
          "Falha ao gerar o datasheet.";
      }

      showMessage(
        error.message ||
        "Erro durante a geração do datasheet.",
        "warning",
        elements.geracao || elements.review
      );

      updatePageState();

    } finally {
      stopProgress();
      clearBusy(elements.gerarDatasheet);

      updateButtons();
    }
  }

  function showDatasheetResult() {
    if (elements.datasheetDownload) {
      elements.datasheetDownload.href = state.datasheetUrl;
      elements.datasheetDownload.download = state.datasheetFilename;
    }
    const open = $("[data-dz-datasheet-open]", elements.datasheetResult || document);
    if (open) open.href = state.datasheetUrl;
    const filename = $("[data-dz-datasheet-filename]", elements.datasheetResult || document);
    if (filename) filename.textContent = state.datasheetFilename || "Rascunho salvo no servidor";
    if (elements.datasheetResult) elements.datasheetResult.hidden = false;
  }

  async function loadDraftPreview(record = null) {
    if (!state.runId || !elements.previewPages) return;
    if (!record) {
      const response = await fetch(`/api/v1/digitalizacao/execucoes/${state.runId}`);
      if (!response.ok) throw new Error("Não foi possível recuperar as prévias do PDF.");
      record = await response.json();
    }
    elements.previewPages.replaceChildren();
    const pages = Number(record.preview_count || 0);
    if (pages) {
      let current = 1;
      const viewer = document.createElement("div");
      viewer.className = "datasheet-viewer";
      const toolbar = document.createElement("div");
      toolbar.className = "datasheet-viewer-toolbar";
      const previous = document.createElement("button");
      previous.type = "button";
      previous.className = "prm-btn prm-btn-sm";
      previous.innerHTML = `${icon("left")}<span>Anterior</span>`;
      const counter = document.createElement("strong");
      const next = document.createElement("button");
      next.type = "button";
      next.className = "prm-btn prm-btn-sm";
      next.innerHTML = `<span>Próxima</span>${icon("right")}`;
      const zoom = document.createElement("button");
      zoom.type = "button";
      zoom.className = "prm-btn prm-btn-sm";
      zoom.innerHTML = `${icon("zoom")}<span>Ampliar</span>`;
      zoom.setAttribute("aria-pressed", "false");
      zoom.addEventListener("click", () => {
        const active = viewer.classList.toggle("is-zoomed");
        zoom.querySelector("span").textContent = active ? "Ajustar" : "Ampliar";
        zoom.setAttribute("aria-pressed", String(active));
      });
      const open = document.createElement("a");
      open.href = state.datasheetUrl;
      open.target = "_blank";
      open.rel = "noopener";
      open.className = "prm-btn prm-btn-sm";
      open.innerHTML = `${icon("external")}<span>Abrir PDF</span>`;
      const page = document.createElement("img");
      page.alt = "Prévia do datasheet";
      const canvas = document.createElement("div");
      canvas.className = "datasheet-viewer-canvas";
      canvas.append(page);
      const show = () => {
        page.src = `/api/v1/digitalizacao/execucoes/${state.runId}/previas/${current}`;
        page.alt = `Página ${current} de ${pages} do datasheet`;
        counter.textContent = `Página ${current} / ${pages}`;
        previous.disabled = current === 1;
        next.disabled = current === pages;
      };
      previous.addEventListener("click", () => { current -= 1; show(); });
      next.addEventListener("click", () => { current += 1; show(); });
      toolbar.append(previous, counter, next, zoom, open);
      viewer.append(toolbar, canvas);
      elements.previewPages.append(viewer);
      show();
    } else {
      const message = document.createElement("p");
      message.textContent = "Prévia de páginas indisponível. Abra o PDF para revisão.";
      elements.previewPages.append(message);
    }
    const problems = [...(record.pending || []), ...(record.warnings || [])];
    if (problems.length) {
      const box = document.createElement("div");
      box.className = "dz-issues is-warn";
      const head = document.createElement("div");
      head.className = "dz-issues-head";
      head.innerHTML = icon("alert");
      const title = document.createElement("strong");
      title.textContent = `${problems.length} ${problems.length === 1 ? "pendência do rascunho" : "pendências do rascunho"} para conferir antes de aprovar`;
      head.append(title);
      const list = document.createElement("ul");
      problems.forEach((text) => { const item = document.createElement("li"); item.textContent = text; list.append(item); });
      box.append(head, list);
      elements.previewPages.append(box);
    }
    state.approved = record.status === "approved" || record.status === "validated";
    state.savedImageCount = Number(record.image_count || 0);
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
    toast("Datasheet aprovado.");
    if (elements.datasheetStatus) elements.datasheetStatus.textContent = state.savedImageCount
      ? "Datasheet aprovado. Você pode criar a pasta do produto."
      : "Datasheet aprovado. Adicione uma foto principal e gere o PDF novamente para criar o pacote final.";
    updatePageState();
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
    document.getElementById("digitalizacao-image-dialog-close")?.addEventListener("click", () => {
      document.getElementById("digitalizacao-image-dialog")?.close();
    });
    document.querySelectorAll("[data-step-target]").forEach((step) => {
      step.addEventListener("click", () => {
        let target = document.getElementById(step.dataset.stepTarget);
        // A revisão só aparece após a análise; até lá, leva à etapa de análise.
        if (target?.hidden) target = elements.analysisSection;
        target?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
    // Arrastar e soltar nos cartões de PDF e 3D: entrega o arquivo ao input original.
    $$("[data-dz-drop]").forEach((card) => {
      const input = document.getElementById(card.dataset.dzDrop);
      if (!input) return;
      ["dragenter", "dragover"].forEach((name) => card.addEventListener(name, (event) => {
        event.preventDefault();
        card.classList.add("is-dragging");
      }));
      ["dragleave", "drop"].forEach((name) => card.addEventListener(name, (event) => {
        event.preventDefault();
        card.classList.remove("is-dragging");
      }));
      card.addEventListener("drop", (event) => {
        const file = event.dataTransfer?.files?.[0];
        if (!file) return;
        if (input.accept === ".pdf" && !/\.pdf$/i.test(file.name)) {
          showMessage("Envie o datasheet do fornecedor em PDF.", "warning", card.parentElement);
          return;
        }
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
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
      approveDatasheet().catch((error) => showMessage(error.message, "warning", elements.geracao || elements.review));
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
      state.savedImageCount = Number(record.image_count || 0);
      state.datasheetGenerated = true;
      state.datasheetUrl = `/api/v1/digitalizacao/execucoes/${record.run_id}/datasheet`;
      state.datasheetFilename = `${record.sku}_Datasheet.pdf`;
      showDatasheetResult();
      renderClaudeReview(record.analysis, { scroll: false });
      if (elements.datasheetStatus) elements.datasheetStatus.textContent = "Datasheet salvo no servidor; revise antes de prosseguir.";
      loadDraftPreview(record).catch((error) => showMessage(error.message, "warning", elements.geracao || elements.review));
      updatePageState();
    },
    markFinalized: (value) => { state.finalized = Boolean(value); updatePageState(); },
    invalidateForFiles: () => { invalidateAnalysis(); updatePageState(); },
  };

  bindEvents();

  renderImages();

  updatePageState();
})();
