// ZARI-229 DOD-02/DOD-03 regression matrix over a local WAB fixture.
// No network, no credentials, no real Plasmic project: this proves the catalog
// and composition contracts, not a live WAB write. Live authenticated E2E
// remains a separate gate (Service Auth / Release).
import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PlasmicClient } from "../libs/plasmic-client/client.ts";
import { plasmicTools } from "../services/plasmic-mcp/tools.ts";
import { resetCatalogCache } from "../services/plasmic-mcp/catalog-tools.ts";

type Map = Record<string, Record<string, unknown>>;

const baseModel = () => ({
  ftText: { __type: "FunctionType", name: "text" },
  ftSlot: { __type: "FunctionType", name: "slot" },
  pTitle: { __type: "Param", name: "title", type: { __ref: "ftText" }, defaultExpr: null },
  pSlot: { __type: "Param", name: "children", type: { __ref: "ftSlot" }, defaultExpr: null },
});

const projectOne = (): Map => ({
  ...baseModel(),
  site: { __type: "Site", name: "Site", components: [{ __ref: "card" }, { __ref: "hero" }], pageArenas: [] },
  card: {
    __type: "Component", name: "Card", uuid: "u-card", params: [{ __ref: "pTitle" }],
    tplTree: { __ref: "cardRoot" }, vsettings: [{ __ref: "cardVs" }],
  },
  cardRoot: { __type: "TplTag", tag: "div", name: "card-root", children: [], vsettings: [{ __ref: "cardVs2" }] },
  cardVs2: { __type: "VariantSetting", variants: [{ __ref: "variant1" }], attrs: {}, rs: { __ref: "cardRs2" }, args: [] },
  cardRs2: { __type: "RuleSet", values: { padding: "16px" }, mixins: [] },
  hero: {
    __type: "Component", name: "Hero", uuid: "u-hero", params: [{ __ref: "pSlot" }],
    tplTree: { __ref: "heroRoot" }, vsettings: [{ __ref: "heroVs" }],
  },
  heroRoot: { __type: "TplTag", tag: "section", name: "hero-root", children: [], vsettings: [{ __ref: "heroVs2" }] },
  heroVs2: { __type: "VariantSetting", variants: [{ __ref: "variant1" }], attrs: {}, rs: { __ref: "heroRs2" }, args: [] },
  heroRs2: { __type: "RuleSet", values: { padding: "48px" }, mixins: [] },
  cardVs: { __type: "VariantSetting", variants: [{ __ref: "variant1" }], attrs: {}, rs: { __ref: "cardRs" }, args: [] },
  cardRs: { __type: "RuleSet", values: {}, mixins: [] },
  heroVs: { __type: "VariantSetting", variants: [{ __ref: "variant1" }], attrs: {}, rs: { __ref: "heroRs" }, args: [] },
  heroRs: { __type: "RuleSet", values: {}, mixins: [] },
  variant1: { __type: "Variant", name: "base" },
  pageHome: {
    __type: "Component", name: "Home", uuid: "u-page", pageMeta: { __ref: "pmHome" },
    tplTree: { __ref: "root" }, vsettings: [{ __ref: "cardVs" }],
  },
  pmHome: { __type: "PageMeta", path: "/" },
  root: {
    __type: "TplTag", tag: "main", name: "root",
    children: [{ __ref: "cardInst" }, { __ref: "heroInst" }], vsettings: [{ __ref: "cardVs" }],
  },
  heroInst: {
    __type: "TplComponent", name: "HeroInst", component: { __ref: "hero" },
    parent: { __ref: "root" }, vsettings: [{ __ref: "heroInstVs" }], children: [],
  },
  heroInstVs: {
    __type: "VariantSetting", variants: [{ __ref: "variant1" }], attrs: {},
    rs: { __ref: "heroInstRs" }, args: [], dataCond: null, dataRep: null,
  },
  heroInstRs: { __type: "RuleSet", values: { margin: "0px" }, mixins: [] },
  cardInst: {
    __type: "TplComponent", name: "CardInst", component: { __ref: "card" },
    parent: { __ref: "root" }, vsettings: [{ __ref: "instVs" }], children: [],
  },
  instVs: {
    __type: "VariantSetting", variants: [{ __ref: "variant1" }], attrs: {},
    rs: { __ref: "instRs" }, args: [], dataCond: null, dataRep: null,
  },
  instRs: { __type: "RuleSet", values: { margin: "0px" }, mixins: [] },
  token1: { __type: "StyleToken", name: "brand", value: "#0f0f0f" },
});

