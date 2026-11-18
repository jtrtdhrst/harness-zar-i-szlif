/**
 * DOD-08: HTTP (Fetch) data queries through MCP only.
 *
 * Honest capability model:
 *   - The adapter never assumes that a self-hosted WAB build supports HTTP data
 *     queries. Support must be declared by the server itself (capability
 *     feature on /healthcheck) AND the live revision must show a query model
 *     that the adapter can copy structurally.
 *   - When either precondition is missing, every write is refused with a named
 *     DATA_QUERY_API_UNSUPPORTED reason and the exact observation that failed.
 *     No undocumented bundle shape is ever created to manufacture a PASS.
 *   - Query entries are never authored from scratch: create copies the
 *     structure of an existing query in the same revision and only overwrites
 *     fields the template already exposes.
 *
 * Secret boundary: request headers are accepted for writes but are never
 * returned; reads report header names only. `service_role`, database
 * connection strings and non-allowlisted hosts are rejected outright.
 */
import { z } from "zod";
import { idempotent } from "@design-stack/contracts/idempotency";
import { sha256 } from "@design-stack/contracts/sync";
import type { ToolDef } from "@design-stack/mcp-server";
import type { BundleDoc } from "@design-stack/plasmic-client";
import { writeOp, type PlasmicCtx, type WabProbeResult } from "./tools.ts";

type Entry = Record<string, unknown>;
type EntryMap = Record<string, Entry>;

/** Entry types that carry a data query/HTTP fetch definition. */
const QUERY_TYPE_PATTERN = /(data[-_]?(source|query)|http[-_]?fetch|fetch[-_]?query)/i;
/** Feature declarations a WAB build must publish before writes are allowed. */
const CAPABILITY_FEATURE_PATTERN = /(data[-_ ]?quer|http[-_ ]?fetch)/i;

const MAX_TYPES = 40;

const isObj = (v: unknown): v is Entry => !!v && typeof v === "object" && !Array.isArray(v);
const refId = (v: unknown): string | undefined =>
  isObj(v) && typeof v.__ref === "string" ? v.__ref : undefined;
const typeOf = (v: unknown): string => (isObj(v) ? String(v.__type ?? "") : "");

export interface CapabilityVerdict {
  versionStatus: "VERIFIED" | "UNVERIFIED";
  wab: {
    host: string | null;
    version: string | null;
    declaredFeatures: string[];
    probes: Array<{ path: string; status?: number; error?: string }>;
  };
  dataQueries: {
    supported: boolean;
    documentedApi: boolean;
    reason: string;
    queryTypes: string[];
    observedEntryTypes: string[];
    modelVersion: number | null;
    hostlessDataVersion: number | null;
  };
}

