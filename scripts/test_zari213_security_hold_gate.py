"""Fail closed on a persisted owner HOLD independent of issue status."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "ops/harness/release/multica_native_release_gate.py"
spec = importlib.util.spec_from_file_location("native_hold_gate", GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class PersistedHoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "security-hold.json"
        self.record = {
            "owner": gate.SECURITY_HOLD_OWNER,
            "reason": "A controlled security hold",
            "activated_at": "2026-11-23T16:00:00Z",
            "clearing_authority": "workspace_owner_and_independent_CTO_COO",
            "active": True,
            "clearance": None,
        }

    def save(self):
        self.path.write_text(json.dumps(self.record))

    def denied(self, reason):
        with self.assertRaisesRegex(gate.Denied, reason):
            gate.enforce_persistent_security_hold("fake-db", self.path)

    def test_active_hold_denies_every_status(self):
        self.save()
        with patch.object(gate, "read_rows") as read:
            for status in ("blocked", "in_review", "done"):
                with self.subTest(status=status):
                    self.denied("security_hold_active")
            read.assert_not_called()

    def test_absent_or_invalid_record_denied(self):
        self.denied("security_hold_record_missing")
        self.path.write_text("not JSON")
        self.denied("security_hold_record_unreadable")
        self.record["activated_at"] = "bad"
        self.save()
        self.denied("security_hold_record_invalid")

    def test_clearance_without_authorization_denied(self):
        self.record["active"] = False
        self.save()
        self.denied("security_hold_clearance_missing")
        self.record["clearance"] = {
            "cleared_by":"wrong","cleared_at":"2026-11-23T16:10:00Z",
            "isolation_e2e_evidence":"verified test",
            "ctocoo_review_sha":"a"*40
        }
        self.save()
        self.denied("security_hold_clearance_not_authorized")

    def test_cleared_source_but_live_metadata_still_held_denied(self):
        self.record["active"] = False
        self.record["clearance"] = {
            "cleared_by": gate.SECURITY_HOLD_OWNER,
            "cleared_at":"2026-11-23T16:10:00Z",
            "isolation_e2e_evidence":"test run",
            "ctocoo_review_sha":"a"*40
        }
        self.save()
        with patch.object(gate, "read_rows",return_value=[{"metadata":{"security_hold": True}}]):
            self.denied("security_hold_live_not_cleared")
        with patch.object(gate, "read_rows",return_value=[]):
            self.denied("security_hold_live_record_missing")
        with patch.object(gate, "read_rows",return_value=[{"metadata":{"security_hold": False}}]):
            self.assertTrue(gate.enforce_persistent_security_hold("fake-db", self.path))

if __name__ == "__main__":
    unittest.main()
