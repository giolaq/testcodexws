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
  assert.match(html, /Plan[\s\S]*Build[\s\S]*Verify[\s\S]*Review/);

  assert.match(html, /Prerequisites/);
  assert.match(html, /Python 3\.11/);
  assert.match(html, /Node\.js 20/);
  assert.match(html, /GitHub CLI and one personal workshop repository/);
  assert.match(html, /facilitator uses a different repository/i);
  assert.match(html, /Rehearsal/);
  assert.match(html, /Live/);
  assert.match(html, /factory control-center/);
  assert.match(html, /localhost:5050/);
  assert.match(html, /Control Center/);

  for (const heading of [
    "Set up",
    "Inspect the app",
    "Read the PRD",
    "Review product intent",
    "Create tickets",
    "Approve tests",
    "Run the factory",
    "Verify the result",
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
  assert.match(html, /planning agents produce the tickets from the PRD/i);
  assert.match(html, /Configure your own agent/);
  assert.match(html, /my-agent =/);
  assert.match(html, /Lean[\s\S]*Standard[\s\S]*Assured/);
  assert.match(html, /Troubleshooting/);

  assert.match(html, /screenshots\/pocket-cinema-before\.webp/);
  assert.match(html, /screenshots\/factory-dashboard-qa-review\.webp/);
  assert.match(html, /screenshots\/factory-dashboard-complete\.webp/);
  assert.match(html, /screenshots\/tablestory-desktop\.webp/);
  assert.match(html, /screenshots\/tablestory-mobile\.webp/);
  assert.match(html, /screenshots\/tablestory-tv\.webp/);
  assert.match(html, /illustrations\/01-from-prompt-to-evidence\.png/);
  assert.match(html, /illustrations\/02-four-planning-perspectives\.png/);
  assert.match(html, /illustrations\/03-evidence-controls-merge\.png/);
  assert.match(html, /Ian Xiaohei illustration workflow/);

  assert.doesNotMatch(html, /lights[- ]off|control experiment|run_lights_off|two delivery systems/i);
  assert.doesNotMatch(html, /localhost:8000|python3 -m http\.server 8000/i);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("attendee page stays within its copy budget", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const words = source.trim().split(/\s+/).length;
  assert.ok(words < 4500, `page.tsx contains ${words} words; expected fewer than 4500`);
});
