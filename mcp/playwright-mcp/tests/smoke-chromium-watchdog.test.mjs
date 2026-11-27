import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync, copyFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const smoke = join(here, "..", "scripts", "smoke-chromium.cjs");

function withFakePlaywright(fn) {
  const dir = mkdtempSync(join(tmpdir(), "zari184-smoke-"));
  try {
    const scriptDir = join(dir, "scripts");
    const core = join(dir, "node_modules", "playwright-core");
    const executable = join(dir, "chromium-1247", "chrome-linux64", "chrome");
    mkdirSync(scriptDir, { recursive: true });
    mkdirSync(core, { recursive: true });
    mkdirSync(dirname(executable), { recursive: true });
    copyFileSync(smoke, join(scriptDir, "smoke-chromium.cjs"));
    writeFileSync(executable, "");
    writeFileSync(join(core, "browsers.json"), JSON.stringify({
      browsers: [{ name: "chromium", revision: "1247" }, { name: "chromium-headless-shell", revision: "1247" }],
    }));
    writeFileSync(join(core, "package.json"), JSON.stringify({
      name: "playwright-core", version: "1.64.0-alpha-test", main: "index.js",
    }));
    writeFileSync(join(core, "index.js"), [
      'const path = require("node:path");',
      "exports.chromium = {",
      '  executablePath: () => path.join(__dirname, "..", "..", "chromium-1247", "chrome-linux64", "chrome"),',
      '  launch: async () => {',
      '    if (process.env.TEST_HUNG_BROWSER === "1") return new Promise(() => {});',
      '    let connected = true;',
      '    return {',
      '      version: () => "fake-chromium",',
      '      newPage: async () => ({',
      '        setContent: async () => {},',
      '        evaluate: async () => 2,',
      '        title: async () => "playwright-mcp-smoke",',
      '      }),',
      '      close: async () => { connected = false; },',
      '      isConnected: () => connected,',
      '    };',
      '  },',
      '};',
    ].join("\n"));
    const run = (env = {}) => spawnSync(process.execPath, [join(scriptDir, "smoke-chromium.cjs")], {
      env: { ...process.env, SMOKE_CHROMIUM_WATCHDOG_MS: "1300", ...env },
      encoding: "utf8",
      timeout: 6000,
    });
    fn(run);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("smoke exits 0 only after page assertions and browser cleanup", () => {
  withFakePlaywright((run) => {
    const result = run();
    assert.equal(result.status, 0, "smoke success failed: " + result.stderr);
    assert.match(result.stdout, /"ok": true/);
    assert.match(result.stdout, /"browserClosed": true/);
    assert.match(result.stderr, /SMOKE_STAGE close-chromium/);
  });
});

test("unresolved browser launch is nonzero with explicit watchdog failure", () => {
  withFakePlaywright((run) => {
    const result = run({ TEST_HUNG_BROWSER: "1" });
    assert.equal(result.error, undefined, "watchdog never fired");
    assert.notEqual(result.status, 0, "an unresolved Chromium launch exited 0");
    assert.match(result.stderr, /"code":"SMOKE_WATCHDOG_TIMEOUT"/);
    assert.match(result.stderr, /"stage":"launch-chromium"/);
  });
});

test("bad page title is nonzero and still closes the browser", () => {
  withFakePlaywright((run) => {
    const result = run({ SMOKE_EXPECT_TITLE: "wrong-title" });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /"code": "SCRIPT_FAILED"/);
    assert.match(result.stderr, /SMOKE_STAGE close-chromium/);
  });
});
