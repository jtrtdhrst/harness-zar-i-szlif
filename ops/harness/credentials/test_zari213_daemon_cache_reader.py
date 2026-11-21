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


class TaskCredentialAncestryTests(unittest.TestCase):
    """No real processes, secrets, credential sockets or network used."""

    def resolve(self, parents, envs):
        def status(pid):
            return {"PPid": str(parents.get(pid, 1))}
        with patch.object(broker, "daemon_pid", return_value=100), \
             patch.object(broker, "proc_status", side_effect=status), \
             patch.object(broker, "proc_environ",
                          side_effect=lambda pid: envs.get(pid, {})):
            return broker.task_agent(900, "test-daemon")

    def task_env(self):
        return {
            "MULTICA_AGENT_ID": "agent-harness",
            "MULTICA_TASK_ID": "task-harness",
            "MULTICA_TOKEN": "synthetic-task-token",
            "MULTICA_WORKSPACE_ID": broker.EXPECTED_WORKSPACE,
        }

    def test_hermes_gateway_with_task_identity_in_shell(self):
        self.assertEqual(
            self.resolve({900: 850, 850: 800, 800: 100},
                         {850: self.task_env()}),
            ("agent-harness", "task-harness", "synthetic-task-token"),
        )

    def test_task_identity_in_helper(self):
        self.assertEqual(
            self.resolve({900: 850, 850: 800, 800: 100},
                         {900: self.task_env()}),
            ("agent-harness", "task-harness", "synthetic-task-token"),
        )

    def test_outside_daemon_cannot_spoof_task(self):
        self.assertIsNone(self.resolve({900: 850, 850: 1},
                                       {900: self.task_env()}))

    def test_wrong_workspace_rejected_without_ancestor_fallback(self):
        forged = dict(self.task_env())
        forged["MULTICA_WORKSPACE_ID"] = "foreign-workspace"
        self.assertIsNone(
            self.resolve({900: 850, 850: 800, 800: 100},
                         {900: forged, 850: self.task_env()}))

    def test_partial_nearest_identity_is_not_upgraded(self):
        self.assertIsNone(
            self.resolve({900: 850, 850: 800, 800: 100},
                         {900: {"MULTICA_TASK_ID": "spoof"},
                          850: self.task_env()}))

    def test_daemon_cache_has_no_task_identity(self):
        self.assertIsNone(
            self.resolve({900: 850, 850: 800, 800: 100}, {}))


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

        original_readlink = broker.os.readlink
        def actual_exe(path):
            if not str(path).startswith("/proc/"):
                return original_readlink(path)
            pid = int(str(path).split("/")[2])
            argv = chain[pid][1]
            if argv[0] == "/usr/lib/git-core/git":
                return "/usr/lib/git-core/git"
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

    def test_real_git_credential_shell_ancestry(self):
        helper = "/usr/local/libexec/multica-zar-git-credential"
        exact = helper + " get"
        self.verify({
            900: (850, ["python3", helper, "get"]),
            850: (800, ["/bin/sh", "-c", exact, exact]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "-C", "/srv/cache", "fetch", "origin"]),
        }, True)

    def test_real_git_remote_https_dispatcher_ancestry(self):
        helper = "/usr/local/libexec/multica-zar-git-credential"
        exact = helper + " get"
        url = "https://github.com/jtrtdhrst/harness-zar-i-szlif"
        self.verify({
            900: (850, ["python3", helper, "get"]),
            850: (800, ["/bin/sh", "-c", exact, exact]),
            800: (750, ["/usr/lib/git-core/git-remote-https", "origin", url]),
            750: (700, ["/usr/lib/git-core/git", "remote-https", "origin", url]),
            700: (100, ["git", "-C", "/srv/cache", "fetch", "origin"]),
        }, True)

    def test_git_remote_dispatcher_rejects_mismatched_transport(self):
        helper = "/usr/local/libexec/multica-zar-git-credential"
        exact = helper + " get"
        url = "https://github.com/jtrtdhrst/harness-zar-i-szlif"
        self.verify({
            900: (850, ["python3", helper, "get"]),
            850: (800, ["/bin/sh", "-c", exact, exact]),
            800: (750, ["git-remote-https", "origin", url]),
            750: (700, ["git", "remote-https", "other-origin", url]),
            700: (100, ["git", "-C", "/srv/cache", "fetch", "origin"]),
        }, False)

    def test_git_remote_dispatcher_rejects_protocol_mismatch(self):
        helper = "/usr/local/libexec/multica-zar-git-credential"
        exact = helper + " get"
        url = "https://github.com/jtrtdhrst/harness-zar-i-szlif"
        self.verify({
            900: (850, ["python3", helper, "get"]),
            850: (800, ["/bin/sh", "-c", exact, exact]),
            800: (750, ["git-remote-https", "origin", url]),
            750: (700, ["git", "remote-http", "origin", url]),
            700: (100, ["git", "-C", "/srv/cache", "fetch", "origin"]),
        }, False)

    def test_git_remote_dispatcher_rejects_usr_bin_git(self):
        helper = "/usr/local/libexec/multica-zar-git-credential"
        exact = helper + " get"
        url = "https://github.com/jtrtdhrst/harness-zar-i-szlif"
        self.verify({
            900: (850, ["python3", helper, "get"]),
            850: (800, ["/bin/sh", "-c", exact, exact]),
            800: (750, ["/usr/lib/git-core/git-remote-https", "origin", url]),
            750: (700, ["/usr/bin/git", "remote-https", "origin", url]),
            700: (100, ["git", "-C", "/srv/cache", "fetch", "origin"]),
        }, False)

    def test_shell_rejects_arbitrary_command(self):
        helper = "/usr/local/libexec/multica-zar-git-credential"
        exact = helper + " get"
        for sh_command in (exact + "; echo extra", "echo " + exact, exact + "  "):
            with self.subTest(command=sh_command):
                self.verify({
                    900: (850, ["python3", helper, "get"]),
                    850: (800, ["/bin/sh", "-c", sh_command, sh_command]),
                    800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
                    700: (100, ["git", "-C", "/srv/cache", "fetch", "origin"]),
                }, False)

    def test_shell_rejects_push_and_extra_ancestor(self):
        helper = "/usr/local/libexec/multica-zar-git-credential"
        exact = helper + " get"
        chain = {
            900: (850, ["python3", helper, "get"]),
            850: (800, ["/bin/sh", "-c", exact, exact]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "push", "origin", "main"]),
        }
        self.verify(chain, False)
        chain[700] = (600, ["git", "-C", "/srv/cache", "fetch", "origin"])
        chain[600] = (100, ["sh", "-c", "git fetch"])
        self.verify(chain, False)

    def test_shell_rejects_wrong_git_helper_argv(self):
        helper = "/usr/local/libexec/multica-zar-git-credential"
        exact = helper + " get"
        self.verify({
            900: (850, ["python3", helper, "token"]),
            850: (800, ["/bin/sh", "-c", exact, exact]),
            800: (700, ["git-remote-https", "origin", "https://github.com/x/y"]),
            700: (100, ["git", "-C", "/srv/cache", "fetch", "origin"]),
        }, False)

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
        original_readlink = broker.os.readlink
        def bad_exe(path):
            if str(path).startswith("/proc/"):
                return "/tmp/fake-python"
            return original_readlink(path)
        with patch.object(broker, "daemon_pid", return_value=100), \
             patch.object(broker, "proc_status", side_effect=status), \
             patch.object(pathlib.Path, "read_bytes", cmdline), \
             patch.object(broker.os, "readlink", side_effect=bad_exe):
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
            "path": "jtrtdhrst/zar-i-szlif.git"
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
        self.assertEqual(result[0]["role"], "cache-reader")
        get_token.assert_called_once()

    def test_daemon_cache_never_gets_raw_token_operation(self):
        result, get_token = self.make_request("token")
        self.assertEqual(result, [{"ok": False, "error": "no_active_multica_task"}])
        get_token.assert_not_called()


