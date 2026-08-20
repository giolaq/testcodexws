import { createHash } from "node:crypto";
import ts from "typescript";

const editableTags = new Set([
  "a",
  "b",
  "button",
  "code",
  "h1",
  "h2",
  "h3",
  "h4",
  "li",
  "p",
  "small",
  "span",
  "strong",
]);

const editableAttributes = new Set(["alt", "caption", "label", "title"]);

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function decodeEntities(value) {
  return value
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([\da-f]+);/gi, (_, code) => String.fromCodePoint(Number.parseInt(code, 16)))
    .replace(/&quot;/g, '"')
    .replace(/&apos;|&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

function normalizeText(value) {
  return decodeEntities(value).replace(/\s+/g, " ").trim();
}

function encodeText(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/{/g, "&#123;")
    .replace(/}/g, "&#125;");
}

function encodeAttribute(value) {
  return encodeText(value).replace(/"/g, "&quot;");
}

function tagName(node) {
  if (!node) return "";
  if (ts.isIdentifier(node)) return node.text;
  return node.getText();
}

function isComponentTag(tag) {
  return /^[A-Z]/.test(tag);
}

function stringAttribute(opening, name, sourceFile, source) {
  const attribute = opening.attributes.properties.find(
    (candidate) => ts.isJsxAttribute(candidate) && candidate.name.text === name,
  );
  if (!attribute || !ts.isJsxAttribute(attribute) || !attribute.initializer) return null;
  if (!ts.isStringLiteral(attribute.initializer)) return null;
  const start = attribute.initializer.getStart(sourceFile) + 1;
  const end = attribute.initializer.getEnd() - 1;
  return decodeEntities(source.slice(start, end));
}

function makeId(kind, start, end, raw) {
  return `${kind}:${start}:${end}:${digest(raw).slice(0, 10)}`;
}

function openingElement(node) {
  if (ts.isJsxElement(node)) return node.openingElement;
  if (ts.isJsxSelfClosingElement(node)) return node;
  return null;
}

export function buildSnapshot(source) {
  const sourceFile = ts.createSourceFile(
    "page.tsx",
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const entries = [];

  function visit(node, section = "page") {
    let activeSection = section;
    const opening = openingElement(node);

    if (opening && tagName(opening.tagName) === "section") {
      activeSection = stringAttribute(opening, "id", sourceFile, source) || section;
    }

    if (ts.isJsxText(node)) {
      const parentOpening = ts.isJsxElement(node.parent) ? node.parent.openingElement : null;
      const tag = parentOpening ? tagName(parentOpening.tagName) : "";
      const start = node.pos;
      const end = node.end;
      const raw = source.slice(start, end);
      const value = normalizeText(raw);

      if ((editableTags.has(tag) || isComponentTag(tag)) && value) {
        entries.push({
          id: makeId("text", start, end, raw),
          kind: "text",
          section: activeSection,
          tag,
          previewSelector: editableTags.has(tag) ? tag : "*",
          value,
          start,
          end,
          raw,
        });
      }
    }

    if (ts.isJsxAttribute(node) && editableAttributes.has(node.name.text) && node.initializer) {
      if (ts.isStringLiteral(node.initializer)) {
        const parent = node.parent?.parent;
        const tag = parent && (ts.isJsxOpeningElement(parent) || ts.isJsxSelfClosingElement(parent))
          ? tagName(parent.tagName)
          : "component";
        const start = node.initializer.getStart(sourceFile) + 1;
        const end = node.initializer.getEnd() - 1;
        const raw = source.slice(start, end);
        const value = decodeEntities(raw);

        if (value.trim()) {
          entries.push({
            id: makeId("attribute", start, end, raw),
            kind: "attribute",
            attribute: node.name.text,
            section: activeSection,
            tag,
            previewSelector: isComponentTag(tag) ? "*" : null,
            value,
            start,
            end,
            raw,
          });
        }
      }
    }

    ts.forEachChild(node, (child) => visit(child, activeSection));
  }

  visit(sourceFile);

  const occurrences = new Map();
  const publicEntries = entries.map((entry) => {
    const key = `${entry.section}\u0000${entry.previewSelector}\u0000${entry.value}`;
    const occurrence = occurrences.get(key) || 0;
    occurrences.set(key, occurrence + 1);
    return {
      id: entry.id,
      kind: entry.kind,
      attribute: entry.attribute,
      section: entry.section,
      tag: entry.tag,
      previewSelector: entry.previewSelector,
      value: entry.value,
      occurrence,
    };
  });

  return {
    version: digest(source),
    entries: publicEntries,
    internalEntries: entries,
  };
}

export function applyEdit(source, { id, version, value }) {
  const snapshot = buildSnapshot(source);
  if (snapshot.version !== version) {
    const error = new Error("The page changed after the editor loaded. Reload the content and try again.");
    error.code = "STALE_SOURCE";
    throw error;
  }

  const entry = snapshot.internalEntries.find((candidate) => candidate.id === id);
  if (!entry) {
    const error = new Error("That text could not be found. Reload the editor and try again.");
    error.code = "ENTRY_NOT_FOUND";
    throw error;
  }

  const cleanValue = String(value ?? "").replace(/\r/g, "").trim();
  if (cleanValue.length > 20_000) {
    const error = new Error("Keep each editable block under 20,000 characters.");
    error.code = "VALUE_TOO_LONG";
    throw error;
  }

  let replacement;
  if (entry.kind === "attribute") {
    replacement = encodeAttribute(cleanValue);
  } else {
    const leading = entry.raw.match(/^\s*/)?.[0] || "";
    const trailing = entry.raw.match(/\s*$/)?.[0] || "";
    replacement = `${leading}${encodeText(cleanValue)}${trailing}`;
  }

  const updatedSource = `${source.slice(0, entry.start)}${replacement}${source.slice(entry.end)}`;
  return {
    source: updatedSource,
    version: digest(updatedSource),
    previousValue: entry.value,
    value: cleanValue,
    section: entry.section,
    tag: entry.tag,
    kind: entry.kind,
    attribute: entry.attribute,
    occurrence: entry.occurrence || 0,
  };
}
