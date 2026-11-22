/**
 * DOD-02: agent-consumable component catalog built from the authorized WAB
 * project revision. Read-only: every item, spec and count is derived from the
 * bundle entries actually returned by WAB for the requested project/branch.
 * Nothing is invented, and unsupported model data is reported as unavailable
 * instead of being faked.
 */
import { z } from "zod";
import { sha256 } from "@design-stack/contracts/sync";
import type { ToolDef } from "@design-stack/mcp-server";
import type { BundleDoc } from "@design-stack/plasmic-client";
import type { PlasmicCtx } from "./tools.ts";

type Entry = Record<string, unknown>;
type EntryMap = Record<string, Entry>;

export interface CatalogItem {
  id: string;
  name: string;
  kind: "page" | "component";
  pagePath?: string;
  instanceCount: number;
  nodeCount: number;
  paramCount: number;
  paramNames: string[];
}

export interface CatalogIndex {
  catalogKey: string;
  revision: number;
  branch: string;
  items: CatalogItem[];
}

const MAX_CACHE_ENTRIES = 8;
const MAX_TREE_NODES = 400;
const cache = new Map<string, CatalogIndex>();

const isObj = (v: unknown): v is Entry => !!v && typeof v === "object" && !Array.isArray(v);
const refId = (v: unknown): string | undefined =>
  isObj(v) && typeof v.__ref === "string" ? v.__ref : undefined;
const refList = (v: unknown): string[] =>
  Array.isArray(v) ? v.map(refId).filter((x): x is string => !!x) : [];
const typeOf = (e: Entry | undefined): string => String(e?.__type ?? "");

/** Deterministic catalog identity: project + branch + revision. */
export function catalogKeyFor(projectId: string, branch: string, revision: number): string {
  return `catalog:${sha256(`${projectId}@${branch}#${revision}`)}`;
}

function childrenOf(map: EntryMap, iid: string, limit = MAX_TREE_NODES): string[] {
  const out: string[] = [];
  const stack = [iid];
  const seen = new Set<string>();
  while (stack.length && out.length < limit) {
    const current = stack.pop()!;
    if (seen.has(current)) continue;
    seen.add(current);
    const entry = map[current];
    if (!entry) continue;
    const children = refList(entry.children);
    if (entry.tplTree !== undefined) {
      const root = refId(entry.tplTree);
      if (root) stack.push(root);
    }
    for (const child of children) {
      if (!seen.has(child)) {
        out.push(child);
        stack.push(child);
      }
    }
  }
  return out;
}

function paramInfo(map: EntryMap, component: Entry): { ids: string[]; names: string[] } {
  const ids = refList(component.params);
  const names = ids.map((id) => String(map[id]?.name ?? id));
  return { ids, names };
}

export function buildCatalogIndex(
  projectId: string,
  branch: string,
  revision: number,
  bundle: BundleDoc,
): CatalogIndex {
  const map = bundle.map as EntryMap;
  const instancesByComponent = new Map<string, number>();
  for (const entry of Object.values(map)) {
    if (typeOf(entry) !== "TplComponent") continue;
    const componentId = refId(entry.component);
    if (!componentId) continue;
    instancesByComponent.set(componentId, (instancesByComponent.get(componentId) ?? 0) + 1);
  }
  const items: CatalogItem[] = [];
  for (const [iid, entry] of Object.entries(map)) {
    // Component instances (TplComponent) are not catalog items.
    if (typeOf(entry) !== "Component") continue;
    const kind: "page" | "component" = entry.pageMeta !== undefined ? "page" : "component";
    const pagePath = kind === "page" ? String(map[refId(entry.pageMeta) ?? ""]?.path ?? "") : undefined;
    const params = paramInfo(map, entry);
    const tplTreeId = refId(entry.tplTree);
    items.push({
      id: iid,
      name: String(entry.name ?? iid),
      kind,
      ...(kind === "page" ? { pagePath } : {}),
      instanceCount: instancesByComponent.get(iid) ?? 0,
      nodeCount: tplTreeId ? childrenOf(map, tplTreeId).length : 0,
      paramCount: params.ids.length,
      paramNames: params.names,
    });
  }
  items.sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
  return {
    catalogKey: catalogKeyFor(projectId, branch, revision),
    revision,
    branch,
    items,
  };
}

/**
 * Revision-scoped index cache. A stale revision can never be served: the caller
 * always reads the live revision first, and the entry is replaced when the
 * revision (or branch) moves.
 */
export function catalogIndex(
  projectId: string,
  branch: string,
  revision: number,
  bundle: BundleDoc,
): { index: CatalogIndex; cacheHit: boolean } {
  const key = `${projectId}@${branch}`;
  const cached = cache.get(key);
  if (cached && cached.revision === revision) {
    cache.delete(key);
    cache.set(key, cached);
    return { index: cached, cacheHit: true };
  }
  const index = buildCatalogIndex(projectId, branch, revision, bundle);
  cache.delete(key);
  cache.set(key, index);
  while (cache.size > MAX_CACHE_ENTRIES) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
  return { index, cacheHit: false };
}

/** Test/ops hook: never exposed as an MCP tool. */
export function resetCatalogCache(): void {
  cache.clear();
}

export function resolveComponentEntry(
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
  throw new Error(`COMPONENT_NOT_FOUND "${ref}"`);
}

