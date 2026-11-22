"""Negative and positive tests for metadata-only retrieval evidence."""
import json
import unittest
from retrieval_evidence import summarize

RUN = "20269f6a-ec02-426c-9921-c9afac2f8adb"
AGENT = "ada5390b-b87e-43f3-a250-3657811e7a0c"

def record(kind="MCP_CALL_RESULT", server="repowise-harness-mcp",
           tool="get_answer", agent=AGENT, result="SUCCESS"):
    event = {
        "kind": kind, "paperclip_run_id": RUN, "paperclip_agent_id": agent,
        "mcp_server": server, "tool": tool, "error_code": result,
        "arguments": {"private": "SENSITIVE_VALUE"},
        "content": "PRIVATE_MEMORY_PAYLOAD"
    }
    return (json.dumps({"chunk": "pc_obs " + json.dumps(event)}) + "\n").encode()

class RetrievalEvidenceTests(unittest.TestCase):
    def test_only_observed_metadata(self):
        logs = (record("MCP_CALL_ATTEMPT") +
                record("MCP_CALL_RESULT", result="TIMEOUT") +
                record("HINDSIGHT_RECALL", server="hindsight") +
                record("HINDSIGHT_RETAIN", server="hindsight"))
        result = summarize(logs, RUN, AGENT)
        self.assertEqual(result["repowise_attempt_events"], 1)
        self.assertEqual(result["repowise_result_events"], 1)
        self.assertEqual(result["repowise_result_categories"], {"TIMEOUT": 1})
        self.assertEqual(result["repowise_server_target_hints"], ["harness"])
        self.assertEqual(result["hindsight_recall_events"], 1)
        self.assertEqual(result["hindsight_retain_events"], 1)
        self.assertFalse(result["correct_repo_sha_verified"])
        self.assertFalse(result["role_bank_verified"])
        self.assertFalse(result["functional_outcome_verified"])
        self.assertNotIn("SENSITIVE_VALUE", json.dumps(result))
        self.assertNotIn("PRIVATE_MEMORY_PAYLOAD", json.dumps(result))

    def test_foreign_or_forged_source_not_counted(self):
        logs = (record(server="evil-repowise") +
                record(agent="00000000-0000-0000-0000-000000000000") +
                record(tool="unsafe_tool") +
                record(server="repowise-product-mcp", tool="search_codebase"))
        result = summarize(logs, RUN, AGENT)
        self.assertEqual(result["repowise_result_events"], 1)
        self.assertEqual(result["repowise_server_target_hints"], ["product"])

    def test_empty_and_broken_logs(self):
        result = summarize(b'garbage\n' + record(server="github-mcp"),
                           RUN, AGENT)
        self.assertEqual(result["observed_retrieval_events"], 0)

if __name__ == "__main__":
    unittest.main()
