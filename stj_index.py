"""Bounded, refreshable SQLite index of actual official STJ judgment records.

Default coverage: two most recent JSON resources per Espelhos dataset, not the
entire historical court corpus. Source resources and dates are exposed to clients.
"""
import asyncio
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlencode
from official_http import fetch, SourceError, now
from search_core import normalize,tokens

CKAN='https://dadosabertos.web.stj.jus.br/api/3/action/package_search'
DB=Path(os.getenv('LEGAL_INDEX_PATH','/tmp/legal-research-index.sqlite3'))
LOCK=asyncio.Lock()
LAST_REFRESH=0.0
STATE={'status':'not_loaded','resources':[],'warnings':[],'complete':False}

def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,timeout=10)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS docs (id TEXT PRIMARY KEY, resource TEXT, payload TEXT)')
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, text, tokenize='unicode61 remove_diacritics 2')")
    c.execute('CREATE TABLE IF NOT EXISTS resources (url TEXT PRIMARY KEY, modified TEXT, fetched TEXT, count INTEGER)')
    c.commit();return c

def record_to_doc(record,resource,fetched):
    rid=record.get('id');case=record.get('numeroProcesso');ementa=record.get('ementa')
    if not rid or not case or not ementa:return None
    topic=record.get('tema');thesis=record.get('teseJuridica')
    # Both must be provided on the judgment record. Mere citations do not qualify.
    precedent=bool(topic and thesis)
    pub=record.get('dataPublicacao')
    decision=record.get('dataDecisao');judgment_date=None
    if decision and re.fullmatch(r'\d{8}',str(decision)):
        v=str(decision);judgment_date=f'{v[:4]}-{v[4:6]}-{v[6:8]}'
    reg=record.get('numeroRegistro')
    return {'title':f"{record.get('siglaClasse','')} {case} — STJ",'tribunal':'stj','class':record.get('siglaClasse'),
        'case_number':str(case),'registration_number':reg,'record_id':str(rid),'judging_body':record.get('nomeOrgaoJulgador'),
        'rapporteur':record.get('ministroRelator'),'judgment_date':judgment_date,'publication':pub,
        'ementa':ementa,'decision':record.get('decisao'),'notes':record.get('notas'),'summary':ementa[:1800],
        'precedent':precedent,'precedent_evidence':{'tema':topic,'tese_juridica':thesis} if precedent else None,
        'area':None,'official_source':'stj','source':'stj','source_type':'jurisprudencia',
        'url':resource['url'],'source_record_locator':{'resource_url':resource['url'],'record_id':str(rid)},
        'process_url':'https://processo.stj.jus.br/processo/pesquisa/?'+urlencode({'num_registro':reg}) if reg else None,
        'individual_document_url':None,'full_text_retrieved':False,'retrieval_status':'judgment_record_retrieved',
        'retrieved_at':fetched,'source_last_modified':resource.get('last_modified'),
        'resource_name':resource.get('name'),'dataset':resource.get('dataset')}

def store_records(records,resource,fetched):
    count=0
    with connect() as c:
        # Refreshing a resource atomically replaces its records, preserving other sources.
        ids=[r[0] for r in c.execute('SELECT id FROM docs WHERE resource=?',(resource['url'],))]
        for rid in ids:c.execute('DELETE FROM search WHERE id=?',(rid,))
        c.execute('DELETE FROM docs WHERE resource=?',(resource['url'],))
        for record in records:
            doc=record_to_doc(record,resource,fetched)
            if not doc:continue
            rid=doc['record_id']
            existing=c.execute('SELECT payload FROM docs WHERE id=?',(rid,)).fetchone()
            if existing and json.loads(existing[0]).get('resource_name','')>resource.get('name',''):
                continue  # A newer official extraction wins, regardless of download order.
            c.execute('DELETE FROM search WHERE id=?',(rid,))
            c.execute('INSERT OR REPLACE INTO docs VALUES(?,?,?)',(rid,resource['url'],json.dumps(doc,ensure_ascii=False)))
            searchable=' '.join(str(record.get(k) or '') for k in ('siglaClasse','numeroProcesso','ementa','notas','teseJuridica','termosAuxiliares','decisao'))
            c.execute('INSERT INTO search(id,text) VALUES(?,?)',(rid,searchable));count+=1
        c.execute('INSERT OR REPLACE INTO resources VALUES(?,?,?,?)',(resource['url'],resource.get('last_modified'),fetched,count))
    return count

