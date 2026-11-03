#!/usr/bin/env python3
"""Conservative, auditable Hermes profile model mapping matching Paperclip 2026-11-03 readback.
Does not change Paperclip models or credentials. Dry-run unless --apply."""
import argparse, hashlib, json, os, pathlib, re, shutil, tempfile
ROOT=pathlib.Path("/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/profiles")
PROFILES=["ceo","cho","cmo","coo","cpo","cto","designer","email-creative","engineer","harness-engineer","lifecycle-ops","mascot-designer","mcp-engineer","ui-qa"]
GO={"designer","email-creative","engineer","lifecycle-ops","mascot-designer","mcp-engineer","ui-qa"}
assert len(PROFILES)==14 and len(GO)==7
parser=argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true")
a=parser.parse_args()
plan=[]
for p in PROFILES:
 f=ROOT/p/"config.yaml"
 if not f.is_file() or f.is_symlink(): raise SystemExit("UNSAFE_FILE "+p)
 c=f.read_text()
 section=re.search(r"(?ms)^model:\n(?:(?:^  [^\n]*\n)|(?:^\n))*",c)
 if section is None: raise SystemExit("MISSING_MODEL_SECTION "+p)
 old=section.group()
 want_def,want_provider=("deepseek-v4.1-flash","opencode-go") if p in GO else ("gpt-6-luna","openai-codex")
 md=re.search(r"(?m)^  default:\s*(\S+)",old)
 mp=re.search(r"(?m)^  provider:\s*(\S+)",old)
 if not md or not mp: raise SystemExit("MODEL_FIELDS_MISSING "+p)
 curr=(md.group(1),mp.group(1))
 target=(want_def,want_provider)
 if curr!=target and curr!=("gpt-6-luna","openai-codex"): raise SystemExit("UNEXPECTED_CURRENT "+p+" "+str(curr))
 new=old
 new=re.sub(r"(?m)^  default:.*$", "  default: "+want_def,new,count=1)
 new=re.sub(r"(?m)^  provider:.*$", "  provider: "+want_provider,new,count=1)
 transformed=c[:section.start()]+new+c[section.end():]
 plan.append((p,f,c,transformed,curr,target))
changes=[x for x in plan if x[2]!=x[3]]
if a.apply and changes:
 from datetime import datetime,timezone
 backup=pathlib.Path("/opt/hermes-gateway-ops/backups/models-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
 backup.mkdir(parents=True,mode=0o700)
 for p,f,old,new,_,_ in changes:
  shutil.copy2(f,backup/(p+".yaml"))
 for p,f,old,new,_,_ in changes:
  st=f.stat()
  fd,tmp=tempfile.mkstemp(prefix=".model-map-",dir=f.parent)
  try:
   with os.fdopen(fd,"w") as out:out.write(new);out.flush();os.fsync(out.fileno())
   os.chown(tmp,st.st_uid,st.st_gid)
   os.chmod(tmp,st.st_mode & 0o777)
   os.replace(tmp,f)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
  assert f.read_text()==new
 else: pass
 print(json.dumps({"mode":"APPLY","changed":len(changes),"profiles_checked":len(plan),"backup_path":str(backup),"mapping":{p:list(target) for p,_,_,_,_,target in plan}}))
else:
 print(json.dumps({"mode":"AUDIT","changed":len(changes),"profiles_checked":len(plan),"changes":[{"profile":p,"before":list(cur),"after":list(target)} for p,_,_,_,cur,target in changes]}))
