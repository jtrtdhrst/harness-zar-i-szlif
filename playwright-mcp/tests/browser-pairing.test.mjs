// Regression suite for the Playwright MCP browser/version pairing.
//
// The 2026-11-17 production defect: the image was built on a Playwright 1.57
// base image (Chromium revision 1200) while @playwright/mcp 0.0.83 pins
// playwright 1.64.0-alpha-1790635538000 (Chromium revision 1247). Browser
// download was skipped, so the container failed on first use with
// `Executable doesn't exist at /ms-playwright/chromium_headless_shell-1247/...`.
//
// These tests are the negative controls for the guard: the exact pre-fix
// Dockerfile must FAIL, and each single-rule mutation must FAIL for its own
// reason, so a passing guard is never a guard that simply says "ok".
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "..");
const { checkPairing } = require(join(ROOT, "scripts", "check-browser-pairing.cjs"));

const read = (p) => readFileSync(join(ROOT, p), "utf8");
const DOCKERFILE = read("Dockerfile");
const PACKAGE_JSON = read("package.json");
const PACKAGE_LOCK = read("package-lock.json");

// The shipped files, as they were before this fix, kept verbatim so the defect
// stays reproducible in the suite.
const PRE_FIX_DOCKERFILE = `FROM mcr.microsoft.com/playwright:v1.57.0-noble

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \\
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \\
    NODE_ENV=production \\
    IDLE_SECONDS=600 \\
    LISTEN_PORTS=8932,8761 \\
    HOME=/home/node

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund \\
    && npm cache clean --force \\
    && ln -s /app/node_modules/@playwright/mcp/cli.js /app/cli.js

COPY idle-proxy.cjs ./

EXPOSE 8932 8761
ENTRYPOINT ["node", "/app/idle-proxy.cjs"]
`;

const codes = (result) => result.failures.map((f) => f.code);

test("shipped Dockerfile and lockfile satisfy the pairing contract", () => {
  const result = checkPairing({ dockerfile: DOCKERFILE, packageJson: PACKAGE_JSON, packageLock: PACKAGE_LOCK });
  assert.deepEqual(result.failures, [], `unexpected pairing failures: ${JSON.stringify(result.failures, null, 2)}`);
  assert.equal(result.ok, true);
  // The lockfile, not the base image, is what decides the browser build.
  assert.match(result.facts.lockedPlaywright, /^\d+\.\d+\.\d+(-[0-9A-Za-z.]+)*$/);
  assert.equal(result.facts.lockedPlaywright, result.facts.lockedPlaywrightCore);
  assert.equal(result.facts.baseImageMatchesPinnedPlaywright, false,
    "base image cannot be assumed to ship the pinned browser build");
  assert.equal(result.facts.installsBrowsers, true, "the pinned Chromium build must be installed at build time");
  assert.equal(result.facts.skipsBrowserDownload, false, "browser download must not be skipped while versions differ");
});

