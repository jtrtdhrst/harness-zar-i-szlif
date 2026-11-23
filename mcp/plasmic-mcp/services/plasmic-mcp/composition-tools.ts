/**
 * DOD-03: safe native composition through MCP only.
 *
 * Every composition is planned against the live WAB revision, then applied in
 * one revision-safe mutation. Two defects of the previous insert path are
 * fixed here and in plasmic_use_component:
 *   1. a cloned instance shared its VariantSetting/RuleSet/attrs entries with
 *      the template instance, so styling a new node silently restyled the
 *      original;
 *   2. a cloned instance was never referenced from any parent's children, so
 *      it was unreachable in Studio and could not render.
 * Unsupported model capabilities (slot routing, responsive variant overrides,
 * undeclared props) are reported as structured errors instead of being faked.
 */
import { z } from "zod";
import { idempotent } from "@design-stack/contracts/idempotency";
import { sha256 } from "@design-stack/contracts/sync";
import type { ToolDef } from "@design-stack/mcp-server";
import { writeOp, type PlasmicCtx } from "./tools.ts";

type Entry = Record<string, unknown>;
type EntryMap = Record<string, Entry>;
type PropScalar = string | number | boolean;

export interface ComposeItem {
  componentId: string;
  props?: Record<string, PropScalar>;
}

export interface InstanceCloneResult {
  instanceIid: string;
  created: string[];
  propsApplied: string[];
  patch: EntryMap;
}

export interface PlanResult {
  patch: EntryMap;
  inserted: Array<{ componentId: string; componentName: string; instanceId: string }>;
  parentChildrenAfter: number;
  warnings: string[];
}

/** Entry types a component instance must own privately, never share. */
const PRIVATE_TYPES = new Set(["RuleSet", "RawText", "CustomCode", "Expr"]);

const isObj = (v: unknown): v is Entry => !!v && typeof v === "object" && !Array.isArray(v);
const refId = (v: unknown): string | undefined =>
  isObj(v) && typeof v.__ref === "string" ? v.__ref : undefined;
const refList = (v: unknown): string[] =>
  Array.isArray(v) ? v.map(refId).filter((x): x is string => !!x) : [];
const typeOf = (v: unknown): string => (isObj(v) ? String(v.__type ?? "") : "");

/** Deterministic id: replays of the same operation produce the same entries. */
export function deterministicId(seed: string, path: string): string {
  return `mcp${sha256(`${seed}|${path}`).slice(0, 16)}`;
}

export function resolveComponent(
  map: EntryMap,
  ref: string,
): { iid: string; entry: Entry } {
  const direct = map[ref];
  if (direct) return { iid: ref, entry: direct };
  const matches = Object.entries(map).filter(
    ([, entry]) => String(entry?.name ?? "").toLowerCase() === ref.toLowerCase(),
  );
  if (matches.length === 1) {
    const [iid, entry] = matches[0]!;
    return { iid, entry };
  }
  if (matches.length > 1) {
    throw new Error(`AMBIGUOUS_COMPONENT "${ref}": ${matches.map(([i]) => i).join(", ")} — use the stable component id`);
  }
  throw new Error(`UNKNOWN_COMPONENT "${ref}" — list the catalog with plasmic_search_components`);
}

interface CloneCtx {
  map: EntryMap;
  seed: string;
  patch: EntryMap;
  created: string[];
  cloned: Map<string, string>;
}

function cloneRefs(value: unknown, ctx: CloneCtx, path: string): unknown {
  if (Array.isArray(value)) return value.map((item, i) => cloneRefs(item, ctx, `${path}[${i}]`));
  if (!isObj(value)) return value;
  const target = refId(value);
  if (target) {
    const entry = ctx.map[target];
    // Style tokens, variants, assets and other shared model entries stay shared.
    if (!entry || !PRIVATE_TYPES.has(typeOf(entry))) return value;
    return { __ref: clonePrivateEntry(target, entry, ctx, path) };
  }
  const out: Entry = {};
  for (const [key, nested] of Object.entries(value)) out[key] = cloneRefs(nested, ctx, `${path}.${key}`);
  return out;
}

