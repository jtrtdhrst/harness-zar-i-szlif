// Fail-closed guard for the Playwright MCP image's version pairing.
//
// Production defect this guards against (2026-11-17): the image was built on
// `mcr.microsoft.com/playwright:v1.57.0-noble` (browsers for Playwright 1.57,
// Chromium revision 1200) while `package.json` pulled `@playwright/mcp 0.0.83`,
// which pins `playwright 1.64.0-alpha-1790635538000` and therefore launches
// Chromium revision 1247. With `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` and no
// install step the container died at the first browser call with
// `Executable doesn't exist at /ms-playwright/chromium_headless_shell-1247/...`.
//
// The pairing is a contract, not a preference. This module checks the four
// things that made the defect possible:
//   PIN_EXACT            - dependency versions are exact, and the lockfile pins
//                          the same exact Playwright build (no ranges, no float)
//   REPRODUCIBLE_INSTALL - the image installs from the lockfile (`npm ci`)
//   BROWSER_SOURCE       - the pinned Chromium build is either shipped by the
//                          base image at exactly the pinned Playwright version,
//                          or installed at build time for that build; browser
//                          download must not be skipped while the base image is
//                          on a different release
//   LAUNCH_SMOKE         - the build launches Chromium (and the MCP backend via
//                          the idle proxy) so a missing/mismatched browser
//                          fails the build instead of production traffic
//
// Pure and dependency-free: it parses the committed Dockerfile/package files and
// is exercised by tests/browser-pairing.test.mjs, including mutation controls
// that re-introduce the original defect.
const fs = require("node:fs");
const path = require("node:path");

const EXACT_VERSION = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)*$/;
const CHROMIUM_SMOKE = "smoke-chromium.cjs";
const MCP_SMOKE = "smoke-mcp.cjs";

const readIfExists = (p) => (fs.existsSync(p) ? fs.readFileSync(p, "utf8") : null);

function parseJson(text, label, failures) {
  if (text === null || text === undefined) {
    failures.push({ code: "PIN_EXACT", detail: `${label} is missing` });
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (e) {
    failures.push({ code: "PIN_EXACT", detail: `${label} is not valid JSON: ${e.message}` });
    return null;
  }
}

// `mcr.microsoft.com/playwright:v1.64.1-noble@sha256:...` -> { ref, tag, version }
// Distro/suffix parts of the tag are not part of the Playwright version.
const TAG_SUFFIX = /-(noble|jammy|focal|bookworm|bullseye|alpine\d*|slim|amd64|arm64|latest)$/i;

function parseBaseImage(dockerfile) {
  const m = String(dockerfile || "").match(/^\s*FROM\s+(\S+)/im);
  if (!m) return { ref: null, tag: null, version: null };
  const ref = m[1].replace(/@sha256:[a-f0-9]+$/i, "");
  const tag = ref.includes(":") ? ref.slice(ref.lastIndexOf(":") + 1) : "";
  let versioned = tag;
  while (TAG_SUFFIX.test(versioned)) versioned = versioned.replace(TAG_SUFFIX, "");
  const v = versioned.match(/^v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)*)/);
  return { ref, tag, version: v ? v[1] : null };
}

