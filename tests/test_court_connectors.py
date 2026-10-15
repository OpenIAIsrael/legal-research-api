import asyncio
import io
import json
import zipfile
import pytest
import cnj_source,court_index,jurisprudence
from official_http import SourceError,validate_url,redirect_target

RESOURCE={'url':'https://sites.tcu.gov.br/dados-abertos/test.csv','retrieved_at':'2026-10-15T13:00:00Z','content_sha256':'abc','sha256':'abc','source_last_modified':None}

def response(body,url='https://www.cnj.jus.br/InfojurisI2/Jurisprudencia.seam?jurisprudenciaIdJuris=5'):
    return {'body':body.encode(),'url':url,'retrieved_at':RESOURCE['retrieved_at'],'source_last_modified':None,'sha256':'abc'}

def cnj_html(case='0003643-82.2026.2.00.0000'):
    fields={'Número do Processo':case,'Classe Processual':'PCA','Relator':'Relator público','Data de Julgamento':'02.10.2026','Ementa':'Concurso público. Cadastro de reserva. Ementa oficial.','Certidão de Julgamento (*)':'Negado provimento.'}
    return ''.join(f'<div class="prop"><table><tr><td class="namenorms">{k}</td></tr><tr><td class="value">{v}</td></tr></table></div>' for k,v in fields.items())

def test_cnj_identity_and_evidence():
    doc=cnj_source.parse_document(response(cnj_html()),'5')
    assert doc['case_number']=='0003643-82.2026.2.00.0000'
    assert doc['judgment_date']=='2026-10-02'
    assert doc['full_text_retrieved'] is False
    assert doc['precedent'] is False
    with pytest.raises(SourceError):cnj_source.parse_document(response(cnj_html('123')),'5')

def test_cnj_public_search_routes_to_individual_document(monkeypatch):
    calls=[]
    form='<form id="jurisprudenciaSearchLivre" action="/InfojurisI2/JurisprudenciaSearch.seam"><input type="hidden" name="javax.faces.ViewState" value="public-state"><input name="f:queryStringExibicao"><input type="submit" name="f:search" value="Buscar"></form>'
    found='Resultados da Busca por Jurisprudência Total: 1 <a href="/InfojurisI2/Jurisprudencia.seam?jurisprudenciaIdJuris=5">Visualizar</a>'
    async def fake(url,**kwargs):
        calls.append((url,kwargs))
        if kwargs.get('method')=='POST':return response(found,cnj_source.SEARCH)
        return response(form,cnj_source.SEARCH) if url==cnj_source.SEARCH else response(cnj_html())
    monkeypatch.setattr(cnj_source,'fetch',fake)
    result=asyncio.run(cnj_source.search('concurso',limit=1))
    assert len(result['results'])==1
    assert calls[1][1]['data']['f:queryStringExibicao']=='concurso'
    assert result['coverage']['source_total']==1

@pytest.mark.parametrize('pdf_number,expected', [('9',1),('8',0)])
def test_cnj_alternative_is_identified_and_matches_pdf_identity(monkeypatch,pdf_number,expected):
    listing='<table><tr><td><a href="/files/real.pdf">Informativo de Jurisprudência</a></td><td>9</td><td>22/06/2026</td><td>Concurso público.</td></tr></table>'
    async def fake(url,**kwargs):
        if url==cnj_source.SEARCH:raise SourceError('Fonte retornou HTTP 403')
        if url==cnj_source.BULLETINS:return response(listing,cnj_source.BULLETINS)
        return {**response('',url),'body':b'%PDF-test','cache_hit':False}
    monkeypatch.setattr(cnj_source,'fetch',fake)
    monkeypatch.setattr(cnj_source,'extract_pdf',lambda raw:f'Informativo de Jurisprudência CNJ Número {pdf_number}/2026. Concurso público. '+('Resumo não oficial. '*12))
    result=asyncio.run(cnj_source.search('concurso',limit=1))
    assert len(result['results'])==expected
    assert '403' in result['warnings'][0]
    if expected:
        doc=result['results'][0]
        assert doc['case_number'] is None and doc['judgment_date'] is None
        assert doc['content_nature']=='resumos_nao_oficiais_publicados_pelo_cnj'
        assert doc['bulletin_full_text_retrieved'] and not doc['full_text_retrieved']

