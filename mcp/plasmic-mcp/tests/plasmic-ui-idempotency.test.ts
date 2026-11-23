import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PlasmicClient } from "../libs/plasmic-client/client.ts";
import { plasmicUiTools } from "../services/plasmic-mcp/ui-tools.ts";

test("native UI write retry is scoped per Plasmic branch and rejects changed input", async () => {
  const dir = await mkdtemp(join(tmpdir(), "plasmic-ui-branch-lock-"));
  const client = new PlasmicClient({ baseUrl: "http://127.0.0.1:9" });
  const calls: string[] = [];
  Object.assign(client, {
    mutate: async (
      _projectId: string, branchId: string | undefined,
      _fn: unknown, _opts: unknown,
    ) => {
      calls.push(branchId ?? "main");
      return { revision: 1 + calls.length, dryRun: false, changed: ["example"] };
    },
  });
  const tools = plasmicUiTools({
    client, stateDir: dir, auditFile: join(dir, "audit.jsonl"),
  });
  const setter = tools.find(t => t.name === "plasmic_batch_set_styles");
  assert.ok(setter);
  const input = {
    projectId: "test-project", idempotencyKey: "reused-key-123",
    dryRun: false,
    edits: [{ elementId: "element-1", styles: { color: "#112233" } }],
  };
  const first = await setter.handler({ ...input, branchId: "branch-a" }) as { deduped: boolean };
  const replay = await setter.handler({ ...input, branchId: "branch-a" }) as { deduped: boolean };
  const other = await setter.handler({ ...input, branchId: "branch-b" }) as { deduped: boolean };
  assert.equal(first.deduped, false);
  assert.equal(replay.deduped, true);
  assert.equal(other.deduped, false);
  assert.deepEqual(calls, ["branch-a", "branch-b"]);
  await assert.rejects(
    setter.handler({
      ...input, branchId: "branch-a",
      edits: [{ elementId: "element-1", styles: { color: "#445566" } }],
    }),
    /IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_INPUT/,
  );
  assert.deepEqual(calls, ["branch-a", "branch-b"], "different input must not reach WAB");
});
