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
  const repository = $("#config-form")?.elements.namedItem("github_repository");
  if (repository) {
    repository.required = next === "live";
    repository.disabled = next !== "live";
  }
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
    const allowed = role === "planning" ? adapters.filter((item) => ["claude", "codex"].includes(item)) : adapters.filter((item) => !item.startsWith("mock"));
    const configured = { qa: config.qa_agent, planning: config.planning_agent, supervisor: config.supervisor_agent, review: config.review_agent, implementation: config.agent }[role];
    const previous = select.value || configured || "codex";
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
  $("#connect-github").textContent = repo.github_repository
    ? `${repo.github_repository}${repo.github_connected ? " · connected" : " · origin mismatch"}`
    : "Not connected";
  $("#connect-dirty").textContent = repo.dirty ? "Uncommitted changes" : "Clean";

  const config = data.config || {};
  $("#sidebar-profile").textContent = config.profile || data.factory?.profile || "standard";
  $("#sidebar-mode").textContent = data.planning?.plan_id ? (data.planning.mode || "live") : mode();
  $("#connect-project").textContent = config.project_number ? `#${config.project_number}` : "Automatic";
  const project = data.project || {};
  $("#contract-status").textContent = project.error
    ? "Contract needs correction"
    : project.configured ? `${project.name} · configured` : `${project.name || "Repository"} · detected`;
  $("#contract-guidance").textContent = project.error
    ? project.error
    : project.configured
      ? `Review ${project.path} whenever the repository structure or verification commands change.`
      : "Create the contract, review and commit it, then run setup and preflight.";
  $("#contract-sources").textContent = (project.source_roots || []).join(", ") || "—";
  $("#contract-tests").textContent = (project.test_roots || []).join(", ") || "—";
  $("#contract-gates").textContent = (project.gates || []).join(", ") || "—";
  $("#initialize-project").disabled = Boolean(project.configured);
  $("#initialize-project").textContent = project.configured ? "Contract created" : "Create contract and Charter";
  $("#prepare-project").disabled = !project.configured || !project.valid || !(project.setup_commands || []).length;
  const charter = data.charter || {};
  $("#charter-status").textContent = !charter.configured
    ? "Not created"
    : !charter.valid
      ? "Needs correction"
      : charter.approved ? "Approved" : "Awaiting your approval";
  $("#charter-guidance").textContent = charter.error
    || (charter.approved
      ? `Approval is bound to policy ${String(charter.policy_sha256 || "").slice(0, 12)}.`
      : "Review the exact policy below. Approval is invalidated if any policy field changes.");
  $("#charter-tier").textContent = charter.consequence_tier || "—";
  $("#charter-merge").textContent = charter.merge_authority || "—";
  $("#charter-gates").textContent = charter.gate_level || "—";
  $("#charter-policy").textContent = charter.text || "Create the Charter draft first.";
  $("#approve-charter").disabled = !charter.configured || !charter.valid || charter.approved;
  $("#approve-charter").textContent = charter.approved ? "Charter approved" : "Approve exact Charter";
  $("#publish-setup").disabled = !charter.approved || project.committed;
  $("#publish-setup").textContent = project.committed ? "Setup published" : "Commit and push setup";
  populateAgentSelects(data.adapters || [], config);
  hydrateConfigForm(config);

  const tickets = data.factory?.tickets || [];
  const active = tickets.filter((ticket) => ["In Progress", "Verifying"].includes(ticket.status)).length;
  const attention = data.factory?.human_attention || {};
  const waiting = attention.awaiting_review ?? tickets.filter((ticket) => ["QA Review", "In Review"].includes(ticket.status)).length;
  $("#metric-plan").textContent = data.planning?.project || "No plan";
  $("#metric-active").textContent = active;
  $("#metric-review").textContent = attention.review_limit ? `${waiting} / ${attention.review_limit}` : waiting;
  $("#metric-done").textContent = tickets.filter((ticket) => ticket.status === "Done").length;
  $("#state-updated").textContent = data.factory?.updated_at ? `Updated ${formatTime(data.factory.updated_at)}` : "Waiting for state";

  renderOperation(data.operation || {});
  renderJourney(data.journey || {});
  renderDecisions(data);
  renderPlanning(data.planning || {});
  renderTickets(data.factory || {});
  renderSupervisor(data.supervisor || {}, data.factory || {}, data.config || {});
  renderEvidence(data);
  renderMonitor(data.monitor || {}, data.repo || {});
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
  if (journey.next?.view === "planning") {
    const planning = app.snapshot?.planning || {};
    app.selectedPlanning = planning.blocked_stage || planning.failed_stage || app.selectedPlanning;
    app.loadedPlanningArtifact = "";
  }
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
  updateAutonomousWarning();
  configHydrated = true;
}

