#!/usr/bin/env python3
"""Fail-closed live Paperclip -> Hermes *entire* skill bundle audit, not SKILL.md-only.
This file is read-only; source snapshot comes from current Paperclip MCP.
"""
from pathlib import Path
import json,hashlib,sys
BASE=Path("/opt/hermes-gateway-ops")
SNAPSHOT=BASE/"e2e-evidence/paperclip-live-desired-skills.json"
MANIFEST=BASE/"profile-skill-allowlist.json"
SRC=Path("/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home/_data/instances/default/skills")
DST=Path("/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/profiles")
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
snap=json.loads(SNAPSHOT.read_text())
manifest=json.loads(MANIFEST.read_text())
assert snap["schema_version"]==1 and len(snap["agents"])==14
assert len(set(x["profile"] for x in snap["agents"]))==14
company_id=manifest["source_company_id"]
report={"source":"Paperclip current desired skill set vs deployed Hermes profile content",
        "agents":14,"desired_total":0,"company_total":0,"company_pinned_total":0,
        "core_total":0,"local_total":0,"missing_desired_skill":[],"unapproved_company_skill":[],"missing_bundle_asset":[],"source_hash_drift":[],"role_summary":[]}
for row in snap["agents"]:
 role=row["profile"]
 actual_skills_dir=DST/role/"skills"
 installed_paths=list(actual_skills_dir.rglob("SKILL.md"))
 installed_names={p.parent.name for p in installed_paths}
 allowed=set(manifest["profiles"][role])
 role_missing=[]
 for detail in row["details"]:
  if detail["state"]!="installed":
   report["missing_desired_skill"].append({"role":role,"key":detail["key"],"reason":"not installed in Paperclip source"})
 for key in row["desired"]:
  report["desired_total"]+=1
  skill=key.split("/")[-1]
  if key.startswith("company/"+company_id+"/"):
   report["company_total"]+=1
   if skill not in allowed:
    report["unapproved_company_skill"].append({"role":role,"key":key})
   else: report["company_pinned_total"]+=1
   src=SRC/company_id/skill
   dst=actual_skills_dir/"company-managed"/skill
   if not (src/"SKILL.md").is_file():
    raise RuntimeError("Canonical Paperclip skill absent "+key)
   for sf in src.rglob("*"):
    if not sf.is_file(): continue
    rel=sf.relative_to(src)
    tf=dst/rel
    if not tf.is_file() or digest(sf)!=digest(tf):
     report["missing_bundle_asset"].append({"role":role,"skill":skill,"asset":str(rel),"reason":"absent" if not tf.is_file() else "SHA_mismatch"})
   if skill in allowed and digest(src/"SKILL.md")!=manifest["approved_sha256"].get(skill):
    report["source_hash_drift"].append({"role":role,"skill":skill})
   if skill not in installed_names:role_missing.append(key)
  elif key.startswith("paperclipai/"):
   report["core_total"]+=1
   runtime=next((d["runtime_name"] for d in row["details"] if d["key"]==key),skill)
   if runtime not in installed_names:role_missing.append(key)
  else:
   report["local_total"]+=1
   runtime=next((d["runtime_name"] for d in row["details"] if d["key"]==key),skill)
   if runtime not in installed_names:role_missing.append(key)
 for missing in role_missing:report["missing_desired_skill"].append({"role":role,"key":missing,"reason":"not visible in profile skill directory"})
 report["role_summary"].append({"profile":role,"desired":len(row["desired"]),"missing":len(role_missing)})
report["pass"]=all(not report[k] for k in ("missing_desired_skill","unapproved_company_skill","missing_bundle_asset","source_hash_drift")) and report["desired_total"]==120
evidence=BASE/"e2e-evidence/paperclip-hermes-skill-bundles-audit.json"
evidence.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({k:(len(v) if isinstance(v,list) else v) for k,v in report.items() if k!="role_summary"},ensure_ascii=False))
print("MISSING_BY_ROLE",json.dumps([x for x in report["role_summary"] if x["missing"]],ensure_ascii=False))
sys.exit(0 if report["pass"] else 2)
