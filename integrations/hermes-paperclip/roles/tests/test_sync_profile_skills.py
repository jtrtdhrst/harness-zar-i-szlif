"""Hermes per-profile approved skill sync tests (stdlib only)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "sync_profile_skills.py"
SPEC = importlib.util.spec_from_file_location("sync_profile_skills", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)

ROLES = (
    "ceo", "cho", "cmo", "coo", "cpo", "cto", "designer",
    "email-creative", "engineer", "harness-engineer",
    "lifecycle-ops", "mascot-designer", "mcp-engineer", "ui-qa",
)
COMPANY = "9894e3c2-3317-46ca-8c72-7a442a76a78e"
SKILL = "test-approved-skill"


class SkillSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "source"
        self.profiles = root / "profiles"
        self.manifest = root / "approved.json"
        canonical = self.source / COMPANY / SKILL
        canonical.mkdir(parents=True)
        (canonical / "SKILL.md").write_text("# Approved skill\n", encoding="utf-8")
        for role in ROLES:
            (self.profiles / role / "skills/company-managed").mkdir(parents=True)
        self.manifest_data = {
            "schema_version": 1,
            "source_company_id": COMPANY,
            "profiles": {role: [SKILL] for role in ROLES},
            "approved_sha256": {SKILL: sync.sha(canonical / "SKILL.md")},
        }
        self._write_manifest()

    def _write_manifest(self):
        self.manifest.write_text(json.dumps(self.manifest_data), encoding="utf-8")

    def test_audit_apply_and_idempotent_resync(self):
        before = sync.run(self.manifest, False, self.source, self.profiles)
        self.assertEqual(before["mismatched_before"], 14)
        applied = sync.run(self.manifest, True, self.source, self.profiles)
        self.assertEqual(applied["mismatched_after"], 0)
        after = sync.run(self.manifest, False, self.source, self.profiles)
        self.assertEqual(after["mismatched_after"], 0)

    def test_unapproved_source_change_fail_closed(self):
        (self.source / COMPANY / SKILL / "SKILL.md").write_text("# Unapproved\n")
        with self.assertRaisesRegex(RuntimeError, "UNAPPROVED_SOURCE_SHA"):
            sync.run(self.manifest, True, self.source, self.profiles)
        self.assertFalse(
            (self.profiles / "ceo" / "skills/company-managed" / SKILL / "SKILL.md").exists()
        )

    def test_destination_symlink_rejected(self):
        target = self.profiles / "ceo" / "skills/company-managed" / SKILL
        target.symlink_to(self.source / COMPANY / SKILL, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unsafe destination dir"):
            sync.run(self.manifest, True, self.source, self.profiles)

    def test_missing_pin_manifest_rejected(self):
        self.manifest_data.pop("approved_sha256")
        self._write_manifest()
        with self.assertRaisesRegex(ValueError, "Approved SHA-256"):
            sync.run(self.manifest, False, self.source, self.profiles)


if __name__ == "__main__":
    unittest.main()