class ScopedRoleTests(unittest.TestCase):
    def test_harness_project_uses_harness_only_role(self):
        scope = {"repo_urls": ["https://github.com/jtrtdhrst/harness-zar-i-szlif.git"]}
        self.assertEqual(broker.scoped_role("implementer", scope), "implementer-harness")
        self.assertEqual(
            broker.scoped_role("reviewer", scope,
                               "jtrtdhrst/harness-zar-i-szlif"),
            "reviewer-harness",
        )

    def test_product_project_uses_product_only_role(self):
        scope = {"repo_urls": ["https://github.com/jtrtdhrst/zar-i-szlif"]}
        self.assertEqual(broker.scoped_role("implementer", scope, "jtrtdhrst/zar-i-szlif"),
                         "implementer-product")

    def test_foreign_repository_denied_even_when_allowlisted(self):
        scope = {"repo_urls": ["https://github.com/jtrtdhrst/harness-zar-i-szlif"]}
        with self.assertRaisesRegex(ValueError, "outside task scope"):
            broker.scoped_role("implementer", scope, "jtrtdhrst/zar-i-szlif")

    def test_redirect_alias_not_in_project_scope_is_denied(self):
        scope = {"repo_urls": ["https://github.com/jtrtdhrst/harness-zar-i-szlif.git"]}
        with self.assertRaises(ValueError):
            broker.scoped_role("reviewer", scope,
                               "miloszspyrka-code/harness-zar-i-szlif")

    def test_empty_or_unknown_scope_fails_closed(self):
        for scope in ({"repo_urls": []},
                      {"repo_urls": ["https://github.com/other/repo"]}):
            with self.subTest(scope=scope):
                with self.assertRaises(ValueError):
                    broker.scoped_role("implementer", scope)

    def test_project_token_scope_validation(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "token": "ghs_" + "synthetic-do-not-use",
                "role": "implementer-harness",
                "expires_at": "2099-01-01T00:00:00Z",
                "repositories": ["jtrtdhrst/harness-zar-i-szlif"],
                "permissions": broker.ROLE_PERMISSIONS["implementer"],
            }
            path = pathlib.Path(directory) / "implementer-harness.json"
            path.write_text(json.dumps(payload))
            self.assertEqual(
                broker.read_role_token(pathlib.Path(directory), "implementer-harness")["role"],
                "implementer-harness",
            )
            payload["repositories"] = sorted(broker.ALLOWED_REPOS)
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "repository scope mismatch"):
                broker.read_role_token(pathlib.Path(directory), "implementer-harness")


