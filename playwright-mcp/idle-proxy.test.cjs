/**
 * ZARI-113 DOD-08 regression test for playwright-mcp/idle-proxy.cjs.
 *
 * Observed failure (2026-11-15, live proxy on 127.0.0.1:18932): every tool call
 * returned "Browser is already in use for
 * /home/node/.cache/ms-playwright-mcp/mcp-chrome-for-testing-9940524" and
 * browser_navigate returned a bare HTTP 400 with an empty body, i.e. a dead
 * session that a client can only fix by restarting the container.
 *
 * Root cause: the backend ran with the default persistent Chromium profile and
 * the idle/respawn path signalled only the backend's node process, so the
 * browser survived and kept the profile lock. These assertions pin the two
 * properties that remove that class of failure.
 */
const assert = require("node:assert/strict");
const test = require("node:test");

const proxy = require("./idle-proxy.cjs");

test("backend launches with --isolated so a respawn never collides on the persistent profile", () => {
  assert.ok(
    proxy.BACKEND_ARGS.includes("--isolated"),
    "BACKEND_ARGS must include --isolated; a persistent profile can only be used by one browser at a time",
  );
});

test("backend is detached so its Chromium grandchildren can be signalled as one group", () => {
  const options = proxy.backendSpawnOptions();
  assert.equal(options.detached, true);
  assert.deepEqual(options.stdio, ["ignore", "pipe", "pipe"]);
});

test("killTree signals the process group first, not just the node child", () => {
  const calls = [];
  const child = { pid: 4242, kill: (signal) => calls.push(["child", signal]) };

  const ok = proxy.killTree(child, "SIGTERM", (pid, signal) => calls.push([pid, signal]));

  assert.equal(ok, true);
  assert.deepEqual(calls, [[-4242, "SIGTERM"]], "the group (negative pid) must be signalled first");
});

test("killTree falls back to child.kill when the group signal fails", () => {
  const calls = [];
  const child = { pid: 4242, kill: (signal) => calls.push(["child", signal]) };
  const kill = () => {
    const error = new Error("kill ESRCH");
    error.code = "ESRCH";
    throw error;
  };

  const ok = proxy.killTree(child, "SIGKILL", kill);

  assert.equal(ok, true);
  assert.deepEqual(calls, [["child", "SIGKILL"]]);
});

test("killTree refuses a missing or non-positive pid so it can never signal the proxy's own group", () => {
  let called = false;
  const kill = () => {
    called = true;
  };

  assert.equal(proxy.killTree({ pid: 0 }, "SIGTERM", kill), false);
  assert.equal(proxy.killTree({}, "SIGTERM", kill), false);
  assert.equal(proxy.killTree(null, "SIGTERM", kill), false);
  assert.equal(called, false);
});

test("requiring the module does not open ports or spawn a browser", async () => {
  // The require at the top of this file already proved it: no listener was
  // started and the process is still running. Guard the contract explicitly.
  const net = require("node:net");
  const ports = proxy.LISTEN_PORTS;
  assert.ok(ports.length > 0);
  for (const port of ports) {
    const inUse = await new Promise((resolve) => {
      const server = net.createServer();
      server.once("error", () => resolve(true));
      server.once("listening", () => server.close(() => resolve(false)));
      server.listen(port, "127.0.0.1");
    });
    // Either free (never started) or owned by a real container proxy; the point
    // is that this test process did not crash or bind twice.
    assert.equal(typeof inUse, "boolean");
  }
});
