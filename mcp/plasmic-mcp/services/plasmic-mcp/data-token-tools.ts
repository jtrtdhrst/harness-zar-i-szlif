/** Native WAB DataToken operations. No Studio/WAB source modification or auto-publish. */
import { randomUUID } from "node:crypto";
import { z } from "zod";
import { idempotent } from "@design-stack/contracts/idempotency";
import { sha256 } from "@design-stack/contracts/sync";
import type { BundleDoc } from "@design-stack/plasmic-client";
import type { ToolDef } from "@design-stack/mcp-server";
import { writeOp, type PlasmicCtx } from "./tools.ts";

type Json = Record<string, unknown>;
type Kind = "text" | "number" | "code";
type Op = "create" | "update" | "delete";
type Args = {
  projectId: string;
  branchId?: string;
  tokenId?: string;
  name?: string;
  value?: string | number;
  valueType?: Kind;
  expectedRevision?: number;
  dryRun?: boolean;
  idempotencyKey?: string;
};
type Patch = { map: Record<string, Json>; toDeleteIids: string[]; tokenId: string; result: Json };
const isObj = (v: unknown): v is Json => !!v && typeof v === "object" && !Array.isArray(v);
const refId = (v: unknown): string | undefined => isObj(v) && typeof v.__ref === "string" ? v.__ref : undefined;
const fail = (reason: string): never => { throw new Error(reason); };
const kindOf = (v: unknown): Kind => {
  if (typeof v !== "string") return "code";
  try {
    const x: unknown = JSON.parse(v);
    if (typeof x === "string") return "text";
    if (typeof x === "number") return "number";
  } catch { /* Plasmic code expressions are not JSON. */ }
  return "code";
};
const codeForbidden = /\b(?:fetch|XMLHttpRequest|WebSocket|require|import|process|globalThis|window|document|navigator|eval|Function|constructor|localStorage|sessionStorage|service_role|api[_-]?key|password|secret)\b/i;
// A DataToken is rendered into the deployed site, so its value must never carry credential
// material. This check is deliberately fail-closed: a false positive costs a rename, a false
// negative publishes a secret to every visitor of the site.
const SECRET_MATERIAL = new RegExp([
  "secret|password|passwd|passphrase|credential|private[_-]?key|api[_-]?key|service[_-]?role",
  "access[_-]?token|refresh[_-]?token|auth[_-]?token|session[_-]?key",
  String.raw`\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{8,}`,
  String.raw`\bgh[pousr]_[A-Za-z0-9]{16,}`,
  String.raw`\bgithub_pat_[A-Za-z0-9_]{20,}`,
  String.raw`\bxox[baprs]-[A-Za-z0-9-]{10,}`,
  String.raw`\bAKIA[0-9A-Z]{16}\b`,
  String.raw`\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}`,
  String.raw`-----BEGIN [A-Z ]*PRIVATE KEY-----`,
  String.raw`\bbearer\s+[A-Za-z0-9._-]{12,}`,
].join("|"), "i");
const RANDOM_MATERIAL = /^[A-Za-z0-9_+/=-]{32,}$/;
export function isSecretMaterial(raw: string): boolean {
  if (SECRET_MATERIAL.test(raw)) return true;
  const bounded = raw.trim();
  return RANDOM_MATERIAL.test(bounded) && /[a-z]/.test(bounded) && /[A-Z]/.test(bounded) && /\d/.test(bounded);
}
export function assertNoSecretMaterial(raw: string, field: "NAME" | "VALUE"): void {
  if (isSecretMaterial(raw)) {
    throw new Error(
      `DATA_TOKEN_SECRET_${field}_REJECTED: DataTokens are rendered into the deployed site, so credential material is refused. ` +
      `Keep secrets in WAB project settings or an allowlisted data query, never in a DataToken.`,
    );
  }
}
const unwrapText = (stored: string): string => {
  try {
    const parsed: unknown = JSON.parse(stored);
    return typeof parsed === "string" ? parsed : stored;
  } catch {
    return stored;
  }
};
export function tokenValue(value: unknown, kind: Kind): string {
  if (kind === "text") {
    if (typeof value !== "string" || value.length > 4000) return fail("INVALID_DATA_TOKEN_TEXT");
    assertNoSecretMaterial(value, "VALUE");
    return JSON.stringify(value);
  }
  if (kind === "number") {
    if (typeof value !== "number" || !Number.isFinite(value)) fail("INVALID_DATA_TOKEN_NUMBER");
    return String(value);
  }
  if (typeof value !== "string" || !value.trim() || value.length > 4000 ||
      codeForbidden.test(value) || /[;][\s]*(?:fetch|eval|import|require)\b/i.test(value)) {
    fail("UNSAFE_DATA_TOKEN_CODE");
  }
  const trimmed = (value as string).trim();
  return trimmed.startsWith("(") && trimmed.endsWith(")") ? trimmed : "(" + trimmed + ")";
}
function safeName(name: unknown): string {
  if (typeof name !== "string" || !name.trim() || name !== name.trim() ||
      name.length > 80 || /[\u0000-\u001f<>]/.test(name) ||
      ["__proto__", "prototype", "constructor"].includes(name.toLowerCase())) {
    return fail("INVALID_DATA_TOKEN_NAME");
  }
  assertNoSecretMaterial(name, "NAME");
  return name;
}
function siteOf(bundle: BundleDoc): { iid: string; site: Json; refs: string[] } {
  const iid = typeof bundle.root === "string" ? bundle.root : fail("DATA_TOKEN_ROOT_INVALID");
  const site: unknown = bundle.map[iid];
  if (!isObj(site) || site.__type !== "Site" || !Array.isArray(site.dataTokens)) {
    return fail("DATA_TOKEN_SITE_MODEL_UNSUPPORTED");
  }
  const refs = site.dataTokens.map(refId);
  if (refs.some((x) => !x)) return fail("DATA_TOKEN_REFERENCE_MODEL_UNSUPPORTED");
  return { iid, site, refs: refs as string[] };
}
function tokenOf(bundle: BundleDoc, iid: string): Json {
  const x: unknown = bundle.map[iid];
  if (!isObj(x) || x.__type !== "DataToken" || x.type !== "Data" ||
      typeof x.name !== "string" || typeof x.value !== "string") {
    return fail("DATA_TOKEN_ENTRY_MODEL_UNSUPPORTED");
  }
  return x;
}
export function inspectDataTokens(bundle: BundleDoc): Json[] {
  return siteOf(bundle).refs.map((id) => {
    const t = tokenOf(bundle, id);
    return { id, name: t.name, valueType: kindOf(t.value), registered: t.isRegistered === true };
  });
}
function locate(bundle: BundleDoc, id: string): { iid: string; token: Json } {
  const refs = siteOf(bundle).refs;
  const matches = refs.filter((iid) => iid === id || tokenOf(bundle, iid).name === id);
  if (matches.length !== 1) return fail(matches.length ? "AMBIGUOUS_DATA_TOKEN" : "DATA_TOKEN_NOT_FOUND");
  return { iid: matches[0]!, token: tokenOf(bundle, matches[0]!) };
}
export function planDataToken(bundle: BundleDoc, op: Op, args: Args): Patch {
  const { iid: siteIid, site, refs } = siteOf(bundle);
  const map: Record<string, Json> = {};
  const toDeleteIids: string[] = [];
  let tokenId = "";
  let result: Json = {};
  if (op === "create") {
    const name = safeName(args.name);
    if (refs.some((id) => String(tokenOf(bundle, id).name).toLowerCase() === name.toLowerCase())) {
      return fail("DATA_TOKEN_NAME_EXISTS");
    }
    if (!args.valueType) return fail("DATA_TOKEN_TYPE_REQUIRED");
    const value = tokenValue(args.value, args.valueType);
    tokenId = "mcp" + randomUUID().replace(/-/g, "").slice(0, 20);
    const uuid = "mcp" + randomUUID().replace(/-/g, "").slice(0, 12);
    map[tokenId] = { __type: "DataToken", uuid, name, type: "Data", value, variantedValues: [], isRegistered: false, regKey: null };
    map[siteIid] = { ...site, dataTokens: [...(site.dataTokens as unknown[]), { __ref: tokenId }] };
    result = { id: tokenId, name, valueType: args.valueType };
  } else {
    if (!args.tokenId) return fail("DATA_TOKEN_ID_REQUIRED");
    const found = locate(bundle, args.tokenId);
    tokenId = found.iid;
    if (found.token.isRegistered === true) return fail("REGISTERED_DATA_TOKEN_IMMUTABLE");
    if (op === "update") {
      const name = args.name === undefined ? String(found.token.name) : safeName(args.name);
      if (refs.some((id) => id !== tokenId && String(tokenOf(bundle, id).name).toLowerCase() === name.toLowerCase())) {
        return fail("DATA_TOKEN_NAME_EXISTS");
      }
      const value = args.value === undefined ? found.token.value :
        tokenValue(args.value, args.valueType ?? kindOf(found.token.value));
      map[tokenId] = { ...found.token, name, value };
      result = { id: tokenId, name, valueType: kindOf(value) };
    } else {
      // Never delete an in-use DataToken, including references from page expressions.
      const needle = JSON.stringify({ __ref: tokenId });
      for (const [iid, entry] of Object.entries(bundle.map)) {
        if (iid !== siteIid && iid !== tokenId && JSON.stringify(entry).includes(needle)) {
          return fail("DATA_TOKEN_IN_USE");
        }
      }
      map[siteIid] = { ...site, dataTokens: (site.dataTokens as unknown[]).filter((x) => refId(x) !== tokenId) };
      toDeleteIids.push(tokenId);
      result = { id: tokenId, deleted: true };
    }
  }
  return { map, toDeleteIids, tokenId, result };
}
function materialize(bundle: BundleDoc, patch: Patch): BundleDoc {
  const map = { ...bundle.map, ...patch.map };
  for (const id of patch.toDeleteIids) delete map[id];
  return { ...bundle, map };
}
function readback(bundle: BundleDoc, op: Op, patch: Patch): boolean {
  const ids = siteOf(bundle).refs;
  if (op === "delete") return !ids.includes(patch.tokenId) && !(patch.tokenId in bundle.map);
  if (!ids.includes(patch.tokenId)) return false;
  return Object.entries(patch.map).every(([iid, expected]) =>
    JSON.stringify(bundle.map[iid]) === JSON.stringify(expected));
}
async function change(ctx: PlasmicCtx, op: Op, args: Args): Promise<Json> {
  const dryRun = args.dryRun !== false;
  if (!dryRun && (!args.branchId || args.branchId === "main" || !args.idempotencyKey)) {
    return fail("DATA_TOKEN_LIVE_REQUIRES_DESIGN_BRANCH_AND_IDEMPOTENCY_KEY");
  }
  // Explicit operator-granted project allowlist. WAB Editor permission alone is not release approval.
  if (!dryRun) {
    const allowed = new Set((process.env.PLASMIC_MCP_WRITABLE_PROJECT_IDS ?? "").split(",").map((s) => s.trim()).filter(Boolean));
    if (!allowed.has(args.projectId)) return fail("DATA_TOKEN_PROJECT_WRITE_NOT_APPROVED");
  }
  const performChange = async (): Promise<Json> => {
    if (!dryRun) {
      const branches = await ctx.client.listBranches(args.projectId);
      if (!branches.branches.some((b) => b.id === args.branchId)) return fail("DATA_TOKEN_BRANCH_NOT_FOUND");
    }
    const rev = await ctx.client.getProjectRev(args.projectId, args.branchId);
    if (args.expectedRevision !== undefined && rev.revision !== args.expectedRevision) {
      return fail("STALE_DATA_TOKEN_REVISION: expected " + args.expectedRevision + ", actual " + rev.revision);
    }
    if (!dryRun && args.expectedRevision === undefined) return fail("DATA_TOKEN_REVISION_REQUIRED");
    const patch = planDataToken(rev.bundle, op, args);
    if (dryRun) {
      return { dryRun: true, revision: rev.revision, wouldChange: Object.keys(patch.map).length + patch.toDeleteIids.length, ...patch.result };
    }
    const nextRevision = rev.revision + 1;
    await ctx.client.saveFull(args.projectId, nextRevision, materialize(rev.bundle, patch),
      args.branchId, { modelVersion: rev.modelVersion, hostlessDataVersion: rev.hostlessDataVersion });
    const after = await ctx.client.getProjectRev(args.projectId, args.branchId);
    if (after.revision < nextRevision || !readback(after.bundle, op, patch)) {
      return fail("DATA_TOKEN_WRITE_READBACK_UNVERIFIED: inspect branch before retry");
    }
    return { dryRun: false, revision: after.revision, ...patch.result };
  };
  if (dryRun) return performChange();
  const key = "live:data-token:" + args.projectId + ":" + args.branchId + ":" + op + ":" + args.idempotencyKey;
  const digest = sha256(JSON.stringify({ op, projectId: args.projectId, branchId: args.branchId,
    tokenId: args.tokenId, name: args.name, value: args.value, valueType: args.valueType,
    expectedRevision: args.expectedRevision }));
  const cached = await idempotent(ctx.stateDir + "/idempotency", key, () =>
    writeOp(ctx, "plasmic_" + op + "_data_token", args.projectId, args.tokenId, digest,
      async () => { const saved = await performChange(); return { ...saved, revision: Number(saved.revision), payloadDigest: digest }; }));
  if (cached.result.payloadDigest !== digest) return fail("DATA_TOKEN_IDEMPOTENCY_CONFLICT");
  const { payloadDigest: _hiddenDigest, ...result } = cached.result;
  return { ...result, deduped: cached.deduped };
}
const common = { projectId: z.string().min(1), branchId: z.string().optional() };
const writeCommon = { ...common, expectedRevision: z.number().int().nonnegative().optional(),
  dryRun: z.boolean().optional(), idempotencyKey: z.string().min(8).max(128).optional() };
