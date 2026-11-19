#!/usr/bin/env python3
"""Objective tool-call pairing from native Multica run events.

Never exports messages, tool names, arguments or results.
This measures trace completeness, NOT final output correctness or E2E readiness.
"""
from collections import Counter
from typing import Any

def pairing_metrics(messages:list[dict[str,Any]])->dict[str,Any]:
    if not isinstance(messages,list):return {'tool_flow_state':'unavailable'}
    uses,results=Counter(),Counter()
    malformed=0
    for m in messages:
        if not isinstance(m,dict):continue
        kind=m.get('type')
        if kind not in ('tool_use','tool_result'):continue
        call_id=m.get('call_id')
        if not isinstance(call_id,str) or len(call_id)>256 or len(call_id)<4:
            malformed+=1
            continue
        if kind=='tool_use':uses[call_id]+=1
        else:results[call_id]+=1
    total_uses=sum(uses.values())
    total_results=sum(results.values())
    if malformed or not total_uses:
        return {'tool_flow_state':'unavailable'}
    matched=sum(min(count,results.get(key,0)) for key,count in uses.items())
    ratio=round(matched/max(total_uses,total_results),6)
    consistent=matched==total_uses==total_results and all(count==1 for count in uses.values()) and all(count==1 for count in results.values())
    return dict(tool_flow_state='measured',tool_calls=total_uses,
                tool_results=total_results,tool_matches=matched,
                tool_pairing_ratio=ratio,tool_pairing_complete=consistent)

def scores(metrics:dict[str,Any])->dict[str,float]:
    return {'multica_tool_pairing_ratio':metrics['tool_pairing_ratio']} if metrics.get('tool_flow_state')=='measured' else {}

if __name__=='__main__':
    def e(kind,ident):return {'type':kind,'call_id':ident,'input':{'secret':'MUST_NOT_EXPORT'}}
    ok=pairing_metrics([e('tool_use','call-123'),e('tool_result','call-123')])
    assert ok['tool_pairing_ratio']==1 and ok['tool_pairing_complete']
    broken=pairing_metrics([e('tool_use','call-123'),e('tool_use','call-456'),e('tool_result','call-123')])
    assert broken['tool_pairing_ratio']==0.5 and not broken['tool_pairing_complete']
    assert scores(pairing_metrics([]))=={}
    assert 'secret' not in str(ok)
    assert pairing_metrics([e('tool_use','')])['tool_flow_state']=='unavailable'
    print('TOOL_PAIRING_NO_PAYLOAD_UNIT_TESTS PASS')
