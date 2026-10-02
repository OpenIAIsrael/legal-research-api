"""Authenticated legal retrieval service. No generated jurisprudence or fake dates."""
from contextlib import asynccontextmanager, suppress
import asyncio
import hmac
import os
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Query
import legislation
import stj_index
from catalog import LEGAL_AREAS
from official_http import now

VERSION='4.1.0'
API_KEY=os.getenv('API_KEY','')
SOURCES=[
 {'id':'camara','name':'Câmara dos Deputados','type':'fontes_oficiais','official':True,'capability':'federal_legislation_live'},
 {'id':'planalto','name':'Planalto','type':'fontes_oficiais','official':True,'capability':'seeded_document_retrieval','limitation':'Discovery restricted to local seeds; network availability varies.'},
 {'id':'lexml','name':'LexML','type':'fontes_oficiais','official':True,'capability':'sru_discovery','limitation':'Security challenge observed; never bypassed.'},
 {'id':'stj','name':'STJ','type':'fontes_oficiais','official':True,'capability':'judgment_records_rolling_index','limitation':'Recent official Espelhos JSON resources; not full historical corpus or full opinions.'},
 {'id':'stf','name':'STF','type':'fontes_oficiais','official':True,'capability':'unavailable','limitation':'HTTP 403 observed; document connector pending.'},
 {'id':'cnj','name':'CNJ','type':'fontes_oficiais','official':True,'capability':'not_implemented'},
 {'id':'tcu','name':'TCU','type':'fontes_oficiais','official':True,'capability':'not_implemented'}]

@asynccontextmanager
async def lifespan(app):
    task=asyncio.create_task(stj_index.maintenance()) if os.getenv('LEGAL_INDEX_BACKGROUND','1')=='1' else None
    try:yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):await task

app=FastAPI(title='Legal Research API',version=VERSION,description='Recuperação de documentos oficiais com cobertura e limitações explícitas.',lifespan=lifespan)

def require_bearer(authorization):
    if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Missing bearer token')
    if not API_KEY or not hmac.compare_digest(authorization[7:].strip(),API_KEY):raise HTTPException(403,'Invalid API key')

def validate_filters(area=None,official_source=None):
    if area and area not in LEGAL_AREAS:raise HTTPException(422,'Área inválida')
    if official_source and official_source not in {s['id'] for s in SOURCES}:raise HTTPException(422,'Fonte inválida')

def envelope(q,result,**filters):
    return {'query':q,**filters,**result,'response_generated_at':now()}

@app.get('/health')
def health(authorization:Optional[str]=Header(None)):
    require_bearer(authorization)
    return {'status':'healthy','api':'Legal Research API','version':VERSION,'timestamp':now(),'commit':os.getenv('RENDER_GIT_COMMIT'),'stj_index_status':stj_index.STATE['status']}

@app.get('/v1/sources')
def list_sources(authorization:Optional[str]=Header(None)):
    require_bearer(authorization);return {'sources':SOURCES}

@app.get('/v1/areas')
def list_areas(authorization:Optional[str]=Header(None)):
    require_bearer(authorization);return {'areas':LEGAL_AREAS}

@app.get('/v1/legislation')
async def search_legislation(q:str=Query(...,min_length=2,max_length=500),area:Optional[str]=None,official_source:Optional[str]=None,
    act_type:Optional[str]=None,only_current:bool=True,include_revoked:bool=False,limit:int=Query(5,ge=1,le=20),authorization:Optional[str]=Header(None)):
    require_bearer(authorization);validate_filters(area,official_source)
    result=await legislation.search(q,area,official_source,act_type,only_current,include_revoked,limit)
    return envelope(q,result,area=area,official_source=official_source,act_type=act_type,only_current=only_current,include_revoked=include_revoked)

@app.get('/v1/jurisprudence')
async def search_jurisprudence(q:str=Query(...,min_length=2,max_length=500),area:Optional[str]=None,tribunal:Optional[str]=None,
    precedent_only:bool=False,limit:int=Query(5,ge=1,le=20),authorization:Optional[str]=Header(None)):
    require_bearer(authorization);validate_filters(area)
    if tribunal and tribunal not in {'stf','stj','cnj','tcu'}:raise HTTPException(422,'Tribunal inválido')
    result=await stj_index.search(q,area,tribunal,precedent_only,limit)
    return envelope(q,result,area=area,tribunal=tribunal,precedent_only=precedent_only)

@app.get('/v1/search')
async def search_legal_content(q:str=Query(...,min_length=2,max_length=500),area:Optional[str]=None,source_type:Optional[str]=None,
    official_source:Optional[str]=None,only_current:bool=True,limit:int=Query(5,ge=1,le=20),authorization:Optional[str]=Header(None)):
    require_bearer(authorization);validate_filters(area,official_source)
    if source_type not in (None,'legislacao','jurisprudencia','fontes_oficiais'):raise HTTPException(422,'Tipo de fonte inválido')
    operations=[]
    if source_type in (None,'legislacao','fontes_oficiais') and official_source in (None,'camara','planalto','lexml'):
        operations.append(legislation.search(q,area,official_source,only_current=only_current,limit=limit))
    if source_type in (None,'jurisprudencia','fontes_oficiais') and official_source in (None,'stj','stf','cnj','tcu'):
        operations.append(stj_index.search(q,area,official_source,limit=limit))
    parts=await asyncio.gather(*operations)
    # Round-robin avoids letting either source type crowd out the other.
    results=[]
    for index in range(limit):
        for part in parts:
            if index<len(part['results']):results.append(part['results'][index])
    warnings=list(dict.fromkeys(w for p in parts for w in p['warnings']))
    if not operations:warnings.append('Combinação de fonte e tipo sem conector compatível.')
    return envelope(q,{'results':results[:limit],'warnings':warnings,'unverified_results':[r for p in parts for r in p.get('unverified_results',[])][:limit],
        'coverage':[p.get('coverage',{}) for p in parts],'meta':{'limit':limit,'complete':False}},area=area,source_type=source_type,official_source=official_source,only_current=only_current)

from mcp_integration import install_mcp
install_mcp(app)
