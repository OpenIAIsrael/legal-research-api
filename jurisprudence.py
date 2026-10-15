"""Route court filters to their own documented official connector."""
import asyncio
import cnj_source
import court_index
import stj_index
from official_http import fetch,SourceError,now

async def stf_search():
    # Probe the official public publication channel. Never solve a challenge or fabricate results.
    reason='Canal oficial do STF não forneceu documentos pesquisáveis; integração bloqueada até acesso automatizado permitido.'
    try:
        response=await fetch('https://portal.stf.jus.br/repercussaogeral/teses.asp',ttl=3600,request_timeout=12)
        reason='Canal STF acessível, mas formato documental ainda não homologado; nenhum resultado apresentado.'
    except SourceError as exc:reason='STF: '+str(exc)+'. É necessário acesso automatizado permitido para homologar a recuperação documental.'
    return {'results':[],'warnings':[reason],'retrieval_status':'source_unavailable','coverage':{'tribunal':'stf','complete':False,'probe_checked_at':now()}}

def combine(parts,limit):
    results=[];seen=set()
    for index in range(limit):
        for part in parts:
            if index>=len(part['results']):continue
            doc=part['results'][index];key=(doc['tribunal'],doc.get('record_id'))
            if key in seen:continue
            seen.add(key);results.append(doc)
    warnings=list(dict.fromkeys(w for p in parts for w in p['warnings']))
    return {'results':results[:limit],'warnings':warnings,'retrieval_status':'partial' if results and warnings else ('documents_retrieved' if results else 'no_results_in_coverage'),
        'coverage':{'sources':[p['coverage'] for p in parts],'complete':False}}

async def search(q,area=None,tribunal=None,precedent_only=False,limit=5):
    if tribunal=='cnj':return await cnj_source.search(q,area,precedent_only,limit)
    if tribunal=='tcu':return await court_index.search('tcu',q,area,precedent_only,limit)
    if tribunal=='stf':return await stf_search()
    operations=[stj_index.search(q,area,'stj',precedent_only,limit),court_index.search('stj_full',q,area,precedent_only,limit)]
    if tribunal is None:operations.extend([cnj_source.search(q,area,precedent_only,limit),court_index.search('tcu',q,area,precedent_only,limit),stf_search()])
    return combine(await asyncio.gather(*operations),limit)
