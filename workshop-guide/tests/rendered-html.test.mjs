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
  assert.match(html, /Build software with controlled AI agents/);
  assert.match(html, /Prepare your development environment/);
  assert.match(html, /Python 3\.11 or later/);
  assert.match(html, /No API key is required/);
  assert.match(html, /Choose your workshop path/);
  assert.match(html, /Set up your workspace/);
  assert.match(html, /Run the lights-off control/);
  assert.match(html, /Review QA tests/);
  assert.match(html, /Compare and verify both results/);
  assert.match(html, /This fixture is not a benchmark/);
  assert.match(html, /Troubleshooting/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});
