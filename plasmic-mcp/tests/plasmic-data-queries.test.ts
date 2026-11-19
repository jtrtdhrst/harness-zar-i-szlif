// ZARI-229 DOD-08: HTTP (Fetch) data-query capability contract over fixtures.
// The point of this file is the fail-closed behaviour: on a WAB build that does
// not declare a data-query capability, or a revision that exposes no query
// model, every write is refused and nothing is written. A declared capability
// plus an observed model enables the write path, proved here on a fixture so no
// live/test-only principal is required to validate the contract.
import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PlasmicClient } from "../libs/plasmic-client/client.ts";
import { plasmicTools } from "../services/plasmic-mcp/tools.ts";

type Map = Record<string, Record<string, unknown>>;

const SECRET = "anon-key-must-never-be-echoed-1234";

const projectPlain = (): Map => ({
  site: { __type: "Site", name: "Site", components: [], pageArenas: [] },
  card: { __type: "Component", name: "Card", uuid: "u-card", tplTree: { __ref: "cardRoot" }, vsettings: [{ __ref: "cardVs" }] },
  cardRoot: { __type: "TplTag", tag: "div", name: "card-root", children: [], vsettings: [{ __ref: "cardVs" }] },
  cardVs: { __type: "VariantSetting", variants: [], attrs: {}, rs: { __ref: "cardRs" }, args: [] },
  cardRs: { __type: "RuleSet", values: {} },
});

const projectWithQuery = (): Map => ({
  ...projectPlain(),
  dsTasks: {
    __type: "DataSource",
    uuid: "u-ds1",
    name: "tasks",
    url: "https://supabase.example.pl/rest/v1/tasks?select=*",
    method: "GET",
    headers: { apikey: SECRET },
    variableName: "tasks",
  },
  viewTag: {
    __type: "TplTag", tag: "div", name: "list",
    children: [], vsettings: [{ __ref: "cardVs" }],
    dynamicValueBinding: { __ref: "exprTasks" },
  },
  exprTasks: { __type: "CustomCode", code: "$q.tasks", fallback: null },
  plainTag: { __type: "TplTag", tag: "div", name: "plain", children: [], vsettings: [{ __ref: "cardVs" }] },
});

const scopeKey = (projectId: string, branchId?: string) =>
  branchId && branchId !== "main" ? `${projectId}@${branchId}` : projectId;

