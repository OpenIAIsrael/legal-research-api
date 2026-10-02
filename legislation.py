"""Live official discovery and document retrieval with evidence-bearing metadata."""
import asyncio
import re
import threading
import pypdfium2 as pdfium
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from defusedxml import ElementTree
from catalog import LEGISLATION_CATALOG
from official_http import fetch, SourceError, now, validate_url
from search_core import identity, Identity, same_identity, normalize, score, tokens

PDF_LOCK=threading.Lock()

def extract_pdf(raw):
    # PDFium is not thread-safe: serialize native calls across all requests.
    with PDF_LOCK, pdfium.PdfDocument(raw) as document:
        if len(document)>300:raise SourceError('PDF excede limite de páginas')
        parts=[]
        for page in document:
            textpage=page.get_textpage()
            try:parts.append(textpage.get_text_bounded())
            finally:textpage.close();page.close()
        return ' '.join(parts)

CAMARA='https://www.camara.leg.br/legislacao/busca'
LEXML='https://www.lexml.gov.br/busca/SRU'
KIND_PATH={'lei':'lei_ordinaria','leicomplementar':'lei_complementar','decreto':'decreto','decretolei':'decreto_lei','emendaconstitucional':'emenda_constitucional','medidaprovisoria':'medida_provisoria'}
TYPE_NAMES={'lei_ordinaria':'Lei Ordinária','lei_complementar':'Lei Complementar','decreto':'Decreto','decreto_lei':'Decreto-Lei','emenda_constitucional':'Emenda Constitucional','medida_provisoria':'Medida Provisória'}

def clean_html(raw):
    soup=BeautifulSoup(raw,'html.parser')
    for tag in soup.select('script,style,nav,header,footer'):tag.decompose()
    return soup, soup.get_text(' ',strip=True)

def url_identity(url):
    m=re.search(r'/legin/fed/([^/]+)/(\d{4})/[^/]+?-(\d+)-',url)
    if not m:return Identity()
    return Identity(str(int(m[3])),int(m[2]),KIND_PATH.get(m[1]),'federal')

def normalize_alias(q):
    for item in LEGISLATION_CATALOG:
        if normalize(q) in [normalize(a) for a in item.get('aliases',[])]:return item['number']
    if normalize(q)=='mrosc':return 'Lei 13.019/2014'
    return q

async def camara_discover(q,limit):
    ident=identity(q)
    if ident.jurisdiction=='non_federal':return [],'Câmara: cobertura deste conector restrita à legislação federal.'
    params={'abrangencia':'Legislação Federal'}
    if ident.number:params['numero']=ident.number
    else:params['geral']=q
    if ident.year:params['ano']=str(ident.year)
    if ident.kind in TYPE_NAMES:params['tipo']=TYPE_NAMES[ident.kind]
    r=await fetch(CAMARA,params=params)
    soup,_=clean_html(r['body']); found=[]
    for a in soup.select('a[href]'):
        url=urljoin(r['url'],a['href'])
        if '/legin/fed/' not in url or not url.endswith('-norma-pl.html'):continue
        if not same_identity(ident,url_identity(url)):continue
        if url not in found:found.append(url)
    return found[:limit],None

async def lexml_discover(q,limit):
    ident=identity(q)
    query=('urn = "'+ ' '.join(str(v) for v in (ident.kind.replace('_','.') if ident.kind else None,ident.year,ident.number) if v)+'"') if ident.number else 'cql.anywhere all "'+q.replace('"',' ')+'"'
    r=await fetch(LEXML,params={'operation':'searchRetrieve','version':'1.1','query':query,'maximumRecords':min(limit,20)})
    try:root=ElementTree.fromstring(r['body'])
    except Exception:raise SourceError('LexML não retornou XML SRU válido') from None
    if root.tag.split('}')[-1]!='searchRetrieveResponse':raise SourceError('LexML retornou formato inesperado')
    records=[]
    for record in root.iter():
        if record.tag.split('}')[-1]=='diagnostic':raise SourceError('LexML retornou diagnóstico de consulta; pesquisa não concluída')
        if record.tag.split('}')[-1]!='recordData':continue
        vals={}
        for e in record.iter():
            if e.text:vals.setdefault(e.tag.split('}')[-1],[]).append(e.text.strip())
        ids=vals.get('identifier',[])
        urls=[v for v in ids if v.startswith('https://')]
        records.append({'title':' '.join(vals.get('title',[])),'urn':next((v for v in ids if v.startswith('urn:')),None),'urls':urls,'summary':' '.join(vals.get('description',[])),'retrieved_at':r['retrieved_at']})
    return records

