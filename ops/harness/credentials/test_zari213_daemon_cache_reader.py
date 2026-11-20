#!/usr/bin/env python3
"""Offline ancestry tests. Never contacts the credential socket or reads tokens."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).with_name("multica-git-credential-broker.py")
spec = importlib.util.spec_from_file_location("zari213_broker_under_test", SOURCE)
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


class DaemonCacheAuthTests(unittest.TestCase):
    def verify(self, chain, expected):
        def status(pid):
            if pid not in chain:
                return {"PPid": "1", "Uid": "997\t997\t997\t997"}
            return {"PPid": str(chain[pid][0]), "Uid": "997\t997\t997\t997"}

        def cmdline(path):
            pid = int(str(path).split("/")[2])
            if pid not in chain:
                return b""
            return b"\0".join(v.encode() for v in chain[pid][1]) + b"\0"

        with patch.object(broker, "daemon_pid", return_value=100), \
             patch.object(broker, "proc_status", side_effect=status), \
             patch.object(pathlib.Path, "read_bytes", cmdline):
            self.assertEqual(
                broker.is_authorized_daemon_cache_fetch(900, "test"), expected
            )

    def test_legitimate_daemon_fetch(self):
        self.verify({
            900: (800, ["python3", "/usr/local/libexec/multica-zar-git-credential", "get"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "-C", "/srv/cache", "fetch", "origin"]),
        }, True)

    def test_legitimate_daemon_clone(self):
        self.verify({
            900: (800, ["python3", "/usr/local/libexec/multica-zar-git-credential", "get"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "clone", "https://github.com/x/y", "/srv/cache"]),
        }, True)

    def test_refuse_push(self):
        self.verify({
            900: (800, ["python3", "/usr/local/libexec/multica-zar-git-credential", "get"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "push", "origin", "main"]),
        }, False)

    def test_refuse_agent_process_masquerading_as_cache(self):
        self.verify({
            900: (800, ["python3", "/usr/local/libexec/multica-zar-git-credential", "get"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["hermes", "acp"]),
        }, False)

    def test_refuse_untrusted_helper(self):
        self.verify({
            900: (800, ["python3", "/tmp/foreign-helper.py", "get"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "-C", "/srv/cache", "fetch", "origin"]),
        }, False)

    def test_refuse_untrusted_direct_shell(self):
        self.verify({
            900: (100, ["sh", "-c", "/usr/local/libexec/multica-zar-git-credential get"]),
        }, False)


if __name__ == "__main__":
    unittest.main()
