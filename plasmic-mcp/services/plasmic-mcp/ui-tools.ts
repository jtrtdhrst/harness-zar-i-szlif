/**
 * Native, bounded Plasmic UI composition. Not HTML import or codegen.
 * Dry runs are the default. All live writes use WAB's revisioned mutate()
 * and are audited + project-serialized by the existing adapter.
 */
import { randomBytes } from "node:crypto";
import { z } from "zod";
import { idempotent } from "@design-stack/contracts/idempotency";
import type { ToolDef } from "@design-stack/mcp-server";
import type { BundleDoc } from "@design-stack/plasmic-client";
import { writeOp, type PlasmicCtx } from "./tools.ts";

type Entry = Record<string, unknown>;
type EntryMap = Record<string, Entry>;
type Ref = { __ref: string };
interface UiNode {
  tag: string;
  name?: string;
  text?: string;
  styles?: Record<string, string>;
  children?: UiNode[];
}
const TAGS = [
  "div", "main", "section", "article", "header", "footer", "nav", "aside",
  "h1", "h2", "h3", "h4", "p", "span", "strong", "em", "small", "ul", "ol", "li",
] as const;
const nodeSchema: z.ZodTypeAny = z.lazy(() => z.object({
  tag: z.enum(TAGS),
  name: z.string().min(1).max(80).optional(),
  text: z.string().max(5000).optional(),
  styles: z.record(z.string(), z.string()).optional(),
  children: z.array(nodeSchema).max(20).optional(),
}).strict());
const stylesSchema = z.record(z.string(), z.string());
const id = () => "mcp" + randomBytes(10).toString("base64url");
const ref = (iid: string): Ref => ({ __ref: iid });
const refId = (value: unknown): string | undefined =>
  value && typeof value === "object" && typeof (value as Ref).__ref === "string"
    ? (value as Ref).__ref : undefined;
const get = (map: EntryMap, iid: string | undefined): Entry | undefined =>
  iid ? map[iid] : undefined;
