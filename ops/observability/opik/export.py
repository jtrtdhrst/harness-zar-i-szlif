#!/usr/bin/env python3
"""Fail-closed, metadata-only Multica -> self-hosted Opik exporter.
Reads official Multica CLI as workspace-authenticated Unix users.
Never exports prompt, model response, errors, paths, comments or credentials.
"""
import argparse,datetime,json,re,subprocess,sys,urllib.error,urllib.parse,urllib.request,uuid
from pathlib import Path
CLI='/opt/experiments/multica-poc/bin/multica'
BASE='http://127.0.0.1:5173/api/v1/private'
WORKSPACES={
 'test':dict(user='multica-poc',profile=None,workspace_id='f45460f5-76a8-4c2f-b3eb-5d025a8f8726',project='multica-brutal-e2e'),
 'zar':dict(user='multica-zar',profile='zar-prod',workspace_id='28378cc8-2c3a-4f8e-af1c-63e308407b17',project='multica-zar-i-szlif')
}
SAFE_ID=re.compile(r'^[A-Z][A-Z0-9-]{1,30}-[0-9]{1,8}$')
SAFE_SESSION=re.compile(r'^(?:local-[0-9a-f]{64}|ses_[A-Za-z0-9_-]{6,100})$')
FINAL={'completed','failed','cancelled'}
def cli(workspace,*args):
  command=['runuser','-u',workspace['user'],'--',CLI]
  if workspace['profile']:command+=['--profile',workspace['profile']]
  command+=list(args)+['--output','json']
  p=subprocess.run(command,capture_output=True,text=True,timeout=35)
  if p.returncode!=0:raise RuntimeError('multica_auth_or_cli_unavailable')
  return json.loads(p.stdout)
def api(method,path,body=None):
  data=None if body is None else json.dumps(body,separators=(',',':')).encode()
  req=urllib.request.Request(BASE+path,data=data,method=method,headers={'Content-Type':'application/json','Accept':'application/json'})
  try:
    with urllib.request.urlopen(req,timeout=12) as r:
      raw=r.read(400000)
      return r.status,json.loads(raw) if raw else {}
  except urllib.error.HTTPError as e:
    e.close();return e.code,{}
def iso(value):
  try:
    d=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError
    return d.astimezone(datetime.timezone.utc).isoformat().replace('+00:00','Z')
  except (ValueError,TypeError,AttributeError):raise RuntimeError('invalid_source_timestamp')
def safe_uuid(value):
  if not isinstance(value,str):raise RuntimeError('invalid_uuid')
  return str(uuid.UUID(value))
def projects():
  status,response=api('GET','/projects?size=100')
  if status!=200:raise RuntimeError('opik_projects_read_failed')
  return {v.get('name'):v.get('id') for v in response.get('content',[])}
def ensure_project(name):
  have=projects()
  if name in have:return have[name]
  status,_=api('POST','/projects',{'name':name,'visibility':'private','description':'Automated metadata-only Multica run lifecycle traces; no user prompts/outputs'})
  if status not in (200,201,204,409):raise RuntimeError('opik_project_create_status_'+str(status))
  have=projects()
  if name not in have:raise RuntimeError('opik_project_create_readback_failed')
  return have[name]
def run_payload(run,issue,workspace):
  if run.get('status') not in FINAL or not run.get('completed_at'):return None
  if run.get('workspace_id')!=workspace['workspace_id'] or issue.get('workspace_id')!=workspace['workspace_id']:raise RuntimeError('cross_workspace_run_rejected')
  run_id=safe_uuid(run['id']);issue_id=safe_uuid(issue['id']);agent_id=safe_uuid(run['agent_id'])
  runtime_id=safe_uuid(run['runtime_id']) if run.get('runtime_id') else None
  identifier=issue.get('identifier','')
  if not SAFE_ID.fullmatch(identifier):raise RuntimeError('invalid_issue_identifier')
  created=iso(run.get('started_at') or run.get('dispatched_at') or run.get('created_at'))
  completed=iso(run['completed_at'])
  if completed<created:raise RuntimeError('source_clock_inversion')
  status=run['status']
  usage=[]
  for entry in (run.get('usage') or [])[:8]:
    if not isinstance(entry,dict):continue
    d={k:entry[k] for k in ('input_tokens','output_tokens','cache_read_tokens','cache_write_tokens') if type(entry.get(k))==int and 0<=entry[k]<10**10}
    model=entry.get('model')
    if isinstance(model,str) and re.fullmatch(r'[A-Za-z0-9_./:+-]{1,128}',model):
      d['model']=model
    if d:usage.append(d)
  attempt=run.get('attempt')
  result=run.get('result')
  candidate=result.get('session_id') if isinstance(result,dict) else None
  sdk_thread_id=candidate if isinstance(candidate,str) and SAFE_SESSION.fullmatch(candidate) else None
  meta=dict(origin='multica',source='official_cli',payload_exported=False,source_workspace_id=workspace['workspace_id'],
     source_issue_id=issue_id,source_run_id=run_id,agent_id=agent_id,runtime_id=runtime_id,
     run_status=status,attempt=attempt if type(attempt)==int else None,
     usage_token_counts=usage)
  if sdk_thread_id:
    # The lifecycle trace continues to group by ISSUE; SDK roots use session IDs.
    # This safe, non-secret join key enables exact run->SDK correlation.
    meta['sdk_thread_id']=sdk_thread_id
    meta['hermes_thread_lookup']=sdk_thread_id
  return dict(id=run_id,name='multica.issue_run.'+identifier,project_name=workspace['project'],start_time=created,
              end_time=completed,thread_id=issue_id,tags=['multica','lifecycle','metadata-only'],
              environment='production' if workspace['project']=='multica-zar-i-szlif' else 'isolated-e2e',
              input={'issue_identifier':identifier,'run_id':run_id},
              output={'status':status},metadata=meta)
