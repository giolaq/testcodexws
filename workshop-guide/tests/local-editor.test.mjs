import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";
import { applyEdit, buildSnapshot } from "../scripts/local-editor/source-model.mjs";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const pagePath = path.resolve(testDirectory, "..", "app", "page.tsx");

test("the local editor discovers workshop headings and paragraphs", async () => {
  const source = await readFile(pagePath, "utf8");
  const snapshot = buildSnapshot(source);

  assert.ok(snapshot.entries.length > 150);
  assert.ok(snapshot.entries.some((entry) => entry.value === "Turn AI coding into an engineering system"));
  assert.ok(snapshot.entries.some((entry) => entry.section === "prerequisites"));
});

test("custom component titles and body copy can be selected in the preview", async () => {
  const source = await readFile(pagePath, "utf8");
  const snapshot = buildSnapshot(source);
  const title = snapshot.entries.find(
    (entry) => entry.value === "Repository ownership is part of the exercise",
  );
  const body = snapshot.entries.find(
    (entry) => entry.value.startsWith("Every attendee creates and owns a separate repository"),
  );

  assert.ok(title);
  assert.equal(title.kind, "attribute");
  assert.equal(title.tag, "Callout");
  assert.equal(title.previewSelector, "*");
  assert.ok(body);
  assert.equal(body.kind, "text");
  assert.equal(body.tag, "Callout");
  assert.equal(body.section, "prerequisites");
  assert.equal(body.previewSelector, "*");
});

test("a custom component body edit remains valid TSX", async () => {
  const source = await readFile(pagePath, "utf8");
  const snapshot = buildSnapshot(source);
  const entry = snapshot.entries.find(
    (candidate) => candidate.value.startsWith("Every attendee creates and owns a separate repository"),
  );
  assert.ok(entry);

  const replacement = "Each attendee owns a separate workshop repository.";
  const result = applyEdit(source, {
    id: entry.id,
    version: snapshot.version,
    value: replacement,
  });

  assert.match(result.source, new RegExp(replacement));
  assert.doesNotMatch(result.source, /Every attendee creates and owns a separate repository/);
  const parsed = ts.createSourceFile("page.tsx", result.source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  assert.equal(parsed.parseDiagnostics.length, 0);
});

test("a text edit changes only the selected source range and remains valid TSX", async () => {
  const source = await readFile(pagePath, "utf8");
  const snapshot = buildSnapshot(source);
  const entry = snapshot.entries.find(
    (candidate) => candidate.value === "Turn AI coding into an engineering system",
  );
  assert.ok(entry);

  const replacement = "Turn agent coding into an engineering system";
  const result = applyEdit(source, {
    id: entry.id,
    version: snapshot.version,
    value: replacement,
  });

  assert.match(result.source, new RegExp(replacement));
  assert.equal(
    result.source.length - source.length,
    replacement.length - entry.value.length,
  );
  const parsed = ts.createSourceFile("page.tsx", result.source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  assert.equal(parsed.parseDiagnostics.length, 0);
});

test("the local editor refuses to overwrite a newer source version", async () => {
  const source = await readFile(pagePath, "utf8");
  const snapshot = buildSnapshot(source);
  const entry = snapshot.entries[0];

  assert.throws(
    () => applyEdit(`${source}\n`, { id: entry.id, version: snapshot.version, value: entry.value }),
    /changed after the editor loaded/,
  );
});