async def refresh(force=False):
    global LAST_REFRESH,STATE
    if not force and time.monotonic()-LAST_REFRESH<3600 and LAST_REFRESH:return STATE
    async with LOCK:
        if not force and time.monotonic()-LAST_REFRESH<3600 and LAST_REFRESH:return STATE
        STATE={**STATE,'status':'loading'}
        try:
            response=await fetch(CKAN,params={'q':'espelhos','rows':20},max_bytes=4_000_000,ttl=3600,request_timeout=35)
            payload=json.loads(response['body'])
            if payload.get('success') is not True:raise SourceError('CKAN não confirmou sucesso')
            packages=[p for p in payload['result']['results'] if p['name'].startswith('espelhos-de-acordaos-')]
            per_dataset=max(1,min(12,int(os.getenv('STJ_RESOURCES_PER_DATASET','2'))))
            selected=[]
            for p in packages:
                rr=[dict(r,dataset=p['name']) for r in p['resources'] if r.get('format','').upper()=='JSON' and r.get('url','').startswith('https://dadosabertos.web.stj.jus.br/')]
                # Resource filename is the extraction date per the official dataset documentation.
                rr.sort(key=lambda r:r.get('name',''))
                selected.extend(rr[-per_dataset:])
            if not selected:raise SourceError('Nenhum lote JSON de espelhos localizado')
            sem=asyncio.Semaphore(3)
            async def ingest(r):
                async with sem:
                    with connect() as c:old=c.execute('SELECT modified,fetched,count FROM resources WHERE url=?',(r['url'],)).fetchone()
                    if old and old[0]==r.get('last_modified'):
                        return dict(url=r['url'],name=r['name'],dataset=r['dataset'],count=old[2],retrieved_at=old[1],cached=True),None
                    try:
                        downloaded=await fetch(r['url'],max_bytes=16_000_000,ttl=0,request_timeout=45)
                        rows=json.loads(downloaded['body'])
                        if not isinstance(rows,list):raise SourceError('Lote STJ não é uma lista de acórdãos')
                        count=await asyncio.to_thread(store_records,rows,r,downloaded['retrieved_at'])
                        return dict(url=r['url'],name=r['name'],dataset=r['dataset'],count=count,retrieved_at=downloaded['retrieved_at'],cached=False),None
                    except (SourceError,ValueError,sqlite3.Error):return None,f"Falha ao atualizar {r['dataset']}/{r['name']}"
            outcomes=await asyncio.gather(*(ingest(r) for r in selected))
            resources=[r for r,e in outcomes if r];warnings=[e for r,e in outcomes if e]
            # Keep the rolling window bounded. Do not delete cache if the refresh failed entirely.
            if resources:
                keep={r['url'] for r in selected}
                with connect() as c:
                    for (url,) in c.execute('SELECT url FROM resources').fetchall():
                        if url not in keep:
                            for (rid,) in c.execute('SELECT id FROM docs WHERE resource=?',(url,)).fetchall():c.execute('DELETE FROM search WHERE id=?',(rid,))
                            c.execute('DELETE FROM docs WHERE resource=?',(url,));c.execute('DELETE FROM resources WHERE url=?',(url,))
            STATE={'status':'partial' if warnings else 'ready','resources':resources,'warnings':warnings,'complete':False,'updated_at':now(),
                'coverage_description':f'Até {per_dataset} lotes JSON mais recentes de cada conjunto de espelhos; não cobre todo o histórico do STJ.'}
        except (SourceError,ValueError,KeyError,sqlite3.Error) as exc:
            reason=str(exc) if isinstance(exc,SourceError) else 'Resposta ou índice em formato inesperado'
            STATE={**STATE,'status':'unavailable','warnings':[f'Não foi possível atualizar o índice oficial do STJ: {reason}. Eventual cache é explicitamente identificado.'],'complete':False}
        LAST_REFRESH=time.monotonic()
        return STATE