async function setup(options: { capability?: "declared" | "undeclared" | "unreachable" | "none"; failingWrite?: boolean } = {}) {
  const bundles: Record<string, Map> = {
    plain: projectPlain(), queries: projectWithQuery(),
    "queries@branch-a": projectWithQuery(), "queries@branch-b": projectWithQuery(),
  };
  const revisions: Record<string, number> = {
    plain: 4, queries: 9, "queries@branch-a": 9, "queries@branch-b": 9,
  };
  let mutations = 0;
  let failNext = options.failingWrite === true;
  const client = new PlasmicClient({
    baseUrl: "https://wab.fixture.invalid",
    fetchImpl: async () => { throw new Error("NO_NETWORK_IN_FIXTURE"); },
  });
  Object.assign(client, {
    getProjectRev: async (projectId: string, branchId?: string) => {
      const key = scopeKey(projectId, branchId);
      const bundle = bundles[key];
      if (!bundle) throw new Error(`Plasmic 404 /api/v1/projects/${projectId}: fixture has no such project`);
      return {
        revision: revisions[key], revId: `rev-${projectId}`,
        project: { id: projectId, name: projectId }, bundle: { map: structuredClone(bundle) },
        modelVersion: 639587200, hostlessDataVersion: 12,
      };
    },
    mutate: async (
      projectId: string,
      branchId: string | undefined,
      fn: (b: { map: Map }) => { map?: Map; toDeleteIids?: string[] } | null,
      opts?: { dryRun?: boolean },
    ) => {
      const key = scopeKey(projectId, branchId);
      if (failNext && !opts?.dryRun) {
        failNext = false;
        // Simulate WAB's optimistic revision check.
        throw new Error(`Plasmic 412 /api/v1/projects/${projectId}/revisions/${revisions[key]! + 1}: revision conflict`);
      }
      const map = bundles[key]!;
      const patch = fn({ map: structuredClone(map) });
      const changed = [...Object.keys(patch?.map ?? {}), ...(patch?.toDeleteIids ?? []).map((i) => `-${i}`)];
      if (!patch || changed.length === 0) return { revision: revisions[key]!, dryRun: true, changed: [] };
      if (opts?.dryRun) return { revision: revisions[key]!, dryRun: true, changed };
      mutations += 1;
      bundles[key] = { ...map, ...(patch.map ?? {}) };
      for (const iid of patch.toDeleteIids ?? []) delete bundles[key]![iid];
      revisions[key] = revisions[key]! + 1;
      return { revision: revisions[key]!, dryRun: false, changed };
    },
  });
  const mode = options.capability ?? "declared";
  const probeWab = mode === "none" ? undefined : async () => {
    if (mode === "unreachable") return { error: "fetch failed: getaddrinfo ENOTFOUND plasmic.fixture.invalid" };
    return {
      status: 200,
      json: mode === "declared"
        ? { version: "wab-2026.10.1", features: ["data-queries/1", "comments"] }
        : { version: "wab-2026.10.1", features: ["comments"] },
    };
  };
  const stateDir = await mkdtemp(join(tmpdir(), "zari229-dq-"));
  const tools = plasmicTools({
    client, stateDir, auditFile: join(stateDir, "audit.jsonl"),
    wabBaseUrl: mode === "none" ? undefined : "https://plasmic.fixture.invalid",
    ...(probeWab ? { probeWab } : {}),
  });
  const tool = (name: string) => {
    const found = tools.find((t) => t.name === name);
    assert.ok(found, `missing tool ${name}`);
    return found!;
  };
  return {
    tool,
    toolNames: tools.map((t) => t.name),
    mapNow: (projectId = "queries", branchId?: string) => bundles[scopeKey(projectId, branchId)]!,
    revisionNow: (projectId = "queries", branchId?: string) => revisions[scopeKey(projectId, branchId)]!,
    mutationCount: () => mutations,
  };
}

function withAllowlist<T>(hosts: string, fn: () => Promise<T>): Promise<T> {
  const previous = process.env.PLASMIC_DATA_QUERY_ALLOWED_HOSTS;
  process.env.PLASMIC_DATA_QUERY_ALLOWED_HOSTS = hosts;
  return fn().finally(() => {
    if (previous === undefined) delete process.env.PLASMIC_DATA_QUERY_ALLOWED_HOSTS;
    else process.env.PLASMIC_DATA_QUERY_ALLOWED_HOSTS = previous;
  });
}

test("capabilities: a declared capability plus an observed query model reports supported", async () => {
  const { tool } = await setup({ capability: "declared" });
  const caps = await tool("plasmic_get_capabilities").handler({ projectId: "queries" }) as {
    versionStatus: string;
    wab: { version: string | null; host: string | null; declaredFeatures: string[]; probes: Array<{ path: string; status?: number }> };
    dataQueries: { supported: boolean; documentedApi: boolean; queryTypes: string[]; modelVersion: number | null; observedEntryTypes: string[] };
  };
  assert.equal(caps.versionStatus, "VERIFIED");
  assert.equal(caps.wab.version, "wab-2026.10.1");
  assert.equal(caps.wab.host, "plasmic.fixture.invalid");
  assert.deepEqual(caps.wab.probes, [{ path: "/healthcheck", status: 200 }]);
  assert.equal(caps.dataQueries.supported, true);
  assert.equal(caps.dataQueries.documentedApi, true);
  assert.deepEqual(caps.dataQueries.queryTypes, ["DataSource"]);
  assert.equal(caps.dataQueries.modelVersion, 639587200);
  assert.ok(caps.dataQueries.observedEntryTypes.some((t) => t.startsWith("DataSource:")));
});

