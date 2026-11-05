import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
import worker
from worker import safe_timeline
RUN="20269f6a-ec02-426c-9921-c9afac2f8adb"
AGENT="ada5390b-b87e-43f3-a250-3657811e7a0c"
def rec(kind="MCP_CALL_RESULT",agent=AGENT):
 event={"kind":kind,"paperclip_run_id":RUN,"paperclip_agent_id":agent,
  "at":"2026-11-05T14:20:00.000Z","tool":"wiki.search",
  "mcp_server":"paperclip-mcp","error_code":"SUCCESS","upstream_status":200,
  "arg_excerpt":"DO_NOT_EXPORT_PRIVATE_ARGUMENT","error_excerpt":"DO_NOT_EXPORT_TOKEN",
  "auth_context":{"bearer":"DO_NOT_EXPORT_CREDENTIAL"},"output_chars":124}
 return (json.dumps({"chunk":"pc_obs "+json.dumps(event)})+"\n").encode()
class TimelineTests(unittest.TestCase):
 def test_whitelist_and_identity(self):
  result=safe_timeline(rec()+rec(agent="00000000-0000-0000-0000-000000000000"),RUN,AGENT)
  self.assertEqual(result["event_count"],1)
  self.assertEqual(result["events"][0]["tool"],"wiki.search")
  self.assertIn("source_at",result["events"][0])
  self.assertNotIn("DO_NOT_EXPORT",json.dumps(result))
 def test_bounded(self):
  result=safe_timeline(rec()*15,RUN,AGENT,limit=3)
  self.assertEqual(result["event_count"],15)
  self.assertTrue(result["sample_truncated"])
  self.assertEqual(len(result["events"]),3)
 def test_invalid_and_foreign(self):
  result=safe_timeline(b'{"chunk":"pc_obs bad-json"}\n'+rec(kind="IGNORED"),RUN,AGENT)
  self.assertEqual(result["event_count"],0)
  self.assertEqual(result["parse_errors"],1)
class StatsTests(unittest.TestCase):
 def test_only_numeric_counts_are_exported(self):
  original=worker.api
  worker.api=lambda *args: {
   "total_nodes":12,"nodes_by_fact_type":{"world":5,"experience":7,"malicious":"DO_NOT_EXPORT"},
   "operations_by_status":{"completed":10,"failed":"SECRET"},
   "last_memory_write_at":"2026-11-05T14:20:00.000Z"}
  try:
   safe=worker.stats("http://allowed", "hermes-cho")
   self.assertEqual(safe["nodes_by_fact_type"],{"world":5,"experience":7})
   self.assertNotIn("SECRET",json.dumps(safe))
  finally:worker.api=original
 def test_untrusted_category_names_never_exported(self):
  original=worker.api
  worker.api=lambda *args: {
   "links_by_fact_type":{"world":2,"PRIVATE_BEARER_SECRET":11},
   "links_by_link_type":{"semantic":3,"secret_credential_value":7},
   "operations_by_status":{"completed":5,"unknown_token_name":8}}
  try:
   safe=worker.stats("http://allowed","hermes-cho")
   self.assertEqual(safe["links_by_fact_type"],{"world":2,"other":11})
   self.assertEqual(safe["links_by_link_type"],{"semantic":3,"other":7})
   self.assertEqual(safe["operations_by_status"],{"completed":5,"other":8})
   self.assertNotIn("SECRET",json.dumps(safe))
   self.assertNotIn("credential",json.dumps(safe))
   self.assertNotIn("token_name",json.dumps(safe))
  finally:worker.api=original
class SafeReaderTests(unittest.TestCase):
 def make_log(self,root,content=b"{}\n"):
  log=Path(root)/"11111111-1111-4111-8111-111111111111"/AGENT/(RUN+".ndjson")
  log.parent.mkdir(parents=True,exist_ok=True)
  log.write_bytes(content)
  return log
 def test_safe_regular_file(self):
  with tempfile.TemporaryDirectory() as tmp:
   log=self.make_log(tmp)
   self.assertEqual(worker.read_log_safely(log),b"{}\n")
 def test_incomplete_final_ndjson_line_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   log=self.make_log(tmp,b"{}")
   with self.assertRaisesRegex(RuntimeError,"unterminated_final_ndjson_line"):
    worker.read_log_safely(log)
 def test_symlink_leaf_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   log=self.make_log(tmp)
   outside=Path(tmp)/"private.ndjson";outside.write_bytes(b"{}\n")
   log.unlink();log.symlink_to(outside)
   with self.assertRaises(OSError):worker.read_log_safely(log)
 def test_symlink_parent_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   company=root/"11111111-1111-4111-8111-111111111111"
   company.mkdir()
   outside=root/"outside";outside.mkdir()
   (outside/(RUN+".ndjson")).write_bytes(b"{}\n")
   (company/AGENT).symlink_to(outside,target_is_directory=True)
   with self.assertRaises(OSError):
    worker.read_log_safely(company/AGENT/(RUN+".ndjson"))
 def test_overlarge_file_is_rejected_before_read(self):
  with tempfile.TemporaryDirectory() as tmp:
   log=self.make_log(tmp,b"12345\n")
   with patch.object(worker,"MAX_BYTES",3):
    with self.assertRaisesRegex(RuntimeError,"invalid_log_file"):
     worker.read_log_safely(log)

if __name__=="__main__":unittest.main()