const projectTwo = (): Map => ({
  ...baseModel(),
  site2: { __type: "Site", name: "Site", components: [{ __ref: "badge" }], pageArenas: [] },
  badge: {
    __type: "Component", name: "Badge", uuid: "u-badge", params: [],
    tplTree: { __ref: "badgeRoot" }, vsettings: [{ __ref: "badgeVs" }],
  },
  badgeRoot: { __type: "TplTag", tag: "span", name: "badge-root", children: [], vsettings: [{ __ref: "badgeVs" }] },
  badgeVs: { __type: "VariantSetting", variants: [{ __ref: "variant1" }], attrs: {}, rs: { __ref: "badgeRs" }, args: [] },
  badgeRs: { __type: "RuleSet", values: { borderRadius: "4px" }, mixins: [] },
  variant1: { __type: "Variant", name: "base" },
  badgeHolder: { __type: "TplTag", tag: "div", name: "holder", children: [{ __ref: "badgeInst" }], vsettings: [{ __ref: "badgeVs" }] },
  badgeInst: {
    __type: "TplComponent", name: "BadgeInst", component: { __ref: "badge" },
    parent: { __ref: "badgeHolder" }, vsettings: [{ __ref: "badgeInstVs" }], children: [],
  },
  badgeInstVs: { __type: "VariantSetting", variants: [{ __ref: "variant1" }], attrs: {}, rs: { __ref: "badgeInstRs" }, args: [] },
  badgeInstRs: { __type: "RuleSet", values: {}, mixins: [] },
});

async function setup() {
  resetCatalogCache();
  const bundles: Record<string, Map> = { "project-1": projectOne(), "project-2": projectTwo() };
  const revisions: Record<string, number> = { "project-1": 7, "project-2": 3 };
  let mutations = 0;
  const client = new PlasmicClient({
    baseUrl: "https://wab.fixture.invalid",
    fetchImpl: async () => { throw new Error("NO_NETWORK_IN_FIXTURE"); },
  });
  Object.assign(client, {
    getProjectRev: async (projectId: string) => {
      const bundle = bundles[projectId];
      if (!bundle) throw new Error(`Plasmic 404 /api/v1/projects/${projectId}: fixture has no such project`);
      return { revision: revisions[projectId], revId: `rev-${projectId}`, project: { id: projectId, name: projectId }, bundle: { map: structuredClone(bundle) } };
    },
    mutate: async (
      projectId: string,
      _branchId: string | undefined,
      fn: (b: { map: Map }) => { map?: Map; toDeleteIids?: string[] } | null,
      opts?: { dryRun?: boolean },
    ) => {
      const map = bundles[projectId]!;
      const patch = fn({ map: structuredClone(map) });
      const changed = [
        ...Object.keys(patch?.map ?? {}),
        ...(patch?.toDeleteIids ?? []).map((i) => `-${i}`),
      ];
      if (!patch || changed.length === 0) return { revision: revisions[projectId]!, dryRun: true, changed: [] };
      if (opts?.dryRun) return { revision: revisions[projectId]!, dryRun: true, changed };
      mutations += 1;
      bundles[projectId] = { ...map, ...(patch.map ?? {}) };
      revisions[projectId] = revisions[projectId]! + 1;
      return { revision: revisions[projectId]!, dryRun: false, changed };
    },
  });
  const stateDir = await mkdtemp(join(tmpdir(), "zari229-compose-"));
  const tools = plasmicTools({
    client, stateDir, auditFile: join(stateDir, "audit.jsonl"), agent: "zari-229-test",
  });
  const tool = (name: string) => {
    const found = tools.find((t) => t.name === name);
    assert.ok(found, `missing tool ${name}`);
    return found!;
  };
  return {
    tool,
    mapNow: (projectId = "project-1") => bundles[projectId]!,
    revisionNow: (projectId = "project-1") => revisions[projectId]!,
    mutationCount: () => mutations,
  };
}