test("capabilities: an unreachable WAB build is UNVERIFIED, never assumed supported", async () => {
  const { tool } = await setup({ capability: "unreachable" });
  const caps = await tool("plasmic_get_capabilities").handler({ projectId: "queries" }) as {
    versionStatus: string; wab: { version: string | null; probes: Array<{ error?: string }> };
    dataQueries: { supported: boolean; reason: string };
  };
  assert.equal(caps.versionStatus, "UNVERIFIED");
  assert.equal(caps.wab.version, null);
  assert.equal(caps.dataQueries.supported, false);
  assert.match(caps.dataQueries.reason, /WAB_HEALTHCHECK_UNREACHABLE/);
  assert.match(String(caps.wab.probes[0]!.error), /ENOTFOUND/);
});

test("capabilities: no capability declaration means no support even with a query model present", async () => {
  const { tool } = await setup({ capability: "undeclared" });
  const caps = await tool("plasmic_get_capabilities").handler({ projectId: "queries" }) as {
    versionStatus: string; dataQueries: { supported: boolean; documentedApi: boolean; reason: string; queryTypes: string[] };
  };
  assert.equal(caps.versionStatus, "VERIFIED");
  assert.equal(caps.dataQueries.supported, false);
  assert.equal(caps.dataQueries.documentedApi, false);
  assert.match(caps.dataQueries.reason, /NO_DATA_QUERY_CAPABILITY_DECLARED/);
  assert.deepEqual(caps.dataQueries.queryTypes, ["DataSource"], "observation is still reported honestly");
});

test("capabilities: no WAB URL configured is reported, not guessed", async () => {
  const { tool } = await setup({ capability: "none" });
  const caps = await tool("plasmic_get_capabilities").handler({}) as {
    versionStatus: string; wab: { host: string | null; probes: Array<{ error?: string }> };
    dataQueries: { supported: boolean; reason: string };
  };
  assert.equal(caps.versionStatus, "UNVERIFIED");
  assert.equal(caps.wab.host, null);
  assert.equal(caps.wab.probes[0]!.error, "WAB_BASE_URL_NOT_CONFIGURED");
  assert.equal(caps.dataQueries.supported, false);
  assert.match(caps.dataQueries.reason, /WAB_BASE_URL_NOT_CONFIGURED/);
});

test("capabilities: a revision without any query model reports the observed schema", async () => {
  const { tool } = await setup({ capability: "declared" });
  const caps = await tool("plasmic_get_capabilities").handler({ projectId: "plain" }) as {
    dataQueries: { supported: boolean; reason: string; queryTypes: string[]; observedEntryTypes: string[] };
  };
  assert.equal(caps.dataQueries.supported, false);
  assert.match(caps.dataQueries.reason, /NO_QUERY_MODEL_IN_REVISION/);
  assert.deepEqual(caps.dataQueries.queryTypes, []);
  assert.ok(caps.dataQueries.observedEntryTypes.includes("Component:1"));
});

test("list/get: queries are readable and header values never leak", async () => {
  const { tool } = await setup({ capability: "declared" });
  const listed = await tool("plasmic_list_data_queries").handler({ projectId: "queries" }) as {
    revision: number; supported: boolean; total: number;
    queries: Array<{ id: string; type: string; url: string; headerNames: string[]; variableName: string }>;
  };
  assert.equal(listed.total, 1);
  assert.equal(listed.supported, true);
  assert.equal(listed.queries[0]!.id, "dsTasks");
  assert.deepEqual(listed.queries[0]!.headerNames, ["apikey"]);
  assert.equal(listed.queries[0]!.variableName, "tasks");
  assert.equal(JSON.stringify(listed).includes(SECRET), false, "header values must never be returned");

  const one = await tool("plasmic_get_data_query").handler({ projectId: "queries", queryId: "dsTasks" }) as {
    query: { fields: string[] };
  };
  assert.ok(one.query.fields.includes("url"));
  assert.equal(JSON.stringify(one).includes(SECRET), false);

  await assert.rejects(
    tool("plasmic_get_data_query").handler({ projectId: "queries", queryId: "card" }),
    /DATA_QUERY_NOT_FOUND/,
    "a non-query entry is not a data query",
  );
});

