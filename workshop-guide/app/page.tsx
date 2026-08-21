"use client";

import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";

type Track = "rehearsal" | "live";

const steps = [
  { id: "setup", label: "Set up", time: "8 min" },
  { id: "baseline", label: "Inspect the app", time: "5 min" },
  { id: "prd", label: "Read the PRD", time: "7 min" },
  { id: "plan", label: "Review product intent", time: "15 min" },
  { id: "publish", label: "Create tickets", time: "18 min" },
  { id: "qa", label: "Approve tests", time: "10 min" },
  { id: "factory", label: "Run the factory", time: "22 min" },
  { id: "finish", label: "Verify the result", time: "15 min" },
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
      <div className="checkpoint-title"><span aria-hidden="true">✓</span> Check</div>
      <div>{children}</div>
    </div>
  );
}

function WorkshopPaths({
  click,
  inspect,
  continueWhen,
  children,
}: {
  click: ReactNode;
  inspect: ReactNode;
  continueWhen: ReactNode;
  children: string;
}) {
  return (
    <div className="instruction-paths">
      <section className="instruction-card control-center-card" aria-label="Control Center path">
        <span className="path-label">Control Center</span>
        <h3>Use the web interface</h3>
        <dl className="instruction-list">
          <div><dt>Click</dt><dd>{click}</dd></div>
          <div><dt>Inspect</dt><dd>{inspect}</dd></div>
          <div><dt>Continue when</dt><dd>{continueWhen}</dd></div>
        </dl>
      </section>
      <section className="instruction-card cli-card" aria-label="CLI path">
        <span className="path-label">CLI</span>
        <h3>Run the equivalent commands</h3>
        <CodeBlock label="CLI">{children}</CodeBlock>
      </section>
    </div>
  );
}

