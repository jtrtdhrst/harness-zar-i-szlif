import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("opik_rollout", ROOT / "rollout.py")
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)

def digest(data):
    return hashlib.sha256(data).hexdigest()

class RolloutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "index.mjs"
        self.source = self.root / "candidate.mjs"
        self.old, self.new = b"safe original code\n", b"safe candidate code\n"
        self.target.write_bytes(self.old)
        self.source.write_bytes(self.new)
        self.target.chmod(0o640)
        a = mock.patch.object(rollout, "BASELINE_SHA", digest(self.old))
        b = mock.patch.object(rollout, "CANDIDATE_SHA", digest(self.new))
        a.start(); b.start()
        self.addCleanup(a.stop); self.addCleanup(b.stop)

    def test_status_is_readonly_and_detects_drift(self):
        before = rollout.status(self.target, self.source)
        self.assertEqual(before["state"], "pristine")
        self.assertFalse((self.root / rollout.JOURNAL_NAME).exists())
        self.target.write_bytes(b"external drift")
        self.assertEqual(rollout.status(self.target, self.source)["state"], "drift")

    def test_apply_and_rollback_checksum_and_mode(self):
        out = rollout.apply(self.target, self.source, True)
        self.assertEqual(out["state"], "applied")
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertEqual(rollout.status(self.target, self.source)["state"], "candidate")
        back = rollout.rollback(self.target, self.source, out["batch_id"], True)
        self.assertEqual(back["state"], "rolled_back")
        self.assertEqual(self.target.read_bytes(), self.old)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)

    def test_journal_privacy_and_target_owner_match(self):
        out = rollout.apply(self.target, self.source, True)
        journal = self.root / rollout.JOURNAL_NAME
        batch = journal / out["batch_id"]
        owner = (self.target.stat().st_uid, self.target.stat().st_gid)
        for path in (journal, batch, journal / ".lock", batch / "original.mjs", batch / "manifest.json"):
            metadata = path.stat()
            self.assertEqual((metadata.st_uid, metadata.st_gid), owner)
            self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o700 if path.is_dir() else 0o600)
        rollout.rollback(self.target, self.source, out["batch_id"], True)

    @unittest.skipUnless(os.geteuid() == 0, "requires root to simulate a node-owned plugin")
    def test_root_deployer_preserves_nonroot_plugin_owner(self):
        os.chown(self.target, 1000, 1000)
        out = rollout.apply(self.target, self.source, True)
        journal = self.root / rollout.JOURNAL_NAME
        batch = journal / out["batch_id"]
        for path in (self.target, journal, journal / ".lock", batch,
                     batch / "original.mjs", batch / "manifest.json"):
            self.assertEqual((path.stat().st_uid, path.stat().st_gid), (1000, 1000))
        rollback = rollout.rollback(self.target, self.source, out["batch_id"], True)
        self.assertEqual(rollback["state"], "rolled_back")
        self.assertEqual((self.target.stat().st_uid, self.target.stat().st_gid), (1000, 1000))

    def test_no_explicit_drain_refuses_write(self):
        with self.assertRaisesRegex(rollout.RolloutError, "drain"):
            rollout.apply(self.target, self.source, False)
        self.assertEqual(self.target.read_bytes(), self.old)

    def test_source_drift_denied(self):
        self.source.write_bytes(b"unreviewed")
        with self.assertRaisesRegex(rollout.RolloutError, "candidate source SHA"):
            rollout.apply(self.target, self.source, True)

    def test_production_drift_denied(self):
        self.target.write_bytes(b"not expected")
        with self.assertRaisesRegex(rollout.RolloutError, "production source drift"):
            rollout.apply(self.target, self.source, True)

    def test_target_symlink_denied(self):
        old = self.root / "real.mjs"
        old.write_bytes(self.old)
        self.target.unlink()
        self.target.symlink_to(old)
        with self.assertRaisesRegex(rollout.RolloutError, "symlink"):
            rollout.apply(self.target, self.source, True)
        self.assertEqual(old.read_bytes(), self.old)

    def test_double_apply_is_idempotent(self):
        out = rollout.apply(self.target, self.source, True)
        second = rollout.apply(self.target, self.source, True)
        self.assertEqual(second["state"], "already_applied")
        self.assertEqual(self.target.read_bytes(), self.new)
        rollout.rollback(self.target, self.source, out["batch_id"], True)

    def test_pending_manifest_denies_new_apply(self):
        out = rollout.apply(self.target, self.source, True)
        self.target.write_bytes(self.old)
        with self.assertRaisesRegex(rollout.RolloutError, "outstanding rollout"):
            rollout.apply(self.target, self.source, True)
        self.assertEqual(out["state"], "applied")

    def test_corrupt_backup_refuses_rollback(self):
        out = rollout.apply(self.target, self.source, True)
        path = self.root / rollout.JOURNAL_NAME / out["batch_id"] / "original.mjs"
        path.write_bytes(b"corrupt")
        with self.assertRaisesRegex(rollout.RolloutError, "backup corrupt"):
            rollout.rollback(self.target, self.source, out["batch_id"], True)
        self.assertEqual(self.target.read_bytes(), self.new)

    def test_external_target_change_refuses_rollback(self):
        out = rollout.apply(self.target, self.source, True)
        self.target.write_bytes(b"third party edit")
        with self.assertRaisesRegex(rollout.RolloutError, "target drift"):
            rollout.rollback(self.target, self.source, out["batch_id"], True)

    def test_rollback_requires_drain_and_valid_batch(self):
        out = rollout.apply(self.target, self.source, True)
        with self.assertRaisesRegex(rollout.RolloutError, "drain"):
            rollout.rollback(self.target, self.source, out["batch_id"], False)
        with self.assertRaisesRegex(rollout.RolloutError, "invalid batch"):
            rollout.rollback(self.target, self.source, "../escape", True)
        self.assertEqual(self.target.read_bytes(), self.new)

class PinnedCandidateTest(unittest.TestCase):
    def test_checked_in_candidate_sha_matches_source_file(self):
        source = ROOT / "index.mjs"
        self.assertTrue(source.is_file())
        self.assertEqual(digest(source.read_bytes()), rollout.CANDIDATE_SHA)

if __name__ == "__main__":
    unittest.main()
