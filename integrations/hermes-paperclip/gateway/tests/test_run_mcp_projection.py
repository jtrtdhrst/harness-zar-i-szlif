import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_mcp import InvalidRunGrant, _project_scoped_tools


def tool(name):
    return {"type": "function", "function": {"name": name, "description": "test",
            "parameters": {"type": "object", "properties": {}}}}


class RunMcpProjectionTests(unittest.TestCase):
    def setUp(self):
        self.agent = SimpleNamespace(
            tools=[tool("existing")], valid_tool_names={"existing"},
            enabled_toolsets=["core"], disabled_toolsets=[],
            _tool_snapshot_generation=2,
        )
        self.registry = SimpleNamespace(
            _generation=9,
            get_toolset_for_tool=lambda name: {
                "existing": "core", "mcp__scoped__read": "mcp-scoped",
            }.get(name),
        )
        fake_model = ModuleType("model_tools")
        fake_model.get_tool_definitions = self.definitions
        fake_tools = ModuleType("tools")
        fake_tools.__path__ = []
        fake_registry = ModuleType("tools.registry")
        fake_registry.registry = self.registry
        self.modules = {"model_tools": fake_model, "tools": fake_tools,
                        "tools.registry": fake_registry}
        self.fail_scoped = False

    def definitions(self, enabled_toolsets=None, disabled_toolsets=None,
                    quiet_mode=True, skip_tool_search_assembly=False):
        enabled = {"core", "mcp-scoped"} if enabled_toolsets is None else set(enabled_toolsets)
        result = [tool("existing")] if "core" in enabled else []
        if "mcp-scoped" in enabled and not self.fail_scoped:
            result.append(tool("mcp__scoped__read"))
        return result

    def test_tools_available_during_run_then_fully_restored(self):
        original_tools = self.agent.tools
        original_names = self.agent.valid_tool_names
        with patch.dict(sys.modules, self.modules):
            with _project_scoped_tools(self.agent, {"mcp__scoped__read": {}}):
                self.assertIn("mcp__scoped__read", self.agent.valid_tool_names)
                self.assertEqual(self.agent._tool_snapshot_generation, 9)
                self.assertIn("mcp-scoped", self.agent.enabled_toolsets)
        self.assertIs(self.agent.tools, original_tools)
        self.assertIs(self.agent.valid_tool_names, original_names)
        self.assertEqual(self.agent.enabled_toolsets, ["core"])
        self.assertEqual(self.agent._tool_snapshot_generation, 2)

    def test_exception_during_execution_restores_original_inventory(self):
        with patch.dict(sys.modules, self.modules):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                with _project_scoped_tools(self.agent, {"mcp__scoped__read": {}}):
                    raise RuntimeError("synthetic failure")
        self.assertEqual(self.agent.valid_tool_names, {"existing"})
        self.assertEqual(self.agent.enabled_toolsets, ["core"])

    def test_disabled_projection_fails_closed(self):
        self.fail_scoped = True
        with patch.dict(sys.modules, self.modules):
            with self.assertRaisesRegex(InvalidRunGrant, "projection denied"):
                with _project_scoped_tools(self.agent, {"mcp__scoped__read": {}}):
                    pass
        self.assertEqual(self.agent.valid_tool_names, {"existing"})

    def test_no_discovered_tools_rejected(self):
        with patch.dict(sys.modules, self.modules):
            with self.assertRaises(InvalidRunGrant):
                with _project_scoped_tools(self.agent, {}):
                    pass

    def test_concurrent_runs_on_one_agent_never_interleave_tool_inventory(self):
        import threading

        first_entered = threading.Event()
        release_first = threading.Event()
        second_entered = threading.Event()
        observed = []

        def first():
            with _project_scoped_tools(self.agent, {"mcp__scoped__read": {}}):
                first_entered.set()
                release_first.wait(2)
                observed.append(("first", set(self.agent.valid_tool_names)))

        def second():
            first_entered.wait(2)
            with _project_scoped_tools(self.agent, {"mcp__scoped__read": {}}):
                second_entered.set()
                observed.append(("second", set(self.agent.valid_tool_names)))

        with patch.dict(sys.modules, self.modules):
            t1 = threading.Thread(target=first)
            t2 = threading.Thread(target=second)
            t1.start()
            t2.start()
            self.assertTrue(first_entered.wait(1))
            self.assertFalse(second_entered.wait(0.2))
            release_first.set()
            t1.join(2)
            t2.join(2)

        self.assertTrue(second_entered.is_set())
        self.assertEqual([name for name, _ in observed], ["first", "second"])
        for _, names in observed:
            self.assertEqual(names, {"existing", "mcp__scoped__read"})
        self.assertEqual(self.agent.valid_tool_names, {"existing"})

    def test_default_toolset_selection_preserved(self):
        self.agent.enabled_toolsets = None
        with patch.dict(sys.modules, self.modules):
            with _project_scoped_tools(self.agent, {"mcp__scoped__read": {}}):
                self.assertIn("existing", self.agent.valid_tool_names)
                self.assertIn("mcp__scoped__read", self.agent.valid_tool_names)
        self.assertIsNone(self.agent.enabled_toolsets)


if __name__ == "__main__":
    unittest.main()
