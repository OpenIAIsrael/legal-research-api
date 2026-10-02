"""Opt-in network checks. Does not require or print production credentials."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import legislation
import stj_index
from official_http import now

async def main():
    report={'tested_at':now(),'kind':'real_public_source_requests','cases':[]}
    state=await stj_index.refresh(force=True)
    report['stj_index']={'status':state['status'],'resource_count':len(state.get('resources',[])),
        'records_per_resource_total':sum(r.get('count',0) for r in state.get('resources',[])),
        'resources':state.get('resources',[]),'warnings':state.get('warnings',[]),'complete':False}
    for query in ['Lei 13.019/2014','13.019','13019','Lei 14.133/2021','Lei 15.210/2025','zqxvnormainexistente987654321']:
        result=await legislation.search(query,limit=2)
        report['cases'].append({'operation':'searchLegislation','query':query,'results':[
            {k:d.get(k) for k in ('title','number','status','url','retrieval_status','text_characters','content_sha256','retrieved_at')}
            for d in result['results']],'warnings':result['warnings']})
    for tribunal,precedent,query in [('stj',False,'imunidade tributária entidades beneficentes'),('stf',False,'imunidade tributária entidades beneficentes'),('stj',True,'tributário')]:
        result=await stj_index.search(query,tribunal=tribunal,precedent_only=precedent,limit=2)
        report['cases'].append({'operation':'searchJurisprudence','query':query,'tribunal':tribunal,'precedent_only':precedent,
            'results':[{k:d.get(k) for k in ('title','record_id','case_number','judgment_date','url','matched_terms','retrieved_at','precedent','precedent_evidence')} for d in result['results']],
            'warnings':result['warnings'],'retrieval_status':result['retrieval_status']})
    Path('LIVE_VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    for case in report['cases']:print(case['operation'],case['query'],case.get('tribunal',''),len(case['results']),flush=True)
    print('STJ index:',report['stj_index']['status'],report['stj_index']['resource_count'],'resources',flush=True)

if __name__=='__main__':asyncio.run(main())
