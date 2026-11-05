#!/usr/bin/env python3
"""Two-file reversible profile rollout, AFTER approved PR39 role segmentation.

Never call apply on a live Gateway: drain, checkpoint, independent review, then
promote a controlled candidate/maintenance window and verify per-profile E2E.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import time
import uuid
from rollout import KNOWN_ROLES, atomic_write, assert_regular_path, digest, sync_dir, RolloutError
import apply_opik_telemetry_privacy as privacy

JOURNAL_DIR = ".opik-privacy-rollout"
PAIR = {
    "lifecycle.py": (privacy.SEGMENTED_LIFECYCLE_SHA256,
                     "e5c9464e94fcddbd075bc25403829e967936b28214b5ab513f5e9b3298f9471c"),
    "hooks.py": (privacy.BASE_HOOKS_SHA256,
                 "d4a222be6571c955e901560f7197809bfc984453993c97c22b1d52a071597f08"),
}

def paths(root: Path) -> dict[str, dict[str, Path]]:
    return {role:{name:root/"profiles"/role/"plugins"/"opik"/name for name in PAIR}
            for role in sorted(KNOWN_ROLES)}

def inspect(root: Path) -> dict[str, dict[str, dict]]:
    if root.is_symlink() or not root.is_dir(): raise RolloutError("unsafe root")
    found={}
    for role, pair in paths(root).items():
        found[role]={}
        for name,path in pair.items():
            assert_regular_path(root,path)
            actual=digest(path.read_bytes())
            if actual not in PAIR[name]:
                raise RolloutError("source drift in "+role+"/"+name)
            stat=path.stat()
            found[role][name]={"hash":actual,"mode":stat.st_mode & 0o777,
                "uid":stat.st_uid,"gid":stat.st_gid}
    return found

def state(root: Path) -> dict:
    snap=inspect(root)
    counts={"segmented_baseline":0,"privacy_patch":0}
    for pair in snap.values():
        states={int(d["hash"]==PAIR[name][1]) for name,d in pair.items()}
        if len(states)!=1:raise RolloutError("mixed per-profile patch state")
        counts["privacy_patch" if states=={1} else "segmented_baseline"]+=1
    if counts["segmented_baseline"] and counts["privacy_patch"]:
        raise RolloutError("mixed role patch state")
    return {"roles":len(snap),**counts,"consistent":True,
            "lifecycle_sha256":PAIR["lifecycle.py"][1],
            "hooks_sha256":PAIR["hooks.py"][1]}

def load_manifest(journal: Path,batch: str) -> dict:
    if not batch or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in batch):
        raise RolloutError("invalid batch ID")
    path=journal/batch/"manifest.json"
    if path.is_symlink() or not path.is_file():raise RolloutError("missing/unsafe journal")
    data=json.loads(path.read_text())
    if data.get("batch")!=batch or data.get("version")!=1 or set(data.get("roles",{}))!=KNOWN_ROLES:
        raise RolloutError("invalid journal")
    return data

def rollback(root: Path,journal: Path,batch: str) -> dict:
    manifest=load_manifest(journal,batch)
    if manifest.get("state") not in ("applying","applied","rolled_back"):
        raise RolloutError("unexpected journal state")
    changes=[]
    for role,pair in paths(root).items():
        for name,path in pair.items():
            assert_regular_path(root,path)
            record=manifest["roles"][role][name]
            backup=journal/batch/role/(name+".bak")
            assert_regular_path(root,backup)
            if record.get("relative_path")!=str(path.relative_to(root)):
                raise RolloutError("journal path drift")
            saved=backup.read_bytes()
            if digest(saved)!=record["before_sha256"]:
                raise RolloutError("backup corrupt")
            present=path.read_bytes()
            if digest(present) not in (record["before_sha256"],record["after_sha256"]):
                raise RolloutError("live file drift; refuse overwrite")
            changes.append((path,saved,record,present!=saved))
    count=0
    for path,saved,record,dirty in changes:
        if dirty:
            atomic_write(path,saved,record["mode"],(record["uid"],record["gid"]))
            count+=1
    manifest["state"]="rolled_back"
    atomic_write(journal/batch/"manifest.json",
        json.dumps(manifest,sort_keys=True,indent=2).encode(),0o600)
    return {"batch":batch,"state":"rolled_back","files_restored":count}

def apply(root: Path,journal: Path) -> dict:
    snap=inspect(root)
    if state(root)["segmented_baseline"]!=len(KNOWN_ROLES):
        raise RolloutError("not all profiles have identical segmented baseline")
    for p in journal.glob("*/manifest.json"):
        if p.is_symlink():raise RolloutError("unsafe manifest")
        if json.loads(p.read_text()).get("state") in ("applying","applied"):
            raise RolloutError("existing active rollout must be resolved")
    # Precompute every output and verify exact pinned hashes before first write.
    planned=[]
    for role,pair in paths(root).items():
        lc,hk=privacy.prepare(pair["lifecycle.py"],pair["hooks.py"])
        data={"lifecycle.py":lc.encode(),"hooks.py":hk.encode()}
        for name,blob in data.items():
            if digest(blob)!=PAIR[name][1]:
                raise RolloutError("patch hash mismatch")
            planned.append((role,name,pair[name],blob))
    batch=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())+"-"+uuid.uuid4().hex[:8]
    folder=journal/batch;folder.mkdir(mode=0o700)
    manifest={"version":1,"batch":batch,"state":"applying","roles":{}}
    for role,name,path,new in planned:
        backup=folder/role
        backup.mkdir(mode=0o700,exist_ok=True)
        old=path.read_bytes()
        atomic_write(backup/(name+".bak"),old,0o600)
        d=snap[role][name]
        manifest["roles"].setdefault(role,{})[name]={
            "relative_path":str(path.relative_to(root)),
            "before_sha256":digest(old),"after_sha256":digest(new),
            "mode":d["mode"],"uid":d["uid"],"gid":d["gid"]}
    atomic_write(folder/"manifest.json",
        json.dumps(manifest,sort_keys=True,indent=2).encode(),0o600)
    sync_dir(folder)
    try:
        for role,name,path,new in planned:
            d=snap[role][name]
            atomic_write(path,new,d["mode"],(d["uid"],d["gid"]))
            if digest(path.read_bytes())!=PAIR[name][1]:
                raise RolloutError("readback mismatch")
        manifest["state"]="applied"
        atomic_write(folder/"manifest.json",
            json.dumps(manifest,sort_keys=True,indent=2).encode(),0o600)
        return {"batch":batch,"state":"applied","files_changed":len(planned)}
    except Exception:
        rollback(root,journal,batch)
        raise

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("status","apply","rollback"))
    p.add_argument("--root",type=Path,default=Path("/opt/data"))
    p.add_argument("--batch-id",default="")
    a=p.parse_args();root=a.root.absolute()
    if a.action=="status":
        print(json.dumps(state(root),indent=2,sort_keys=True));return
    journal=root/JOURNAL_DIR
    if journal.is_symlink():raise RolloutError("unsafe journal")
    journal.mkdir(mode=0o700,exist_ok=True)
    # Use the same flock as the prerequisite segmentation rollout.
    common=root/".opik-segmentation-rollout"
    if common.is_symlink():raise RolloutError("unsafe shared journal")
    common.mkdir(mode=0o700,exist_ok=True)
    lockfile=common/".lock"
    if lockfile.is_symlink():raise RolloutError("unsafe lock")
    with lockfile.open("a+b") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        result=rollback(root,journal,a.batch_id) if a.action=="rollback" else apply(root,journal)
        print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
