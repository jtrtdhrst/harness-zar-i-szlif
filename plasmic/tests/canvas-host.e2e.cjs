#!/usr/bin/env node
"use strict";
/**
 * Read-only Plasmic Canvas Host regression test. Requires Playwright.
 * The synthetic top frame contains no user credentials or real project data.
 * Usage: PLAYWRIGHT_CHROMIUM_PATH=/path/to/chrome node canvas-host.e2e.cjs
 */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const studio = (process.env.PLASMIC_STUDIO_ORIGIN || "https://plasmic.kompaszbiorek.pl").replace(/\/$/, "");
const host = (process.env.PLASMIC_HOST_ORIGIN || "https://plasmic-host.51.89.174.58.sslip.io").replace(/\/$/, "");
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;

async function run() {
  assert.notEqual(new URL(studio).origin, new URL(host).origin,
    "Canvas host must run on a different origin than Studio");
  const response = await fetch(host + "/static/host.html");
  assert.equal(response.status, 200, "Canvas host must be publicly reachable");
  assert.match(response.headers.get("content-type") || "", /html/i);
  const start = Date.now();
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
    args: ["--no-sandbox"]
  });
  try {
    const context = await browser.newContext();
    const parentUrl = studio + "/__plasmic_canvas_host_e2e_parent";
    await context.route(parentUrl, (route) => route.fulfill({
      status: 200,
      contentType: "text/html",
      body: '<!doctype html><title>Canvas host test</title>' +
            '<script>window.__messages=[];' +
            'window.addEventListener("message",e=>window.__messages.push(e.data?.type||null));</script>'
    }));
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(parentUrl, { waitUntil: "load" });
    const params = new URLSearchParams({
      origin: studio,
      staticBaseUrl: studio + "/static",
      isProd: "false"
    }).toString();
    await page.evaluate((url) => {
      const iframe = document.createElement("iframe");
      iframe.src = url;
      document.body.appendChild(iframe);
    }, host + "/static/host.html#" + params);
    await page.waitForFunction(
      () => window.__messages.includes("PLASMIC_HOST_REGISTER"),
      null,
      { timeout: 20000 }
    );
    assert.deepEqual(errors, [], "No JavaScript errors during Canvas host bootstrap");
    console.log(JSON.stringify({
      result: "PASS",
      event: "PLASMIC_HOST_REGISTER",
      studio, host, elapsedMs: Date.now() - start
    }));
  } finally {
    await browser.close();
  }
}
run().catch((error) => {
  console.error(JSON.stringify({ result: "FAIL", reason: error.message }));
  process.exitCode = 1;
});
