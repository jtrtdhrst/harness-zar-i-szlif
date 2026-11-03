"""Production schema-2 Hermes approved full-bundle skill sync tests (stdlib only)."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "sync_profile_skills.py"
SPEC = importlib.util.spec_from_file_location("sync_profile_skills", MODULE_PATH)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)

ROLES = (
    "ceo", "cho", "cmo", "coo", "cpo", "cto", "designer",
    "email-creative", "engineer", "harness-engineer",
    "lifecycle-ops", "mascot-designer", "mcp-engineer", "ui-qa",
)
COMPANY = "9894e3c2-3317-46ca-8c72-7a442a76a78e"
SKILL = "test-approved-skill"


class SkillBundleSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.source, self.profiles = base / "source", base / "profiles"
        self.manifest = base / "approved.json"
        self.canonical = self.source / COMPANY / SKILL
        (self.canonical / "references").mkdir(parents=True)
        (self.canonical / "scripts").mkdir()
        (self.canonical / "SKILL.md").write_text("# Approved skill\n", encoding="utf-8")
        (self.canonical / "references" / "guide.md").write_text("Safe reference\n", encoding="utf-8")
        (self.canonical / "scripts" / "run.sh").write_text("#!/bin/sh\necho approved\n", encoding="utf-8")
        (self.canonical / "scripts" / "run.sh").chmod(0o755)
        for role in ROLES:
            (self.profiles / role / "skills" / "company-managed").mkdir(parents=True)
        self.pin = {
            str(p.relative_to(self.canonical)): sync.sha(p)
            for p in self.canonical.rglob("*") if p.is_file()
        }
        self.doc = {
            "schema_version": 2,
            "source_company_id": COMPANY,
            "profiles": {role: [SKILL] for role in ROLES},
            "approved_sha256": {SKILL: self.pin["SKILL.md"]},
            "approved_files_sha256": {SKILL: dict(self.pin)},
        }
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.doc), encoding="utf-8")

    def call(self, apply=False):
        return sync.run(self.manifest, self.source, self.profiles, apply)

    def destination(self, role="cho", asset="SKILL.md"):
        return self.profiles / role / "skills" / "company-managed" / SKILL / asset

    def test_full_bundle_apply_then_idempotent_audit(self):
        before = self.call()
        self.assertEqual(before["profiles"], 14)
        self.assertEqual(before["skills_checked"], 14)
        self.assertEqual(before["files_checked"], 42)
        self.assertEqual(before["mismatched_after"], 42)
        self.assertEqual(self.call(True)["mismatched_after"], 0)
        after = self.call()
        self.assertEqual(after["mismatched_after"], 0)
        for role in ROLES:
            for asset, expected in self.pin.items():
                self.assertEqual(sync.sha(self.destination(role, asset)), expected)
        self.assertTrue(os.access(self.destination("cho", "scripts/run.sh"), os.X_OK))

    def test_unapproved_source_sha_blocks_before_write(self):
        (self.canonical / "SKILL.md").write_text("# Tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_SOURCE_SHA"):
            self.call(True)
        self.assertFalse(self.destination().exists())

    def test_unpinned_extra_file_blocks_before_write(self):
        (self.canonical / "references" / "unapproved.md").write_text("not pinned", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_SOURCE_SHA"):
            self.call(True)
        self.assertFalse(self.destination().exists())

    def test_source_symlink_rejected(self):
        (self.canonical / "references" / "leak.txt").symlink_to(self.canonical / "SKILL.md")
        with self.assertRaisesRegex(ValueError, "linked canonical skill file"):
            self.call(True)

    def test_destination_symlink_rejected(self):
        self.destination("cho").parent.symlink_to(self.canonical, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe destination skill"):
            self.call(True)

    def test_missing_nested_file_pin_rejected(self):
        del self.doc["approved_files_sha256"][SKILL]["references/guide.md"]
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_SOURCE_SHA"):
            self.call(True)

    def test_missing_manifest_file_pin_set_rejected(self):
        self.doc.pop("approved_files_sha256")
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "approved head and full-file hashes"):
            self.call(True)

    def test_wrong_schema_rejected(self):
        self.doc["schema_version"] = 1
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "schema 2"):
            self.call()

    def test_destination_drift_repaired_after_verified_source(self):
        self.call(True)
        self.destination("engineer", "references/guide.md").write_text("changed", encoding="utf-8")
        self.assertEqual(self.call()["drift_files"], 1)
        self.assertEqual(self.call(True)["mismatched_after"], 0)
        self.assertEqual(sync.sha(self.destination("engineer", "references/guide.md")), self.pin["references/guide.md"])

    def test_only_role_assigned_skill_receives_files(self):
        self.doc["profiles"] = {role: [SKILL] if role == "cho" else [] for role in ROLES}
        self.write_manifest()
        self.assertEqual(self.call(True)["files_checked"], 3)
        self.assertTrue(self.destination("cho").is_file())
        self.assertFalse(self.destination("cto").exists())

    def test_duplicate_skill_assignment_rejected(self):
        self.doc["profiles"]["cho"] = [SKILL, SKILL]
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "duplicate skills"):
            self.call()

    def test_pinned_absolute_asset_path_rejected(self):
        self.doc["approved_files_sha256"][SKILL]["/tmp/evil"] = "0" * 64
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_SOURCE_SHA|unsafe relative"):
            self.call()


if __name__ == "__main__":
    unittest.main()