test("writes are refused while the capability is unverified and nothing reaches WAB", async () => {
  const { tool, revisionNow, mutationCount } = await setup({ capability: "undeclared" });
  const before = revisionNow();
  await withAllowlist("supabase.example.pl", async () => {
    await assert.rejects(
      tool("plasmic_create_data_query").handler({
        projectId: "queries", url: "https://supabase.example.pl/rest/v1/tasks", dryRun: false, idempotencyKey: "dq-1",
      }),
      /DATA_QUERY_API_UNSUPPORTED/,
    );
    await assert.rejects(
      tool("plasmic_update_data_query").handler({
        projectId: "queries", queryId: "dsTasks", patch: { url: "https://supabase.example.pl/rest/v1/other" }, dryRun: false, idempotencyKey: "dq-2",
      }),
      /DATA_QUERY_API_UNSUPPORTED/,
    );
    await assert.rejects(
      tool("plasmic_delete_data_query").handler({
        projectId: "queries", queryId: "dsTasks", force: true, dryRun: false, idempotencyKey: "dq-3",
      }),
      /DATA_QUERY_API_UNSUPPORTED/,
    );
    await assert.rejects(
      tool("plasmic_bind_data_query").handler({
        projectId: "queries", queryId: "dsTasks", elementId: "viewTag", propName: "items", dryRun: false, idempotencyKey: "dq-4",
      }),
      /DATA_QUERY_API_UNSUPPORTED/,
    );
  });
  assert.equal(revisionNow(), before);
  assert.equal(mutationCount(), 0);
});

test("create: dry-run is the default, live write copies the observed query schema", async () => {
  const { tool, mapNow, revisionNow } = await setup({ capability: "declared" });
  await withAllowlist("supabase.example.pl", async () => {
    const planned = await tool("plasmic_create_data_query").handler({
      projectId: "queries", name: "sessions",
      url: "https://supabase.example.pl/rest/v1/sessions?select=*",
      method: "GET",
    }) as { dryRun: boolean; id: string };
    assert.equal(planned.dryRun, true);
    assert.equal(revisionNow(), 9, "dry run must not write");
    assert.equal(mapNow()[planned.id], undefined);

    const live = await tool("plasmic_create_data_query").handler({
      projectId: "queries", name: "sessions",
      url: "https://supabase.example.pl/rest/v1/sessions?select=*",
      method: "GET", dryRun: false, idempotencyKey: "create-sessions-1",
    }) as { id: string; deduped: boolean; revision: number };
    assert.equal(live.deduped, false);
    const created = mapNow()[live.id]!;
    assert.equal(created.__type, "DataSource");
    assert.equal(created.url, "https://supabase.example.pl/rest/v1/sessions?select=*");
    assert.equal(created.name, "sessions");
    // No invented fields: the created entry exposes exactly the template keys.
    assert.deepEqual(Object.keys(created).sort(), Object.keys(mapNow().dsTasks!).sort());

    const replay = await tool("plasmic_create_data_query").handler({
      projectId: "queries", name: "sessions",
      url: "https://supabase.example.pl/rest/v1/sessions?select=*",
      method: "GET", dryRun: false, idempotencyKey: "create-sessions-1",
    }) as { deduped: boolean };
    assert.equal(replay.deduped, true);
    assert.equal(revisionNow(), 10, "replay is a no-op");

    await assert.rejects(
      tool("plasmic_create_data_query").handler({
        projectId: "queries", url: "https://supabase.example.pl/rest/v1/x", params: { a: 1 },
      }),
      /QUERY_FIELD_UNSUPPORTED "params"/,
      "a field the template does not expose is refused rather than invented",
    );
    await assert.rejects(
      tool("plasmic_create_data_query").handler({
        projectId: "queries", url: "https://supabase.example.pl/rest/v1/x", templateId: "card",
      }),
      /NO_QUERY_TEMPLATE/,
    );
  });
});

