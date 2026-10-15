"""Bounded disk-backed ingestion of official TCU CSV and STJ full-text ZIPs."""
import asyncio
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import zipfile
import zlib
from contextlib import closing
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin,urlparse
import httpx
from official_http import fetch,validate_url,SourceError,now,network_failure
from search_core import normalize,tokens

ROOT=Path(os.getenv('COURT_INDEX_DIR',tempfile.gettempdir()))
LOCK=threading.RLock()
STATE={s:{'status':'not_loaded','resources':[],'warnings':[],'complete':False} for s in ('tcu','stj_full')}
REFRESH_LOCKS={s:asyncio.Lock() for s in STATE}
LAST={s:0.0 for s in STATE}
TCU_BASE='https://sites.tcu.gov.br/dados-abertos/jurisprudencia/'
STJ_PACKAGE='https://dadosabertos.web.stj.jus.br/api/3/action/package_show'
STJ_FULL='integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica'

class PlainText(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip:self.skip-=1
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

def text(raw):
    raw=raw or ''
    if '<' not in raw:return ' '.join(raw.split())
    parser=PlainText();parser.feed(raw);parser.close()
    return ' '.join(' '.join(parser.parts).split())
def iso_date(value):
    for fmt in ('%d/%m/%Y','%Y-%m-%d'):
        try:return datetime.strptime(str(value),fmt).date().isoformat()
        except ValueError:pass
    return None

async def download(url,path,max_bytes=400_000_000,timeout=180):
    """Stream to a task-owned temporary file; never disable TLS or follow unvalidated redirects."""
    validate_url(url);current=url;size=0;digest=hashlib.sha256()
    try:
        async with asyncio.timeout(timeout),httpx.AsyncClient(timeout=httpx.Timeout(30,connect=5),follow_redirects=False,headers={'User-Agent':'LegalResearchAPI/4.2'}) as client:
            for _ in range(4):
                validate_url(current)
                async with client.stream('GET',current) as response:
                    if response.status_code in (301,302,303,307,308):
                        current=urljoin(current,response.headers.get('location',''));continue
                    if response.status_code!=200:raise SourceError(f'Fonte retornou HTTP {response.status_code}')
                    if int(response.headers.get('content-length',0))>max_bytes:raise SourceError('Lote excede limite de tamanho')
                    with path.open('wb') as output:
                        async for chunk in response.aiter_bytes():
                            size+=len(chunk)
                            if size>max_bytes:raise SourceError('Lote excede limite de tamanho')
                            output.write(chunk);digest.update(chunk)
                    return {'url':current,'retrieved_at':now(),'source_last_modified':response.headers.get('last-modified'),'content_sha256':digest.hexdigest(),'bytes':size}
            raise SourceError('Excesso de redirecionamentos')
    except (httpx.HTTPError,TimeoutError,OSError,ValueError) as exc:
        raise SourceError('Falha na coleta oficial ('+network_failure(exc)+')') from None

def tcu_document(row,resource,kind):
    rid=row.get('KEY','');case=row.get('PROC')
    if not rid:raise SourceError('Lote TCU sem KEY')
    if kind=='acordaos':
        if normalize(row.get('SITUACAO','')) in ('sigiloso','invalidado'):return None
        body='\n'.join(text(row.get(k,'')) for k in ('ACORDAO','DECISAO','RELATORIO','VOTO') if row.get(k))
        if len(body)<30:return None
        title=row.get('TITULO') or f"Acórdão {row.get('NUMACORDAO')}/{row.get('ANOACORDAO')} — TCU"
        summary=text(row.get('SUMARIO',''));full=True;cls='acordao';precedent=False
    else:
        summary=text(row.get('ENUNCIADO',''));body=summary+'\n'+text(row.get('EXCERTO',''))
        full=False;cls='sumula' if kind=='sumulas' else 'resposta_consulta';precedent=cls=='sumula' and normalize(row.get('VIGENTE','')) in ('sim','s','true','vigente')
        title=f"Súmula {row.get('NUMERO')} — TCU" if cls=='sumula' else f"Acórdão {row.get('NUMACORDAO')}/{row.get('ANOACORDAO')} — Consulta TCU"
    return {'title':title,'tribunal':'tcu','class':cls,'case_number':case,'record_id':rid,
        'judging_body':row.get('COLEGIADO'),'rapporteur':row.get('RELATOR') or row.get('AUTORTESE'),
        'judgment_date':iso_date(row.get('DATASESSAO') or row.get('DATASESSAOFORMATADA')),
        'summary':summary[:1400],'ementa':summary[:20000],'decision':text(row.get('DECISAO',''))[:20000],
        'text_excerpt':body[:24000],'text_characters':len(body),'excerpt_truncated':len(body)>24000,
        'full_text_retrieved':full,'retrieval_status':'full_text_retrieved' if full else 'official_excerpt_retrieved',
        'precedent':precedent,'precedent_evidence':{'classification':'sumula','status':row.get('VIGENTE'),'source_record_id':rid} if precedent else None,
        'area':None,'source_area':row.get('AREA'),'official_source':'tcu','source':'tcu','source_type':'jurisprudencia',
        'url':resource['url'],'source_record_locator':{'resource_url':resource['url'],'record_id':rid},
        'retrieved_at':resource['retrieved_at'],'source_last_modified':resource.get('source_last_modified'),
        'content_sha256':resource['content_sha256'],'_search':body[:100000]+' '+title+' '+(case or '')}

def csv_documents(path,resource,kind):
    csv.field_size_limit(5_000_000)
    with path.open('r',encoding='utf-8-sig',newline='') as file:
        rows=csv.DictReader(file,delimiter='|')
        required={'KEY','ACORDAO','NUMACORDAO','ANOACORDAO'} if kind=='acordaos' else {'KEY','ENUNCIADO'}
        if not required.issubset(rows.fieldnames or []):raise SourceError('Colunas do CSV TCU inesperadas')
        for row in rows:
            doc=tcu_document(row,resource,kind)
            if doc:yield doc

def build_index(path,documents):
    count=0
    with closing(sqlite3.connect(path)) as c,c:
        c.execute('CREATE TABLE docs (id TEXT PRIMARY KEY,payload TEXT,precedent INTEGER)')
        c.execute('CREATE VIRTUAL TABLE search USING fts5(text,tokenize="unicode61 remove_diacritics 2")')
        for doc in documents:
            searchable=doc.pop('_search');payload=zlib.compress(json.dumps(doc,ensure_ascii=False).encode('utf-8'))
            c.execute('INSERT INTO docs(id,payload,precedent) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,precedent=excluded.precedent',(doc['record_id'],payload,int(doc.get('precedent',False))))
            rowid=c.execute('SELECT rowid FROM docs WHERE id=?',(doc['record_id'],)).fetchone()[0]
            c.execute('DELETE FROM search WHERE rowid=?',(rowid,));c.execute('INSERT INTO search(rowid,text) VALUES (?,?)',(rowid,normalize(searchable)))
            count+=1
            if count>60000:raise SourceError('Limite de registros da janela excedido')
            if count%100==0 and c.execute('PRAGMA page_count').fetchone()[0]*c.execute('PRAGMA page_size').fetchone()[0]>450_000_000:raise SourceError('Índice excede limite de disco')
        if count==0:raise SourceError('Nenhum registro documental válido no lote')
    return count

async def refresh_tcu(force=False):
    source='tcu'
    if not force and LAST[source] and time.monotonic()-LAST[source]<86400:return STATE[source]
    async with REFRESH_LOCKS[source]:
        STATE[source]={**STATE[source],'status':'loading'}
        ROOT.mkdir(parents=True,exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix='tcu-load-',dir=ROOT) as scratch:
                folder=Path(scratch);resources=[];specs=[]
                year=datetime.utcnow().year
                for kind,relative in [('acordaos',f'arquivos/acordao-completo/acordao-completo-{year}.csv'),('consultas','arquivos/resposta-consulta/resposta-consulta.csv'),('sumulas','arquivos/sumula/sumula.csv')]:
                    path=folder/(kind+'.csv');info=await download(TCU_BASE+relative,path,max_bytes=400_000_000 if kind=='acordaos' else 12_000_000)
                    resources.append(info);specs.append((path,info,kind))
                def documents():
                    for path,info,kind in specs:yield from csv_documents(path,info,kind)
                count=await asyncio.to_thread(build_index,folder/'index.sqlite3',documents())
                with LOCK:os.replace(folder/'index.sqlite3',ROOT/'tcu.sqlite3')
                STATE[source]={'status':'ready','resources':resources,'records':count,'warnings':[],'complete':False,'updated_at':now(),
                    'coverage_description':f'Acórdãos do ano {year}, respostas a consultas e súmulas; não cobre todos os anos.'}
        except (SourceError,ValueError,csv.Error,OSError,sqlite3.Error) as exc:
            STATE[source]={**STATE[source],'status':'unavailable','warnings':[str(exc) if isinstance(exc,SourceError) else 'Falha de formato ou armazenamento TCU.'],'complete':False}
        LAST[source]=time.monotonic()
        return STATE[source]

async def maintenance():
    while True:
        await asyncio.gather(refresh_tcu(),refresh_stj_full())
        await asyncio.sleep(86400)

def zip_documents(metadata,raw,resource):
    """Read known text members in memory, never extract ZIP paths to disk."""
    if not isinstance(metadata,list):raise SourceError('Metadados de íntegra STJ inesperados')
    lookup={str(row.get('SeqDocumento')):row for row in metadata if row.get('SeqDocumento') is not None}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members=archive.infolist()
        if len(members)>10000 or sum(m.file_size for m in members)>30_000_000:raise SourceError('ZIP STJ excede limite de extração')
        for member in members:
            if member.is_dir():continue
            if not re.fullmatch(r'\d+\.txt',member.filename) or member.file_size>2_000_000:raise SourceError('Membro ZIP STJ não permitido')
            rid=member.filename[:-4];row=lookup.get(rid)
            if not row:continue
            body=text(archive.read(member).decode('utf-8-sig'))
            if len(body)<100:continue
            process=row.get('processo','')
            if not process:continue
            yield {'title':(row.get('recurso') or '')+' '+process+' — íntegra STJ','tribunal':'stj',
                'class':row.get('tipoDocumento'),'case_number':process,'registration_number':row.get('numeroRegistro'),'record_id':rid,
                'rapporteur':row.get('NM_MINISTRO'),'judgment_date':None,'publication_date':iso_date(row.get('dataPublicacao')),
                'summary':body[:1400],'text_excerpt':body[:24000],'text_characters':len(body),'excerpt_truncated':len(body)>24000,
                'full_text_retrieved':True,'retrieval_status':'full_text_retrieved','precedent':False,'precedent_evidence':None,
                'official_source':'stj','source':'stj','source_type':'jurisprudencia','area':None,
                'url':resource['url'],'source_record_locator':{'resource_url':resource['url'],'archive_member':member.filename,'record_id':rid},
                'retrieved_at':resource['retrieved_at'],'source_last_modified':resource.get('source_last_modified'),
                'content_sha256':hashlib.sha256(archive.read(member)).hexdigest(),'resource_sha256':resource['sha256'],
                '_search':process+' '+(row.get('recurso') or '')+' '+body[:100000]}

async def refresh_stj_full(force=False):
    source='stj_full'
    if not force and LAST[source] and time.monotonic()-LAST[source]<86400:return STATE[source]
    async with REFRESH_LOCKS[source]:
        STATE[source]={**STATE[source],'status':'loading'};ROOT.mkdir(parents=True,exist_ok=True)
        try:
            catalog=await fetch(STJ_PACKAGE,params={'id':STJ_FULL},max_bytes=6_000_000,request_timeout=35)
            payload=json.loads(catalog['body'])
            if payload.get('success') is not True:raise SourceError('Catálogo STJ de íntegra não confirmou sucesso')
            resources=payload['result']['resources']
            pairs=[]
            for r in resources:
                m=re.fullmatch(r'metadados(\d{8})',r.get('name',''))
                if m and r.get('format','').upper()=='JSON':
                    z=next((z for z in resources if z.get('format','').upper()=='ZIP' and z.get('name')==m[1]+'.zip'),None)
                    if z:pairs.append((m[1],r,z))
            pairs=sorted(pairs,key=lambda p:p[0])[-3:]
            if not pairs:raise SourceError('Nenhum par de metadados e ZIP oficial localizado')
            collected=[];info=[];warnings=[]
            for day,meta,zip_resource in pairs:
                for r in (meta,zip_resource):
                    if urlparse(r['url']).hostname!='dadosabertos.web.stj.jus.br':raise SourceError('Recurso fora do portal STJ')
                m,z=await asyncio.gather(fetch(meta['url'],max_bytes=12_000_000,request_timeout=45),fetch(zip_resource['url'],max_bytes=16_000_000,ttl=0,request_timeout=45))
                records=json.loads(m['body']);docs=await asyncio.to_thread(lambda:list(zip_documents(records,z['body'],z)))
                collected.extend(docs);info.append({'date':day,'metadata_url':meta['url'],'url':z['url'],'retrieved_at':z['retrieved_at'],'metadata_records':len(records),'text_records':len(docs),'sha256':z['sha256']})
                if sum(len(d['_search']) for d in collected)>40_000_000:raise SourceError('Janela de íntegra STJ excede limite de memória')
                if len(docs)<len(records):warnings.append(f'Lote {day}: {len(docs)} textos recuperados para {len(records)} metadados; pares ausentes não são apresentados como íntegra.')
            with tempfile.TemporaryDirectory(prefix='stj-full-',dir=ROOT) as scratch:
                path=Path(scratch)/'index.sqlite3';count=await asyncio.to_thread(build_index,path,iter(collected))
                with LOCK:os.replace(path,ROOT/'stj_full.sqlite3')
            STATE[source]={'status':'ready','resources':info,'records':count,'warnings':warnings,'complete':False,'updated_at':now(),
                'coverage_description':'Até três lotes diários mais recentes com JSON e ZIP correspondentes; não cobre todo o histórico nem textos ausentes do ZIP.'}
        except (SourceError,ValueError,KeyError,OSError,sqlite3.Error,zipfile.BadZipFile,UnicodeError) as exc:
            STATE[source]={**STATE[source],'status':'unavailable','warnings':[str(exc) if isinstance(exc,SourceError) else 'Formato ou armazenamento de íntegra STJ inválido.'],'complete':False}
        LAST[source]=time.monotonic()
        return STATE[source]

async def search(source,q,area=None,precedent_only=False,limit=5):
    state=STATE[source];results=[];warnings=list(state.get('warnings',[]))
    if area:
        warnings.append('Área jurídica não mapeada com evidência nesta fonte; filtro não satisfeito.')
    elif (ROOT/(source+'.sqlite3')).exists():
        query=' AND '.join('"'+t.replace('"','')+'"' for t in tokens(q)[:20])
        if query:
            with LOCK,closing(sqlite3.connect(ROOT/(source+'.sqlite3'))) as c:
                rows=c.execute('SELECT d.payload FROM search JOIN docs d ON d.rowid=search.rowid WHERE search MATCH ? AND (?=0 OR d.precedent=1) ORDER BY bm25(search) LIMIT ?',(query,int(precedent_only),limit)).fetchall()
            results=[dict(json.loads(zlib.decompress(row[0]) if isinstance(row[0],bytes) else row[0]),cache_status=state['status']) for row in rows]
    if state['status']!='ready':warnings.append('Índice em carga ou indisponível; eventual cache está explicitamente identificado.')
    if not results:warnings.append('Nenhum resultado na janela disponível; isso não prova inexistência de jurisprudência.')
    return {'results':results,'warnings':warnings,'retrieval_status':'documents_retrieved' if results else ('no_results_in_coverage' if state['status']=='ready' else 'source_unavailable'),
        'coverage':dict(state,tribunal='stj' if source=='stj_full' else 'tcu')}
