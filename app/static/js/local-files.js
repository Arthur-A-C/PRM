/* Seleção de arquivos/pastas do computador do usuário e envio retomável ao PRM (/api/v1/envios).
   O navegador só conhece caminhos relativos à pasta escolhida; nada é gravado no computador do usuário.
   Uso: <div data-local-files="lote|imagens" data-zip-input="id-do-input-zip"></div> dentro do formulário. */
(() => {
  "use strict";
  const api = "/api/v1/envios";
  const IMAGES = [".jpg", ".jpeg", ".png", ".webp"];
  const PROFILES = {
    imagens: [...IMAGES, ".svg"],
    lote: [...IMAGES, ".pdf", ".zip", ".rar", ".7z", ".step", ".stp", ".dwg", ".dxf", ".csv"],
  };
  const PARALLEL = 3, RETRIES = 4;
  const csrf = () => document.querySelector('input[name="csrf_token"]')?.value || "";
  const bytes = n => n >= 1073741824 ? (n / 1073741824).toFixed(2) + " GB" : n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
  const ext = name => { const i = name.lastIndexOf("."); return i < 0 ? "" : name.slice(i).toLowerCase(); };
  const wait = ms => new Promise(r => setTimeout(r, ms));
  function el(tag, text, className) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (className) n.className = className; return n; }
  function hash(text) { let h = 2166136261; for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(36); }
  function store(key, value) { try { value === undefined ? sessionStorage.removeItem(key) : sessionStorage.setItem(key, value); } catch (_) { /* retomada é opcional */ } }
  function stored(key) { try { return sessionStorage.getItem(key); } catch (_) { return null; } }

  async function call(url, options = {}) {
    const r = await fetch(url, { credentials: "same-origin", cache: "no-store", ...options,
      headers: { "X-CSRF-Token": csrf(), ...(options.headers || {}) } });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const e = Error(typeof data.detail === "string" ? data.detail : "Falha no envio"); e.status = r.status; e.data = data; throw e; }
    return data;
  }

  /** Splits a FileList into accepted entries (relative path without the selected root) and ignored ones. */
  function classify(list, profile, fromFolder) {
    const allowed = PROFILES[profile], files = [], ignored = [];
    let root = "";
    for (const file of Array.from(list || [])) {
      let path = (fromFolder && file.webkitRelativePath) || file.name;
      if (fromFolder && path.includes("/")) { root = root || path.split("/")[0]; path = path.split("/").slice(1).join("/"); }
      const parts = path.split("/");
      const reason = parts.some(p => p.startsWith(".")) ? "oculto" : !allowed.includes(ext(path)) ? "tipo não usado neste módulo"
        : !file.size ? "arquivo vazio" : profile === "imagens" && parts[0].toLowerCase() === "backup-fotos" ? "Backup-fotos é criado pelo PRM" : "";
      (reason ? ignored : files).push({ file, path, reason });
    }
    files.sort((a, b) => a.path.localeCompare(b.path, "pt-BR"));
    return { files, ignored, root, total: files.reduce((s, f) => s + f.file.size, 0) };
  }

  class Picker {
    constructor(host) {
      this.host = host; this.profile = host.dataset.localFiles; this.selection = null; this.controller = null; this.session = null;
      this.zip = host.dataset.zipInput ? document.getElementById(host.dataset.zipInput) : null;
      const accept = PROFILES[this.profile].join(",");
      const folderInput = el("input"); folderInput.type = "file"; folderInput.multiple = true; folderInput.webkitdirectory = true; folderInput.hidden = true;
      const filesInput = el("input"); filesInput.type = "file"; filesInput.multiple = true; filesInput.accept = accept; filesInput.hidden = true;
      const folderButton = el("label", null, "prm-btn lf-pick"); folderButton.append(el("span", "Selecionar pasta do computador"), folderInput);
      const filesButton = el("label", null, "prm-btn lf-pick"); filesButton.append(el("span", "Selecionar arquivos"), filesInput);
      this.clearButton = el("button", "Limpar", "prm-btn lf-clear"); this.clearButton.type = "button"; this.clearButton.hidden = true;
      const actions = el("div", null, "lf-actions"); actions.append(folderButton, filesButton, this.clearButton);
      this.summary = el("p", "Nenhum arquivo selecionado. A pasta é lida no seu computador e enviada ao servidor do PRM.", "prm-status lf-summary");
      this.preview = el("details", null, "lf-preview"); this.preview.hidden = true;
      this.progress = el("progress", null, "lf-progress"); this.progress.max = 100; this.progress.value = 0; this.progress.hidden = true;
      this.status = el("p", null, "prm-status lf-status"); this.status.setAttribute("aria-live", "polite");
      this.cancelButton = el("button", "Cancelar envio", "prm-btn lf-cancel"); this.cancelButton.type = "button"; this.cancelButton.hidden = true;
      host.classList.add("lf-picker"); host.replaceChildren(actions, this.summary, this.preview, this.progress, this.status, this.cancelButton);
      folderInput.addEventListener("change", () => { this.select(folderInput.files, true); folderInput.value = ""; });
      filesInput.addEventListener("change", () => { this.select(filesInput.files, false); filesInput.value = ""; });
      this.clearButton.addEventListener("click", () => this.select(null));
      this.cancelButton.addEventListener("click", () => this.cancel());
      if (!("webkitdirectory" in folderInput)) { folderButton.hidden = true; this.summary.textContent = "Este navegador não permite selecionar pastas; use Chrome ou Edge, ou selecione os arquivos."; }
      host.picker = this;
    }

    select(list, fromFolder) {
      const s = list ? classify(list, this.profile, fromFolder) : null;
      this.selection = s && (s.files.length || s.ignored.length) ? s : null;
      this.session = null; this.progress.hidden = true; this.status.textContent = "";
      this.clearButton.hidden = !this.selection;
      if (this.zip) { this.zip.required = !this.selection?.files.length; if (this.selection) this.zip.value = ""; }
      this.render();
      this.host.dispatchEvent(new CustomEvent("local-files:change", { bubbles: true, detail: this.selection }));
    }

    render() {
      const s = this.selection;
      this.preview.replaceChildren(); this.preview.hidden = !s;
      if (!s) { this.summary.textContent = "Nenhum arquivo selecionado."; return; }
      const folders = new Set(s.files.map(f => f.path.split("/").slice(0, -1).join("/")).filter(Boolean));
      this.summary.textContent = `${s.root ? `Pasta "${s.root}": ` : ""}${s.files.length} arquivo(s) · ${bytes(s.total)}` +
        (folders.size ? ` · ${folders.size} subpasta(s)` : "") + (s.ignored.length ? ` · ${s.ignored.length} ignorado(s)` : "");
      this.preview.append(el("summary", "Prévia dos arquivos"));
      const thumbs = el("div", null, "lf-thumbs");
      // SVG shown through <img> only: the browser renders it as a static image (no scripts, no external loads).
      s.files.filter(f => IMAGES.includes(ext(f.path)) || (this.profile === "imagens" && ext(f.path) === ".svg")).slice(0, 12).forEach(f => {
        const img = el("img"); img.alt = f.path; img.loading = "lazy"; img.src = URL.createObjectURL(f.file);
        img.addEventListener("load", () => URL.revokeObjectURL(img.src), { once: true }); thumbs.append(img);
      });
      if (thumbs.childElementCount) this.preview.append(thumbs);
      const list = el("ul", null, "lf-list");
      s.files.slice(0, 200).forEach(f => list.append(el("li", `${f.path} · ${bytes(f.file.size)}`)));
      if (s.files.length > 200) list.append(el("li", `… e mais ${s.files.length - 200} arquivo(s)`));
      this.preview.append(list);
      if (s.ignored.length) {
        const ignored = el("ul", null, "lf-list lf-ignored");
        s.ignored.slice(0, 100).forEach(f => ignored.append(el("li", `${f.path} — ${f.reason}`)));
        this.preview.append(el("p", "Ignorados (não serão enviados):", "prm-status"), ignored);
      }
    }

    hasFiles() { return Boolean(this.selection?.files.length); }

    key() {
      const s = this.selection;
      return "prm-envio:" + this.profile + ":" + hash(s.root + "|" + s.files.map(f => `${f.path}:${f.file.size}:${f.file.lastModified}`).join("|"));
    }

    /** Uploads the selection (resuming an interrupted envio of the same files) and returns the envio id. */
    async upload() {
      if (!this.hasFiles()) throw Error("Selecione arquivos ou uma pasta do computador.");
      const s = this.selection, key = this.key();
      this.controller = new AbortController(); const signal = this.controller.signal;
      this.progress.hidden = false; this.cancelButton.hidden = false; this.progress.value = 0;
      try {
        let session = null;
        const previous = this.session || stored(key);
        if (previous) session = await call(`${api}/${previous}`, { signal }).catch(() => null);
        // Resume only an envio of exactly these files (same paths and sizes, same order): never mix selections.
        if (session && (session.arquivos.length !== s.files.length ||
            session.arquivos.some((a, i) => a.caminho !== s.files[i].path || a.tamanho !== s.files[i].file.size))) session = null;
        if (!session) {
          this.status.textContent = "Preparando envio…";
          session = await call(api, { method: "POST", signal, headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ perfil: this.profile, pasta: s.root, arquivos: s.files.map(f => ({ caminho: f.path, tamanho: f.file.size })) }) });
        } else this.status.textContent = "Retomando envio anterior…";
        this.session = session.id; store(key, session.id);
        if (session.estado !== "ready") {
          const received = session.arquivos.map(a => a.recebido), block = session.bloco_bytes;
          const show = () => {
            const done = received.reduce((a, b) => a + b, 0);
            this.progress.value = Math.round(100 * done / s.total);
            this.status.textContent = `Enviando ${bytes(done)} de ${bytes(s.total)} (${session.arquivos.filter((a, i) => received[i] === a.tamanho).length}/${s.files.length} arquivos)`;
          };
          show();
          const queue = session.arquivos.map((a, i) => i).filter(i => received[i] < session.arquivos[i].tamanho);
          let failed = false; // first error stops every worker, so its message is the one left on screen
          const worker = async () => {
            for (let i = queue.shift(); i !== undefined && !failed; i = queue.shift()) {
              const file = s.files[i].file;
              while (received[i] < file.size && !failed) {
                try { received[i] = await this.chunk(session.id, i, received[i], file.slice(received[i], received[i] + block), signal); }
                catch (e) { failed = true; throw Object.assign(e, { message: `${s.files[i].path}: ${e.message}` }); }
                if (!failed) show();
              }
            }
          };
          await Promise.all(Array.from({ length: PARALLEL }, worker));
          this.status.textContent = "Conferindo arquivos no servidor…";
          await call(`${api}/${session.id}/concluir`, { method: "POST", signal });
        }
        this.progress.value = 100; this.status.textContent = `Envio concluído: ${s.files.length} arquivo(s), ${bytes(s.total)}.`;
        return session.id;
      } catch (e) {
        if (signal.aborted) throw Error("Envio cancelado.");
        this.status.textContent = `${e.message} Selecione a mesma pasta e envie novamente para retomar de onde parou.`;
        throw e;
      } finally { this.cancelButton.hidden = true; this.controller = null; }
    }

    /** One block with retries; a 409 means the server already has a different amount: continue from there. */
    async chunk(id, index, start, blob, signal) {
      for (let attempt = 0; ; attempt++) {
        try {
          const data = await call(`${api}/${id}/arquivos/${index}?inicio=${start}`, { method: "PUT", signal, body: blob,
            headers: { "Content-Type": "application/octet-stream" } });
          return data.recebido;
        } catch (e) {
          if (e.status === 409 && typeof e.data?.recebido === "number") return e.data.recebido;
          if (signal.aborted || (e.status && e.status < 500) || attempt >= RETRIES) throw e;
          await wait(1000 * 2 ** attempt);
        }
      }
    }

    async cancel() {
      this.controller?.abort();
      if (this.session) {
        const id = this.session; this.session = null; store(this.key(), undefined);
        await call(`${api}/${id}`, { method: "DELETE" }).catch(() => {});
      }
      this.progress.hidden = true; this.status.textContent = "Envio cancelado; os arquivos parciais foram removidos do servidor.";
    }

    /** After the module accepted the envio, it owns the files: forget the resume key. */
    done() { if (this.selection) store(this.key(), undefined); this.session = null; }
  }

  /** For forms that take a ZIP: if a folder/files were picked, upload them and send `envio` instead of the ZIP field. */
  async function applyTo(form, data) {
    const picker = form.querySelector("[data-local-files]")?.picker;
    if (!picker?.hasFiles()) return null;
    if (picker.zip) data.delete(picker.zip.name);
    data.set("envio", await picker.upload());
    return picker;
  }

  function init(scope = document) { scope.querySelectorAll("[data-local-files]").forEach(host => host.picker || new Picker(host)); }
  window.PRMLocalFiles = { init, applyTo, classify, bytes };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => init()); else init();
})();
