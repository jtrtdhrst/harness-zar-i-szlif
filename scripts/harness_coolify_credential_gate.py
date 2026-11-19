#!/usr/bin/env python3
"""Read-only, fail-closed Coolify credential rotation gate for 3 controllers.

No token value is ever printed, stored in argv/logs or sent anywhere except
a GET to the configured loopback Coolify API. No provider writes or deployment.
"""
import argparse
import hmac
import json
import os
import re
import stat
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

OLD = Path("/root/coolify-secrets/coolify_api_token")
CONTROLLERS = {
  "harness": (Path("/usr/local/libexec/harness_native_delivery.py"), Path("/root/coolify-secrets/harness_delivery_api_token")),
  "product_image": (Path("/usr/local/libexec/product-image-delivery.py"), Path("/root/coolify-secrets/product_image_delivery_api_token")),
  "product_mcp_host": (Path("/usr/local/libexec/product_mcp_host_delivery.py"), Path("/root/coolify-secrets/product_mcp_host_delivery_api_token")),
}
UUID = re.compile(r"[a-z0-9]{20,32}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
CONTAINER = re.compile(r"[a-z0-9][a-z0-9_.-]{1,127}\Z")
BASE = "http://127.0.0.1:8001/api/v1"

class Denied(Exception): pass

def read_secret(path):
  fd = None
  try:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o777 != 0o600:
      raise Denied("insecure_secret_permissions")
    raw = os.read(fd, 16385)
    if not raw or len(raw) > 16384:
      raise Denied("invalid_secret_size")
    try: token = raw.strip().decode("ascii")
    except UnicodeError: raise Denied("invalid_secret_encoding") from None
    if not token or any(c.isspace() for c in token):
      raise Denied("invalid_secret_format")
    return token
  except OSError:
    raise Denied("secret_unavailable_or_symlink") from None
  finally:
    if fd is not None: os.close(fd)

def get_status(token, uuid):
  if not UUID.fullmatch(uuid): raise Denied("invalid_service_uuid")
  req = urllib.request.Request(BASE + "/services/" + uuid, method="GET",
                               headers={"Authorization": "Bearer " + token})
  try:
    with urllib.request.urlopen(req, timeout=8) as resp: return resp.status
  except urllib.error.HTTPError as e: return e.code
  except (OSError, TimeoutError): raise Denied("coolify_unreachable") from None

def source_flags(src, candidate):
  try: text = src.read_text(encoding="utf8")
  except OSError: raise Denied("controller_missing") from None
  return {"legacy_ref": str(OLD) in text, "dedicated_ref": str(candidate) in text}

def decide(phase, refs, legacy_status, candidate_status, collision, same_image):
  reasons = []
  if not same_image: reasons.append("image_changed")
  if phase == "inspect":
    if legacy_status == 200: reasons.append("legacy_token_active")
    if any(x["legacy_ref"] for x in refs.values()): reasons.append("shared_legacy_path_active")
    reasons.append("rotation_incomplete")
  else:
    if phase == "staged" and legacy_status != 200:
      reasons.append("cannot_verify_working_legacy_baseline")
    if phase == "revoked" and legacy_status != 401:
      reasons.append("old_token_not_revoked")
    if phase == "revoked" and any(x["legacy_ref"] for x in refs.values()):
      reasons.append("controllers_still_reference_old_token")
    if phase == "revoked" and any(not x["dedicated_ref"] for x in refs.values()):
      reasons.append("controllers_not_switched")
    for name in CONTROLLERS:
      if name not in candidate_status: reasons.append(name + "_missing_candidate")
      elif candidate_status[name] != 200: reasons.append(name + "_candidate_not_authorized")
    if collision: reasons.append("credential_reuse_detected")
  return sorted(set(reasons))

def main(argv=None):
  a = argparse.ArgumentParser(description=__doc__)
  a.add_argument("--phase", choices=["inspect","staged","revoked"], default="inspect")
  a.add_argument("--legacy-service-uuid", required=True)
  a.add_argument("--target", action="append", default=[], metavar="CONTROLLER=SERVICE_UUID")
  a.add_argument("--expected-image-id", required=True)
  a.add_argument("--container", default="plasmic-mcp-a6ci2beifbinzckfnneiqnjd")
  args = a.parse_args(argv)
  output = {"phase":args.phase,"result":"BLOCKED","reasons":[],"http_statuses":{},"source_references":{}}
  try:
    if not IMAGE.fullmatch(args.expected_image_id): raise Denied("invalid_expected_image")
    if not CONTAINER.fullmatch(args.container): raise Denied("invalid_container")
    r = subprocess.run(["docker","inspect",args.container,"--format","{{.Image}}"],
                       capture_output=True,text=True,timeout=12)
    if r.returncode: raise Denied("container_not_found")
    old = read_secret(OLD)
    legacy_status = get_status(old,args.legacy_service_uuid)
    output["http_statuses"]["legacy"] = legacy_status
    refs = {name:source_flags(*pair) for name,pair in CONTROLLERS.items()}
    output["source_references"] = refs
    targets = {}
    for entry in args.target:
      name,sep,uuid = entry.partition("=")
      if not sep or name not in CONTROLLERS or name in targets or not UUID.fullmatch(uuid):
        raise Denied("invalid_target_spec")
      targets[name] = uuid
    statuses = {};tokens=[old]
    if args.phase != "inspect":
      if set(targets) != set(CONTROLLERS): raise Denied("all_three_targets_required")
      for name,(_,path) in CONTROLLERS.items():
        try: token=read_secret(path)
        except Denied: continue
        statuses[name] = get_status(token,targets[name])
        tokens.append(token)
    output["http_statuses"]["candidates"] = statuses
    reused = any(hmac.compare_digest(a,b) for i,a in enumerate(tokens) for b in tokens[i+1:])
    output["reasons"]=decide(args.phase,refs,legacy_status,statuses,reused,r.stdout.strip()==args.expected_image_id)
    if not output["reasons"]: output["result"]="PASS"
  except (Denied, OSError, subprocess.TimeoutExpired) as e:
    output["reasons"] = [str(e) if isinstance(e,Denied) else "host_probe_error"]
  print(json.dumps(output,sort_keys=True))
  return 0 if output["result"]=="PASS" else 1

if __name__=="__main__":
  sys.exit(main())
