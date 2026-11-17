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
// Exit 0 = Chromium launched and ran script; non-zero = image is unusable.
const fs = require("node:fs");
const path = require("node:path");

const fail = (code, detail) => {
  console.error(JSON.stringify({ ok: false, code, detail }, null, 2));
  process.exit(1);
};

(async () => {
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

  let browser;
  try {
    browser = await chromium.launch({ args: ["--no-sandbox"] });
    const page = await browser.newPage();
    await page.setContent("<title>playwright-mcp-smoke</title><p id=v>1</p>");
    const value = await page.evaluate(() => 1 + 1);
    const title = await page.title();
    const version = browser.version();
    if (value !== 2 || title !== "playwright-mcp-smoke") {
      fail("SCRIPT_FAILED", `page did not evaluate as expected (value=${value}, title=${title})`);
    }
    console.log(JSON.stringify({
      ok: true,
      check: "chromium-launch",
      playwrightCore: expected.playwrightCore,
      chromiumRevision: expected.chromium,
      chromiumHeadlessShellRevision: expected.chromiumHeadlessShell,
      installedRevisionDir: revisionDir,
      executablePath,
      browserVersion: version,
    }, null, 2));
  } catch (e) {
    fail("LAUNCH_FAILED", String((e && e.message) || e).split("\n").slice(0, 6).join(" | "));
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
})();
