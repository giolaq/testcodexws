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
  assert.match(html, /One PRD\. Two delivery systems\./);
  assert.match(html, /Prepare your development environment/);
  assert.match(html, /Python 3\.11 or later/);
  assert.match(html, /No API key is required/);
  assert.match(html, /configure --preset claude-workshop/);
  assert.match(html, /Tickets come from the PRD/);
  assert.match(html, /factory seed recipe-rebrand/);
  assert.match(html, /Choose your workshop path/);
  assert.match(html, /Prepare a safe workspace/);
  assert.match(html, /Establish the lights-off control/);
  assert.match(html, /Define acceptance evidence before implementation/);
  assert.match(html, /Compare, decide, and adapt/);
  assert.match(html, /Design the factory your delivery risk requires/);
  assert.match(html, /Factory design canvas/);
  assert.match(html, /This fixture is not a benchmark/);
  assert.match(html, /Troubleshooting/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});
