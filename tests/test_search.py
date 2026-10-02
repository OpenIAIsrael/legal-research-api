import asyncio
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from search_core import identity,score,Identity,same_identity
import main,legislation,stj_index
from official_http import SourceError,validate_url

@pytest.mark.parametrize('q',['13.019','13019','Lei 13.019/2014','Lei nº 13.019, de 2014','art. 2º da Lei 13.019/2014'])
def test_exact_number(q):
    item={'number':'Lei 13.019/2014','year':2014,'act_type':'lei_ordinaria','jurisdiction':'federal'}
    assert score(q,item)==100
    assert score(q,{'number':'Lei 14.133/2021','year':2021,'act_type':'lei_ordinaria'})==0
    assert score(q,{'number':'EC 132/2023','year':2023,'act_type':'emenda_constitucional'})==0

@pytest.mark.parametrize('q',['Lei 13.019/2015','Decreto 13.019/2014','Lei estadual 13.019/2014','Lei municipal 13.019/2014'])
def test_different_identity(q):
    assert score(q,{'number':'Lei 13.019/2014','year':2014,'act_type':'lei_ordinaria'})==0

def test_accents_aliases_and_no_substrings():
    assert score('licitações',{'title':'Lei de Licitações'})>0
    assert score('civil',{'title':'civilização'})==0
    assert score('inexistente xyz',{'title':'Lei de Licitações'})==0
    assert legislation.normalize_alias('MROSC')=='Lei 13.019/2014'

@pytest.mark.parametrize('url',['http://www.camara.leg.br/','https://127.0.0.1/','https://www.camara.leg.br.attacker.test/','https://u:p@www.camara.leg.br/','https://www.camara.leg.br:8443/'])
def test_unsafe_url_rejected(url):
    with pytest.raises(SourceError):validate_url(url)

META='https://www2.camara.leg.br/legin/fed/lei/2014/lei-13019-31-julho-2014-779123-norma-pl.html'
BODY=META.replace('-norma-pl','-normaatualizada-pl')

def fake_response(body,url):return {'body':body.encode(),'url':url,'retrieved_at':'2026-10-02T14:00:00Z','source_last_modified':None,'sha256':'abc','cache_hit':False}

def install_camara(monkeypatch,status='Não consta revogação expressa'):
    async def fetch(url,params=None,**kwargs):
        if url==legislation.LEXML:raise SourceError('Verificação de segurança')
        if url==legislation.CAMARA:return fake_response(f'<a href="{META}">Lei 13.019</a>',url)
        if url==META:return fake_response(f'<h1>LEI Nº 13.019, DE 31 DE JULHO DE 2014</h1><p>Situação: {status}</p><a href="{BODY}">Texto Atualizado (HTML)</a>',url)
        if url==BODY:return fake_response('<h1>LEI Nº 13.019, DE 31 DE JULHO DE 2014</h1><p>Art. 1º '+('parcerias com organizações da sociedade civil. '*20)+'</p>',url)
        raise SourceError('Desconhecida')
    monkeypatch.setattr(legislation,'fetch',fetch)

@pytest.mark.parametrize('q',['Lei 13.019/2014','13.019','13019'])
def test_live_document_pipeline_fixture(monkeypatch,q):
    install_camara(monkeypatch)
    result=asyncio.run(legislation.search(q))
    assert len(result['results'])==1
    d=result['results'][0]
    assert d['text_characters']>200 and d['url']==BODY
    assert d['vigency_verified'] is False and d['vigente'] is None
    assert d['retrieved_at']=='2026-10-02T14:00:00Z'
    assert any('LexML' in w for w in result['warnings'])

def test_wrong_year_no_silent_replacement(monkeypatch):
    install_camara(monkeypatch)
    assert not asyncio.run(legislation.search('Lei 13.019/2015'))['results']

def test_unknown_status_separated(monkeypatch):
    install_camara(monkeypatch,'Não informada')
    r=asyncio.run(legislation.search('13019'))
    assert not r['results'] and len(r['unverified_results'])==1
    assert asyncio.run(legislation.search('13019',only_current=False))['results']

def test_revoked_and_conflicting_flags(monkeypatch):
    install_camara(monkeypatch,'Revogada')
    assert not asyncio.run(legislation.search('13019'))['results']
    assert not asyncio.run(legislation.search('13019',only_current=False))['results']
    assert asyncio.run(legislation.search('13019',only_current=False,include_revoked=True))['results']
    assert asyncio.run(legislation.search('13019',include_revoked=True))['retrieval_status']=='invalid_filters'

def test_no_matches_and_failure_are_honest():
    r=asyncio.run(legislation.search('xyz_inexistente_987654321'))
    assert not r['results'] and any('indisponível' in w for w in r['warnings'])

RECORD={'id':'123','numeroProcesso':'9876','numeroRegistro':'202000000001','siglaClasse':'REsp','ementa':'TRIBUTÁRIO. Imunidade tributária de entidades beneficentes.','decisao':'Recurso provido.','dataDecisao':'20200115','nomeOrgaoJulgador':'PRIMEIRA SEÇÃO','ministroRelator':'Relator teste','tema':None,'teseJuridica':None}
RESOURCE={'url':'https://dadosabertos.web.stj.jus.br/dataset/test/download/test.json','name':'test.json','dataset':'test','last_modified':'2026-01-01'}

