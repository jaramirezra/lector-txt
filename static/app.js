(() => {
  "use strict";

  const LIST_RE = /^\s*(?:[•◦▪‣·∙]\s*|[-–—*]\s+|\d{1,3}[.)]\s+)/;
  const MAX_HISTORY = 60;
  const KIND_LABELS = {
    heading: "Título",
    paragraph: "Párrafo",
    list: "Lista",
    table: "Tabla",
    quote: "Cita",
  };
  const DEFAULT_OPTIONS = {
    paragraph_sep: "single",
    list_prefix: "keep",
    table_sep: "tab",
    heading_style: "none",
    join_hyphenated: false,
    encoding: "utf-8",
    newline: "lf",
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const els = {
    uploadView: $("#upload-view"),
    workspace: $("#workspace"),
    dropzone: $("#dropzone"),
    fileInput: $("#file-input"),
    dropBusy: $("#drop-busy"),
    dropBusyText: $("#drop-busy-text"),
    uploadError: $("#upload-error"),
    btnNew: $("#btn-new"),
    btnExport: $("#btn-export"),
    docKind: $("#doc-kind"),
    docName: $("#doc-name"),
    docMeta: $("#doc-meta"),
    docStats: $("#doc-stats"),
    warnings: $("#warnings"),
    search: $("#search"),
    searchStatus: $("#search-status"),
    btnAll: $("#btn-all"),
    btnNone: $("#btn-none"),
    btnSuggest: $("#btn-suggest"),
    suggestCount: $("#suggest-count"),
    btnUndo: $("#btn-undo"),
    btnRedo: $("#btn-redo"),
    pdfView: $("#pdf-view"),
    docxView: $("#docx-view"),
    docEmpty: $("#doc-empty"),
    docScroll: $("#doc-scroll"),
    blockList: $("#block-list"),
    blockCount: $("#block-count"),
    result: $("#result"),
    resultStats: $("#result-stats"),
    manualNote: $("#manual-note"),
    btnRegenerate: $("#btn-regenerate"),
    options: $("#options"),
    optSep: $("#opt-sep"),
    optList: $("#opt-list"),
    optTable: $("#opt-table"),
    optHeading: $("#opt-heading"),
    optEncoding: $("#opt-encoding"),
    optNewline: $("#opt-newline"),
    optHyphen: $("#opt-hyphen"),
    pwModal: $("#password-modal"),
    pwForm: $("#pw-form"),
    pwFile: $("#pw-file"),
    pwMeta: $("#pw-meta"),
    pwInput: $("#pw-input"),
    pwToggle: $("#pw-toggle"),
    pwError: $("#pw-error"),
    pwSubmit: $("#pw-submit"),
    pwClose: $("#pw-close"),
    pwField: $(".pw-field"),
    toast: $("#toast"),
  };

  const state = {
    jobId: null,
    status: null,
    kind: null,
    filename: null,
    pageCount: 0,
    pages: [],
    blocks: [],
    warnings: [],
    previewHtml: null,
    encryption: null,
    manualDirty: false,
    history: [],
    future: [],
    search: "",
    options: loadOptions(),
    blockMap: new Map(),
    rowMap: new Map(),
    overlayMap: new Map(),
    docxMap: new Map(),
    busy: false,
  };

  let pendingJob = null;
  let toastTimer = null;

  // ---------------------------------------------------------------- utilidades

  function sanitizeOptions(options) {
    const merged = { ...DEFAULT_OPTIONS, ...(options || {}) };
    if (!["none", "single", "double"].includes(merged.paragraph_sep)) merged.paragraph_sep = "single";
    if (!["keep", "dash", "none"].includes(merged.list_prefix)) merged.list_prefix = "keep";
    if (!["tab", "pipe", "newline"].includes(merged.table_sep)) merged.table_sep = "tab";
    if (!["none", "upper", "markdown"].includes(merged.heading_style)) merged.heading_style = "none";
    if (!["utf-8", "utf-8-sig"].includes(merged.encoding)) merged.encoding = "utf-8";
    if (!["lf", "crlf"].includes(merged.newline)) merged.newline = "lf";
    merged.join_hyphenated = Boolean(merged.join_hyphenated);
    return merged;
  }

  function loadOptions() {
    try {
      const stored = JSON.parse(localStorage.getItem("lector-txt-options") || "{}");
      return sanitizeOptions(stored);
    } catch (_error) {
      return { ...DEFAULT_OPTIONS };
    }
  }

  function saveOptions() {
    try {
      localStorage.setItem("lector-txt-options", JSON.stringify(state.options));
    } catch (_error) {
      /* almacenamiento no disponible */
    }
  }

  function truncate(text, limit = 150) {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean;
  }

  function normalizeText(text) {
    const lines = String(text ?? "")
      .replace(/\r\n?/g, "\n")
      .split("\n")
      .map((line) => line.replace(/[ \t]+$/g, ""));
    return lines.join("\n").trim();
  }

  function showToast(message) {
    els.toast.textContent = message;
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      els.toast.hidden = true;
    }, 3200);
  }

  function showUploadError(message) {
    els.uploadError.textContent = message;
    els.uploadError.hidden = false;
  }

  function hideUploadError() {
    els.uploadError.hidden = true;
    els.uploadError.textContent = "";
  }

  function setUploadBusy(busy, message = "Leyendo documento…") {
    state.busy = busy;
    els.dropBusy.hidden = !busy;
    els.dropBusyText.textContent = message;
    els.dropzone.classList.toggle("is-busy", busy);
  }

  function flash(element) {
    if (!element) return;
    element.classList.remove("is-flash");
    void element.offsetWidth;
    element.classList.add("is-flash");
    setTimeout(() => element.classList.remove("is-flash"), 1300);
  }

  function setPane(name) {
    $$(".pane-tabs button").forEach((button) => {
      const active = button.dataset.paneTarget === name;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", String(active));
    });
    $$(".pane").forEach((pane) => {
      pane.classList.toggle("is-active", pane.dataset.pane === name);
    });
  }

  // ------------------------------------------------------------ carga de archivo

  function validateFile(file) {
    const name = (file.name || "").toLowerCase();
    if (!name.endsWith(".pdf") && !name.endsWith(".docx")) {
      return "Solo se admiten archivos PDF o DOCX.";
    }
    const maxMb = Number(document.body.dataset.maxFileMb || 30);
    if (file.size > maxMb * 1024 * 1024) {
      return `El archivo supera el límite de ${maxMb} MB.`;
    }
    return null;
  }

  async function handleFile(file) {
    if (!file || state.busy) return;
    hideUploadError();
    const problem = validateFile(file);
    if (problem) {
      showUploadError(problem);
      return;
    }

    setUploadBusy(true);
    const body = new FormData();
    body.append("file", file);

    try {
      const response = await fetch("/api/jobs", { method: "POST", body });
      const data = await response.json().catch(() => ({}));

      if (response.status === 202 && data.status === "locked") {
        showPasswordModal(data);
        return;
      }
      if (!response.ok) {
        throw new Error(data.message || "No se pudo abrir el documento.");
      }
      renderJob(data);
    } catch (error) {
      showUploadError(error.message || "No se pudo abrir el documento.");
    } finally {
      setUploadBusy(false);
    }
  }

  // ------------------------------------------------------------ modal contraseña

  function showPasswordModal(data) {
    pendingJob = data;
    els.pwFile.textContent = data.filename || "Documento";
    const parts = [];
    if (data.encryption && data.encryption.method) parts.push(data.encryption.method);
    if (data.page_count) parts.push(`${data.page_count} páginas`);
    els.pwMeta.textContent = parts.join(" · ") || "Introduce la contraseña para continuar";
    els.pwInput.value = "";
    els.pwInput.type = "password";
    els.pwToggle.textContent = "Ver";
    els.pwError.hidden = true;
    els.pwField.classList.remove("is-invalid");
    els.pwModal.hidden = false;
    setTimeout(() => els.pwInput.focus(), 30);
  }

  function showPasswordError(message) {
    els.pwError.textContent = message;
    els.pwError.hidden = false;
    els.pwField.classList.remove("is-invalid");
    void els.pwField.offsetWidth;
    els.pwField.classList.add("is-invalid");
  }

  function setPasswordBusy(busy) {
    els.pwSubmit.disabled = busy;
    els.pwInput.disabled = busy;
    els.pwSubmit.textContent = busy ? "Comprobando…" : "Abrir documento";
  }

  function closePasswordModal(deleteJob) {
    const job = pendingJob;
    pendingJob = null;
    els.pwModal.hidden = true;
    els.pwInput.value = "";
    if (deleteJob && job && job.job_id) {
      fetch(`/api/jobs/${encodeURIComponent(job.job_id)}`, { method: "DELETE" }).catch(() => {});
    }
  }

  async function submitPassword(event) {
    event.preventDefault();
    if (!pendingJob) return;
    const password = els.pwInput.value;
    if (!password) {
      showPasswordError("Introduce la contraseña del documento.");
      els.pwInput.focus();
      return;
    }

    setPasswordBusy(true);
    els.pwError.hidden = true;
    try {
      const response = await fetch(
        `/api/jobs/${encodeURIComponent(pendingJob.job_id)}/unlock`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password }),
        },
      );
      const data = await response.json().catch(() => ({}));

      if (response.ok) {
        closePasswordModal(false);
        renderJob(data);
        return;
      }
      if (response.status === 410) {
        closePasswordModal(false);
        showUploadError(data.message || "Se agotaron los intentos. Sube el documento de nuevo.");
        return;
      }
      const attempts = Number(data.attempts_left);
      if (Number.isFinite(attempts) && attempts > 0) {
        showPasswordError(
          `Contraseña incorrecta. Te quedan ${attempts} intento${attempts === 1 ? "" : "s"}.`,
        );
      } else {
        showPasswordError(data.message || "Contraseña incorrecta.");
      }
      els.pwInput.select();
    } catch (_error) {
      showPasswordError("No se pudo comprobar la contraseña. Inténtalo de nuevo.");
    } finally {
      setPasswordBusy(false);
    }
  }

  // --------------------------------------------------------------- renderizado

  function renderJob(data) {
    state.jobId = data.job_id;
    state.status = data.status;
    state.kind = data.kind;
    state.filename = data.filename;
    state.pageCount = data.page_count || 0;
    state.pages = data.pages || [];
    state.blocks = (data.blocks || []).map((block) => ({
      ...block,
      text: block.text,
      originalText: block.text,
      included: true,
    }));
    state.warnings = data.warnings || [];
    state.previewHtml = data.preview_html || null;
    state.encryption = data.encryption || null;
    state.manualDirty = false;
    state.history = [];
    state.future = [];
    state.search = "";
    state.blockMap = new Map(state.blocks.map((block) => [block.id, block]));
    state.rowMap = new Map();
    state.overlayMap = new Map();
    state.docxMap = new Map();

    els.search.value = "";
    els.searchStatus.textContent = "";
    els.result.value = "";
    els.manualNote.hidden = true;
    els.btnExport.disabled = false;
    els.btnNew.hidden = false;
    els.uploadView.hidden = true;
    els.workspace.hidden = false;
    hideUploadError();

    renderHeader();
    renderWarnings();
    renderDocument();
    renderBlocks();
    updateStats();
    updateResult();
    updateHistoryButtons();
    setPane("doc");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function renderHeader() {
    els.docKind.textContent = state.kind === "pdf" ? "PDF" : "DOCX";
    els.docName.textContent = state.filename || "Documento";
    els.docName.title = state.filename || "";

    const meta = [];
    if (state.kind === "pdf") {
      meta.push(`${state.pageCount} página${state.pageCount === 1 ? "" : "s"}`);
    } else {
      meta.push("Documento de Word");
    }
    if (state.encryption) meta.push("cifrado y desbloqueado");
    meta.push(`${state.blocks.length} bloques`);
    els.docMeta.textContent = meta.join(" · ");
  }

  function renderWarnings() {
    els.warnings.innerHTML = "";
    if (!state.warnings.length) {
      els.warnings.hidden = true;
      return;
    }
    state.warnings.forEach((warning) => {
      const item = document.createElement("p");
      item.className = "warning";
      item.textContent = warning;
      els.warnings.appendChild(item);
    });
    els.warnings.hidden = false;
  }

  function renderDocument() {
    els.pdfView.innerHTML = "";
    els.docxView.innerHTML = "";
    els.docxView.hidden = true;
    els.pdfView.hidden = false;
    els.docEmpty.hidden = true;

    if (state.kind === "pdf") {
      renderPdf();
    } else if (state.kind === "docx") {
      renderDocx();
    } else {
      els.docEmpty.hidden = false;
    }
  }

  function renderPdf() {
    if (!state.pages.length) {
      els.pdfView.hidden = true;
      els.docEmpty.hidden = false;
      return;
    }

    const byPage = new Map();
    state.blocks.forEach((block) => {
      if (!block.bbox) return;
      if (!byPage.has(block.page)) byPage.set(block.page, []);
      byPage.get(block.page).push(block);
    });

    const fragment = document.createDocumentFragment();
    state.pages.forEach((page) => {
      const wrapper = document.createElement("div");
      wrapper.className = "pdf-page";
      wrapper.dataset.page = String(page.number);
      wrapper.style.aspectRatio = `${page.width} / ${page.height}`;

      const image = document.createElement("img");
      image.loading = "lazy";
      image.decoding = "async";
      image.alt = `Página ${page.number}`;
      image.src = `/api/jobs/${encodeURIComponent(state.jobId)}/pages/${page.number}.png`;
      wrapper.appendChild(image);

      (byPage.get(page.number) || []).forEach((block) => {
        const overlay = document.createElement("button");
        overlay.type = "button";
        overlay.className = "block-overlay";
        overlay.dataset.id = block.id;
        overlay.style.left = `${(block.bbox[0] * 100).toFixed(3)}%`;
        overlay.style.top = `${(block.bbox[1] * 100).toFixed(3)}%`;
        overlay.style.width = `${((block.bbox[2] - block.bbox[0]) * 100).toFixed(3)}%`;
        overlay.style.height = `${((block.bbox[3] - block.bbox[1]) * 100).toFixed(3)}%`;
        overlay.title = truncate(block.text, 180);
        overlay.setAttribute(
          "aria-label",
          `${KIND_LABELS[block.kind] || "Bloque"} de la página ${block.page}: ${truncate(block.text, 80)}`,
        );
        overlay.addEventListener("click", () => toggleBlock(block.id));
        state.overlayMap.set(block.id, overlay);
        wrapper.appendChild(overlay);
      });

      fragment.appendChild(wrapper);
    });

    els.pdfView.appendChild(fragment);
    syncDocumentClasses();
  }

  function renderDocx() {
    els.pdfView.hidden = true;
    els.docxView.hidden = false;

    if (!state.previewHtml) {
      els.docxView.hidden = true;
      els.docEmpty.hidden = false;
      return;
    }

    els.docxView.innerHTML = state.previewHtml;
    $$("[data-block-id]", els.docxView).forEach((element) => {
      const id = element.dataset.blockId;
      state.docxMap.set(id, element);
      element.addEventListener("click", () => {
        const selection = window.getSelection();
        if (selection && selection.toString().length > 0) return;
        toggleBlock(id);
      });
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggleBlock(id);
        }
      });
    });
    syncDocumentClasses();
  }

  function syncDocumentClasses() {
    state.blocks.forEach((block) => {
      const excluded = !block.included;
      const overlay = state.overlayMap.get(block.id);
      if (overlay) overlay.classList.toggle("is-excluded", excluded);
      const docx = state.docxMap.get(block.id);
      if (docx) {
        docx.classList.toggle("is-excluded", excluded);
        docx.setAttribute("aria-pressed", String(!excluded));
      }
    });
  }

  function renderBlocks() {
    els.blockList.innerHTML = "";
    state.rowMap = new Map();
    const fragment = document.createDocumentFragment();

    state.blocks.forEach((block) => {
      const row = document.createElement("div");
      row.className = "block-row";
      row.dataset.id = block.id;
      row.tabIndex = 0;

      const check = document.createElement("button");
      check.type = "button";
      check.className = "check";
      check.setAttribute("role", "checkbox");
      check.setAttribute("aria-checked", String(block.included));
      check.setAttribute("aria-label", "Incluir bloque en el TXT");
      check.textContent = "✓";

      const main = document.createElement("div");
      main.className = "block-main";

      const meta = document.createElement("div");
      meta.className = "block-meta";

      const kind = document.createElement("span");
      kind.className = `kind kind-${block.kind}`;
      kind.textContent = KIND_LABELS[block.kind] || "Texto";
      meta.appendChild(kind);

      if (block.page > 0) {
        const page = document.createElement("span");
        page.className = "page-tag";
        page.textContent = `p. ${block.page}`;
        meta.appendChild(page);
      }

      if (block.suggested && block.reason) {
        const suggest = document.createElement("span");
        suggest.className = "suggest-tag";
        suggest.textContent = block.reason;
        meta.appendChild(suggest);
      }

      const text = document.createElement("p");
      text.className = "block-text";
      text.textContent = block.text;

      const actions = document.createElement("div");
      actions.className = "row-actions";

      const locate = document.createElement("button");
      locate.type = "button";
      locate.className = "mini-btn";
      locate.dataset.action = "locate";
      locate.title = "Ver en el documento";
      locate.setAttribute("aria-label", "Ver este bloque en el documento");
      locate.textContent = "◎";

      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "mini-btn";
      edit.dataset.action = "edit";
      edit.title = "Editar este bloque";
      edit.setAttribute("aria-label", "Editar el texto de este bloque");
      edit.textContent = "✎";

      actions.append(locate, edit);
      main.append(meta, text);
      row.append(check, main, actions);
      fragment.appendChild(row);
      state.rowMap.set(block.id, row);
    });

    els.blockList.appendChild(fragment);

    syncBlockClasses();
    applySearch();
  }

  function onBlockListClick(event) {
    const action = event.target.closest("[data-action]");
    const row = event.target.closest(".block-row");
    if (!row) return;
    const id = row.dataset.id;
    if (action) {
      event.stopPropagation();
      if (action.dataset.action === "edit") startEdit(id);
      else locateBlock(id);
      return;
    }
    if (event.target.closest("textarea")) return;
    toggleBlock(id);
  }

  function onBlockListKeydown(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest("button, textarea")) return;
    const row = event.target.closest(".block-row");
    if (!row) return;
    event.preventDefault();
    toggleBlock(row.dataset.id);
  }

  function syncBlockClasses() {
    state.blocks.forEach((block) => {
      const row = state.rowMap.get(block.id);
      if (!row) return;
      row.classList.toggle("is-excluded", !block.included);
      const check = $(".check", row);
      if (check) check.setAttribute("aria-checked", String(block.included));
    });
    syncDocumentClasses();
  }

  function syncBlockUI(block) {
    const row = state.rowMap.get(block.id);
    if (row) {
      row.classList.toggle("is-excluded", !block.included);
      const check = $(".check", row);
      if (check) check.setAttribute("aria-checked", String(block.included));
      const text = $(".block-text", row);
      if (text) text.textContent = block.text;
    }
    const overlay = state.overlayMap.get(block.id);
    if (overlay) overlay.classList.toggle("is-excluded", !block.included);
    const docx = state.docxMap.get(block.id);
    if (docx) {
      docx.classList.toggle("is-excluded", !block.included);
      docx.setAttribute("aria-pressed", String(block.included));
    }
  }

  // ------------------------------------------------------------------ acciones

  function toggleBlock(id) {
    const block = state.blockMap.get(id);
    if (!block) return;
    pushHistory();
    block.included = !block.included;
    syncBlockUI(block);
    updateStats();
    updateResult();
  }

  function setAll(included) {
    const changed = state.blocks.some((block) => block.included !== included);
    if (!changed) return;
    pushHistory();
    state.blocks.forEach((block) => {
      block.included = included;
    });
    syncBlockClasses();
    updateStats();
    updateResult();
  }

  function applySuggestions() {
    const candidates = state.blocks.filter((block) => block.suggested && block.included);
    if (!candidates.length) {
      showToast("No hay sugerencias pendientes");
      return;
    }
    pushHistory();
    candidates.forEach((block) => {
      block.included = false;
    });
    syncBlockClasses();
    updateStats();
    updateResult();
    showToast(`${candidates.length} bloque${candidates.length === 1 ? "" : "s"} excluido${candidates.length === 1 ? "" : "s"}`);
  }

  function locateBlock(id) {
    setPane("doc");
    requestAnimationFrame(() => {
      const target =
        state.kind === "pdf" ? state.overlayMap.get(id) : state.docxMap.get(id);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        flash(target);
      }
      const row = state.rowMap.get(id);
      if (row) flash(row);
    });
  }

  function startEdit(id) {
    const block = state.blockMap.get(id);
    const row = state.rowMap.get(id);
    if (!block || !row || row.classList.contains("is-editing")) return;
    row.classList.add("is-editing");
    const paragraph = $(".block-text", row);
    if (!paragraph) return;

    const textarea = document.createElement("textarea");
    textarea.className = "block-edit";
    textarea.value = block.text;
    paragraph.insertAdjacentElement("afterend", textarea);
    textarea.focus();
    textarea.select();

    let done = false;
    const finish = (save) => {
      if (done) return;
      done = true;
      row.classList.remove("is-editing");
      const value = textarea.value;
      textarea.remove();
      if (save && value !== block.text) {
        pushHistory();
        block.text = value;
        paragraph.textContent = value;
        updateStats();
        updateResult();
        applySearch();
        showToast("Bloque actualizado");
      } else {
        paragraph.textContent = block.text;
      }
    };

    textarea.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        finish(false);
      } else if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        finish(true);
      }
    });
    textarea.addEventListener("blur", () => finish(true), { once: true });
  }

  // ------------------------------------------------------------------ historial

  function snapshot() {
    return {
      blocks: state.blocks.map((block) => ({
        id: block.id,
        included: block.included,
        text: block.text,
      })),
      manualDirty: state.manualDirty,
      manualText: state.manualDirty ? els.result.value : null,
    };
  }

  function pushHistory() {
    state.history.push(snapshot());
    if (state.history.length > MAX_HISTORY) state.history.shift();
    state.future = [];
    updateHistoryButtons();
  }

  function restore(snap) {
    snap.blocks.forEach((item) => {
      const block = state.blockMap.get(item.id);
      if (!block) return;
      block.included = item.included;
      block.text = item.text;
    });
    state.manualDirty = Boolean(snap.manualDirty);
    state.blocks.forEach((block) => {
      const row = state.rowMap.get(block.id);
      const text = row && $(".block-text", row);
      if (text) text.textContent = block.text;
    });
    syncBlockClasses();
    updateStats();
    updateHistoryButtons();
    if (state.manualDirty) {
      els.result.value = snap.manualText || "";
      els.manualNote.hidden = false;
      updateResultStats();
    } else {
      els.manualNote.hidden = true;
      updateResult(true);
    }
    syncBlockClasses();
  }

  function undo() {
    if (!state.history.length) return;
    state.future.push(snapshot());
    const snap = state.history.pop();
    restore(snap);
  }

  function redo() {
    if (!state.future.length) return;
    state.history.push(snapshot());
    const snap = state.future.pop();
    restore(snap);
  }

  function updateHistoryButtons() {
    els.btnUndo.disabled = state.history.length === 0;
    els.btnRedo.disabled = state.future.length === 0;
  }

  // ------------------------------------------------------------------ resultado

  function buildText() {
    const options = state.options;
    const separators = { none: "\n", single: "\n\n", double: "\n\n\n" };
    const separator = separators[options.paragraph_sep] || "\n\n";
    const pieces = [];
    let previousKind = null;

    state.blocks.forEach((block) => {
      if (!block.included) return;
      let text = normalizeText(block.text);
      if (!text) return;

      if (options.join_hyphenated) {
        text = text.replace(/(\p{L})-\n(?=\p{L})/gu, "$1");
      }

      if (block.kind === "heading") {
        if (options.heading_style === "upper") {
          text = text.toUpperCase();
        } else if (options.heading_style === "markdown") {
          const level = Math.min(6, Math.max(1, parseInt(block.meta && block.meta.level, 10) || 1));
          text = `${"#".repeat(level)} ${text}`;
        }
      } else if (block.kind === "list") {
        const hasBullet = LIST_RE.test(text);
        const plain = text.replace(LIST_RE, "").trimStart();
        if (options.list_prefix === "none") {
          text = plain;
        } else if (options.list_prefix === "dash") {
          text = plain ? `- ${plain}` : "";
        } else if (!hasBullet && block.meta && block.meta.needs_bullet) {
          text = `- ${text}`;
        }
      } else if (block.kind === "table") {
        if (options.table_sep === "pipe") text = text.replace(/\t/g, " | ");
        else if (options.table_sep === "newline") text = text.replace(/\t/g, "\n");
      }

      text = text.trim();
      if (!text) return;
      const joiner = previousKind === "list" && block.kind === "list" ? "\n" : separator;
      pieces.push({ text, joiner });
      previousKind = block.kind;
    });

    let output = "";
    pieces.forEach((piece, index) => {
      if (index > 0) output += piece.joiner;
      output += piece.text;
    });
    output = normalizeText(output).replace(/\n{4,}/g, "\n\n\n");
    return output ? `${output}\n` : "";
  }

  function updateResult(force = false) {
    if (!state.manualDirty || force) {
      els.result.value = buildText();
    }
    els.manualNote.hidden = !state.manualDirty;
    updateResultStats();
  }

  function updateResultStats() {
    const text = els.result.value;
    const trimmed = text.trim();
    const words = trimmed ? trimmed.split(/\s+/).length : 0;
    const chars = text.length;
    els.resultStats.textContent = `${words.toLocaleString("es")} palabras · ${chars.toLocaleString("es")} caracteres`;
  }

  function updateStats() {
    const total = state.blocks.length;
    const included = state.blocks.filter((block) => block.included).length;
    const suggestions = state.blocks.filter((block) => block.suggested && block.included).length;
    els.docStats.textContent = `${included} de ${total} bloque${total === 1 ? "" : "s"}`;
    els.blockCount.textContent = String(total);
    els.suggestCount.textContent = String(suggestions);
    els.btnSuggest.hidden = suggestions === 0;
    updateResultStats();
  }

  function applySearch() {
    const query = state.search.trim().toLowerCase();
    let visible = 0;
    state.blocks.forEach((block) => {
      const row = state.rowMap.get(block.id);
      if (!row) return;
      const matches = !query || block.text.toLowerCase().includes(query);
      row.classList.toggle("is-hidden", !matches);
      if (matches) visible += 1;
    });
    els.searchStatus.textContent = query
      ? `${visible} de ${state.blocks.length} coinciden`
      : "";
  }

  // ------------------------------------------------------------------ opciones

  function readOptions() {
    state.options = {
      paragraph_sep: els.optSep.value,
      list_prefix: els.optList.value,
      table_sep: els.optTable.value,
      heading_style: els.optHeading.value,
      join_hyphenated: els.optHyphen.checked,
      encoding: els.optEncoding.value,
      newline: els.optNewline.value,
    };
    saveOptions();
    updateResult();
  }

  function applyOptionsToControls() {
    const options = state.options;
    els.optSep.value = options.paragraph_sep;
    els.optList.value = options.list_prefix;
    els.optTable.value = options.table_sep;
    els.optHeading.value = options.heading_style;
    els.optHyphen.checked = Boolean(options.join_hyphenated);
    els.optEncoding.value = options.encoding;
    els.optNewline.value = options.newline;
  }

  // ------------------------------------------------------------------ exportar

  function filenameFromDisposition(header) {
    if (!header) return null;
    const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
    if (encoded) {
      try {
        return decodeURIComponent(encoded[1]);
      } catch (_error) {
        /* continúa */
      }
    }
    const plain = /filename="?([^";]+)"?/i.exec(header);
    return plain ? plain[1] : null;
  }

  async function exportTxt() {
    if (!state.jobId || state.status !== "ready") return;

    const payload = {
      included: state.blocks.filter((block) => block.included).map((block) => block.id),
      edits: {},
      options: { ...state.options },
    };
    state.blocks.forEach((block) => {
      if (block.text !== block.originalText) payload.edits[block.id] = block.text;
    });
    if (state.manualDirty) payload.text_override = els.result.value;

    els.btnExport.disabled = true;
    try {
      const response = await fetch(
        `/api/jobs/${encodeURIComponent(state.jobId)}/export`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.message || "No se pudo exportar el TXT.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download =
        filenameFromDisposition(response.headers.get("Content-Disposition")) ||
        `${(state.filename || "documento").replace(/\.(pdf|docx)$/i, "")}.txt`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
      showToast("TXT descargado");
    } catch (error) {
      showToast(error.message || "No se pudo exportar el TXT.");
    } finally {
      els.btnExport.disabled = false;
    }
  }

  // ------------------------------------------------------------------ reinicio

  function resetToUpload() {
    const jobId = state.jobId;
    closePasswordModal(false);
    state.jobId = null;
    state.status = null;
    state.kind = null;
    state.filename = null;
    state.pageCount = 0;
    state.pages = [];
    state.blocks = [];
    state.warnings = [];
    state.previewHtml = null;
    state.encryption = null;
    state.history = [];
    state.future = [];
    state.manualDirty = false;
    state.blockMap = new Map();
    state.rowMap = new Map();
    state.overlayMap = new Map();
    state.docxMap = new Map();
    state.search = "";
    els.workspace.hidden = true;
    els.uploadView.hidden = false;
    els.btnNew.hidden = true;
    els.btnExport.disabled = true;
    els.pdfView.innerHTML = "";
    els.docxView.innerHTML = "";
    els.blockList.innerHTML = "";
    els.result.value = "";
    els.search.value = "";
    els.searchStatus.textContent = "";
    els.fileInput.value = "";
    hideUploadError();
    setPane("doc");
    if (jobId) {
      fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" }).catch(() => {});
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function newDocument() {
    if (state.jobId && !window.confirm("¿Cerrar este documento? Se perderán los cambios.")) {
      return;
    }
    resetToUpload();
  }

  // ------------------------------------------------------------------ eventos

  function bindEvents() {
    els.dropzone.addEventListener("click", () => els.fileInput.click());
    els.dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        els.fileInput.click();
      }
    });
    els.fileInput.addEventListener("change", () => {
      const file = els.fileInput.files && els.fileInput.files[0];
      handleFile(file);
      els.fileInput.value = "";
    });

    ["dragenter", "dragover"].forEach((name) => {
      els.dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        els.dropzone.classList.add("is-dragging");
      });
    });
    ["dragleave", "dragend"].forEach((name) => {
      els.dropzone.addEventListener(name, () => {
        els.dropzone.classList.remove("is-dragging");
      });
    });
    els.dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      els.dropzone.classList.remove("is-dragging");
      const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
      handleFile(file);
    });
    window.addEventListener("dragover", (event) => event.preventDefault());
    window.addEventListener("drop", (event) => {
      if (!els.dropzone.contains(event.target)) event.preventDefault();
    });

    els.blockList.addEventListener("click", onBlockListClick);
    els.blockList.addEventListener("keydown", onBlockListKeydown);
    els.btnNew.addEventListener("click", newDocument);
    els.btnExport.addEventListener("click", exportTxt);
    els.btnAll.addEventListener("click", () => setAll(true));
    els.btnNone.addEventListener("click", () => setAll(false));
    els.btnSuggest.addEventListener("click", applySuggestions);
    els.btnUndo.addEventListener("click", undo);
    els.btnRedo.addEventListener("click", redo);
    els.search.addEventListener("input", () => {
      state.search = els.search.value;
      applySearch();
    });

    [els.optSep, els.optList, els.optTable, els.optHeading, els.optEncoding, els.optNewline].forEach(
      (select) => select.addEventListener("change", readOptions),
    );
    els.optHyphen.addEventListener("change", readOptions);

    els.result.addEventListener("input", () => {
      state.manualDirty = true;
      els.manualNote.hidden = false;
      updateResultStats();
    });
    els.btnRegenerate.addEventListener("click", () => {
      state.manualDirty = false;
      els.manualNote.hidden = true;
      updateResult(true);
      showToast("Texto regenerado desde los bloques");
    });

    $$(".pane-tabs button").forEach((button) => {
      button.addEventListener("click", () => setPane(button.dataset.paneTarget));
    });

    els.pwForm.addEventListener("submit", submitPassword);
    els.pwClose.addEventListener("click", () => closePasswordModal(true));
    els.pwToggle.addEventListener("click", () => {
      const showing = els.pwInput.type === "text";
      els.pwInput.type = showing ? "password" : "text";
      els.pwToggle.textContent = showing ? "Ver" : "Ocultar";
      els.pwInput.focus();
    });
    els.pwModal.addEventListener("click", (event) => {
      if (event.target === els.pwModal) closePasswordModal(true);
    });

    document.addEventListener("keydown", (event) => {
      if (!els.pwModal.hidden) {
        if (event.key === "Escape") closePasswordModal(true);
        return;
      }
      const active = document.activeElement;
      const typing =
        active &&
        (["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName) || active.isContentEditable);
      if (typing) return;
      const key = event.key.toLowerCase();
      if ((event.ctrlKey || event.metaKey) && key === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
      }
    });
  }

  function init() {
    applyOptionsToControls();
    bindEvents();
    els.btnNew.hidden = true;
    els.btnExport.disabled = true;
    els.workspace.hidden = true;
  }

  init();
})();