test("shipped Dockerfile launches Chromium and the MCP backend at build time", () => {
  assert.match(DOCKERFILE, /smoke-chromium\.cjs/, "build must prove Chromium launches");
  assert.match(DOCKERFILE, /smoke-mcp\.cjs/, "build must prove the MCP backend serves a browser call");
  assert.match(DOCKERFILE, /npm ci\b/, "dependencies must come from the lockfile");
  assert.doesNotMatch(DOCKERFILE, /PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD\s*=\s*["']?1/i);
  assert.ok(existsSync(join(ROOT, "scripts", "smoke-chromium.cjs")));
  assert.ok(existsSync(join(ROOT, "scripts", "smoke-mcp.cjs")));
  assert.ok(existsSync(join(ROOT, "scripts", "docker-smoke.sh")));
});

test("NEGATIVE CONTROL: the pre-fix Dockerfile fails the guard", () => {
  const result = checkPairing({ dockerfile: PRE_FIX_DOCKERFILE, packageJson: PACKAGE_JSON, packageLock: PACKAGE_LOCK });
  assert.equal(result.ok, false, "the defect that broke production must not pass the guard");
  assert.equal(result.facts.baseImageVersion, "1.57.0");
  assert.equal(result.facts.baseImageMatchesPinnedPlaywright, false);
  assert.equal(result.facts.skipsBrowserDownload, true);
  assert.equal(result.facts.installsBrowsers, false);
  const found = codes(result);
  for (const expected of ["BROWSER_SOURCE", "REPRODUCIBLE_INSTALL", "LAUNCH_SMOKE"]) {
    assert.ok(found.includes(expected), `pre-fix Dockerfile should trip ${expected}, got ${found.join(",")}`);
  }
});

test("NEGATIVE CONTROL: a floating @playwright/mcp range fails the pin rule", () => {
  const floating = JSON.stringify({ ...JSON.parse(PACKAGE_JSON), dependencies: { "@playwright/mcp": "^0.0.83" } });
  const result = checkPairing({ dockerfile: DOCKERFILE, packageJson: floating, packageLock: PACKAGE_LOCK });
  assert.equal(result.ok, false);
  assert.ok(codes(result).includes("PIN_EXACT"));
});

test("NEGATIVE CONTROL: a lockfile whose Playwright builds disagree fails", () => {
  const lock = JSON.parse(PACKAGE_LOCK);
  lock.packages["node_modules/playwright-core"].version = "1.57.0";
  const result = checkPairing({ dockerfile: DOCKERFILE, packageJson: PACKAGE_JSON, packageLock: JSON.stringify(lock) });
  assert.equal(result.ok, false);
  assert.ok(codes(result).includes("PIN_EXACT"));
});

test("NEGATIVE CONTROL: dropping the launch smoke fails the guard", () => {
  const noSmoke = DOCKERFILE
    .split("\n")
    .filter((l) => !l.includes("smoke-chromium.cjs") && !l.includes("smoke-mcp.cjs"))
    .join("\n");
  const result = checkPairing({ dockerfile: noSmoke, packageJson: PACKAGE_JSON, packageLock: PACKAGE_LOCK });
  assert.equal(result.ok, false);
  assert.ok(codes(result).includes("LAUNCH_SMOKE"));
});

test("NEGATIVE CONTROL: skipping the download while the base image matches the pin is rejected when an install step also runs", () => {
  const lock = JSON.parse(PACKAGE_LOCK);
  const pinned = lock.packages["node_modules/playwright"].version;
  const matchingBase = DOCKERFILE
    .replace(/^FROM\s+(\S+)$/m, `FROM mcr.microsoft.com/playwright:v${pinned}-noble`)
    .replace("ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright", "ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \\\n    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1");
  const result = checkPairing({ dockerfile: matchingBase, packageJson: PACKAGE_JSON, packageLock: JSON.stringify(lock) });
  assert.equal(result.facts.baseImageMatchesPinnedPlaywright, true);
  assert.equal(result.facts.skipsBrowserDownload, true);
  assert.equal(result.facts.installsBrowsers, true);
  assert.equal(result.ok, false, "two conflicting browser sources must not pass");
  assert.ok(codes(result).includes("BROWSER_SOURCE"));
});

test("POSITIVE CONTROL: a matching base image may skip the browser download", () => {
  const lock = JSON.parse(PACKAGE_LOCK);
  const pinned = lock.packages["node_modules/playwright"].version;
  const matchingBase = DOCKERFILE
    .replace(/^FROM\s+(\S+)$/m, `FROM mcr.microsoft.com/playwright:v${pinned}-noble`)
    .replace(/^RUN node node_modules\/playwright-core\/cli\.js install.*$/m, "")
    .replace("ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright", "ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \\\n    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1");
  const result = checkPairing({ dockerfile: matchingBase, packageJson: PACKAGE_JSON, packageLock: JSON.stringify(lock) });
  assert.deepEqual(result.failures, [], `a base image on exactly the pinned release is a valid browser source: ${JSON.stringify(result.failures)}`);
  assert.equal(result.facts.baseImageMatchesPinnedPlaywright, true);
});

test("the guard CLI exits non-zero on the pre-fix source", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const dir = mkdtempSync(join(tmpdir(), "pw-pairing-"));
  writeFileSync(join(dir, "Dockerfile"), PRE_FIX_DOCKERFILE);
  writeFileSync(join(dir, "package.json"), PACKAGE_JSON);
  writeFileSync(join(dir, "package-lock.json"), PACKAGE_LOCK);
  const run = spawnSync(process.execPath, [join(ROOT, "scripts", "check-browser-pairing.cjs"), dir], { encoding: "utf8" });
  assert.equal(run.status, 1, "guard must fail closed on the pre-fix Dockerfile");
  assert.match(run.stdout, /BROWSER_SOURCE/);

  const ok = spawnSync(process.execPath, [join(ROOT, "scripts", "check-browser-pairing.cjs")], { encoding: "utf8" });
  assert.equal(ok.status, 0, `guard must pass on the shipped files: ${ok.stdout}${ok.stderr}`);
});
