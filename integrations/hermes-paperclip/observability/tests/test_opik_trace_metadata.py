"""Exercise actual transformed start_root_trace with an in-memory SDK spy."""
import ast
import datetime
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apply_opik_segmentation import transform

SOURCE = '''import datetime

def start_root_trace(
    task_key: str,
    *,
    task_id: str,
    session_id: str,
    platform: str,
    provider: str,
    model: str,
    api_mode: str,
    messages: object,
    client: object,
    turn_id: str = "",
    api_request_id: str = "",
):
    trace_input = extract_last_user_message(messages)
    metadata = {
        "source": "hermes",
        "task_id": task_id,
        "provider": provider,
        "model": model,
        "platform": platform,
    }
    # Build the create payload once and keep it:
    create_kwargs = {
        "name": "Hermes turn",
        "project_name": project_name(),
        "thread_id": session_id or None,
        "input": trace_input,
        "metadata": metadata,
        "tags": tags(),
        "start_time": datetime.datetime.now(datetime.timezone.utc),
    }
    return client.trace(**create_kwargs)
'''


def run_spy(plugin_path: str, *, task_id: str, session_id: str) -> dict:
    result = transform(SOURCE)
    bytecode = compile(result, plugin_path, "exec")
    fake = Mock()
    fake.trace.return_value = object()
    namespace = {
        "__file__": plugin_path,
        "__name__": "test_hermes_observability",
        "Path": Path,
        "datetime": datetime,
        "extract_last_user_message": lambda messages: {"content": "test"},
        "project_name": lambda: "hermes",
        "tags": lambda: ["hermes"],
    }
    exec(bytecode, namespace)
    namespace["start_root_trace"](
        "key", task_id=task_id, session_id=session_id, platform="api_server",
        provider="openai-codex", model="gpt-6-luna", api_mode="codex_responses",
        messages=[{"role": "user", "content": "test"}], client=fake,
    )
    fake.trace.assert_called_once()
    return fake.trace.call_args.kwargs


@contextmanager
def configured_plugin(role: str, mode: str = "cloud", bank_id: str | None = None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "profiles" / role
        plugin = root / "plugins/opik/lifecycle.py"
        plugin.parent.mkdir(parents=True)
        config = root / "hindsight/config.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({
            "mode": mode, "bank_id": bank_id or "hermes-" + role,
            "apiKey": "SENSITIVE_TEST_SENTINEL_DO_NOT_LOG",
        }), encoding="utf-8")
        yield str(plugin)


class OpikTraceMetadataTest(unittest.TestCase):
    def test_verified_role_bank_and_paperclip_thread(self):
        run_id = "paperclip:run:7f7df793-3ff0-4d17-b287-3126c34fcbff"
        with configured_plugin("cpo", "local_external") as plugin:
            got = run_spy(
                plugin, task_id=run_id, session_id="session-real-0123",
            )
        self.assertEqual(got["project_name"], "hermes")
        self.assertEqual(got["thread_id"], run_id)
        self.assertEqual(got["metadata"]["task_id"], run_id)
        self.assertEqual(got["metadata"]["agent_role"], "cpo")
        self.assertEqual(got["metadata"]["memory_bank"], "hermes-cpo")
        self.assertEqual(got["metadata"]["memory_backend"], "local_external")
        self.assertNotIn("SENSITIVE_TEST_SENTINEL_DO_NOT_LOG", str(got))
        self.assertEqual(got["metadata"]["service"], "hermes-gateway")
        self.assertEqual(got["tags"], ["hermes", "agent:cpo"])

    def test_cli_thread_unchanged_and_service_segmentation(self):
        with configured_plugin("harness-engineer", "cloud") as plugin:
            got = run_spy(plugin, task_id="local-98abc", session_id="cli-canonical")
        self.assertEqual(got["thread_id"], "cli-canonical")
        self.assertEqual(got["metadata"]["agent_role"], "harness-engineer")
        self.assertEqual(got["metadata"]["memory_bank"], "hermes-harness-engineer")
        self.assertEqual(got["metadata"]["memory_backend"], "cloud")

    def test_invalid_paperclip_label_does_not_become_thread(self):
        got = run_spy(
            "/opt/data/profiles/cho/plugins/opik/lifecycle.py",
            task_id="paperclip:run:not-a-real-uuid",
            session_id="session-fallback",
        )
        self.assertEqual(got["thread_id"], "session-fallback")
        self.assertEqual(got["metadata"]["task_id"], "paperclip:run:not-a-real-uuid")
        self.assertEqual(got["metadata"]["agent_role"], "cho")

    def test_mismatched_hindsight_bank_cannot_claim_memory_label(self):
        with configured_plugin("cho", "local_external", bank_id="hermes-cpo") as plugin:
            got = run_spy(plugin, task_id="local-test", session_id="session-test")
        self.assertEqual(got["metadata"]["agent_role"], "cho")
        self.assertNotIn("memory_bank", got["metadata"])
        self.assertNotIn("memory_backend", got["metadata"])

    def test_missing_memory_config_is_unclassified(self):
        got = run_spy("/opt/data/profiles/cto/plugins/opik/lifecycle.py",
                      task_id="local-xyz", session_id="test")
        self.assertEqual(got["metadata"]["agent_role"], "cto")
        self.assertNotIn("memory_bank", got["metadata"])
        self.assertNotIn("memory_backend", got["metadata"])

    def test_shared_plugin_does_not_fake_identity(self):
        got = run_spy(
            "/opt/data/plugins/opik/lifecycle.py",
            task_id="local-45", session_id="unknown",
        )
        self.assertNotIn("agent_role", got["metadata"])
        self.assertNotIn("memory_bank", got["metadata"])
        self.assertEqual(got["tags"], ["hermes"])


if __name__ == "__main__":
    unittest.main()