const nameValue = { name: z.string().min(1).max(80), valueType: z.enum(["text", "number", "code"]),
  value: z.union([z.string(), z.number()]) };
export function plasmicDataTokenTools(ctx: PlasmicCtx): ToolDef[] {
  return [
    { name: "plasmic_list_data_tokens", annotations: { readOnlyHint: true },
      description: "List WAB DataTokens (names, types, IDs) in an authorized project/branch; no secret values.",
      schema: common, handler: async (a) => {
        const rev = await ctx.client.getProjectRev(a.projectId as string, a.branchId as string | undefined);
        return { revision: rev.revision, tokens: inspectDataTokens(rev.bundle) };
      } },
    { name: "plasmic_get_data_token", annotations: { readOnlyHint: true },
      description: "Read one WAB DataToken under the service account's WAB project permissions; credential-shaped or unsafe values are redacted, never returned.",
      schema: { ...common, tokenId: z.string().min(1) }, handler: async (a) => {
        const rev = await ctx.client.getProjectRev(a.projectId as string, a.branchId as string | undefined);
        const token = locate(rev.bundle, a.tokenId as string);
        const stored = String(token.token.value);
        const kind = kindOf(stored);
        // Existing tokens may predate the create/update guard, so redact on read as well:
        // code expressions are never echoed and text values are withheld when they look like
        // credential material.
        const sensitive = codeForbidden.test(stored) ||
          (kind === "text" && isSecretMaterial(unwrapText(stored)));
        return { id: token.iid, name: token.token.name, revision: rev.revision,
          valueType: kind, value: sensitive ? undefined : stored,
          valueRedacted: sensitive, registered: token.token.isRegistered === true };
      } },
    { name: "plasmic_create_data_token",
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
      description: "Create WAB DataToken; credential-shaped names/values are refused; dryRun by default, live writes require existing design branch, revision CAS and idempotency key. No publish.",
      schema: { ...writeCommon, ...nameValue },
      handler: (a) => change(ctx, "create", a as Args) },
    { name: "plasmic_update_data_token",
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true },
      description: "Update DataToken on an existing design branch with CAS, readback and dryRun default.",
      schema: { ...writeCommon, tokenId: z.string().min(1),
        name: z.string().min(1).max(80).optional(), valueType: z.enum(["text", "number", "code"]).optional(),
        value: z.union([z.string(), z.number()]).optional() },
      handler: (a) => change(ctx, "update", a as Args) },
    { name: "plasmic_delete_data_token",
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true },
      description: "Delete only an unregistered, unreferenced DataToken on existing test branch; CAS required, dryRun default.",
      schema: { ...writeCommon, tokenId: z.string().min(1) },
      handler: (a) => change(ctx, "delete", a as Args) },
  ];
}