function WorkshopMedia({
  src,
  alt,
  label,
  caption,
  width,
  height,
  portrait = false,
  illustration = false,
}: {
  src: string;
  alt: string;
  label: string;
  caption: string;
  width: number;
  height: number;
  portrait?: boolean;
  illustration?: boolean;
}) {
  return (
    <figure className={`workshop-figure${portrait ? " workshop-figure-portrait" : ""}${illustration ? " workshop-illustration" : ""}`}>
      <a className="workshop-screenshot" href={src} target="_blank" rel="noreferrer">
        {/* These local screenshots keep their intrinsic size and open as source evidence. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} width={width} height={height} loading="lazy" />
        <span>Open image</span>
      </a>
      <figcaption><strong>{label}</strong><span>{caption}</span></figcaption>
      {illustration && (
        <p className="illustration-credit">
          Illustration created for this workshop with the Ian Xiaohei illustration workflow. Source skill: <a href="https://github.com/helloianneo/ian-xiaohei-illustrations">helloianneo/ian-xiaohei-illustrations</a>.
        </p>
      )}
    </figure>
  );
}

function StepSection({
  index,
  id,
  title,
  goal,
  complete,
  onToggle,
  children,
}: {
  index: number;
  id: string;
  title: string;
  goal: string;
  complete: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section id={id} className={`lesson${complete ? " lesson-complete" : ""}`}>
      <div className="lesson-heading">
        <span className="step-number">{complete ? "✓" : index}</span>
        <div>
          <span className="lesson-kicker">Step {index} · {steps[index - 1].time}</span>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="lesson-body">
        <p className="goal"><strong>Goal:</strong> {goal}</p>
        {children}
      </div>
      <div className="lesson-footer">
        <button className={`complete-button${complete ? " completed" : ""}`} type="button" onClick={onToggle}>
          {complete ? "Completed" : "Mark step complete"}
        </button>
      </div>
    </section>
  );
}

export default function Home() {
  const [track, setTrack] = useState<Track>("rehearsal");
  const [completed, setCompleted] = useState<string[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const restore = window.setTimeout(() => {
      const storedTrack = window.localStorage.getItem("workshop-track");
      const storedCompleted = window.localStorage.getItem("workshop-completed");
      if (storedTrack === "rehearsal" || storedTrack === "live") setTrack(storedTrack);
      if (storedCompleted) {
        try {
          setCompleted(JSON.parse(storedCompleted));
        } catch {
          window.localStorage.removeItem("workshop-completed");
        }
      }
    }, 0);
    return () => window.clearTimeout(restore);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("workshop-track", track);
  }, [track]);

  useEffect(() => {
    window.localStorage.setItem("workshop-completed", JSON.stringify(completed));
  }, [completed]);

  const progress = useMemo(() => Math.round((completed.length / steps.length) * 100), [completed]);

  function toggleStep(id: string) {
    setCompleted((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  function chooseTrack(next: Track) {
    setTrack(next);
    document.getElementById("setup")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to workshop</a>
      <header className="topbar">
        <button className="menu-button" type="button" aria-label="Open navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>
          <span /><span /><span />
        </button>
        <a className="brand" href="#overview">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>
          <b>Software (re)-Factory</b>
        </a>
        <span className="header-divider" aria-hidden="true" />
        <span className="header-section">Workshop guide</span>
        <div className="topbar-actions">
          <span className="duration-pill">100 minutes</span>
          <a className="github-link" href="https://github.com/giolaq/software-refactory-workshop">GitHub</a>
        </div>
      </header>

      {menuOpen && <button className="nav-scrim" type="button" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <aside className={`left-nav ${menuOpen ? "left-nav-open" : ""}`} aria-label="Workshop steps">
        <div className="nav-progress">
          <div className="nav-progress-row"><span>Progress</span><strong>{completed.length}/{steps.length}</strong></div>
          <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
        </div>
        <nav aria-label="Workshop sections">
          <p className="nav-label">Start</p>
          <a href="#overview" onClick={() => setMenuOpen(false)}>Overview</a>
          <a href="#prerequisites" onClick={() => setMenuOpen(false)}>Prerequisites</a>
          <a href="#path" onClick={() => setMenuOpen(false)}>Choose a path</a>
          <p className="nav-label">Workshop</p>
          {steps.map((step, index) => (
            <a key={step.id} href={`#${step.id}`} className={completed.includes(step.id) ? "nav-step-complete" : ""} onClick={() => setMenuOpen(false)}>
              <span>{completed.includes(step.id) ? "✓" : index + 1}</span>
              <span>{step.label}<small>{step.time}</small></span>
            </a>
          ))}
          <p className="nav-label">Afterward</p>
          <a href="#adapt" onClick={() => setMenuOpen(false)}>Use your own agents</a>
          <a href="#troubleshooting" onClick={() => setMenuOpen(false)}>Troubleshooting</a>
          <a href="#reference" onClick={() => setMenuOpen(false)}>Command reference</a>
        </nav>
      </aside>
      <main id="main-content">
        <section id="overview" className="hero">
          <div>
            <span className="eyebrow">Hands-on developer workshop</span>
            <h1>Turn a PRD into verified code</h1>
            <p className="hero-lede">
              Plan with expert agents, approve the tickets, run coding agents in isolated worktrees, and verify their evidence before merge.
            </p>
            <div className="hero-meta">
              <span><b>Duration:</b> 100 minutes</span>
              <span><b>Format:</b> individual repository</span>
              <span><b>Tools:</b> Claude, Codex, Cursor, or your own CLI</span>
            </div>
            <a className="primary-button" href="#prerequisites">Start the workshop</a>
          </div>
          <div className="factory-map" aria-label="Workshop workflow">
            <div className="map-row"><span className="map-node">PRD</span><i>→</i><span className="map-node node-blue">Plan</span><i>→</i><span className="map-node node-human">Approve</span></div>
            <div className="map-down">↓</div>
            <div className="map-row"><span className="map-node node-purple">Agents</span><i>→</i><span className="map-node node-blue">QA</span><i>→</i><span className="map-node node-human">Review</span></div>
            <div className="map-down">↓</div>
            <div className="map-row"><span className="map-node node-green">Verified change</span></div>
          </div>
        </section>

        <section className="concept-section">
          <div className="section-heading">
            <span className="section-kicker">The idea</span>
            <h2>A factory is the workflow around the agents</h2>
            <p>Agents supply execution. The factory supplies shared context, isolation, quality gates, evidence, and human decisions.</p>
          </div>
          <WorkshopMedia
            src="/illustrations/01-from-prompt-to-evidence.png"
            alt="A developer guides work from a PRD through agents and quality gates to verified evidence"
            label="From prompt to evidence"
            caption="The useful unit is not generated code. It is a reviewed change with proof."
            width={1600}
            height={900}
            illustration
          />
          <div className="concept-grid compact-concept-grid">
            <article><span>01</span><h3>Plan</h3><p>Turn product intent into contracts and small vertical slices.</p></article>
            <article><span>02</span><h3>Build</h3><p>Give each ticket and agent an isolated Git worktree.</p></article>
            <article><span>03</span><h3>Verify</h3><p>Let QA define tests before implementation begins.</p></article>
            <article><span>04</span><h3>Review</h3><p>Merge only when tests, evidence, and human review agree.</p></article>
          </div>
        </section>

        <section id="prerequisites" className="prerequisites-section">
          <div className="section-heading">
            <span className="section-kicker">Before the session</span>
            <h2>Prerequisites</h2>
            <p>Install these before the workshop. Do not spend workshop time on machine setup.</p>
          </div>
          <div className="prerequisites-grid">
            <article>
              <span className="requirement-label">Everyone</span>
              <h3>Local tools</h3>
              <ul>
                <li>macOS, Linux, or Windows with WSL2</li>
                <li>Python 3.11+ with virtual environments</li>
                <li>Node.js 20+, Git, and a modern browser</li>
                <li>Ports 5000 and 5050 available</li>
                <li>GitHub CLI and one personal workshop repository</li>
              </ul>
            </article>
            <article>
              <span className="requirement-label">Live path</span>
              <h3>Accounts and access</h3>
              <ul>
                <li>GitHub CLI with the <code>project</code> scope</li>
                <li>Permission to create issues, branches, and Projects</li>
                <li>An authenticated Claude, Codex, Cursor, or custom agent CLI</li>
                <li>Network access to GitHub and your model provider</li>
              </ul>
            </article>
          </div>
          <CodeBlock label="Check versions">{`python3 --version
node --version
git --version
gh --version`}</CodeBlock>
          <Callout type="warning" title="Use your own repository">
            <p>Every attendee creates a personal workshop repository. The facilitator uses a different repository on screen.</p>
          </Callout>
        </section>

        <section id="path" className="path-section">
          <div className="section-heading">
            <span className="section-kicker">Choose once</span>
            <h2>Select your path</h2>
            <p>The page changes its commands to match your choice.</p>
          </div>
          <div className="path-grid">
            <button type="button" className={`path-card${track === "rehearsal" ? " path-selected" : ""}`} onClick={() => chooseTrack("rehearsal")}>
              <span className="recommended">Recommended for a dry run</span>
              <span className="path-icon rehearsal-icon">R</span>
              <strong>Rehearsal</strong>
              <span>Uses deterministic fixtures. It does not write to GitHub Projects or require a model login or API key.</span>
              <small>Best for learning the workflow quickly.</small>
            </button>
            <button type="button" className={`path-card${track === "live" ? " path-selected" : ""}`} onClick={() => chooseTrack("live")}>
              <span className="path-icon live-icon">L</span>
              <strong>Live</strong>
              <span>Uses your repository, GitHub Project, and real coding agents.</span>
              <small>Best after the rehearsal path works.</small>
            </button>
          </div>
        </section>

        <StepSection index={1} id="setup" title="Set up" goal="Start from a clean, personal workshop repository." complete={completed.includes("setup")} onToggle={() => toggleStep("setup")}>
          <p>Clone the workshop and create your own repository first.</p>
          <CodeBlock label="Terminal 1 — repository setup">{track === "rehearsal" ? `gh auth login
git clone https://github.com/giolaq/software-refactory-workshop.git software-refactory-demo
cd software-refactory-demo
git remote rename origin upstream
gh repo create software-refactory-demo --private --source=. --remote=origin --push
./setup_demo.sh --scenario recipe-rebrand
git push origin main --follow-tags` : `gh auth login
gh auth refresh -s project
git clone https://github.com/giolaq/software-refactory-workshop.git software-refactory-demo
cd software-refactory-demo
git remote rename origin upstream
gh repo create software-refactory-demo --private --source=. --remote=origin --push
./setup_demo.sh --scenario recipe-rebrand
git push origin main --follow-tags`}</CodeBlock>

          <div className="activity-card launch-card">
            <span className="activity-label">Do this before using the screenshots</span>
            <h3>Open the Control Center</h3>
            <p>Open another terminal tab in the <code>software-refactory-demo</code> repository. Run:</p>
            <CodeBlock label="Terminal 2 — keep this running">{`./factory/factory control-center`}</CodeBlock>
            <ol>
              <li>Wait for <code>Factory Control Center: http://127.0.0.1:5050</code>.</li>
              <li>Your browser should open automatically. If it does not, open <a href="http://127.0.0.1:5050">127.0.0.1:5050</a> yourself.</li>
              <li>Leave this terminal running for the workshop. Press <code>Ctrl+C</code> only when you want to stop the Control Center.</li>
            </ol>
          </div>

          <WorkshopPaths
            click={<>In the browser that just opened, select <strong>Connect</strong>, choose your agent preset, then select <strong>Run preflight</strong>.</>}
            inspect={<>Confirm the repository, branch, remote, agent roles, QA approval, and parallel-ticket limit.</>}
            continueWhen={<>Preflight reports no blockers and the header shows the correct repository.</>}
          >{`./factory/factory configure --preset claude-workshop
./factory/factory doctor --full`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/control-center-connect.jpg"
            alt="Control Center Connect screen with agent presets, repository details, and preflight button"
            label="Connect"
            caption="Click Connect in the left navigation. Check the repository panel before running preflight."
            width={1440}
            height={900}
          />
          <Callout type="tip" title="Use the Overview as your guide">
            <p><strong>Current phase</strong> explains what is running. <strong>Next checkpoint</strong> opens the next decision. Use <strong>Reset or start again</strong> to repeat a Rehearsal while keeping either the approved plan or only your configuration.</p>
          </Callout>
          <Checkpoint><a href="http://127.0.0.1:5050">127.0.0.1:5050</a> is open, the repository is connected, and preflight reports no blocking errors.</Checkpoint>
        </StepSection>

        <StepSection index={2} id="baseline" title="Inspect the app" goal="Understand the system before changing it." complete={completed.includes("baseline")} onToggle={() => toggleStep("baseline")}>
          <p>The demo begins as Pocket Cinema. Open it and identify its navigation, data flow, responsive layouts, and existing tests.</p>
          <WorkshopPaths
            click={<>Open <strong>Overview</strong> and check that the factory is at <strong>Define the PRD</strong>.</>}
            inspect={<>Confirm no ticket work has started. The Control Center monitors the factory; the app itself runs in a terminal.</>}
            continueWhen={<>Pocket Cinema opens locally and the factory still shows the starting phase.</>}
          >{`.factory/venv/bin/python demo-app/app.py`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/pocket-cinema-before.webp"
            alt="Pocket Cinema application before the workshop change"
            label="Expected baseline"
            caption="A working media application that will become TableStory."
            width={1440}
            height={900}
          />
          <Checkpoint>The app runs, and you can name one behavior that must survive the rebrand.</Checkpoint>
        </StepSection>

        <StepSection index={3} id="prd" title="Read the PRD" goal="Turn a broad request into a testable product outcome." complete={completed.includes("prd")} onToggle={() => toggleStep("prd")}>
          <WorkshopPaths
            click={<>Select <strong>PRD</strong> in the left navigation. Edit the document if needed, then select <strong>Save PRD</strong>.</>}
            inspect={<>Answer the four questions in the right panel: audience, user change, compatibility, and evidence of success.</>}
            continueWhen={<>The PRD is saved and you can explain the outcome without describing implementation.</>}
          >{`sed -n '1,220p' recipe-app-prd.md`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/control-center-prd.jpg"
            alt="Control Center PRD editor with Save PRD and Start Product Review buttons"
            label="PRD"
            caption="Read the outcome in the editor and use the four-question checklist on the right."
            width={1440}
            height={900}
          />
          <Checkpoint>You can explain the change in one sentence without describing implementation.</Checkpoint>
        </StepSection>

        <StepSection index={4} id="plan" title="Review product intent" goal="Approve the problem and desired behavior before technical design begins." complete={completed.includes("plan")} onToggle={() => toggleStep("plan")}>
          <WorkshopPaths
            click={<>In <strong>PRD</strong>, choose {track === "rehearsal" ? "Rehearsal" : "Live"}, select <strong>Start Product Review</strong>, then open <strong>Planning → Product Review</strong>.</>}
            inspect={<>Check the user problem, desired behavior, requirement <code>R4</code>, evidence, and blocking questions. Revise vague output.</>}
            continueWhen={<>The product artifact is specific, testable, and records a human approval.</>}
          >{`./factory/factory plan recipe-app-prd.md${track === "rehearsal" ? " --mock" : ""}
export PLAN_ID=<plan-id-from-output>
./factory/factory review product "$PLAN_ID"
./factory/factory revise "$PLAN_ID" product \\
  --feedback "Clarify the user journey and measurable outcome."${track === "rehearsal" ? " --mock" : ""}
./factory/factory review product "$PLAN_ID"
./factory/factory approve-product "$PLAN_ID"`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/control-center-planning.jpg"
            alt="Control Center Planning screen showing the expert stages and human approval gates"
            label="Planning"
            caption="Click Product Review first. The yellow cards are decisions that require a person."
            width={1440}
            height={900}
          />
          <Checkpoint>The product artifact shows objective <code>R4</code> and a human approval.</Checkpoint>
        </StepSection>

        <StepSection index={5} id="publish" title="Create tickets" goal="Agree on architecture, program design, and vertical slices before publishing work." complete={completed.includes("publish")} onToggle={() => toggleStep("publish")}>
          <WorkshopPaths
            click={<>In <strong>Planning</strong>, select <strong>Run remaining experts</strong>. Open each expert card, approve alignment, then select <strong>Create tickets</strong>.</>}
            inspect={<>Check component contracts, data models, types, call paths, acceptance criteria, dependencies, and delivery waves.</>}
            continueWhen={track === "live" ? <>GitHub Projects contains the approved slices as issues.</> : <>The rehearsal ticket board contains the approved slices.</>}
          >{track === "rehearsal" ? `./factory/factory continue-plan "$PLAN_ID" --mock
./factory/factory review alignment "$PLAN_ID"
./factory/factory approve-rehearsal "$PLAN_ID" --scenario recipe-rebrand
./factory/factory run --mock --scenario recipe-rebrand --dry-run` : `./factory/factory continue-plan "$PLAN_ID"
./factory/factory review alignment "$PLAN_ID"
./factory/factory approve "$PLAN_ID" --new-project-title "TableStory Workshop"`}</WorkshopPaths>
          <p>Four specialists contribute one artifact each:</p>
          <div className="concept-grid compact-concept-grid">
            <article><span>P</span><h3>Product review</h3><p>Problem, users, behavior, and success.</p></article>
            <article><span>A</span><h3>Architecture</h3><p>Components, contracts, data, and constraints.</p></article>
            <article><span>D</span><h3>Program design</h3><p>Types, signatures, layout, and call paths.</p></article>
            <article><span>V</span><h3>Vertical slices</h3><p>Small, ordered tickets with acceptance criteria.</p></article>
          </div>
          <WorkshopMedia
            src="/illustrations/02-four-planning-perspectives.png"
            alt="Four experts align product, architecture, program design, and vertical slices"
            label="Four planning perspectives"
            caption="Alignment happens before parallel implementation begins."
            width={1600}
            height={900}
            illustration
          />
          <Callout type="warning" title="Do not seed normal workshop tickets">
            <p>The planning agents produce the tickets from the PRD. Seeding exists only for fixtures and recovery demos.</p>
          </Callout>
          <Checkpoint>{track === "live" ? "GitHub Projects shows the approved vertical slices as issues." : "The dry run prints the issues that would be created in GitHub."}</Checkpoint>
        </StepSection>

        <StepSection index={6} id="qa" title="Approve tests" goal="Have a QA agent define acceptance evidence before implementation." complete={completed.includes("qa")} onToggle={() => toggleStep("qa")}>
          <WorkshopPaths
            click={<>Open <strong>Tickets</strong>, select <strong>Run one cycle</strong>, open ticket <strong>#1</strong>, then select <strong>Tests</strong>. Return to Summary to approve.</>}
            inspect={<>Read the protected test path and verify that the proposed assertions prove the ticket’s acceptance criteria.</>}
            continueWhen={<>The test proposal is credible and the ticket history records your approval.</>}
          >{`./factory/factory run${track === "rehearsal" ? " --mock --scenario recipe-rebrand" : ""} --review-qa-tests --once
./factory/factory approve-tests ISSUE_NUMBER`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/control-center-ticket-tests.jpg"
            alt="Control Center ticket drawer open on the Tests tab"
            label="Ticket tests"
            caption="Open a QA Review ticket, then click Tests in the detail drawer."
            width={1440}
            height={900}
          />
          <Checkpoint>The ticket contains acceptance tests, and its history records QA approval.</Checkpoint>
        </StepSection>

        <StepSection index={7} id="factory" title="Run the factory" goal="Observe agents implement, verify, and review isolated tickets." complete={completed.includes("factory")} onToggle={() => toggleStep("factory")}>
          <WorkshopPaths
            click={<>Open <strong>Tickets</strong> and select <strong>Run factory</strong>. Open a moving ticket; use Prompt, Live log, Diff, Tests, and History.</>}
            inspect={<>Follow its state, attempt count, dependencies, exact prompt, worktree changes, gate output, and review decisions.</>}
            continueWhen={<>At least one ticket reaches Done and its detail drawer contains the evidence for that state.</>}
          >{`./factory/factory run${track === "rehearsal" ? " --mock --scenario recipe-rebrand" : ""}`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/control-center-tickets.jpg"
            alt="Control Center Tickets board with backlog and QA Review columns"
            label="Ticket board"
            caption="Click a card to inspect its prompt, live log, diff, tests, and history."
            width={1440}
            height={900}
          />
          <WorkshopMedia
            src="/screenshots/control-center-overview.jpg"
            alt="Control Center Overview showing current phase, next checkpoint, progress, and human decisions"
            label="Overview"
            caption="Use Current phase to orient yourself and Next checkpoint to find the next human action."
            width={1440}
            height={900}
          />
          <Callout type="tip" title="Retries are evidence">
            <p>A failed gate should return the ticket to the agent with a clear reason. Do not hide the loop.</p>
          </Callout>
          <Checkpoint>At least one ticket reaches Done, and you can open its log, diff, tests, and review evidence.</Checkpoint>
        </StepSection>

        <StepSection index={8} id="finish" title="Verify the result" goal="Check the integrated product, not only individual tickets." complete={completed.includes("finish")} onToggle={() => toggleStep("finish")}>
          <WorkshopPaths
            click={<>Open <strong>Evidence</strong>. Inspect the checklist, complete the Factory Canvas, then select <strong>Create evidence packet</strong>.</>}
            inspect={<>Confirm product intent, plan approval, test records, required gates, completed tickets, and the integrated user journeys.</>}
            continueWhen={<>Every checklist item is complete and the generated packet explains why the delivery is done.</>}
          >{`.factory/venv/bin/python -m pytest -q demo-app/tests
node --test demo-app/static/tests/*.test.js
.factory/venv/bin/python demo-app/app.py
./factory/factory canvas --output factory-canvas.md
./factory/factory evidence "$PLAN_ID" --canvas factory-canvas.md`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/control-center-evidence.jpg"
            alt="Control Center Evidence screen with completion checklist and evidence packet button"
            label="Evidence"
            caption="Inspect every checklist row before creating the evidence packet."
            width={1440}
            height={900}
          />
          <p>Verify five journeys: browse recipes, search, open details, save a favorite, and use the TV layout. Check desktop and mobile widths.</p>
          <div className="workshop-figure-grid">
            <WorkshopMedia src="/screenshots/tablestory-mobile.webp" alt="TableStory on a mobile viewport" label="Mobile" caption="Touch layout" width={430} height={932} portrait />
            <WorkshopMedia src="/screenshots/tablestory-desktop.webp" alt="TableStory on a desktop viewport" label="Desktop" caption="Primary browsing layout" width={1440} height={900} />
          </div>
          <WorkshopMedia src="/screenshots/tablestory-tv.webp" alt="TableStory television layout" label="TV" caption="Remote-friendly navigation and readable focus states" width={1440} height={900} />
          <WorkshopMedia
            src="/illustrations/03-evidence-controls-merge.png"
            alt="Evidence from tests, review, and product verification controls the merge"
            label="Evidence controls the merge"
            caption="Completion means the integrated behavior is demonstrated, not merely generated."
            width={1600}
            height={900}
            illustration
          />
          <Checkpoint>The app passes its tests, works at three viewport sizes, and the evidence report explains why the change is complete.</Checkpoint>
        </StepSection>

        <section className="completion-panel">
          <div className="completion-ring" style={{ "--progress": `${progress}%` } as CSSProperties}><span>{progress}%</span></div>
          <div><span className="section-kicker">Workshop progress</span><h2>{progress === 100 ? "Factory complete" : "Keep going"}</h2><p>{completed.length} of {steps.length} steps marked complete.</p></div>
          {progress < 100 && <a className="primary-button" href={`#${steps.find((step) => !completed.includes(step.id))?.id ?? "setup"}`}>Next step</a>}
        </section>

        <section id="adapt" className="apply-section">
          <div className="section-heading">
            <span className="section-kicker">After the workshop</span>
            <h2>Use your own agents</h2>
            <p>Map the factory roles to the command-line agents your team already uses.</p>
          </div>
          <h3 className="subsection-title">Pick your next experiment</h3>
          <ol>
            <li>Which repeated engineering task is slow or inconsistent?</li>
            <li>What evidence would make an agent change safe to review?</li>
            <li>Where must a human make the final decision?</li>
          </ol>
          <details className="optional-detail">
            <summary>Configure your own agent</summary>
            <p>Start with a built-in preset, or map each role to a different CLI.</p>
            <CodeBlock>{`./factory/factory configure --preset claude-workshop
# Or: --preset codex-workshop

./factory/factory configure \\
  --planning-agent claude --agent my-agent --qa-agent my-agent \\
  --review-qa-tests --max-parallel 1`}</CodeBlock>
            <p>Add a custom adapter in <code>factory/factory.toml</code>:</p>
            <CodeBlock label="factory/factory.toml">{`[agents]
my-agent = './tools/run-my-agent.sh {prompt}'`}</CodeBlock>
            <p>Keep test roots and quality gates in the same configuration, then run <code>./factory/factory doctor --full</code>.</p>
          </details>
        </section>

        <section id="troubleshooting" className="support-section">
          <div className="section-heading">
            <span className="section-kicker">When something stops</span>
            <h2>Troubleshooting</h2>
            <p>Start with the symptom you see.</p>
          </div>
          <div className="accordion-list">
            <details><summary><code>doctor</code> reports a failure</summary><p>Fix the first failed check, then rerun the same doctor command. Later errors are often consequences.</p></details>
            <details><summary>No Git remotes found</summary><p>Run <code>git remote -v</code> inside the demo repository. Add or correct <code>origin</code>; do not point the factory repository at the demo project.</p></details>
            <details><summary>Claude asks for an OpenAI API key</summary><p>Your selected adapter is still the OpenAI preset. Run <code>./factory/factory configure --preset claude-workshop</code>, confirm Claude is authenticated, then rerun doctor.</p></details>
            <details><summary>A ticket is blocked</summary><p>Open its event history and agent log. Fix the recorded cause, then run <code>./factory/factory retry ISSUE_NUMBER</code>.</p></details>
            <details><summary>The Control Center reports a deadlock</summary><p>One or more dependency chains form a cycle. Edit issue dependencies so at least one ticket can start, then rerun the factory.</p></details>
            <details><summary>Live planning is slow or inconsistent</summary><p>Use the rehearsal path to learn the workflow. Return to live mode after credentials, model access, and the PRD are stable.</p></details>
            <details><summary>A port or worktree is already in use</summary><p>Stop the stale process or inspect active worktrees with <code>git worktree list</code>. Remove only a worktree you have confirmed is disposable.</p></details>
            <details><summary>I want to repeat the workshop</summary><p>Open <strong>Reset or start again</strong> in the local Control Center. Reset ticket execution to keep the approved PRD plan, or type <code>START OVER</code> to return to the beginning. For Live mode, create a fresh repository.</p></details>
          </div>
        </section>

        <section id="reference" className="reference-section">
          <div className="section-heading">
            <span className="section-kicker">Keep nearby</span>
            <h2>Core commands</h2>
            <p>The commands you are most likely to repeat.</p>
          </div>
          <div className="reference-table">
            <div><code>factory control-center</code><span>Open the local operator interface.</span></div>
            <div><code>factory doctor --full</code><span>Check live prerequisites and configuration.</span></div>
            <div><code>factory plan PRD</code><span>Start the four-stage planning workflow.</span></div>
            <div><code>factory review product PLAN_ID</code><span>Read the product artifact before approval.</span></div>
            <div><code>factory approve-product PLAN_ID</code><span>Record the human product decision.</span></div>
            <div><code>factory approve PLAN_ID</code><span>Publish approved slices as GitHub issues.</span></div>
            <div><code>factory run</code><span>Process available tickets with configured agents.</span></div>
            <div><code>factory approve-tests ISSUE</code><span>Allow implementation after reviewing QA tests.</span></div>
            <div><code>factory status</code><span>Summarize the current ticket states.</span></div>
            <div><code>factory retry ISSUE</code><span>Retry a ticket after fixing its blocker.</span></div>
            <div><code>factory canvas --output FILE</code><span>Capture the factory design for evidence export.</span></div>
          </div>
          <div className="next-links">
            <a href="https://github.com/giolaq/software-refactory-workshop/blob/main/factory/WORKSHOP_OUTLINE.md"><span>FACILITATOR</span><b>Workshop outline</b><i>→</i></a>
            <a href="https://github.com/giolaq/software-refactory-workshop/blob/main/factory/CONFIGURATION.md"><span>REFERENCE</span><b>Agent configuration</b><i>→</i></a>
          </div>
        </section>
      </main>

      <aside className="right-rail">
        <div className="rail-card"><span className="rail-label">PATH</span><strong>{track === "live" ? "Live" : "Rehearsal"}</strong><button type="button" onClick={() => document.getElementById("path")?.scrollIntoView({ behavior: "smooth" })}>Change path</button></div>
        <div className="rail-card"><span className="rail-label">PROGRESS</span><strong>{completed.length} of {steps.length}</strong><div className="progress-track"><span style={{ width: `${progress}%` }} /></div></div>
        <div className="rail-help"><span className="rail-help-icon">?</span><strong>Stuck?</strong><p>Read the ticket event history first. It records the reason for every state change.</p><a href="#troubleshooting">Open troubleshooting</a></div>
      </aside>

      <footer>
        <span className="footer-brand"><span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>Software (re)-Factory</span>
        <span>Plan clearly. Isolate work. Require evidence.</span>
      </footer>
    </>
  );
}
