import test from "node:test";
import assert from "node:assert/strict";
import { inspectDataTokens, planDataToken, plasmicDataTokenTools, tokenValue } from "../services/plasmic-mcp/data-token-tools.ts";
import type { BundleDoc } from "@design-stack/plasmic-client";

const fresh = (): BundleDoc => ({
  version: "test", root: "site", deps: [],
  map: { site: { __type: "Site", dataTokens: [], components: [] } },
});
const applied = (b: BundleDoc, patch: ReturnType<typeof planDataToken>): BundleDoc => {
  const map = { ...b.map, ...patch.map };
  for (const iid of patch.toDeleteIids) delete map[iid];
  return { ...b, map };
};
const created = () => {
  const base = fresh();
  const insert = planDataToken(base, "create", { projectId: "fixture", name: "greeting", valueType: "text", value: "Hello" });
  return { base, insert, bundle: applied(base, insert) };
};

test("Data Token serialization matches WAB Text/Number/Code semantics", () => {
  assert.equal(tokenValue("Hi", "text"), '"Hi"');
  assert.equal(tokenValue(2.5, "number"), "2.5");
  assert.equal(tokenValue("(amount) => Math.round(amount)", "code"), "(amount) => Math.round(amount)");
  assert.equal(tokenValue("x + 1", "code"), "(x + 1)");
  assert.throws(() => tokenValue(Number.POSITIVE_INFINITY, "number"), /INVALID_DATA_TOKEN_NUMBER/);
  assert.throws(() => tokenValue("fetch('https://example.org')", "code"), /UNSAFE_DATA_TOKEN_CODE/);
  assert.throws(() => tokenValue("process.env.SECRET", "code"), /UNSAFE_DATA_TOKEN_CODE/);
});
test("Create emits native WAB DataToken and updates root Site refs without editing original", () => {
  const { base, insert, bundle } = created();
  const token = bundle.map[insert.tokenId]!;
  assert.equal(token.__type, "DataToken");
  assert.equal(token.type, "Data");
  assert.equal(token.value, '"Hello"');
  assert.equal(token.isRegistered, false);
  assert.deepEqual(token.variantedValues, []);
  assert.deepEqual(bundle.map.site!.dataTokens, [{ __ref: insert.tokenId }]);
  assert.deepEqual(base.map.site!.dataTokens, []);
  assert.deepEqual(inspectDataTokens(bundle), [{ id: insert.tokenId, name: "greeting", valueType: "text", registered: false }]);
});
test("Update uses stable iid and preserves UUID while changing value and name", () => {
  const { bundle, insert } = created();
  const prior = bundle.map[insert.tokenId]!;
  const update = planDataToken(bundle, "update", { projectId: "fixture", tokenId: insert.tokenId, name: "welcome", value: "Hello again" });
  const after = applied(bundle, update);
  assert.equal(after.map[insert.tokenId]!.uuid, prior.uuid);
  assert.equal(after.map[insert.tokenId]!.value, '"Hello again"');
  assert.equal(after.map[insert.tokenId]!.name, "welcome");
});
test("Delete removes referenced token, but refuses token in use", () => {
  const { bundle, insert } = created();
  const inUse = { ...bundle, map: { ...bundle.map, page: { __type: "SomeExpression", token: { __ref: insert.tokenId } } } };
  assert.throws(() => planDataToken(inUse, "delete", { projectId: "fixture", tokenId: insert.tokenId }), /DATA_TOKEN_IN_USE/);
  const del = planDataToken(bundle, "delete", { projectId: "fixture", tokenId: insert.tokenId });
  const after = applied(bundle, del);
  assert.equal(after.map[insert.tokenId], undefined);
  assert.deepEqual(after.map.site!.dataTokens, []);
});
test("Conflicts, duplicate names and registered tokens fail closed", () => {
  const { bundle, insert } = created();
  assert.throws(() => planDataToken(bundle, "create", { projectId: "fixture", name: "Greeting", valueType: "text", value: "dup" }), /DATA_TOKEN_NAME_EXISTS/);
  assert.throws(() => planDataToken(bundle, "create", { projectId: "fixture", name: "__proto__", valueType: "text", value: "x" }), /INVALID_DATA_TOKEN_NAME/);
  const registered = { ...bundle, map: { ...bundle.map, [insert.tokenId]: { ...bundle.map[insert.tokenId], isRegistered: true } } };
  assert.throws(() => planDataToken(registered, "update", { projectId: "fixture", tokenId: insert.tokenId, name: "new" }), /REGISTERED_DATA_TOKEN_IMMUTABLE/);
});
test("Five native MCP tool actions expose correct read/write annotations", () => {
  const ctx = { client: {} as any, stateDir: "/tmp/unused", auditFile: "/tmp/unused/audit" };
  const defs = plasmicDataTokenTools(ctx);
  assert.deepEqual(defs.map((x) => x.name), ["plasmic_list_data_tokens", "plasmic_get_data_token", "plasmic_create_data_token", "plasmic_update_data_token", "plasmic_delete_data_token"]);
  assert.equal(defs[0]!.annotations?.readOnlyHint, true);
  assert.equal(defs[1]!.annotations?.readOnlyHint, true);
  assert.equal(defs[2]!.annotations?.readOnlyHint, false);
  assert.equal(defs[4]!.annotations?.destructiveHint, true);
});
test("Dry-run previews existing project without a WAB write or branch auto-publication", async () => {
  let saves = 0;
  const ctx = { client: {
    getProjectRev: async () => ({ revision: 7, bundle: fresh(), modelVersion: 30 }),
    saveFull: async () => { saves++; throw new Error("unsafe write"); },
  } as any, stateDir: "/tmp/unused", auditFile: "/tmp/unused/audit" };
  const def = plasmicDataTokenTools(ctx).find((x) => x.name === "plasmic_create_data_token")!;
  const out = await def.handler({ projectId: "fixture", name: "hello", valueType: "text", value: "World", expectedRevision: 7, dryRun: true });
  assert.equal((out as any).dryRun, true);
  assert.equal((out as any).revision, 7);
  assert.equal(saves, 0);
  await assert.rejects(() => def.handler({ projectId: "fixture", name: "hello", valueType: "text", value: "World", dryRun: false, expectedRevision: 7, idempotencyKey: "abc-def-123" }), /DESIGN_BRANCH/);
  await assert.rejects(() => def.handler({ projectId: "fixture", name: "hello", valueType: "text", value: "World", dryRun: true, expectedRevision: 6 }), /STALE_DATA_TOKEN_REVISION/);
});
test("Production writes have explicit operator project grant and never auto-run on unlisted IDs", async () => {
  const old = process.env.PLASMIC_MCP_WRITABLE_PROJECT_IDS;
  try {
    delete process.env.PLASMIC_MCP_WRITABLE_PROJECT_IDS;
    const ctx = { client: { getProjectRev: async () => { throw new Error("should not contact WAB"); } } as any, stateDir: "/tmp/unused", auditFile: "/tmp/unused/audit" };
    const def = plasmicDataTokenTools(ctx).find((x) => x.name === "plasmic_create_data_token")!;
    await assert.rejects(() => def.handler({ projectId: "unapproved", branchId: "unsafe", name: "x", value: "x", valueType: "text", expectedRevision: 1, dryRun: false, idempotencyKey: "test-key-0001" }), /DATA_TOKEN_PROJECT_WRITE_NOT_APPROVED/);
  } finally {
    if (old === undefined) delete process.env.PLASMIC_MCP_WRITABLE_PROJECT_IDS;
    else process.env.PLASMIC_MCP_WRITABLE_PROJECT_IDS = old;
  }
});

