#!/usr/bin/env python3
"""Read-only Paperclip run-log and Hindsight bank-stat exporter to existing Opik traces."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BANKS={"0425b468-4ded-4350-a8b4-539ff601a1eb":"hermes-lifecycle-ops","7d8fe327-8143-4b17-8906-00ce435758b1":"hermes-cpo","a9de363c-345f-4b32-822d-4c847c4819fe":"hermes-designer","78608591-71b4-471f-a5eb-17122d8db7da":"hermes-cmo","ada5390b-b87e-43f3-a250-3657811e7a0c":"hermes-harness-engineer","da8d1a1d-dd22-4716-a142-0420b0147672":"hermes-coo","7cbc484a-bd04-4a7b-bc16-cbd643acf519":"hermes-ceo","2e4b7d95-5938-43fa-af09-a86245a1ef47":"hermes-email-creative","1a9eba12-8a05-4a58-ac99-17d1bc80ed62":"hermes-mcp-engineer","2642a166-36dc-475b-8e17-f9332f769636":"hermes-ui-qa","ff703eba-3c3d-46f0-b265-df0db1101a19":"hermes-cto","5595f2c4-95e2-4c3e-97b4-c00d4e4d6601":"hermes-cho","3fe90c23-8386-40d5-b0a8-52d8c40f812e":"hermes-engineer","43957949-8d00-4020-85d7-b69caf71d8c2":"hermes-mascot-designer"}
UUID=re.compile(r"^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$")
SAFE_EVENTS=frozenset(("SKILL_MANIFEST","PROMPT_SNAPSHOT","SKILL_LOAD_ATTEMPT",
 "SKILL_LOADED","SKILL_LOAD_FAILED","MCP_CALL_ATTEMPT","MCP_CALL_RESULT",
 "TOOL_SELECTED","TOOL_UNAVAILABLE","COMPACTION","PERMISSION_DECISION",
 "MEMORY_READ","MEMORY_WRITE","HINDSIGHT_RECALL","HINDSIGHT_RETAIN"))
SAFE_ERRORS=frozenset(("SUCCESS","AUTH_DENIED","UNAUTHORIZED","PERMISSION_DENIED",
 "AUTHORIZATION_FAILED","GRANT_EXPIRED","NOT_FOUND","TOOL_NOT_FOUND",
 "TIMEOUT","RATE_LIMITED","NETWORK_ERROR","UNKNOWN_ERROR","VALIDATION_FAILED",
 "HTTP_ERROR","MCP_TOOL_ERROR","MCP_TRANSPORT_ERROR","SCHEMA_INVALID"))
NAMESPACE=uuid.UUID("b91da63d-dc08-42b8-b915-732344882ee4")
MAX_BYTES=8000000
def now():
 return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None
HTTP=urllib.request.build_opener(NoRedirect)
def api(base,path,params=None,body=None):
 url=base.rstrip("/")+path
 if params:url+="?"+urllib.parse.urlencode(params)
 payload=json.dumps(body,separators=(",",":")).encode() if body is not None else None
 req=urllib.request.Request(url,method="POST" if body is not None else "GET",
  data=payload,headers={"Content-Type":"application/json","Accept":"application/json"})
 with HTTP.open(req,timeout=8) as response:
  if response.status not in (200,201,204):raise RuntimeError("unexpected_backend_status")
  raw=response.read(2000000)
  return json.loads(raw) if raw else {}
def is_uuid(v):return isinstance(v,str) and bool(UUID.fullmatch(v))
def parse_events(raw,run,agent):
 kinds,errors,invalid,ignored={},{},0,0
 for line in raw.splitlines():
  if b"pc_obs " not in line:continue
  try:
   outer=json.loads(line)
   text=outer.get("chunk")
   if not isinstance(text,str) or not text.startswith("pc_obs "):
    ignored+=1;continue
   ev=json.loads(text[7:])
   if ev.get("paperclip_run_id")!=run or ev.get("paperclip_agent_id")!=agent:
    ignored+=1;continue
   kind=ev.get("kind")
   if not isinstance(kind,str) or kind not in SAFE_EVENTS:
    ignored+=1;continue
   kinds[kind]=kinds.get(kind,0)+1
   if kind=="MCP_CALL_RESULT":
    code=ev.get("error_code")
    label=code if isinstance(code,str) and code in SAFE_ERRORS else "OTHER_UNCLASSIFIED"
    errors[label]=errors.get(label,0)+1
  except (ValueError,TypeError,KeyError):
   invalid+=1
 return {"event_counts":kinds,"mcp_result_categories":errors,
  "parsed_event_count":sum(kinds.values()),"invalid_records":invalid,
  "ignored_records":ignored,"source_log_sha256":hashlib.sha256(raw).hexdigest(),
  "source_log_size_bytes":len(raw),"raw_log_exported":False}
def candidates(root,quiet,age_hours):
 if root.is_symlink() or not root.is_dir():raise RuntimeError("bad_log_root")
 found=[];ts=time.time()
 for company in root.iterdir():
  if company.is_symlink() or not company.is_dir() or not is_uuid(company.name):continue
  for agent in company.iterdir():
   if agent.is_symlink() or not agent.is_dir() or agent.name not in BANKS:continue
   for log in agent.glob("*.ndjson"):
    if log.is_symlink() or not log.is_file() or not is_uuid(log.stem):continue
    info=log.stat();delta=ts-info.st_mtime
    if 0<info.st_size<=MAX_BYTES and quiet<delta<age_hours*3600:
     found.append((log,agent.name,log.stem,info.st_mtime))
 found.sort(key=lambda x:x[3],reverse=True)
 return found[:120]
def trace_for(opik,agent,run,cache):
 project="paperclip-"+agent[:8]
 if project not in cache:
  traces=[]
  for page in range(1,5):
   data=api(opik,"/v1/private/traces",{"project_name":project,"size":100,"page":page})
   traces+=data.get("content",[])
   if page*100>=data.get("total",0):break
  cache[project]=traces
 matches=[t for t in cache[project] if
  (t.get("metadata") or {}).get("paperclip_run_id")==run and
  (t.get("metadata") or {}).get("agent_id")==agent]
 return matches[0] if len(matches)==1 and matches[0].get("end_time") else None
def span_names(opik,project,trace_id):
 names=set()
 for page in range(1,5):
  d=api(opik,"/v1/private/spans",{"project_name":project,
   "trace_id":trace_id,"size":100,"page":page})
  names.update(x.get("name") for x in d.get("content",[]))
  if page*100>=d.get("total",0):break
 return names
def identity(run,name):return str(uuid.uuid5(NAMESPACE,run+"/"+name+"/1"))
def emit(opik,project,trace,run,agent,name,output,metadata,start,end):
 body={"spans":[{"id":identity(run,name),"project_name":project,"trace_id":trace,
  "name":name,"type":"general","start_time":start,"end_time":end,
  "input":{"run_id":run},"output":output,
  "metadata":{"paperclip_run_id":run,"agent_id":agent,**metadata}}]}
 api(opik,"/v1/private/spans/batch",body=body)
def stats(hindsight,bank):
 if bank not in BANKS.values():raise ValueError("unknown_bank")
 d=api(hindsight,"/v1/default/banks/"+urllib.parse.quote(bank,safe="")+"/stats")
 keys=("total_nodes","total_links","total_documents","pending_operations",
  "failed_operations","pending_consolidation","failed_consolidation","total_observations")
 safe={k:d[k] for k in keys if type(d.get(k))==int}
 finished=(d.get("operations_by_status") or {}).get("completed")
 if type(finished)==int:safe["completed_operations"]=finished
 date=d.get("last_memory_write_at")
 if isinstance(date,str) and len(date)<60:safe["last_memory_write_at"]=date
 return safe
def enrich(log,agent,run,opik,hindsight,cache):
 trace=trace_for(opik,agent,run,cache)
 if trace is None:return 0
 project="paperclip-"+agent[:8]
 present=span_names(opik,project,trace["id"])
 added=0
 if "paperclip.run.audit_summary" not in present:
  raw=log.read_bytes()
  if len(raw)>MAX_BYTES or len(raw)!=log.stat().st_size:
   raise RuntimeError("log_changed")
  summary=parse_events(raw,run,agent)
  if summary["parsed_event_count"]>0:
   emit(opik,project,trace["id"],run,agent,"paperclip.run.audit_summary",summary,
    {"evidence":"paperclip_run_ndjson_counts_only",
     "run_status":"unknown_without_paperclip_status_api",
     "trace_identity_verified":True,"raw_log_content_exported":False},
    trace["start_time"],trace["end_time"])
   added+=1
 if hindsight and "hindsight.bank.stats_snapshot" not in present:
  bank=BANKS[agent];snapshot=stats(hindsight,bank)
  if snapshot:
   at=now()
   emit(opik,project,trace["id"],run,agent,"hindsight.bank.stats_snapshot",snapshot,
    {"evidence":"private_hindsight_stats_only","bank_id":bank,
     "bank_used_in_this_run":"unverified","memory_contents_exported":False,
     "snapshot_at":at},at,at)
   added+=1
 return added
def cycle(root,opik,hindsight,quiet,age_hours):
 cache={};added,skipped,failed=0,0,0
 for log,agent,run,_ in candidates(root,quiet,age_hours):
  try:
   created=enrich(log,agent,run,opik,hindsight,cache)
   if created:added+=1
   else:skipped+=1
  except Exception as exc:
   failed+=1
   print(json.dumps({"event":"error","run_id":run,
    "error_class":type(exc).__name__}),flush=True)
 return {"event":"cycle","at":now(),"runs_enriched":added,
  "runs_skipped":skipped,"runs_failed":failed}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--once",action="store_true")
 p.add_argument("--quiet-seconds",type=int,default=55)
 p.add_argument("--age-hours",type=int,default=4)
 args=p.parse_args()
 root=Path(os.environ.get("PAPERCLIP_LOG_ROOT","/paperclip-logs"))
 opik=os.environ.get("OPIK_INTERNAL_BASE","http://backend-s7a4rwqbij7w4fxlnauriblo:8080")
 hindsight=os.environ.get("HINDSIGHT_INTERNAL_BASE","")
 if not (opik.startswith("http://backend-") and opik.endswith(":8080")):
  raise SystemExit("unsafe_opik_target")
 if hindsight and not (hindsight.startswith("http://hindsight-admin-") and hindsight.endswith(":8888")):
  raise SystemExit("unsafe_hindsight_target")
 while True:
  try:print(json.dumps(cycle(root,opik,hindsight,args.quiet_seconds,args.age_hours)),flush=True)
  except Exception as exc:
   print(json.dumps({"event":"cycle_failed","error_class":type(exc).__name__}),flush=True)
   if args.once:raise
  if args.once:break
  time.sleep(75)
if __name__=="__main__":main()