function clonePrivateEntry(srcIid: string, entry: Entry, ctx: CloneCtx, path: string): string {
  const cached = ctx.cloned.get(srcIid);
  if (cached) return cached;
  const newIid = deterministicId(ctx.seed, `entry:${path}`);
  ctx.cloned.set(srcIid, newIid);
  const copy: Entry = {};
  for (const [key, value] of Object.entries(entry)) copy[key] = cloneRefs(value, ctx, `${path}.${key}`);
  if (typeof entry.uuid === "string") copy.uuid = deterministicId(ctx.seed, `uuid:${path}`);
  ctx.patch[newIid] = copy;
  ctx.created.push(newIid);
  return newIid;
}

function paramIndex(map: EntryMap, component: Entry | undefined): Map<string, string> {
  const out = new Map<string, string>();
  for (const paramIid of refList(component?.params)) {
    const name = map[paramIid]?.name;
    if (typeof name === "string") out.set(name, paramIid);
  }
  return out;
}

/**
 * Clone one existing component instance so the copy owns its own
 * VariantSetting/RuleSet/attrs/args chain. The caller decides where the copy is
 * wired (see planComposition); this helper never touches a parent.
 */
export function cloneInstanceAsPrivate(
  map: EntryMap,
  templateIid: string,
  seed: string,
  props?: Record<string, PropScalar>,
): InstanceCloneResult {
  const template = map[templateIid];
  if (typeOf(template) !== "TplComponent") {
    throw new Error(`NO_INSTANCE_TEMPLATE "${templateIid}" is ${typeOf(template) || "unknown"}, not a component instance`);
  }
  if (refList(template.children).length > 0) {
    throw new Error(
      `SLOT_CONTENT_CLONE_UNSUPPORTED "${templateIid}" carries slot content — instantiate a content-free component instead of guessing slot semantics`,
    );
  }
  const ctx: CloneCtx = { map, seed, patch: {}, created: [], cloned: new Map() };
  const vsIds = refList(template.vsettings);
  if (vsIds.length === 0) throw new Error(`VARIANT_SETTING_MISSING "${templateIid}" has no vsettings to clone`);
  const newVsIds: string[] = [];
  vsIds.forEach((vsIid, index) => {
    const vs = map[vsIid];
    if (!isObj(vs)) throw new Error(`VARIANT_SETTING_MISSING "${vsIid}"`);
    const newVsIid = deterministicId(seed, `vs:${index}`);
    ctx.cloned.set(vsIid, newVsIid);
    const copy: Entry = {};
    for (const [key, value] of Object.entries(vs)) copy[key] = cloneRefs(value, ctx, `vs${index}.${key}`);
    ctx.patch[newVsIid] = copy;
    ctx.created.push(newVsIid);
    newVsIds.push(newVsIid);
  });

  const instanceIid = deterministicId(seed, "instance");
  const propsApplied: string[] = [];
  const entry: Entry = {
    ...template,
    uuid: deterministicId(seed, "uuid"),
    vsettings: newVsIds.map((id) => ({ __ref: id })),
    children: [],
  };
  if (props && Object.keys(props).length > 0) {
    const componentId = refId(template.component);
    const params = paramIndex(map, componentId ? map[componentId] : undefined);
    const baseVs = ctx.patch[newVsIds[0]!]!;
    const args = Array.isArray(baseVs.args) ? [...baseVs.args] : [];
    for (const [name, value] of Object.entries(props)) {
      const paramIid = params.get(name);
      if (!paramIid) {
        throw new Error(
          `PROP_UNSUPPORTED "${name}" — component "${componentId ?? "?"}" declares no such param; declared params: ${[...params.keys()].join(", ") || "none"}`,
        );
      }
      if (!["string", "number", "boolean"].includes(typeof value)) {
        throw new Error(`PROP_UNSUPPORTED "${name}" — only string/number/boolean props are supported`);
      }
      const exprIid = deterministicId(seed, `prop:${name}`);
      ctx.patch[exprIid] = { __type: "CustomCode", code: JSON.stringify(value), fallback: null };
      ctx.created.push(exprIid);
      args.push({ param: { __ref: paramIid }, expr: { __ref: exprIid } });
      propsApplied.push(name);
    }
    ctx.patch[newVsIds[0]!] = { ...baseVs, args };
  }
  ctx.patch[instanceIid] = entry;
  ctx.created.push(instanceIid);
  return { instanceIid, created: ctx.created, propsApplied, patch: ctx.patch };
}

