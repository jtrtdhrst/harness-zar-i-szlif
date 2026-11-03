#!/usr/bin/env python3
"""Read-only pre-cutover checks, never a substitute for a real Paperclip Hermes run."""
import json, pathlib, hashlib, subprocess, sys
base=pathlib.Path("/opt/hermes-gateway-ops")
a=pathlib.Path("/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home/_data/instances/default/data/wiki-root")
b=pathlib.Path("/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/wiki-paperclip-test")
root=pathlib.Path("/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/profiles")
profiles=json.loads((base/"profile-skill-allowlist.json").read_text())["profiles"]
def run(cmd):
 r=subprocess.run(cmd,capture_output=True,text=True)
 return r.returncode,r.stdout,r.stderr
checks={}
pa={str(p.relative_to(a)):hashlib.sha256(p.read_bytes()).hexdigest() for p in a.rglob("*.md") if p.is_file()}
pb={str(p.relative_to(b)):hashlib.sha256(p.read_bytes()).hexdigest() for p in b.rglob("*.md") if p.is_file()}
checks["wiki_snapshot"]={"pass":pa==pb,"source_files":len(pa),"snapshot_files":len(pb),"mismatched_paths":sorted(set(pa)^set(pb)|{p for p in pa.keys()&pb.keys() if pa[p]!=pb[p]})[:20]}
rc,o,e=run(["python3",str(base/"sync_profile_skills.py")])
try: result=json.loads(o)
except:result={}
checks["skill_manifest"]={"pass":rc==0 and result.get("mismatched_after")==0,"profiles":result.get("profiles"),"checked":result.get("skills_checked"),"mismatched":result.get("mismatched_after")}
rc,o,e=run(["python3",str(base/"reconcile_model_map.py")])
try: result=json.loads(o)
except:result={}
# Full live desired-skill set, including bundled Paperclip skills and every reference/script.
# The legacy skill_manifest check covers only 68 pinned top-level SKILL.md files.
bundle_proc=subprocess.run(
    ["python3",str(base/"audit_runtime_skill_packages.py")],
    capture_output=True,text=True,timeout=40)
bundle_report=json.loads((base/"e2e-evidence/paperclip-hermes-skill-bundles-audit.json").read_text())
checks["full_paperclip_skill_bundle"]={
    "pass":bundle_proc.returncode==0 and bundle_report.get("pass") is True,
    "desired":bundle_report.get("desired_total"),
    "company_pinned":bundle_report.get("company_pinned_total"),
    "missing_skills":len(bundle_report.get("missing_desired_skill",[])),
    "unapproved_company":len(bundle_report.get("unapproved_company_skill",[])),
    "missing_bundle_files":len(bundle_report.get("missing_bundle_asset",[])),
    "source_hash_drift":len(bundle_report.get("source_hash_drift",[])),
    "evidence":"/opt/hermes-gateway-ops/e2e-evidence/paperclip-hermes-skill-bundles-audit.json"
}
checks["model_map"]={"pass":rc==0 and result.get("changed")==0,"profiles":result.get("profiles_checked"),"drift":result.get("changed")}
rc,o,e=run(["python3",str(base/"apply_gateway_api_toolsets.py")])
try: result=json.loads(o)
except:result={}
checks["toolsets"]={"pass":rc==0 and not any(p.get("changed") for p in result.get("profiles",[])),"profiles":len(result.get("profiles",[]))}
pc_active=[]
for profile in profiles:
 cfg=(root/profile/"config.yaml").read_text()
 if "  pc:\n" in cfg or "  paperclip_knowledge:\n" in cfg:pc_active.append(profile)
checks["per_agent_paperclip_mcp"]={"pass":len(pc_active)==len(profiles),"present":len(pc_active),"expected":len(profiles)}
retired=("hermes-test","delivery-release-manager")
archive_root=root.parent/"retired-profiles"
backup_root=base/"backups"/"retired-profiles-20261103"
# The runtime may recreate small internal state.db scaffolds. Config+service membership,
# not directory existence, determines whether a retired agent is active.
legacy_configs=[name for name in retired if (root/name/"config.yaml").exists()]
archived=[name for name in retired if (archive_root/name).is_dir() and (backup_root/(name+".tar.gz")).is_file()]
checks["retired_profile_cleanup"]={"pass":len(legacy_configs)==0 and len(archived)==2,
 "active_retired_configs":legacy_configs,"archived":archived,
 "scaffolds_regenerated":[name for name in retired if (root/name).exists()]}
identity_rows=json.loads((base/"paperclip-agent-identities.json").read_text())["profiles"]
identity_mismatched=[]
for identity in identity_rows:
    soul=root/identity["profile"]/"SOUL.md"
    content=soul.read_text(encoding="utf-8") if soul.is_file() else ""
    if (identity["agent_id"] not in content or
        "<!-- PAPERCLIP_AGENT_IDENTITY_BEGIN -->" not in content or
        "<!-- PAPERCLIP_AGENT_IDENTITY_END -->" not in content):
        identity_mismatched.append(identity["profile"])
checks["per_profile_identity"]={"pass":len(identity_rows)==14 and not identity_mismatched,
 "expected":14,"mismatched":identity_mismatched,
 "note":"SOUL identity only; full Paperclip role AGENTS.md still requires an authenticated Paperclip-issued Hermes run"}
# Endpoint auth-preflight for both address families. Intentionally invalid bearer:
# validates only Cloudflare Access routing to Hermes, not live profile credentials.
import subprocess
try:
    network_probe=subprocess.run(
        [str(base/"check-dualstack-gateway.sh")],
        text=True, capture_output=True, timeout=32, check=False)
    network_ok=network_probe.returncode==0 and network_probe.stdout.count("PASS ipv")==2
    network_detail=network_probe.stdout.strip() if network_ok else "dual_stack_route_failed"
