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

        def actual_exe(path):
            pid = int(str(path).split("/")[2])
            argv = chain[pid][1]
            exe = pathlib.Path(argv[0]).name
            if exe.startswith("python3"):
                return "/usr/bin/python3.11"
            if exe.startswith("git-remote-"):
                return "/usr/lib/git-core/git-remote-http"
            if exe == "git":
                return "/usr/bin/git"
            return "/usr/bin/dash"

        with patch.object(broker.os, "readlink", side_effect=actual_exe), \
             patch.object(broker, "daemon_pid", return_value=100), \
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


    def test_refuse_python_dummy_trusted_arg(self):
        self.verify({
            900: (800, ["python3", "/tmp/attacker.py",
                        "/usr/local/libexec/multica-zar-git-credential", "get"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "fetch", "origin"]),
        }, False)

    def test_refuse_python_c_payload(self):
        self.verify({
            900: (800, ["python3", "-c", "print('bad')",
                        "/usr/local/libexec/multica-zar-git-credential"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "fetch", "origin"]),
        }, False)

    def test_refuse_shell_substring(self):
        self.verify({
            900: (800, ["sh", "-c", "echo /usr/local/libexec/multica-zar-git-credential"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "fetch", "origin"]),
        }, False)

    def test_refuse_reordered_chain(self):
        self.verify({
            900: (800, ["python3", "/usr/local/libexec/multica-zar-git-credential", "get"]),
            800: (700, ["git", "fetch", "origin"]),
            700: (100, ["git-remote-https", "origin", "https://github.com/x/y"]),
        }, False)

    def test_refuse_fetch_word_as_argument(self):
        self.verify({
            900: (800, ["python3", "/usr/local/libexec/multica-zar-git-credential", "get"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "config", "fetch"]),
        }, False)

    def test_refuse_config_override(self):
        self.verify({
            900: (800, ["python3", "/usr/local/libexec/multica-zar-git-credential", "get"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "-c", "credential.helper=!echo pwned", "fetch"]),
        }, False)

    def test_refuse_untrusted_proc_exe(self):
        chain = {
            900: (800, ["python3", "/usr/local/libexec/multica-zar-git-credential", "get"]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "fetch", "origin"]),
        }
        def status(pid):
            return {"PPid": str(chain[pid][0]), "Uid": "997 997 997 997"}
        def cmdline(path):
            return b"\0".join(x.encode() for x in chain[int(str(path).split("/")[2])][1]) + b"\0"
        with patch.object(broker, "daemon_pid", return_value=100), \
             patch.object(broker, "proc_status", side_effect=status), \
             patch.object(pathlib.Path, "read_bytes", cmdline), \
             patch.object(broker.os, "readlink", return_value="/tmp/fake-python"):
            self.assertFalse(broker.is_authorized_daemon_cache_fetch(900, "test"))


class BrokerHandlerTests(unittest.TestCase):
    def make_request(self, op):
        import io
        import json
        import struct
        from types import SimpleNamespace
        from unittest.mock import Mock
        h = object.__new__(broker.Handler)
        h.request = Mock()
        h.request.getsockopt.return_value = struct.pack("3i", 900, 997, 981)
        h.rfile = io.BytesIO(json.dumps({
            "op": op, "protocol": "https", "host": "github.com",
            "path": "miloszspyrka-code/zar-i-szlif.git"
        }).encode() + b"\n")
        h.server = SimpleNamespace(daemon_unit="unit", pidfile=None,
                                   allow_any_daemon=False, tokens=pathlib.Path("/no/tokens"))
        result = []
        h.reply = result.append
        with patch.object(broker, "task_agent", return_value=None), \
             patch.object(broker, "is_authorized_daemon_cache_fetch", return_value=True), \
             patch.object(broker, "token_for_role", return_value={
                 "token": "synthetic-test-only", "expires_at": "2099-01-01T00:00:00Z"
             }) as get_token:
            h.handle()
        return result, get_token

    def test_daemon_cache_credential_success_no_unbound_agent(self):
        result, get_token = self.make_request("credential")
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["ok"], result)
        self.assertEqual(result[0]["role"], "reviewer")
        get_token.assert_called_once()

    def test_daemon_cache_never_gets_raw_token_operation(self):
        result, get_token = self.make_request("token")
        self.assertEqual(result, [{"ok": False, "error": "no_active_multica_task"}])
        get_token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