def test_stj_actual_record_and_precendent_filter():
    stj_index.store_records([RECORD],RESOURCE,'2026-10-01')
    r=asyncio.run(stj_index.search('imunidade tributária entidades beneficentes',tribunal='stj'))
    assert r['results'][0]['case_number']=='9876'
    assert r['results'][0]['ementa']==RECORD['ementa']
    assert r['results'][0]['full_text_retrieved'] is False
    assert not asyncio.run(stj_index.search('imunidade',tribunal='stj',precedent_only=True))['results']
    stj_index.store_records([{**RECORD,'tema':'123','teseJuridica':'Tese expressa do próprio registro'}],RESOURCE,'2026-10-01')
    assert asyncio.run(stj_index.search('imunidade',tribunal='stj',precedent_only=True))['results'][0]['precedent_evidence']['tema']=='123'

def test_stj_dedupe_limit_and_filter():
    stj_index.store_records([RECORD,{**RECORD,'id':'456'}],RESOURCE,'2026-10-01')
    stj_index.store_records([RECORD,{**RECORD,'id':'456'}],RESOURCE,'2026-10-01')
    assert len(asyncio.run(stj_index.search('imunidade',tribunal='stj',limit=1))['results'])==1
    assert not asyncio.run(stj_index.search('imunidade',tribunal='stf'))['results']
    assert not asyncio.run(stj_index.search('imunidade',tribunal='stj',area='tributario'))['results']
    assert not asyncio.run(stj_index.search('inexistenteabsoluto',tribunal='stj'))['results']

def test_rest_filters_do_not_leak_sources(monkeypatch):
    install_camara(monkeypatch)
    stj_index.store_records([RECORD],RESOURCE,'2026-10-01')
    with TestClient(main.app) as c:
        headers={'Authorization':'Bearer '+main.API_KEY}
        r=c.get('/v1/search',params={'q':'13019','source_type':'legislacao'},headers=headers).json()
        assert r['results'] and all(d['source_type']=='legislacao' for d in r['results'])
        r=c.get('/v1/search',params={'q':'imunidade','source_type':'jurisprudencia','official_source':'stf'},headers=headers).json()
        assert not r['results']
        assert c.get('/v1/search',params={'q':'teste','source_type':'invalid'},headers=headers).status_code==422
        r=c.get('/v1/legislation',params={'q':'13019','act_type':'decreto'},headers=headers).json()
        assert not r['results']

def test_lexml_xml_and_challenge_detection(monkeypatch):
    async def xml(*a,**kw):return fake_response('<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"><records><record><recordData><dc xmlns="http://purl.org/dc/elements/1.1/"><title>Lei</title><identifier>urn:lex:br:federal:lei:2014-07-31;13019</identifier></dc></recordData></record></records></searchRetrieveResponse>',legislation.LEXML)
    monkeypatch.setattr(legislation,'fetch',xml)
    assert asyncio.run(legislation.lexml_discover('13019',2))[0]['urn'].endswith(';13019')
    async def html(*a,**kw):return fake_response('<html>Verificação de segurança</html>',legislation.LEXML)
    monkeypatch.setattr(legislation,'fetch',html)
    with pytest.raises(SourceError):asyncio.run(legislation.lexml_discover('13019',2))

def test_official_pdf_fallback(monkeypatch):
    from types import SimpleNamespace
    pdf=BODY.replace('.html','.pdf')
    async def fetch(url,params=None,**kwargs):
        if url==META:
            return fake_response(f'<h1>Legislação</h1><h1>LEI Nº 13.019, DE 31 DE JULHO DE 2014</h1><p>Situação: Não consta revogação expressa</p><a href="{BODY}">Texto Atualizado (HTML)</a><a href="{pdf}">Formato pdf</a>',url)
        if url==BODY:raise SourceError('Fonte retornou página de erro em resposta HTTP 200')
        if url==pdf:return fake_response('%PDF-synthetic-fixture',url)
        raise SourceError('Não configurado')
    monkeypatch.setattr(legislation,'fetch',fetch)
    monkeypatch.setattr(legislation,'PdfReader',lambda data:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:'LEI Nº 13.019, DE 31 DE JULHO DE 2014. '+('Texto oficial. '*30))]))
    result=asyncio.run(legislation.camara_document(META,'13019'))
    assert result['url']==pdf and result['text_characters']>200

def test_newer_stj_extraction_wins():
    newer={**RESOURCE,'name':'20260930.json','url':RESOURCE['url'].replace('test.json','new.json')}
    older={**RESOURCE,'name':'20260831.json'}
    stj_index.store_records([{**RECORD,'ementa':'IMUNIDADE. Versão mais recente.'}],newer,'2026-10-01')
    stj_index.store_records([{**RECORD,'ementa':'IMUNIDADE. Versão antiga.'}],older,'2026-10-01')
    result=asyncio.run(stj_index.search('imunidade',tribunal='stj'))
    assert result['results'][0]['resource_name']=='20260930.json'

@pytest.mark.parametrize('status,headers,body,limit',[
    (301,{'location':'http://127.0.0.1/private'},b'',1000),
    (200,{},b'<html>504 Gateway Time-out</html>',1000),
    (200,{},b'x'*101,100),
])
def test_official_http_rejects_redirect_gateway_and_oversize(monkeypatch,status,headers,body,limit):
    import official_http
    class Response:
        status_code=status
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def aiter_bytes(self):yield body
    Response.headers=headers
    class Client:
        def __init__(self,*args,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def stream(self,*args,**kwargs):return Response()
    monkeypatch.setattr(official_http.httpx,'AsyncClient',Client)
    monkeypatch.setattr(official_http,'CACHE',{})
    with pytest.raises(SourceError):
        asyncio.run(official_http.fetch('https://www.camara.leg.br/test',max_bytes=limit))
