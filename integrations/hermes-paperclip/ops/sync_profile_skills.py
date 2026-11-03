#!/usr/bin/env python3
"""Full Paperclip-approved company skill bundles -> isolated Hermes profiles.

Default read-only audit. --apply uses atomic, SHA-verified copies, no deletion.
Only canonical Paperclip company-managed skills assigned in the live snapshot,
frozen with every file's SHA-256 in the approved manifest (schema 2).
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,stat,tempfile
from pathlib import Path
SRC_BASE=Path('/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home/_data/instances/default/skills')
DST_BASE=Path('/var/lib/docker/volumes/2sganhxhhnioiqh4an9g2f4k-hermes-gateway-poc-v2-data/_data/profiles')
SAFE=re.compile(r'^[a-z0-9][a-z0-9-]{0,80}$')
SHA=re.compile(r'^[a-f0-9]{64}$')
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def is_safe_dir(path:Path)->bool:return path.is_dir() and not path.is_symlink()
def check_rel(rel:str)->None:
    p=Path(rel)
    if (p.is_absolute() or not rel or rel.startswith('.') or
        any(part in ('','..','.') or part.startswith('.') for part in p.parts)):
        raise ValueError('unsafe relative skill asset name')
def run(manifest_file:Path,source:Path,profiles:Path,apply:bool)->dict:
    manifest=json.loads(manifest_file.read_text())
    roles=manifest.get('profiles')
    company=manifest.get('source_company_id')
    if (manifest.get('schema_version')!=2 or not isinstance(roles,dict) or len(roles)!=14 or
        not isinstance(company,str) or not re.fullmatch(r'[a-f0-9-]{36}',company)):
        raise ValueError('schema 2 + exactly 14 roles required')
    names={v for role,skills in roles.items() for v in skills}
    headpins=manifest.get('approved_sha256')
    filepins=manifest.get('approved_files_sha256')
    if not isinstance(headpins,dict) or not isinstance(filepins,dict) or set(headpins)!=names or set(filepins)!=names:
        raise ValueError('all skills must have approved head and full-file hashes')
    canonical=source/company
    if not is_safe_dir(canonical):raise ValueError('unsafe canonical skills directory')
    validated={}
    for name in sorted(names):
        if not SAFE.fullmatch(name):raise ValueError('invalid skill name')
        skilldir=canonical/name
        if not is_safe_dir(skilldir):raise ValueError('missing canonical skill directory '+name)
        actual={}
        for f in skilldir.rglob('*'):
            if f.is_symlink():raise ValueError('linked canonical skill file '+name)
            if not f.is_file():continue
            if f.stat().st_size>2_000_000:raise ValueError('oversized source skill file')
            rel=f.relative_to(skilldir).as_posix()
            check_rel(rel)
            actual[rel]=sha(f)
        approved=filepins[name]
        if not isinstance(approved,dict) or actual!=approved or actual.get('SKILL.md')!=headpins[name]:
            raise ValueError('UNAPPROVED_SOURCE_SHA '+name)
        validated[name]=tuple(sorted(actual))
    plan=[]
    for role,skills in sorted(roles.items()):
        if not SAFE.fullmatch(role) or not isinstance(skills,list) or len(skills)!=len(set(skills)):
            raise ValueError('invalid role or duplicate skills')
        dstbase=profiles/role/'skills'/'company-managed'
        if not is_safe_dir(dstbase):raise ValueError('unsafe destination base '+role)
        for name in skills:
            dstroot=dstbase/name
            if dstroot.exists() and not is_safe_dir(dstroot):
                raise ValueError('unsafe destination skill '+role+'/'+name)
            for rel in validated[name]:
                target=dstroot/rel
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise ValueError('unsafe destination skill asset')
                for ancestor in target.parents:
                    if ancestor==dstbase:break
                    if ancestor.is_symlink():raise ValueError('unsafe linked destination parent')
                current=sha(target) if target.is_file() else None
                digest=filepins[name][rel]
                plan.append(dict(role=role,skill=name,asset=rel,
                                 source=canonical/name/rel,target=target,sha256=digest,
                                 state='match' if current==digest else ('missing' if current is None else 'drift')))
    changed=[x for x in plan if x['state']!='match']
    if apply:
        for x in changed:
            target=x['target']
            parent=target.parent
            parent.mkdir(parents=True,exist_ok=True,mode=0o755)
            if parent.is_symlink() or not is_safe_dir(parent):raise ValueError('unsafe target parent')
            fd,temp=tempfile.mkstemp(prefix='.paperclip-skill-',dir=parent)
            try:
                with os.fdopen(fd,'wb') as out:
                    out.write(x['source'].read_bytes())
                    out.flush()
                    os.fsync(out.fileno())
                os.chown(temp,10000,10000)
                original_mode=x['source'].stat().st_mode
                os.chmod(temp,0o555 if (original_mode & 0o111) else 0o444)
                if sha(Path(temp))!=x['sha256']:raise RuntimeError('SHA mismatch during copy')
                os.replace(temp,target)
            finally:
                if os.path.exists(temp):os.unlink(temp)
        bad=[x for x in plan if not x['target'].is_file() or sha(x['target'])!=x['sha256']]
        if bad:raise RuntimeError('post-copy SHA mismatch '+str(len(bad)))
    return dict(mode='APPLY' if apply else 'AUDIT',
                profiles=len(roles),skills_checked=sum(len(x) for x in roles.values()),
                unique_skills=len(names),files_checked=len(plan),
                mismatched_before=len(changed),mismatched_after=0 if apply else len(changed),
                missing_files=sum(x['state']=='missing' for x in changed),
                drift_files=sum(x['state']=='drift' for x in changed),
                differences=[{k:x[k] for k in ('role','skill','asset','state')} for x in changed][:30])
def main():
    a=argparse.ArgumentParser()
    a.add_argument('--manifest',type=Path,default=Path(__file__).with_name('profile-skill-allowlist.json'))
    a.add_argument('--source-root',type=Path,default=SRC_BASE)
    a.add_argument('--profiles-root',type=Path,default=DST_BASE)
    a.add_argument('--apply',action='store_true')
    args=a.parse_args()
    result=run(args.manifest,args.source_root,args.profiles_root,args.apply)
    print(json.dumps(result,ensure_ascii=False))
    if result['mismatched_after']:raise SystemExit(2)
if __name__=='__main__':main()