// Comments describe the rules; only real instructions may satisfy or break them.
const stripComments = (dockerfile) =>
  String(dockerfile || "").split(/\r?\n/).filter((line) => !/^\s*#/.test(line)).join("\n");

const skipDownloadEnabled = (dockerfile) =>
  /PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD\s*=\s*["']?(1|true|yes)["']?/i.test(stripComments(dockerfile));

const installsBrowsers = (dockerfile) =>
  /(?:playwright-core\/cli\.js|playwright\s+|\bnpx\s+playwright)\s+install\b/i.test(stripComments(dockerfile));

function checkPairing({ dockerfile, packageJson, packageLock }) {
  const failures = [];
  const facts = {};

  const pkg = parseJson(packageJson, "package.json", failures);
  const lock = parseJson(packageLock, "package-lock.json", failures);

  const declaredMcp = pkg?.dependencies?.["@playwright/mcp"] ?? null;
  const lockedMcp = lock?.packages?.["node_modules/@playwright/mcp"]?.version ?? null;
  const lockedPlaywright = lock?.packages?.["node_modules/playwright"]?.version ?? null;
  const lockedPlaywrightCore = lock?.packages?.["node_modules/playwright-core"]?.version ?? null;
  const base = parseBaseImage(dockerfile);

  facts.declaredMcp = declaredMcp;
  facts.lockedMcp = lockedMcp;
  facts.lockedPlaywright = lockedPlaywright;
  facts.lockedPlaywrightCore = lockedPlaywrightCore;
  facts.baseImage = base.ref;
  facts.baseImageVersion = base.version;

  // --- PIN_EXACT -----------------------------------------------------------
  if (declaredMcp === null) {
    failures.push({ code: "PIN_EXACT", detail: "@playwright/mcp is not a declared dependency" });
  } else if (!EXACT_VERSION.test(String(declaredMcp))) {
    failures.push({ code: "PIN_EXACT", detail: `@playwright/mcp must be pinned exactly, found "${declaredMcp}"` });
  }
  if (lock) {
    for (const [label, v] of [["@playwright/mcp", lockedMcp], ["playwright", lockedPlaywright], ["playwright-core", lockedPlaywrightCore]]) {
      if (!v) failures.push({ code: "PIN_EXACT", detail: `package-lock.json does not pin ${label}` });
      else if (!EXACT_VERSION.test(String(v))) failures.push({ code: "PIN_EXACT", detail: `package-lock.json pins ${label} with a non-exact version "${v}"` });
    }
    if (declaredMcp && lockedMcp && declaredMcp !== lockedMcp) {
      failures.push({ code: "PIN_EXACT", detail: `package.json declares @playwright/mcp ${declaredMcp} but the lockfile pins ${lockedMcp}` });
    }
    if (lockedPlaywright && lockedPlaywrightCore && lockedPlaywright !== lockedPlaywrightCore) {
      failures.push({ code: "PIN_EXACT", detail: `playwright ${lockedPlaywright} and playwright-core ${lockedPlaywrightCore} are different builds` });
    }
  }

  // --- REPRODUCIBLE_INSTALL -----------------------------------------------
  const df = stripComments(dockerfile);
  if (!/\bnpm\s+ci\b/.test(df)) {
    failures.push({ code: "REPRODUCIBLE_INSTALL", detail: "Dockerfile must install with `npm ci` from the committed lockfile" });
  }
  if (/\bnpm\s+install\b/.test(df)) {
    failures.push({ code: "REPRODUCIBLE_INSTALL", detail: "Dockerfile uses `npm install`, which re-resolves the dependency tree" });
  }

  // --- BROWSER_SOURCE ------------------------------------------------------
  const baseMatchesPin = !!(base.version && lockedPlaywright && base.version === lockedPlaywright);
  facts.baseImageMatchesPinnedPlaywright = baseMatchesPin;
  const installStep = installsBrowsers(df);
  const skipping = skipDownloadEnabled(df);
  facts.installsBrowsers = installStep;
  facts.skipsBrowserDownload = skipping;

  if (baseMatchesPin) {
    // Base image already ships the exact browser build the pin resolves, so
    // skipping the download is legitimate. An extra install step is harmless.
    if (skipping && installStep) {
      failures.push({ code: "BROWSER_SOURCE", detail: "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD is set but an install step is present; pick one source" });
    }
  } else {
    if (skipping) {
      failures.push({
        code: "BROWSER_SOURCE",
        detail: `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD is set while the base image (${base.version || "unknown"}) does not match the pinned Playwright build (${lockedPlaywright || "unknown"}); the required Chromium revision is never installed`,
      });
    }
    if (!installStep) {
      failures.push({
        code: "BROWSER_SOURCE",
        detail: `base image ${base.version || "unknown"} != pinned Playwright ${lockedPlaywright || "unknown"} and the Dockerfile never installs the pinned Chromium build`,
      });
    }
  }

  // --- LAUNCH_SMOKE --------------------------------------------------------
  if (!df.includes(CHROMIUM_SMOKE)) {
    failures.push({ code: "LAUNCH_SMOKE", detail: `Dockerfile must run ${CHROMIUM_SMOKE} so a non-launching browser fails the build` });
  }
  if (!df.includes(MCP_SMOKE)) {
    failures.push({ code: "LAUNCH_SMOKE", detail: `Dockerfile must run ${MCP_SMOKE} so a broken MCP backend/idle proxy fails the build` });
  }

  return { ok: failures.length === 0, failures, facts };
}

function checkFromDisk(root = path.resolve(__dirname, "..")) {
  return checkPairing({
    dockerfile: readIfExists(path.join(root, "Dockerfile")),
    packageJson: readIfExists(path.join(root, "package.json")),
    packageLock: readIfExists(path.join(root, "package-lock.json")),
  });
}

module.exports = { checkPairing, checkFromDisk, parseBaseImage, EXACT_VERSION, CHROMIUM_SMOKE, MCP_SMOKE };

if (require.main === module) {
  const result = checkFromDisk(process.argv[2] ? path.resolve(process.argv[2]) : undefined);
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}