test("catalog: search filters, paginates and keys the index by project/branch/revision", async () => {
  const { tool } = await setup();
  const search = tool("plasmic_search_components");
  const all = await search.handler({ projectId: "project-1", kind: "component" }) as {
    total: number; items: Array<{ id: string; name: string; kind: string; instanceCount: number }>;
    catalogKey: string; cacheHit: boolean;
  };
  assert.deepEqual(all.items.map((i) => i.name), ["Card", "Hero"]);
  assert.equal(all.total, 2);
  assert.match(all.catalogKey, /^catalog:[0-9a-f]{16}$/);
  assert.equal(all.cacheHit, false);
  assert.equal(all.items.find((i) => i.id === "card")!.instanceCount, 1);

  const again = await search.handler({ projectId: "project-1", kind: "component" }) as { cacheHit: boolean };
  assert.equal(again.cacheHit, true, "same revision must reuse the index");

  const page = await search.handler({ projectId: "project-1", kind: "page" }) as {
    items: Array<{ id: string; kind: string; pagePath?: string }>;
  };
  assert.deepEqual(page.items.map((i) => i.id), ["pageHome"]);
  assert.equal(page.items[0]!.pagePath, "/");

  const paged = await search.handler({ projectId: "project-1", limit: 1, offset: 1, kind: "component" }) as {
    items: Array<{ name: string }>; total: number; offset: number; limit: number;
  };
  assert.deepEqual(paged.items.map((i) => i.name), ["Hero"]);
  assert.equal(paged.total, 2);
  assert.equal(paged.offset, 1);

  const filtered = await search.handler({ projectId: "project-1", query: "car" }) as {
    items: Array<{ name: string }>;
  };
  assert.deepEqual(filtered.items.map((i) => i.name), ["Card"]);
});

test("catalog: a new revision invalidates the index and the cache key moves", async () => {
  const { tool, mapNow, revisionNow } = await setup();
  const search = tool("plasmic_search_components");
  const first = await search.handler({ projectId: "project-1" }) as { catalogKey: string };
  const before = revisionNow();
  await tool("plasmic_insert").handler({
    projectId: "project-1", elementId: "extraTag",
    entry: { __type: "TplTag", name: "extra" }, idempotencyKey: "cache-bump",
  });
  assert.equal(revisionNow(), before + 1);
  const second = await search.handler({ projectId: "project-1" }) as { catalogKey: string; cacheHit: boolean };
  assert.equal(second.cacheHit, false, "stale revision must never be served");
  assert.notEqual(second.catalogKey, first.catalogKey);
  assert.ok(mapNow().extraTag);
});

test("catalog: project isolation — no cross-project catalog or spec leakage", async () => {
  const { tool } = await setup();
  const search = tool("plasmic_search_components");
  const two = await search.handler({ projectId: "project-2" }) as { items: Array<{ id: string; name: string }> };
  assert.deepEqual(two.items.map((i) => i.id), ["badge"]);
  const one = await search.handler({ projectId: "project-1", kind: "component" }) as {
    items: Array<{ id: string }>;
  };
  assert.equal(one.items.some((i) => i.id === "badge"), false);

  const spec = tool("plasmic_get_component_spec");
  await assert.rejects(
    spec.handler({ projectId: "project-2", componentId: "card" }),
    /COMPONENT_NOT_FOUND/,
    "a component id from another project must not resolve",
  );
  await assert.rejects(
    search.handler({ projectId: "project-missing" }),
    /404/,
  );
});

