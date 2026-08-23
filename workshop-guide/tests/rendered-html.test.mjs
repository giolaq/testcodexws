import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the concise self-guided workshop", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Software \(re\)-Factory Workshop<\/title>/i);
  assert.match(html, /Turn a PRD into verified code/);
  assert.match(html, /A factory is the workflow around the agents/);
  assert.match(html, /Start with one responsible delivery loop/);
  assert.match(html, /Human attention is the limiting resource/);
  assert.match(html, /Ambiguity, collisions, weak proof/);
  assert.match(html, /More agents are a cost/);
  assert.match(html, /Plan[\s\S]*Build[\s\S]*Verify[\s\S]*Review/);
  assert.match(html, /Agent Supervisor recommends coordination/);
  assert.match(html, /Code Review Agent closes the feedback loop/);
  assert.match(html, /Code Review Agent can approve or request changes/);
  assert.match(html, /review feedback.*repair.*approval.*Supervisor recommendation.*human merge/);
  assert.match(html, /GitHub approval needs a separate identity/);
  assert.match(html, /worker Handoff Receipts/i);
  assert.match(html, /only lifecycle authority/i);
  assert.match(html, /The supervisor coordinates work\. It does not own delivery\./);
  assert.match(html, /The supervisor can/);
  assert.match(html, /The supervisor cannot/);
  assert.match(html, /Why use Handoff Receipts\?/);
  assert.match(html, /Any PRD, one explicit repository contract/);
  assert.match(html, /factory\.project\.toml/);
  assert.match(html, /Use Live mode for an arbitrary PRD/i);

  assert.match(html, /Prerequisites/);
  assert.match(html, /Python 3\.11/);
  assert.match(html, /Node\.js 20/);
  assert.match(html, /A local Git repository for the Rehearsal path/);
  assert.match(html, /One personal GitHub workshop repository/);
  assert.match(html, /facilitator uses a different repository/i);
  assert.match(html, /Rehearsal/);
  assert.match(html, /Live/);
  assert.match(html, /factory control-center/);
  assert.match(html, /Open the Control Center/);
  assert.match(html, /Project Contract/);
  assert.match(html, /Terminal 2 — keep this running/);
  assert.match(html, /Factory Control Center: http:\/\/127\.0\.0\.1:5050/);
  assert.match(html, /browser should open automatically/i);
  assert.match(html, /Ctrl\+C/);
  assert.match(html, /Control Center/);
  assert.match(html, /Control Center path/);
  assert.match(html, /CLI path/);
  assert.match(html, /What is happening/);
  assert.match(html, /Why it stopped/);
  assert.match(html, /What evidence to inspect/);
  assert.match(html, /What you decide/);

  for (const heading of [
    "Set up",
    "Inspect the app",
    "Read the PRD",
    "Review product intent",
    "Create tickets",
    "Approve tests",
    "Run the factory",
    "Verify and monitor",
  ]) {
    assert.match(html, new RegExp(heading));
  }

  assert.match(html, /factory doctor --full/);
  assert.match(html, /factory plan recipe-app-prd\.md/);
  assert.match(html, /factory approve-product/);
  assert.match(html, /factory approve-rehearsal/);
  assert.match(html, /factory run --mock --scenario recipe-rebrand --review-qa-tests --once/);
  assert.match(html, /factory approve-tests ISSUE_NUMBER/);
  assert.match(html, /factory evidence/);
  assert.match(html, /RED PROVED/);
  assert.match(html, /GREEN PROVED/);
  assert.match(html, /NEEDS YOU/);
  assert.match(html, /remote claim/);
  assert.match(html, /Merge exact revision/);
  assert.match(html, /Autonomous Demo delegates the final merge/);
  assert.match(html, /Add architecture and design approval gates/);
  assert.match(html, /Declared load-bearing paths can also select these gates automatically/);
  assert.match(html, /factory approve-stage architecture PLAN_ID/);
  assert.match(html, /Not the normal shipping path/);
  assert.match(html, /factory monitor/);
  assert.match(html, /Monitor reports health separately and never repairs code/);
  assert.match(html, /planning agents produce the tickets from the PRD/i);
  assert.match(html, /Configure your own agent/);
  assert.match(html, /my-agent =/);
  assert.match(html, /Use your own agents/);
  assert.match(html, /--supervisor-agent my-agent/);
  assert.match(html, /Troubleshooting/);

  assert.match(html, /screenshots\/pocket-cinema-before\.webp/);
  assert.match(html, /screenshots\/control-center-connect\.jpg/);
  assert.match(html, /screenshots\/control-center-prd\.jpg/);
  assert.match(html, /screenshots\/control-center-planning\.jpg/);
  assert.match(html, /screenshots\/control-center-tickets\.jpg/);
  assert.match(html, /screenshots\/control-center-ticket-tests\.jpg/);
  assert.match(html, /screenshots\/control-center-overview\.jpg/);
  assert.match(html, /screenshots\/control-center-human-merge\.jpg/);
  assert.match(html, /screenshots\/control-center-evidence\.jpg/);
  assert.match(html, /screenshots\/tablestory-desktop\.webp/);
  assert.match(html, /screenshots\/tablestory-mobile\.webp/);
  assert.match(html, /screenshots\/tablestory-tv\.webp/);
  assert.match(html, /illustrations\/01-from-prompt-to-evidence\.png/);
  assert.match(html, /illustrations\/02-four-planning-perspectives\.png/);
  assert.match(html, /illustrations\/03-evidence-controls-merge\.png/);
  assert.match(html, /Ian Xiaohei illustration workflow/);

  assert.doesNotMatch(html, /lights[- ]off|control experiment|run_lights_off|two delivery systems/i);
  assert.doesNotMatch(html, /Choose the smallest useful factory|Small internal tools|Regulated systems/i);
  assert.doesNotMatch(html, /localhost:8000|python3 -m http\.server 8000/i);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("attendee page stays within its copy budget", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const response = await render();
  const html = await response.text();
  const initiallyVisibleHtml = html.replace(
    /<details\b(?![^>]*\bopen\b)[^>]*>([\s\S]*?)<\/details>/gi,
    (_, content) => content.match(/<summary\b[^>]*>[\s\S]*?<\/summary>/i)?.[0] ?? "",
  );
  const visible = initiallyVisibleHtml
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&(?:[a-z]+|#\d+);/gi, " ");
  const words = visible.trim().split(/\s+/).filter(Boolean).length;
  assert.ok(words < 3200, `attendee page renders ${words} visible words; expected fewer than 3200`);
  assert.match(source, /doctor\$\{track === "live" \? " --full" : ""\}/);
  assert.match(source, /gh project view <project-number>/);
  assert.match(source, /screenshots\/github-project-board\.jpg/);
  assert.match(source, /agent_capabilities\.my-agent/);
});

test("server-rendered workshop has accessible document and image structure", async () => {
  const response = await render();
  const html = await response.text();
  assert.match(html, /<html[^>]+lang="en"/i);
  assert.match(html, /<main\b/i);
  assert.match(html, /<nav\b[^>]*aria-label=/i);
  const headings = html.match(/<h1\b/g) ?? [];
  assert.equal(headings.length, 1, "the attendee page should expose one primary heading");
  const images = html.match(/<img\b[^>]*>/gi) ?? [];
  assert.ok(images.length > 0, "the attendee page should render its instructional images");
  for (const tag of images) {
    assert.match(tag, /\balt="[^"]+"/i, `instructional image is missing useful alt text: ${tag}`);
  }
});