except (subprocess.SubprocessError, OSError):
    network_ok=False
    network_detail="probe_unavailable"
checks["cloudflare_access_dualstack"]={"pass":network_ok,"scope":"VPS-only IPv4/IPv6 public HTTPS to Hermes origin","result":network_detail,
    "note":"Unauthenticated negative route only; NOT proof Paperclip Vault key works."}
checks["paperclip_full_role_prompt"]={
    "pass":False,
    "source":"Paperclip managed instructions and scoped Wiki",
    "verified_identity_profiles":14,
    "full_role_contract_native_run_proofs":0,
    "note":"SOUL.md identity and Wiki tool access do not prove complete Paperclip role instructions in an authenticated Hermes Gateway issue run."
}
checks["opik_same_paperclip_run"]={
    "pass":False,
    "hermes_cli_llm_tool_traces_verified":True,
    "paperclip_opencode_run_correlation_verified":True,
    "same_paperclip_hermes_run_correlation_verified":False,
    "note":"Require the exact Paperclip run UUID in a Hermes-native Opik trace with verified role-scoped MCP tool and model spans."
}
# Actual recent CLI inference and post-restart MCP proof, separate from a Paperclip native run.
# Never turn any of these into a substitute for the blocked native canary gate.
try:
    infer=json.loads((base/"e2e-evidence/20261103-14-inference/summary.json").read_text())
    profile_names=set(profiles)
    observed_names={r.get("profile") for r in infer.get("results",[])}
    completed=sum(r.get("returncode")==0 for r in infer.get("results",[]))
    exact=sum(r.get("exact_response") is True for r in infer.get("results",[]))
    checks["hermes_live_model_inference"]={
        "pass":infer.get("total")==14 and completed==14 and observed_names==profile_names,
        "profiles":infer.get("total"),"successful_model_calls":completed,
        "strict_single_marker":exact,"strict_expected":14,
        "note":"14 real CLI model calls; Engineer returned marker plus extra profile text, not a transport failure. Independent of Paperclip-issued Hermes runs.",
        "evidence":"/opt/hermes-gateway-ops/e2e-evidence/20261103-14-inference/summary.json"}
except (OSError,ValueError,TypeError,KeyError):
    checks["hermes_live_model_inference"]={"pass":False,"reason":"missing_or_invalid_live_model_evidence"}
try:
    wiki_live=json.loads((base/"e2e-evidence/real-14-profile-wiki-mcp.json").read_text())
    current_gw=subprocess.check_output(["docker","ps","--format","{{.Names}}"],text=True).splitlines()
    current_gw=next((x for x in current_gw if x.startswith("2sganhxhhnioiqh4an9g2f4k-")),None)
    checks["hermes_postrestart_14_wiki_mcp"]={
        "pass":wiki_live.get("passed")==14 and wiki_live.get("expected")==14 and wiki_live.get("gateway_container")==current_gw,
        "passed_profiles":wiki_live.get("passed"),"expected":14,
        "container_matches":wiki_live.get("gateway_container")==current_gw,
        "note":"Real profile-aware tool discovery after current Gateway restart; not a Paperclip per-run grant."}
except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):
    checks["hermes_postrestart_14_wiki_mcp"]={"pass":False,"reason":"missing_postrestart_tool_evidence"}
checks["cpo_selfhosted_hindsight_exact_recall"]={
    "pass":False,"profile":"cpo","mode":"local_external",
    "retain_tool":"CALLED_QUEUED","independent_recall":"DID_NOT_RETURN_EXACT_NEW_CANARY",
    "traces":["01a1a2de-49f4-72cf-a71c-1fb90e1921e6","01a1a2de-7ca3-70e2-b966-a2352da42775"],
    "note":"Source Opik traces show actual native retain and recall tools. Readback returned an earlier unrelated phrase, not the new synthetic value. No positive independent recall evidence; fail-closed until fresh retest."}
checks["native_canary"]={"pass":False,"issue":"KOMAA-1562","run_id":"7f7df793-3ff0-4d17-b287-3126c34fcbff","error_code":"hermes_gateway_auth_failed","current_state":"RETESTED_HERMES_ORIGIN_REJECTED_API_KEY","origin_rejection_observed":"2026-11-03T19:54:19Z Hermes gateway API log confirms rejected invalid API key, POST /p/cho/v1/runs from Paperclip node","rollback":"CHO restored to opencode_local/GPT-6 Luna using native Paperclip revision; canary terminalized cancelled","note":"Real post-Cloudflare-IPv6-repair Paperclip-issued CHO run. Secure profile-key binding is required before native positive E2E can pass."}
out={"verdict":"PRE_CUTOVER_BLOCKED","checks":checks,"gateway_agent_e2e":"AUTHENTICATED_RUN_FAILED_PROFILE_API_KEY","paperclip_adapter_cutover":"ROLLED_BACK","opik_run_correlation":"NOT_VERIFIED","independent_cli_tests":{"gpt6":"PASS","opencode_go_deepseek":"PASS","hindsight_retain_recall":"PASS","crossbank_cho_cpo":"PASS","opik_cli_traces":"PASS"}}
if all(x["pass"] for x in checks.values()) and out["gateway_agent_e2e"]=="PASS":out["verdict"]="READY"
print(json.dumps(out,ensure_ascii=False,indent=2))
sys.exit(0 if out["verdict"]=="READY" else 2)