def test_cnj_failure_not_empty_success(monkeypatch):
    async def fake(url,**kwargs):return response('Página de login')
    monkeypatch.setattr(cnj_source,'fetch',fake)
    result=asyncio.run(cnj_source.search('concurso'))
    assert result['retrieval_status']=='source_unavailable' and not result['results']
    assert asyncio.run(cnj_source.search('concurso',precedent_only=True))['retrieval_status']=='unsupported_filter'

def test_cnj_session_removed_from_result_url():
    url,rid=cnj_source.public_record_url('https://www.cnj.jus.br/InfojurisI2/Jurisprudencia.seam;jsessionid=secret?jurisprudenciaIdJuris=5')
    assert rid=='5' and 'secret' not in url
    with pytest.raises(SourceError):cnj_source.public_record_url('https://www.cnj.jus.br/InfojurisI2/JurisprudenciaEdit.seam?jurisprudenciaIdJuris=5')

def test_tcu_full_record_and_fts_filter(tmp_path):
    row={'KEY':'ACORDAO-1','NUMACORDAO':'10','ANOACORDAO':'2026','SITUACAO':'Oficializado','ACORDAO':'Licitação. Contrato administrativo. Decisão completa publicada pelo TCU.','SUMARIO':'Licitação e contratos.','PROC':'001.001/2026-0','DATASESSAO':'01/10/2026'}
    doc=court_index.tcu_document(row,RESOURCE,'acordaos')
    court_index.ROOT.mkdir();court_index.build_index(court_index.ROOT/'tcu.sqlite3',iter([doc]))
    court_index.STATE['tcu']['status']='ready'
    result=asyncio.run(court_index.search('tcu','licitação',limit=1))
    assert result['results'][0]['full_text_retrieved'] is True
    assert result['results'][0]['judgment_date']=='2026-10-01'
    assert not asyncio.run(court_index.search('tcu','licitação',precedent_only=True))['results']
    assert not asyncio.run(court_index.search('tcu','licitação',area='administrativo'))['results']
    assert court_index.tcu_document({**row,'SITUACAO':'Sigiloso'},RESOURCE,'acordaos') is None

def test_tcu_excerpt_is_not_full_text():
    doc=court_index.tcu_document({'KEY':'CONSULTA-1','NUMACORDAO':'1','ANOACORDAO':'2026','ENUNCIADO':'Enunciado oficial de consulta.','EXCERTO':'Fragmento do voto.'},RESOURCE,'consultas')
    assert not doc['full_text_retrieved'] and not doc['precedent']
    assert doc['retrieval_status']=='official_excerpt_retrieved'

def archive(name,content=b'Texto oficial de decisao de licitacao com conteudo integral. '*3):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:z.writestr(name,content)
    return buffer.getvalue()

def test_stj_full_text_requires_matching_metadata():
    data=[{'SeqDocumento':5,'processo':'REsp 123','tipoDocumento':'ACÓRDÃO','dataPublicacao':'2026-10-08'}]
    docs=list(court_index.zip_documents(data,archive('5.txt'),RESOURCE))
    assert docs[0]['full_text_retrieved'] and docs[0]['source_record_locator']['archive_member']=='5.txt'
    assert docs[0]['judgment_date'] is None
    assert list(court_index.zip_documents(data,archive('6.txt'),RESOURCE))==[]

@pytest.mark.parametrize('name',['../5.txt','/5.txt','5.exe'])
def test_zip_paths_never_extracted(name):
    with pytest.raises(SourceError):list(court_index.zip_documents([],archive(name),RESOURCE))

def test_tcu_wrong_csv_rejected(tmp_path):
    path=tmp_path/'input.csv';path.write_text('<html>captcha</html>')
    with pytest.raises(SourceError):list(court_index.csv_documents(path,RESOURCE,'acordaos'))