test("catalog: component spec exposes declared params, slots, instances and provenance honestly", async () => {
  const { tool } = await setup();
  const spec = tool("plasmic_get_component_spec");
  const card = await spec.handler({ projectId: "project-1", componentId: "card" }) as {
    component: {
      id: string; kind: string; params: Array<{ name: string; typeName: string | null }>;
      slots: Array<{ name: string }>; slotsAvailable: boolean;
      instances: Array<{ id: string; parentId: string | null }>;
      previewAvailable: boolean;
    };
    provenance: { projectId: string; branch: string; revision: number };
  };
  assert.equal(card.component.id, "card");
  assert.equal(card.component.kind, "component");
  assert.deepEqual(card.component.params.map((p) => p.name), ["title"]);
  assert.equal(card.component.params[0]!.typeName, "text");
  assert.deepEqual(card.component.slots, []);
  assert.equal(card.component.slotsAvailable, true);
  assert.deepEqual(card.component.instances, [{ id: "cardInst", parentId: "root" }]);
  assert.equal(card.component.previewAvailable, false, "no preview URL may be invented");
  assert.deepEqual(card.provenance, { projectId: "project-1", branch: "main", revision: 7 });

  const hero = await spec.handler({ projectId: "project-1", componentId: "hero" }) as {
    component: { slots: Array<{ name: string; typeName: string }> };
  };
  assert.deepEqual(hero.component.slots.map((s) => s.name), ["children"]);
  assert.equal(hero.component.slots[0]!.typeName, "slot");

  await assert.rejects(
    spec.handler({ projectId: "project-1", componentId: "root" }),
    /NOT_A_COMPONENT/,
    "a TplTag id is not a component spec",
  );
});

test("composition: plan is read-only and returns deterministic entries", async () => {
  const { tool, mapNow, revisionNow, mutationCount } = await setup();
  const plan = await tool("plasmic_plan_composition").handler({
    projectId: "project-1", parentElementId: "root",
    items: [{ componentId: "card" }, { componentId: "hero" }],
  }) as {
    revision: number; dryRun: boolean; inserted: Array<{ componentId: string; instanceId: string }>;
    parentChildrenAfter: number; entriesToCreate: number; warnings: string[];
  };
  assert.equal(plan.dryRun, true);
  assert.equal(plan.revision, 7);
  assert.deepEqual(plan.inserted.map((i) => i.componentId), ["card", "hero"]);
  assert.equal(new Set(plan.inserted.map((i) => i.instanceId)).size, 2);
  assert.equal(plan.parentChildrenAfter, 4);
  assert.ok(plan.entriesToCreate >= 2);
  assert.equal(mutationCount(), 0, "planning must not mutate");
  assert.equal(revisionNow(), 7);
  assert.equal(
    (mapNow().root!.children as unknown[]).length, 2,
    "parent children untouched by the plan",
  );
});