function assertNoDanglingRefs(patch: EntryMap, map: EntryMap): void {
  const known = new Set([...Object.keys(map), ...Object.keys(patch)]);
  const dangling = new Set<string>();
  const walk = (value: unknown): void => {
    if (Array.isArray(value)) { value.forEach(walk); return; }
    if (!isObj(value)) return;
    const target = refId(value);
    if (target) {
      if (!known.has(target)) dangling.add(target);
      return;
    }
    Object.values(value).forEach(walk);
  };
  Object.values(patch).forEach(walk);
  if (dangling.size) throw new Error(`DANGLING_REFS after plan: ${[...dangling].join(", ")}`);
}

/**
 * Plan a composition against one live revision: validate the parent, every
 * component reference, prop support and the insertion index, then return the
 * exact entries to write. No mutation happens here.
 */
export function planComposition(
  map: EntryMap,
  opts: { parentElementId: string; index?: number; items: ComposeItem[]; seed: string },
): PlanResult {
  const parent = map[opts.parentElementId];
  if (!parent) throw new Error(`PARENT_NOT_FOUND "${opts.parentElementId}"`);
  const children = Array.isArray(parent.children) ? [...parent.children] : undefined;
  if (!children) {
    throw new Error(
      `PARENT_NOT_A_CONTAINER "${opts.parentElementId}" is ${typeOf(parent) || "unknown"} without a children array — pass a TplTag container id (a component root is its tplTree id)`,
    );
  }
  if (opts.items.length === 0) throw new Error("EMPTY_COMPOSITION");
  const index = opts.index ?? children.length;
  if (!Number.isInteger(index) || index < 0 || index > children.length) {
    throw new Error(`INDEX_OUT_OF_RANGE ${index} — parent has ${children.length} children`);
  }
  const patch: EntryMap = {};
  const inserted: PlanResult["inserted"] = [];
  const newRefs: Array<{ __ref: string }> = [];
  opts.items.forEach((item, i) => {
    const { iid, entry } = resolveComponent(map, item.componentId);
    if (typeOf(entry) !== "Component") {
      throw new Error(`NOT_A_COMPONENT "${iid}" is ${typeOf(entry) || "unknown"}`);
    }
    if (entry.pageMeta !== undefined) {
      throw new Error(`PAGE_COMPONENT_NOT_INSTANTIABLE "${iid}" is a page — pages are not placed as child instances`);
    }
    const template = Object.entries(map).find(
      ([, candidate]) => typeOf(candidate) === "TplComponent" && refId(candidate.component) === iid,
    );
    if (!template) {
      throw new Error(
        `NO_INSTANCE_TEMPLATE "${iid}" has no instance in this revision to clone — create the first instance in Studio, then compose through MCP`,
      );
    }
    const cloned = cloneInstanceAsPrivate(map, template[0], `${opts.seed}:item:${i}`, item.props);
    Object.assign(patch, cloned.patch);
    newRefs.push({ __ref: cloned.instanceIid });
    inserted.push({
      componentId: iid,
      componentName: String(entry.name ?? iid),
      instanceId: cloned.instanceIid,
    });
  });
  const nextChildren = [...children.slice(0, index), ...newRefs, ...children.slice(index)];
  patch[opts.parentElementId] = { ...parent, children: nextChildren };
  assertNoDanglingRefs(patch, map);
  return {
    patch,
    inserted,
    parentChildrenAfter: nextChildren.length,
    warnings: [
      "Responsive variant overrides and slot routing are not supported by this tool; compose the base variant only.",
    ],
  };
}