function updateAutonomousWarning() {
  const profile = $("#config-form")?.elements.namedItem("profile")?.value;
  const warning = $("#autonomous-merge-warning");
  const optIn = $("#autonomous-merge-opt-in");
  if (!warning || !optIn) return;
  warning.hidden = profile !== "autonomous-demo";
  if (warning.hidden) optIn.checked = false;
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
  const attention = data.factory?.human_attention || {};
  if (attention.dispatch_paused) {
    const oldest = tickets.find((ticket) => Number(ticket.number) === Number(attention.oldest?.ticket));
    decisions.push({ title: "NEEDS YOU · Dispatch paused", text: `${attention.reason}. Complete the oldest decision to resume new work.`, ticket: oldest, view: "tickets" });
  }
  if (planning.requires_replan) decisions.push({ title: "Restart planning safely", text: planning.replan_reason || "Planning inputs changed.", view: "planning", planning: planning.failed_stage || "product_review" });
  const blockedExpert = planning.stages?.find((stage) => stage.id === planning.blocked_stage);
  if (blockedExpert && !planning.requires_replan) decisions.push({ title: `Answer ${blockedExpert.title}`, text: `${blockedExpert.questions?.length || 0} decision(s) are blocking technical planning.`, view: "planning", planning: blockedExpert.id });
  const product = planning.stages?.find((stage) => stage.id === "product_review");
  if (product?.status === "complete" && !planning.approvals?.product && !planning.requires_replan) decisions.push({ title: "Approve Product Review", text: "Confirm the user outcome before technical planning.", view: "planning", planning: "product_review_gate" });
  for (const stage of ["system_architecture", "program_design"]) {
    if (planning.status === `awaiting_${stage}_approval` && !planning.approvals?.[stage]) {
      const title = stage === "system_architecture" ? "System Architecture" : "Program Design";
      decisions.push({ title: `Approve ${title}`, text: "Confirm the exact expert artifact before downstream planning continues.", view: "planning", planning: `${stage}_gate` });
    }
  }
  if (planning.status === "awaiting_alignment_approval" && !planning.approvals?.alignment) decisions.push({ title: "Approve alignment", text: "Accept architecture, program design, and vertical slices.", view: "planning", planning: "alignment_gate" });
  tickets.filter((ticket) => ticket.status === "QA Review").forEach((ticket) => decisions.push({ title: `Approve tests for #${ticket.number}`, text: ticket.title, ticket }));
  tickets.filter((ticket) => ticket.status === "In Review" && ticket.merge_authority === "human").forEach((ticket) => decisions.push({ title: `Decide whether to merge #${ticket.number}`, text: `Exact approved head ${(ticket.approved_head || "").slice(0, 12) || "not recorded"} · ${ticket.title}`, ticket }));
  tickets.filter((ticket) => ticket.status === "Blocked").forEach((ticket) => decisions.push({ title: `Resolve blocked #${ticket.number}`, text: ticket.failure || ticket.title, ticket }));
  $("#decision-list").innerHTML = decisions.length ? decisions.map((item, index) => `<article class="decision"><b>${esc(item.title)}</b><p>${esc(item.text)}</p><button class="button" type="button" data-decision="${index}">Review</button></article>`).join("") : '<p class="empty-state">No approvals are waiting.</p>';
  $$('[data-decision]').forEach((button) => button.addEventListener("click", () => {
    const item = decisions[Number(button.dataset.decision)];
    if (item.ticket) return openTicket(item.ticket.number);
    if (item.planning) {
      app.selectedPlanning = item.planning;
      app.loadedPlanningArtifact = "";
    }
    if (item.view) showView(item.view);
  }));
}

function planningSequence(planning) {
  const stages = planning.stages || [];
  if (!stages.length) return [];
  const required = new Set([
    ...(planning.governance?.planning_approvals || ["product_review", "alignment"]),
    ...(planning.planning_controls?.planning_approvals || []),
  ]);
  const approvalKey = { product_review: "product", system_architecture: "system_architecture", program_design: "program_design" };
  const sequence = [];
  for (const stage of stages) {
    sequence.push(stage);
    if (!required.has(stage.id) || stage.id === "vertical_slices") continue;
    const key = approvalKey[stage.id];
    const title = stage.id === "product_review" ? "Approve product" : stage.id === "system_architecture" ? "Approve architecture" : "Approve program design";
    sequence.push({
      id: `${stage.id}_gate`,
      stage: stage.id,
      title,
      status: planning.approvals?.[key] ? "approved" : planning.status === `awaiting_${stage.id}_approval` || (stage.id === "product_review" && stage.status === "complete") ? "waiting" : "pending",
      gate: true,
    });
  }
  if (required.has("alignment")) {
    sequence.push({ id: "alignment_gate", title: "Approve alignment", status: planning.approvals?.alignment ? "approved" : planning.status === "awaiting_alignment_approval" ? "waiting" : "pending", gate: true });
  }
  return sequence;
}

function renderPlanning(planning) {
  $("#plan-id").textContent = planning.plan_id || "No plan";
  const sequence = planningSequence(planning);
  if (!app.selectedPlanning && sequence.length) app.selectedPlanning = planning.blocked_stage || planning.failed_stage || sequence[0].id;
  $("#planning-pipeline").innerHTML = sequence.length ? sequence.map((item, index) => `<button type="button" class="planning-stage ${esc(item.status || "pending")} ${item.gate ? "gate" : ""} ${app.selectedPlanning === item.id ? "active" : ""}" data-planning-stage="${esc(item.id)}"><span class="stage-type">${item.gate ? "Human gate" : `Expert ${String(index + 1).padStart(2, "0")}`}</span><b>${esc(item.title)}</b><small>${esc((item.status || "pending").replaceAll("_", " "))}</small></button>`).join("") : '<div class="surface empty-state">Save a PRD and start Product Review.</div>';
  $$('[data-planning-stage]').forEach((button) => button.addEventListener("click", () => selectPlanning(button.dataset.planningStage)));
  const selected = sequence.find((item) => item.id === app.selectedPlanning);
  if (!selected) {
    $("#artifact-title").textContent = "Select a planning stage";
    $("#artifact-content").textContent = "The expert output will appear here.";
    $("#approval-panel").innerHTML = '<span class="section-label">Human gate</span><h2>Review before approval</h2><p>Select Product Review or Alignment to make a decision.</p>';
  } else if (planning.requires_replan) {
    app.loadedPlanningArtifact = "";
    app.artifactPath = "";
    $("#artifact-label").textContent = "Recovery required";
    $("#artifact-title").textContent = "Planning inputs changed";
    $("#artifact-content").textContent = "The previous artifacts remain available as evidence, but they cannot be approved or retried under different governance.";
    $("#open-artifact").hidden = true;
    $("#approval-panel").innerHTML = `<span class="section-label">Deterministic recovery</span><h2>Restart from the saved PRD</h2><div class="safety-note"><b>A retry cannot fix this run</b><p>${esc(planning.replan_reason || "The PRD, Project Contract, or Factory Charter changed.")}</p></div><p>The factory keeps the PRD, regenerates the expert artifacts, and binds the new run to the current approved Charter and Project Contract.</p><div class="approval-actions"><button class="button button-primary" type="button" id="restart-planning">Restart planning safely</button></div><p class="field-help">The invalidated run remains in <code>.factory/plans</code> as evidence. No GitHub ticket is changed.</p>`;
    $("#restart-planning").addEventListener("click", () => action("restart-plan"));
  } else if (selected.gate) {
    app.loadedPlanningArtifact = "";
    renderPlanningGate(selected, planning);
  } else {
    loadPlanningArtifact(selected);
  }

  const running = ["running", "stopping"].includes(app.snapshot?.operation?.status);
  $("#continue-plan").disabled = running || !planning.can_continue;
  $("#continue-plan").textContent = planning.continue_label || "Run remaining experts";
  $("#continue-plan").title = planning.requires_decisions ? "Answer the blocked expert's questions below." : "";
  $("#publish-plan").disabled = running || planning.status !== "awaiting_alignment_approval";
}

