const STATES = ["Backlog", "Ready", "In Progress", "QA Review", "Verifying", "In Review", "Done", "Blocked"];
const app = {
  snapshot: null,
  view: location.hash.slice(1) || "overview",
  selectedPlanning: "",
  selectedTicket: null,
  drawerTab: "summary",
  artifactPath: "",
  loadedPlanningArtifact: "",
  prdLoaded: false,
  canvasLoaded: false,
  eventSource: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

async function request(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(value.error || `Request failed (${response.status})`);
  return value;
}

function toast(message, error = false) {
  const element = document.createElement("div");
  element.className = `toast${error ? " error" : ""}`;
  element.textContent = message;
  $("#toast-region").append(element);
  window.setTimeout(() => element.remove(), 4200);
}

function showView(name, updateHash = true) {
  if (!$(`[data-view="${name}"]`)) name = "overview";
  app.view = name;
  $$(".view").forEach((view) => {
    const active = view.dataset.view === name;
    view.hidden = !active;
    view.classList.toggle("active", active);
  });
  $$('[data-view-link]').forEach((link) => link.classList.toggle("active", link.dataset.viewLink === name));
  if (updateHash) history.replaceState(null, "", `#${name}`);
  closeSidebar();
  if (name === "prd") loadPrd();
  if (name === "evidence") loadCanvas();
  document.title = `${name[0].toUpperCase()}${name.slice(1)} · Factory Control Center`;
}

function openSidebar() {
  $("#sidebar").classList.add("open");
  $("#sidebar-scrim").hidden = false;
  $("#menu-button").setAttribute("aria-expanded", "true");
}

function closeSidebar() {
  $("#sidebar").classList.remove("open");
  $("#sidebar-scrim").hidden = true;
  $("#menu-button").setAttribute("aria-expanded", "false");
}

function mode() {
  return $("#connect-mode")?.value || $("#run-mode")?.value || $("#planning-mode")?.value || localStorage.getItem("factory-control-mode") || "rehearsal";
}

function setMode(value) {
  const next = value === "live" ? "live" : "rehearsal";
  localStorage.setItem("factory-control-mode", next);
  if ($("#connect-mode")) $("#connect-mode").value = next;
  if ($("#run-mode")) $("#run-mode").value = next;
  if ($("#planning-mode")) $("#planning-mode").value = next;
  $("#sidebar-mode").textContent = next;
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function section(body, title) {
  const match = String(body || "").match(new RegExp(`## ${title}\\s*\\n([\\s\\S]*?)(?=\\n## |$)`, "i"));
  return match?.[1]?.trim() || "Not provided.";
}

function populateAgentSelects(adapters, config) {
  $$('[data-agent-select]').forEach((select) => {
    const role = select.dataset.agentSelect;
    const allowed = role === "planning" ? adapters.filter((item) => ["claude", "codex"].includes(item)) : adapters.filter((item) => !["mock", "mock-qa"].includes(item));
    const previous = select.value || (role === "qa" ? config.qa_agent : role === "planning" ? config.planning_agent : config.agent) || "codex";
    select.innerHTML = allowed.map((item) => `<option value="${esc(item)}">${esc(item[0].toUpperCase() + item.slice(1))}</option>`).join("");
    if (allowed.includes(previous)) select.value = previous;
  });
}

function renderSnapshot(data) {
  app.snapshot = data;
  const repo = data.repo || {};
  $("#repo-name").textContent = repo.name || "Unknown repository";
  $("#repo-branch").textContent = repo.branch || "—";
  $("#repo-dot").className = `status-dot ${repo.dirty ? "warn" : "good"}`;
  $("#connection-label").textContent = "Connected";
  $("#connect-repo").textContent = repo.name || "—";
  $("#connect-branch").textContent = repo.branch || "—";
  $("#connect-remote").textContent = repo.remote || "No origin remote";
  $("#connect-dirty").textContent = repo.dirty ? "Uncommitted changes" : "Clean";

  const config = data.config || {};
  $("#sidebar-profile").textContent = config.profile || data.factory?.profile || "standard";
  $("#connect-project").textContent = config.project_number ? `#${config.project_number}` : "Automatic";
  populateAgentSelects(data.adapters || [], config);
  hydrateConfigForm(config);

  const tickets = data.factory?.tickets || [];
  const active = tickets.filter((ticket) => ["In Progress", "Verifying"].includes(ticket.status)).length;
  const waiting = tickets.filter((ticket) => ["QA Review", "In Review"].includes(ticket.status)).length;
  $("#metric-plan").textContent = data.planning?.project || "No plan";
  $("#metric-active").textContent = active;
  $("#metric-review").textContent = waiting;
  $("#metric-done").textContent = tickets.filter((ticket) => ticket.status === "Done").length;
  $("#state-updated").textContent = data.factory?.updated_at ? `Updated ${formatTime(data.factory.updated_at)}` : "Waiting for state";

  renderOperation(data.operation || {});
  renderJourney(data.journey || {});
  renderDecisions(data);
  renderPlanning(data.planning || {});
  renderTickets(data.factory || {});
  renderEvidence(data);
  if (app.selectedTicket) {
    const current = tickets.find((ticket) => Number(ticket.number) === Number(app.selectedTicket.number));
    if (current) {
      app.selectedTicket = current;
      if (!$("#ticket-drawer").hidden) renderDrawer();
    }
  }
}

function renderJourney(journey) {
  if (!journey.phases?.length) return;
  $("#journey-kicker").textContent = `Phase ${journey.phase_number} of ${journey.phase_count} · ${journey.phase_label}`;
  $("#journey-state").textContent = journey.state || "ready";
  $("#journey-state").className = `journey-state ${journey.state || "ready"}`;
  $("#journey-pulse").className = `now-pulse ${journey.state || "ready"}`;
  $("#journey-headline").textContent = journey.headline;
  $("#journey-detail").textContent = journey.detail;
  $("#journey-next-label").textContent = journey.next?.label || "Open current phase";
  $("#journey-next-detail").textContent = journey.next?.detail || "Continue with the current workshop phase.";
  $("#journey-next").textContent = journey.next?.label || "Open current phase";
  $("#global-next").textContent = `Next: ${journey.next?.label || journey.phase_label}`;
  $("#journey-steps").innerHTML = journey.phases.map((phase, index) => `<li class="journey-step ${esc(phase.status)}"><button type="button" data-journey-view="${esc(phase.view)}"><i>${phase.status === "complete" ? "✓" : index + 1}</i><b>${esc(phase.label)}</b><small>${esc(phase.description)}</small></button></li>`).join("");
  $$('[data-journey-view]').forEach((button) => button.addEventListener("click", () => showView(button.dataset.journeyView)));
}

function followJourney() {
  const journey = app.snapshot?.journey;
  if (!journey) return;
  showView(journey.next?.view || "overview");
  if (journey.ticket && journey.next?.view === "tickets") openTicket(journey.ticket);
}

let configHydrated = false;
function hydrateConfigForm(config) {
  if (configHydrated || !Object.keys(config).length) return;
  const form = $("#config-form");
  for (const [key, value] of Object.entries(config)) {
    const field = form.elements.namedItem(key);
    if (!field) continue;
    if (field.type === "checkbox") field.checked = Boolean(value);
    else field.value = value;
  }
  configHydrated = true;
}

function renderOperation(operation) {
  const status = operation.status || "idle";
  $("#operation-title").textContent = operation.title || "No operation running";
  const badge = $("#operation-status");
  badge.textContent = status;
  badge.className = `operation-status ${status}`;
  $("#operation-command").textContent = operation.command || "Actions show their exact CLI command here.";
  $("#operation-context").textContent = ["running", "stopping"].includes(status)
    ? "This is the active factory command. Output streams below until it finishes or is stopped."
    : status === "failed"
      ? "The command stopped at an error. Fix the first reported cause before repeating it."
      : status === "succeeded"
        ? "The command completed. The current phase and next checkpoint above have been updated."
        : "No command is running. Use the next checkpoint above.";
  const output = $("#operation-output");
  const newOutput = operation.output || "Select a workflow action to begin.";
  const nearBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 40;
  if (output.textContent !== newOutput) output.textContent = newOutput;
  if (nearBottom) output.scrollTop = output.scrollHeight;
  $("#stop-operation").hidden = !["running", "stopping"].includes(status);
  $$('[data-action]').forEach((button) => {
    if (button.dataset.action === "doctor") return;
    button.disabled = status === "running" || status === "stopping";
  });
}

function renderDecisions(data) {
  const planning = data.planning || {};
  const tickets = data.factory?.tickets || [];
  const decisions = [];
  const product = planning.stages?.find((stage) => stage.id === "product_review");
  if (product?.status === "complete" && !planning.approvals?.product) decisions.push({ title: "Approve Product Review", text: "Confirm the user outcome before technical planning.", view: "planning", planning: "product_gate" });
  if (planning.status === "awaiting_alignment_approval" && !planning.approvals?.alignment) decisions.push({ title: "Approve alignment", text: "Accept architecture, program design, and vertical slices.", view: "planning", planning: "alignment_gate" });
  tickets.filter((ticket) => ticket.status === "QA Review").forEach((ticket) => decisions.push({ title: `Approve tests for #${ticket.number}`, text: ticket.title, ticket }));
  tickets.filter((ticket) => ticket.status === "Blocked").forEach((ticket) => decisions.push({ title: `Resolve blocked #${ticket.number}`, text: ticket.failure || ticket.title, ticket }));
  $("#decision-list").innerHTML = decisions.length ? decisions.map((item, index) => `<article class="decision"><b>${esc(item.title)}</b><p>${esc(item.text)}</p><button class="button" type="button" data-decision="${index}">Review</button></article>`).join("") : '<p class="empty-state">No approvals are waiting.</p>';
  $$('[data-decision]').forEach((button) => button.addEventListener("click", () => {
    const item = decisions[Number(button.dataset.decision)];
    if (item.ticket) return openTicket(item.ticket.number);
    app.selectedPlanning = item.planning;
    showView(item.view);
    renderPlanning(app.snapshot.planning || {});
  }));
}

function planningSequence(planning) {
  const stages = planning.stages || [];
  if (!stages.length) return [];
  const productGate = { id: "product_gate", title: "Approve product", status: planning.approvals?.product ? "approved" : stages[0]?.status === "complete" ? "waiting" : "pending", gate: true };
  const alignmentGate = { id: "alignment_gate", title: "Approve alignment", status: planning.approvals?.alignment ? "approved" : planning.status === "awaiting_alignment_approval" ? "waiting" : "pending", gate: true };
  return [stages[0], productGate, ...stages.slice(1), alignmentGate];
}

function renderPlanning(planning) {
  $("#plan-id").textContent = planning.plan_id || "No plan";
  const sequence = planningSequence(planning);
  if (!app.selectedPlanning && sequence.length) app.selectedPlanning = sequence[0].id;
  $("#planning-pipeline").innerHTML = sequence.length ? sequence.map((item, index) => `<button type="button" class="planning-stage ${esc(item.status || "pending")} ${item.gate ? "gate" : ""} ${app.selectedPlanning === item.id ? "active" : ""}" data-planning-stage="${esc(item.id)}"><span class="stage-type">${item.gate ? "Human gate" : `Expert ${String(index + 1).padStart(2, "0")}`}</span><b>${esc(item.title)}</b><small>${esc((item.status || "pending").replaceAll("_", " "))}</small></button>`).join("") : '<div class="surface empty-state">Save a PRD and start Product Review.</div>';
  $$('[data-planning-stage]').forEach((button) => button.addEventListener("click", () => selectPlanning(button.dataset.planningStage)));
  const selected = sequence.find((item) => item.id === app.selectedPlanning);
  if (!selected) {
    $("#artifact-title").textContent = "Select a planning stage";
    $("#artifact-content").textContent = "The expert output will appear here.";
    $("#approval-panel").innerHTML = '<span class="section-label">Human gate</span><h2>Review before approval</h2><p>Select Product Review or Alignment to make a decision.</p>';
  } else if (selected.gate) {
    app.loadedPlanningArtifact = "";
    renderPlanningGate(selected, planning);
  } else {
    loadPlanningArtifact(selected);
  }

  const running = ["running", "stopping"].includes(app.snapshot?.operation?.status);
  $("#continue-plan").disabled = running || planning.status !== "product_approved";
  $("#publish-plan").disabled = running || planning.status !== "awaiting_alignment_approval";
}

async function loadPlanningArtifact(item) {
  const selectedId = item.id;
  const artifactKey = `${item.markdown || item.json || ""}:${item.sha256 || item.status || ""}`;
  if (app.loadedPlanningArtifact === artifactKey) return;
  app.loadedPlanningArtifact = artifactKey;
  $("#artifact-label").textContent = item.status || "Artifact";
  $("#artifact-title").textContent = item.title;
  $("#artifact-content").textContent = "Loading…";
  app.artifactPath = item.markdown || item.json || "";
  $("#open-artifact").hidden = !app.artifactPath;
  try {
    const value = await request(`/api/artifact?path=${encodeURIComponent(app.artifactPath)}`);
    if (app.selectedPlanning !== selectedId) return;
    $("#artifact-content").textContent = value.content;
  } catch (error) {
    if (app.selectedPlanning !== selectedId) return;
    $("#artifact-content").textContent = error.message;
  }
  if (app.selectedPlanning !== selectedId) return;
  $("#approval-panel").innerHTML = `<span class="section-label">Expert contract</span><h2>${esc(item.title)}</h2><p>${item.questions?.length ? `${item.questions.length} blocking question(s) must be resolved.` : "No blocking questions recorded."}</p><div class="approval-card"><b>Artifact hash</b><p><code>${esc(item.sha256 || "Pending")}</code></p></div>`;
}

function selectPlanning(id) {
  app.selectedPlanning = id;
  app.loadedPlanningArtifact = "";
  renderPlanning(app.snapshot?.planning || {});
}

function renderPlanningGate(item, planning) {
  $("#artifact-label").textContent = "Human decision";
  $("#artifact-title").textContent = item.title;
  $("#artifact-content").textContent = item.id === "product_gate" ? "Approve only when the problem, users, behavior, scope, and evidence are clear." : "Approve only when requirements trace to architecture, program design, tickets, and QA evidence.";
  $("#open-artifact").hidden = true;
  const approved = item.status === "approved";
  if (approved) {
    $("#approval-panel").innerHTML = `<span class="section-label">Human gate</span><h2>${esc(item.title)}</h2><div class="safety-note"><b>Approved</b><p>This decision and its artifact hashes are recorded in the plan manifest.</p></div>`;
    return;
  }
  if (item.id === "product_gate") {
    $("#approval-panel").innerHTML = `<span class="section-label">Human gate</span><h2>Product Review</h2><p>Approve the outcome or send focused feedback to the product expert.</p><div class="approval-card"><label>Revision feedback<textarea id="product-feedback" placeholder="Describe what must become clearer or testable."></textarea></label><div class="approval-actions"><button class="button" type="button" id="revise-product">Request revision</button><button class="button button-primary" type="button" id="approve-product">Approve product</button></div></div>`;
    $("#revise-product").addEventListener("click", () => action("revise-product", { feedback: $("#product-feedback").value }));
    $("#approve-product").addEventListener("click", () => action("approve-product"));
  } else {
    $("#approval-panel").innerHTML = `<span class="section-label">Human gate</span><h2>Alignment</h2><p>Publishing creates the approved vertical slices as ${mode() === "live" ? "GitHub issues" : "local rehearsal tickets"}.</p><div class="approval-card"><label>New GitHub Project title<input id="project-title" value="TableStory Workshop" ${mode() === "live" ? "" : "disabled"}></label><div class="approval-actions"><button class="button button-primary" type="button" id="approve-alignment">Approve and create tickets</button></div></div>`;
    $("#approve-alignment").addEventListener("click", () => action("publish-plan", { project_title: $("#project-title").value }));
  }
}

function renderTickets(factory) {
  const tickets = factory.tickets || [];
  $("#state-summary").innerHTML = STATES.map((state) => `<span>${esc(state)} ${tickets.filter((ticket) => ticket.status === state).length}</span>`).join("");
  $("#ticket-board").innerHTML = STATES.map((state) => {
    const items = tickets.filter((ticket) => ticket.status === state);
    const cards = items.map((ticket) => `<button class="ticket-card" type="button" data-ticket="${ticket.number}"><div class="ticket-top"><span class="ticket-number">#${ticket.number}</span><span>${esc(ticket.agent || "unassigned")}</span></div><h3>${esc(ticket.title)}</h3><div class="ticket-meta"><div><b>${esc(ticket.phase || ticket.status)}</b><span>Attempt ${ticket.attempt || 0}</span></div><div><span>Needs</span><span class="dependency-list">${ticket.dependencies?.length ? ticket.dependencies.map((number) => `<i>#${number}</i>`).join("") : "None"}</span></div></div></button>`).join("");
    return `<section class="ticket-column"><header><h2>${esc(state)}</h2><span>${items.length}</span></header><div class="ticket-cards">${cards || '<p class="ticket-empty">No tickets</p>'}</div></section>`;
  }).join("");
  $$('[data-ticket]').forEach((card) => card.addEventListener("click", () => openTicket(Number(card.dataset.ticket))));
}

function renderEvidence(data) {
  const tickets = data.factory?.tickets || [];
  const requiredGatesPass = tickets.length > 0 && tickets.every((ticket) => {
    const required = (ticket.gate_results || []).filter((gate) => gate.required);
    return required.length > 0 && required.every((gate) => gate.exit_code === 0);
  });
  const checks = [
    [Boolean(data.planning?.approvals?.product), "Product intent approved", "Problem and behavior accepted by a person"],
    [Boolean(data.planning?.approvals?.alignment), "Delivery plan approved", "Architecture and slices accepted"],
    [tickets.length > 0 && tickets.every((ticket) => Object.keys(ticket.qa_tests || {}).length), "Acceptance tests recorded", "Independent QA evidence exists for every ticket"],
    [requiredGatesPass, "Required gates pass", "Every ticket has a successful required gate"],
    [tickets.length > 0 && tickets.every((ticket) => ticket.status === "Done"), "All tickets complete", "Integrated delivery has no unfinished work"],
  ];
  $("#evidence-checks").innerHTML = checks.map(([complete, title, text]) => `<div class="evidence-check ${complete ? "complete" : ""}"><span>${complete ? "✓" : "·"}</span><div><b>${esc(title)}</b><small>${esc(text)}</small></div></div>`).join("");
  $("#evidence-files").innerHTML = data.evidence?.length ? data.evidence.map((file) => `<button class="file-item text-button" type="button" data-artifact="${esc(file.path)}"><span>FILE</span><div><b>${esc(file.name)}</b><small>${Math.ceil(file.size / 1024)} KB · ${formatTime(file.updated_at)}</small></div><i>Open</i></button>`).join("") : '<p class="empty-state">No evidence packet generated yet.</p>';
  $$('[data-artifact]', $("#evidence-files")).forEach((button) => button.addEventListener("click", () => openArtifact(button.dataset.artifact)));
}

async function loadPrd() {
  if (app.prdLoaded) return;
  try {
    const value = await request("/api/prd");
    $("#prd-editor").value = value.text;
    $("#prd-save-state").textContent = value.saved ? `Saved as ${value.path}` : `Loaded ${value.path}`;
    app.prdLoaded = true;
  } catch (error) {
    toast(error.message, true);
  }
}

async function savePrd() {
  const value = await request("/api/prd", { method: "PUT", body: JSON.stringify({ text: $("#prd-editor").value }) });
  $("#prd-save-state").textContent = `Saved as ${value.path}`;
  return value;
}

async function loadCanvas() {
  if (app.canvasLoaded) return;
  try {
    const value = await request("/api/canvas");
    $("#canvas-text").value = value.text;
    $("#canvas-save-state").textContent = value.saved ? "Canvas saved" : "Complete the canvas before export";
    app.canvasLoaded = true;
  } catch (error) { toast(error.message, true); }
}

async function saveCanvas() {
  const value = await request("/api/canvas", { method: "PUT", body: JSON.stringify({ text: $("#canvas-text").value }) });
  $("#canvas-save-state").textContent = "Canvas saved";
  return value;
}

function basePayload(extra = {}) {
  return {
    mode: mode(),
    scenario: "recipe-rebrand",
    plan_id: app.snapshot?.planning?.plan_id || "",
    review_qa_tests: app.snapshot?.config?.review_qa_tests ?? true,
    ...extra,
  };
}

async function action(name, extra = {}) {
  try {
    const destructive = ["publish-plan", "approve-product", "approve-tests", "retry"].includes(name);
    if (destructive && !window.confirm("Record this decision and continue?")) return;
    const operation = await request(`/api/actions/${name}`, { method: "POST", body: JSON.stringify(basePayload(extra)) });
    renderOperation(operation);
    showView("overview");
    toast(`${operation.title} started.`);
  } catch (error) {
    toast(error.message, true);
  }
}

function openResetDialog() {
  const dialog = $("#reset-dialog");
  const live = mode() === "live";
  const busy = ["running", "stopping"].includes(app.snapshot?.operation?.status);
  $("#reset-run").disabled = live || busy;
  $("#reset-all-confirm").disabled = live || busy;
  $("#reset-all").disabled = true;
  $("#reset-all-confirm").value = "";
  $("#reset-note").innerHTML = live
    ? "<b>Live reset is disabled.</b> GitHub issues, branches, and pull requests may be visible to other people. Create a fresh workshop repository instead."
    : busy
      ? "<b>Wait for the current operation.</b> Stop it from the operation console before resetting."
      : "<b>Rehearsal only.</b> Reset uses the tagged Pocket Cinema baseline. Uncommitted demo-app changes are protected and make the reset fail safely.";
  dialog.showModal();
}

async function resetRun() {
  if (!window.confirm("Reset ticket execution? The saved PRD, approved plan, and agent configuration will be kept.")) return;
  $("#reset-dialog").close();
  await action("reset-run");
}

async function resetAll() {
  const confirmation = $("#reset-all-confirm").value;
  if (confirmation !== "START OVER") return;
  $("#reset-dialog").close();
  app.prdLoaded = false;
  app.canvasLoaded = false;
  app.selectedPlanning = "";
  app.loadedPlanningArtifact = "";
  await action("reset-all", { confirm: confirmation });
}

async function submitConfig(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.review_qa_tests = event.currentTarget.elements.review_qa_tests.checked;
  if (payload.preset) {
    delete payload.planning_agent;
    delete payload.agent;
    delete payload.qa_agent;
  } else {
    delete payload.preset;
  }
  for (const field of ["max_parallel", "project_number"]) if (!payload[field]) delete payload[field];
  await action("configure", payload);
}

function openTicket(number) {
  const ticket = app.snapshot?.factory?.tickets?.find((item) => Number(item.number) === Number(number));
  if (!ticket) return;
  app.selectedTicket = ticket;
  app.drawerTab = "summary";
  showDrawer(`#${ticket.number} · ${ticket.status}`, ticket.title, true);
  renderDrawer();
  $("#close-drawer").focus();
}

function showDrawer(label, title, showTabs) {
  $("#drawer-issue").textContent = label;
  $("#ticket-drawer-title").textContent = title;
  $(".drawer-tabs").hidden = !showTabs;
  $("#ticket-drawer").hidden = false;
  $("#drawer-scrim").hidden = false;
  document.body.style.overflow = "hidden";
}

function closeDrawer() {
  $("#ticket-drawer").hidden = true;
  $("#drawer-scrim").hidden = true;
  document.body.style.overflow = "";
}

async function renderDrawer() {
  const ticket = app.selectedTicket;
  if (!ticket) return;
  const requestedTab = app.drawerTab;
  $$('.drawer-tabs button').forEach((button) => button.classList.toggle("active", button.dataset.drawerTab === app.drawerTab));
  const content = $("#drawer-content");
  if (app.drawerTab === "summary") {
    const actions = ticket.status === "QA Review" ? `<button class="button button-primary" type="button" data-ticket-action="approve-tests">Approve tests</button>` : ticket.status === "Blocked" ? `<button class="button button-primary" type="button" data-ticket-action="retry">Retry ticket</button>` : "";
    content.innerHTML = `<div class="detail-grid"><section class="detail-panel"><h3>Implementation</h3><p><span class="pill">${esc(ticket.agent)}</span> attempt ${ticket.attempt || 0}</p></section><section class="detail-panel"><h3>Independent QA</h3><p><span class="pill">${esc(ticket.qa_agent || "disabled")}</span> attempt ${ticket.qa_attempt || 0}</p></section></div><section class="detail-panel"><h3>Specification</h3><pre>${esc(section(ticket.body, "Spec"))}</pre></section><section class="detail-panel"><h3>Acceptance criteria</h3><pre>${esc(section(ticket.body, "Acceptance criteria"))}</pre></section>${ticket.failure ? `<section class="detail-panel"><h3>Last failure</h3><pre>${esc(ticket.failure)}</pre></section>` : ""}<div class="form-actions">${actions}${ticket.issue_url ? `<a class="button" href="${esc(ticket.issue_url)}" target="_blank" rel="noreferrer">Open issue</a>` : ""}${ticket.pr_url ? `<a class="button" href="${esc(ticket.pr_url)}" target="_blank" rel="noreferrer">Open pull request</a>` : ""}</div>`;
    $('[data-ticket-action="approve-tests"]', content)?.addEventListener("click", () => action("approve-tests", { issue: ticket.number }));
    $('[data-ticket-action="retry"]', content)?.addEventListener("click", () => action("retry", { issue: ticket.number }));
    return;
  }
  if (app.drawerTab === "tests") {
    const tests = Object.keys(ticket.qa_tests || {});
    const gates = ticket.gate_results || [];
    content.innerHTML = `<section class="detail-panel"><h3>Protected acceptance tests</h3>${tests.length ? tests.map((path) => `<span class="pill">${esc(path)}</span>`).join("") : "No tests recorded."}</section><section class="detail-panel"><h3>Verification gates</h3>${gates.length ? gates.map((gate) => `<div class="gate-result"><strong class="${gate.exit_code === 0 ? "pass" : "fail"}">${gate.exit_code === 0 ? "PASS" : "FAIL"} · ${esc(gate.name)}</strong><p>${gate.duration_seconds || 0}s</p><pre>${esc(gate.output || "")}</pre></div>`).join("") : "No gates have run."}</section>`;
    return;
  }
  if (app.drawerTab === "history") {
    content.innerHTML = `<section class="detail-panel"><h3>State history</h3><div class="history-list">${ticket.history?.length ? ticket.history.map((item) => `<div class="history-item"><time>${formatTime(item.at)}</time><strong>${esc(item.status)}</strong><span>${esc(item.note)}</span></div>`).join("") : "No history recorded."}</div></section><section class="detail-panel"><h3>Handoff receipts</h3>${ticket.receipts?.length ? ticket.receipts.map((path) => `<button class="text-button" type="button" data-receipt="${esc(path)}">${esc(path.split("/").at(-1))}</button>`).join("<br>") : "No receipts recorded."}</section>`;
    $$('[data-receipt]', content).forEach((button) => button.addEventListener("click", () => openArtifact(button.dataset.receipt)));
    return;
  }
  content.innerHTML = '<section class="detail-panel"><h3>Loading</h3><pre>Loading artifact…</pre></section>';
  try {
    let value;
    let title;
    if (requestedTab === "diff") {
      value = await request(`/api/tickets/${ticket.number}/diff`);
      title = "Ticket diff";
    } else {
      const path = requestedTab === "prompt" ? ticket.current_prompt : ticket.current_log;
      if (!path) throw new Error(`No ${requestedTab} is available yet.`);
      value = await request(`/api/artifact?path=${encodeURIComponent(path)}`);
      title = `${requestedTab === "prompt" ? "Agent prompt" : "Agent log"} · ${path.split("/").at(-1)}`;
    }
    if (app.selectedTicket?.number === ticket.number && app.drawerTab === requestedTab) content.innerHTML = `<section class="detail-panel"><h3>${esc(title)}</h3><pre>${esc(value.content)}</pre></section>`;
  } catch (error) {
    if (app.selectedTicket?.number === ticket.number && app.drawerTab === requestedTab) content.innerHTML = `<section class="detail-panel"><h3>Not available</h3><pre>${esc(error.message)}</pre></section>`;
  }
}

async function openArtifact(path) {
  try {
    const value = await request(`/api/artifact?path=${encodeURIComponent(path)}`);
    app.selectedTicket = null;
    showDrawer("Factory artifact", path.split("/").at(-1), false);
    $("#drawer-content").innerHTML = `<section class="detail-panel"><h3>${esc(path)}</h3><pre>${esc(value.content)}</pre></section>`;
  } catch (error) { toast(error.message, true); }
}

function connectEvents() {
  app.eventSource?.close();
  const source = new EventSource("/api/events");
  app.eventSource = source;
  source.onmessage = (event) => {
    try { renderSnapshot(JSON.parse(event.data)); } catch { /* next event retries */ }
  };
  source.onerror = () => { $("#connection-label").textContent = "Reconnecting"; };
}

function wireEvents() {
  $$('[data-view-link]').forEach((link) => link.addEventListener("click", (event) => { event.preventDefault(); showView(link.dataset.viewLink); }));
  $$('[data-action]').forEach((button) => button.addEventListener("click", () => action(button.dataset.action, button.dataset.action === "doctor" ? { full: mode() === "live" } : {})));
  $("#menu-button").addEventListener("click", openSidebar);
  $("#sidebar-scrim").addEventListener("click", closeSidebar);
  $("#config-form").addEventListener("submit", submitConfig);
  $("#save-prd").addEventListener("click", async () => { try { await savePrd(); toast("PRD saved."); } catch (error) { toast(error.message, true); } });
  $("#prd-editor").addEventListener("input", () => { $("#prd-save-state").textContent = "Unsaved changes"; });
  $("#start-planning").addEventListener("click", async () => { try { await savePrd(); setMode($("#planning-mode").value); await action("plan"); } catch (error) { toast(error.message, true); } });
  $("#continue-plan").addEventListener("click", () => action("continue-plan"));
  $("#publish-plan").addEventListener("click", () => action("publish-plan", { project_title: "TableStory Workshop" }));
  $("#planning-mode").addEventListener("change", (event) => { setMode(event.target.value); renderPlanning(app.snapshot?.planning || {}); });
  $("#connect-mode").addEventListener("change", (event) => setMode(event.target.value));
  $("#run-mode").addEventListener("change", (event) => setMode(event.target.value));
  $("#stop-operation").addEventListener("click", async () => { if (!window.confirm("Stop the running factory process? The next run will recover interrupted tickets.")) return; try { await request("/api/stop", { method: "POST", body: "{}" }); toast("Stopping operation."); } catch (error) { toast(error.message, true); } });
  $("#copy-operation").addEventListener("click", async () => { const command = app.snapshot?.operation?.command; if (!command) return toast("No command to copy."); await navigator.clipboard.writeText(command); toast("Command copied."); });
  $("#command-help").addEventListener("click", () => { showView("overview"); toast("Every operation displays its exact CLI command above the live output."); });
  $("#global-next").addEventListener("click", followJourney);
  $("#journey-next").addEventListener("click", followJourney);
  $("#open-reset").addEventListener("click", openResetDialog);
  $("#open-reset-overview").addEventListener("click", openResetDialog);
  $("#close-reset").addEventListener("click", () => $("#reset-dialog").close());
  $("#reset-run").addEventListener("click", resetRun);
  $("#reset-all").addEventListener("click", resetAll);
  $("#reset-all-confirm").addEventListener("input", (event) => { $("#reset-all").disabled = event.target.value !== "START OVER"; });
  $("#close-drawer").addEventListener("click", closeDrawer);
  $("#drawer-scrim").addEventListener("click", closeDrawer);
  $$('.drawer-tabs button').forEach((button) => button.addEventListener("click", () => { app.drawerTab = button.dataset.drawerTab; renderDrawer(); }));
  $("#open-artifact").addEventListener("click", () => app.artifactPath && openArtifact(app.artifactPath));
  $("#save-canvas").addEventListener("click", async () => { try { await saveCanvas(); toast("Factory Canvas saved."); } catch (error) { toast(error.message, true); } });
  $("#canvas-text").addEventListener("input", () => { $("#canvas-save-state").textContent = "Unsaved canvas changes"; });
  $("#create-evidence").addEventListener("click", async () => { try { await saveCanvas(); await action("evidence"); } catch (error) { toast(error.message, true); } });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeDrawer(); closeSidebar(); } });
  window.addEventListener("hashchange", () => showView(location.hash.slice(1) || "overview", false));
}

async function boot() {
  wireEvents();
  setMode(localStorage.getItem("factory-control-mode") || "rehearsal");
  showView(app.view, false);
  try { renderSnapshot(await request("/api/snapshot")); } catch (error) { toast(error.message, true); }
  connectEvents();
}

boot();