def export_one(profile,limit,dry):
  workspace=WORKSPACES[profile]
  try:
    visible=cli(workspace,'workspace','list')
  except Exception:
    print('SKIP',profile,'reason=owner_auth_unavailable' if profile=='zar' else 'reason=test_cli_unavailable')
    return 0
  if not any(x.get('id')==workspace['workspace_id'] for x in visible):raise RuntimeError('wrong_workspace_auth')
  collected=[]
  for page in range(6):
    d=cli(workspace,'issue','list','--limit','100','--offset',str(page*100),'--fields','id,identifier,workspace_id,status')
    for issue in d.get('issues',[]):
      if issue.get('workspace_id')!=workspace['workspace_id']:raise RuntimeError('cross_workspace_issue_rejected')
      for run in cli(workspace,'issue','runs',issue['id']):
        item=run_payload(run,issue,workspace)
        if item:collected.append(item)
    if not d.get('has_more'):break
  collected.sort(key=lambda x:x['start_time'],reverse=True)
  if dry:
    print('DRY_RUN',profile,'eligible',len(collected),'planned_max',limit)
    return 0
  proj=ensure_project(workspace['project'])
  count=0;already=0
  for item in collected[:limit]:
    status,old=api('GET','/traces/'+urllib.parse.quote(item['id'],safe=''))
    if status==200:
      if old.get('project_id')!=proj or (old.get('metadata') or {}).get('source_run_id')!=item['id']:
        raise RuntimeError('trace_id_conflict')
      # Backfill only trusted metadata derived from authenticated CLI runs.
      # Preserve other fields and the existing issue thread grouping.
      current_meta=old.get('metadata') or {}
      requested_meta=item['metadata']
      if any(current_meta.get(k)!=v for k,v in requested_meta.items()):
        updated=dict(current_meta)
        updated.update(requested_meta)
        patch_status,_=api('PATCH','/traces/'+urllib.parse.quote(item['id'],safe=''),{'project_id':proj,'metadata':updated})
        if patch_status not in (200,204):raise RuntimeError('opik_trace_metadata_patch_http_'+str(patch_status))
        verify_status,verify=api('GET','/traces/'+urllib.parse.quote(item['id'],safe=''))
        if verify_status!=200 or any((verify.get('metadata') or {}).get(k)!=v for k,v in requested_meta.items()):
          raise RuntimeError('opik_trace_metadata_patch_verify_failed')
      already+=1;continue
    if status!=404:raise RuntimeError('opik_trace_read_http_'+str(status))
    status,_=api('POST','/traces',item)
    if status!=201:raise RuntimeError('opik_trace_write_http_'+str(status))
    check,readback=api('GET','/traces/'+urllib.parse.quote(item['id'],safe=''))
    if check!=200 or readback.get('project_id')!=proj or readback.get('thread_id')!=item['thread_id']:
      raise RuntimeError('opik_trace_readback_failed')
    count+=1
  print('EXPORT',profile,'eligible',len(collected),'created',count,'existing',already,'project',workspace['project'])
  return count
def main():
  p=argparse.ArgumentParser()
  p.add_argument('--profile',choices=['test','zar','both'],default='zar')
  p.add_argument('--max-items',type=int,default=100)
  p.add_argument('--dry-run',action='store_true')
  args=p.parse_args()
  if args.max_items<1 or args.max_items>250:raise RuntimeError('invalid_limit')
  for profile in ['test','zar'] if args.profile=='both' else [args.profile]:
    export_one(profile,args.max_items,args.dry_run)
if __name__=='__main__':
  try:main()
  except Exception as e:
    print('EXPORTER_ERROR',type(e).__name__,str(e)[:80],file=sys.stderr)
    sys.exit(1)
