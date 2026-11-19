#!/usr/bin/env python3
"""Correct false Hermes TTFT in 14 role-local Opik plugins.
Only report measured TTFT if a true provider-supplied value is available in ms.
No guessed streaming timing, secret expansion or daemon restart.
"""
from pathlib import Path
import hashlib,os,sys,tempfile,shutil
ROOT=Path('/srv/multica-zar/.hermes/profiles')
BACKUP=Path('/opt/operations/multica-opik/backups/20261119-ttft')
OLD="""        # The same measured wall-clock value serves two purposes: it backdates
        # the chat span start (real span duration in waterfalls) and fills the
        # shared TTFT field (for non-streaming calls TTFT == full latency).
        ttft_ms = call_duration_ms
"""
NEW="""        # API wall-clock duration is NOT time-to-first-token. In non-streaming
        # Hermes requests first-token timing is unavailable. Only emit a
        # separately measured provider TTFT expressed explicitly in ms.
        raw_ttft_ms = kwargs.get("ttft_ms")
        ttft_ms = None
        if raw_ttft_ms is not None and not isinstance(raw_ttft_ms, bool):
            try:
                measured_ttft_ms = float(raw_ttft_ms)
                if (0 <= measured_ttft_ms < float("inf") and
                    (call_duration_ms is None or measured_ttft_ms <= call_duration_ms)):
                    ttft_ms = measured_ttft_ms
            except (TypeError, ValueError, OverflowError):
                pass
"""
def digest(b):return hashlib.sha256(b).hexdigest()
def main(apply):
 files=sorted(ROOT.glob('*/plugins/traceverse_hermes_otel/__init__.py'))
 if len(files)!=14:raise RuntimeError('missing_plugin_profile')
 originals=[(p,p.read_bytes()) for p in files]
 if any(p.parent.is_symlink() for p,_ in originals):raise RuntimeError('cross_role_symlink')
 if len({digest(b) for _,b in originals})!=1:raise RuntimeError('plugin_source_divergence')
 original=originals[0][1].decode('utf-8')
 if NEW in original:
  print('ALREADY_PATCHED',len(files),'sha256',digest(originals[0][1]));return
 if original.count(OLD)!=1:raise RuntimeError('upstream_code_not_matching_expected')
 patched=original.replace(OLD,NEW).encode('utf-8')
 compile(patched,'__init__.py','exec')
 print('PRECHECK roles='+str(len(files)),'old_sha='+digest(originals[0][1]),'new_sha='+digest(patched))
 if not apply:return
 BACKUP.mkdir(parents=True,exist_ok=False,mode=0o700)
 try:
  for p,b in originals:
   dest=BACKUP/(p.parents[2].name+'.__init__.py')
   dest.write_bytes(b)
   dest.chmod(0o600)
   if dest.read_bytes()!=b:raise RuntimeError('backup_corrupt')
  written=[]
  try:
   for p,_ in originals:
    fd,tmp=tempfile.mkstemp(prefix='.ttft-',dir=str(p.parent))
    try:
     os.write(fd,patched);os.fchmod(fd,0o600);os.fchown(fd,997,981);os.fsync(fd)
    finally:os.close(fd)
    os.replace(tmp,p)
    if digest(p.read_bytes())!=digest(patched):raise RuntimeError('verification_fail')
    written.append(p)
  except BaseException:
   for p in written:
    p.write_bytes((BACKUP/(p.parents[2].name+'.__init__.py')).read_bytes())
    p.chmod(0o600);os.chown(p,997,981)
   raise
  print('PATCHED',len(written),'SHA256',digest(patched))
 except BaseException:
  if not any(p.read_bytes()==patched for p,_ in originals):shutil.rmtree(BACKUP)
  raise
if __name__=='__main__':
 try:main('--apply' in sys.argv)
 except Exception as e:print('ERROR',type(e).__name__,str(e),file=sys.stderr);sys.exit(1)
