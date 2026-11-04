import importlib.util,json,hashlib,tempfile,time,unittest,os
from pathlib import Path
from unittest.mock import patch
p=Path(__file__).with_name("worker.py")
spec=importlib.util.spec_from_file_location("worker",p)
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
class Tests(unittest.TestCase):
 def test_secret_output_not_relayed(self):
  run="11111111-1111-4111-8111-111111111111";agent=next(iter(w.BANKS))
  records=[{"kind":"MCP_CALL_ATTEMPT","paperclip_run_id":run,"paperclip_agent_id":agent,
     "args":{"password":"FAKE_SECRET_NEVER_SEND"}},
   {"kind":"MCP_CALL_RESULT","paperclip_run_id":run,"paperclip_agent_id":agent,
     "error_code":"SUCCESS","output":"FAKE_SECRET_NEVER_SEND"},
   {"kind":"MCP_CALL_RESULT","paperclip_run_id":run,"paperclip_agent_id":agent,
     "error_code":"FAKE_SECRET_NEVER_SEND"}]
  raw=b"".join((json.dumps({"chunk":"pc_obs "+json.dumps(z)})+"\n").encode() for z in records)
  result=w.parse_events(raw,run,agent)
  self.assertNotIn("FAKE_SECRET_NEVER_SEND",json.dumps(result))
  self.assertEqual(result["parsed_event_count"],3)
  self.assertEqual(result["mcp_result_categories"],{"SUCCESS":1,"OTHER_UNCLASSIFIED":1})
  self.assertEqual(result["source_log_sha256"],hashlib.sha256(raw).hexdigest())
 def test_wrong_agent_not_attached(self):
  agent=next(iter(w.BANKS));run="11111111-1111-4111-8111-111111111111"
  payload={"content":[{"id":"true","metadata":{"paperclip_run_id":run,"agent_id":agent},
   "end_time":"2026-11-04T20:01:00Z"},{"id":"false",
   "metadata":{"paperclip_run_id":run,"agent_id":"other"},"end_time":"2026-11-04T20:01:00Z"}],"total":2}
  with patch.object(w,"api",return_value=payload):
   self.assertEqual(w.trace_for("http://backend-test:8080",agent,run,{})["id"],"true")
 def test_ambiguous_or_open_trace_denied(self):
  agent=next(iter(w.BANKS));run="11111111-1111-4111-8111-111111111111"
  t={"id":"same","metadata":{"paperclip_run_id":run,"agent_id":agent},"end_time":None}
  with patch.object(w,"api",return_value={"content":[t],"total":1}):
   self.assertIsNone(w.trace_for("http://backend-test:8080",agent,run,{}))
  t["end_time"]="2026-11-04T20:01:00Z"
  with patch.object(w,"api",return_value={"content":[t,t],"total":2}):
   self.assertIsNone(w.trace_for("http://backend-test:8080",agent,run,{}))
 def test_bank_metadata_allowlist(self):
  with patch.object(w,"api",return_value={"total_nodes":3,
    "operations_by_status":{"completed":7},"raw_facts":"NEVER_COPY"}):
   out=w.stats("http://hindsight-admin-test:8888",next(iter(w.BANKS.values())))
  self.assertEqual(out,{"total_nodes":3,"completed_operations":7})
 def test_only_known_agent_logs(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);comp=root/"11111111-1111-4111-8111-111111111111"
   valid=comp/next(iter(w.BANKS));valid.mkdir(parents=True)
   invalid=comp/"22222222-2222-4222-8222-222222222222";invalid.mkdir()
   filename="33333333-3333-4333-8333-333333333333.ndjson"
   f=valid/filename;f.write_text("{}");(invalid/filename).write_text("{}")
   os.utime(f,(time.time()-100,time.time()-100))
   self.assertEqual(len(w.candidates(root,55,4)),1)
 def test_idempotent_existing_name(self):
  agent=next(iter(w.BANKS));run="11111111-1111-4111-8111-111111111111"
  with tempfile.TemporaryDirectory() as d:
   file=Path(d)/"run.ndjson";file.write_text("{}")
   trace={"id":"trace","start_time":"2026-11-04T20:00:00Z","end_time":"2026-11-04T20:01:00Z"}
   with patch.object(w,"trace_for",return_value=trace),\
    patch.object(w,"span_names",return_value={"paperclip.run.audit_summary"}),\
    patch.object(w,"emit") as out:
    self.assertEqual(w.enrich(file,agent,run,"http://backend-test:8080","",{}),0)
    out.assert_not_called()
 def test_stable_ids(self):
  self.assertEqual(w.identity("x","paperclip.run.audit_summary","2026-11-04T20:00:00Z"),w.identity("x","paperclip.run.audit_summary","2026-11-04T20:00:00Z"))
  self.assertNotEqual(w.identity("x","paperclip.run.audit_summary","2026-11-04T20:00:00Z"),w.identity("x","hindsight.bank.stats_snapshot","2026-11-04T20:00:00Z"))
  self.assertEqual(__import__("uuid").UUID(w.identity("x","paperclip.run.audit_summary","2026-11-04T20:00:00Z")).version,7)

 def test_exact_internal_targets(self):
  with patch.dict(os.environ,{"OPIK_INTERNAL_BASE":"http://backend-attacker:8080"}):
   with patch("sys.argv",["worker.py","--once"]):
    with self.assertRaisesRegex(SystemExit,"unsafe_opik_target"):w.main()
  with patch.dict(os.environ,{"OPIK_INTERNAL_BASE":"http://backend-s7a4rwqbij7w4fxlnauriblo:8080",
   "HINDSIGHT_INTERNAL_BASE":"http://hindsight-admin-malicious:8888"}):
   with patch("sys.argv",["worker.py","--once"]):
    with self.assertRaisesRegex(SystemExit,"unsafe_hindsight_target"):w.main()

if __name__=="__main__":unittest.main()
