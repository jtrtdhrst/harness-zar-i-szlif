"""Negative security regressions for source-verified, credential-free Product CI."""
import io
import json
import tempfile
import os
import stat
import tarfile
import unittest
from unittest.mock import patch
import product_rootless_ci_attest as ci

class AttesterSecurityTests(unittest.TestCase):
    def test_sha_is_exact_lowercase_hex(self):
        self.assertEqual(ci.require_sha("a" * 40), "a" * 40)
        for value in ("f" * 39, "F" * 40, "../" + "a" * 40, "", None):
            with self.subTest(value=value), self.assertRaises(ci.Refused):
                ci.require_sha(value)

    def test_hmac_binds_entire_evidence(self):
        key = bytes(range(32))
        payload = {"sha": "a" * 40, "tree": "b" * 40,
                   "runner_uid": 991, "exit_code": 0}
        signed = dict(payload, signature=ci.sign(payload, key))
        self.assertTrue(ci.verify(signed, key))
        for field, altered in (("sha", "c" * 40), ("tree", "d" * 40),
                               ("runner_uid", 0), ("exit_code", 1)):
            with self.subTest(field=field):
                bad = dict(signed, **{field: altered})
                self.assertFalse(ci.verify(bad, key))
        self.assertFalse(ci.verify(dict(payload), key))
        with self.assertRaises(ci.Refused):
            ci.sign(payload, b"weak")

    @staticmethod
    def _tar(name: str, *, link: bool = False):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as t:
            d = tarfile.TarInfo("product-stable/")
            d.type = tarfile.DIRTYPE
            t.addfile(d)
            entry = tarfile.TarInfo(name)
            if link:
                entry.type = tarfile.SYMTYPE
                entry.linkname = "/etc/shadow"
                t.addfile(entry)
            else:
                b = b"x"
                entry.size = len(b)
                t.addfile(entry, io.BytesIO(b))
        data.seek(0)
        return data

    def test_single_root_valid_tar(self):
        with tarfile.open(fileobj=self._tar("product-stable/README.md"), mode="r:") as t:
            self.assertEqual(ci.validated_members(t), "product-stable")

    def test_traversal_and_absolute_tar_rejected(self):
        for path in ("product-stable/../../outside", "/etc/passwd",
                     "foreign-root/README.md", "product-stable\\attack"):
            with self.subTest(path=path), tarfile.open(fileobj=self._tar(path), mode="r:") as t:
                with self.assertRaises(ci.Refused):
                    ci.validated_members(t)

    def test_tar_link_denied_before_root_extraction(self):
        with tarfile.open(fileobj=self._tar("product-stable/escape", link=True), mode="r:") as t:
            with self.assertRaises(ci.Refused):
                ci.validated_members(t)

    def test_socket_requires_owner_only_permissions(self):
        from types import SimpleNamespace
        from stat import S_IFSOCK
        with patch.object(ci.os, "geteuid", return_value=0), \
             patch.object(ci, "guest_uid", return_value=991):
            for mode in (0o660, 0o666, 0o640):
                with self.subTest(mode=mode), \
                     patch.object(ci.DOCKER_SOCKET.__class__, "stat",
                                  return_value=SimpleNamespace(st_mode=S_IFSOCK | mode, st_uid=991)):
                    with self.assertRaises(ci.Refused):
                        ci.preflight()
            with patch.object(ci.DOCKER_SOCKET.__class__, "stat",
                              return_value=SimpleNamespace(st_mode=S_IFSOCK | 0o600, st_uid=991)):
                self.assertEqual(ci.preflight(), 991)

    def test_signed_receipt_is_write_once_and_old_bytes_remain(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(ci, "RECEIPTS", Path(folder)):
            key = bytes(range(32))
            payload = {"sha": "a"*40, "tree": "b"*40, "exit_code": 0,
                       "log_sha256": "c"*64, "log_path": "/some/nonsecret/digest.log"}
            saved = ci.store_receipt(payload, key)
            original = saved.read_bytes()
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ci.Refused, "attestation_already_exists"):
                ci.store_receipt(dict(payload, tree="d"*40), key)
            self.assertEqual(saved.read_bytes(), original)
            self.assertTrue(ci.verify(json.loads(original), key))

    def test_compatible_premerge_receipt_is_not_replaceable(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(ci, "RECEIPTS", Path(folder)):
            payload = {"sha": "a"*40, "tree": "b"*40,
                       "verified_at": "2026-11-19T15:00:00Z"}
            saved = ci.store_premerge_receipt(payload)
            old = saved.read_bytes()
            with self.assertRaisesRegex(ci.Refused, "attestation_already_exists"):
                ci.store_premerge_receipt(dict(payload, verified_at="2026-11-19T16:00:00Z"))
            self.assertEqual(saved.read_bytes(), old)

    def test_rejected_evidence_does_not_overwrite_original(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder) / "original.log"
            old.write_bytes(b"first-success-immutable")
            original_hash = __import__("hashlib").sha256(old.read_bytes()).hexdigest()
            candidate = Path(folder) / "second-attempt.failed"
            candidate.write_bytes(b"failed-retry")
            self.assertEqual(__import__("hashlib").sha256(old.read_bytes()).hexdigest(), original_hash)
            self.assertNotEqual(old.read_bytes(), candidate.read_bytes())
            with self.assertRaisesRegex(ci.Refused, "attestation_already_exists"):
                ci._write_once(old, b"failed-retry")
            self.assertEqual(old.read_bytes(), b"first-success-immutable")

    def test_plan_does_not_download_or_build(self):
        with patch.object(ci, "github_snapshot", side_effect=AssertionError("unexpected network")), \
             patch.object(ci, "guest_ci", side_effect=AssertionError("unexpected build")), \
             patch.object(ci, "preflight", return_value=991), \
             patch("sys.argv", ["ci", "--sha", "f" * 40, "--plan"]):
            self.assertEqual(ci.main(), 0)

if __name__ == "__main__":
    unittest.main()
