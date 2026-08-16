"use client";

import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";

type Track = "rehearsal" | "live";

const steps = [
  { id: "setup", label: "Set up your workspace", time: "8 min" },
  { id: "baseline", label: "Inspect the baseline", time: "5 min" },
  { id: "prd", label: "Read the PRD", time: "7 min" },
  { id: "plan", label: "Approve product intent", time: "15 min" },
  { id: "publish", label: "Align and publish", time: "15 min" },
  { id: "qa", label: "Review QA tests", time: "12 min" },
  { id: "factory", label: "Run the factory", time: "25 min" },
  { id: "finish", label: "Verify the product", time: "13 min" },
] as const;

function CodeBlock({ children, label = "Terminal" }: { children: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(children);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="code-block">
      <div className="code-toolbar">
        <span>{label}</span>
        <button type="button" onClick={copy} aria-label={`Copy ${label} command`}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre><code>{children}</code></pre>
    </div>
  );
}

function Callout({
  type = "note",
  title,
  children,
}: {
  type?: "note" | "tip" | "warning";
  title: string;
  children: ReactNode;
}) {
  return (
    <aside className={`callout callout-${type}`}>
      <span className="callout-icon" aria-hidden="true">
        {type === "tip" ? "✓" : type === "warning" ? "!" : "i"}
      </span>
      <div>
        <strong>{title}</strong>
        <div>{children}</div>
      </div>
    </aside>
  );
}

function Checkpoint({ children }: { children: ReactNode }) {
  return (
    <div className="checkpoint">
      <div className="checkpoint-title"><span aria-hidden="true">✓</span> Checkpoint</div>
      <div>{children}</div>
    </div>
  );
}

function StepSection({
  id,
  number,
  title,
  time,
  completed,
  onComplete,
  children,
}: {
  id: string;
  number: number;
  title: string;
  time: string;
  completed: boolean;
  onComplete: () => void;
  children: ReactNode;
}) {
  return (
    <section className={`lesson ${completed ? "lesson-complete" : ""}`} id={id}>
      <div className="lesson-heading">
        <div className="step-number" aria-hidden="true">{completed ? "✓" : number}</div>
        <div>
          <span className="lesson-kicker">Step {number} · {time}</span>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="lesson-body">{children}</div>
      <div className="lesson-footer">
        <button
          type="button"
          className={completed ? "complete-button completed" : "complete-button"}
          onClick={onComplete}
        >
          <span aria-hidden="true">{completed ? "✓" : "○"}</span>
          {completed ? "Step completed" : "Mark step complete"}
        </button>
      </div>
    </section>
  );
}

