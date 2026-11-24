#!/usr/bin/env python3
"""Privacy-preserving execution metrics from native Multica run events.

Never exports tool names, arguments, outputs, comments, or identifiers of calls.
Tool observation is not tool success or acceptance of issue DoD.
"""
from collections import Counter
from datetime import datetime
from typing import Any

def elapsed(start, end):
    try:
        a = datetime.fromisoformat(start.replace('Z', '+00:00'))
        b = datetime.fromisoformat(end.replace('Z', '+00:00'))
        if a.tzinfo is None or b.tzinfo is None:
            return None
        delta = (b-a).total_seconds()
        return round(delta, 6) if 0 <= delta <= 31*86400 else None
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None

def native_items(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get('items'), list):
        return value['items']
    raise ValueError('unexpected_native_collection')

def pairing_metrics(messages:Any, start=None, expected_run_id=None, expected_issue_id=None)->dict[str,Any]:
    try:
        messages = native_items(messages)
    except ValueError:
        return {'tool_flow_state':'unavailable'}
    uses, results, names = Counter(), Counter(), Counter()
    first = None
    malformed = 0
    for m in messages:
        if not isinstance(m,dict):
            malformed += 1
            continue
        if expected_run_id and m.get('task_id') != expected_run_id:
            return {'tool_flow_state':'identity_mismatch'}
        if expected_issue_id and m.get('issue_id') != expected_issue_id:
            return {'tool_flow_state':'identity_mismatch'}
        kind = m.get('type')
        if kind not in ('tool_use','tool_result'):
            continue
        call_id = m.get('call_id')
        if not isinstance(call_id,str) or not 4 <= len(call_id) <= 256:
            malformed += 1
            continue
        if kind == 'tool_use':
            uses[call_id] += 1
            name = m.get('tool')
            if isinstance(name,str) and 0 < len(name) <= 256:
                names[name] += 1
            delay = elapsed(start,m.get('created_at'))
            if delay is not None:
                first = delay if first is None else min(first,delay)
        else:
            results[call_id] += 1
    if malformed:
        return {'tool_flow_state':'unavailable'}
    u, r = sum(uses.values()), sum(results.values())
    matched = sum(min(count,results.get(key,0)) for key,count in uses.items())
    out = dict(tool_flow_state='measured',tool_calls=u,tool_results=r,tool_matches=matched,
               tool_pairing_complete=(matched == u == r and all(n==1 for n in uses.values()) and all(n==1 for n in results.values())),
               repeated_tool_name_calls=sum(n-1 for n in names.values()),
               tool_name_observations=sum(names.values()))
    if max(u,r):
        out['tool_pairing_ratio'] = round(matched/max(u,r),6)
    if first is not None:
        out['first_observed_tool_call_seconds'] = first
    return out

def scores(metrics:dict[str,Any])->dict[str,float]:
    measured = metrics.get('tool_flow_state') == 'measured'
    out = {'multica_tool_flow_measured':float(measured)}
    if not measured:
        return out
    for key,name in (
        ('tool_pairing_ratio','multica_tool_pairing_ratio'),
        ('tool_calls','multica_tool_calls_observed'),
        ('first_observed_tool_call_seconds','multica_first_observed_tool_call_seconds'),
        ('repeated_tool_name_calls','multica_repeated_tool_name_calls')):
        if key in metrics:
            out[name] = float(metrics[key])
    return out

if __name__=='__main__':
    def e(kind,ident,**kw):
        return {'type':kind,'call_id':ident,'input':{'secret':'MUST_NOT_EXPORT'},**kw}
    ok = pairing_metrics({'items':[e('tool_use','call-123'),e('tool_result','call-123')]})
    assert ok['tool_pairing_ratio']==1 and ok['tool_pairing_complete']
    broken=pairing_metrics([e('tool_use','call-123'),e('tool_use','call-456'),e('tool_result','call-123')])
    assert broken['tool_pairing_ratio']==0.5 and not broken['tool_pairing_complete']
    assert scores(pairing_metrics([]))=={'multica_tool_flow_measured':1.0,'multica_tool_calls_observed':0.0,'multica_repeated_tool_name_calls':0.0}
    assert 'secret' not in str(ok)
    assert pairing_metrics([e('tool_use','')])['tool_flow_state']=='unavailable'
    assert pairing_metrics([e('tool_result','call-123')])['tool_pairing_ratio']==0
    assert pairing_metrics([e('tool_use','call-123',task_id='foreign')],expected_run_id='local')['tool_flow_state']=='identity_mismatch'
    assert elapsed('2026-11-24T10:00:00Z','2026-11-24T10:00:02Z')==2
    assert elapsed('2026-11-24T10:00:02Z','2026-11-24T10:00:00Z') is None
    print('TOOL_PAIRING_NO_PAYLOAD_UNIT_TESTS PASS')
