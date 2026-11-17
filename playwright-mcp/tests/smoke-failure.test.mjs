// Failure-path suite for the two smoke helpers.
//
// These tests exist because of the CTO finding on 973ce0c: `smoke-mcp.cjs`
// accepted any HTTP 200 whose body contained the page title, but the requested
// data URL contains that title, so a failed launch — which echoes the URL —
// produced a green build smoke. The suite also proves the smoke helpers clean
// up on failure instead of leaking the proxy/backend/browser, which the old
// `process.exit(1)` inside `try/finally` did.
import assert from "node:assert/strict";
import test from "node:test";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { once } from "node:events";
import { connect } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdtempSync, readFileSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "..");
const SMOKE_MCP = join(ROOT, "scripts", "smoke-mcp.cjs");
const SMOKE_CHROMIUM = join(ROOT, "scripts", "smoke-chromium.cjs");
const STUB = join(here, "fixtures", "stub-smoke-backend.mjs");
const PAGE_TITLE = "playwright-mcp-smoke";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function freePort() {
  const srv = createServer();
  srv.listen(0, "127.0.0.1");
  await once(srv, "listening");
  const { port } = srv.address();
  srv.close();
  await once(srv, "close");
  return port;
}

function portOpen(port) {
  return new Promise((resolve) => {
    const socket = connect({ host: "127.0.0.1", port });
    const done = (open) => { socket.destroy(); resolve(open); };
    socket.setTimeout(800, () => done(false));
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
  });
}

const processAlive = (pid) => {
  try { process.kill(pid, 0); return true; } catch (e) { return e.code === "EPERM"; }
};

function lastJson(text) {
  const trimmed = String(text || "").trim();
  const start = trimmed.lastIndexOf("\n{");
  const candidates = [trimmed, start === -1 ? null : trimmed.slice(start + 1)].filter(Boolean);
  for (const candidate of candidates) {
    try { return JSON.parse(candidate); } catch { /* keep trying */ }
  }
  return null;
}

// Runs the shipped smoke-mcp against the scripted stub backend.
async function runSmoke(mode) {
  const port = await freePort();
  const dir = mkdtempSync(join(tmpdir(), `pw-smoke-${mode}-`));
  const pidFile = join(dir, "stub.pid");
  const run = spawnSync(process.execPath, [SMOKE_MCP], {
    env: { ...process.env, SMOKE_BACKEND_ENTRY: STUB, SMOKE_STUB_MODE: mode, SMOKE_STUB_PID_FILE: pidFile,
      SMOKE_LISTEN_PORT: String(port), SMOKE_BOOT_TIMEOUT_MS: "30000" },
    encoding: "utf8",
    timeout: 60000,
  });
  const stubPid = existsSync(pidFile) ? Number(readFileSync(pidFile, "utf8").trim()) : null;
  return { status: run.status, stdout: run.stdout, stderr: run.stderr, json: lastJson(run.stderr) || lastJson(run.stdout),
    port, stubPid, dir };
}

// No orphan proxy port, no live stub backend (the backend's Chromium is in its
// process group and dies with it).
async function assertNoOrphans(result) {
  await sleep(300);
  assert.equal(await portOpen(result.port), false, `proxy port ${result.port} is still open after the smoke exited`);
  if (result.stubPid) {
    for (let i = 0; i < 20 && processAlive(result.stubPid); i++) await sleep(200);
    assert.equal(processAlive(result.stubPid), false, `stub backend pid ${result.stubPid} survived the smoke`);
  }
  assert.equal(result.json && result.json.cleanup && result.json.cleanup.proxyPortClosed, true,
    "the smoke must report a closed proxy port");
}

test("POSITIVE CONTROL: a real snapshot result passes", async () => {
  const result = await runSmoke("success");
  assert.equal(result.status, 0, `expected exit 0, got ${result.status}: ${result.stderr.slice(-800)}`);
  assert.equal(result.json.ok, true);
  assert.equal(result.json.pageTitle, PAGE_TITLE);
  assert.equal(result.json.cleanup.backendPortClosed, true);
  await assertNoOrphans(result);
});

