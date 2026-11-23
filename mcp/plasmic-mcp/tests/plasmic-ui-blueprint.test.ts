import assert from "node:assert/strict";
import test from "node:test";
import { planNativeTree, validateUiStyles } from "../services/plasmic-mcp/ui-tools.ts";

const fixture = () => ({
  parent: { __type: "TplTag", tag: "div", children: [], vsettings: [{ __ref: "vs" }] },
  vs: { __type: "VariantSetting", variants: [{ __ref: "base" }], rs: { __ref: "rs" } },
  base: { __type: "Variant", name: "base" },
  rs: { __type: "RuleSet", values: {} },
});
test("native UI blueprint preserves parent and all internal references", () => {
  const { patch, created } = planNativeTree(fixture(), "parent", [{
    tag: "section", name: "Hero", styles: { display: "flex", gap: "1rem" }, children: [
      { tag: "h1", text: "Żar i Szlif", styles: { color: "#D62839" } },
      { tag: "p", text: "Zacznij rozwijać drużynę" },
    ],
  }]);
  assert.equal(created.length, 3);
  assert.equal((patch.parent.children as { __ref: string }[]).length, 1);
  const existing = fixture();
  const merged: Record<string, Record<string, unknown>> = { ...existing, ...patch };
  for (const [iid, entry] of Object.entries(patch)) {
    assert.ok(entry.__type, iid + ": missing type");
    const refs: string[] = [];
    const walk = (v: unknown) => {
      if (Array.isArray(v)) v.forEach(walk);
      else if (v && typeof v === "object") {
        const o = v as Record<string, unknown>;
        if (typeof o.__ref === "string") refs.push(o.__ref);
        else Object.values(o).forEach(walk);
      }
    };
    walk(entry);
    for (const target of refs) assert.ok(target in merged, iid + " dangling " + target);
  }
  const rawTexts = Object.values(patch).filter(e => e.__type === "RawText");
  assert.equal(rawTexts.length, 2);
  assert.equal(rawTexts[0]!.markers instanceof Array, true);
});
test("blueprint rejects unsafe or overly broad edits", () => {
  assert.throws(() => validateUiStyles({ color: "url(javascript:alert(1))" }), /INVALID_STYLE/);
  assert.throws(() => planNativeTree(fixture(), "missing", [{ tag: "div" }]), /PARENT_NOT_TPLTAG/);
  assert.throws(() => planNativeTree(fixture(), "parent", [{ tag: "p", text: "hi", children: [{ tag: "span" }] }]), /TEXT_WITH_CHILDREN/);
  assert.throws(() => planNativeTree(fixture(), "parent", Array.from({ length: 61 }, () => ({ tag: "div" }))), /TREE_NODE_LIMIT/);
});
