#!/usr/bin/env python3
"""Replace cross-role OTel plugin symlinks with private per-role, verified copies.

No shell, no secrets, no daemon restarts; role-local immutable source layout.
"""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import stat
import sys
import tempfile

ROOT = Path('/srv/multica-zar/.hermes/profiles')
NAME = 'traceverse_hermes_otel'
SOURCE = ROOT/'mascot-designer'/'plugins'/NAME
EXCLUDE = shutil.ignore_patterns('.git', '.github', '__pycache__', '.pytest_cache', 'tests', 'docs', '*.pyc')
REQUIRED = ('plugin.yaml', '__init__.py', 'provider.py', 'emitter.py', 'log_emitter.py')
UID, GID = 997, 981

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(path):
    for filename in REQUIRED:
        f = path/filename
        if not f.is_file() or f.is_symlink() or digest(f) != digest(SOURCE/filename):
            raise RuntimeError('source verification failed: '+filename)
    if any(f.is_symlink() for f in path.rglob('*')):
        raise RuntimeError('unsafe symlink in private plugin copy')

def migrate(role, apply):
    home=ROOT/role
    target=home/'plugins'/NAME
    if role=='mascot-designer':return (role,'source',None)
    if not target.is_symlink():
        if target.is_dir():
            verify(target)
            return (role,'local_verified',None)
        raise RuntimeError('unexpected non-symlink plugin path in '+role)
    if target.resolve() != SOURCE.resolve():
        raise RuntimeError('unexpected symlink target in '+role)
    if not apply: return (role,'needs_local_copy',None)
    backupdir=home/'backups'/'opik-otel-link-20261119'
    backupdir.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chown(backupdir,UID,GID)
    backup=backupdir/NAME
    if backup.exists() or backup.is_symlink():
        raise RuntimeError('backup collision for '+role)
    stage=Path(tempfile.mkdtemp(prefix='.otel-stage-',dir=home/'plugins'))
    try:
        # create stage under each isolated role; never traverse symlinks during copy
        shutil.copytree(SOURCE,stage,dirs_exist_ok=True,symlinks=False,ignore=EXCLUDE)
        for p in [stage,*stage.rglob('*')]:
            if p.is_symlink(): raise RuntimeError('source embedded symlink')
            if p.is_dir():
                p.chmod(0o700)
            elif p.is_file():
                p.chmod(0o600)
            os.chown(p,UID,GID)
        verify(stage)
        os.replace(target,backup)
        try: os.replace(stage,target)
        except BaseException:
            os.replace(backup,target)
            raise
        verify(target)
        return (role,'fixed_verified',str(backup))
    finally:
        if stage.exists(): shutil.rmtree(stage)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--role')
    args=ap.parse_args()
    if not SOURCE.is_dir() or SOURCE.is_symlink():raise RuntimeError('unexpected source plugin')
    allroles=sorted(x.name for x in ROOT.iterdir() if (x/'plugins'/NAME).exists())
    roles=[args.role] if args.role else allroles
    for role in roles:
        if role not in allroles:raise RuntimeError('unknown role '+role)
        print(*migrate(role,args.apply)[:2])
if __name__=='__main__':
    try:main()
    except Exception as e:print('ERROR',type(e).__name__,str(e),file=sys.stderr);sys.exit(1)
