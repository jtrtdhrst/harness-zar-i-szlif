#!/usr/bin/env python3
"""Objective execution signals and Go quota-equivalent cost (not billed USD).

Price provenance: https://docs.opencode.ai/docs/go/ (verified 2026-11-19).
Only price the exact DeepSeek V4.1 Flash route on OpenCode Go.
Never infer missing usage fields, or convert terminal status into quality.
"""
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
from typing import Any

MODEL_ALIASES={'opencode-go:deepseek-v4.1-flash','opencode-go/deepseek-v4.1-flash'}
PRICE_SOURCE='https://docs.opencode.ai/docs/go/'
RATES_OFFPEAK={'input':Decimal('0.15'),'output':Decimal('0.60'),'cache_read':Decimal('0.003')}
RATES_PEAK={'input':Decimal('0.30'),'output':Decimal('1.20'),'cache_read':Decimal('0.006')}
REQUIRED=('input_tokens','output_tokens','cache_read_tokens','cache_write_tokens')
MILLION=Decimal(1000000)

def price_usage(meta:dict[str,Any],start_time:str)->dict[str,Any]:
    # Never estimate a subscription invoice; estimate only provider quota-equivalent
    # using published per-million token consumption tariff.
    result={'go_quota_pricing_status':'unavailable',
            'go_quota_price_source':PRICE_SOURCE,
            'go_quota_estimate_kind':'usage_equivalent_not_billed'}
    entries=meta.get('usage_token_counts')
    if not isinstance(entries,list) or not entries:return result
    try:
        t=datetime.fromisoformat(start_time.replace('Z','+00:00'))
        if t.tzinfo is None: return result
        t=t.astimezone(timezone.utc)
    except (ValueError,TypeError,AttributeError):return result
    peak=t.weekday()<5 and (1<=t.hour<4 or 6<=t.hour<10)
    rates=RATES_PEAK if peak else RATES_OFFPEAK
    cost=Decimal(0)
    for e in entries:
        if not isinstance(e,dict) or e.get('model') not in MODEL_ALIASES:
            return result
        if any(type(e.get(k)) is not int or not 0 <= e[k] < 10**10 for k in REQUIRED):
            return result
        if e['cache_write_tokens']!=0:
            # Provider lists no cache-write unit price, so complete estimate is impossible.
            return result
        cost+=(
          Decimal(e['input_tokens'])*rates['input']+
          Decimal(e['output_tokens'])*rates['output']+
          Decimal(e['cache_read_tokens'])*rates['cache_read']
        )/MILLION
    result.update(go_quota_pricing_status='estimated',
                  go_quota_estimate_usd=float(cost.quantize(Decimal('0.00000001'),rounding=ROUND_HALF_UP)),
                  go_quota_period='peak' if peak else 'offpeak',
                  go_quota_time_granularity='run_start_utc',
                  go_quota_billed_cost_known=False)
    return result

def objective_scores(meta:dict[str,Any])->dict[str,float]:
    # Completion is NOT correctness, CI PASS, production readiness, or approval.
    status=meta.get('run_status')
    if status not in {'completed','failed','cancelled'}:return {}
    scores={'multica_run_completed':float(status=='completed')}
    if meta.get('go_quota_pricing_status')=='estimated' and type(meta.get('go_quota_estimate_usd')) in (int,float):
        scores['go_quota_usage_equivalent_usd']=float(meta['go_quota_estimate_usd'])
    entries=meta.get('usage_token_counts')
    complete=isinstance(entries,list) and bool(entries) and all(
        isinstance(e,dict) and all(type(e.get(k)) is int and 0<=e[k]<10**10 for k in REQUIRED)
        for e in entries)
    scores['multica_usage_measured']=float(complete)
    if complete:
        for key in REQUIRED:
            scores['multica_'+key]=float(sum(e[key] for e in entries))
    for key in ('queue_wait_seconds','dispatch_to_start_seconds','run_elapsed_seconds','attempt'):
        value=meta.get(key)
        if type(value) in (int,float) and 0<=value<10**9:
            scores['multica_'+key]=float(value)
    return scores

if __name__=='__main__':
    sample={'run_status':'completed','usage_token_counts':[{'model':'opencode-go:deepseek-v4.1-flash','input_tokens':1000000,'output_tokens':1000000,'cache_read_tokens':1000000,'cache_write_tokens':0}]}
    assert price_usage(sample,'2026-11-19T05:00:00Z')['go_quota_estimate_usd']==0.753
    assert price_usage(sample,'2026-11-19T07:00:00Z')['go_quota_estimate_usd']==1.506
    assert price_usage(sample,'2026-11-22T07:00:00Z')['go_quota_estimate_usd']==0.753
    assert price_usage(sample,'2026-11-19T07:00:00Z')['go_quota_period']=='peak'
    assert price_usage(sample,'2026-11-19T05:00:00Z')['go_quota_period']=='offpeak'
    sample['usage_token_counts'][0]['cache_write_tokens']=100
    assert price_usage(sample,'2026-11-19T07:00:00Z')['go_quota_pricing_status']=='unavailable'
    sample['usage_token_counts'][0]['cache_write_tokens']=0
    sample['usage_token_counts'][0]['model']='unknown'
    assert price_usage(sample,'2026-11-19T07:00:00Z')['go_quota_pricing_status']=='unavailable'
    assert objective_scores({'run_status':'failed'})=={'multica_run_completed':0.0,'multica_usage_measured':0.0}
    assert objective_scores({'run_status':'completed'})=={'multica_run_completed':1.0,'multica_usage_measured':0.0}
    assert 'release_approved' not in objective_scores({'run_status':'completed'})
    sample['queue_wait_seconds']=7
    scores=objective_scores(sample)
    assert scores['multica_cache_read_tokens']==1000000
    assert scores['multica_queue_wait_seconds']==7
    assert scores['multica_usage_measured']==1
    assert objective_scores({'run_status':'completed','usage_token_counts':[{'input_tokens':1}]})['multica_usage_measured']==0
    print('PRICE_PEAK_OFFPEAK_UNKNOWN_AND_OBJECTIVE_SCORE_TESTS PASS')