const styleKey = /^[a-z][a-z0-9-]{0,48}$/;
const forbiddenCss = /(?:expression\s*\(|@import|url\s*\(\s*["']?\s*(?:data|javascript):|[{};])/i;
export function validateUiStyles(styles: Record<string, string>): void {
  if (Object.keys(styles).length > 48) throw new Error("STYLE_LIMIT: max 48 properties per node");
  for (const [key, value] of Object.entries(styles)) {
    if (!styleKey.test(key) || key.startsWith("--") || value.length > 320 || forbiddenCss.test(value)) {
      throw new Error("INVALID_STYLE: use plain CSS declarations without embedded code");
    }
  }
}
function countNodes(nodes: UiNode[], depth = 1): number {
  if (depth > 7) throw new Error("TREE_DEPTH_LIMIT: max 7");
  let count = 0;
  for (const node of nodes) {
    validateUiStyles(node.styles ?? {});
    if (node.text !== undefined && (node.children?.length ?? 0) > 0) {
      throw new Error("TEXT_WITH_CHILDREN: choose one representation");
    }
    count += 1 + countNodes(node.children ?? [], depth + 1);
    if (count > 60) throw new Error("TREE_NODE_LIMIT: max 60 nodes per operation");
  }
  return count;
}
function baseVariants(map: EntryMap, parent: Entry): Ref[] {
  const settings = get(map, refId((parent.vsettings as unknown[] | undefined)?.[0]));
  const variants = settings?.variants;
  if (!Array.isArray(variants) || !variants.length || !variants.every(v => !!get(map, refId(v)))) {
    throw new Error("BASE_VARIANT_UNAVAILABLE: parent must have a valid base VariantSetting");
  }
  return structuredClone(variants) as Ref[];
}
export function planNativeTree(
  map: EntryMap, parentIid: string, nodes: UiNode[],
): { patch: EntryMap; created: string[] } {
  const parent = map[parentIid];
  if (!parent || parent.__type !== "TplTag") {
    throw new Error("PARENT_NOT_TPLTAG: use the iid of an existing native TplTag");
  }
  const childRefs = parent.children;
  if (!Array.isArray(childRefs)) throw new Error("PARENT_CHILDREN_INVALID");
  const variants = baseVariants(map, parent);
  const total = countNodes(nodes);
  if (!total) throw new Error("EMPTY_TREE");
  const patch: EntryMap = {};
  const created: string[] = [];
  const build = (node: UiNode, parentId: string): string => {
    const tagId = id(), variantId = id(), rulesId = id();
    created.push(tagId);
    const children = (node.children ?? []).map(child => ref(build(child, tagId)));
    const textId = node.text !== undefined ? id() : undefined;
    patch[tagId] = {
      __type: "TplTag", tag: node.tag, name: node.name ?? null,
      children, type: textId ? "text" : "other", codeGenType: null,
      columnsSetting: null, uuid: id(), parent: ref(parentId),
      locked: null, vsettings: [ref(variantId)],
    };
    patch[rulesId] = {
      __type: "RuleSet", values: { ...(node.styles ?? {}) },
      mixins: [], animations: null,
    };
    patch[variantId] = {
      __type: "VariantSetting", variants: structuredClone(variants), args: [],
      attrs: {}, rs: ref(rulesId), dataCond: null, dataRep: null,
      text: textId ? ref(textId) : null, columnsConfig: null,
    };
    if (textId !== undefined) {
      patch[textId] = { __type: "RawText", text: node.text ?? "", markers: [] };
    }
    return tagId;
  };
  const roots = nodes.map(node => ref(build(node, parentIid)));
  patch[parentIid] = { ...parent, children: [...childRefs, ...roots] };
  return { patch, created };
}
function sanitizeOutline(map: EntryMap, rootId: string, depthLimit: number, nodeLimit: number) {
  const seen = new Set<string>();
  let truncated = false;
  const walk = (iid: string, depth: number): unknown => {
    if (depth > depthLimit || seen.size >= nodeLimit || seen.has(iid)) {
      truncated = true;
      return { iid, truncated: true };
    }
    seen.add(iid);
    const entry = get(map, iid);
    if (!entry) return { iid, missing: true };
    if (entry.__type === "TplComponent") {
      return { iid, kind: "component-instance", componentId: refId(entry.component) };
    }
    if (entry.__type !== "TplTag") {
      return { iid, kind: entry.__type ?? "unknown" };
    }
    const vs = get(map, refId((entry.vsettings as unknown[] | undefined)?.[0]));
    const rs = get(map, refId(vs?.rs));
    const raw = get(map, refId(vs?.text));
    const children = (Array.isArray(entry.children) ? entry.children : []).map(refId).filter(Boolean) as string[];
    return {
      iid, kind: "tag", tag: entry.tag, name: entry.name,
      text: raw?.__type === "RawText" ? String(raw.text ?? "").slice(0, 5000) : undefined,
      styles: rs?.__type === "RuleSet" ? rs.values : {},
      children: depth < depthLimit ? children.map(child => walk(child, depth + 1)) : [],
      ...(depth >= depthLimit && children.length ? { moreChildren: children.length } : {}),
    };
  };
  return { tree: walk(rootId, 0), visited: seen.size, truncated };
}
export function plasmicUiTools(ctx: PlasmicCtx): ToolDef[] {
  const c = ctx.client;
  const projectId = z.string().min(1);
  const branchId = z.string().optional();
  const dryRun = z.boolean().optional();
  const key = z.string().min(8).max(120).optional();
  const write = async (
    tool: string, pid: string, target: string, idem: string, preview: boolean,
    perform: () => Promise<{ revision: number; dryRun: boolean; changed: string[]; created?: string[] }>,
  ) => {
    const op = () => writeOp(ctx, tool, pid, target, JSON.stringify({ tool, target }), perform);
    if (preview) return { ...(await op()), deduped: false };
    const value = await idempotent(ctx.stateDir + "/idempotency", "live:" + tool + ":" + pid + ":" + idem, op);
    return { ...value.result, deduped: value.deduped };
  };
  return [
    {
      name: "plasmic_read_ui_outline",
      description: "Read one editable page/component as a bounded native TplTag tree with text and styles; no raw project secrets.",
      annotations: { readOnlyHint: true },
      schema: {
        projectId, componentId: z.string().min(1), branchId,
        depth: z.number().int().min(1).max(7).optional(),
        maxNodes: z.number().int().min(1).max(120).optional(),
      },
      handler: async a => {
        const rev = await c.getProjectRev(a.projectId as string, a.branchId as string | undefined);
        const map = rev.bundle.map as EntryMap;
        const entry = map[a.componentId as string];
        if (entry?.__type !== "Component") throw new Error("COMPONENT_NOT_FOUND");
        const root = refId(entry.tplTree);
        if (!root) throw new Error("COMPONENT_ROOT_NOT_FOUND");
        return {
          revision: rev.revision, componentId: a.componentId,
          ...sanitizeOutline(map, root, (a.depth as number | undefined) ?? 5,
            (a.maxNodes as number | undefined) ?? 90),
        };
      },
    },
    {
      name: "plasmic_append_ui_tree",
      description: "Append a semantically structured, editable native UI tree (text, typography, flex/grid CSS) to an existing TplTag, in one revisioned WAB mutation. Defaults to dryRun; no arbitrary HTML or JS.",
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
      schema: {
        projectId, branchId, parentElementId: z.string().min(1),
        nodes: z.array(nodeSchema).min(1).max(20),
        dryRun, idempotencyKey: key,
      },
      handler: async a => {
        const nodes = a.nodes as UiNode[];
        countNodes(nodes);
        const preview = a.dryRun !== false;
        if (!preview && !a.idempotencyKey) throw new Error("IDEMPOTENCY_KEY_REQUIRED");
        return write("plasmic_append_ui_tree", a.projectId as string,
          a.parentElementId as string, a.idempotencyKey as string, preview, async () => {
            let created: string[] = [];
            const result = await c.mutate(a.projectId as string,
              a.branchId as string | undefined,
              (bundle: BundleDoc) => {
                const plan = planNativeTree(bundle.map as EntryMap, a.parentElementId as string, nodes);
                created = plan.created;
                return { map: plan.patch };
              }, { dryRun: preview, saveMode: "full" });
            return { ...result, created, nodeCount: created.length };
          });
      },
    },
    {
      name: "plasmic_batch_set_styles",
      description: "Update CSS RuleSet values of several native Plasmic nodes together, in a single revision; rejects shared styles and unsafe CSS. Defaults to dryRun.",
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
      schema: {
        projectId, branchId, dryRun, idempotencyKey: key,
        edits: z.array(z.object({
          elementId: z.string().min(1), styles: stylesSchema,
        }).strict()).min(1).max(25),
      },
      handler: async a => {
        const edits = a.edits as Array<{ elementId: string; styles: Record<string, string> }>;
        if (new Set(edits.map(e => e.elementId)).size !== edits.length) {
          throw new Error("DUPLICATE_ELEMENT_ID");
        }
        for (const e of edits) validateUiStyles(e.styles);
        const preview = a.dryRun !== false;
        if (!preview && !a.idempotencyKey) throw new Error("IDEMPOTENCY_KEY_REQUIRED");
        return write("plasmic_batch_set_styles", a.projectId as string,
          "multi:" + edits.length, a.idempotencyKey as string, preview, async () =>
            c.mutate(a.projectId as string, a.branchId as string | undefined,
              (bundle: BundleDoc) => {
                const map = bundle.map as EntryMap, patch: EntryMap = {};
                for (const e of edits) {
                  const tag = get(map, e.elementId);
                  if (tag?.__type !== "TplTag") throw new Error("NOT_TPLTAG " + e.elementId);
                  const vs = get(map, refId((tag.vsettings as unknown[] | undefined)?.[0]));
                  const rsId = refId(vs?.rs), rs = get(map, rsId);
                  if (!rs || rs.__type !== "RuleSet" || !rsId) throw new Error("RULESET_NOT_FOUND " + e.elementId);
                  const ownerRefs = Object.values(map).filter(x =>
                    x.__type === "VariantSetting" && refId(x.rs) === rsId).length;
                  if (ownerRefs > 1) throw new Error("SHARED_RULESET " + rsId);
                  if (patch[rsId]) throw new Error("DUPLICATE_RULESET " + rsId);
                  patch[rsId] = { ...rs, values: { ...(rs.values as object ?? {}), ...e.styles } };
                }
                return { map: patch };
              }, { dryRun: preview })
        );
      },
    },
  ];
}
