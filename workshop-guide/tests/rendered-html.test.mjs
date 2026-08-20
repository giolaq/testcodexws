import assert from "node:assert/strict";
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

test("server-renders the self-guided workshop", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Software \(re\)-Factory Workshop<\/title>/i);
  assert.match(html, /Turn AI coding into an engineering system/);
  assert.match(html, /What is an AI software factory\?/);
  assert.match(html, /Agents can produce more code than teams can safely absorb/);
  assert.match(html, /Follow one requirement from intent to evidence\./);
  assert.match(html, /Prepare your development environment/);
  assert.match(html, /Python 3\.11 or later/);
  assert.match(html, /No API key is required/);
  assert.match(html, /configure --preset claude-workshop/);
  assert.match(html, /Use the agents your team already trusts/);
  assert.match(html, /my-agent =/);
  assert.match(html, /Any registered adapter/);
  assert.match(html, /Configure project policy/);
  assert.match(html, /test_roots/);
  assert.match(html, /configure --project-number PROJECT_NUMBER/);
  assert.match(html, /Tickets come from the PRD/);
  assert.match(html, /factory approve-rehearsal PLAN_ID/);
  assert.match(html, /factory seed recipe-rebrand/);
  assert.match(html, /Choose your workshop path/);
  assert.match(html, /Instructor-led Live Run/);
  assert.match(html, /Self-paced Rehearsal Run/);
  assert.match(html, /Every attendee creates and owns a separate repository/);
  assert.match(html, /facilitator uses a different repository/i);
  assert.match(html, /review a peer’s repository/i);
  assert.match(html, /Plan[\s\S]*Build[\s\S]*Verify[\s\S]*Review/);
  assert.match(html, /Backlog[\s\S]*Ready[\s\S]*In Progress[\s\S]*QA Review[\s\S]*Verifying[\s\S]*In Review[\s\S]*Done[\s\S]*Blocked/);
  assert.match(html, /Lean Factory Profile/);
  assert.match(html, /Standard Factory Profile/);
  assert.match(html, /Assured Factory Profile/);
  assert.match(html, /Agent Role contract/);
  assert.match(html, /Ownership[\s\S]*Exclusions[\s\S]*Verification responsibility[\s\S]*Handoff Receipt/);
  assert.match(html, /workshop-policy-v1/);
  assert.match(html, /factory revise PLAN_ID product/);
  assert.match(html, /preserve mode=tv/);
  assert.match(html, /R3[\s\S]*Product Review[\s\S]*System Architecture[\s\S]*Program Design[\s\S]*Vertical Slices/);
  assert.match(html, /first deterministic implementation is incomplete/);
  assert.match(html, /factory canvas/);
  assert.match(html, /factory evidence PLAN_ID/);
  assert.match(html, /Evidence Packet/);
  assert.match(html, /Raw prompts, raw logs, environment values, tokens, and credentials are excluded/);
  assert.match(html, /consenting attendee’s repository/);
  assert.match(html, /Live agents have no presentation timeout/);
  assert.match(html, /release-check --rehearsal/);
  assert.match(html, /confirm-disposable-repo/);
  assert.match(html, /uses Claude for planning, independent QA, and implementation/);
  assert.match(html, /Untrusted-code sandboxing/);
  assert.match(html, /workshop-v1\.0\.0/);
  assert.match(html, /Prepare a safe workspace/);
  assert.match(html, /Define acceptance evidence before implementation/);
  assert.match(html, /Verify, decide, and adapt/);
  assert.match(html, /screenshots\/pocket-cinema-before\.webp/);
  assert.match(html, /Before · Pocket Cinema/);
  assert.match(html, /screenshots\/factory-dashboard-qa-review\.webp/);
  assert.match(html, /Reference state · QA Review/);
  assert.match(html, /screenshots\/factory-dashboard-complete\.webp/);
  assert.match(html, /screenshots\/tablestory-desktop\.webp/);
  assert.match(html, /screenshots\/tablestory-mobile\.webp/);
  assert.match(html, /screenshots\/tablestory-tv\.webp/);
  assert.match(html, /After · TableStory/);
  assert.match(html, /illustrations\/01-from-prompt-to-evidence\.png/);
  assert.match(html, /illustrations\/02-four-planning-perspectives\.png/);
  assert.match(html, /illustrations\/03-evidence-controls-merge\.png/);
  assert.match(html, /Ian Xiaohei Illustrations/);
  assert.match(html, /used under the MIT License/);
  assert.match(html, /Design the factory your delivery risk requires/);
  assert.match(html, /Factory design canvas/);
  assert.match(html, /Troubleshooting/);
  assert.doesNotMatch(html, /lights[- ]off|control experiment|run_lights_off|two delivery systems/i);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});
