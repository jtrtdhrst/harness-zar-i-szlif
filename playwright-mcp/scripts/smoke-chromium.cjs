// Build-time proof that Chromium really launches with the Playwright build this
// image ships.
//
// The 2026-11-17 production failure was a silent version skew: dependencies
// installed fine, the image built fine, and the container only failed later at
// the first browser call with
//   Executable doesn't exist at /ms-playwright/chromium_headless_shell-1247/...
// Running this inside `docker build` turns that class of defect into a build
// failure. It is also the container smoke used after a deploy:
//   docker run --rm --entrypoint node <image> /app/scripts/smoke-chromium.cjs
//
// Exit 0 = Chromium launched, ran script, and was closed; non-zero = unusable.
//
// Cleanup rule: no `process.exit()` on any path. Failures throw, the `finally`
// closes the browser, and only then is the exit code set. A smoke that dies
// mid-way must never leave a Chromium process behind.
//
// SMOKE_EXPECT_TITLE (default `playwright-mcp-smoke`) overrides only the
// expected title, not the page content, so an operator can force a post-launch
// assertion failure to exercise that cleanup path.
const fs = require("node:fs");
const path = require("node:path");

const PAGE_TITLE = "playwright-mcp-smoke";
const EXPECTED_TITLE = process.env.SMOKE_EXPECT_TITLE || PAGE_TITLE;

class SmokeFailure extends Error {
  constructor(code, detail) {
    super(detail);
    this.code = code;
    this.detail = detail;
  }
}
const fail = (code, detail) => { throw new SmokeFailure(code, detail); };

async function run() {
  const coreDir = path.join(__dirname, "..", "node_modules", "playwright-core");
  const browsersJsonPath = path.join(coreDir, "browsers.json");
  if (!fs.existsSync(browsersJsonPath)) {
    fail("PLAYWRIGHT_CORE_MISSING", `no browsers.json at ${browsersJsonPath}; dependencies were not installed`);
  }
  const browsersJson = JSON.parse(fs.readFileSync(browsersJsonPath, "utf8"));
  const revisionOf = (name) => (browsersJson.browsers.find((b) => b.name === name) || {}).revision || null;
  const expected = {
    playwrightCore: require(path.join(coreDir, "package.json")).version,
    chromium: revisionOf("chromium"),
    chromiumHeadlessShell: revisionOf("chromium-headless-shell"),
  };

  const { chromium } = require(path.join(coreDir));
  const executablePath = chromium.executablePath();
  if (!fs.existsSync(executablePath)) {
    fail("BROWSER_NOT_INSTALLED", `pinned Chromium is not present at ${executablePath} (expected revision ${expected.chromium})`);
  }
  // The installed directory name carries the revision the browser build was
  // published under; a mismatch means the pin and the filesystem disagree.
  const revisionDir = path.basename(path.dirname(path.dirname(executablePath)));
  const dirRevision = (revisionDir.match(/(\d+)$/) || [])[1];
  if (expected.chromium && dirRevision && dirRevision !== String(expected.chromium)) {
    fail("REVISION_MISMATCH", `installed browser directory ${revisionDir} does not match pinned revision ${expected.chromium}`);
  }

  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage();
    await page.setContent(`<title>${PAGE_TITLE}</title><p id=v>1</p>`);
    const value = await page.evaluate(() => 1 + 1);
    const title = await page.title();
    const version = browser.version();
    if (value !== 2 || title !== EXPECTED_TITLE) {
      fail("SCRIPT_FAILED", `page did not evaluate as expected (value=${value}, title=${title}, expectedTitle=${EXPECTED_TITLE})`);
    }
    return {
      check: "chromium-launch",
      playwrightCore: expected.playwrightCore,
      chromiumRevision: expected.chromium,
      chromiumHeadlessShellRevision: expected.chromiumHeadlessShell,
      installedRevisionDir: revisionDir,
      executablePath,
      browserVersion: version,
    };
  } finally {
    // Always release the browser, on success and on every failure path.
    await browser.close().catch(() => {});
    if (browser.isConnected && browser.isConnected()) {
      // close() failing would leave a live Chromium behind: that is a defect
      // in its own right and must not be reported as a clean run.
      throw new SmokeFailure("BROWSER_NOT_CLOSED", "Chromium is still connected after close()");
    }
  }
}

(async () => {
  let outcome = null;
  let failure = null;
  try {
    outcome = await run();
  } catch (e) {
    failure = e instanceof SmokeFailure ? e : new SmokeFailure("SMOKE_ERROR", String((e && e.message) || e));
  }
  if (failure) {
    console.error(JSON.stringify({ ok: false, code: failure.code, detail: failure.detail }, null, 2));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify({ ok: true, cleanup: { browserClosed: true }, ...outcome }, null, 2));
  process.exitCode = 0;
})();
