"""Opt-in public network validation; never uses production credentials."""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cnj_source,court_index,jurisprudence
from official_http import now

def summarized(result):
    return {**result,'results':[{k:d.get(k) for k in ('title','tribunal','class','case_number','record_id','judgment_date','publication_date','url','source_record_locator','retrieval_status','full_text_retrieved','text_characters','content_sha256','precedent','precedent_evidence')} for d in result['results']]}

async def main():
    report={'tested_at':now(),'environment':'local_public_source_network_checks','cases':[]}
    async def tcu():
        state=await court_index.refresh_tcu(force=True)
        print('TCU index',state['status'],state.get('records'),flush=True)
        return state
    async def stj():
        state=await court_index.refresh_stj_full(force=True)
        print('STJ full index',state['status'],state.get('records'),flush=True)
        return state
    async def cnj():
        result=await cnj_source.search('concurso',limit=2)
        print('CNJ',result['retrieval_status'],len(result['results']),result['warnings'],flush=True)
        report['cases'].append({'query':'concurso',**summarized(result)})
    await asyncio.gather(tcu(),stj(),cnj())
    for source,query in [('tcu','licitação'),('stj_full','recurso')]:
        result=await court_index.search(source,query,limit=2)
        report['cases'].append({'query':query,**summarized(result)})
        print(source,len(result['results']),result['warnings'],flush=True)
    report['cases'].append({'query':'imunidade',**await jurisprudence.stf_search()})
    Path('VALIDATION_4_2_REAL.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':asyncio.run(main())
