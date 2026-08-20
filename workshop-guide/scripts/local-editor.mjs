#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile, rename, writeFile } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { applyEdit, buildSnapshot } from "./local-editor/source-model.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectDirectory = path.resolve(scriptDirectory, "..");
const assetDirectory = path.join(scriptDirectory, "local-editor");
const sourcePath = path.join(projectDirectory, "app", "page.tsx");
const editorPort = Number(process.env.WORKSHOP_EDITOR_PORT || 3001);
const previewPort = Number(process.env.WORKSHOP_PREVIEW_PORT || 3000);
const editorOrigin = `http://127.0.0.1:${editorPort}`;
const previewHost = "127.0.0.1";
const undoStack = [];
let childProcess = null;

const assetTypes = new Map([
  ["editor.css", "text/css; charset=utf-8"],
  ["editor.js", "text/javascript; charset=utf-8"],
]);

function isLoopback(request) {
  const address = request.socket.remoteAddress || "";
  return address === "127.0.0.1" || address === "::1" || address === "::ffff:127.0.0.1";
}

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sendJson(response, status, payload) {
  response.writeHead(status, {
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify(payload));
}

async function readBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 100_000) throw new Error("Request body is too large.");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

async function writeSource(source) {
  const temporaryPath = `${sourcePath}.workshop-editor-${process.pid}.tmp`;
  await writeFile(temporaryPath, source, "utf8");
  await rename(temporaryPath, sourcePath);
}

async function handleApi(request, response, pathname) {
  if (!isLoopback(request)) {
    sendJson(response, 403, { error: "The workshop editor is available only on this computer." });
    return;
  }

  if (request.method === "GET" && pathname === "/__workshop_editor/api/content") {
    const source = await readFile(sourcePath, "utf8");
    const snapshot = buildSnapshot(source);
    sendJson(response, 200, {
      version: snapshot.version,
      entries: snapshot.entries,
      canUndo: undoStack.length > 0,
      sourceFile: "app/page.tsx",
    });
    return;
  }

  if (request.method === "POST" && pathname === "/__workshop_editor/api/save") {
    const body = await readBody(request);
    const source = await readFile(sourcePath, "utf8");
    const result = applyEdit(source, body);
    await writeSource(result.source);
    undoStack.push({ before: source, afterVersion: result.version });
    if (undoStack.length > 20) undoStack.shift();
    sendJson(response, 200, {
      ok: true,
      canUndo: true,
      version: result.version,
      saved: {
        section: result.section,
        tag: result.tag,
        value: result.value,
      },
    });
    return;
  }

  if (request.method === "POST" && pathname === "/__workshop_editor/api/undo") {
    const latest = undoStack.at(-1);
    if (!latest) {
      sendJson(response, 409, { error: "There is no editor save to undo." });
      return;
    }
    const current = await readFile(sourcePath, "utf8");
    if (hash(current) !== latest.afterVersion) {
      sendJson(response, 409, {
        error: "The page changed outside the editor. Use Git to review or undo that change.",
      });
      return;
    }
    await writeSource(latest.before);
    undoStack.pop();
    sendJson(response, 200, { ok: true, canUndo: undoStack.length > 0 });
    return;
  }

  sendJson(response, 404, { error: "Unknown editor action." });
}

function serveAsset(response, filename) {
  const contentType = assetTypes.get(filename);
  if (!contentType) return false;
  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Type": contentType,
  });
  createReadStream(path.join(assetDirectory, filename)).pipe(response);
  return true;
}

function proxyRequest(request, response) {
  const headers = { ...request.headers, host: `${previewHost}:${previewPort}` };
  const upstream = http.request(
    {
      hostname: previewHost,
      port: previewPort,
      path: request.url,
      method: request.method,
      headers,
    },
    (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    },
  );

  upstream.on("error", () => {
    response.writeHead(503, { "Content-Type": "text/html; charset=utf-8" });
    response.end(`<!doctype html><meta http-equiv="refresh" content="1"><title>Starting preview</title><style>body{font:16px system-ui;padding:3rem;color:#3c4043}</style><p>Starting the workshop preview…</p>`);
  });
  request.pipe(upstream);
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || "/", editorOrigin);
  try {
    if (url.pathname.startsWith("/__workshop_editor/api/")) {
      await handleApi(request, response, url.pathname);
      return;
    }
    if (url.pathname === "/__workshop_editor" || url.pathname === "/__workshop_editor/") {
      response.writeHead(200, {
        "Cache-Control": "no-store",
        "Content-Type": "text/html; charset=utf-8",
      });
      createReadStream(path.join(assetDirectory, "index.html")).pipe(response);
      return;
    }
    if (url.pathname.startsWith("/__workshop_editor/")) {
      const filename = path.basename(url.pathname);
      if (serveAsset(response, filename)) return;
    }
    proxyRequest(request, response);
  } catch (error) {
    sendJson(response, error.code === "STALE_SOURCE" ? 409 : 500, {
      error: error instanceof Error ? error.message : "The local editor failed.",
    });
  }
});

server.on("upgrade", (request, socket, head) => {
  const upstream = net.connect(previewPort, previewHost, () => {
    const headers = Object.entries({ ...request.headers, host: `${previewHost}:${previewPort}` })
      .map(([name, value]) => `${name}: ${value}`)
      .join("\r\n");
    upstream.write(`${request.method} ${request.url} HTTP/${request.httpVersion}\r\n${headers}\r\n\r\n`);
    if (head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.on("error", () => socket.destroy());
});

async function previewIsWorkshop() {
  try {
    const response = await fetch(`http://${previewHost}:${previewPort}`, {
      signal: AbortSignal.timeout(800),
    });
    const html = await response.text();
    return response.ok && html.includes("Software (re)-Factory");
  } catch {
    return false;
  }
}

function openEditor() {
  if (process.argv.includes("--no-open") || process.env.CI) return;
  const command = process.platform === "darwin"
    ? ["open", [editorOrigin + "/__workshop_editor"]]
    : process.platform === "win32"
      ? ["cmd", ["/c", "start", "", editorOrigin + "/__workshop_editor"]]
      : ["xdg-open", [editorOrigin + "/__workshop_editor"]];
  const opener = spawn(command[0], command[1], { detached: true, stdio: "ignore" });
  opener.unref();
}

function stop() {
  if (childProcess && !childProcess.killed) childProcess.kill("SIGTERM");
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1_000).unref();
}

server.listen(editorPort, "127.0.0.1", async () => {
  const previewReady = await previewIsWorkshop();
  if (!previewReady) {
    childProcess = spawn(
      "npm",
      ["run", "dev", "--", "--hostname", previewHost, "--port", String(previewPort)],
      {
      cwd: projectDirectory,
      env: process.env,
      stdio: "inherit",
      },
    );
    childProcess.on("exit", (code) => {
      if (code && code !== 0) {
        process.stderr.write(`\nWorkshop preview stopped with exit code ${code}.\n`);
      }
    });
  }

  process.stdout.write(`\nWorkshop editor: ${editorOrigin}/__workshop_editor\n`);
  process.stdout.write("Click text in the preview, edit it, then choose Save to project.\n\n");
  setTimeout(openEditor, 900);
});

process.on("SIGINT", stop);
process.on("SIGTERM", stop);