async def maintenance():
    while True:
        await refresh()
        await asyncio.sleep(3600)

async def search(q,area=None,tribunal=None,precedent_only=False,limit=5):
    if tribunal not in (None,'stj'):
        reasons={'stf':'Acesso automatizado ao portal retornou HTTP 403 na validação. Conector documental pendente.',
            'cnj':'Recuperação documental de jurisprudência CNJ não implementada.',
            'tcu':'Recuperação documental de jurisprudência TCU não implementada.'}
        return {'results':[],'warnings':[reasons.get(tribunal,'Tribunal não suportado')],'retrieval_status':'source_unavailable','coverage':{'tribunal':tribunal,'complete':False}}
    warnings=[]
    if tribunal is None:warnings.append('Pesquisa documental disponível somente no STJ; STF, CNJ e TCU não foram pesquisados.')
    if area:
        return {'results':[],'warnings':['Os lotes STJ não fornecem classificação por área compatível; filtro não pode ser satisfeito sem inferência.'],'retrieval_status':'unsupported_filter','coverage':{'complete':False}}
    if not LAST_REFRESH:
        try:await asyncio.wait_for(asyncio.shield(refresh()),timeout=24)
        except TimeoutError:warnings.append('Índice STJ em atualização; repita a consulta após a carga inicial.')
    warnings.extend(STATE.get('warnings',[]))
    terms=list(dict.fromkeys(t.rstrip('s') if len(t)>5 else t for t in tokens(q)))[:12]
    if not terms:return {'results':[],'warnings':['Consulta sem termos pesquisáveis.'],'retrieval_status':'no_results','coverage':STATE}
    match=' OR '.join('"'+t+'"*' for t in terms)
    with connect() as c:
        rows=c.execute('SELECT d.payload, s.text FROM search s JOIN docs d ON d.id=s.id WHERE search MATCH ? ORDER BY bm25(search) LIMIT 150',(match,)).fetchall()
    ranked=[]
    for payload,text in rows:
        doc=json.loads(payload);words=tokens(text)
        hits=[t for t in terms if any(w.startswith(t) for w in words)]
        if len(hits)<max(1,(len(terms)+1)//2):continue
        if precedent_only and not doc['precedent']:continue
        doc['matched_terms']=hits;doc['cache_status']=STATE['status'];ranked.append((len(hits),doc))
    ranked.sort(key=lambda v:(v[0],str(v[1].get('judgment_date') or '')),reverse=True)
    results=[d for _,d in ranked[:limit]]
    for doc in results:
        truncated=[]
        for field in ('ementa','decision','notes'):
            if isinstance(doc.get(field),str) and len(doc[field])>12000:
                doc[field]=doc[field][:12000];truncated.append(field)
        doc['truncated_fields']=truncated
    if not results:warnings.append('Nenhum acórdão correspondente na janela indexada; isso não prova inexistência de jurisprudência.')
    warnings.append('Resultados são espelhos oficiais com ementa e decisão; não constituem recuperação do inteiro teor. A URL aponta ao lote oficial, com record_id para localização inequívoca.')
    if precedent_only:warnings.append('Precedente selecionado apenas quando o próprio registro contém tema e tese jurídica; classificação não equivale a verificação de superação posterior.')
    return {'results':results,'warnings':warnings,'retrieval_status':'judgment_records_retrieved' if results else 'no_results_in_coverage','coverage':STATE}