// A DataToken is rendered into the deployed site, so credential material must never enter one
// (create/update) and must never be echoed back from an existing one (read).
const secretText = "CLIENT_SECRET_CANARY_ONLY_NOT_REAL";
test("Text values with credential material are rejected on create and update", () => {
  assert.throws(() => tokenValue(secretText, "text"), /DATA_TOKEN_SECRET_VALUE_REJECTED/);
  assert.throws(() => tokenValue("Bearer abcdefghijklmnop", "text"), /DATA_TOKEN_SECRET_VALUE_REJECTED/);
  assert.throws(() => tokenValue("eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.c2lnbmF0dXJlMTIzNA", "text"), /DATA_TOKEN_SECRET_VALUE_REJECTED/);
  assert.throws(() => tokenValue("AKIAIOSFODNN7EXAMPLE", "text"), /DATA_TOKEN_SECRET_VALUE_REJECTED/);
  assert.throws(() => tokenValue("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", "text"), /DATA_TOKEN_SECRET_VALUE_REJECTED/);
  const { bundle, insert } = created();
  assert.throws(() => planDataToken(bundle, "create", { projectId: "fixture", name: "api", valueType: "text", value: secretText }), /DATA_TOKEN_SECRET_VALUE_REJECTED/);
  assert.throws(() => planDataToken(bundle, "update", { projectId: "fixture", tokenId: insert.tokenId, value: secretText }), /DATA_TOKEN_SECRET_VALUE_REJECTED/);
});
test("Token names that announce a credential are refused", () => {
  const { bundle } = created();
  assert.throws(() => planDataToken(bundle, "create", { projectId: "fixture", name: "client_secret", valueType: "text", value: "Hello" }), /DATA_TOKEN_SECRET_NAME_REJECTED/);
  assert.throws(() => planDataToken(bundle, "create", { projectId: "fixture", name: "SUPABASE_SERVICE_ROLE", valueType: "text", value: "Hello" }), /DATA_TOKEN_SECRET_NAME_REJECTED/);
});
test("Ordinary site text still round-trips through the same guards", () => {
  const { bundle, insert } = created();
  assert.equal(tokenValue("Brand Color #6C47FF", "text"), '"Brand Color #6C47FF"');
  assert.equal(tokenValue("Hello, world", "text"), '"Hello, world"');
  assert.equal(bundle.map[insert.tokenId]!.value, '"Hello"');
  const update = planDataToken(bundle, "update", { projectId: "fixture", tokenId: insert.tokenId, value: "Summer sale — 20% off" });
  assert.equal(applied(bundle, update).map[insert.tokenId]!.value, '"Summer sale — 20% off"');
});
test("get_data_token withholds credential-shaped existing values and returns safe ones", async () => {
  const legacySecret: BundleDoc = {
    version: "test", root: "site", deps: [],
    map: {
      site: { __type: "Site", dataTokens: [{ __ref: "tokSecret" }, { __ref: "tokSafe" }], components: [] },
      tokSecret: { __type: "DataToken", uuid: "u1", name: "legacy", type: "Data", value: JSON.stringify(secretText), variantedValues: [], isRegistered: false, regKey: null },
      tokSafe: { __type: "DataToken", uuid: "u2", name: "greeting", type: "Data", value: JSON.stringify("Hello"), variantedValues: [], isRegistered: false, regKey: null },
    },
  };
  const ctx = { client: { getProjectRev: async () => ({ revision: 4, bundle: legacySecret, modelVersion: 30 }) } as any, stateDir: "/tmp/unused", auditFile: "/tmp/unused/audit" };
  const get = plasmicDataTokenTools(ctx).find((x) => x.name === "plasmic_get_data_token")!;
  const unsafe = await get.handler({ projectId: "fixture", tokenId: "legacy" }) as Record<string, unknown>;
  assert.equal(unsafe.valueRedacted, true);
  assert.equal(unsafe.value, undefined);
  assert.ok(!JSON.stringify(unsafe).includes(secretText), "redacted read must not carry the secret anywhere in the result");
  const safe = await get.handler({ projectId: "fixture", tokenId: "greeting" }) as Record<string, unknown>;
  assert.equal(safe.valueRedacted, false);
  assert.equal(safe.value, '"Hello"');
  const list = plasmicDataTokenTools(ctx).find((x) => x.name === "plasmic_list_data_tokens")!;
  const listed = await list.handler({ projectId: "fixture" }) as Record<string, unknown>;
  assert.ok(!JSON.stringify(listed).includes(secretText), "list must never return values");
});