def excerpt(text,q,max_chars=9000):
    # Preserve literal source text. Never synthesize a legal passage.
    s=normalize(text); wanted=tokens(q)
    pos=0
    m=re.search(r'\b(?:art\.?|artigo)\s*(\d+)',normalize(q))
    if m:
        match=re.search(r'\bart\.?\s*'+m[1]+r'\b',s)
        if match:pos=max(0,match.start()-80)
    elif not identity(q).number:
        positions=[s.find(t) for t in wanted if s.find(t)>=0]
        if positions:pos=max(0,min(positions)-250)
    return text[pos:pos+max_chars]

async def camara_document(url,q):
    metadata=await fetch(url);soup,text=clean_html(metadata['body']);ident=url_identity(url)
    heading=next((h for h in soup.find_all('h1') if identity(h.get_text(' ',strip=True)).number==ident.number),None)
    title=heading.get_text(' ',strip=True) if heading else ''
    head_id=identity(title)
    if not ident.number or head_id.number!=ident.number or head_id.kind!=ident.kind or str(ident.year) not in title:raise SourceError('Identidade da norma não confirmada na página oficial')
    ntext=normalize(text)
    status='desconhecida';status_text=None
    m=re.search(r'situacao:\s*(.{0,140})',ntext)
    if m:
        if m[1].startswith('nao consta revogacao expressa'):
            status='sem_revogacao_expressa_na_fonte';status_text='Não consta revogação expressa'
        elif m[1].startswith(('revogada','revogado')):
            status='revogada';status_text=m[1].split('texto')[0][:100]
    updated=[]; original=[]
    for a in soup.select('a[href]'):
        label=normalize(a.get_text(' ',strip=True)); target=urljoin(url,a['href'])
        if 'texto atualizado (html)' in label or ('formato pdf' in label and 'normaatualizada' in target):
            updated.append(target)
        elif 'publicacao original' in label and target.endswith('.html'):
            original.append(target)
    body_urls=list(dict.fromkeys(updated or original))[:2]
    version='texto_atualizado_na_fonte' if updated else 'publicacao_original'
    if not body_urls:raise SourceError('Página da norma sem texto recuperável')
    async def retrieve_body(target):
        try:
            body=await fetch(target,max_bytes=8_000_000)
            if body['body'].startswith(b'%PDF'):
                full=await asyncio.wait_for(asyncio.to_thread(extract_pdf,body['body']),timeout=12)
            else:
                _,full=clean_html(body['body'])
            header=normalize(full[:4000])
            number_pattern=r'(?<!\d)'+r'[.\s]*'.join(ident.number)+r'(?!\d)'
            if len(full)<200 or not re.search(number_pattern,header):
                raise SourceError('Texto recuperado não confirmou o número da norma')
            return body,full,None
        except SourceError as exc:
            return None,None,str(exc)
        except (ValueError,TimeoutError,pdfium.PdfiumError):
            return None,None,'Falha ou limite de tempo na extração do texto oficial'
    outcomes=await asyncio.gather(*(retrieve_body(u) for u in body_urls))
    success=next(((b,t) for b,t,e in outcomes if b),None)
    if not success:raise SourceError('; '.join(dict.fromkeys(e for b,t,e in outcomes if e)))
    body,full=success
    return {'title':title,'number':f"{title.split(' Nº')[0] if ' Nº' in title else 'Norma'} {ident.number}/{ident.year}",
        'act_type':ident.kind,'year':ident.year,'jurisdiction':'federal','area':None,
        'official_source':'camara','source':'camara','source_type':'legislacao','discovery_source':'camara',
        'url':body['url'],'metadata_url':url,'status':status,'status_evidence':status_text,
        'status_checked_at':metadata['retrieved_at'],'vigente':None,'vigency_verified':False,
        'document_version':version,'retrieval_status':'document_retrieved',
        'text_excerpt':excerpt(full,q),'text_characters':len(full),'excerpt_truncated':len(full)>9000,
        'summary':excerpt(full,q,1400),'retrieved_at':body['retrieved_at'],
        'source_last_modified':body['source_last_modified'],'content_sha256':body['sha256'],'cache_hit':body['cache_hit']}

async def planalto_document(item,q):
    r=await fetch(item['url']);_,text=clean_html(r['body']);ident=identity(item['number'])
    if ident.number and ident.number not in re.sub(r'(?<=\d)\.(?=\d)','',text[:2500]):raise SourceError('Identidade não confirmada no documento Planalto')
    return {**{k:v for k,v in item.items() if k not in ('aliases','themes','status')},'official_source':'planalto','source':'planalto','source_type':'legislacao',
        'discovery_source':'local_catalog','jurisdiction':'federal','status':'desconhecida','vigente':None,'vigency_verified':False,
        'retrieval_status':'document_retrieved','text_excerpt':excerpt(text,q),'text_characters':len(text),'excerpt_truncated':len(text)>9000,
        'retrieved_at':r['retrieved_at'],'source_last_modified':r['source_last_modified'],'content_sha256':r['sha256'],'cache_hit':r['cache_hit']}