test("composition: live compose wires ordered instances with private style entries", async () => {
  const { tool, mapNow, revisionNow } = await setup();
  // A plan made with the same idempotency key must predict the applied ids.
  const predicted = await tool("plasmic_plan_composition").handler({
    projectId: "project-1", parentElementId: "root", index: 0,
    items: [{ componentId: "card", props: { title: "Witaj" } }, { componentId: "hero" }],
    idempotencyKey: "compose-live-1",
  }) as { inserted: Array<{ instanceId: string }> };
  const out = await tool("plasmic_compose_components").handler({
    projectId: "project-1", parentElementId: "root", index: 0,
    items: [{ componentId: "card", props: { title: "Witaj" } }, { componentId: "hero" }],
    dryRun: false, idempotencyKey: "compose-live-1",
  }) as {
    revision: number; dryRun: boolean; deduped: boolean;
    plan: Array<{ componentId: string; instanceId: string }>; parentChildrenAfter: number;
  };
  assert.equal(out.revision, 8);
  assert.equal(out.dryRun, false);
  assert.equal(out.deduped, false);
  assert.equal(out.parentChildrenAfter, 4);
  assert.deepEqual(
    out.plan.map((p) => p.instanceId),
    predicted.inserted.map((p) => p.instanceId),
    "plan and apply must agree when they share an idempotency key",
  );

  const map = mapNow();
  const children = (map.root!.children as Array<{ __ref: string }>).map((c) => c.__ref);
  assert.deepEqual(children, [out.plan[0]!.instanceId, out.plan[1]!.instanceId, "cardInst", "heroInst"]);
  for (const inserted of out.plan) {
    const instance = map[inserted.instanceId]!;
    assert.equal(instance.__type, "TplComponent");
    assert.equal((instance.component as { __ref: string }).__ref, inserted.componentId);
    assert.equal((instance.parent as { __ref: string }).__ref, "root");
    const vsId = (instance.vsettings as Array<{ __ref: string }>)[0]!.__ref;
    assert.notEqual(vsId, "instVs", "the clone must not share the template VariantSetting");
    const vs = map[vsId]!;
    const rsId = (vs.rs as { __ref: string }).__ref;
    assert.notEqual(rsId, "instRs", "the clone must not share the template RuleSet");
  }
  // The template instance is untouched.
  assert.deepEqual(map.cardInst!.vsettings, [{ __ref: "instVs" }]);
  assert.deepEqual((map.instRs as { values: unknown }).values, { margin: "0px" });

  // Props land as a param-bound Arg with a private expression.
  const cardVsId = (map[out.plan[0]!.instanceId]!.vsettings as Array<{ __ref: string }>)[0]!.__ref;
  const args = (map[cardVsId] as { args: Array<{ param: { __ref: string }; expr: { __ref: string } }> }).args;
  assert.equal(args.length, 1);
  assert.equal(args[0]!.param.__ref, "pTitle");
  assert.equal((map[args[0]!.expr.__ref] as { code: string }).code, "\"Witaj\"");

  // Replay is a no-op, not a duplicate node.
  const replay = await tool("plasmic_compose_components").handler({
    projectId: "project-1", parentElementId: "root", index: 0,
    items: [{ componentId: "card", props: { title: "Witaj" } }, { componentId: "hero" }],
    dryRun: false, idempotencyKey: "compose-live-1",
  }) as { deduped: boolean; revision: number };
  assert.equal(replay.deduped, true);
  assert.equal(revisionNow(), 8);
  assert.equal((mapNow().root!.children as unknown[]).length, 4);
});

test("composition: negatives are structured errors, never fake success", async () => {
  const { tool, revisionNow } = await setup();
  const compose = tool("plasmic_compose_components");
  const cases: Array<[string, Record<string, unknown>, RegExp]> = [
    ["missing parent", { parentElementId: "nope", items: [{ componentId: "card" }] }, /PARENT_NOT_FOUND/],
    ["parent is a component", { parentElementId: "card", items: [{ componentId: "hero" }] }, /PARENT_NOT_A_CONTAINER/],
    ["page as child", { parentElementId: "root", items: [{ componentId: "pageHome" }] }, /PAGE_COMPONENT_NOT_INSTANTIABLE/],
    ["unknown component", { parentElementId: "root", items: [{ componentId: "ghost" }] }, /UNKNOWN_COMPONENT/],
    ["undeclared prop", { parentElementId: "root", items: [{ componentId: "card", props: { subtitle: "x" } }] }, /PROP_UNSUPPORTED/],
    ["index out of range", { parentElementId: "root", index: 9, items: [{ componentId: "card" }] }, /INDEX_OUT_OF_RANGE/],
    ["empty composition", { parentElementId: "root", items: [] }, /EMPTY_COMPOSITION/],
  ];
  for (const [label, args, pattern] of cases) {
    await assert.rejects(
      // eslint-disable-next-line no-await-in-loop
      compose.handler({ projectId: "project-1", ...args }),
      pattern,
      label,
    );
  }
  await assert.rejects(
    compose.handler({ projectId: "project-1", parentElementId: "root", items: [{ componentId: "card" }], dryRun: false }),
    /IDEMPOTENCY_KEY_REQUIRED/,
  );
  assert.equal(revisionNow(), 7, "rejected compositions must not reach WAB");
});

