#!/usr/bin/env python3
"""Narrow, credential-free regression tests for ZARI-263 broker role scopes."""
import datetime
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest

PATH = pathlib.Path(__file__).with_name("multica-git-credential-broker.py")
SPEC = importlib.util.spec_from_file_location("zari263_broker", PATH)
broker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(broker)
broker.TRUSTED_UID = os.getuid()  # test fixtures; production defaults to root

H = "jtrtdhrst/harness-zar-i-szlif"
P = "jtrtdhrst/zar-i-szlif"


def token(role, repos, permissions=None):
    base = role if role == "cache-reader" else role.split("-", 1)[0]
    return {
        "token": "ghs_" + "x" * 46,
        "role": role,
        "repositories": list(repos),
        "permissions": permissions or broker.ROLE_PERMISSIONS[base],
        "expires_at": (datetime.datetime.now(datetime.timezone.utc)
                       + datetime.timedelta(minutes=35)).isoformat(),
    }


class ScopedAgentGrants(unittest.TestCase):
    def read(self, role, data):
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / (role + ".json")
            path.write_text(json.dumps(data), encoding="utf-8")
            path.chmod(0o600)
            return broker.read_role_token(pathlib.Path(root), role)

    def test_scoped_roles_are_explicit_and_restrict_foreign_repo(self):
        for base in ("implementer", "reviewer", "release"):
            for suffix, own, foreign in (("harness", H, P), ("product", P, H)):
                role = base + "-" + suffix
                self.assertIn(role, broker.AGENT_ROLES)
                self.assertTrue(broker.role_repo_allowed(role, own))
                self.assertFalse(broker.role_repo_allowed(role, foreign))
                self.assertEqual(self.read(role, token(role, [own]))["role"], role)
                with self.assertRaisesRegex(ValueError, "repository scope mismatch"):
                    self.read(role, token(role, [own, foreign]))

    def test_broker_refuses_privileged_runner_and_unmapped_roles(self):
        for role in ("runner", "runner-harness", "runner-product", "unknown"):
            self.assertNotIn(role, broker.AGENT_ROLES)
            with self.assertRaisesRegex(ValueError, "not authorized"):
                self.read(role, token(role, [H, P], permissions={"metadata": "read"}))

    def test_role_or_permission_substitution_fails_closed(self):
        role = "reviewer-harness"
        wrong_role = token(role, [H])
        wrong_role["role"] = "implementer-harness"
        with self.assertRaisesRegex(ValueError, "permissions mismatch"):
            self.read(role, wrong_role)
        wrong_perms = token(role, [H], {"contents": "write", "metadata": "read"})
        with self.assertRaisesRegex(ValueError, "permissions mismatch"):
            self.read(role, wrong_perms)

    def test_broad_base_roles_cannot_be_mapped_or_read(self):
        for role in ("implementer", "reviewer", "release"):
            self.assertNotIn(role, broker.AGENT_ROLES)
            self.assertFalse(broker.role_repo_allowed(role, H))
            self.assertFalse(broker.role_repo_allowed(role, P))
            with self.assertRaisesRegex(ValueError, "not authorized"):
                self.read(role, token(role, [H, P]))

    def test_daemon_cache_reader_remains_read_only(self):
        self.assertNotIn("cache-reader", broker.AGENT_ROLES)
        self.assertEqual(set(self.read("cache-reader", token("cache-reader", [H, P]))["repositories"]), {H, P})


if __name__ == "__main__":
    unittest.main()