async def search(q,area=None,official_source=None,act_type=None,only_current=True,include_revoked=False,limit=5):
    warnings=[];query=normalize_alias(q); candidates=[];unverified=[];lex_records=[]
    if only_current and include_revoked:
        return {'results':[],'warnings':['Filtros incompatíveis: only_current=true e include_revoked=true. Use only_current=false para incluir revogadas.'],'retrieval_status':'invalid_filters','unverified_results':[]}
    if official_source not in (None,'camara','planalto','lexml'):
        return {'results':[],'warnings':['Fonte solicitada não oferece legislação neste conector.'],'retrieval_status':'unsupported_source','unverified_results':[]}
    if official_source in (None,'camara'):
        async def cam():
            try:return await camara_discover(query,min(limit,5))
            except SourceError as e:return [],f'Câmara: {e}'
        async def lex():
            try:return await lexml_discover(query,min(limit,5)),None
            except SourceError as e:return [],f'LexML: {e}'
        (urls,err),(lex_records,lexerr)=await asyncio.gather(cam(),lex()) if official_source is None else (await cam(),([],None))
        if err:warnings.append(err)
        if lexerr:warnings.append(lexerr)
        # Only discovered, allowlisted Câmara metadata URLs are admitted here.
        for record in lex_records:
            for u in record['urls']:
                if urlparse(u).hostname=='www2.camara.leg.br' and u.endswith('-norma-pl.html') and same_identity(identity(query),url_identity(u)) and u not in urls:urls.append(u)
        async def retrieve(u):
            try:return await camara_document(u,q),None
            except SourceError as e:return None,f'Câmara: {e}'
        for result,err in await asyncio.gather(*(retrieve(u) for u in urls[:5])):
            if result:candidates.append(result)
            if err:warnings.append(err)
        if len(urls)>=5:warnings.append('Cobertura limitada aos primeiros cinco documentos candidatos desta consulta.')
    elif official_source=='lexml':
        try:lex_records=await lexml_discover(query,limit)
        except SourceError as e:warnings.append(f'LexML: {e}')
        for r in lex_records:
            candidates.append({'title':r['title'],'summary':r['summary'],'urn':r['urn'],'url':r['urls'][0] if r['urls'] else None,'official_source':'lexml','source':'lexml','source_type':'legislacao','status':'desconhecida','vigency_verified':False,'retrieval_status':'metadata_only','retrieved_at':r['retrieved_at'],'area':None,'act_type':None})
    elif official_source=='planalto':
        seeds=sorted((i for i in LEGISLATION_CATALOG if score(query,i)>0),key=lambda i:-score(query,i))[:min(limit,3)]
        warnings.append('Planalto: descoberta restrita ao catálogo de apoio; texto é consultado na fonte quando acessível.')
        for item in seeds:
            try:candidates.append(await planalto_document(item,q))
            except SourceError as e:warnings.append(f'Planalto: {e}')
    output=[]
    for item in candidates:
        # Only verified catalog classification can satisfy an area filter.
        seed=next((x for x in LEGISLATION_CATALOG if identity(x['number']).number==identity(item.get('number','')).number and x['year']==item.get('year')),None)
        if seed:item['area']=seed['area']
        if area and item.get('area')!=area:continue
        if act_type and item.get('act_type')!=act_type:continue
        if item['status']=='revogada' and not include_revoked:continue
        if only_current and item['status'] not in ('sem_revogacao_expressa_na_fonte','vigente'):
            unverified.append(item);continue
        output.append(item)
    if area:warnings.append('Área aplicada apenas a normas com classificação cadastrada; documentos sem classificação foram excluídos.')
    if only_current:warnings.append('only_current exige evidência documental de ausência de revogação expressa; não certifica vigência integral, eficácia ou validade de cada dispositivo.')
    if unverified:warnings.append('Documentos sem situação verificável foram separados em unverified_results e não satisfazem only_current.')
    if not output:warnings.append('Nenhum documento elegível foi recuperado; isso não prova inexistência de norma.')
    return {'results':output[:limit],'unverified_results':unverified[:limit],'warnings':list(dict.fromkeys(warnings)),
        'retrieval_status':'partial' if warnings and output else ('documents_retrieved' if output else 'no_verified_results'),
        'coverage':{'camara':'legislação federal; primeiros cinco candidatos','lexml_records':len(lex_records),'complete':False}}