test("composition: uncloneable templates fail closed with a named reason", async () => {
  const { tool, mapNow } = await setup();
  const plan = tool("plasmic_plan_composition");
  const map = mapNow();
  // A template carrying slot content cannot be cloned without slot semantics.
  map.heroInst = { ...map.heroInst!, children: [{ __ref: "root" }] };
  await assert.rejects(
    plan.handler({ projectId: "project-1", parentElementId: "root", items: [{ componentId: "hero" }] }),
    /SLOT_CONTENT_CLONE_UNSUPPORTED/,
  );
  // An instance without VariantSetting cannot be given private style ownership.
  map.cardInst = { ...map.cardInst!, vsettings: [] };
  await assert.rejects(
    plan.handler({ projectId: "project-1", parentElementId: "root", items: [{ componentId: "card" }] }),
    /VARIANT_SETTING_MISSING/,
  );
  // A component with no instance at all cannot be composed.
  delete map.heroInst;
  await assert.rejects(
    plan.handler({ projectId: "project-1", parentElementId: "root", items: [{ componentId: "hero" }] }),
    /NO_INSTANCE_TEMPLATE/,
  );
});

test("composition: idempotency key reuse with different input is rejected before WAB", async () => {
  const { tool, revisionNow, mutationCount } = await setup();
  const compose = tool("plasmic_compose_components");
  await compose.handler({
    projectId: "project-1", parentElementId: "root", index: 0,
    items: [{ componentId: "card" }], dryRun: false, idempotencyKey: "reused-key-1",
  });
  const afterFirst = revisionNow();
  const mutationsAfterFirst = mutationCount();
  await assert.rejects(
    compose.handler({
      projectId: "project-1", parentElementId: "root", index: 0,
      items: [{ componentId: "hero" }], dryRun: false, idempotencyKey: "reused-key-1",
    }),
    /IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_INPUT/,
  );
  assert.equal(revisionNow(), afterFirst);
  assert.equal(mutationCount(), mutationsAfterFirst);
});

test("use_component: clone owns private style entries and is attached to the parent", async () => {
  const { tool, mapNow } = await setup();
  const out = await tool("plasmic_use_component").handler({
    projectId: "project-1", componentId: "card", parentElementId: "root", index: 0,
    idempotencyKey: "use-private-1",
  }) as { id: string; parentAttached: boolean; changed: string[] };
  assert.equal(out.parentAttached, true);
  const map = mapNow();
  const children = (map.root!.children as Array<{ __ref: string }>).map((c) => c.__ref);
  assert.equal(children[0], out.id, "the new instance is wired into the parent children");
  assert.equal(children[1], "cardInst");
  const vsId = (map[out.id]!.vsettings as Array<{ __ref: string }>)[0]!.__ref;
  assert.notEqual(vsId, "instVs");
  const rsId = (map[vsId] as { rs: { __ref: string } }).rs.__ref;
  assert.notEqual(rsId, "instRs");
  // Editing the clone must not leak into the template instance.
  await tool("plasmic_set_styles").handler({
    projectId: "project-1", elementId: out.id, styles: { color: "#123456" },
  });
  const templateRs = mapNow()[(mapNow().instVs as { rs: { __ref: string } }).rs.__ref] as { values: Record<string, string> };
  assert.equal(templateRs.values.color, undefined, "template RuleSet must stay untouched");
});

test("use_component: an unattached clone is reported, not silently orphaned", async () => {
  const { tool, mapNow } = await setup();
  // project-2's badgeInst has a parent, so remove the target by cloning the
  // badge template into a container-free component instance scenario: we use
  // project-1's card template with an explicit empty parent list instead.
  const map = mapNow();
  map.cardInst = { ...map.cardInst!, parent: undefined };
  const out = await tool("plasmic_use_component").handler({
    projectId: "project-1", componentId: "card", idempotencyKey: "use-unattached-1",
  }) as { id: string; parentAttached: boolean; warning?: string };
  assert.equal(out.parentAttached, false);
  assert.match(String(out.warning), /INSTANCE_NOT_ATTACHED/);
  assert.ok(mapNow()[out.id], "the instance still exists so the caller can wire it explicitly");
});
