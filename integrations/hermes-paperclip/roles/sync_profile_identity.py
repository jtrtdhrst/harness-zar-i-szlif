#!/usr/bin/env python3
"""Sync only a short per-profile identity header from an approved Paperclip agent registry snapshot.
No credentials, no task execution, no shared SOUL, no unreviewed Wiki inclusion.
"""
import argparse,hashlib,json,pathlib,re,shutil,sys
HOME=pathlib.Path("/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/profiles")
ROOT=pathlib.Path("/opt/hermes-gateway-ops")
START="<!-- PAPERCLIP_AGENT_IDENTITY_BEGIN -->"
END="<!-- PAPERCLIP_AGENT_IDENTITY_END -->"
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--apply",action="store_true")
 args=ap.parse_args()
 d=json.loads((ROOT/"paperclip-agent-identities.json").read_text())
 rows=d["profiles"]
 if len(rows)!=14 or len({r["profile"] for r in rows})!=14:
  raise ValueError("Only exactly 14 unique approved real profiles")
 backup=ROOT/"backups"/"soul-identity-20261103"
 changed=[]
 for row in rows:
  profile=row["profile"]
  if not re.fullmatch(r"[a-z][a-z0-9-]+",profile) or profile in {"hermes-test","delivery-release-manager"}: raise ValueError("Invalid profile")
  path=HOME/profile/"SOUL.md"
  if path.is_symlink() or not path.is_file():raise ValueError("Missing or unsafe profile identity "+profile)
  existing=path.read_text(encoding="utf-8")
  if (START in existing)!=(END in existing):raise ValueError("Malformed managed marker "+profile)
  if START in existing:
   clean=existing[:existing.index(START)]+existing[existing.index(END)+len(END):]
   # Strip only the single newline following the managed section.
   if clean.startswith("\n"):clean=clean[1:]
  else:clean=existing
  name=row["name"];title=row["title"];aid=row["agent_id"]
  if not all(isinstance(x,str) and x and "\n" not in x for x in (name,title,aid)):raise ValueError("Malformed identity metadata")
  header=(
   f"{START}\n"
   f"Your named Paperclip agent identity is {name} ({title}).\n"
   f"Paperclip agent ID: {aid}.\n"
   "Paperclip is the authoritative control plane for your task assignments, role instructions, "
   "approved skills, Wiki and per-run permission grants. Follow the current authorized run context. "
   "Never claim a role-specific tool, permission, worktree or credential without verifying it. "
   "Do not substitute identity metadata for the full Paperclip AGENTS.md instructions. "
   "Never access another agent's memory or act outside the assigned issue scope.\n"
   f"{END}\n"
  )
  target=header+clean
  if target!=existing:changed.append(profile)
  if args.apply and target!=existing:
   backup.mkdir(mode=0o700,parents=True,exist_ok=True)
   b=backup/(profile+".SOUL.md")
   if not b.exists():shutil.copy2(path,b)
   tmp=path.with_name(".SOUL.md.paperclip-tmp")
   if tmp.exists():raise ValueError("Unclaimed temporary file")
   tmp.write_text(target,encoding="utf-8")
   tmp.chmod(0o640)
   shutil.chown(tmp,user=10000,group=10000)
   tmp.replace(path)
 for row in rows:
  if args.apply:
   s=(HOME/row["profile"]/"SOUL.md").read_text()
   assert START in s and END in s and row["agent_id"] in s
 print(json.dumps({"mode":"APPLY" if args.apply else "AUDIT","profiles":len(rows),"changed":changed,"identity_headers_verified":len(rows) if args.apply else len(rows)-len(changed)}))
 return 0
if __name__=="__main__":sys.exit(main())