function renderExpertPanel(item) {
  const questions = item.questions || [];
  if (item.error && !questions.length) {
    const validationFailure = item.failure_kind === "validation";
    const currentAgent = app.snapshot?.planning?.planning_agent || "";
    const recovery = app.snapshot?.planning?.recovery || {};
    const fallbackAgents = recovery.alternative_adapters || (app.snapshot?.adapters || []).filter((agent) => ["claude", "codex"].includes(agent) && agent !== currentAgent);
    const fallback = fallbackAgents.length ? `<div class="approval-card"><label><b>Use another planning agent</b><select id="planning-retry-agent">${fallbackAgents.map((agent) => `<option value="${esc(agent)}">${esc(agent[0].toUpperCase() + agent.slice(1))}</option>`).join("")}</select></label><div class="approval-actions"><button class="button button-primary" type="button" id="retry-planning-with-agent">Switch adapter and continue</button></div><p class="field-help">The factory reuses approved upstream work and records the adapter change in the planning manifest.</p></div>` : "";
    const suggestedCorrection = `Return a complete corrected ${item.title} artifact that satisfies this validator error: ${item.validation_error || item.error}`;
    const correction = validationFailure ? `<div class="approval-card"><label><b>Correction sent to the expert</b><textarea id="planning-recovery-feedback">${esc(suggestedCorrection)}</textarea></label><div class="approval-actions"><button class="button button-primary" type="button" id="apply-planning-correction">${item.id === "product_review" ? "Apply correction" : "Apply correction and continue"}</button></div><p class="field-help">Edit the instruction if needed. The factory uses the rejected artifact as the revision source, validates the replacement, and resumes only after it passes.</p></div>` : "";
    const retrySame = !validationFailure && recovery.retry_same_adapter ? `<div class="approval-actions"><button class="button" type="button" id="retry-planning-same-agent">Retry same adapter</button></div>` : "";
    const preflight = ["authentication", "adapter_setup"].includes(recovery.kind) ? `<div class="approval-actions"><button class="button" type="button" id="check-planning-adapter">Run preflight after fixing the adapter</button></div>` : "";
    const summary = recovery.summary || (validationFailure ? "The artifact needs a correction before planning can continue." : "Inspect the failure before choosing a recovery.");
    $("#approval-panel").innerHTML = `<span class="section-label">Expert recovery</span><h2>${esc(item.title)} ${validationFailure ? "failed validation" : "failed"}</h2><div class="safety-note"><b>${validationFailure ? "Deterministic validator" : "Agent process"}</b><p>${esc(item.error)}</p></div>${item.rejected_artifact ? `<div class="approval-card"><b>Rejected artifact preserved</b><p><code>${esc(item.rejected_artifact)}</code></p></div>` : ""}<p><b>What fixes it:</b> ${esc(summary)}</p>${correction}${preflight}${retrySame}${fallback}`;
    $("#apply-planning-correction")?.addEventListener("click", () => {
      const feedback = $("#planning-recovery-feedback").value.trim();
      if (!feedback) return toast("Describe the required correction before continuing.", true);
      if (item.id === "product_review") action("revise-product", { feedback });
      else action("revise-stage", { stage: item.id, feedback });
    });
    $("#check-planning-adapter")?.addEventListener("click", () => action("doctor", { full: true }));
    $("#retry-planning-same-agent")?.addEventListener("click", () => action("continue-plan"));
    $("#retry-planning-with-agent")?.addEventListener("click", () => action("continue-plan", { planning_agent: $("#planning-retry-agent").value }));
    return;
  }
  if (!questions.length) {
    $("#approval-panel").innerHTML = `<span class="section-label">Expert contract</span><h2>${esc(item.title)}</h2><p>No blocking questions recorded.</p><div class="approval-card"><b>Artifact hash</b><p><code>${esc(item.sha256 || "Pending")}</code></p></div>`;
    return;
  }
  const running = ["running", "stopping"].includes(app.snapshot?.operation?.status);
  $("#approval-panel").innerHTML = `<span class="section-label">Human decisions required</span><h2>Unblock ${esc(item.title)}</h2><p>Answer every question. Your decisions are sent back to this expert, recorded in revision history, and used to regenerate the artifact.</p><div class="approval-card blocking-question-list">${questions.map((question, index) => `<label class="blocking-question"><b>Question ${index + 1}</b><span>${esc(question)}</span><textarea data-question-answer="${index}" placeholder="Record your decision and any constraint the expert must preserve."></textarea></label>`).join("")}<div class="approval-actions"><button class="button button-primary" type="button" id="resolve-planning-questions" ${running ? "disabled" : ""}>${item.id === "product_review" ? "Submit decisions" : "Submit decisions and continue"}</button></div><p class="field-help">The factory keeps the previous artifact, records these answers, and reruns only the affected expert. Technical planning then resumes from the next valid stage.</p></div>`;
  $("#resolve-planning-questions").addEventListener("click", () => {
    const answers = $$('[data-question-answer]', $("#approval-panel")).map((field) => field.value.trim());
    if (answers.some((answer) => !answer)) {
      toast("Answer every blocking question before continuing.", true);
      return;
    }
    const feedback = ["Resolve the blocking questions using these human decisions:", "", ...questions.flatMap((question, index) => [`${index + 1}. Question: ${question}`, `Decision: ${answers[index]}`, ""])].join("\n");
    const actionName = item.id === "product_review" ? "revise-product" : "revise-stage";
    action(actionName, { stage: item.id, feedback });
  });
}