test("NEGATIVE: an error that echoes the requested URL/title cannot pass", async () => {
  const result = await runSmoke("error-echo-url");
  assert.equal(result.status, 1, `an error result must fail the smoke: ${result.stdout}`);
  assert.equal(result.json.ok, false);
  assert.equal(result.json.code, "TOOL_CALL_IS_ERROR",
    `expected the isError gate to reject it, got ${result.json.code}: ${result.json.detail}`);
  await assertNoOrphans(result);
});

test("NEGATIVE: isError=true cannot pass even when the payload looks like a snapshot", async () => {
  const result = await runSmoke("error-with-fake-snapshot");
  assert.equal(result.status, 1);
  assert.equal(result.json.code, "TOOL_CALL_IS_ERROR",
    `a well-formed snapshot inside an error result must still be rejected, got ${result.json.code}`);
  await assertNoOrphans(result);
});

test("NEGATIVE: a snapshot of the wrong page cannot pass", async () => {
  const result = await runSmoke("wrong-title");
  assert.equal(result.status, 1);
  assert.equal(result.json.code, "SNAPSHOT_TITLE_MISMATCH",
    `expected title validation to reject it, got ${result.json.code}: ${result.json.detail}`);
  await assertNoOrphans(result);
});

test("failure cleanup also holds for the shipped Chromium smoke", async (t) => {
  const coreDir = join(ROOT, "node_modules", "playwright-core");
  if (!existsSync(join(coreDir, "browsers.json"))) {
    t.skip("node_modules/playwright-core is not installed in this checkout");
    return;
  }
  const { chromium } = require(coreDir);
  const executablePath = chromium.executablePath();
  if (!existsSync(executablePath)) {
    t.skip(`pinned Chromium is not installed at ${executablePath}`);
    return;
  }
  // Force a post-launch assertion failure: the browser must still be closed.
  const run = spawnSync(process.execPath, [SMOKE_CHROMIUM], {
    env: { ...process.env, SMOKE_EXPECT_TITLE: "a-title-this-page-does-not-have" },
    encoding: "utf8",
    timeout: 60000,
  });
  assert.equal(run.status, 1, `expected exit 1, got ${run.status}`);
  const json = lastJson(run.stderr);
  assert.equal(json && json.code, "SCRIPT_FAILED", `expected SCRIPT_FAILED, got ${json && json.code}`);
  await sleep(500);
  const survivors = readProcessCommandLines().filter((cmd) => cmd.includes(executablePath));
  assert.deepEqual(survivors, [], `Chromium survived the failed smoke: ${survivors.join(" | ")}`);
});

test("CONTROL: the orphan detector catches a launcher that skips cleanup", async () => {
  const dir = mkdtempSync(join(tmpdir(), "pw-orphan-"));
  const launcher = join(dir, "leaky.cjs");
  const port = await freePort();
  writeFileSync(launcher, `
    const { spawn } = require("node:child_process");
    const child = spawn(process.execPath, [${JSON.stringify(join(ROOT, "idle-proxy.cjs"))}], {
      env: { ...process.env, LISTEN_PORTS: ${JSON.stringify(String(port))}, BACKEND_ENTRY: ${JSON.stringify(STUB)} },
      stdio: "ignore", detached: true,
    });
    child.unref();
    console.log(child.pid);
  `);
  const run = spawnSync(process.execPath, [launcher], { encoding: "utf8", timeout: 20000 });
  const pid = Number(String(run.stdout).trim());
  try {
    let open = false;
    for (let i = 0; i < 30 && !open; i++) { open = await portOpen(port); if (!open) await sleep(200); }
    assert.equal(open, true, "a launcher that skips cleanup must leave the proxy port open, else the orphan assertion proves nothing");
  } finally {
    try { process.kill(-pid, "SIGKILL"); } catch { try { process.kill(pid, "SIGKILL"); } catch { /* gone */ } }
    await sleep(300);
  }
});

function readProcessCommandLines() {
  const { readdirSync } = require("node:fs");
  const out = [];
  for (const entry of readdirSync("/proc")) {
    if (!/^\d+$/.test(entry)) continue;
    try {
      const raw = readFileSync(`/proc/${entry}/cmdline`, "utf8");
      out.push(raw.split("\0").join(" ").trim());
    } catch { /* process vanished */ }
  }
  return out;
}