class TaskScopeHandlerTests(unittest.TestCase):
    def make_handler(self, requested_repo):
        import io
        import json
        import struct
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import Mock

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        roles = pathlib.Path(directory.name) / "agent-roles.json"
        roles.write_text(json.dumps({"agent-1": "implementer"}))
        h = object.__new__(broker.Handler)
        h.request = Mock()
        h.request.getsockopt.return_value = struct.pack("3i", 900, 997, 981)
        h.rfile = io.BytesIO(json.dumps({
            "op": "credential", "protocol": "https", "host": "github.com",
            "path": requested_repo,
        }).encode() + b"\n")
        h.server = SimpleNamespace(daemon_unit="unit", pidfile=None,
                                   allow_any_daemon=False, tokens=pathlib.Path("/no/tokens"),
                                   roles_file=roles)
        result = []
        h.reply = result.append
        return h, result

    def test_task_token_is_bound_to_daemon_project_scope(self):
        h, result = self.make_handler("jtrtdhrst/harness-zar-i-szlif.git")
        with patch.object(broker, "task_agent", return_value=("agent-1", "task-1", "tok")), \
             patch.object(broker, "task_repo_scope", return_value={
                 "workspace_id": broker.EXPECTED_WORKSPACE,
                 "task_id": "task-1",
                 "agent_id": "agent-1",
                 "repo_urls": ["https://github.com/jtrtdhrst/harness-zar-i-szlif"],
             }), \
             patch.object(broker, "token_for_role", return_value={
                 "token": "synthetic-test-only", "expires_at": "2099-01-01T00:00:00Z"
             }) as get_token:
            h.handle()
        self.assertEqual(result[0]["role"], "implementer-harness")
        get_token.assert_called_once_with(pathlib.Path("/no/tokens"), "implementer-harness")

    def test_task_cannot_request_foreign_project_repo(self):
        h, result = self.make_handler("jtrtdhrst/zar-i-szlif.git")
        with patch.object(broker, "task_agent", return_value=("agent-1", "task-1", "tok")), \
             patch.object(broker, "task_repo_scope", return_value={
                 "workspace_id": broker.EXPECTED_WORKSPACE,
                 "task_id": "task-1",
                 "agent_id": "agent-1",
                 "repo_urls": ["https://github.com/jtrtdhrst/harness-zar-i-szlif"],
             }), \
             patch.object(broker, "token_for_role") as get_token:
            h.handle()
        self.assertEqual(result, [{"ok": False, "error": "repository_not_allowed"}])
        get_token.assert_not_called()

    def test_task_scope_mismatch_denies_credentials(self):
        h, result = self.make_handler("jtrtdhrst/harness-zar-i-szlif.git")
        with patch.object(broker, "task_agent", return_value=("agent-1", "task-1", "tok")), \
             patch.object(broker, "task_repo_scope", return_value=None) as scope, \
             patch.object(broker, "token_for_role") as get_token:
            h.handle()
        self.assertEqual(result, [{"ok": False, "error": "no_active_multica_task"}])
        scope.assert_called_once_with("tok")
        get_token.assert_not_called()