test("create/update: privileged keys, connection strings and non-allowlisted hosts are refused", async () => {
  const { tool, revisionNow } = await setup({ capability: "declared" });
  await withAllowlist("supabase.example.pl", async () => {
    const cases: Array<[Record<string, unknown>, RegExp]> = [
      [{ url: "https://supabase.example.pl/rest/v1/x?apikey=service_role" }, /UNSAFE_DATA_QUERY_URL/],
      [{ url: "postgresql://user:pw@db.example.pl:5432/postgres" }, /UNSAFE_DATA_QUERY_URL/],
      [{ url: "http://supabase.example.pl/rest/v1/x" }, /only https/],
      [{ url: "https://evil.example.com/rest/v1/x" }, /DATA_QUERY_HOST_NOT_ALLOWLISTED/],
      [{ url: "https://supabase.example.pl/rest/v1/x", headers: { Authorization: "Bearer service_role" } }, /UNSAFE_DATA_QUERY_HEADER/],
    ];
    for (const [args, pattern] of cases) {
      // eslint-disable-next-line no-await-in-loop
      await assert.rejects(
        tool("plasmic_create_data_query").handler({ projectId: "queries", ...args }),
        pattern,
        JSON.stringify(args),
      );
    }
    await assert.rejects(
      tool("plasmic_update_data_query").handler({
        projectId: "queries", queryId: "dsTasks", patch: { url: "postgres://db/x" },
      }),
      /UNSAFE_DATA_QUERY_URL/,
    );
    await assert.rejects(
      tool("plasmic_update_data_query").handler({
        projectId: "queries", queryId: "dsTasks", patch: { notAQueryField: 1 },
      }),
      /QUERY_FIELD_UNSUPPORTED/,
    );
  });
  assert.equal(revisionNow(), 9);
});

test("update: a stale revision conflict is surfaced, never reported as success", async () => {
  const { tool, mapNow, revisionNow } = await setup({ capability: "declared", failingWrite: true });
  await withAllowlist("supabase.example.pl", async () => {
    await assert.rejects(
      tool("plasmic_update_data_query").handler({
        projectId: "queries", queryId: "dsTasks",
        patch: { url: "https://supabase.example.pl/rest/v1/tasks?select=id" },
        dryRun: false, idempotencyKey: "update-stale-1",
      }),
      /revision conflict/,
    );
  });
  assert.equal(revisionNow(), 9);
  assert.equal(mapNow().dsTasks!.url, "https://supabase.example.pl/rest/v1/tasks?select=*");
});

test("delete: in-use queries need force, and dry-run deletes nothing", async () => {
  const { tool, mapNow, revisionNow } = await setup({ capability: "declared" });
  await withAllowlist("supabase.example.pl", async () => {
    await assert.rejects(
      tool("plasmic_delete_data_query").handler({ projectId: "queries", queryId: "dsTasks", dryRun: false, idempotencyKey: "del-1" }),
      /DATA_QUERY_IN_USE/,
      "an entry still referencing the query blocks the delete",
    );
    const planned = await tool("plasmic_delete_data_query").handler({ projectId: "queries", queryId: "dsTasks", force: true }) as {
      dryRun: boolean; changed: string[];
    };
    assert.equal(planned.dryRun, true);
    assert.equal(revisionNow(), 9);
    assert.ok(mapNow().dsTasks);
    const live = await tool("plasmic_delete_data_query").handler({
      projectId: "queries", queryId: "dsTasks", force: true, dryRun: false, idempotencyKey: "del-2",
    }) as { revision: number };
    assert.equal(live.revision, 10);
    assert.equal(mapNow().dsTasks, undefined);
  });
});