def test_failed_refresh_keeps_previous_cache(monkeypatch):
    row={'KEY':'ACORDAO-1','NUMACORDAO':'10','ANOACORDAO':'2026','ACORDAO':'Licitação. Contrato administrativo. Texto oficial anterior.'}
    court_index.ROOT.mkdir();court_index.build_index(court_index.ROOT/'tcu.sqlite3',iter([court_index.tcu_document(row,RESOURCE,'acordaos')]))
    async def malformed(url,path,**kwargs):
        path.write_text('<html>indisponível</html>');return RESOURCE
    monkeypatch.setattr(court_index,'download',malformed)
    state=asyncio.run(court_index.refresh_tcu(force=True))
    assert state['status']=='unavailable'
    result=asyncio.run(court_index.search('tcu','licitação'))
    assert result['results'][0]['cache_status']=='unavailable'
    assert result['results'][0]['record_id']=='ACORDAO-1'

def test_duplicate_resource_record_replaces_search_text():
    def doc(body):
        return court_index.tcu_document({'KEY':'ACORDAO-1','NUMACORDAO':'10','ANOACORDAO':'2026','ACORDAO':body},RESOURCE,'acordaos')
    court_index.ROOT.mkdir()
    court_index.build_index(court_index.ROOT/'tcu.sqlite3',iter([doc('Texto oficial inicial sobre improbidade administrativa.'),doc('Texto oficial corrigido sobre licitação e contratos administrativos.')]))
    court_index.STATE['tcu']['status']='ready'
    assert not asyncio.run(court_index.search('tcu','improbidade'))['results']
    assert len(asyncio.run(court_index.search('tcu','licitação'))['results'])==1

def test_new_hosts_are_exact_and_https():
    validate_url('https://sites.tcu.gov.br/dados-abertos/')
    for url in ('https://sites.tcu.gov.br.attacker.test/','http://www.cnj.jus.br/','https://digital.stf.jus.br:8080/'):
        with pytest.raises(SourceError):validate_url(url)

def test_cnj_redirect_stays_https_and_never_upgrades_other_destinations():
    result=redirect_target(cnj_source.SEARCH,'http://www.cnj.jus.br/InfojurisI2/JurisprudenciaListSearch.seam?cid=5')
    assert result.startswith('https://www.cnj.jus.br/')
    for destination in ('http://evil.test/InfojurisI2/JurisprudenciaListSearch.seam','http://www.cnj.jus.br/InfojurisI2/JurisprudenciaEdit.seam','http://www.cnj.jus.br:8080/InfojurisI2/JurisprudenciaListSearch.seam'):
        with pytest.raises(SourceError):redirect_target(cnj_source.SEARCH,destination)

def test_tribunal_routing_does_not_replace_cnj_with_stj(monkeypatch):
    async def cnj(*args,**kwargs):return {'results':[],'warnings':['CNJ only'],'coverage':{'tribunal':'cnj'},'retrieval_status':'no_results_in_coverage'}
    monkeypatch.setattr(cnj_source,'search',cnj)
    result=asyncio.run(jurisprudence.search('concurso',tribunal='cnj'))
    assert result['warnings']==['CNJ only'] and result['coverage']['tribunal']=='cnj'

@pytest.mark.parametrize('q',['AREsp 3335301','AREsp 3.335.301','AgInt no AREsp n. 3.335.301/SP'])
def test_process_identifier_excludes_other_cases_and_keeps_full_text(monkeypatch,q):
    wrong={'tribunal':'stj','class':'REsp','case_number':'1556957','record_id':'wrong','summary':'Menciona AREsp na decisão.'}
    right={'tribunal':'stj','class':'DECISÃO','case_number':'AREsp 3335301','record_id':'right','full_text_retrieved':True}
    async def mirrors(*args,**kwargs):return {'results':[wrong],'warnings':[],'coverage':{}}
    async def full(source,query,*args,**kwargs):
        assert query=='aresp 3335301'
        return {'results':[right],'warnings':[],'coverage':{}}
    monkeypatch.setattr(jurisprudence.stj_index,'search',mirrors)
    monkeypatch.setattr(court_index,'search',full)
    result=asyncio.run(jurisprudence.search(q,tribunal='stj',limit=1))
    assert result['results']==[right]

def test_wrong_process_class_is_not_exact_match():
    doc={'tribunal':'stj','class':'REsp','case_number':'3335301'}
    assert not jurisprudence.matches_case(doc,('aresp','3335301'))