export function plasmicCompositionTools(ctx: PlasmicCtx): ToolDef[] {
  const c = ctx.client;
  const itemSchema = z.object({
    componentId: z.string().min(1),
    props: z.record(z.string(), z.union([z.string(), z.number(), z.boolean()])).optional(),
  }).strict();

  const seedFor = (projectId: string, branch: string, parent: string, index: number | undefined, items: ComposeItem[], key?: string) =>
    `compose:${projectId}@${branch}:${key ?? sha256(JSON.stringify({ parent, index: index ?? null, items })).slice(0, 20)}`;

  return [
    {
      name: "plasmic_plan_composition",
      annotations: { readOnlyHint: true },
      description:
        "Dry-run plan for composing catalog components into a Plasmic container: validates parent, component refs, props and insertion index against the live revision and returns the exact entries and order that would be written. Never writes.",
      schema: {
        projectId: z.string().min(1),
        branchId: z.string().optional(),
        parentElementId: z.string().min(1),
        items: z.array(itemSchema).min(1).max(10),
        index: z.number().int().min(0).optional(),
        idempotencyKey: z.string().min(8).max(120).optional().describe(
          "Pass the key you will use for the live write so the planned instance ids match the applied ones",
        ),
      },
      handler: async (a) => {
        const projectId = a.projectId as string;
        const branchId = a.branchId as string | undefined;
        const rev = await c.getProjectRev(projectId, branchId);
        const map = rev.bundle.map as EntryMap;
        const items = a.items as ComposeItem[];
        const seed = seedFor(projectId, branchId ?? "main", a.parentElementId as string, a.index as number | undefined, items, a.idempotencyKey as string | undefined);
        const plan = planComposition(map, {
          parentElementId: a.parentElementId as string,
          ...(a.index !== undefined ? { index: a.index as number } : {}),
          items,
          seed,
        });
        return {
          revision: rev.revision,
          dryRun: true,
          parentElementId: a.parentElementId,
          inserted: plan.inserted,
          parentChildrenAfter: plan.parentChildrenAfter,
          entriesToCreate: Object.keys(plan.patch).filter((id) => id !== a.parentElementId).length,
          warnings: plan.warnings,
        };
      },
    },
    {
      name: "plasmic_compose_components",
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
      description:
        "Compose catalog components into one Plasmic container in a single revision-safe mutation (dryRun by default). Each inserted instance owns private style/prop entries and is wired into the parent's children, so it is editable and renders. Requires an idempotency key for live writes.",
      schema: {
        projectId: z.string().min(1),
        branchId: z.string().optional(),
        parentElementId: z.string().min(1),
        items: z.array(itemSchema).min(1).max(10),
        index: z.number().int().min(0).optional(),
        dryRun: z.boolean().optional(),
        idempotencyKey: z.string().min(8).max(120).optional(),
      },
      handler: async (a) => {
        const projectId = a.projectId as string;
        const branchId = a.branchId as string | undefined;
        const parentElementId = a.parentElementId as string;
        const items = a.items as ComposeItem[];
        const preview = a.dryRun !== false;
        if (!preview && !a.idempotencyKey) throw new Error("IDEMPOTENCY_KEY_REQUIRED");
        const seed = seedFor(projectId, branchId ?? "main", parentElementId, a.index as number | undefined, items, a.idempotencyKey as string | undefined);
        const payload = { parentElementId, index: a.index ?? null, items };
        const inputHash = sha256(JSON.stringify(payload));
        let planned: PlanResult | undefined;
        const perform = async () => {
          const result = await c.mutate(projectId, branchId, (bundle) => {
            const map = bundle.map as EntryMap;
            const plan = planComposition(map, {
              parentElementId,
              ...(a.index !== undefined ? { index: a.index as number } : {}),
              items,
              seed,
            });
            planned = plan;
            // Deterministic ids make a retry a no-op instead of a duplicate node.
            if (plan.inserted.every((entry) => !!map[entry.instanceId])) return null;
            return { map: plan.patch };
          }, { dryRun: preview, saveMode: "full" });
          return { ...result, ...(planned ? { plan: planned.inserted, parentChildrenAfter: planned.parentChildrenAfter, warnings: planned.warnings } : {}) };
        };
        const op = () => writeOp(ctx, "plasmic_compose_components", projectId, parentElementId, JSON.stringify({ inputHash }), perform);
        if (preview) return { ...(await op()), deduped: false, dryRun: true };
        const cacheKey = ["live", "plasmic_compose_components", projectId, branchId ?? "main", a.idempotencyKey as string].join(":");
        const value = await idempotent(ctx.stateDir + "/idempotency", cacheKey, async () => ({ inputHash, effect: await op() }));
        if (value.result.inputHash !== inputHash) {
          throw new Error("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_INPUT");
        }
        return { ...value.result.effect, deduped: value.deduped };
      },
    },
  ];
}