test("bind: repoints an existing $q dynamic value and refuses to invent a binding", async () => {
  const { tool, mapNow } = await setup({ capability: "declared" });
  await withAllowlist("supabase.example.pl", async () => {
    // An element with no dynamic-value field cannot be given one by the adapter.
    await assert.rejects(
      tool("plasmic_bind_data_query").handler({ projectId: "queries", queryId: "dsTasks", elementId: "plainTag", propName: "items" }),
      /DYNAMIC_VALUE_BINDING_FIELD_UNKNOWN/,
    );
    // Create a second query with a different variable, then rebind viewTag to it.
    const created = await tool("plasmic_create_data_query").handler({
      projectId: "queries", name: "sessions", url: "https://supabase.example.pl/rest/v1/sessions",
      dryRun: false, idempotencyKey: "bind-setup-1",
    }) as { id: string };
    // The template carries variableName "tasks"; give the new query its own.
    mapNow()[created.id]!.variableName = "sessions";
    const bound = await tool("plasmic_bind_data_query").handler({
      projectId: "queries", queryId: created.id, elementId: "viewTag", propName: "items",
      dryRun: false, idempotencyKey: "bind-1",
    }) as { changed: string[] };
    const element = mapNow().viewTag!;
    const newExprId = (element.dynamicValueBinding as { __ref: string }).__ref;
    assert.notEqual(newExprId, "exprTasks");
    assert.ok(bound.changed.includes(newExprId));
    assert.equal((mapNow()[newExprId] as { code: string }).code, "$q.sessions");
    assert.equal((mapNow().exprTasks as { code: string }).code, "$q.tasks", "the previous expression is untouched");
    assert.deepEqual(element.vsettings, [{ __ref: "cardVs" }], "unrelated element fields are preserved");
  });
});


test("idempotent data-query writes are branch-scoped with independent readback", async () => {
  const { tool, mapNow, revisionNow, mutationCount } = await setup({ capability: "declared" });
  const create = tool("plasmic_create_data_query");
  const update = tool("plasmic_update_data_query");
  const sameInput = {
    projectId: "queries", name: "crossBranch",
    url: "https://supabase.example.pl/rest/v1/cross-branch?select=*",
    dryRun: false, idempotencyKey: "dataquery-branch-scope-1",
  };
  await withAllowlist("supabase.example.pl", async () => {
    const first = await create.handler({ ...sameInput, branchId: "branch-a" }) as {
      id: string; deduped: boolean; revision: number;
    };
    assert.equal(first.deduped, false);
    assert.equal(first.revision, 10);
    assert.ok(mapNow("queries", "branch-a")[first.id]);
    assert.equal(revisionNow("queries", "branch-b"), 9);

    const second = await create.handler({ ...sameInput, branchId: "branch-b" }) as {
      id: string; deduped: boolean; revision: number;
    };
    assert.equal(second.deduped, false, "same key on another branch must execute");
    assert.equal(second.revision, 10);
    assert.notEqual(first.id, second.id, "deterministic ids must include branch identity");
    assert.ok(mapNow("queries", "branch-b")[second.id]);
    assert.equal(mapNow("queries", "branch-a")[second.id], undefined);
    assert.equal(mapNow("queries", "branch-b")[first.id], undefined);
    assert.equal(mutationCount(), 2);

    const replay = await create.handler({ ...sameInput, branchId: "branch-a" }) as { deduped: boolean };
    assert.equal(replay.deduped, true, "same-branch replay must be idempotent");
    assert.equal(mutationCount(), 2);

    const updateInput = {
      projectId: "queries", queryId: "dsTasks",
      patch: { url: "https://supabase.example.pl/rest/v1/tasks?select=id" },
      dryRun: false, idempotencyKey: "dataquery-branch-update-1",
    };
    const updatedA = await update.handler({ ...updateInput, branchId: "branch-a" }) as {
      deduped: boolean; revision: number;
    };
    assert.equal(updatedA.deduped, false);
    assert.equal(updatedA.revision, 11);
    assert.equal(mapNow("queries", "branch-b").dsTasks!.url, "https://supabase.example.pl/rest/v1/tasks?select=*");

    const updatedB = await update.handler({ ...updateInput, branchId: "branch-b" }) as {
      deduped: boolean; revision: number;
    };
    assert.equal(updatedB.deduped, false);
    assert.equal(updatedB.revision, 11);
    assert.equal(mapNow("queries", "branch-a").dsTasks!.url, updateInput.patch.url);
    assert.equal(mapNow("queries", "branch-b").dsTasks!.url, updateInput.patch.url);
    assert.equal(mutationCount(), 4);
    const replayUpdate = await update.handler({ ...updateInput, branchId: "branch-b" }) as { deduped: boolean };
    assert.equal(replayUpdate.deduped, true);
    assert.equal(mutationCount(), 4);
    assert.equal(revisionNow("queries"), 9, "default branch stays unchanged");
  });
});