export function plasmicCatalogTools(ctx: PlasmicCtx): ToolDef[] {
  const c = ctx.client;
  return [
    {
      name: "plasmic_search_components",
      annotations: { readOnlyHint: true },
      description:
        "Project-scoped, paginated search over the component/page catalog of one Plasmic project branch (name filter, kind filter, stable ids, instance counts, revision-scoped cache key). Read-only.",
      schema: {
        projectId: z.string().min(1),
        branchId: z.string().optional(),
        query: z.string().max(120).optional().describe("Case-insensitive substring match on the component name"),
        kind: z.enum(["all", "component", "page"]).optional(),
        limit: z.number().int().min(1).max(100).optional(),
        offset: z.number().int().min(0).optional(),
      },
      handler: async (a) => {
        const projectId = a.projectId as string;
        const branchId = a.branchId as string | undefined;
        const branch = branchId ?? "main";
        const rev = await c.getProjectRev(projectId, branchId);
        const { index, cacheHit } = catalogIndex(projectId, branch, rev.revision, rev.bundle);
        const query = ((a.query as string | undefined) ?? "").trim().toLowerCase();
        const kind = (a.kind as "all" | "component" | "page" | undefined) ?? "all";
        const limit = (a.limit as number | undefined) ?? 20;
        const offset = (a.offset as number | undefined) ?? 0;
        const filtered = index.items.filter((item) => {
          if (kind !== "all" && item.kind !== kind) return false;
          return query ? item.name.toLowerCase().includes(query) : true;
        });
        return {
          revision: rev.revision,
          catalogKey: index.catalogKey,
          cacheHit,
          total: filtered.length,
          offset,
          limit,
          items: filtered.slice(offset, offset + limit),
        };
      },
    },
    {
      name: "plasmic_get_component_spec",
      annotations: { readOnlyHint: true },
      description:
        "Component specification from the live WAB revision: declared params/slots, instances, subtree dependencies, style tokens and provenance. Model data that the revision does not expose is reported as unavailable, never invented.",
      schema: {
        projectId: z.string().min(1),
        componentId: z.string().min(1),
        branchId: z.string().optional(),
      },
      handler: async (a) => {
        const projectId = a.projectId as string;
        const branchId = a.branchId as string | undefined;
        const branch = branchId ?? "main";
        const rev = await c.getProjectRev(projectId, branchId);
        const map = rev.bundle.map as EntryMap;
        const { iid, entry } = resolveComponentEntry(map, a.componentId as string);
        if (typeOf(entry) !== "Component") {
          throw new Error(`NOT_A_COMPONENT "${iid}" is ${typeOf(entry) || "unknown"}`);
        }
        const paramIds = refList(entry.params);
        const params = paramIds.map((paramIid) => {
          const param = map[paramIid];
          const typeIid = refId(param?.type);
          const typeEntry = typeIid ? map[typeIid] : undefined;
          return {
            id: paramIid,
            name: String(param?.name ?? paramIid),
            typeId: typeIid ?? null,
            typeName: typeEntry ? String(typeEntry.name ?? typeEntry.__type ?? typeIid) : null,
            defaultExpr: refId(param?.defaultExpr) ?? null,
          };
        });
        // Slots are params whose resolved type name is a slot type. When the
        // revision does not carry resolvable param types we say so instead of
        // guessing.
        const typedParams = params.filter((p) => p.typeName !== null);
        const slots = typedParams.filter((p) => /slot/i.test(String(p.typeName)));
        const slotsAvailable = typedParams.length === params.length;
        const tplTreeId = refId(entry.tplTree);
        const subtree = tplTreeId ? childrenOf(map, tplTreeId) : [];
        const instances = Object.entries(map)
          .filter(([, e]) => typeOf(e) === "TplComponent" && refId(e.component) === iid)
          .map(([instanceIid, e]) => ({ id: instanceIid, parentId: refId(e.parent) ?? null }))
          .slice(0, 20);
        const subtreeText = subtree.map((id) => JSON.stringify(map[id] ?? {})).join(" ");
        const dependencies = Object.entries(map)
          .filter(([depIid, e]) => depIid !== iid && typeOf(e) === "Component" && subtreeText.includes(depIid))
          .map(([depIid, e]) => ({ id: depIid, name: String(e.name ?? depIid) }))
          .slice(0, 50);
        const tokens = Object.entries(map)
          .filter(([tokenIid, e]) => typeOf(e).toLowerCase().includes("token") && subtreeText.includes(tokenIid))
          .map(([tokenIid, e]) => ({ id: tokenIid, name: String(e.name ?? tokenIid) }))
          .slice(0, 50);
        return {
          revision: rev.revision,
          catalogKey: catalogKeyFor(projectId, branch, rev.revision),
          component: {
            id: iid,
            name: String(entry.name ?? iid),
            kind: entry.pageMeta !== undefined ? "page" : "component",
            tplTreeId: tplTreeId ?? null,
            nodeCount: subtree.length,
            params,
            slots,
            slotsAvailable,
            instances,
            dependencies,
            styleTokens: tokens,
            previewAvailable: false,
            previewNote: "No preview URL is exposed by this adapter; read the tree with plasmic_read_ui_outline.",
          },
          provenance: { projectId, branch, revision: rev.revision },
        };
      },
    },
  ];
}
