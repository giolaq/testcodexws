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
  { id: "finish", label: "Verify and monitor", time: "15 min" },
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
  whyStopped,
  inspect,
  continueWhen,
  children,
}: {
  click: ReactNode;
  whyStopped?: ReactNode;
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
          <div><dt>What is happening</dt><dd>{click}</dd></div>
          <div><dt>Why it stopped</dt><dd>{whyStopped ?? <>The factory reached a human decision or a failed control. <strong>Current phase</strong> names the owner and recovery.</>}</dd></div>
          <div><dt>What evidence to inspect</dt><dd>{inspect}</dd></div>
          <div><dt>What you decide</dt><dd>{continueWhen}</dd></div>
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
          <a href="#capability-ladder" onClick={() => setMenuOpen(false)}>Why the controls exist</a>
          <a href="#supervisor-role" onClick={() => setMenuOpen(false)}>Supervisor role</a>
          <a href="#code-review-role" onClick={() => setMenuOpen(false)}>Code review role</a>
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
            <div className="map-row"><span className="map-node node-purple">Supervisor</span><i>→</i><span className="map-node node-blue">Agents</span><i>→</i><span className="map-node node-human">Review + merge</span></div>
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
            <article><span>02</span><h3>Build</h3><p>Supervise each safe ticket wave in isolated Git worktrees.</p></article>
            <article><span>03</span><h3>Verify</h3><p>Let QA define tests before implementation begins.</p></article>
            <article><span>04</span><h3>Review</h3><p>Have a separate agent inspect the candidate diff, then leave merge judgment to a person.</p></article>
          </div>
        </section>

        <section id="capability-ladder" className="supervisor-section">
          <div className="section-heading">
            <span className="section-kicker">Build capability in response to failure</span>
            <h2>Start with one responsible delivery loop</h2>
            <p>Begin with a clear issue, one coding agent, one real test, one pull request, and a human merge. Add factory controls only when the work exposes a specific failure mode. Human attention is the limiting resource, so the factory stops creating review work when that queue is full.</p>
          </div>
          <div className="supervisor-role-flow" aria-label="Capability ladder">
            <article><span>Minimum loop</span><h3>Issue → code → test → PR</h3><p>A person owns intent and the exact revision that ships.</p></article>
            <article><span>Failure modes</span><h3>Ambiguity, collisions, weak proof</h3><p>Parallel work also creates review queues, lost decisions, and stale evidence.</p></article>
            <article><span>Add controls</span><h3>Plan, claim, verify, record</h3><p>Use only the planning depth, isolation, gates, review, and monitoring the risk requires.</p></article>
          </div>
          <Callout type="tip" title="More agents are a cost">
            <p>Agent count and check count are not quality measures. The useful result is a bounded change whose ownership, evidence, and human decision are easy to inspect.</p>
          </Callout>
        </section>

        <section id="supervisor-role" className="supervisor-section">
          <div className="section-heading">
            <span className="section-kicker">Multi-agent coordination</span>
            <h2>The supervisor coordinates work. It does not own delivery.</h2>
            <p>A ticket agent sees one assignment. The Agent Supervisor sees the delivery state between work waves and recommends what should happen next.</p>
          </div>
          <details className="optional-detail">
            <summary>Inspect the Supervisor contract</summary>
            <div className="supervisor-role-flow" aria-label="Supervisor coordination flow">
              <article><span>1 · Report</span><h3>Workers report</h3><p>Agents return a Handoff Receipt with checks, artifacts, and risks.</p></article>
              <article><span>2 · Coordinate</span><h3>Supervisor proposes</h3><p>It reads dependencies, capacity, and receipts, then proposes a safe wave or block.</p></article>
              <article><span>3 · Enforce</span><h3>Orchestrator decides</h3><p>It validates commands, starts worktrees, and owns ticket state.</p></article>
            </div>
            <div className="supervisor-boundaries">
              <article>
                <span className="boundary-label">The supervisor can</span>
                <ul>
                  <li>Select dependency-ready work.</li>
                  <li>Reduce concurrency and focus instructions.</li>
                  <li>Block on recorded risk.</li>
                  <li>Recommend an approved revision for merge.</li>
                </ul>
              </article>
              <article>
                <span className="boundary-label">The supervisor cannot</span>
                <ul>
                  <li>Edit code or protected tests.</li>
                  <li>Change scope or dependencies.</li>
                  <li>Waive gates, approve code, or merge.</li>
                  <li>Move tickets outside the orchestrator.</li>
                </ul>
              </article>
            </div>
            <Callout title="Why use Handoff Receipts?">
              <p>Receipts make worker results, Supervisor recommendations, and orchestrator decisions inspectable.</p>
            </Callout>
          </details>
        </section>

        <section id="code-review-role" className="supervisor-section">
          <div className="section-heading">
            <span className="section-kicker">Independent code review</span>
            <h2>The Code Review Agent closes the feedback loop.</h2>
            <p>After tests and required gates pass, the factory opens or updates a pull request. A separate read-only agent reviews that exact candidate revision.</p>
          </div>
          <details className="optional-detail">
            <summary>Inspect the review and rework loop</summary>
            <div className="supervisor-role-flow" aria-label="Code review flow">
              <article><span>1 · Inspect</span><h3>Review the diff</h3><p>The reviewer checks the approved Ticket against the exact candidate.</p></article>
              <article><span>2 · Decide</span><h3>Approve or comment</h3><p>Actionable comments name a file, severity, and explanation.</p></article>
              <article><span>3 · Close</span><h3>Fix and recheck</h3><p>Comments return to implementation. Gates and review rerun before a person can merge.</p></article>
            </div>
            <Callout type="note" title="Three roles, separate authority">
              <p>The Code Review Agent can approve or request changes. The Supervisor can recommend that exact commit. Only the human merge action ships it.</p>
            </Callout>
            <Callout type="warning" title="GitHub approval needs a separate identity">
              <p>With one workshop login, review is published as a labelled PR comment. For formal approval, use a second account through <code>FACTORY_REVIEW_GH_TOKEN</code>. Never commit it.</p>
            </Callout>
          </details>
        </section>

        <section id="project-contract" className="supervisor-section">
          <div className="section-heading">
            <span className="section-kicker">Use it beyond the exercise</span>
            <h2>Any PRD, one explicit repository contract.</h2>
            <p>The PRD defines what should change. <code>factory.project.toml</code> defines how this repository is built and verified. The human-owned <code>factory.charter.toml</code> defines authority, protected paths, limits, and stop conditions. Agents receive all three.</p>
          </div>
          <details className="optional-detail">
            <summary>See how a generic repository is connected</summary>
            <div className="supervisor-role-flow" aria-label="Generic project setup flow">
              <article><span>1 · Detect</span><h3>Initialize</h3><p><code>factory init</code> detects roots, tools, and gates.</p></article>
              <article><span>2 · Review</span><h3>Approve governance</h3><p>A developer corrects the contract and approves the Charter hash.</p></article>
              <article><span>3 · Run</span><h3>Use Live agents</h3><p>Paste any PRD and publish approved slices to GitHub Projects.</p></article>
            </div>
            <Callout type="note" title="Why Rehearsal is different">
              <p>Deterministic agents implement only TableStory. Use Live mode for an arbitrary PRD.</p>
            </Callout>
          </details>
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
                <li>A local Git repository for the Rehearsal path</li>
              </ul>
            </article>
            <article>
              <span className="requirement-label">Live path</span>
              <h3>Accounts and access</h3>
              <ul>
                <li>GitHub CLI with the <code>project</code> scope</li>
                <li>One personal GitHub workshop repository</li>
                <li>Permission to create issues, branches, and Projects</li>
                <li>An authenticated Claude, Codex, Cursor, or custom agent CLI</li>
                <li>Network access to GitHub and your model provider</li>
                <li>Optional: a second reviewer identity for formal GitHub approval</li>
              </ul>
            </article>
          </div>
          <CodeBlock label="Check versions">{`python3 --version
node --version
git --version
${track === "live" ? "gh --version" : ""}`}</CodeBlock>
          <Callout type="warning" title="Use your own repository">
            <p>Every Live attendee creates a personal GitHub repository. The facilitator uses a different repository on screen. Rehearsal stays local and needs no GitHub or model credentials.</p>
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
          <p>{track === "live" ? "Create a personal GitHub repository from the workshop template, then clone it." : "Clone the workshop into a disposable local repository. Deterministic agents do not write to GitHub or call a model provider."}</p>
          <CodeBlock label="Terminal 1 — repository setup">{track === "rehearsal" ? `git clone https://github.com/giolaq/software-refactory-workshop.git software-refactory-rehearsal
cd software-refactory-rehearsal
./setup_demo.sh --scenario recipe-rebrand
git remote remove origin
git add .
git commit -m "chore: start workshop rehearsal"` : `gh auth login
gh auth refresh -s project
gh repo create YOUR-REPOSITORY --private \
  --template giolaq/software-refactory-workshop --clone
cd YOUR-REPOSITORY
./setup_demo.sh --scenario recipe-rebrand
git push origin main --follow-tags`}</CodeBlock>
          <Callout type="tip" title="Already created the repository?">
            <p>Clone it if it already contains the workshop template. Otherwise clone the workshop locally and paste your repository URL in Connect; saving Live configuration will set that repository as <code>origin</code>. Push <code>main</code> before preflight.</p>
          </Callout>
          {track === "live" ? <Callout type="note" title="Using an existing project instead?">
            <p>Keep the factory checkout separate. Run the commands below from it, review the generated contract, then continue in the Control Center. The guided steps that mention Pocket Cinema apply only to the workshop repository.</p>
            <CodeBlock label="Target another Git checkout">{`./factory/factory init --repo /path/to/your-project
# Review factory.project.toml and factory.charter.toml
./factory/factory approve-charter --repo /path/to/your-project --yes
git -C /path/to/your-project add factory.project.toml factory.charter.toml .gitignore
git -C /path/to/your-project commit -m "chore: configure software factory"
git -C /path/to/your-project push origin HEAD
./factory/factory prepare --repo /path/to/your-project
./factory/factory control-center --repo /path/to/your-project`}</CodeBlock>
          </Callout> : null}

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
            click={<>Select <strong>Connect</strong>. Create the Project Contract and Charter if needed. Review both. Approve the exact Charter, then choose <strong>{track === "live" ? "Live" : "Rehearsal"}</strong>{track === "live" ? <>, paste your repository URL, choose an agent preset, and save</> : null}. Select <strong>Run preflight</strong>.</>}
            whyStopped={<>Planning stays locked until the repository contract exists and a person approves the exact Charter policy.</>}
            inspect={<>Confirm source roots, test roots, gate levels, protected paths, consequence tier, human merge authority, and—on Live—the GitHub target and agents.</>}
            continueWhen={<>The Charter says <strong>Approved</strong>, preflight reports no blockers, and the header names the correct repository.</>}
          >{`${track === "live" ? `./factory/factory configure --preset claude-workshop \\\n  --github-repository https://github.com/YOUR-NAME/YOUR-REPOSITORY
` : ""}./factory/factory approve-charter --yes
./factory/factory doctor${track === "live" ? " --full" : ""}`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/control-center-connect.jpg"
            alt="Control Center Connect screen with agent presets, repository details, and preflight button"
            label="Connect"
            caption="Click Connect. In Live mode, paste the repository URL, save it, and confirm that the GitHub target says connected before preflight."
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
            click={<>In <strong>Planning</strong>, select <strong>Run remaining experts</strong>. Open each expert card. If an expert blocks, answer every question in its card and select <strong>Submit decisions and continue</strong>. Approve alignment, then select <strong>Create tickets</strong>.</>}
            inspect={<>Check component contracts, data models, types, call paths, acceptance criteria, dependencies, and delivery waves. A blocked expert must show the decisions it needs; you do not edit its JSON.</>}
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
            whyStopped={<>Implementation cannot start until the focused command has failed for the missing behavior and a person accepts the QA-owned tests.</>}
            inspect={<>Read the protected test path, focused command, command hash, and <strong>RED PROVED</strong> result. Collection errors, timeouts, skipped tests, and unrelated failures are not valid red evidence.</>}
            continueWhen={<>The test detects the missing behavior, the evidence says <strong>RED PROVED</strong>, and you approve the proposal.</>}
          >{`./factory/factory run${track === "rehearsal" ? " --mock --scenario recipe-rebrand" : ""} --review-qa-tests --once
./factory/factory approve-tests ISSUE_NUMBER`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/control-center-ticket-tests.jpg"
            alt="Control Center ticket drawer open on the Tests tab"
            label="Ticket tests"
            caption="Open a QA Review ticket, click Tests, and require RED PROVED before approval. The same focused command must later show GREEN PROVED."
            width={1440}
            height={900}
          />
          <Checkpoint>The ticket records the protected test, identical focused command, RED PROVED result, and human QA approval.</Checkpoint>
        </StepSection>

        <StepSection index={7} id="factory" title="Run the factory" goal="Observe a supervisor coordinate agents that implement, verify, and review isolated tickets." complete={completed.includes("factory")} onToggle={() => toggleStep("factory")}>
          <WorkshopPaths
            click={track === "live" ? <>Keep your <strong>GitHub Project</strong> open. In the Control Center, open <strong>Tickets</strong>, select <strong>Run factory</strong>, then open <strong>Supervisor</strong>.</> : <>Open <strong>Tickets</strong>, select <strong>Run factory</strong>, then open <strong>Supervisor</strong>.</>}
            whyStopped={<>The scheduler stops for full human-review capacity, an owned remote claim, failed causal proof, a gate failure, review comments, or the final human merge decision. The top <strong>NEEDS YOU</strong> card names the reason.</>}
            inspect={track === "live" ? <>Use GitHub Projects for shared state. In Supervisor, follow worker Handoff Receipts into a dispatch instruction. Open the Ticket for its prompt, log, diff, tests, and gates. When verification passes, open <strong>Code review</strong>, compare the decision with the GitHub review or labelled Factory comment, then inspect the human merge gate.</> : <>Follow worker Handoff Receipts into a dispatch instruction. Open the selected Ticket and compare its instruction with its prompt, logs, gates, Code Review Agent decision, Supervisor recommendation, and human merge gate.</>}
            continueWhen={<>The reviewer approves the exact PR head. You inspect the evidence and select <strong>Merge exact revision</strong>; only then does the Ticket reach Done.</>}
          >{track === "live" ? `gh project view <project-number> --owner "@me" --web
./factory/factory run` : `./factory/factory run --mock --scenario recipe-rebrand`}</WorkshopPaths>
          <WorkshopMedia
            src="/screenshots/control-center-tickets.jpg"
            alt="Control Center Tickets board with backlog and QA Review columns"
            label="Ticket board"
            caption="Click a card, then use Code review to inspect comments, approval, publication mode, and the exact candidate commit."
            width={1440}
            height={900}
          />
          {track === "live" && <WorkshopMedia
            src="/screenshots/github-project-board.jpg"
            alt="Illustrated GitHub Project board showing factory Tickets in lifecycle columns"
            label="Illustrated GitHub Project checkpoint"
            caption="Open Projects from your repository and select the workshop board. Use it for shared state; GitHub's exact layout may vary."
            width={1440}
            height={900}
          />}
          <WorkshopMedia
            src="/screenshots/control-center-overview.jpg"
            alt="Control Center Overview showing current phase, next checkpoint, progress, and human decisions"
            label="Overview"
            caption="Use Current phase to orient yourself and Next checkpoint to find the next human action."
            width={1440}
            height={900}
          />
          <div className="activity-card">
            <span className="activity-label">Coordination checkpoint</span>
            <h3>Trace one supervised handoff</h3>
            <ol>
              <li>Read the latest worker report under <strong>Supervisor</strong>.</li>
              <li>Find the matching dispatch, block, or deferred Ticket.</li>
              <li>Open that Ticket’s <strong>Supervisor</strong> tab and read its instruction.</li>
              <li>After the worker finishes, find its new Handoff Receipt in the next supervisor decision.</li>
            </ol>
            <p>The Agent Supervisor recommends coordination. The orchestrator validates commands and remains the only lifecycle authority.</p>
          </div>
          <WorkshopMedia
            src="/screenshots/control-center-human-merge.jpg"
            alt="Control Center Ticket summary showing an exact-revision human merge action"
            label="Human merge gate"
            caption="Check that the approved head matches the pull request head, then click Merge exact revision. Standard and Assured never merge automatically."
            width={1440}
            height={900}
          />
          <div className="activity-card">
            <span className="activity-label">Review checkpoint</span>
            <h3>Trace one candidate diff</h3>
            <ol>
              <li>Open a verified Ticket and select <strong>Code review</strong>.</li>
              <li>Confirm the report names the candidate commit and only changed paths.</li>
              <li>If it says REQUEST_CHANGES, watch every comment return to implementation as retry context.</li>
              <li>After APPROVE, confirm the Supervisor recommendation names the same commit, then make the human merge decision.</li>
            </ol>
          </div>
          <Callout type="tip" title="Retries are evidence">
            <p>A failed gate should return the ticket to the agent with a clear reason. Do not hide the loop.</p>
          </Callout>
          {track === "live" && <Callout type="tip" title="Two views, one run">
            <p>GitHub Projects is the shared work-management view. The local Control Center is the engine room for prompts, worktrees, tests, logs, and verification evidence.</p>
          </Callout>}
          <Checkpoint>At least one Ticket reaches Done, and you can trace dispatch → worker evidence → review feedback → repair → approval → Supervisor recommendation → human merge.</Checkpoint>
        </StepSection>

        <StepSection index={8} id="finish" title="Verify and monitor" goal="Check the integrated product, preserve evidence, and inspect what needs attention next." complete={completed.includes("finish")} onToggle={() => toggleStep("finish")}>
          <WorkshopPaths
            click={<>Open <strong>Evidence</strong>, complete the Factory Canvas, and create the packet. Then open <strong>Monitor</strong> and select <strong>Preview findings</strong>.</>}
            whyStopped={<>Evidence waits for completed Tickets and a complete Canvas. Monitor reports health separately and never repairs code in the same run.</>}
            inspect={<>Confirm product intent, approvals, RED/GREEN proof, gates, exact-revision human merge, stage time, verification overhead, human wait, and any Monitor findings or limitations.</>}
            continueWhen={<>The packet explains why delivery is done and the read-only Monitor report has a named owner for every follow-up.</>}
          >{`.factory/venv/bin/python -m pytest -q demo-app/tests
node --test demo-app/static/tests/*.test.js
.factory/venv/bin/python demo-app/app.py
./factory/factory canvas --output factory-canvas.md
./factory/factory evidence "$PLAN_ID" --canvas factory-canvas.md
./factory/factory monitor`}</WorkshopPaths>
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
          <Checkpoint>The app passes its tests, works at three viewport sizes, the evidence packet explains the merge, and Monitor proposes no hidden repair.</Checkpoint>
        </StepSection>

        <section className="completion-panel">
          <div className="completion-ring" style={{ "--progress": `${progress}%` } as CSSProperties}><span>{progress}%</span></div>
          <div><span className="section-kicker">Workshop progress</span><h2>{progress === 100 ? "Factory complete" : "Keep going"}</h2><p>{completed.length} of {steps.length} steps marked complete.</p></div>
          {progress < 100 && <a className="primary-button" href={`#${steps.find((step) => !completed.includes(step.id))?.id ?? "setup"}`}>Next step</a>}
        </section>

        <section className="supervisor-section" id="autonomous-demo">
          <div className="section-heading"><span className="section-kicker">Optional contrast · outside the 100-minute core</span><h2>Autonomous Demo delegates the final merge</h2><p>Use this only to demonstrate the accountability tradeoff. It preserves exact-head checks, but the operator explicitly delegates merge execution to the Supervisor recommendation and orchestrator.</p></div>
          <Callout type="warning" title="Not the normal shipping path">
            <p>Standard and Assured end at a human exact-revision merge. Autonomous Demo requires a visible opt-in every time the run starts; it is not a production default.</p>
          </Callout>
          <CodeBlock>{`./factory/factory configure --profile autonomous-demo
./factory/factory run --allow-autonomous-merge`}</CodeBlock>
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
          <Callout title="Complete the Factory Canvas">
            <p>Name the consequence tier, merge authority, human review capacity, load-bearing paths, gate budget, durable remote record, and monitoring owner. These choices determine which controls your use case actually needs.</p>
          </Callout>
          <details className="optional-detail">
            <summary>Add architecture and design approval gates</summary>
            <p>Product Review and final alignment always require a person. For higher-consequence work, add <code>system_architecture</code> or <code>program_design</code> to <code>policy.planning_approvals</code> in the Factory Charter. Declared load-bearing paths can also select these gates automatically. The Control Center pauses and binds each approval to the exact artifact hash.</p>
            <CodeBlock>{`./factory/factory review architecture PLAN_ID
./factory/factory approve-stage architecture PLAN_ID
./factory/factory continue-plan PLAN_ID`}</CodeBlock>
          </details>
          <details className="optional-detail">
            <summary>Configure your own agent</summary>
            <p>Start with a built-in preset, or map each role to a different CLI.</p>
            <CodeBlock>{`./factory/factory configure --preset claude-workshop
# Or: --preset codex-workshop

./factory/factory configure \\
  --planning-agent claude --supervisor-agent my-agent \\
  --agent my-agent --qa-agent my-agent --review-agent my-agent \\
  --review-qa-tests --max-parallel 1`}</CodeBlock>
            <p>Add a custom adapter in <code>factory/factory.toml</code>:</p>
            <CodeBlock label="factory/factory.toml">{`[agents]
my-agent = './tools/run-my-agent.sh {prompt}'

[agent_capabilities.my-agent]
execution_environment = "local"
filesystem_mode = "workspace-write"
allowed_working_roots = ["worktree"]
network_expectation = "provider-only"
environment_allowlist = ["PATH", "HOME", "MY_AGENT_HOME"]
credential_names = []
read_only_template = './tools/run-my-agent.sh --read-only {prompt}'

[supervisor]
agent = "my-agent"

[review]
agent = "my-agent"`}</CodeBlock>
            <p>Declare only the environment names the adapter needs. Unsupported read-only, network, container, or hosted-runner controls appear as limitations; Git worktrees are not security sandboxes. The Supervisor returns structured dispatch and revision-bound merge recommendations. The reviewer must leave the worktree unchanged. Then run <code>./factory/factory doctor --full</code>.</p>
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
            <details><summary>Repository is not connected</summary><p>Open <strong>Connect</strong>, choose <strong>Live</strong>, paste the repository URL, and save. The factory verifies access and configures <code>origin</code>. Push <code>main</code>, then rerun preflight.</p></details>
            <details><summary>Claude asks for an OpenAI API key</summary><p>Your selected adapter is still the OpenAI preset. Run <code>./factory/factory configure --preset claude-workshop</code>, confirm Claude is authenticated, then rerun doctor.</p></details>
            <details><summary>A ticket is blocked</summary><p>Open its event history and agent log. Fix the recorded cause, then run <code>./factory/factory retry ISSUE_NUMBER</code>.</p></details>
            <details><summary>Retry blocked expert repeats the same error</summary><p>Open the failed expert&apos;s recovery card. For validation, select <strong>Apply correction and continue</strong>; the factory sends the rejected artifact and exact validator message to the expert. For a session or rate limit, select <strong>Fix with Codex</strong> (or another configured adapter). After the same process failure occurs twice, the Control Center disables same-agent retry and keeps the completed upstream artifacts. If the PRD, Project Contract, or Factory Charter changed, select <strong>Restart planning safely</strong>.</p></details>
            <details><summary>NEEDS YOU says dispatch is paused</summary><p>The human queue reached its Charter limit. Open the oldest linked decision. Approve, reject, answer, or merge it; dispatch resumes when the queue falls below the limit.</p></details>
            <details><summary>A remote claim belongs to an abandoned run</summary><p>Confirm the owner is no longer running. Open the blocked Ticket and select <strong>Release abandoned claim</strong>. Local reset never releases a remote claim.</p></details>
            <details><summary>The Control Center reports a deadlock</summary><p>One or more dependency chains form a cycle. Edit issue dependencies so at least one ticket can start, then rerun the factory.</p></details>
            <details><summary>Live planning is slow or inconsistent</summary><p>Use the rehearsal path to learn the workflow. Return to live mode after credentials, model access, and the PRD are stable.</p></details>
            <details><summary>A port or worktree is already in use</summary><p>Stop the stale process or inspect active worktrees with <code>git worktree list</code>. Remove only a worktree you have confirmed is disposable.</p></details>
            <details><summary>I want to repeat the workshop</summary><p>Open <strong>Reset or start again</strong>. Reset ticket execution to keep the approved PRD plan, or type <code>START OVER</code> to clear local planning history. In Live mode, both actions keep the selected mode and preserve tracked source plus every GitHub artifact. Use a fresh repository when you need an empty Live board.</p></details>
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
            <div><code>factory configure --supervisor-agent NAME</code><span>Select the adapter that coordinates Standard and Assured dispatch.</span></div>
            <div><code>factory configure --review-agent NAME</code><span>Select the read-only adapter that reviews candidate pull-request diffs.</span></div>
            <div><code>factory approve-tests ISSUE</code><span>Allow implementation after reviewing Acceptance Tests.</span></div>
            <div><code>factory merge ISSUE</code><span>Perform the human exact-revision merge for Standard and Assured.</span></div>
            <div><code>factory status</code><span>Summarize the current ticket states.</span></div>
            <div><code>factory retry ISSUE</code><span>Retry a ticket after fixing its blocker.</span></div>
            <div><code>factory release-claim ISSUE</code><span>Release a confirmed abandoned remote claim explicitly.</span></div>
            <div><code>factory monitor</code><span>Preview read-only post-delivery health findings.</span></div>
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
        <span>Plan clearly. Isolate work. Require evidence. · workshop-v1.1.0</span>
      </footer>
    </>
  );
}