test("live stdio server exposes the data-query tools and reports UNVERIFIED without a WAB", async () => {
  const { spawn } = await import("node:child_process");
  const { dirname } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const repo = join(dirname(fileURLToPath(import.meta.url)), "..");
  const stateDir = await mkdtemp(join(tmpdir(), "zari229-dq-stdio-"));
  const proc = spawn(process.execPath, [join(repo, "services/plasmic-mcp/server.ts")], {
    cwd: repo,
    env: {
      ...process.env, PLASMIC_BASE_URL: "http://127.0.0.1:9", PLASMIC_STATE_DIR: stateDir,
      PLASMIC_AUDIT_FILE: join(stateDir, "audit.jsonl"), MCP_HTTP_PORT: "",
      PLASMIC_EMAIL: "", PLASMIC_PASSWORD: "", PLASMIC_TEAM_TOKEN: "", MCP_AUTH_TOKEN: "", MCP_AUTH_TOKENS: "",
    },
    stdio: ["pipe", "pipe", "pipe"],
  });
  const pending = new Map<number, (value: { result?: Record<string, unknown>; error?: { message?: string } }) => void>();
  let buffer = "";
  proc.stdout.setEncoding("utf8");
  proc.stdout.on("data", (chunk: string) => {
    buffer += chunk;
    let idx: number;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      try {
        const msg = JSON.parse(line) as { id?: number };
        const resolve = msg.id !== undefined ? pending.get(msg.id) : undefined;
        if (resolve && msg.id !== undefined) { pending.delete(msg.id); resolve(msg as never); }
      } catch { /* server logs on stdout */ }
    }
  });
  let nextId = 1;
  const rpc = (method: string, params: unknown) => new Promise<{ result?: Record<string, unknown>; error?: { message?: string } }>((resolve, reject) => {
    const id = nextId++;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`timeout ${method}`)); }, 20000);
    pending.set(id, (value) => { clearTimeout(timer); resolve(value); });
    proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
  });
  try {
    await rpc("initialize", { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "zari-229-dq", version: "1" } });
    proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");
    const list = await rpc("tools/list", {}) as { result: { tools: Array<{ name: string }> } };
    const names = list.result.tools.map((t) => t.name);
    for (const name of [
      "plasmic_get_capabilities", "plasmic_list_data_queries", "plasmic_get_data_query",
      "plasmic_create_data_query", "plasmic_update_data_query", "plasmic_delete_data_query",
      "plasmic_bind_data_query",
    ]) {
      assert.ok(names.includes(name), `missing ${name}`);
    }
    assert.equal(names.length, 42); // ZARI-260: five Data Token actions added to ZARI-229 catalog
    const caps = await rpc("tools/call", { name: "plasmic_get_capabilities", arguments: {} }) as {
      result?: { isError?: boolean; content?: Array<{ text?: string }> };
    };
    const payload = JSON.parse(caps.result?.content?.[0]?.text ?? "{}") as {
      ok: boolean; versionStatus: string; dataQueries: { supported: boolean; reason: string };
    };
    assert.equal(payload.ok, true);
    assert.equal(payload.versionStatus, "UNVERIFIED");
    assert.equal(payload.dataQueries.supported, false);
    assert.match(payload.dataQueries.reason, /WAB_HEALTHCHECK_UNREACHABLE/);
  } finally {
    proc.kill();
  }
});
