#!/usr/bin/env python3
"""Privacy-preserving Opik tool classification compatibility patch.
Applies only to verified profile-local traceverse_hermes_otel emitter modules.
No content captured: emits an explicit redacted marker in official OTel tool key.
"""
from pathlib import Path
import sys, os, hashlib, tempfile, py_compile, shutil
ROOT=Path('/srv/multica-zar/.hermes/profiles')
NAME='traceverse_hermes_otel'
BACKUP=Path('/opt/operations/multica-opik/backups/20261119-tooltype')
ANCHOR='            span.set_attribute("gen_ai.tool.type", tool_type)\n'
INSERT=('            # Opik maps tool spans by gen_ai.tool.call.arguments/result.\n'
        '            # Preserve strict privacy: never send real tool I/O unless opt-in.\n'
        '            if not self._capture_content:\n'
        '                span.set_attribute("gen_ai.tool.call.arguments", \'{"redacted":true}\')\n'
        '            elif arguments is not None:\n'
        '                _set_if(span, "gen_ai.tool.call.arguments", _safe_str(arguments))\n'
        '            if self._capture_content and result is not None:\n'
        '                _set_if(span, "gen_ai.tool.call.result", _safe_str(result))\n')
FILES=sorted(ROOT.glob('*/plugins/traceverse_hermes_otel/emitter.py'))
def sha(b):return hashlib.sha256(b).hexdigest()
def main(apply):
    assert len(FILES)==14, 'Expected 14 roles'
    data=[(f, f.read_bytes()) for f in FILES]
    assert all(not f.parent.is_symlink() for f,_ in data),'Cross-role symlinks present'
    assert len({sha(b) for _,b in data})==1, 'Role versions diverged; abort'
    old=data[0][1].decode()
    if INSERT in old:
        print('ALREADY_PATCHED',len(data))
        return
    if old.count(ANCHOR)!=1:raise RuntimeError('Unrecognized emitter version')
    new=old.replace(ANCHOR,ANCHOR+INSERT).encode()
    compile(new,'emitter.py','exec')
    print('PLAN',len(data),'roles','from_sha256',sha(data[0][1]),'to_sha256',sha(new))
    if not apply:return
    BACKUP.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(BACKUP,0o700)
    # Preflight all backup paths before any replacements
    for f,b in data:
        bp=BACKUP/(f.parents[2].name+'.emitter.py')
        if bp.exists():raise RuntimeError('Existing backup collision '+str(bp))
        bp.write_bytes(b);os.chmod(bp,0o600)
        if bp.read_bytes()!=b:raise RuntimeError('Backup readback mismatch')
    written=[]
    try:
        for f,_ in data:
            fd,tmp=tempfile.mkstemp(prefix='.otel-type-',dir=str(f.parent))
            try:
                os.write(fd,new);os.fchmod(fd,0o600);os.fchown(fd,997,981);os.fsync(fd)
            finally:os.close(fd)
            os.replace(tmp,f)
            if sha(f.read_bytes())!=sha(new):raise RuntimeError('Post-write hash mismatch')
            written.append(f)
    except BaseException:
        for f in written:
            bp=BACKUP/(f.parents[2].name+'.emitter.py')
            shutil.copy2(bp,f)
            os.chown(f,997,981);os.chmod(f,0o600)
        raise
    print('PATCHED',len(written),'roles; verified hash',sha(new))
if __name__=='__main__':
    try:main('--apply' in sys.argv)
    except Exception as e:print('ERROR',type(e).__name__,str(e),file=sys.stderr);sys.exit(1)
