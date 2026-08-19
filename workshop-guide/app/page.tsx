"use client";

import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";

type Track = "rehearsal" | "live";

const steps = [
  { id: "setup", label: "Prepare the workshop", time: "8 min" },
  { id: "baseline", label: "Understand the system", time: "5 min" },
  { id: "prd", label: "Frame the outcome", time: "7 min" },
  { id: "plan", label: "Align product intent", time: "17 min" },
  { id: "publish", label: "Design delivery", time: "20 min" },
  { id: "qa", label: "Define acceptance evidence", time: "10 min" },
  { id: "factory", label: "Operate the factory", time: "22 min" },
  { id: "finish", label: "Verify and adapt", time: "11 min" },
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
          <p className="nav-label">Foundations</p>
          <a href="#start" onClick={() => setMenuOpen(false)}>Overview</a>
          <a href="#concept" onClick={() => setMenuOpen(false)}>What is a software factory?</a>
          <a href="#why-now" onClick={() => setMenuOpen(false)}>Why now?</a>
          <a href="#story" onClick={() => setMenuOpen(false)}>The workshop story</a>
          <p className="nav-label">Get started</p>
          <a href="#prerequisites" onClick={() => setMenuOpen(false)}>Prerequisites</a>
          <a href="#configure" onClick={() => setMenuOpen(false)}>Configure your factory</a>
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
          <p className="nav-label">Take it back</p>
          <a href="#apply" onClick={() => setMenuOpen(false)}>Design your factory</a>
          <p className="nav-label">Help</p>
          <a href="#troubleshooting" onClick={() => setMenuOpen(false)}>Troubleshooting</a>
          <a href="#reference" onClick={() => setMenuOpen(false)}>Command reference</a>
        </nav>
      </aside>

      <main id="main-content">
        <section className="hero" id="start">
          <div className="hero-copy">
            <div className="eyebrow">SELF-GUIDED DEVELOPER LAB</div>
            <h1>Turn AI coding into an engineering system</h1>
            <p className="hero-lede">
              Learn how an AI software factory turns one product requirement into
              aligned plans, reviewable tickets, independent tests, isolated changes,
              and evidence a team can trust.
            </p>
            <div className="hero-meta">
              <span><b>Level</b> Intermediate</span>
              <span><b>Time</b> 100 minutes</span>
              <span><b>Modes</b> Rehearsal or live GitHub</span>
            </div>
            <a className="primary-button" href="#concept">Start with the concept <span aria-hidden="true">→</span></a>
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

        <section className="concept-section" id="concept">
          <div className="section-heading">
            <span className="section-kicker">The operating model</span>
            <h2>What is an AI software factory?</h2>
            <p>
              An AI software factory is a repeatable delivery system in which specialized
              agents do bounded work and humans control the decisions that carry product
              or engineering risk.
            </p>
          </div>
          <div className="definition-panel">
            <p>
              A prompt asks for code. A factory defines how work moves from intent to
              production—and what evidence is required before it can move again.
            </p>
          </div>
          <div className="concept-grid">
            <article>
              <span>01</span>
              <h3>Reviewed inputs</h3>
              <p>A PRD becomes explicit product behavior, architecture contracts, program design, and vertical slices.</p>
            </article>
            <article>
              <span>02</span>
              <h3>Specialist stations</h3>
              <p>Planning, QA, and implementation agents receive one role, a bounded context, and a defined output.</p>
            </article>
            <article>
              <span>03</span>
              <h3>Controlled movement</h3>
              <p>Dependencies, worktrees, protected tests, automated gates, and human approvals determine what can advance.</p>
            </article>
            <article>
              <span>04</span>
              <h3>Visible evidence</h3>
              <p>Every ticket keeps its prompt, logs, files, test results, review state, and merge outcome.</p>
            </article>
          </div>
          <Callout type="note" title="The factory is not a model or a swarm">
            It is the workflow around the agents. You can replace the model, agent CLI,
            execution environment, or repository host while keeping the same contracts
            and control points.
          </Callout>
        </section>

        <section className="why-section" id="why-now">
          <div className="section-heading">
            <span className="section-kicker">Why now</span>
            <h2>Agents can produce more code than teams can safely absorb</h2>
            <p>
              Coding agents can inspect repositories, edit several files, run commands,
              and respond to failures. The bottleneck moves from writing code to choosing
              the right work, coordinating changes, and proving that the result is correct.
            </p>
          </div>
          <div className="why-grid">
            <article>
              <span className="why-icon" aria-hidden="true">{`{ }`}</span>
              <h3>Agents can act</h3>
              <p>They can complete repository-level tasks instead of returning only a code suggestion.</p>
            </article>
            <article>
              <span className="why-icon" aria-hidden="true">⇄</span>
              <h3>Delivery has control surfaces</h3>
              <p>Git, worktrees, tickets, CI, and pull requests give agent work clear boundaries and observable state.</p>
            </article>
            <article>
              <span className="why-icon" aria-hidden="true">✓</span>
              <h3>Evidence can be automated</h3>
              <p>Structured plans and executable tests let a system check more than whether an agent says it is finished.</p>
            </article>
          </div>
          <h3 className="subsection-title">What the factory gives a team</h3>
          <div className="benefit-grid">
            <div><b>Faster feedback</b><p>Independent work starts in parallel when ownership and dependencies allow it.</p></div>
            <div><b>Smaller reviews</b><p>Vertical slices replace one large, late implementation diff.</p></div>
            <div><b>Earlier decisions</b><p>Product and architecture ambiguity appears before code makes it expensive.</p></div>
            <div><b>Traceable confidence</b><p>Requirements connect to tickets, tests, gate output, and merge history.</p></div>
          </div>
        </section>

        <section className="story-section" id="story">
          <div className="section-heading">
            <span className="section-kicker">The workshop story</span>
            <h2>Follow one requirement from intent to evidence.</h2>
            <p>
              You will transform <strong>Pocket Cinema</strong>, a mobile film browser,
              into <strong>TableStory</strong>, a responsive recipe app. Follow the mobile
              recipe journey from the PRD through reviewed plans, GitHub tickets,
              independent QA, isolated implementation, and verification.
            </p>
          </div>
          <div className="story-line" aria-label="Four-part workshop learning journey">
            <article><span>Act 1 · Steps 1–3</span><h3>Understand</h3><p>Prepare the environment, inspect the existing product, and frame the required outcome.</p></article>
            <article><span>Act 2 · Steps 4–6</span><h3>Align</h3><p>Turn intent into contracts, slices, and acceptance evidence before implementation.</p></article>
            <article><span>Act 3 · Step 7</span><h3>Operate</h3><p>Watch bounded agents work through dependencies, retries, gates, and review.</p></article>
            <article><span>Act 4 · Step 8</span><h3>Adapt</h3><p>Inspect the evidence and design the smallest useful factory for your team.</p></article>
          </div>
          <div className="outcome-grid">
            <div>
              <h3>What you will build</h3>
              <p>Recipe search, details, saved recipes, and keyboard-driven TV navigation in a rebranded application.</p>
            </div>
            <div>
              <h3>What you will be able to do</h3>
              <ul className="check-list">
                <li>Choose useful agent roles and boundaries</li>
                <li>Place human approval where risk changes</li>
                <li>Trace requirements to acceptance evidence</li>
                <li>Decide when parallel work is safe</li>
                <li>Diagnose retries and blocked work</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="prerequisites-section" id="prerequisites">
          <div className="section-heading">
            <span className="section-kicker">Prerequisites</span>
            <h2>Prepare your development environment</h2>
            <p>Complete these checks before the workshop. A Rehearsal Run has no account or model requirement.</p>
          </div>
          <div className="prerequisites-grid">
            <article>
              <span className="requirement-label">Both modes</span>
              <h3>Local tools</h3>
              <ul>
                <li>macOS, Linux, or Windows with WSL 2</li>
                <li>Python 3.11 or later with <code>venv</code></li>
                <li>Node.js 20 or later</li>
                <li>Git and a current web browser</li>
                <li>Permission to create sibling directories</li>
                <li>Ports 5000, 5050, and 8000 available</li>
              </ul>
            </article>
            <article>
              <span className="requirement-label">Live Run only</span>
              <h3>Accounts and access</h3>
              <ul>
                <li>GitHub CLI authenticated with the <code>project</code> scope</li>
                <li>A disposable repository you can push to</li>
                <li>Permission to create issues, Projects, and pull requests</li>
                <li>A current, authenticated Claude or Codex CLI for structured planning</li>
                <li>An authenticated implementation and QA agent CLI or wrapper</li>
                <li>Network access to GitHub and the agent provider</li>
              </ul>
            </article>
          </div>
          <h3>Check the required versions</h3>
          <CodeBlock>{`python3 --version   # 3.11 or later
node --version      # 20 or later
git --version`}</CodeBlock>
          <p className="install-links">
            Install a missing tool: <a href="https://www.python.org/downloads/" target="_blank" rel="noreferrer">Python</a>
            <span aria-hidden="true"> · </span><a href="https://nodejs.org/en/download" target="_blank" rel="noreferrer">Node.js</a>
            <span aria-hidden="true"> · </span><a href="https://git-scm.com/downloads" target="_blank" rel="noreferrer">Git</a>
            <span aria-hidden="true"> · </span><a href="https://cli.github.com/" target="_blank" rel="noreferrer">GitHub CLI</a>
            <span aria-hidden="true"> · </span><a href="https://code.claude.com/docs/en/cli-usage" target="_blank" rel="noreferrer">Claude Code</a>
          </p>
          <h3>Set up the live worked example</h3>
          <p>The guided commands use Claude. On macOS, Linux, or WSL, install the current CLI and sign in with your Claude account:</p>
          <CodeBlock>{`curl -fsSL https://claude.ai/install.sh | bash
claude auth login
claude auth status --text`}</CodeBlock>
          <Callout type="note" title="No API key is required">
            A Rehearsal Run uses deterministic local agents. The Claude worked example uses your authenticated Claude Code session; it does not require <code>OPENAI_API_KEY</code> or <code>ANTHROPIC_API_KEY</code>. You can choose another supported setup below.
          </Callout>
          <h3>Use separate terminals</h3>
          <div className="terminal-grid">
            <div><b>Terminal A</b><span>Factory commands</span></div>
            <div><b>Terminal B</b><span>Dashboard server</span></div>
            <div><b>Terminal C</b><span>Demo app, if needed</span></div>
          </div>
        </section>

        <section className="configuration-section" id="configure">
          <div className="section-heading">
            <span className="section-kicker">Project configuration</span>
            <h2>Use the agents your team already trusts</h2>
            <p>
              The factory controls the workflow; it does not require one coding model.
              Choose built-in adapters by role or register a noninteractive command for
              your own agent, model wrapper, container, or remote runner.
            </p>
          </div>
          <div className="prerequisites-grid">
            <article>
              <span className="requirement-label">Structured planning</span>
              <h3>Claude or Codex</h3>
              <p>One of these adapters runs the four planning experts and validates their JSON contracts.</p>
            </article>
            <article>
              <span className="requirement-label">Implementation and QA</span>
              <h3>Any registered adapter</h3>
              <p>Use Claude, Codex, Cursor, or a lowercase adapter name registered in <code>factory/factory.toml</code>.</p>
            </article>
          </div>

          <h3>Start with a preset</h3>
          <p>Use one command to save attendee-specific defaults in the ignored <code>.factory/local.toml</code> file:</p>
          <CodeBlock>{`# Claude for planning, QA, and implementation
./factory/factory configure --preset claude-workshop

# Codex for planning, QA, and implementation
./factory/factory configure --preset codex-workshop`}</CodeBlock>

          <h3>Mix adapters by role</h3>
          <p>Planning, independent QA, and implementation do not need to use the same CLI:</p>
          <CodeBlock>{`./factory/factory configure \\
  --planning-agent claude \\
  --agent cursor \\
  --qa-agent codex \\
  --review-qa-tests \\
  --max-parallel 2`}</CodeBlock>

          <h3>Register your own implementation or QA agent</h3>
          <p>Add its command to the committed project policy in <code>factory/factory.toml</code>:</p>
          <CodeBlock label="factory/factory.toml">{`[agents]
my-agent = './tools/run-my-agent.sh {prompt}'`}</CodeBlock>
          <p>
            The command runs from an isolated ticket worktree. It must read the prompt,
            run without interactive input, keep changes in that worktree, stream useful
            output, and return a nonzero exit status on failure. Put model flags,
            authentication-aware launch logic, and container or remote-runner setup in
            the wrapper.
          </p>
          <CodeBlock>{`./factory/factory configure \\
  --planning-agent claude \\
  --agent my-agent \\
  --qa-agent my-agent \\
  --review-qa-tests \\
  --max-parallel 2

./factory/factory doctor --full`}</CodeBlock>

          <h3>Configure project policy</h3>
          <p>
            Edit the committed <code>factory/factory.toml</code> file so the factory
            uses your repository&apos;s time limits, acceptance-test directories, and
            verification commands:
          </p>
          <CodeBlock label="factory/factory.toml">{`[factory]
max_retries = 2
agent_timeout = 900
gate_timeout = 300

[qa]
agent = "my-agent"
max_retries = 1
require_human_approval = true
test_roots = ["tests/acceptance", "web/tests"]

[[gate]]
name = "unit-tests"
cmd = '{python} -m pytest -q'
required = true

[[gate]]
name = "lint"
cmd = 'npm run lint'
required = true`}</CodeBlock>
          <p>
            QA may add tests only below <code>test_roots</code>. Gates run in order
            from each ticket worktree. A required gate blocks the ticket after its
            retries; an optional gate records a warning.
          </p>

          <h3>Connect a GitHub Project</h3>
          <p>Save an existing Project number locally, or let plan approval create and remember a new Project:</p>
          <CodeBlock>{`# Use an existing GitHub Project
./factory/factory configure --project-number PROJECT_NUMBER

# Or create one after reviewing the PRD-derived plan
./factory/factory approve PLAN_ID \\
  --new-project-title "My workshop"`}</CodeBlock>
          <Callout type="tip" title="Project policy stays with the repository">
            Commit agent command templates, Acceptance Test roots, retry and timeout values, and
            verification gates in <code>factory/factory.toml</code>. Keep credentials and
            each attendee&apos;s selected agents and GitHub Project number outside Git in
            <code>.factory/local.toml</code>.
          </Callout>
          <p>
            See the <a href="https://github.com/giolaq/software-refactory-workshop/blob/main/factory/CONFIGURATION.md" target="_blank" rel="noreferrer">complete configuration guide <span aria-hidden="true">↗</span></a> for
            placeholders, QA policy, gates, custom execution environments, and preflight.
          </p>
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
              <strong>Rehearsal Run</strong>
              <span>Run deterministic planning, QA, implementation, and local merges. No GitHub writes or model credentials.</span>
              <small>Use this path for the dry run</small>
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
              <small>Requires a disposable repository and authenticated agents</small>
            </button>
          </div>
          <Callout type="note" title={`You selected ${track === "live" ? "Live GitHub Run" : "Rehearsal Run"}`}>
            The commands below now follow this path. Complete each checkpoint before moving on.
          </Callout>
        </section>

        <StepSection id="setup" number={1} title="Prepare a safe workspace" time="8 min" completed={completed.includes("setup")} onComplete={() => toggleStep("setup")}>
          <p className="goal">Create a clean checkout, initialize the demo, and pass the readiness check for your selected mode.</p>
          {track === "rehearsal" ? (
            <>
              <p>In Terminal A, clone the workshop and prepare the deterministic recipe scenario:</p>
              <CodeBlock>{`git clone https://github.com/giolaq/software-refactory-workshop.git
cd software-refactory-workshop
./setup_demo.sh --scenario recipe-rebrand`}</CodeBlock>
              <p>The script creates the Python environment, installs Flask and pytest, restores Pocket Cinema, and initializes empty factory state. It doesn’t call GitHub or a model.</p>
              <Checkpoint>
                Your terminal ends with <code>Factory reset complete for scenario: recipe-rebrand</code>.
              </Checkpoint>
            </>
          ) : (
            <>
              <p>These guided commands use the Claude preset. Confirm GitHub and Claude access before creating the disposable repository. If you selected another setup above, run its login checks and substitute its <code>factory configure</code> command.</p>
              <CodeBlock>{`gh auth status
gh auth refresh -s project
claude auth login
claude auth status --text`}</CodeBlock>
              <p>Clone the workshop, replace its read-only upstream remote with a private disposable repository, and run the full preflight:</p>
              <CodeBlock>{`git clone https://github.com/giolaq/software-refactory-workshop.git
cd software-refactory-workshop
git remote rename origin upstream
gh repo create software-refactory-dry-run \
  --private --source=. --remote=origin --push
./setup_demo.sh --scenario recipe-rebrand
git push origin main
./factory/factory configure --preset claude-workshop
./factory/factory doctor --full`}</CodeBlock>
              <p>If that repository name already exists, choose another name. The doctor checks the clean branch, remote synchronization, GitHub Projects access, selected agent adapters, ports, QA policy, and all configured gates.</p>
              <Callout type="warning" title="Use a disposable repository">
                A live run creates branches, worktrees, issues, Projects items, and pull requests. Don’t use a repository that contains unrelated work.
              </Callout>
              <Checkpoint>
                The doctor reports <code>0 failures</code>. A warning is acceptable only for an optional agent that you won’t use.
              </Checkpoint>
            </>
          )}
        </StepSection>

        <StepSection id="baseline" number={2} title="Understand the product you are changing" time="5 min" completed={completed.includes("baseline")} onComplete={() => toggleStep("baseline")}>
          <p className="goal">Understand the product before an agent changes it.</p>
          <p>Start Pocket Cinema from the repository root:</p>
          <CodeBlock>{`.factory/venv/bin/python demo-app/app.py`}</CodeBlock>
          <p>Open <a href="http://localhost:5000" target="_blank" rel="noreferrer">localhost:5000 <span aria-hidden="true">↗</span></a>. Browse the film cards, search, and open one detail page. When you finish, return to the terminal and press <code>Ctrl+C</code> so the final app can use the same port.</p>
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
            You can explain why this is a domain conversion rather than a cosmetic redesign, and the baseline server is stopped.
          </Checkpoint>
        </StepSection>

        <StepSection id="prd" number={3} title="Frame the required outcome" time="7 min" completed={completed.includes("prd")} onComplete={() => toggleStep("prd")}>
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

        <StepSection id="plan" number={4} title="Align product intent before code" time="17 min" completed={completed.includes("plan")} onComplete={() => toggleStep("plan")}>
          <p className="goal">Agree on the problem, behavior, scope, and evidence before any agent makes a technical decision.</p>
          <p>Run the first read-only expert. A Rehearsal Run uses a deterministic, schema-valid artifact; a Live Run starts a fresh Claude Code planning agent.</p>
          <CodeBlock>{track === "live"
            ? `./factory/factory plan recipe-app-prd.md`
            : `./factory/factory plan recipe-app-prd.md --mock`}</CodeBlock>
          <p>Copy the printed <code>PLAN_ID</code>. You will use it in every remaining planning command. Then open the readable Product Review:</p>
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
            <p>Pick one requirement and explain its successful user-visible outcome. If two reasonable interpretations remain, edit <code>.factory/plans/PLAN_ID/01-product-review.json</code>, review it again, and approve only when the ambiguity is resolved.</p>
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

        <StepSection id="publish" number={5} title="Design architecture, programs, and slices" time="20 min" completed={completed.includes("publish")} onComplete={() => toggleStep("publish")}>
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
          <Callout type="note" title="Tickets come from the PRD">
            The Vertical Slices expert creates the backlog from the approved PRD, architecture, and program design. Seeding is not part of the normal path; <code>factory seed recipe-rebrand</code> is a deterministic recovery option when live planning cannot finish.
          </Callout>
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
              <p>Type <code>APPROVE ALIGNMENT</code> only after reviewing all four contracts. The factory creates the GitHub tickets, adds them to the new Project, and remembers that Project for later commands.</p>
              <Checkpoint>
                GitHub shows five issues in a new Project. Dependency-free issues are Ready; the others remain Backlog.
              </Checkpoint>
            </>
          ) : (
            <>
              <p>A Rehearsal Run doesn’t write to GitHub. Preview the five deterministic tickets and their dependency order:</p>
              <CodeBlock>{`./factory/factory run --mock \
  --scenario recipe-rebrand --dry-run`}</CodeBlock>
              <Checkpoint>
                The alignment review is complete, its traceability rows are populated, and the preview lists Recipe API and Design system as the first wave.
              </Checkpoint>
            </>
          )}
        </StepSection>

        <StepSection id="qa" number={6} title="Define acceptance evidence before implementation" time="10 min" completed={completed.includes("qa")} onComplete={() => toggleStep("qa")}>
          <p className="goal">Review independent acceptance tests before implementation begins.</p>
          <p>In Terminal B, serve the dashboard from the repository root and leave it running:</p>
          <CodeBlock>{`python3 -m http.server 8000`}</CodeBlock>
          <p>Open <a href="http://localhost:8000/factory/dashboard.html" target="_blank" rel="noreferrer">localhost:8000/factory/dashboard.html <span aria-hidden="true">↗</span></a>. Return to Terminal A before starting the factory.</p>
          <p>The alignment pipeline appears above the ticket board. Click a planning stage to inspect its readable artifact, hash, status, and blocking questions.</p>
          {track === "live" ? (
            <CodeBlock>{`./factory/factory run`}</CodeBlock>
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
          <p>Approve a reviewed test set from another terminal. In a Rehearsal Run, the first wave uses issues 1 and 2:</p>
          <CodeBlock>{track === "live"
            ? `./factory/factory approve-tests ISSUE_NUMBER`
            : `./factory/factory approve-tests 1 --yes
./factory/factory approve-tests 2 --yes`}</CodeBlock>
          <Callout type="note" title="Protected means protected">
            The factory records each Acceptance Test’s Git blob hash. An implementation that changes, renames, or deletes the test fails verification.
          </Callout>
          <Checkpoint>
            At least one Acceptance Test has been reviewed and approved. Its ticket is ready to resume in the preserved worktree.
          </Checkpoint>
        </StepSection>

        <StepSection id="factory" number={7} title="Operate and observe the factory" time="22 min" completed={completed.includes("factory")} onComplete={() => toggleStep("factory")}>
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
              <p>This command resumes the approved first wave and runs the remaining deterministic tickets without another manual QA pause. Independent QA still runs for every ticket.</p>
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
            <p>A Rehearsal Run performs local merges automatically. Watch a completed ticket unlock the next dependency wave in the dashboard.</p>
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

        <StepSection id="finish" number={8} title="Verify, decide, and adapt" time="11 min" completed={completed.includes("finish")} onComplete={() => toggleStep("finish")}>
          <p className="goal">Verify the user outcome, inspect its delivery evidence, and decide which controls your own work needs.</p>
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
            <li>The dashboard shows Acceptance Tests and green gate evidence.</li>
          </ul>
          <h3>Review the delivery evidence</h3>
          <ul className="check-list">
            <li>Trace requirement R3 from Product Review to its ticket and acceptance evidence.</li>
            <li>Explain why one dependency waited and what caused it to unlock.</li>
            <li>Use prompt, test, gate, and merge evidence to explain why the narrative ticket is complete.</li>
          </ul>
          <div className="activity-card final-reflection">
            <span className="activity-label">Take it back to your team</span>
            <h3>Design your first factory experiment</h3>
            <p>Choose one repository and identify its most expensive delivery risk. The design guide after this step helps you select only the controls that address that risk.</p>
          </div>
          <Checkpoint>
            You can explain the factory’s control boundaries and choose which ones address the delivery risk in your own use case.
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

        <section className="apply-section" id="apply">
          <div className="section-heading">
            <span className="section-kicker">Use it for your work</span>
            <h2>Design the factory your delivery risk requires</h2>
            <p>
              The goal is not to reproduce every workshop stage. Start with the smallest
              operating model that makes your next change easier to understand, review,
              and trust.
            </p>
          </div>
          <div className="control-spectrum">
            <article>
              <span>LOW COORDINATION</span>
              <h3>Direct agent</h3>
              <p>Use for a clear, reversible change with a small diff and strong existing tests.</p>
              <ul><li>One task</li><li>One workspace</li><li>Human diff review</li></ul>
            </article>
            <article className="spectrum-featured">
              <span>SHARED CHANGE</span>
              <h3>Guided workflow</h3>
              <p>Use when a feature crosses files or layers but does not need several agents at once.</p>
              <ul><li>Reviewed outcome</li><li>QA acceptance tests</li><li>Automated gates</li></ul>
            </article>
            <article>
              <span>HIGH COORDINATION</span>
              <h3>Software factory</h3>
              <p>Use when work has shared contracts, dependent slices, parallel agents, or high failure cost.</p>
              <ul><li>Specialist plans</li><li>Isolated execution</li><li>Approval gates and evidence</li></ul>
            </article>
          </div>

          <h3 className="subsection-title">Patterns you can adapt</h3>
          <div className="use-case-grid">
            <article><b>Legacy modernization</b><p>Map existing contracts first, slice by user journey, and let regression QA protect behavior during replacement.</p></article>
            <article><b>Platform migration</b><p>Use program design to define compatibility boundaries, then schedule dependency waves across services or packages.</p></article>
            <article><b>Product-critical features</b><p>Add independent QA, protected acceptance tests, and a human approval before implementation changes user-visible behavior.</p></article>
            <article><b>Multi-team delivery</b><p>Use product review and ownership maps to settle terminology, interfaces, and handoffs before parallel work begins.</p></article>
          </div>

          <div className="canvas-panel">
            <div>
              <span className="section-kicker">Factory design canvas</span>
              <h3>Answer five questions</h3>
              <p>Your answers define the first version of your operating model.</p>
            </div>
            <ol>
              <li><b>Input</b><span>What must be true before an agent starts?</span></li>
              <li><b>Roles</b><span>Which decisions need a specialist perspective?</span></li>
              <li><b>Boundaries</b><span>How will concurrent work stay isolated?</span></li>
              <li><b>Evidence</b><span>What proves the user outcome and engineering constraints?</span></li>
              <li><b>Authority</b><span>Which transitions require a human decision?</span></li>
            </ol>
          </div>
          <Callout type="tip" title="Run one bounded experiment next week">
            Choose a feature that normally takes one or two days. Save the baseline,
            add one planning contract and one independent QA gate, then compare review
            time, rework, and confidence with your usual workflow. Keep the controls that
            changed the outcome; remove the ones that did not.
          </Callout>
        </section>

        <section className="support-section" id="troubleshooting">
          <div className="section-heading">
            <span className="section-kicker">Troubleshooting</span>
            <h2>Resolve common workshop problems</h2>
          </div>
          <div className="accordion-list">
            <details>
              <summary>A prerequisite command is missing or too old</summary>
              <p>Install the required version, open a new terminal, and run the version checks again. Windows users should run the workshop inside WSL 2, not Command Prompt or PowerShell.</p>
              <CodeBlock>{`python3 --version
node --version
git --version`}</CodeBlock>
            </details>
            <details>
              <summary>The live-mode doctor reports a failure</summary>
              <p>Don’t continue with a failed preflight. Read the named check, fix that condition, and rerun the same doctor command. Your saved configuration tells the doctor which adapters are required.</p>
              <CodeBlock>{`./factory/factory doctor --full`}</CodeBlock>
            </details>
            <details>
              <summary>The factory reports “no git remotes found”</summary>
              <p>A Rehearsal Run does not require a remote. For a Live Run, create or attach a GitHub repository and push <code>main</code> before running the factory.</p>
              <CodeBlock>{`git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main`}</CodeBlock>
            </details>
            <details>
              <summary>Claude is missing or not signed in</summary>
              <p>The Claude workshop preset uses the Claude Code CLI for all four planning experts, independent QA, and implementation. Check the saved login and rerun the doctor; no API key is required.</p>
              <CodeBlock>{`claude auth login
claude auth status --text
./factory/factory doctor`}</CodeBlock>
            </details>
            <details>
              <summary>My custom agent is not registered</summary>
              <p>Add the lowercase adapter name and noninteractive command under <code>[agents]</code> in <code>factory/factory.toml</code>. Use the same name in <code>factory configure</code>, then run preflight again.</p>
              <CodeBlock label="factory/factory.toml">{`[agents]
my-agent = './tools/run-my-agent.sh {prompt}'`}</CodeBlock>
            </details>
            <details>
              <summary>Live planning is too slow for the workshop</summary>
              <p>Use the deterministic TableStory backlog only as a recovery path. This command creates reviewed fixture tickets and clearly reports that it bypasses PRD planning and the two alignment gates:</p>
              <CodeBlock>{`./factory/factory seed recipe-rebrand`}</CodeBlock>
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
            <div role="row"><code>factory configure --preset claude-workshop</code><span>Save local Claude defaults for short commands.</span></div>
            <div role="row"><code>factory configure --agent NAME --qa-agent NAME</code><span>Save registered implementation and QA adapters.</span></div>
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
            <div role="row"><code>factory seed recipe-rebrand</code><span>Create deterministic fallback tickets without running planning.</span></div>
          </div>
          <div className="next-links">
            <a href="https://github.com/giolaq/software-refactory-workshop/blob/main/factory/ARCHITECTURE.md" target="_blank" rel="noreferrer">
              <span>UNDERSTAND</span><b>Read the architecture map</b><i aria-hidden="true">→</i>
            </a>
            <a href="https://github.com/giolaq/software-refactory-workshop/blob/main/factory/CONFIGURATION.md" target="_blank" rel="noreferrer">
              <span>EXTEND</span><b>Configure your agents and project</b><i aria-hidden="true">→</i>
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
          <a href="#apply">Design your factory →</a>
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
