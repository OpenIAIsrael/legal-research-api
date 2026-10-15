"""Public Infojuris search and individual records; no login or access bypass."""
import asyncio
import re
from datetime import datetime
from urllib.parse import urljoin,urlparse,parse_qs,urlencode
import httpx
from bs4 import BeautifulSoup
from official_http import fetch,SourceError,validate_url
from search_core import normalize

SEARCH='https://www.cnj.jus.br/InfojurisI2/JurisprudenciaSearch.seam'

def soup_of(raw):
    # The page declares an incorrect Latin-1 encoding while serving UTF-8.
    return BeautifulSoup(raw.decode('utf-8',errors='replace'),'html.parser')

def public_record_url(url):
    p=validate_url(url)
    if p.hostname!='www.cnj.jus.br' or p.path.split(';')[0]!='/InfojurisI2/Jurisprudencia.seam':raise SourceError('Link Infojuris inesperado')
    record_id=parse_qs(p.query).get('jurisprudenciaIdJuris',[''])[0]
    if not record_id.isdigit():raise SourceError('Registro Infojuris sem identificador')
    return 'https://www.cnj.jus.br/InfojurisI2/Jurisprudencia.seam?'+urlencode({'jurisprudenciaIdJuris':record_id}),record_id

def parse_document(response,record_id):
    s=soup_of(response['body']);fields={}
    for prop in s.select('.prop'):
        label=prop.select_one('td.namenorms');value=prop.select_one('td.value')
        if label and value:fields[normalize(label.get_text(' ',strip=True))]=value.get_text(' ',strip=True)
    case=fields.get('numero do processo','')
    if not re.fullmatch(r'\d{7}-\d{2}\.\d{4}\.2\.00\.\d{4}',case):raise SourceError('Número de processo CNJ não confirmado')
    ementa_node=s.select_one('#dscEmenta textarea')
    ementa=ementa_node.get_text(' ',strip=True) if ementa_node else fields.get('ementa','')
    if len(ementa)<30:raise SourceError('Documento Infojuris sem ementa')
    date=None
    if fields.get('data de julgamento'):
        try:date=datetime.strptime(fields['data de julgamento'],'%d.%m.%Y').date().isoformat()
        except ValueError:pass
    return {'title':f"{fields.get('classe processual','CNJ')} {case}",'tribunal':'cnj','class':fields.get('classe processual'),
        'case_number':case,'record_id':record_id,'rapporteur':fields.get('relator'),'judgment_date':date,
        'judging_body':fields.get('sessao'),'ementa':ementa[:20000],'summary':ementa[:1400],
        'decision':fields.get('certidao de julgamento (*)'),'official_source':'cnj','source':'cnj','source_type':'jurisprudencia',
        'url':public_record_url(response['url'])[0],'retrieved_at':response['retrieved_at'],
        'source_last_modified':response['source_last_modified'],'content_sha256':response['sha256'],
        'retrieval_status':'judgment_record_retrieved','full_text_retrieved':False,'precedent':False,'precedent_evidence':None,
        'area':None,'cache_hit':False,'excerpt_truncated':len(ementa)>20000}

def search_form(response,q):
    s=soup_of(response['body']);form=s.find('form',id='jurisprudenciaSearchLivre')
    if not form:raise SourceError('Formulário público Infojuris não encontrado')
    action=urljoin(response['url'],form.get('action',''));p=validate_url(action)
    if p.hostname!='www.cnj.jus.br' or not p.path.startswith('/InfojurisI2/JurisprudenciaSearch.seam'):raise SourceError('Destino do formulário Infojuris inesperado')
    data={}
    for i in form.select('input[name]'):
        typ=i.get('type','text')
        if typ in ('hidden','text') or (typ in ('checkbox','radio') and i.has_attr('checked')):data[i['name']]=i.get('value','')
    for i in form.select('select[name]'):
        option=i.find('option',selected=True) or i.find('option');data[i['name']]=option.get('value','') if option else ''
    submit=next((i for i in form.select('input[type=submit]') if i.get('value')=='Buscar'),None)
    query=next((i for i in form.select('input[name]') if i['name'].endswith(':queryStringExibicao')),None)
    if submit is None or query is None:raise SourceError('Campos de pesquisa Infojuris inesperados')
    data[query['name']]=q;data[submit['name']]=submit.get('value','')
    return action,data

async def search(q,area=None,precedent_only=False,limit=5):
    result={'results':[],'warnings':[],'retrieval_status':'source_unavailable','coverage':{'tribunal':'cnj','complete':False,'method':'public_infojuris','max_candidates':min(limit,10)}}
    if area or precedent_only:
        result.update(retrieval_status='unsupported_filter',warnings=['Infojuris não confirma classificação de área ou precedente qualificado; filtro solicitado não pode ser satisfeito.'])
        return result
    try:
        async with asyncio.timeout(45),httpx.AsyncClient(timeout=httpx.Timeout(15,connect=5),follow_redirects=False,headers={'User-Agent':'LegalResearchAPI/4.2'}) as client:
            page=await fetch(SEARCH,client=client,ttl=0)
            action,data=search_form(page,q)
            found=await fetch(action,client=client,method='POST',data=data,ttl=0)
            s=soup_of(found['body']);text=normalize(s.get_text(' ',strip=True))
            if 'transao falhou' in text or 'transacao falhou' in text:raise SourceError('Sessão pública Infojuris rejeitou a transação de pesquisa')
            if 'resultados da busca por jurisprudencia' not in text:raise SourceError('Infojuris não confirmou execução da pesquisa')
            urls=[]
            for a in s.select('a[href]'):
                if '/Jurisprudencia.seam' not in a['href']:continue
                url,rid=public_record_url(urljoin(found['url'],a['href']))
                if (url,rid) not in urls:urls.append((url,rid))
            total=re.search(r'total:\s*(\d+)',text)
            result['coverage']['source_total']=int(total[1]) if total else None
            for url,rid in urls[:min(limit,10)]:
                try:result['results'].append(parse_document(await fetch(url,client=client,ttl=0),rid))
                except SourceError as e:result['warnings'].append(str(e))
            if not urls and not total:raise SourceError('Formato dos resultados Infojuris inesperado')
            result['retrieval_status']='judgment_records_retrieved' if result['results'] else 'no_results_in_coverage'
            result['warnings'].append('CNJ: primeiros dez candidatos no máximo, com ementa e certidão; inteiro teor e precedentes qualificados não confirmados.')
    except (SourceError,TimeoutError,httpx.HTTPError) as e:
        result['warnings'].append(str(e) if isinstance(e,SourceError) else 'Infojuris: falha de rede ou limite de tempo.')
        if result['results']:result['retrieval_status']='partial'
    return result
