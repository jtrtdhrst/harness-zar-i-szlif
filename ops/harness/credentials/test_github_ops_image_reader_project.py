#!/usr/bin/env python3
"""Adversarial offline tests for the separate one-repo GHCR token projector."""
import datetime
import importlib.util
from pathlib import Path
import stat
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).with_name("github-ops-image-reader-project.py")
spec = importlib.util.spec_from_file_location("github_ops_image_reader_project", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
APP = "o968ndolpcfecgswerjjeg6j"
VOLUME = APP + "-ghops-harness-reader"


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 11, 23, 12, 0, tzinfo=datetime.timezone.utc)
        self.valid = {
            "role": m.ROLE, "app_id": m.APP_ID,
            "installation_id": m.INSTALLATION_ID,
            "repositories": ["jtrtdhrst/harness-zar-i-szlif", "jtrtdhrst/zar-i-szlif"],
            "permissions": {"actions": "read", "administration": "read", "contents": "read", "deployments": "read", "metadata": "read"},
            "token": "t" * 50,
            "expires_at": (self.now + datetime.timedelta(minutes=35)).isoformat(),
        }

    def test_exact_scope_and_expiry(self):
        self.assertEqual(m.validate_grant(self.valid, self.now), self.valid)

    def test_extra_repo_write_scope_and_token_role_are_denied(self):
        changes = [
            {"role": "github-ops-reader"},
            {"role": "github-ops-reader-harness"},
            {"role": "github-ops-writer"},
            {"app_id": m.APP_ID + 1},
            {"installation_id": m.INSTALLATION_ID + 1},
            {"repositories": ["jtrtdhrst/zar-i-szlif"]},
            {"repositories": ["jtrtdhrst/harness-zar-i-szlif"]},
            {"repositories": ["jtrtdhrst/harness-zar-i-szlif", "jtrtdhrst/zar-i-szlif", "another/repo"]},
            {"permissions": {"actions": "read", "administration": "read", "contents": "write", "deployments": "read", "metadata": "read"}},
            {"permissions": {"actions": "read", "administration": "read", "contents": "read", "deployments": "read", "metadata": "read", "issues": "read"}},
            {"token": "wrong token value"},
            {"expires_at": (self.now + datetime.timedelta(minutes=9)).isoformat()},
            {"expires_at": (self.now + datetime.timedelta(minutes=61)).isoformat()},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                m.validate_grant({**self.valid, **change}, self.now)

    def test_unknown_and_duplicate_repo_are_denied(self):
        for repos in ([], ["jtrtdhrst/harness-zar-i-szlif"] * 2,
                      ["jtrtdhrst/harness-zar-i-szlif", "jtrtdhrst/harness-zar-i-szlif"],
                      "jtrtdhrst/harness-zar-i-szlif"):
            with self.subTest(repos=repos), self.assertRaises(RuntimeError):
                m.validate_grant({**self.valid, "repositories": repos}, self.now)


class VolumeTests(unittest.TestCase):
    def setUp(self):
        self.stat_info = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        self.mount = Path("/var/lib/docker/volumes") / VOLUME / "_data"
        self.container = {
            "Config": {"Labels": {"coolify.applicationUuid": APP}},
            "Mounts": [{"Type": "volume", "Name": VOLUME,
                        "Destination": "/run/secrets/github-ops"}],
        }

    def call(self, app=APP, volume=VOLUME, container=None, mode=None):
        stat_info = SimpleNamespace(st_mode=stat.S_IFDIR | (mode or 0o755), st_uid=0)
        def docker_json(*args):
            if args[0] == "volume":
                return [{"Name": VOLUME, "Mountpoint": str(self.mount)}]
            return [container or self.container]
        with patch.object(m, "docker_json", side_effect=docker_json), \
             patch.object(m.os, "lstat", return_value=stat_info), \
             patch.object(m.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout="container-id\n")):
            return m.validated_volume(app, volume)

    def test_only_uuid_bound_volume_mounted_to_expected_path_passes(self):
        self.assertEqual(self.call(), self.mount)

    def test_wrong_uuid_or_volume_name_fails_closed(self):
        for app, volume in ((APP[:-1], VOLUME), (APP, "unrelated-volume"),
                            (APP, APP + "-bad*path")):
            with self.subTest(app=app, volume=volume), self.assertRaises(RuntimeError):
                self.call(app, volume)

    def test_foreign_container_and_wrong_mount_path_are_denied(self):
        for other in (
            {**self.container, "Config": {"Labels": {"coolify.applicationUuid": "a" * 24}}},
            {**self.container, "Mounts": [{"Type": "volume", "Name": VOLUME,
                                          "Destination": "/data"}]},
        ):
            with self.subTest(other=other), self.assertRaises(RuntimeError):
                self.call(container=other)

    def test_group_or_world_writable_mount_is_denied(self):
        for mode in (0o775, 0o777):
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                self.call(mode=mode)


if __name__ == "__main__":
    unittest.main()
