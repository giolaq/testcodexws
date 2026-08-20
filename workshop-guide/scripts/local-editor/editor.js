const state = {
  snapshot: null,
  selected: null,
  previewNode: null,
  previewElement: null,
  originalPreviewOutline: "",
  saving: false,
};

const elements = {
  connection: document.querySelector("#connection"),
  discard: document.querySelector("#discard"),
  empty: document.querySelector("#selection-empty"),
  editor: document.querySelector("#selection-editor"),
  count: document.querySelector("#character-count"),
  preview: document.querySelector("#preview"),
  reload: document.querySelector("#reload-preview"),
  resultCount: document.querySelector("#result-count"),
  resultList: document.querySelector("#result-list"),
  results: document.querySelector("#search-results"),
  save: document.querySelector("#save"),
  search: document.querySelector("#search"),
  section: document.querySelector("#selection-section"),
  tag: document.querySelector("#selection-tag"),
  toast: document.querySelector("#toast"),
  undo: document.querySelector("#undo"),
  value: document.querySelector("#copy-value"),
};

function normalize(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function sectionLabel(value) {
  if (!value || value === "page") return "Page chrome";
  return value.replace(/-/g, " ");
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("visible"), 2600);
}

async function api(path, options) {
  const response = await fetch(`/__workshop_editor/api/${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "The editor request failed.");
  return payload;
}

async function loadContent() {
  try {
    state.snapshot = await api("content");
    elements.connection.classList.add("ready");
    elements.connection.lastChild.textContent = " Ready";
    elements.undo.disabled = !state.snapshot.canUndo;
    renderResults();
  } catch (error) {
    showToast(error.message);
  }
}

function clearHighlight() {
  if (state.previewElement) {
    state.previewElement.style.outline = state.originalPreviewOutline;
    state.previewElement.style.outlineOffset = "";
  }
  state.previewElement = null;
  state.previewNode = null;
}

function previewRoot(entry) {
  const previewDocument = elements.preview.contentDocument;
  if (!previewDocument) return null;
  return entry.section && entry.section !== "page"
    ? previewDocument.getElementById(entry.section)
    : previewDocument.body;
}

function findPreviewNode(entry) {
  if (!entry.previewSelector) return null;
  const root = previewRoot(entry);
  if (!root) return null;
  const matches = [];
  for (const candidate of root.querySelectorAll(entry.previewSelector)) {
    for (const child of candidate.childNodes) {
      if (child.nodeType === Node.TEXT_NODE && normalize(child.nodeValue) === entry.value) {
        matches.push({ node: child, element: candidate });
      }
    }
  }
  return matches[entry.occurrence] || matches[0] || null;
}

function updateSaveState() {
  const dirty = Boolean(state.selected) && elements.value.value.trim() !== state.selected.value;
  elements.save.disabled = !dirty || state.saving;
  elements.count.textContent = `${elements.value.value.length} character${elements.value.value.length === 1 ? "" : "s"}`;
}

function selectEntry(entry, focus = true) {
  if (!entry) return;
  clearHighlight();
  state.selected = entry;
  elements.empty.hidden = true;
  elements.editor.hidden = false;
  elements.section.textContent = sectionLabel(entry.section);
  elements.tag.textContent = entry.kind === "attribute" ? `${entry.tag} · ${entry.attribute}` : `<${entry.tag}>`;
  elements.value.value = entry.value;
  updateSaveState();

  const previewMatch = findPreviewNode(entry);
  if (previewMatch) {
    state.previewNode = previewMatch.node;
    state.previewElement = previewMatch.element;
    state.originalPreviewOutline = previewMatch.element.style.outline;
    previewMatch.element.style.outline = "2px solid #0b57d0";
    previewMatch.element.style.outlineOffset = "4px";
    previewMatch.element.scrollIntoView({ behavior: "smooth", block: "center" });
  } else if (entry.section && entry.section !== "page") {
    previewRoot(entry)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (focus) {
    elements.value.focus();
    elements.value.setSelectionRange(elements.value.value.length, elements.value.value.length);
  }
}

function discardDraft() {
  if (!state.selected) return;
  elements.value.value = state.selected.value;
  if (state.previewNode) state.previewNode.nodeValue = state.selected.value;
  updateSaveState();
}

function renderResults() {
  const query = normalize(elements.search.value).toLocaleLowerCase();
  if (!state.snapshot || query.length < 2) {
    elements.results.hidden = true;
    elements.resultList.replaceChildren();
    return;
  }

  const terms = query.split(" ").filter(Boolean);
  const matches = state.snapshot.entries
    .filter((entry) => {
      const haystack = `${entry.section} ${entry.value}`.toLocaleLowerCase();
      return terms.every((term) => haystack.includes(term));
    })
    .slice(0, 40);

  elements.results.hidden = false;
  elements.resultCount.textContent = matches.length === 40 ? "First 40" : String(matches.length);
  elements.resultList.replaceChildren(...matches.map((entry) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-button";
    const text = document.createElement("span");
    text.textContent = entry.value;
    const context = document.createElement("small");
    context.textContent = `${sectionLabel(entry.section)} · ${entry.kind === "attribute" ? entry.attribute : entry.tag}`;
    button.append(text, context);
    button.addEventListener("click", () => selectEntry(entry));
    return button;
  }));
}

function candidateEntries(target) {
  if (!state.snapshot) return [];
  let element = target?.nodeType === 1 ? target : target?.parentElement;
  const candidates = [];
  for (let depth = 0; element && depth < 4; depth += 1, element = element.parentElement) {
    const section = element.closest("section[id]")?.id || "page";
    for (const child of element.childNodes) {
      if (child.nodeType !== Node.TEXT_NODE) continue;
      const value = normalize(child.nodeValue);
      if (!value) continue;
      const entry = state.snapshot.entries.find(
        (item) => item.section === section
          && item.value === value
          && item.previewSelector
          && (item.previewSelector === "*" || element.matches(item.previewSelector)),
      );
      if (entry) candidates.push(entry);
    }
    if (candidates.length) break;
  }
  return candidates;
}

function attachPreviewEditing() {
  const previewDocument = elements.preview.contentDocument;
  if (!previewDocument) return;
  previewDocument.addEventListener("click", (event) => {
    const entries = candidateEntries(event.target);
    if (!entries.length) return;
    event.preventDefault();
    event.stopPropagation();
    selectEntry(entries[0]);
  }, true);
  if (state.selected) {
    const matching = state.snapshot?.entries.find(
      (entry) => entry.section === state.selected.section
        && entry.tag === state.selected.tag
        && entry.value === state.selected.value,
    );
    if (matching) selectEntry(matching, false);
  }
}

async function save() {
  if (!state.selected || elements.save.disabled) return;
  state.saving = true;
  updateSaveState();
  try {
    await api("save", {
      method: "POST",
      body: JSON.stringify({
        id: state.selected.id,
        version: state.snapshot.version,
        value: elements.value.value,
      }),
    });
    const selectedIdentity = {
      section: state.selected.section,
      tag: state.selected.tag,
      value: elements.value.value.trim(),
    };
    await loadContent();
    const updatedEntry = state.snapshot.entries.find(
      (entry) => entry.section === selectedIdentity.section
        && entry.tag === selectedIdentity.tag
        && entry.value === selectedIdentity.value,
    );
    state.selected = updatedEntry || null;
    elements.undo.disabled = false;
    showToast("Saved to the project. The preview is refreshing.");
    window.setTimeout(() => elements.preview.contentWindow.location.reload(), 450);
  } catch (error) {
    showToast(error.message);
  } finally {
    state.saving = false;
    updateSaveState();
  }
}

async function undo() {
  try {
    await api("undo", { method: "POST", body: "{}" });
    state.selected = null;
    clearHighlight();
    elements.editor.hidden = true;
    elements.empty.hidden = false;
    await loadContent();
    showToast("Last editor save undone.");
    window.setTimeout(() => elements.preview.contentWindow.location.reload(), 350);
  } catch (error) {
    showToast(error.message);
  }
}

elements.value.addEventListener("input", () => {
  if (state.previewNode) state.previewNode.nodeValue = elements.value.value;
  updateSaveState();
});
elements.search.addEventListener("input", renderResults);
elements.discard.addEventListener("click", discardDraft);
elements.save.addEventListener("click", save);
elements.undo.addEventListener("click", undo);
elements.reload.addEventListener("click", () => elements.preview.contentWindow.location.reload());
elements.preview.addEventListener("load", () => {
  // Let the preview finish React hydration before the editor adds highlights.
  window.setTimeout(attachPreviewEditing, 900);
});
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    save();
  }
});

loadContent();
