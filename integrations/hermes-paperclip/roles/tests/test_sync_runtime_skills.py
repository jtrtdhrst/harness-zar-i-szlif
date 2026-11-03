"""Role-scoped Paperclip runtime skill pins; no Docker or real credentials required."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

FILE = Path(__file__).resolve().parents[1] / "sync_runtime_skills.py"
SPEC = importlib.util.spec_from_file_location("sync_runtime_skills", FILE)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)

COMPANY = sync.COMPANY
ROOT = f"/paperclip/instances/default/skills/{COMPANY}"
UNIVERSAL = ["paperclip", "complain", "suggestion-box"]
SPECS = {
    f"paperclipai/paperclip/{name}": (name, f"/app/skills/{name}")
    for name in UNIVERSAL
}
SPECS.update({
    "local/5ee1f0f6fb/kompas-brand-email":
        ("kompas-brand-email", f"{ROOT}/kompas-brand-email"),
    "paperclipai/bundled/paperclip-operations/status-card-query":
        ("status-card-query--5374d5ae20", f"{ROOT}/__catalog__/status-card-query--5374d5ae20"),
    "paperclipai/paperclip/paperclip-opencode-health":
        ("paperclip-opencode-health", f"{ROOT}/__runtime__/paperclip-opencode-health"),
})


class RuntimeSkillSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.sources = root / "source"
        self.profiles = root / "profiles"
        self.manifest = root / "pins.json"
        source_specs = {}
        for key, (name, source) in SPECS.items():
            folder = self.sources / name
            (folder / "references").mkdir(parents=True)
            (folder / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
            (folder / "references" / "guide.md").write_text("Approved reference\n", encoding="utf-8")
            source_specs[key] = {"runtime_name": name, "source_path": source,
                                 "approved_files_sha256": {
                                     "SKILL.md": sync.digest(folder / "SKILL.md"),
                                     "references/guide.md": sync.digest(folder / "references/guide.md"),
                                 }}
        universal_keys = [f"paperclipai/paperclip/{name}" for name in UNIVERSAL]
        roles = {role: list(universal_keys) for role in sync.ROLES}
        roles["coo"].append("paperclipai/bundled/paperclip-operations/status-card-query")
        roles["harness-engineer"].append("paperclipai/paperclip/paperclip-opencode-health")
        roles["email-creative"].append("local/5ee1f0f6fb/kompas-brand-email")
        self.doc = {
            "schema_version": 1, "company_id": COMPANY,
            "roles": {r: sorted(skills) for r, skills in roles.items()},
            "sources": source_specs,
        }
        for role in sync.ROLES:
            (self.profiles / role / "skills").mkdir(parents=True)
        self.write()

    def write(self):
        self.manifest.write_text(json.dumps(self.doc) + "\n", encoding="utf-8")

    def run_sync(self, apply=False):
        return sync.run(self.manifest, self.profiles, apply, self.sources)

    def dest(self, role, name, asset="SKILL.md"):
        return self.profiles / role / "skills" / "paperclip-managed" / name / asset

    def test_full_pinned_45_assignments_and_no_leakage(self):
        before = self.run_sync()
        self.assertEqual((before["profiles"], before["assignments"], before["unique_skills"]),
                         (14, 45, 6))
        self.assertEqual(before["files_checked"], 90)
        self.assertEqual(before["mismatched_after"], 90)
        self.assertEqual(self.run_sync(True)["mismatched_after"], 0)
        self.assertEqual(self.run_sync()["mismatched_after"], 0)
        for role in sync.ROLES:
            for name in UNIVERSAL:
                self.assertTrue(self.dest(role, name).is_file())
        self.assertFalse(self.dest("cho", "kompas-brand-email").exists())
        self.assertFalse(self.dest("coo", "kompas-brand-email").exists())
        self.assertFalse(self.dest("ceo", "paperclip-opencode-health").exists())
        self.assertTrue(self.dest("email-creative", "kompas-brand-email").exists())
        self.assertTrue(self.dest("coo", "status-card-query--5374d5ae20").exists())
        self.assertTrue(self.dest("harness-engineer", "paperclip-opencode-health").exists())

    def test_atomic_idempotent_drift_repair(self):
        self.run_sync(True)
        path = self.dest("cho", "paperclip", "references/guide.md")
        path.write_text("drift", encoding="utf-8")
        self.assertEqual(self.run_sync()["drift_files"], 1)
        self.assertEqual(self.run_sync(True)["mismatched_after"], 0)
        self.assertEqual(path.read_text(encoding="utf-8"), "Approved reference\n")

    def test_unapproved_source_change_blocks_before_first_write(self):
        (self.sources / "paperclip" / "SKILL.md").write_text("tamper", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_SOURCE_SHA"):
            self.run_sync(True)
        self.assertFalse(self.dest("cho", "complain").exists())

    def test_source_symlink_blocks(self):
        (self.sources / "complain" / "bad").symlink_to(self.sources / "paperclip" / "SKILL.md")
        with self.assertRaisesRegex(ValueError, "Symlink in approved"):
            self.run_sync(True)

    def test_unapproved_nested_file_blocks(self):
        (self.sources / "paperclip" / "references" / "other.md").write_text("bad", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_SOURCE_SHA"):
            self.run_sync(True)

    def test_wrong_schema_blocks(self):
        self.doc["schema_version"] = 2
        self.write()
        with self.assertRaisesRegex(ValueError, "metadata invalid"):
            self.run_sync()

    def test_cross_role_asset_would_fail_closed(self):
        self.run_sync(True)
        outsider = self.dest("cho", "kompas-brand-email")
        outsider.parent.mkdir(parents=True)
        outsider.write_text("not assigned", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_DESTINATION_FILES"):
            self.run_sync()

    def test_invalid_source_path_blocks(self):
        key = "paperclipai/paperclip/paperclip"
        self.doc["sources"][key]["source_path"] = "/tmp/rogue"
        self.write()
        with self.assertRaisesRegex(ValueError, "not on the approved allowlist"):
            self.run_sync()

    def test_fake_profile_added_blocks(self):
        self.doc["roles"]["hermes-test"] = self.doc["roles"]["cho"][:]
        self.write()
        with self.assertRaisesRegex(ValueError, "14 real roles"):
            self.run_sync()

    def test_special_skill_cannot_be_reassigned_to_cho(self):
        key = "paperclipai/bundled/paperclip-operations/status-card-query"
        self.doc["roles"]["coo"].remove(key)
        self.doc["roles"]["cho"].append(key)
        self.write()
        with self.assertRaisesRegex(ValueError, "UNAUTHORIZED_PROFILE_SKILL_ASSIGNMENT"):
            self.run_sync()

    def test_unsafe_destination_symlink_blocks(self):
        first = self.profiles / "cho" / "skills" / "paperclip-managed"
        first.symlink_to(self.sources, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unsafe per-profile destination"):
            self.run_sync()


if __name__ == "__main__":
    unittest.main()
