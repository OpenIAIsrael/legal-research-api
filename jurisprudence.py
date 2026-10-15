"""Route court filters to their own documented official connector."""
import asyncio
import re
import cnj_source
import court_index
import stj_index
from official_http import fetch,SourceError,now
from search_core import normalize

def case_identifier(q):
    match=re.search(r'\b(aresp|resp|eresp|hc|rhc|rms|ms|cc|pet)\s+(?:n[º°o.]?\s*)?([\d.]+)(?:/[a-z]{2})?\s*$',normalize(q))
    if not match:return None
    number=re.sub(r'\D','',match[2])
    return (match[1],str(int(number))) if number else None

def matches_case(doc,ident):
    cls,number=ident;case=str(doc.get('case_number') or '')
    numeric=re.sub(r'\D','',case)
    return doc.get('tribunal')=='stj' and numeric and str(int(numeric))==number and bool(re.search(r'\b'+cls+r'\b',normalize(str(doc.get('class') or '')+' '+case)))

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
    ident=case_identifier(q) if tribunal=='stj' else None
    effective_q=' '.join(ident) if ident else q
    operations=[stj_index.search(effective_q,area,'stj',precedent_only,limit),court_index.search('stj_full',effective_q,area,precedent_only,limit)]
    if tribunal is None:operations.extend([cnj_source.search(q,area,precedent_only,limit),court_index.search('tcu',q,area,precedent_only,limit),stf_search()])
    parts=await asyncio.gather(*operations)
    if ident:
        for part in parts:
            part['results']=[doc for doc in part['results'] if matches_case(doc,ident)]
            part['warnings'].append('Consulta identificadora: classe e número do processo comparados exatamente; menções temáticas a outros processos não são correspondência.')
    return combine(parts,limit)
