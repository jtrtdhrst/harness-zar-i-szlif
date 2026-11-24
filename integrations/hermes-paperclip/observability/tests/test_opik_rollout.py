"""Transactional Opik role segmentation release gates (no production mutations)."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rollout
from apply_opik_segmentation import transform

BASELINE = (
    "import datetime\n"
    "\ndef start_root_trace(\n    task_key: str,\n):\n"
    '    metadata = {\n        "source": "hermes",\n    }\n'
    "    # Build the create payload once and keep it:\n"
    '    create_kwargs = {\n        "thread_id": session_id or None,\n        "tags": tags(),\n    }\n'
)


class RolloutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original = BASELINE.encode()
        self.patched = transform(BASELINE).encode()
        self.addCleanup(
            mock.patch.stopall
        )
        mock.patch.object(rollout, "BASE_SHA256",
                          hashlib.sha256(self.original).hexdigest()).start()
        mock.patch.object(rollout, "PATCHED_SHA256",
                          hashlib.sha256(self.patched).hexdigest()).start()
        for p in rollout.source_paths(self.root).values():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(self.original)

    def test_apply_readback_rollback_all_roles(self):
        journal = self.root / rollout.JOURNAL_DIR
        self.assertEqual(rollout.status(self.root)["pristine"], 14)
        owners = {role: (p.stat().st_uid, p.stat().st_gid, p.stat().st_mode & 0o777)
                  for role, p in rollout.source_paths(self.root).items()}
        result = rollout.apply(self.root, journal)
        self.assertEqual(result["roles_patched"], 14)
        self.assertEqual(rollout.status(self.root)["patched"], 14)
        self.assertTrue(rollout.status(self.root)["consistent"])
        self.assertEqual(owners, {role: (p.stat().st_uid, p.stat().st_gid, p.stat().st_mode & 0o777)
                                  for role, p in rollout.source_paths(self.root).items()})
        self.assertTrue(all(p.read_bytes() == self.patched
                            for p in rollout.source_paths(self.root).values()))
        restored = rollout.rollback(self.root, journal, result["batch_id"])
        self.assertEqual(restored["restored"], 14)
        self.assertEqual(rollout.status(self.root)["pristine"], 14)
        self.assertEqual(owners, {role: (p.stat().st_uid, p.stat().st_gid, p.stat().st_mode & 0o777)
                                  for role, p in rollout.source_paths(self.root).items()})
        self.assertTrue(all(p.read_bytes() == self.original
                            for p in rollout.source_paths(self.root).values()))

    def test_preflight_rejects_partial_drift_before_writes(self):
        target = rollout.source_paths(self.root)["cpo"]
        target.write_text("unreviewed")
        with self.assertRaisesRegex(rollout.RolloutError, "drift"):
            rollout.apply(self.root, self.root / rollout.JOURNAL_DIR)
        self.assertEqual(target.read_text(), "unreviewed")
        self.assertEqual(rollout.source_paths(self.root)["cho"].read_bytes(),
                         self.original)

    def test_symlink_refused(self):
        target = rollout.source_paths(self.root)["cto"]
        target.unlink()
        target.symlink_to(rollout.source_paths(self.root)["cpo"])
        with self.assertRaisesRegex(rollout.RolloutError, "symlink"):
            rollout.status(self.root)

    def test_active_transaction_must_be_rolled_back_first(self):
        journal = self.root / rollout.JOURNAL_DIR
        result = rollout.apply(self.root, journal)
        with self.assertRaisesRegex(rollout.RolloutError, "not all profiles are pristine"):
            rollout.apply(self.root, journal)
        rollout.rollback(self.root, journal, result["batch_id"])

    def test_corrupt_backup_refused_without_any_partial_restore(self):
        journal = self.root / rollout.JOURNAL_DIR
        result = rollout.apply(self.root, journal)
        (journal / result["batch_id"] / "ceo.bak").write_text("tampered")
        with self.assertRaisesRegex(rollout.RolloutError, "checksum"):
            rollout.rollback(self.root, journal, result["batch_id"])
        self.assertEqual(rollout.status(self.root)["patched"], 14)

    def test_incomplete_install_can_be_restored(self):
        journal = self.root / rollout.JOURNAL_DIR
        result = rollout.apply(self.root, journal)
        rollout.source_paths(self.root)["cpo"].write_bytes(self.original)
        status = rollout.status(self.root)
        self.assertEqual(status["patched"], 13)
        self.assertFalse(status["consistent"])
        recovered = rollout.rollback(self.root, journal, result["batch_id"])
        self.assertEqual(recovered["restored"], 13)
        self.assertEqual(rollout.status(self.root)["pristine"], 14)


if __name__ == "__main__":
    unittest.main()
