// Regresja: /state musi być zapisywalny przez uid kontenera, a gdy nie jest,
// narzędzie musi zwrócić konkretną diagnozę zamiast surowego EACCES.
import assert from "node:assert/strict";
import test from "node:test";
import { chmod, mkdtemp, readFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import {
  probeStateDir,
  requireWritableStateDir,
} from "@design-stack/contracts/state";
import { plasmicTools, type PlasmicCtx } from "../services/plasmic-mcp/tools.ts";
import type { PlasmicClient } from "@design-stack/plasmic-client";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const isRoot = typeof process.getuid === "function" && process.getuid() === 0;

/** Katalog istniejący, ale bez prawa zapisu dla bieżącego użytkownika. */
async function unwritableDir() {
  const dir = await mkdtemp(join(tmpdir(), "plasmic-ro-"));
  await chmod(dir, 0o555);
  return dir;
}

function fakeCtx(stateDir: string): PlasmicCtx {
  const client = {
    getProjectRev: async () => ({
      revision: 7,
      bundle: { map: { AaBbCcDdEeFf: { __type: "Text", name: "Title" } } },
    }),
  } as unknown as PlasmicClient;
  return { client, stateDir, auditFile: join(stateDir, "audit.jsonl") };
}

test("writable state dir passes the probe", async () => {
  const dir = await mkdtemp(join(tmpdir(), "plasmic-rw-"));
  const probe = await probeStateDir(dir);
  assert.equal(probe.ok, true);
  assert.equal(probe.detail, undefined);
});

test("unwritable state dir is reported with path, uid and the fix", { skip: isRoot ? "root bypasses permission checks" : false }, async () => {
  const dir = await unwritableDir();
  const probe = await probeStateDir(dir);
  assert.equal(probe.ok, false);
  assert.match(probe.detail ?? "", /EACCES/);
  assert.ok(probe.detail?.includes(dir), "diagnostic must name the exact path");
  assert.match(probe.detail ?? "", /uid 10001/);
  assert.match(probe.detail ?? "", /chown/);
});

test("write gate fails closed with STATE_DIR_UNWRITABLE", { skip: isRoot ? "root bypasses permission checks" : false }, async () => {
  const dir = await unwritableDir();
  await assert.rejects(
    () => requireWritableStateDir(join(dir, "locks"), "plasmic_update_text project lock"),
    (e: Error) => {
      assert.match(e.message, /^STATE_DIR_UNWRITABLE \(plasmic_update_text project lock\)/);
      assert.ok(e.message.includes(join(dir, "locks")));
      return true;
    },
  );
});

test("plasmic_get_changes reports the state-dir cause instead of a bare EACCES", { skip: isRoot ? "root bypasses permission checks" : false }, async () => {
  const dir = await unwritableDir();
  const tools = plasmicTools(fakeCtx(dir));
  const getChanges = tools.find((t) => t.name === "plasmic_get_changes");
  assert.ok(getChanges, "plasmic_get_changes must exist");
  await assert.rejects(
    () => getChanges!.handler({ projectId: "proj-1" }),
    (e: Error) => {
      assert.match(e.message, /STATE_DIR_UNWRITABLE \(plasmic_get_changes seen marker\)/);
      assert.ok(e.message.includes(join(dir, "seen")));
      return true;
    },
  );
});

test("plasmic_get_changes writes the seen marker when the state dir is writable", async () => {
  const dir = await mkdtemp(join(tmpdir(), "plasmic-seen-"));
  const tools = plasmicTools(fakeCtx(dir));
  const getChanges = tools.find((t) => t.name === "plasmic_get_changes")!;
  const first = (await getChanges.handler({ projectId: "proj-1" })) as {
    changed: boolean;
    lastSeen: unknown;
  };
  assert.equal(first.changed, true);
  assert.equal(first.lastSeen, null);
  const marker = JSON.parse(await readFile(join(dir, "seen", "proj-1__main.json"), "utf8"));
  assert.equal(marker.revision, 7);
  const second = (await getChanges.handler({ projectId: "proj-1" })) as { changed: boolean };
  assert.equal(second.changed, false, "second read of an unchanged revision must not report a change");
});

test("image prepares /state for the runtime uid before dropping privileges", async () => {
  const dockerfile = await readFile(join(root, "Dockerfile"), "utf8");
  assert.match(dockerfile, /mkdir -p \/state/, "Dockerfile must create the /state mount point");
  assert.match(dockerfile, /chown -R mcp:mcp \/app \/state/, "/state must be owned by the runtime user");
  const chownAt = dockerfile.indexOf("chown -R mcp:mcp /app /state");
  const userAt = dockerfile.indexOf("\nUSER mcp");
  assert.ok(chownAt > 0 && userAt > chownAt, "ownership must be set before USER mcp");
});