class CacheTokenScopeTests(unittest.TestCase):
    def test_cache_token_accepts_exact_contents_read(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "token": "ghs_" + "synthetic-do-not-use",
                "role": "cache-reader",
                "expires_at": "2099-01-01T00:00:00Z",
                "repositories": sorted(broker.ALLOWED_REPOS),
                "permissions": {"contents": "read", "metadata": "read"},
            }
            (pathlib.Path(directory) / "cache-reader.json").write_text(json.dumps(payload))
            read = broker.read_role_token(pathlib.Path(directory), "cache-reader")
            self.assertEqual(read["permissions"], payload["permissions"])

    def test_cache_token_rejects_pr_write_and_wrong_role(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "token": "ghs_" + "synthetic-do-not-use",
                "role": "cache-reader",
                "expires_at": "2099-01-01T00:00:00Z",
                "repositories": sorted(broker.ALLOWED_REPOS),
                "permissions": {"contents": "read", "metadata": "read",
                                "pull_requests": "write"},
            }
            path = pathlib.Path(directory) / "cache-reader.json"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "permissions mismatch"):
                broker.read_role_token(pathlib.Path(directory), "cache-reader")
            del payload["permissions"]["pull_requests"]
            payload["role"] = "reviewer"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "permissions mismatch"):
                broker.read_role_token(pathlib.Path(directory), "cache-reader")

    def test_cache_token_rejects_unapproved_repo_scope(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "token": "ghs_" + "synthetic-do-not-use",
                "role": "cache-reader",
                "expires_at": "2099-01-01T00:00:00Z",
                "repositories": ["jtrtdhrst/zar-i-szlif"],
                "permissions": {"contents": "read", "metadata": "read"},
            }
            (pathlib.Path(directory) / "cache-reader.json").write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "repository scope mismatch"):
                broker.read_role_token(pathlib.Path(directory), "cache-reader")


if __name__ == "__main__":
    unittest.main()