export default function Home() {
  const [track, setTrack] = useState<Track>("rehearsal");
  const [completed, setCompleted] = useState<string[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const savedTrack = window.localStorage.getItem("factory-workshop-track") as Track | null;
      const savedProgress = window.localStorage.getItem("factory-workshop-progress");
      if (savedTrack === "live" || savedTrack === "rehearsal") setTrack(savedTrack);
      if (savedProgress) {
        try {
          const values = JSON.parse(savedProgress);
          if (Array.isArray(values)) setCompleted(values.filter((id) => steps.some((step) => step.id === id)));
        } catch {
          window.localStorage.removeItem("factory-workshop-progress");
        }
      }
      setHydrated(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem("factory-workshop-track", track);
  }, [hydrated, track]);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem("factory-workshop-progress", JSON.stringify(completed));
  }, [completed, hydrated]);

  const percent = Math.round((completed.length / steps.length) * 100);
  const nextStep = useMemo(
    () => steps.find((step) => !completed.includes(step.id)),
    [completed],
  );

  function toggleStep(id: string) {
    setCompleted((current) => current.includes(id)
      ? current.filter((value) => value !== id)
      : [...current, id]);
  }

  function chooseTrack(value: Track) {
    setTrack(value);
    document.getElementById("setup")?.scrollIntoView({ behavior: "smooth" });
  }

  function resetProgress() {
    setCompleted([]);
    document.getElementById("start")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to workshop</a>
      <header className="topbar">
        <button
          className="menu-button"
          type="button"
          aria-label="Open workshop navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((value) => !value)}
        >
          <span></span><span></span><span></span>
        </button>
        <a className="brand" href="#start" aria-label="Software re-Factory workshop home">
          <span className="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
          <span>Software <b>(re)-Factory</b></span>
        </a>
        <span className="header-divider" aria-hidden="true"></span>
        <span className="header-section">Workshop</span>
        <div className="topbar-actions">
          <span className="duration-pill">100 min</span>
          <a
            className="github-link"
            href="https://github.com/giolaq/software-refactory-workshop"
            target="_blank"
            rel="noreferrer"
          >
            View repository <span aria-hidden="true">↗</span>
          </a>
        </div>
      </header>

      {menuOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}

      <aside className={`left-nav ${menuOpen ? "left-nav-open" : ""}`} aria-label="Workshop steps">
        <div className="nav-progress">
          <div className="nav-progress-row">
            <span>Your progress</span>
            <strong>{completed.length}/{steps.length}</strong>
          </div>
          <div className="progress-track" role="progressbar" aria-label="Workshop progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
            <span style={{ width: `${percent}%` }}></span>
          </div>
        </div>
        <nav>
          <p className="nav-label">Get started</p>
          <a href="#start" onClick={() => setMenuOpen(false)}>Overview</a>
          <a href="#choose-track" onClick={() => setMenuOpen(false)}>Choose a path</a>
          <p className="nav-label">Guided lab</p>
          {steps.map((step, index) => (
            <a
              key={step.id}
              href={`#${step.id}`}
              className={completed.includes(step.id) ? "nav-step-complete" : ""}
              onClick={() => setMenuOpen(false)}
            >
              <span>{completed.includes(step.id) ? "✓" : index + 1}</span>
              <span>{step.label}<small>{step.time}</small></span>
            </a>
          ))}
          <p className="nav-label">Help</p>
          <a href="#troubleshooting" onClick={() => setMenuOpen(false)}>Troubleshooting</a>
          <a href="#reference" onClick={() => setMenuOpen(false)}>Command reference</a>
        </nav>
      </aside>

      <main id="main-content">
        <section className="hero" id="start">
          <div className="hero-copy">
            <div className="eyebrow">GUIDED LAB</div>
            <h1>Run an AI software factory</h1>
            <p className="hero-lede">
              Align product, architecture, program design, and vertical slices before code;
              then let independent QA and implementation agents work with visible evidence.
            </p>
            <div className="hero-meta">
              <span><b>Level</b> Intermediate</span>
              <span><b>Time</b> 100 minutes</span>
              <span><b>Cost</b> Free in rehearsal mode</span>
            </div>
            <a className="primary-button" href="#choose-track">Start the workshop <span aria-hidden="true">→</span></a>
          </div>
          <div className="factory-map" aria-label="Workshop flow from PRD to merged application">
            <div className="map-row">
              <span className="map-node node-blue">PRD</span><i>→</i><span className="map-node">Product review</span><i>→</i><span className="map-node node-human">Product gate</span>
            </div>
            <div className="map-down">↓</div>
            <div className="map-row">
              <span className="map-node">Architecture</span><i>→</i><span className="map-node">Program design</span><i>→</i><span className="map-node">Vertical slices</span>
            </div>
            <div className="map-down">↓</div>
            <div className="map-row">
              <span className="map-node node-human">Alignment gate</span><i>→</i><span className="map-node">GitHub tickets</span><i>→</i><span className="map-node node-green">QA evidence</span>
            </div>
            <div className="map-down">↓</div>
            <div className="map-row">
              <span className="map-node node-purple">Coding agents</span><i>→</i><span className="map-node">Gates</span><i>→</i><span className="map-node node-green">Merge</span>
            </div>
          </div>
        </section>

        <section className="intro-grid">
          <div>
            <h2>What you’ll build</h2>
            <p>
              You’ll transform <strong>Pocket Cinema</strong>, a mobile film browser, into
              <strong> TableStory</strong>, a responsive recipe app. The result includes recipe
              search, details, saved recipes, and keyboard-driven TV navigation.
            </p>
          </div>
          <div>
            <h2>What you’ll learn</h2>
            <ul className="check-list">
              <li>Align four expert planning contracts</li>
              <li>Trace requirements to QA evidence</li>
              <li>Control safe parallel execution</li>
              <li>Review QA-authored tests</li>
              <li>Diagnose retries and blocked work</li>
            </ul>
          </div>
        </section>

        <section className="path-section" id="choose-track">
          <div className="section-heading">
            <span className="section-kicker">Before you begin</span>
            <h2>Choose your workshop path</h2>
            <p>You can change paths later. Your selection and progress are saved in this browser.</p>
          </div>
          <div className="path-grid" role="radiogroup" aria-label="Workshop path">
            <button
              className={`path-card ${track === "rehearsal" ? "path-selected" : ""}`}
              type="button"
              role="radio"
              aria-checked={track === "rehearsal"}
              onClick={() => chooseTrack("rehearsal")}
            >
              <span className="recommended">RECOMMENDED</span>
              <span className="path-icon rehearsal-icon" aria-hidden="true">▶</span>
              <strong>Rehearsal mode</strong>
              <span>Use deterministic agents and local merges. No GitHub writes or model credentials.</span>
              <small>Best for first-time attendees</small>
            </button>
            <button
              className={`path-card ${track === "live" ? "path-selected" : ""}`}
              type="button"
              role="radio"
              aria-checked={track === "live"}
              onClick={() => chooseTrack("live")}
            >
              <span className="path-icon live-icon" aria-hidden="true">⌘</span>
              <strong>Live GitHub mode</strong>
              <span>Use real agent CLIs, GitHub Issues, Projects, worktrees, and pull requests.</span>
              <small>Requires GitHub and an agent login</small>
            </button>
          </div>
          <Callout type="note" title={`You selected ${track === "live" ? "Live GitHub mode" : "Rehearsal mode"}`}>
            The commands below now follow this path. Complete each checkpoint before moving on.
          </Callout>
        </section>

        <StepSection id="setup" number={1} title="Set up your workspace" time="8 min" completed={completed.includes("setup")} onComplete={() => toggleStep("setup")}>
          <p className="goal">Create a clean workshop checkout and confirm the required tools are available.</p>
          {track === "rehearsal" ? (
            <>
              <p>Open a terminal and run:</p>
              <CodeBlock>{`git clone https://github.com/giolaq/software-refactory-workshop.git
cd software-refactory-workshop
./setup_demo.sh --scenario recipe-rebrand`}</CodeBlock>
              <p>The setup script creates a Python environment, installs the small demo dependency set, restores Pocket Cinema, and initializes empty factory state.</p>
              <Checkpoint>
                Your terminal ends with <code>Factory reset complete for scenario: recipe-rebrand</code>.
              </Checkpoint>
            </>
          ) : (
            <>
              <p>Clone the repository, authenticate GitHub, and run the complete preflight:</p>
              <CodeBlock>{`git clone https://github.com/giolaq/software-refactory-workshop.git
cd software-refactory-workshop
gh auth login
gh auth refresh -s project
./setup_demo.sh --scenario recipe-rebrand
./factory/factory doctor --full --agent codex --qa-agent codex`}</CodeBlock>
              <Callout type="warning" title="Use a disposable repository">
                A live run creates branches, worktrees, issues, Projects items, and pull requests. Don’t use a repository that contains unrelated work.
              </Callout>
              <Checkpoint>
                The doctor reports no blocking failures. Confirm GitHub authentication includes the <code>project</code> scope and your agent CLI is authenticated.
              </Checkpoint>
            </>
          )}
        </StepSection>

        <StepSection id="baseline" number={2} title="Inspect the starting product" time="5 min" completed={completed.includes("baseline")} onComplete={() => toggleStep("baseline")}>
          <p className="goal">Understand the product before an agent changes it.</p>
          <p>Start Pocket Cinema from the repository root:</p>
          <CodeBlock>{`.factory/venv/bin/python demo-app/app.py`}</CodeBlock>
          <p>Open <a href="http://localhost:5000" target="_blank" rel="noreferrer">localhost:5000 <span aria-hidden="true">↗</span></a>. Browse the film cards, search, and open one detail page.</p>
          <div className="activity-card">
            <span className="activity-label">30-second activity</span>
            <h3>Predict the rebrand surface</h3>
            <p>Name three things that must change besides the logo. Consider data, language, routes, interaction behavior, and tests.</p>
            <details>
              <summary>Compare your answer</summary>
              <p>A complete rebrand affects the content model, public APIs, routes, navigation labels, search behavior, saved-item language, visual tokens, accessibility text, tests, and documentation.</p>
            </details>
          </div>
          <Checkpoint>
            You can explain why this is a domain conversion rather than a cosmetic redesign. Leave the app running for comparison later.
          </Checkpoint>
        </StepSection>

        <StepSection id="prd" number={3} title="Read the product requirements" time="7 min" completed={completed.includes("prd")} onComplete={() => toggleStep("prd")}>
          <p className="goal">Identify the user outcome, constraints, and observable definition of done.</p>
          <p>Open <code>recipe-app-prd.md</code> in your editor, or preview it in the terminal:</p>
          <CodeBlock>{`sed -n '1,240p' recipe-app-prd.md`}</CodeBlock>
          <h3>Focus on these sections</h3>
          <ul>
            <li><strong>Product goal:</strong> what a home cook must be able to accomplish.</li>
            <li><strong>Terminology:</strong> which cinema concepts must disappear.</li>
            <li><strong>Functional requirements:</strong> mobile, API, cookbook, and TV behavior.</li>
            <li><strong>Constraints:</strong> keep Flask and vanilla JavaScript; remain offline-capable.</li>
            <li><strong>Definition of done:</strong> what a human can verify in the finished app.</li>
          </ul>
          <div className="activity-card">
            <span className="activity-label">Decision point</span>
            <h3>Find the dangerous requirement</h3>
            <p>Which part of the PRD would create the most integration risk if several agents changed it independently?</p>
            <details>
              <summary>Suggested answer</summary>
              <p>The shared recipe data model and public API are foundational. UI tickets should depend on them, while visual tokens can begin in parallel because they have a smaller overlap surface.</p>
            </details>
          </div>
          <Checkpoint>
            You can state the final user journey in one sentence: find a recipe, inspect it, save it, and navigate it from mobile or TV.
          </Checkpoint>
        </StepSection>

        <StepSection id="plan" number={4} title="Review and approve product intent" time="15 min" completed={completed.includes("plan")} onComplete={() => toggleStep("plan")}>
          <p className="goal">Agree on the problem, behavior, scope, and evidence before any agent makes a technical decision.</p>
          <p>Run the first read-only expert. Rehearsal mode uses a deterministic, schema-valid artifact; live mode starts a fresh Codex CLI agent.</p>
          <CodeBlock>{track === "live"
            ? `./factory/factory plan recipe-app-prd.md`
            : `./factory/factory plan recipe-app-prd.md --mock`}</CodeBlock>
          <p>Copy the printed <code>PLAN_ID</code>, then open the readable Product Review:</p>
          <CodeBlock>{`./factory/factory review product PLAN_ID`}</CodeBlock>
          <h3>Review the Product Review contract</h3>
          <ol>
            <li>Does the problem describe a user need rather than a requested feature?</li>
            <li>Does every <code>R*</code> requirement have observable success evidence and a PRD source?</li>
            <li>Do journeys include failure, empty, and edge states?</li>
            <li>Are in-scope and out-of-scope boundaries unambiguous?</li>
            <li>Are mockup needs, assumptions, and blocking questions explicit?</li>
          </ol>
          <div className="activity-card">
            <span className="activity-label">Product decision</span>
            <h3>Would two teams build the same product?</h3>
            <p>Pick one requirement and explain its successful user-visible outcome. If two reasonable interpretations remain, edit <code>01-product-review.json</code> before approval.</p>
          </div>
          <p>When the behavior and scope are correct, approve only the product contract:</p>
          <CodeBlock>{`./factory/factory approve-product PLAN_ID`}</CodeBlock>
          <p>Type <code>APPROVE PRODUCT</code>. This authorizes technical planning—it does not create tickets or start implementation.</p>
          <Callout type="warning" title="Approval follows the artifact hash">
            Editing Product Review later clears this approval and marks every downstream planning artifact stale.
          </Callout>
          <Checkpoint>
            Product Review is approved, no blocking question remains, and System Architecture has not run before your decision.
          </Checkpoint>
        </StepSection>

        <StepSection id="publish" number={5} title="Align architecture, program design, and slices" time="15 min" completed={completed.includes("publish")} onComplete={() => toggleStep("publish")}>
          <p className="goal">Use three specialist contracts to make implementation predictable and reviewable before publishing tickets.</p>
          <p>Continue the approved plan. The experts run sequentially because each one consumes the previous contract.</p>
          <CodeBlock>{track === "live"
            ? `./factory/factory continue-plan PLAN_ID`
            : `./factory/factory continue-plan PLAN_ID --mock`}</CodeBlock>
          <CodeBlock label="Open the alignment review">{`./factory/factory review alignment PLAN_ID`}</CodeBlock>
          <div className="evidence-grid planning-evidence">
            <div><span>01</span><b>Product Review</b><p>Problem, behavior, journeys, scope, and evidence.</p></div>
            <div><span>02</span><b>System Architecture</b><p>Components, ownership, data models, and contracts.</p></div>
            <div><span>03</span><b>Program Design</b><p>Modules, types, signatures, calls, errors, and test seams.</p></div>
            <div><span>04</span><b>Vertical Slices</b><p>End-to-end outcomes, dependencies, file ownership, and QA evidence.</p></div>
          </div>
          <h3>Read the traceability matrix</h3>
          <p>For each <code>R*</code> row, follow the requirement through architecture contracts, program elements, ticket slices, and QA evidence. A blank final column is a reason to stop.</p>
          <h3>Expected execution waves</h3>
          <div className="waves" aria-label="Ticket dependency waves">
            <div><span>Wave 1</span><b>Recipe API</b><b>Design system</b></div>
            <i aria-hidden="true">→</i>
            <div><span>Wave 2</span><b>Mobile experience</b></div>
            <i aria-hidden="true">→</i>
            <div><span>Wave 3</span><b>TV experience</b></div>
            <i aria-hidden="true">→</i>
            <div><span>Wave 4</span><b>Docs & terminology</b></div>
          </div>
          <Callout type="tip" title="Check file ownership before parallelism">
            The validator rejects two parallel tickets that claim the same file. Dependency order is required when shared ownership is intentional.
          </Callout>
          {track === "live" ? (
            <>
              <p>Approve the whole aligned package and publish its slices:</p>
              <CodeBlock>{`./factory/factory approve PLAN_ID \
  --new-project-title "TableStory Workshop"`}</CodeBlock>
              <p>Type <code>APPROVE ALIGNMENT</code> only after reviewing all four contracts. Save the Project number printed by the command.</p>
              <Checkpoint>
                GitHub shows five issues in a new Project. Dependency-free issues are Ready; the others remain Backlog.
              </Checkpoint>
            </>
          ) : (
            <>
              <p>Rehearsal mode stops before the GitHub write. Confirm the deterministic execution set matches the reviewed five slices:</p>
              <CodeBlock>{`./factory/factory run --mock \
  --scenario recipe-rebrand --dry-run`}</CodeBlock>
              <Checkpoint>
                The alignment review is complete, its traceability rows are populated, and the preview lists Recipe API and Design system as the first wave.
              </Checkpoint>
            </>
          )}
        </StepSection>

        <StepSection id="qa" number={6} title="Let QA define the evidence" time="12 min" completed={completed.includes("qa")} onComplete={() => toggleStep("qa")}>
          <p className="goal">Review independent acceptance tests before implementation begins.</p>
          <p>First, serve the live dashboard from a second terminal:</p>
          <CodeBlock>{`python3 -m http.server 8000`}</CodeBlock>
          <p>Open <a href="http://localhost:8000/factory/dashboard.html" target="_blank" rel="noreferrer">localhost:8000/factory/dashboard.html <span aria-hidden="true">↗</span></a>.</p>
          <p>The alignment pipeline appears above the ticket board. Click a planning stage to inspect its readable artifact, hash, status, and blocking questions.</p>
          {track === "live" ? (
            <CodeBlock>{`./factory/factory run \
  --agent codex \
  --qa-agent codex \
  --review-qa-tests \
  --max-parallel 4 \
  --project-number PROJECT_NUMBER`}</CodeBlock>
          ) : (
            <CodeBlock>{`./factory/factory run --mock \
  --scenario recipe-rebrand \
  --review-qa-tests \
  --once`}</CodeBlock>
          )}
          <p>Wait for one or more tickets to enter <strong>QA Review</strong>. Click a ticket and inspect its specification, QA prompt, log, changed files, and protected test list.</p>
          <div className="activity-card">
            <span className="activity-label">Human control point</span>
            <h3>Would these tests prove the requirement?</h3>
            <p>Look for assertions that test behavior rather than implementation details. If a test is weak, stop and improve the ticket instead of approving it.</p>
          </div>
          <p>Approve a reviewed test set. In rehearsal mode, the first wave uses issues 1 and 2:</p>
          <CodeBlock>{track === "live"
            ? `./factory/factory approve-tests ISSUE_NUMBER`
            : `./factory/factory approve-tests 1 --yes
./factory/factory approve-tests 2 --yes`}</CodeBlock>
          <Callout type="note" title="Protected means protected">
            The factory records each QA test’s Git blob hash. An implementation that changes, renames, or deletes the test fails verification.
          </Callout>
          <Checkpoint>
            At least one QA test has been reviewed and approved. Its ticket is ready to resume in the preserved worktree.
          </Checkpoint>
        </StepSection>

        <StepSection id="factory" number={7} title="Run and observe the factory" time="25 min" completed={completed.includes("factory")} onComplete={() => toggleStep("factory")}>
          <p className="goal">Follow parallel implementation, verification, review, and dependency synchronization.</p>
          {track === "live" ? (
            <>
              <p>Leave the factory command running. It notices QA approvals, dispatches implementation agents, and opens pull requests after required gates pass.</p>
              <p>For each active ticket, use the dashboard to follow:</p>
            </>
          ) : (
            <>
              <p>Resume the first wave after QA approval:</p>
              <CodeBlock>{`./factory/factory run --mock \
  --scenario recipe-rebrand \
  --review-qa-tests \
  --once`}</CodeBlock>
              <p>Repeat the review-and-approve cycle when the next wave reaches QA Review. To run the remaining deterministic scenario without pauses, omit <code>--review-qa-tests</code>.</p>
            </>
          )}
          <div className="evidence-grid">
            <div><span>01</span><b>Prompt</b><p>What the agent was asked to do.</p></div>
            <div><span>02</span><b>Live log</b><p>What the agent is doing now.</p></div>
            <div><span>03</span><b>Changed files</b><p>The exact implementation surface.</p></div>
            <div><span>04</span><b>Gate output</b><p>The evidence used to pass or retry.</p></div>
          </div>
          <h3>Understand the state transitions</h3>
          <div className="state-line" aria-label="Ticket lifecycle">
            <span>Backlog</span><i>→</i><span>Ready</span><i>→</i><span>QA</span><i>→</i><span>In progress</span><i>→</i><span>Verifying</span><i>→</i><span>In review</span><i>→</i><span>Done</span>
          </div>
          <Callout type="warning" title="A failure is part of the lesson">
            Required gate output is sent back to the implementation agent for a bounded retry. Repeated failure moves the ticket to Blocked and preserves its worktree for inspection.
          </Callout>
          {track === "live" ? (
            <>
              <h3>Merge one dependency pull request</h3>
              <p>Review and merge a green pull request in GitHub. Watch the dashboard history for <strong>PR merged and synchronized</strong>.</p>
              <p>The factory fetches and fast-forwards the default branch, verifies the merge commit, and only then unlocks dependent tickets.</p>
            </>
          ) : (
            <p>Mock mode performs local merges automatically. Watch a completed ticket unlock the next dependency wave in the dashboard.</p>
          )}
          <details className="failure-lab">
            <summary>Optional: run the deliberate failure lab</summary>
            <p>Reset to the TV scenario and run it. Ticket 8 is rejected because “It feels right” cannot be converted into an objective acceptance test.</p>
            <CodeBlock>{`./setup_demo.sh --scenario tv --force
./factory/factory run --mock --scenario tv --once`}</CodeBlock>
            <p>Rewrite the issue with a measurable focus or layout requirement, then use <code>./factory/factory retry 8</code>.</p>
          </details>
          <Checkpoint>
            You can explain why a ticket passed, retried, or blocked using visible evidence—not trust in the agent.
          </Checkpoint>
        </StepSection>

        <StepSection id="finish" number={8} title="Verify the finished product" time="13 min" completed={completed.includes("finish")} onComplete={() => toggleStep("finish")}>
          <p className="goal">Connect the factory’s evidence to the user-visible product outcome.</p>
          {track === "rehearsal" && (
            <>
              <p>If you still have paused QA reviews, finish the deterministic run without human pauses:</p>
              <CodeBlock>{`./factory/factory run --mock --scenario recipe-rebrand --once`}</CodeBlock>
            </>
          )}
          <p>Start the final application:</p>
          <CodeBlock>{`.factory/venv/bin/python demo-app/app.py`}</CodeBlock>
          <div className="verification-grid">
            <a href="http://localhost:5000/" target="_blank" rel="noreferrer">
              <span className="device device-mobile" aria-hidden="true"></span>
              <b>Mobile experience</b>
              <small>localhost:5000</small>
              <p>Search by ingredient, open a recipe, and save it to My Cookbook.</p>
            </a>
            <a href="http://localhost:5000/?mode=tv" target="_blank" rel="noreferrer">
              <span className="device device-tv" aria-hidden="true"></span>
              <b>TV experience</b>
              <small>localhost:5000/?mode=tv</small>
              <p>Use Arrow keys, Enter, and Escape or Backspace without a pointer.</p>
            </a>
          </div>
          <h3>Completion checklist</h3>
          <ul className="check-list completion-list">
            <li>TableStory is recognizable from the first viewport.</li>
            <li>Recipe search matches titles and ingredients.</li>
            <li>Details contain metadata, ingredients, and ordered steps.</li>
            <li>My Cookbook exposes saved state.</li>
            <li>TV navigation works entirely from the keyboard.</li>
            <li>The dashboard shows QA tests and green gate evidence.</li>
          </ul>
          <div className="activity-card final-reflection">
            <span className="activity-label">Take it back to your team</span>
            <h3>Design your first factory experiment</h3>
            <p>Choose one repository and write down: the four planning expert prompts, ticket backend, QA policy, required gates, execution boundary, and human approval points you would use.</p>
          </div>
          <Checkpoint>
            You can explain the five control boundaries: product approval, alignment approval, QA-test approval, verification gates, and human merge.
          </Checkpoint>
        </StepSection>

        <section className="completion-panel" aria-live="polite">
          <div className="completion-ring" style={{ "--progress": `${percent * 3.6}deg` } as CSSProperties}>
            <span>{percent}%</span>
          </div>
          <div>
            <span className="section-kicker">Workshop progress</span>
            <h2>{percent === 100 ? "You completed the factory" : "Keep building"}</h2>
            <p>{percent === 100
              ? "You planned, controlled, observed, and verified a multi-agent delivery workflow."
              : `${steps.length - completed.length} step${steps.length - completed.length === 1 ? "" : "s"} remaining. Your progress is saved on this device.`}</p>
          </div>
          {percent === 100 ? (
            <a className="primary-button" href="#reference">Explore the reference <span aria-hidden="true">→</span></a>
          ) : nextStep ? (
            <a className="primary-button" href={`#${nextStep.id}`}>Continue to {nextStep.label} <span aria-hidden="true">→</span></a>
          ) : null}
        </section>

        <section className="support-section" id="troubleshooting">
          <div className="section-heading">
            <span className="section-kicker">Troubleshooting</span>
            <h2>Resolve common workshop problems</h2>
          </div>
          <div className="accordion-list">
            <details>
              <summary>The factory reports “no git remotes found”</summary>
              <p>Rehearsal mode does not require a remote. For live mode, create or attach a GitHub repository and push <code>main</code> before running the factory.</p>
              <CodeBlock>{`git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main`}</CodeBlock>
            </details>
            <details>
              <summary>A ticket says the OpenAI API key is missing</summary>
              <p>The workshop is designed to use the authenticated Codex CLI, not a direct API key. Confirm you have a current Codex executable with a saved login:</p>
              <CodeBlock>{`codex login status
./factory/factory doctor --agent codex --qa-agent codex`}</CodeBlock>
              <p>If several Codex versions are installed, set <code>FACTORY_CODEX_BIN</code> to the authenticated executable.</p>
            </details>
            <details>
              <summary>The scheduler reports a deadlock</summary>
              <p>Check whether every dependency is Done and whether its pull request was merged and synchronized. A cycle or an unmerged prerequisite keeps dependent tickets in Backlog.</p>
              <CodeBlock>{`./factory/factory status`}</CodeBlock>
            </details>
            <details>
              <summary>A planning artifact is blocked or stale</summary>
              <p>Open its JSON artifact, resolve every blocking question, and rerun <code>continue-plan</code>. Editing Product Review clears product approval; review and approve it again first. The manifest never silently reuses downstream output with changed input hashes.</p>
              <CodeBlock>{`./factory/factory review product PLAN_ID
./factory/factory approve-product PLAN_ID
./factory/factory continue-plan PLAN_ID`}</CodeBlock>
            </details>
            <details>
              <summary>A ticket is Blocked</summary>
              <p>Open the ticket drawer and inspect the final prompt, log, and gate output. Improve the issue or implementation, then retry it:</p>
              <CodeBlock>{`./factory/factory retry ISSUE_NUMBER`}</CodeBlock>
            </details>
            <details>
              <summary>Port 5000, 8000, or a worktree is already in use</summary>
              <p>Stop the earlier server or use a fresh disposable checkout. To reset only workshop state and the demo app:</p>
              <CodeBlock>{`./setup_demo.sh --scenario recipe-rebrand --force`}</CodeBlock>
              <p>The reset refuses uncommitted <code>demo-app/</code> changes unless <code>--force</code> is explicit.</p>
            </details>
          </div>
        </section>

        <section className="reference-section" id="reference">
          <div className="section-heading">
            <span className="section-kicker">Reference</span>
            <h2>Factory commands</h2>
          </div>
          <div className="reference-table" role="table" aria-label="Factory command reference">
            <div role="row"><code>factory doctor</code><span>Check whether the environment is ready.</span></div>
            <div role="row"><code>factory plan PRD.md</code><span>Run Product Review in a read-only planning run.</span></div>
            <div role="row"><code>factory review product PLAN_ID</code><span>Inspect behavior, scope, evidence, and blockers.</span></div>
            <div role="row"><code>factory approve-product PLAN_ID</code><span>Authorize technical planning without publishing tickets.</span></div>
            <div role="row"><code>factory continue-plan PLAN_ID</code><span>Run Architecture, Program Design, and Vertical Slices.</span></div>
            <div role="row"><code>factory review alignment PLAN_ID</code><span>Inspect traceability, ownership, evidence, and waves.</span></div>
            <div role="row"><code>factory approve PLAN_ID</code><span>Approve alignment and publish slices to GitHub.</span></div>
            <div role="row"><code>factory run</code><span>Schedule QA, implementation, gates, and review.</span></div>
            <div role="row"><code>factory approve-tests ISSUE</code><span>Authorize implementation after QA review.</span></div>
            <div role="row"><code>factory status</code><span>Print the current ticket state.</span></div>
            <div role="row"><code>factory retry ISSUE</code><span>Reset a blocked ticket for another attempt.</span></div>
          </div>
          <div className="next-links">
            <a href="https://github.com/giolaq/software-refactory-workshop/blob/main/factory/ARCHITECTURE.md" target="_blank" rel="noreferrer">
              <span>UNDERSTAND</span><b>Read the architecture map</b><i aria-hidden="true">→</i>
            </a>
            <a href="https://github.com/giolaq/software-refactory-workshop/blob/main/factory/README.md" target="_blank" rel="noreferrer">
              <span>EXTEND</span><b>Configure agents and gates</b><i aria-hidden="true">→</i>
            </a>
            <a href="https://github.com/giolaq/software-refactory-workshop/blob/main/factory/PLANNING.md" target="_blank" rel="noreferrer">
              <span>ALIGN</span><b>Study the four expert contracts</b><i aria-hidden="true">→</i>
            </a>
          </div>
        </section>

        <footer>
          <div className="brand footer-brand">
            <span className="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
            <span>Software <b>(re)-Factory</b></span>
          </div>
          <p>Built for learning how to control multiple coding agents with evidence.</p>
          <button type="button" onClick={resetProgress}>Reset workshop progress</button>
        </footer>
      </main>

      <aside className="right-rail" aria-label="Current workshop status">
        <div className="rail-card">
          <span className="rail-label">CURRENT PATH</span>
          <strong>{track === "live" ? "Live GitHub" : "Rehearsal"}</strong>
          <button type="button" onClick={() => document.getElementById("choose-track")?.scrollIntoView({ behavior: "smooth" })}>Change path</button>
        </div>
        <div className="rail-card">
          <span className="rail-label">YOUR PROGRESS</span>
          <strong>{percent}% complete</strong>
          <div className="progress-track"><span style={{ width: `${percent}%` }}></span></div>
          {nextStep ? <a href={`#${nextStep.id}`}>Next: {nextStep.label} →</a> : <a href="#reference">Open reference →</a>}
        </div>
        <div className="rail-card rail-help">
          <span className="rail-help-icon" aria-hidden="true">?</span>
          <strong>Need help?</strong>
          <p>Start with the ticket log and verification output.</p>
          <a href="#troubleshooting">Troubleshoot an issue</a>
        </div>
      </aside>
    </>
  );
}
