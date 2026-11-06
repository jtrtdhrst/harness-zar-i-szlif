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


    def test_run_tools_become_visible_only_during_own_agent_run(self):
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        agent = types.SimpleNamespace(enabled_toolsets=["skills", "mcp-wiki_fs"], disabled_toolsets=[])
        original = list(agent.enabled_toolsets)
        with native.installed():
            with borrowed_run_tools(authority, grant("cho", "run-binding"),
                                    authenticated_profile="cho", run_id="run-binding", agent=agent):
                bound = [x for x in agent.enabled_toolsets if x not in original]
                self.assertEqual(len(bound), 1)
                self.assertTrue(bound[0].startswith("mcp-isolated_paperclip-run_cho_run-binding"))
                self.assertEqual(agent.enabled_toolsets[:len(original)], original)
            self.assertEqual(agent.enabled_toolsets, original)
        self.assertFalse(native.active)

    def test_agent_disabled_run_mcp_toolset_fails_closed(self):
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        scope = "paperclip-run:cho:run-denied"
        denied = "mcp-" + native.names(scope, [{"name": "paperclip"}])[0]
        agent = types.SimpleNamespace(enabled_toolsets=["skills"], disabled_toolsets=[denied])
        with native.installed():
            with self.assertRaises(InvalidRunGrant):
                with borrowed_run_tools(authority, grant("cho", "run-denied"),
                                        authenticated_profile="cho", run_id="run-denied", agent=agent):
                    self.fail("forbidden toolset must not be exposed")
            self.assertEqual(agent.enabled_toolsets, ["skills"])
        self.assertFalse(native.active)

    def test_concurrent_agents_do_not_inherit_borrowed_toolsets(self):
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        first = types.SimpleNamespace(enabled_toolsets=["skills"], disabled_toolsets=[])
        second = types.SimpleNamespace(enabled_toolsets=["skills"], disabled_toolsets=[])
        with native.installed():
            with borrowed_run_tools(authority, grant("cho", "run-one"),
                                    authenticated_profile="cho", run_id="run-one", agent=first):
                with borrowed_run_tools(authority, grant("cho", "run-two"),
                                        authenticated_profile="cho", run_id="run-two", agent=second):
                    self.assertEqual(len(first.enabled_toolsets), 2)
                    self.assertEqual(len(second.enabled_toolsets), 2)
                    self.assertNotEqual(first.enabled_toolsets[1], second.enabled_toolsets[1])
                self.assertEqual(second.enabled_toolsets, ["skills"])
                self.assertEqual(len(first.enabled_toolsets), 2)
            self.assertEqual(first.enabled_toolsets, ["skills"])
        self.assertFalse(native.active)

    def test_model_visible_catalog_is_refreshed_then_restored(self):
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        old_tools = [{"type": "function", "function": {"name": "tool_search"}}]
        agent = types.SimpleNamespace(
            enabled_toolsets=["skills"], disabled_toolsets=[], quiet_mode=True,
            tools=old_tools, valid_tool_names={"tool_search"})
        mocked_model = types.ModuleType("model_tools")
        mocked_model.get_tool_definitions = lambda **kw: [
            {"type": "function", "function": {"name": "tool_search"}},
            {"type": "function", "function": {"name": "tool_a"}}]
        mocked_oneshot = types.ModuleType("agent.oneshot_footprint")
        mocked_oneshot.prune_oneshot_tools = lambda x: x
        mocked_toolsets = types.ModuleType("toolsets")
        mocked_toolsets.agent_tool_drops = lambda agent: []
        with native.installed(), patch.dict(sys.modules, {
            "model_tools": mocked_model, "agent.oneshot_footprint": mocked_oneshot,
            "toolsets": mocked_toolsets,
        }):
            with borrowed_run_tools(authority, grant("cho", "run-model-catalog"),
                                    authenticated_profile="cho", run_id="run-model-catalog", agent=agent):
                self.assertEqual(agent.valid_tool_names, {"tool_search", "tool_a"})
                self.assertEqual(len(agent.tools), 2)
                self.assertEqual(len(agent.enabled_toolsets), 2)
            self.assertIs(agent.tools, old_tools)
            self.assertEqual(agent.valid_tool_names, {"tool_search"})
            self.assertEqual(agent.enabled_toolsets, ["skills"])

    def test_catalog_missing_run_mcp_schema_fails_closed(self):
        native = FakeNativeRegistry()
        authority = types.SimpleNamespace(_local_editor_mcp={})
        agent = types.SimpleNamespace(
            enabled_toolsets=["skills"], disabled_toolsets=[], quiet_mode=True,
            tools=[{"type": "function", "function": {"name": "tool_search"}}],
            valid_tool_names={"tool_search"})
        mocked_model = types.ModuleType("model_tools")
        mocked_model.get_tool_definitions = lambda **kw: [
            {"type": "function", "function": {"name": "tool_search"}}]
        mocked_oneshot = types.ModuleType("agent.oneshot_footprint")
        mocked_oneshot.prune_oneshot_tools = lambda x: x
        mocked_toolsets = types.ModuleType("toolsets")
        mocked_toolsets.agent_tool_drops = lambda agent: []
        with native.installed(), patch.dict(sys.modules, {
            "model_tools": mocked_model, "agent.oneshot_footprint": mocked_oneshot,
            "toolsets": mocked_toolsets,
        }):
            with self.assertRaises(InvalidRunGrant):
                with borrowed_run_tools(authority, grant("cho", "run-missing-catalog"),
                                        authenticated_profile="cho", run_id="run-missing-catalog", agent=agent):
                    self.fail("unavailable model toolset must be rejected")
            self.assertEqual(agent.enabled_toolsets, ["skills"])
            self.assertEqual(agent.valid_tool_names, {"tool_search"})
        self.assertFalse(native.active)

if __name__ == "__main__":
    unittest.main()
