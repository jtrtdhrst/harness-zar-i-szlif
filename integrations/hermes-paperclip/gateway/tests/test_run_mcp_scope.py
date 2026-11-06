"""Positive lifecycle tests for the native Hermes per-run MCP scope.

No production keys or network connections. The sole mock is Hermes'
session_local_mcp._borrowed boundary; validation and cleanup are real.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_mcp import InvalidRunGrant, borrowed_run_tools


def grant(role: str, run_id: str) -> dict:
    expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
    return {
        "version": 1,
        "company_id": "company-canary",
        "agent_id": "agent-canary",
        "issue_id": "KOMAA-1512",
        "run_id": run_id,
        "profile": role,
        "scopes": ["tools:call"],
        "expires_at": expiry.isoformat(),
        "servers": [{"name": "paperclip",
                     "url": "https://paperclip-mcp.zariszlif.pl/mcp",
                     "token": "synthetic-canary-token"}],
    }


class FakeNativeRegistry:
    def __init__(self):
        self.events: list[tuple] = []
        self.active: dict[str, dict] = {}
        self.connections = 1

    def names(self, scope, servers):
        return {i: "isolated_" + scope.replace(":", "_") + "_" + str(i)
                for i in range(len(servers))}

    @contextmanager
    def borrowed(self, authority, scope, servers, names, cwd, *, partial):
        self.events.append(("open", scope, tuple(names.values())))
        self.active[scope] = {"server": servers[0]["name"], "count": len(servers)}
        try:
            yield ({"tool_a": {"type": "object"}}, {i: True for i in range(self.connections)})
        finally:
            self.events.append(("closed", scope))
            self.active.pop(scope, None)

    @contextmanager
    def installed(self):
        fake = types.ModuleType("gateway.session_local_mcp")
        fake._server_names = self.names
        fake._borrowed = self.borrowed
        with patch.dict(sys.modules, {"gateway.session_local_mcp": fake}), patch.dict(
            "os.environ", {"HERMES_PAPERCLIP_MCP_URLS": "https://paperclip-mcp.zariszlif.pl/mcp"}
        ):
            yield


class RunMcpScopeTests(unittest.TestCase):
    def test_positive_discovery_and_cleanup(self):
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        with native.installed():
            with borrowed_run_tools(authority, grant("cho", "run-1"),
                                    authenticated_profile="cho", run_id="run-1") as scope:
                self.assertEqual(scope, "paperclip-run:cho:run-1")
                self.assertIn(scope, native.active)
                authority._local_editor_mcp[scope] = "transient"
            self.assertNotIn(scope, native.active)
            self.assertNotIn(scope, authority._local_editor_mcp)
        self.assertEqual([x[0] for x in native.events], ["open", "closed"])
        self.assertNotIn("synthetic-canary-token", str(native.events))

    def test_concurrent_isolation_distinct_role_and_run(self):
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        with native.installed():
            with borrowed_run_tools(authority, grant("cpo", "run-1"),
                                    authenticated_profile="cpo", run_id="run-1") as a:
                with borrowed_run_tools(authority, grant("cto", "run-2"),
                                        authenticated_profile="cto", run_id="run-2") as b:
                    self.assertNotEqual(a, b)
                    self.assertEqual(len(native.active), 2)
                    self.assertNotEqual(native.events[0][2], native.events[1][2])
                self.assertEqual(set(native.active), {a})
            self.assertFalse(native.active)

    def test_invalid_profile_does_not_borrow_any_connection(self):
        native = FakeNativeRegistry()
        with native.installed():
            with self.assertRaises(InvalidRunGrant):
                with borrowed_run_tools(object(), grant("cho", "run-1"),
                                        authenticated_profile="cto", run_id="run-1"):
                    self.fail("wrong-profile must be denied")
        self.assertFalse(native.events)

    def test_negative_missing_discovery_revokes_scope(self):
        native = FakeNativeRegistry()
        native.connections = 0
        authority = types.SimpleNamespace(_local_editor_mcp={})
        with native.installed():
            with self.assertRaises(InvalidRunGrant):
                with borrowed_run_tools(authority, grant("cho", "run-1"),
                                        authenticated_profile="cho", run_id="run-1"):
                    self.fail("no tool discovery must be denied")
        self.assertFalse(native.active)
        self.assertEqual([x[0] for x in native.events], ["open", "closed"])

    def test_agent_exception_propagates_and_cleanup_runs(self):
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        with native.installed():
            with self.assertRaisesRegex(RuntimeError, "agent failed"):
                with borrowed_run_tools(authority, grant("cho", "run-1"),
                                        authenticated_profile="cho", run_id="run-1") as scope:
                    authority._local_editor_mcp[scope] = "transient"
                    raise RuntimeError("agent failed")
        self.assertFalse(native.active)
        self.assertFalse(authority._local_editor_mcp)

    def test_same_profile_simultaneous_runs_are_isolated(self):
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        with native.installed():
            with borrowed_run_tools(authority, grant("cho", "run-1"),
                                    authenticated_profile="cho", run_id="run-1") as first:
                with borrowed_run_tools(authority, grant("cho", "run-2"),
                                        authenticated_profile="cho", run_id="run-2") as second:
                    self.assertNotEqual(first, second)
                    self.assertEqual(set(native.active), {first, second})
                    self.assertNotEqual(native.events[0][2], native.events[1][2])
                self.assertEqual(set(native.active), {first})
            self.assertFalse(native.active)

    def test_cancellation_cleans_up_session_registry(self):
        import asyncio
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        with native.installed():
            with self.assertRaises(asyncio.CancelledError):
                with borrowed_run_tools(authority, grant("cho", "run-cancel"),
                                        authenticated_profile="cho", run_id="run-cancel") as scope:
                    authority._local_editor_mcp[scope] = "transient"
                    raise asyncio.CancelledError()
        self.assertFalse(native.active)
        self.assertFalse(authority._local_editor_mcp)


if __name__ == "__main__":
    unittest.main()