async function loadPlanningArtifact(item) {
  const selectedId = item.id;
  const artifactPath = item.status === "blocked" && item.rejected_artifact
    ? item.rejected_artifact
    : item.markdown || item.json || "";
  const artifactKey = `${artifactPath}:${item.sha256 || item.status || ""}:${item.error || ""}`;
  if (app.loadedPlanningArtifact === artifactKey) return;
  app.loadedPlanningArtifact = artifactKey;
  $("#artifact-label").textContent = item.status || "Artifact";
  $("#artifact-title").textContent = item.title;
  $("#artifact-content").textContent = "Loading…";
  app.artifactPath = artifactPath;
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
  renderExpertPanel(item);
}

function selectPlanning(id) {
  app.selectedPlanning = id;
  app.loadedPlanningArtifact = "";
  renderPlanning(app.snapshot?.planning || {});
}

function renderPlanningGate(item, planning) {
  $("#artifact-label").textContent = "Human decision";
  $("#artifact-title").textContent = item.title;
  $("#artifact-content").textContent = item.id === "product_review_gate" ? "Approve only when the problem, users, behavior, scope, and evidence are clear." : item.id === "alignment_gate" ? "Approve only when requirements trace to architecture, program design, tickets, and QA evidence." : "Approve only when this exact expert artifact respects its upstream contract and the approved Factory Charter.";
  $("#open-artifact").hidden = true;
  const approved = item.status === "approved";
  if (approved) {
    $("#approval-panel").innerHTML = `<span class="section-label">Human gate</span><h2>${esc(item.title)}</h2><div class="safety-note"><b>Approved</b><p>This decision and its artifact hashes are recorded in the plan manifest.</p></div>`;
    return;
  }
  if (item.id === "product_review_gate") {
    $("#approval-panel").innerHTML = `<span class="section-label">Human gate</span><h2>Product Review</h2><p>Approve the outcome or send focused feedback to the product expert.</p><div class="approval-card"><label>Revision feedback<textarea id="product-feedback" placeholder="Describe what must become clearer or testable."></textarea></label><div class="approval-actions"><button class="button" type="button" id="revise-product">Request revision</button><button class="button button-primary" type="button" id="approve-product">Approve product</button></div></div>`;
    $("#revise-product").addEventListener("click", () => action("revise-product", { feedback: $("#product-feedback").value }));
    $("#approve-product").addEventListener("click", () => action("approve-product"));
  } else if (item.id === "alignment_gate") {
    $("#approval-panel").innerHTML = `<span class="section-label">Human gate</span><h2>Alignment</h2><p>Publishing creates the approved vertical slices as ${mode() === "live" ? "GitHub issues" : "local rehearsal tickets"}.</p><div class="approval-card"><label>New GitHub Project title<input id="project-title" value="TableStory Workshop" ${mode() === "live" ? "" : "disabled"}></label><div class="approval-actions"><button class="button button-primary" type="button" id="approve-alignment">Approve and create tickets</button></div></div>`;
    $("#approve-alignment").addEventListener("click", () => action("publish-plan", { project_title: $("#project-title").value }));
  } else {
    const title = item.stage === "system_architecture" ? "System Architecture" : "Program Design";
    $("#approval-panel").innerHTML = `<span class="section-label">Charter-required human gate</span><h2>${esc(title)}</h2><p>Review the adjacent expert artifact. Approval records its exact hash and allows the next expert to run.</p><div class="approval-actions"><button class="button button-primary" type="button" id="approve-planning-stage">Approve ${esc(title)}</button></div>`;
    $("#approve-planning-stage").addEventListener("click", () => action("approve-stage", { stage: item.stage }));
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

function renderSupervisor(supervisor, factory, config) {
  const configuredAgent = factory.supervisor_agent || config.supervisor_agent;
  const status = supervisor.status || (configuredAgent === "disabled" || config.profile === "lean" ? "disabled" : "waiting");
  const badge = $("#supervisor-status");
  badge.textContent = status;
  badge.className = `operation-status ${status === "ready" ? "succeeded" : status === "running" ? "running" : status === "failed" ? "failed" : "idle"}`;
  $("#supervisor-agent").textContent = supervisor.agent ? `Adapter: ${supervisor.agent}` : `Adapter: ${configuredAgent || "not configured"}`;
  const latest = supervisor.latest;
  if (!latest) {
    $("#supervisor-summary").textContent = status === "disabled" ? "Supervisor is not part of this profile" : "No coordination decision yet";
    $("#supervisor-explanation").textContent = supervisor.error || (status === "disabled" ? "Choose the Standard or Assured Factory Profile to coordinate ticket agents." : "The supervisor runs automatically when dependency-ready tickets are available.");
    $("#supervisor-updated").textContent = supervisor.updated_at ? formatTime(supervisor.updated_at) : "—";
    $("#supervisor-commands").innerHTML = '<p class="empty-state">No dispatch commands recorded.</p>';
    $("#supervisor-reports").innerHTML = '<p class="empty-state">No Handoff Receipts considered yet.</p>';
    $("#supervisor-artifacts").innerHTML = "";
  } else {
    $("#supervisor-summary").textContent = latest.summary;
    $("#supervisor-explanation").textContent = latest.kind === "merge"
      ? `Decision ${latest.id} issued ${latest.action} for Ticket #${latest.ticket} at candidate ${(latest.candidate_head || "").slice(0, 8)}.`
      : `Decision ${latest.id} selected ${latest.dispatch?.length || 0} ticket(s), blocked ${latest.block?.length || 0}, and deferred ${latest.deferred?.length || 0}.`;
    $("#supervisor-updated").textContent = formatTime(latest.at);
    const commands = [
      ...(latest.kind === "merge" && latest.action === "MERGE" ? [`<article class="supervisor-command dispatch"><span>Merge #${latest.ticket}</span><p>Approved candidate ${esc((latest.candidate_head || "").slice(0, 8))} · ${String(latest.pull_request || "").startsWith("http") ? `<a href="${esc(latest.pull_request)}" target="_blank" rel="noreferrer">open pull request</a>` : esc(latest.pull_request || "rehearsal candidate")}</p></article>`] : []),
      ...(latest.dispatch || []).map((item) => `<article class="supervisor-command dispatch"><span>Dispatch #${item.ticket}</span><p>${esc(item.instruction)}</p></article>`),
      ...(latest.block || []).map((item) => `<article class="supervisor-command block"><span>Block #${item.ticket}</span><p>${esc(item.reason)}</p></article>`),
      ...((latest.deferred || []).length ? [`<article class="supervisor-command defer"><span>Defer</span><p>${latest.deferred.map((number) => `#${number}`).join(", ")}</p></article>`] : []),
    ];
    $("#supervisor-commands").innerHTML = commands.join("") || '<p class="empty-state">No commands recorded.</p>';
    const reports = latest.worker_reports || [];
    $("#supervisor-reports").innerHTML = reports.length ? reports.map((report) => `<article class="worker-report"><b>#${report.ticket} · ${esc(report.role)}</b><span>${esc(report.claimed_result)}</span><small>${report.unresolved_risks?.length ? esc(report.unresolved_risks.join(" · ")) : "No unresolved risk reported"}</small></article>`).join("") : '<p class="empty-state">This first dispatch had no earlier worker reports.</p>';
    $("#supervisor-artifacts").innerHTML = [latest.prompt, latest.log].filter(Boolean).map((path) => `<button class="button" type="button" data-supervisor-artifact="${esc(path)}">Open ${path === latest.prompt ? "input" : "log"}</button>`).join("");
    $$('[data-supervisor-artifact]').forEach((button) => button.addEventListener("click", () => openArtifact(button.dataset.supervisorArtifact)));
  }
  const events = supervisor.events || [];
  $("#supervisor-history").innerHTML = events.length ? [...events].reverse().map((event) => `<article class="supervisor-event"><time>${formatTime(event.at)}</time><b>${esc(event.id)}</b><span>${esc(event.summary)}</span><small>${event.kind === "merge" ? `${esc(event.action)} Ticket #${event.ticket} · candidate ${esc((event.candidate_head || "").slice(0, 8))}` : `${event.dispatch?.length || 0} dispatched · ${event.block?.length || 0} blocked · ${event.deferred?.length || 0} deferred`}</small></article>`).join("") : '<p class="empty-state">Decisions will appear here after the first ready wave.</p>';
}

function renderEvidence(data) {
  const tickets = data.factory?.tickets || [];
  const profile = data.factory?.profile || data.config?.profile || "standard";
  const causalRequired = ["standard", "assured", "autonomous-demo"].includes(profile);
  const causalProofPass = tickets.length > 0 && tickets.every((ticket) => {
    if (!causalRequired) return true;
    const evidence = ticket.qa_evidence || {};
    return evidence.red?.result === "RED PROVED"
      && evidence.green?.result === "GREEN PROVED"
      && (profile !== "assured" || evidence.negative?.result === "NEGATIVE PROOF PROVED");
  });
  const requiredGatesPass = tickets.length > 0 && tickets.every((ticket) => {
    const required = (ticket.gate_results || []).filter((gate) => gate.required);
    return required.length > 0 && required.every((gate) => gate.exit_code === 0);
  });
  const checks = [
    [Boolean(data.planning?.approvals?.product), "Product intent approved", "Problem and behavior accepted by a person"],
    [Boolean(data.planning?.approvals?.alignment), "Delivery plan approved", "Architecture and slices accepted"],
    [causalProofPass, causalRequired ? "Red and green proved" : "Existing tests reviewed", causalRequired ? "The same focused command detects missing behavior and passes after implementation" : "The Lean path uses the repository's existing evidence"],
    [requiredGatesPass, "Required gates pass", "Every ticket has a successful required gate"],
    [tickets.length > 0 && tickets.every((ticket) => ticket.status === "Done"), "All tickets complete", "Integrated delivery has no unfinished work"],
  ];
  $("#evidence-checks").innerHTML = checks.map(([complete, title, text]) => `<div class="evidence-check ${complete ? "complete" : ""}"><span>${complete ? "✓" : "·"}</span><div><b>${esc(title)}</b><small>${esc(text)}</small></div></div>`).join("");
  $("#evidence-files").innerHTML = data.evidence?.length ? data.evidence.map((file) => `<button class="file-item text-button" type="button" data-artifact="${esc(file.path)}"><span>FILE</span><div><b>${esc(file.name)}</b><small>${Math.ceil(file.size / 1024)} KB · ${formatTime(file.updated_at)}</small></div><i>Open</i></button>`).join("") : '<p class="empty-state">No evidence packet generated yet.</p>';
  $$('[data-artifact]', $("#evidence-files")).forEach((button) => button.addEventListener("click", () => openArtifact(button.dataset.artifact)));
}

function renderMonitor(report, repo) {
  const findings = Array.isArray(report.findings) ? report.findings : [];
  const hotspots = Array.isArray(report.hotspots) ? report.hotspots : [];
  const limitations = Array.isArray(report.limitations) ? report.limitations : [];
  const status = report.status || (report.version ? "healthy" : "not run");
  $("#monitor-summary").textContent = report.version
    ? `${status === "healthy" ? "No blocking findings" : `${findings.length} finding${findings.length === 1 ? "" : "s"}`} · ${status}`
    : "No monitoring report yet";
  $("#monitor-meta").textContent = report.generated_at
    ? `Generated ${formatTime(report.generated_at)} from ${report.default_revision || repo.branch || "the current revision"}.`
    : "Run a preview to check the repository without changing it.";
  const counts = report.counts || {};
  $("#monitor-counts").innerHTML = Object.keys(counts).length
    ? Object.entries(counts).map(([kind, count]) => `<div><b>${esc(count)}</b><span>${esc(kind.replaceAll("_", " "))}</span></div>`).join("")
    : "";
  $("#monitor-findings").innerHTML = findings.length
    ? findings.map((finding) => `<article class="monitor-finding"><span>${esc((finding.severity || "info").toUpperCase())}</span><div><b>${esc(finding.summary || finding.title || finding.id)}</b><p>${esc(finding.detail || finding.message || "Review this finding.")}</p><small>${esc(finding.recovery || finding.recommendation || "A person decides the follow-up.")}</small></div></article>`).join("")
    : `<p class="empty-state">${report.version ? "No actionable findings." : "No report loaded."}</p>`;
  $("#monitor-hotspots").innerHTML = hotspots.length
    ? hotspots.map((item) => `<div class="monitor-row"><code>${esc(item.path || item.name || item)}</code><span>${esc(item.changes ?? item.count ?? "")}</span></div>`).join("")
    : '<p class="empty-state">No changed hotspots reported.</p>';
  $("#monitor-limitations").innerHTML = limitations.length
    ? limitations.map((item) => `<p class="monitor-limitation">${esc(item.message || item)}</p>`).join("")
    : '<p class="empty-state">No limitations reported.</p>';
  $("#publish-monitor").disabled = !repo.github_connected || mode() !== "live";
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
  const profile = $("#config-form")?.elements.namedItem("profile")?.value;
  return {
    mode: mode(),
    scenario: "recipe-rebrand",
    plan_id: app.snapshot?.planning?.plan_id || "",
    review_qa_tests: app.snapshot?.config?.review_qa_tests ?? true,
    allow_autonomous_merge: profile === "autonomous-demo" && Boolean($("#autonomous-merge-opt-in")?.checked),
    ...extra,
  };
}

async function action(name, extra = {}) {
  try {
    if (name === "init-project" && !window.confirm("Create factory.project.toml and a conservative factory.charter.toml draft from the detected repository structure?")) return;
    if (name === "approve-charter" && !window.confirm("Approve the exact Factory Charter policy shown in Connect? Any policy edit will invalidate this approval.")) return;
    if (name === "publish-setup" && !window.confirm("Commit and push only .gitignore, factory.project.toml, and the approved factory.charter.toml to the default branch?")) return;
    if (name === "merge" && !window.confirm("Merge only the exact approved revision shown for this Ticket? This records your human shipping decision.")) return;
    if (name === "prepare-project" && !window.confirm("Run the setup commands recorded in factory.project.toml? Review that file first.")) return;
    const destructive = ["publish-plan", "approve-product", "approve-stage", "approve-tests", "retry", "release-claim"].includes(name);
    if (destructive && !window.confirm("Record this decision and continue?")) return;
    const operation = await request(`/api/actions/${name}`, { method: "POST", body: JSON.stringify(basePayload(extra)) });
    renderOperation(operation);
    showView("overview");
    toast(`${operation.title} started.`);
    return operation;
  } catch (error) {
    toast(error.message, true);
    return null;
  }
}

function openResetDialog() {
  const dialog = $("#reset-dialog");
  const live = mode() === "live";
  const busy = ["running", "stopping"].includes(app.snapshot?.operation?.status);
  $("#reset-run").disabled = busy;
  $("#reset-all-confirm").disabled = busy;
  $("#reset-all").disabled = true;
  $("#reset-run").textContent = live ? "Reset local run state" : "Reset ticket execution";
  $("#reset-all").textContent = live ? "Clear local run history" : "Start workshop over";
  $("#reset-all-confirm").value = "";
  $("#reset-note").innerHTML = live
    ? "<b>GitHub and source files stay unchanged.</b> Reset clears only local factory state. Existing issues, Projects, branches, and pull requests remain visible and the Control Center stays in Live mode."
    : busy
      ? "<b>Wait for the current operation.</b> Stop it from the operation console before resetting."
      : "<b>Rehearsal pack.</b> Reset uses the repository's reviewed reset adapter. Uncommitted work is protected and makes a destructive adapter fail safely.";
  dialog.showModal();
}

async function resetRun() {
  const live = mode() === "live";
  const prompt = live
    ? "Reset local execution state? GitHub artifacts and tracked source files will not be changed."
    : "Reset ticket execution? The saved PRD, approved plan, and agent configuration will be kept.";
  if (!window.confirm(prompt)) return;
  $("#reset-dialog").close();
  const operation = await action("reset-run", { local_only: live });
}

async function resetAll() {
  const live = mode() === "live";
  const confirmation = $("#reset-all-confirm").value;
  if (confirmation !== "START OVER") return;
  $("#reset-dialog").close();
  const operation = await action("reset-all", { confirm: confirmation, local_only: live });
  if (!operation) return;
  app.prdLoaded = false;
  app.canvasLoaded = false;
  app.selectedPlanning = "";
  app.loadedPlanningArtifact = "";
}

async function submitConfig(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.mode = mode();
  payload.review_qa_tests = event.currentTarget.elements.review_qa_tests.checked;
  if (payload.preset) {
    delete payload.planning_agent;
    delete payload.agent;
    delete payload.qa_agent;
    delete payload.supervisor_agent;
    delete payload.review_agent;
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
    const claimOwner = ticket.remote_claim?.owner_run_id || ticket.remote_claim?.run_id;
    const claimBlocked = ticket.status === "Blocked" && claimOwner && ticket.failure?.includes("Remote Ticket claim");
    const actions = ticket.status === "QA Review" ? `<button class="button button-primary" type="button" data-ticket-action="approve-tests">Approve tests</button>` : claimBlocked ? `<button class="button button-danger" type="button" data-ticket-action="release-claim">Release abandoned claim</button>` : ticket.status === "Blocked" ? `<button class="button button-primary" type="button" data-ticket-action="retry">Retry ticket</button>` : ticket.status === "In Review" && ticket.merge_authority === "human" ? `<button class="button button-primary" type="button" data-ticket-action="merge">Merge exact revision</button>` : "";
    const merge = ticket.status === "In Review" ? `<section class="detail-panel"><h3>Merge authority</h3><p><span class="pill">${esc(ticket.merge_authority || "human")}</span> Approved head <code>${esc(ticket.approved_head || "not recorded")}</code></p><p>${ticket.supervisor_merge_action === "MERGE" && ticket.merge_authority === "human" ? "The Supervisor recommends merge. A person still owns the final decision." : esc(ticket.supervisor_merge_decision || "Inspect the evidence before deciding.")}</p></section>` : "";
    const triage = ticket.triage || {};
    const controls = triage.controls || {};
    const metrics = ticket.metrics || {};
    const timing = `<section class="detail-panel"><h3>Time by owner</h3><div class="detail-grid"><p><b>${esc(metrics.agent_seconds || 0)}s</b><br><small>Useful agent work</small></p><p><b>${esc(metrics.gate_seconds || ticket.verification_duration_seconds || 0)}s</b><br><small>Verification overhead</small></p><p><b>${esc(metrics.human_wait_seconds || 0)}s</b><br><small>Human wait</small></p><p><b>${esc(metrics.retry_count || 0)}</b><br><small>Retries · ${esc(metrics.verifier_rejections || 0)} verifier rejections</small></p></div></section>`;
    content.innerHTML = `<div class="detail-grid"><section class="detail-panel"><h3>Implementation</h3><p><span class="pill">${esc(ticket.agent)}</span> attempt ${ticket.attempt || 0}</p></section><section class="detail-panel"><h3>Independent QA</h3><p><span class="pill">${esc(ticket.qa_agent || "disabled")}</span> attempt ${ticket.qa_attempt || 0}</p></section></div><section class="detail-panel"><h3>Triage and controls</h3><p><span class="pill">${esc(triage.result || "not run")}</span> ${esc(controls.risk || "unclassified")} risk · ${esc(ticket.verification_level || controls.gate_level || "unselected")} verification</p><p>${esc(controls.reason || triage.reason || "Controls are selected before dispatch and checked again from the actual diff.")}</p></section>${timing}${merge}<section class="detail-panel"><h3>Specification</h3><pre>${esc(section(ticket.body, "Spec"))}</pre></section><section class="detail-panel"><h3>Acceptance criteria</h3><pre>${esc(section(ticket.body, "Acceptance criteria"))}</pre></section>${ticket.failure ? `<section class="detail-panel"><h3>Last failure</h3><pre>${esc(ticket.failure)}</pre></section>` : ""}<div class="form-actions">${actions}${ticket.issue_url ? `<a class="button" href="${esc(ticket.issue_url)}" target="_blank" rel="noreferrer">Open issue</a>` : ""}${ticket.pr_url ? `<a class="button" href="${esc(ticket.pr_url)}" target="_blank" rel="noreferrer">Open pull request</a>` : ""}</div>`;
    $('[data-ticket-action="approve-tests"]', content)?.addEventListener("click", () => action("approve-tests", { issue: ticket.number }));
    $('[data-ticket-action="retry"]', content)?.addEventListener("click", () => action("retry", { issue: ticket.number }));
    $('[data-ticket-action="release-claim"]', content)?.addEventListener("click", () => action("release-claim", { issue: ticket.number, owner_run_id: claimOwner, reason: "Operator confirmed this remote claim was abandoned in the Control Center" }));
    $('[data-ticket-action="merge"]', content)?.addEventListener("click", () => action("merge", { issue: ticket.number }));
    return;
  }
  if (app.drawerTab === "supervisor") {
    const receipts = (ticket.receipts || []).filter((path) => path.includes("supervisor"));
    content.innerHTML = `<section class="detail-panel"><h3>Current instruction</h3><p>${ticket.supervisor_instruction ? esc(ticket.supervisor_instruction) : "No supervisor instruction has been issued for this Ticket."}</p></section><section class="detail-panel"><h3>Dispatch decision</h3><p>${esc(ticket.supervisor_decision || "Not dispatched by a supervisor")}</p></section><section class="detail-panel"><h3>Merge recommendation</h3><p>${ticket.supervisor_merge_action ? `<span class="pill">${esc(ticket.supervisor_merge_action)}</span> ${esc(ticket.supervisor_merge_decision || "")}` : "No merge recommendation has been issued. Code review approval is required first."}</p></section><section class="detail-panel"><h3>Supervisor receipts</h3>${receipts.length ? receipts.map((path) => `<button class="text-button" type="button" data-supervisor-receipt="${esc(path)}">${esc(path.split("/").at(-1))}</button>`).join("<br>") : "No supervisor Handoff Receipt recorded."}</section>`;
    $$('[data-supervisor-receipt]', content).forEach((button) => button.addEventListener("click", () => openArtifact(button.dataset.supervisorReceipt)));
    return;
  }
  if (app.drawerTab === "review") {
    const review = ticket.code_review;
    if (!review) {
      content.innerHTML = '<section class="detail-panel"><h3>Code review</h3><p>No Code Review Agent decision has been recorded for this Ticket.</p></section>';
      return;
    }
    const result = review.result || {};
    const findings = result.findings || [];
    const publication = review.publication || {};
    const publicationText = !publication.published ? "Not published" : publication.official ? "Formal GitHub review" : publication.mode === "rehearsal" ? "Rehearsal decision" : "Factory PR comment (not a branch-protection approval)";
    content.innerHTML = `<section class="detail-panel"><h3>${esc(result.decision || review.status || "Code review")}</h3><p>${esc(result.summary || review.failure || "No summary recorded.")}</p><p><span class="pill">${esc(review.agent || "unknown")}</span> candidate ${esc((review.head || "").slice(0, 8) || "—")}</p><p>${esc(publicationText)}</p></section><section class="detail-panel"><h3>Review comments</h3>${findings.length ? findings.map((finding) => `<div class="gate-result"><strong class="${finding.severity === "blocking" ? "fail" : "pass"}">${esc(finding.severity.toUpperCase())} · ${esc(finding.path)}${finding.line ? `:${finding.line}` : ""}</strong><p>${esc(finding.message)}</p></div>`).join("") : "No comments reported. The candidate is eligible for a revision-bound Supervisor recommendation and human merge decision."}</section>${review.artifact ? `<button class="text-button" type="button" data-review-artifact="${esc(review.artifact)}">Open structured review artifact</button>` : ""}`;
    $('[data-review-artifact]', content)?.addEventListener("click", (event) => openArtifact(event.currentTarget.dataset.reviewArtifact));
    return;
  }
  if (app.drawerTab === "tests") {
    const tests = Object.keys(ticket.qa_tests || {});
    const gates = ticket.gate_results || [];
    const causal = ticket.qa_evidence || {};
    const proof = (name, value, waiting) => `<div class="gate-result"><strong class="${value?.result?.includes("PROVED") && !value.result.includes("NOT") ? "pass" : value ? "fail" : ""}">${esc(value?.result || waiting)} · ${name}</strong>${value ? `<p>${esc(value.classification || "unknown")} · exit ${value.exit_code ?? "—"} · ${value.duration_seconds || 0}s</p><pre>${esc(value.output || "")}</pre>` : ""}</div>`;
    const causalEvidence = causal.focused_test_command
      ? `<section class="detail-panel"><h3>Causal acceptance evidence</h3><p>Identical focused command</p><pre>${esc(causal.focused_test_command)}</pre>${proof("Before implementation", causal.red, "RED NOT PROVED")}${proof("After implementation", causal.green, "GREEN NOT PROVED")}${causal.negative ? proof("Assured negative proof", causal.negative, "NEGATIVE PROOF NOT RUN") : ""}</section>`
      : `<section class="detail-panel"><h3>Causal acceptance evidence</h3><p>RED NOT PROVED · No focused Acceptance Test command has been accepted.</p></section>`;
    content.innerHTML = `<section class="detail-panel"><h3>Protected acceptance tests</h3>${tests.length ? tests.map((path) => `<span class="pill">${esc(path)}</span>`).join("") : "No tests recorded."}</section>${causalEvidence}<section class="detail-panel"><h3>Deterministic verification gates</h3><p>Selected level: <span class="pill">${esc(ticket.verification_level || "not selected")}</span> · ${ticket.verification_duration_seconds || 0}s total</p>${gates.length ? gates.map((gate) => { const verdict = gate.classification || (gate.exit_code === 0 ? "PASS" : "FAIL"); return `<div class="gate-result"><strong class="${verdict === "PASS" ? "pass" : "fail"}">${esc(verdict)} · ${esc(gate.name)} · ${esc(gate.level || "full")}</strong><p>${gate.duration_seconds || 0}s</p><pre>${esc(gate.output || "")}</pre></div>`; }).join("") : "No gates have run."}</section>`;
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
  $("#config-form").elements.namedItem("profile").addEventListener("change", updateAutonomousWarning);
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