function hostOf(url: string | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function pickVersion(json: unknown): { version: string | null; features: string[] } {
  if (!isObj(json)) return { version: null, features: [] };
  for (const key of ["version", "wabVersion", "build", "gitSha", "revision"]) {
    const value = json[key];
    if (typeof value === "string" && value.trim()) {
      return { version: value.trim(), features: declaredFeatures(json) };
    }
  }
  return { version: null, features: declaredFeatures(json) };
}

function declaredFeatures(json: unknown): string[] {
  if (!isObj(json)) return [];
  const direct = [...stringArray(json.features), ...stringArray(json.capabilities)];
  if (isObj(json.dataQueries) && json.dataQueries.enabled === true) direct.push("dataQueries.enabled");
  return direct;
}

async function defaultProbe(baseUrl: string, path: string): Promise<WabProbeResult> {
  try {
    const res = await fetch(`${baseUrl}${path}`, { method: "GET" });
    const text = await res.text();
    let json: unknown;
    try {
      json = JSON.parse(text);
    } catch {
      json = undefined;
    }
    return { status: res.status, ...(json !== undefined ? { json } : {}) };
  } catch (err) {
    return { error: String(err instanceof Error ? err.message : err).slice(0, 200) };
  }
}

function entryTypeHistogram(map: EntryMap): string[] {
  const counts = new Map<string, number>();
  for (const entry of Object.values(map)) {
    const type = typeOf(entry);
    if (!type) continue;
    counts.set(type, (counts.get(type) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, MAX_TYPES)
    .map(([type, count]) => `${type}:${count}`);
}

export function queryEntries(map: EntryMap): Array<{ iid: string; entry: Entry }> {
  return Object.entries(map)
    .filter(([, entry]) => QUERY_TYPE_PATTERN.test(typeOf(entry)))
    .map(([iid, entry]) => ({ iid, entry }));
}

/**
 * Read-only capability verdict. Never cached: an upgrade of the deployed WAB
 * build must be able to enable the write path without a code change.
 */
export async function probeCapabilities(
  ctx: PlasmicCtx,
  model?: { projectId: string; branchId?: string },
): Promise<CapabilityVerdict> {
  const probes: CapabilityVerdict["wab"]["probes"] = [];
  let version: string | null = null;
  let features: string[] = [];
  let healthOk = false;

  if (!ctx.probeWab && !ctx.wabBaseUrl) {
    probes.push({ path: "/healthcheck", error: "WAB_BASE_URL_NOT_CONFIGURED" });
  } else {
    const probe = ctx.probeWab ?? ((path: string) => defaultProbe(ctx.wabBaseUrl as string, path));
    const result = await probe("/healthcheck");
    probes.push({ path: "/healthcheck", ...(result.status !== undefined ? { status: result.status } : {}), ...(result.error ? { error: result.error } : {}) });
    healthOk = result.status === 200;
    const picked = pickVersion(result.json);
    version = picked.version;
    features = picked.features;
  }

  let queryTypes: string[] = [];
  let observedEntryTypes: string[] = [];
  let modelVersion: number | null = null;
  let hostlessDataVersion: number | null = null;
  let revisionError: string | undefined;

  if (model) {
    try {
      const rev = await ctx.client.getProjectRev(model.projectId, model.branchId);
      const map = rev.bundle.map as EntryMap;
      queryTypes = [...new Set(queryEntries(map).map(({ entry }) => typeOf(entry)))].sort();
      observedEntryTypes = entryTypeHistogram(map);
      modelVersion = rev.modelVersion ?? null;
      hostlessDataVersion = rev.hostlessDataVersion ?? null;
    } catch (err) {
      revisionError = String(err instanceof Error ? err.message : err).slice(0, 200);
    }
  }

  const documentedApi = features.some((feature) => CAPABILITY_FEATURE_PATTERN.test(feature));
  const reasons: string[] = [];
  if (!healthOk) {
    const failed = probes[probes.length - 1];
    reasons.push(
      `WAB_HEALTHCHECK_UNREACHABLE: ${failed?.error ?? `status ${failed?.status ?? "unknown"}`}`,
    );
  } else if (!documentedApi) {
    reasons.push(
      `NO_DATA_QUERY_CAPABILITY_DECLARED: /healthcheck does not publish an HTTP/data-query capability (declared features: ${features.join(", ") || "none"})`,
    );
  }
  if (!model) reasons.push("REVISION_MODEL_NOT_PROVIDED");
  if (revisionError) reasons.push(`REVISION_READ_FAILED: ${revisionError}`);
  if (model && !revisionError && queryTypes.length === 0) {
    reasons.push(
      `NO_QUERY_MODEL_IN_REVISION: no entry type matches a data query/HTTP fetch model (observed types: ${observedEntryTypes.slice(0, 12).join(", ") || "none"})`,
    );
  }

  const supported = documentedApi && queryTypes.length > 0;
  return {
    versionStatus: version ? "VERIFIED" : "UNVERIFIED",
    wab: {
      host: hostOf(ctx.wabBaseUrl),
      version,
      declaredFeatures: features,
      probes,
    },
    dataQueries: {
      supported,
      documentedApi,
      reason: supported
        ? `HTTP data queries declared by the server and present in the revision (${queryTypes.join(", ")})`
        : reasons.join(" | ") || "UNVERIFIED",
      queryTypes,
      observedEntryTypes,
      modelVersion,
      hostlessDataVersion,
    },
  };
}

function requireSupported(verdict: CapabilityVerdict, operation: string): void {
  if (!verdict.dataQueries.supported) {
    throw new Error(
      `DATA_QUERY_API_UNSUPPORTED (${operation}): ${verdict.dataQueries.reason}. ` +
      `WAB version: ${verdict.wab.version ?? "UNVERIFIED"}. No bundle shape is injected to fake support.`,
    );
  }
}

const SECRET_TOKENS = /service_role|postgres(ql)?:\/\/|password=|secret=|bearer\s+[A-Za-z0-9._-]{8,}/i;

export function assertSafeHttpFetchTarget(url: string): URL {
  if (SECRET_TOKENS.test(url)) {
    throw new Error("UNSAFE_DATA_QUERY_URL: a connection string, service_role key or inline secret is not allowed in a client HTTP query");
  }
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("INVALID_DATA_QUERY_URL");
  }
  if (parsed.protocol !== "https:") {
    throw new Error("UNSAFE_DATA_QUERY_URL: only https endpoints are allowed");
  }
  const allowed = (process.env.PLASMIC_DATA_QUERY_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
  if (allowed.length === 0) {
    throw new Error(
      "DATA_QUERY_HOST_NOT_ALLOWLISTED: set PLASMIC_DATA_QUERY_ALLOWED_HOSTS to the verified self-hosted REST hosts",
    );
  }
  if (!allowed.includes(parsed.host.toLowerCase())) {
    throw new Error(`DATA_QUERY_HOST_NOT_ALLOWLISTED: ${parsed.host}`);
  }
  return parsed;
}

function assertSafeHeaders(headers: Record<string, string> | undefined): void {
  if (!headers) return;
  for (const [name, value] of Object.entries(headers)) {
    if (SECRET_TOKENS.test(value)) {
      throw new Error(`UNSAFE_DATA_QUERY_HEADER "${name}": privileged key or connection string is not allowed`);
    }
  }
}

/** Field names the adapter is willing to overwrite on a query entry. */
const WRITABLE_FIELDS = new Set(["url", "method", "headers", "params", "name", "body"]);

function summarizeQuery(iid: string, entry: Entry) {
  const headers = isObj(entry.headers) ? Object.keys(entry.headers) : [];
  return {
    id: iid,
    type: typeOf(entry),
    name: typeof entry.name === "string" ? entry.name : null,
    url: typeof entry.url === "string" ? entry.url : null,
    method: typeof entry.method === "string" ? entry.method : null,
    variableName:
      typeof entry.variableName === "string"
        ? entry.variableName
        : typeof entry.variable === "string" ? entry.variable : null,
    headerNames: headers,
    fields: Object.keys(entry).sort(),
  };
}

export function plasmicDataQueryTools(ctx: PlasmicCtx): ToolDef[] {
  const c = ctx.client;
  const write = async (
    tool: string, projectId: string, branchId: string | undefined, target: string,
    payload: unknown, idem: string | undefined, preview: boolean,
    perform: () => Promise<{ revision: number; dryRun: boolean; changed: string[] }>,
  ) => {
    const branch = branchId ?? "main";
    const inputHash = sha256(JSON.stringify({ tool, projectId, branch, target, payload }));
    const op = () => writeOp(ctx, tool, projectId, target, JSON.stringify({ tool, branch, target, inputHash }), perform);
    if (preview) return { ...(await op()), deduped: false };
    const cacheKey = ["live", tool, projectId, branch, idem].join(":");
    const value = await idempotent(ctx.stateDir + "/idempotency", cacheKey, async () => ({ inputHash, effect: await op() }));
    if (value.result.inputHash !== inputHash) {
      throw new Error("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_INPUT");
    }
    return { ...value.result.effect, deduped: value.deduped };
  };

  return [
    {
      name: "plasmic_get_capabilities",
      annotations: { readOnlyHint: true },
      description:
        "Read-only capability report for this adapter: configured WAB host, build/version as published by the server, declared capability features, and whether the live revision exposes an HTTP data-query model. Reports UNVERIFIED instead of inventing support.",
      schema: {
        projectId: z.string().min(1).optional(),
        branchId: z.string().optional(),
      },
      handler: async (a) => {
        const projectId = a.projectId as string | undefined;
        return probeCapabilities(ctx, projectId ? { projectId, branchId: a.branchId as string | undefined } : undefined);
      },
    },
    {
      name: "plasmic_list_data_queries",
      annotations: { readOnlyHint: true },
      description:
        "List data queries (HTTP Fetch) present in one project branch revision. Reports an empty list plus the capability reason when the revision exposes no supported query model; header values are never returned.",
      schema: {
        projectId: z.string().min(1),
        branchId: z.string().optional(),
      },
      handler: async (a) => {
        const projectId = a.projectId as string;
        const branchId = a.branchId as string | undefined;
        const verdict = await probeCapabilities(ctx, { projectId, branchId });
        const rev = await c.getProjectRev(projectId, branchId);
        const queries = queryEntries(rev.bundle.map as EntryMap).map(({ iid, entry }) => summarizeQuery(iid, entry));
        return {
          revision: rev.revision,
          supported: verdict.dataQueries.supported,
          capabilityReason: verdict.dataQueries.reason,
          queryTypes: verdict.dataQueries.queryTypes,
          total: queries.length,
          queries,
        };
      },
    },
    {
      name: "plasmic_get_data_query",
      annotations: { readOnlyHint: true },
      description:
        "Read one data query by id from the live revision: url, method, header names, declared fields and bound variable name. Header values and secrets are never returned.",
      schema: {
        projectId: z.string().min(1),
        queryId: z.string().min(1),
        branchId: z.string().optional(),
      },
      handler: async (a) => {
        const rev = await c.getProjectRev(a.projectId as string, a.branchId as string | undefined);
        const map = rev.bundle.map as EntryMap;
        const entry = map[a.queryId as string];
        if (!entry || !QUERY_TYPE_PATTERN.test(typeOf(entry))) {
          throw new Error(`DATA_QUERY_NOT_FOUND "${a.queryId}" — list ids with plasmic_list_data_queries`);
        }
        return { revision: rev.revision, query: summarizeQuery(a.queryId as string, entry) };
      },
    },
    {
      name: "plasmic_create_data_query",
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
      description:
        "Create an HTTP Fetch data query by copying the structure of an existing query in the same revision (dryRun default). Refused with DATA_QUERY_API_UNSUPPORTED unless the deployed WAB declares data-query capability and the revision exposes that model; no shape is invented.",
      schema: {
        projectId: z.string().min(1),
        branchId: z.string().optional(),
        name: z.string().min(1).max(120).optional(),
        url: z.string().min(1).max(2000),
        method: z.enum(["GET", "POST"]).optional(),
        headers: z.record(z.string(), z.string()).optional(),
        params: z.record(z.string(), z.unknown()).optional(),
        templateId: z.string().optional().describe("Existing query entry to copy the schema from"),
        dryRun: z.boolean().optional(),
        idempotencyKey: z.string().min(8).max(120).optional(),
      },
      handler: async (a) => {
        const projectId = a.projectId as string;
        const branchId = a.branchId as string | undefined;
        const preview = a.dryRun !== false;
        if (!preview && !a.idempotencyKey) throw new Error("IDEMPOTENCY_KEY_REQUIRED");
        assertSafeHttpFetchTarget(a.url as string);
        assertSafeHeaders(a.headers as Record<string, string> | undefined);
        const verdict = await probeCapabilities(ctx, { projectId, branchId });
        requireSupported(verdict, "plasmic_create_data_query");
        const seed = `dataquery:${projectId}@${branchId ?? "main"}:${a.idempotencyKey ?? sha256(JSON.stringify(a))}`;
        const newId = `mcpdq${sha256(seed).slice(0, 14)}`;
        return write("plasmic_create_data_query", projectId, branchId, a.url as string, a, a.idempotencyKey as string | undefined, preview,
          async () => {
            const out = await c.mutate(projectId, branchId, (bundle: BundleDoc) => {
              const map = bundle.map as EntryMap;
              const templates = queryEntries(map);
              const template = a.templateId
                ? templates.find(({ iid }) => iid === a.templateId)
                : templates[0];
              if (!template) {
                throw new Error(
                  "NO_QUERY_TEMPLATE: this revision has no existing data query to copy a schema from; create the first one in Studio and re-run",
                );
              }
              if (map[newId]) return null; // deterministic id: replay is a no-op
              const fields = Object.keys(template.entry);
              for (const key of Object.keys({ name: a.name, url: a.url, method: a.method, headers: a.headers, params: a.params })) {
                if ((a as Record<string, unknown>)[key] === undefined) continue;
                if (!fields.includes(key)) {
                  throw new Error(
                    `QUERY_FIELD_UNSUPPORTED "${key}": template ${template.iid} (${typeOf(template.entry)}) exposes only ${fields.join(", ")}`,
                  );
                }
              }
              const created: Entry = { ...template.entry };
              // Only overwrite fields the template already exposes.
              if (typeof created.uuid === "string") created.uuid = `${newId}-uuid`;
              if (a.name !== undefined) created.name = a.name;
              created.url = a.url;
              if (a.method !== undefined) created.method = a.method;
              if (a.headers !== undefined) created.headers = a.headers;
              if (a.params !== undefined) created.params = a.params;
              return { map: { [newId]: created } };
            }, { dryRun: preview, saveMode: "full" });
            return { ...out, id: newId, capability: verdict.dataQueries.reason };
          });
      },
    },
    {
      name: "plasmic_update_data_query",
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true },
      description:
        "Update an existing HTTP Fetch data query field-by-field in one revision-safe mutation (dryRun default). Only fields the entry already exposes can be written; values are re-read and revision-checked before the write.",
      schema: {
        projectId: z.string().min(1),
        queryId: z.string().min(1),
        branchId: z.string().optional(),
        patch: z.record(z.string(), z.unknown()),
        dryRun: z.boolean().optional(),
        idempotencyKey: z.string().min(8).max(120).optional(),
      },
      handler: async (a) => {
        const projectId = a.projectId as string;
        const branchId = a.branchId as string | undefined;
        const preview = a.dryRun !== false;
        if (!preview && !a.idempotencyKey) throw new Error("IDEMPOTENCY_KEY_REQUIRED");
        const patch = a.patch as Record<string, unknown>;
        for (const key of Object.keys(patch)) {
          if (!WRITABLE_FIELDS.has(key)) throw new Error(`QUERY_FIELD_UNSUPPORTED "${key}"`);
        }
        if (typeof patch.url === "string") assertSafeHttpFetchTarget(patch.url);
        if (isObj(patch.headers)) assertSafeHeaders(patch.headers as Record<string, string>);
        const verdict = await probeCapabilities(ctx, { projectId, branchId });
        requireSupported(verdict, "plasmic_update_data_query");
        return write("plasmic_update_data_query", projectId, branchId, a.queryId as string, patch, a.idempotencyKey as string | undefined, preview,
          async () => {
            const out = await c.mutate(projectId, branchId, (bundle: BundleDoc) => {
              const map = bundle.map as EntryMap;
              const entry = map[a.queryId as string];
              if (!entry || !QUERY_TYPE_PATTERN.test(typeOf(entry))) {
                throw new Error(`DATA_QUERY_NOT_FOUND "${a.queryId}"`);
              }
              for (const key of Object.keys(patch)) {
                if (!(key in entry)) {
                  throw new Error(
                    `QUERY_FIELD_UNSUPPORTED "${key}": ${a.queryId} (${typeOf(entry)}) exposes only ${Object.keys(entry).sort().join(", ")}`,
                  );
                }
              }
              return { map: { [a.queryId as string]: { ...entry, ...patch } } };
            }, { dryRun: preview });
            return { ...out, id: a.queryId, capability: verdict.dataQueries.reason };
          });
      },
    },
    {
      name: "plasmic_delete_data_query",
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false },
      description:
        "Delete a data query from the revision. Refuses while other entries still reference it unless force:true. dryRun default; test-only cleanup helper for disposable projects.",
      schema: {
        projectId: z.string().min(1),
        queryId: z.string().min(1),
        branchId: z.string().optional(),
        force: z.boolean().optional(),
        dryRun: z.boolean().optional(),
        idempotencyKey: z.string().min(8).max(120).optional(),
      },
      handler: async (a) => {
        const projectId = a.projectId as string;
        const branchId = a.branchId as string | undefined;
        const preview = a.dryRun !== false;
        if (!preview && !a.idempotencyKey) throw new Error("IDEMPOTENCY_KEY_REQUIRED");
        const verdict = await probeCapabilities(ctx, { projectId, branchId });
        requireSupported(verdict, "plasmic_delete_data_query");
        const queryId = a.queryId as string;
        return write("plasmic_delete_data_query", projectId, branchId, queryId, { force: !!a.force }, a.idempotencyKey as string | undefined, preview,
          async () => {
            const out = await c.mutate(projectId, branchId, (bundle: BundleDoc) => {
              const map = bundle.map as EntryMap;
              const entry = map[queryId];
              if (!entry || !QUERY_TYPE_PATTERN.test(typeOf(entry))) {
                throw new Error(`DATA_QUERY_NOT_FOUND "${queryId}"`);
              }
              // A query is in use when another entry references its id OR its
              // $q.<variableName> expression — the expression is the real usage.
              const variable = typeof entry.variableName === "string" ? entry.variableName : null;
              const variableRef = variable ? `$q.${variable}` : null;
              const referencedBy = Object.entries(map)
                .filter(([iid, other]) => {
                  if (iid === queryId) return false;
                  const text = JSON.stringify(other);
                  return text.includes(queryId) || (variableRef !== null && text.includes(variableRef));
                })
                .map(([iid]) => iid);
              if (referencedBy.length > 0 && !a.force) {
                throw new Error(`DATA_QUERY_IN_USE by ${referencedBy.join(", ")} — remove bindings first or pass force:true`);
              }
              return { toDeleteIids: [queryId] };
            }, { dryRun: preview });
            return { ...out, id: queryId, capability: verdict.dataQueries.reason };
          });
      },
    },
    {
      name: "plasmic_bind_data_query",
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
      description:
        "Bind a data query result to an element prop as a native $q.<name> dynamic expression, copying an existing dynamic-expression entry as the structural template. Fails closed when the revision exposes no such model.",
      schema: {
        projectId: z.string().min(1),
        branchId: z.string().optional(),
        queryId: z.string().min(1),
        elementId: z.string().min(1),
        propName: z.string().min(1).max(80),
        templateId: z.string().optional(),
        dryRun: z.boolean().optional(),
        idempotencyKey: z.string().min(8).max(120).optional(),
      },
      handler: async (a) => {
        const projectId = a.projectId as string;
        const branchId = a.branchId as string | undefined;
        const preview = a.dryRun !== false;
        if (!preview && !a.idempotencyKey) throw new Error("IDEMPOTENCY_KEY_REQUIRED");
        const verdict = await probeCapabilities(ctx, { projectId, branchId });
        requireSupported(verdict, "plasmic_bind_data_query");
        return write("plasmic_bind_data_query", projectId, branchId, a.elementId as string,
          { queryId: a.queryId, propName: a.propName }, a.idempotencyKey as string | undefined, preview,
          async () => {
            const out = await c.mutate(projectId, branchId, (bundle: BundleDoc) => {
              const map = bundle.map as EntryMap;
              const query = map[a.queryId as string];
              if (!query || !QUERY_TYPE_PATTERN.test(typeOf(query))) {
                throw new Error(`DATA_QUERY_NOT_FOUND "${a.queryId}"`);
              }
              const variable = typeof query.variableName === "string" ? query.variableName : null;
              if (!variable) {
                throw new Error(
                  `QUERY_VARIABLE_UNRESOLVED "${a.queryId}" (${typeOf(query)}) — the entry exposes no variable name for a $q.<name> reference`,
                );
              }
              // Rebinding only: the adapter never invents a dynamic-value field
              // or an expression shape. The element must already have a binding.
              const element = map[a.elementId as string];
              if (!element) throw new Error(`ELEMENT_NOT_FOUND "${a.elementId}"`);
              const bindingField = Object.keys(element).find(
                (key) => /(dyn(amic)?|dataval|binding|drvalue)/i.test(key) && !!refId(element[key]),
              );
              if (!bindingField) {
                throw new Error(
                  `DYNAMIC_VALUE_BINDING_FIELD_UNKNOWN: "${a.elementId}" (${typeOf(element)}) exposes no existing dynamic-value field (fields: ${Object.keys(element).sort().join(", ")}); create the first binding in Studio`,
                );
              }
              const currentExprId = refId(element[bindingField]);
              const templateId = (a.templateId as string | undefined) ?? currentExprId;
              const template = templateId ? map[templateId] : undefined;
              if (!template) throw new Error(`DYNAMIC_VALUE_TEMPLATE_NOT_FOUND "${templateId}"`);
              const templateText = JSON.stringify(template);
              const previousVariable = /\$q\.([A-Za-z0-9_]+)/.exec(templateText)?.[1];
              if (!previousVariable) {
                throw new Error(
                  `QUERY_REFERENCE_NOT_FOUND_IN_TEMPLATE "${templateId}" (${typeOf(template)}) — the template carries no $q.<name> expression to repoint`,
                );
              }
              if (previousVariable === variable) return null;
              const exprId = `mcpdv${sha256(`${projectId}@${branchId ?? "main"}:${a.queryId}:${previousVariable}:${templateId}`).slice(0, 14)}`;
              if (map[exprId]) return null;
              const clone = JSON.parse(
                templateText.replace(new RegExp(`\\$q\\.${previousVariable}(?![A-Za-z0-9_])`, "g"), `$q.${variable}`),
              ) as Entry;
              const patched: Entry = { ...clone, uuid: `${exprId}-uuid` };
              return {
                map: {
                  [exprId]: patched,
                  [a.elementId as string]: { ...element, [bindingField]: { __ref: exprId } },
                },
              };
            }, { dryRun: preview });
            return { ...out, capability: verdict.dataQueries.reason };
          });
      },
    },
  ];
}
