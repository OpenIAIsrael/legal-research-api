"""Bounded HTTPS requests to an explicit set of public official hosts."""
import asyncio
import hashlib
import ipaddress
import logging
import socket
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
import httpx

HOSTS={'www.lexml.gov.br','www.planalto.gov.br','www.camara.leg.br','www2.camara.leg.br','dadosabertos.web.stj.jus.br','scon.stj.jus.br','processo.stj.jus.br'}
HOSTS.update({'sites.tcu.gov.br','www.cnj.jus.br','atos.cnj.jus.br','portal.stf.jus.br','jurisprudencia.stf.jus.br','digital.stf.jus.br'})
CACHE={}
LOGGER=logging.getLogger(__name__)
class SourceError(Exception):pass

def network_failure(exc):
    """Classify failures without copying exception text, URLs or credentials."""
    chain=[];seen=set();current=exc
    while current is not None and id(current) not in seen:
        seen.add(id(current));chain.append(current)
        current=current.__cause__ or current.__context__
    if any(isinstance(e,socket.gaierror) for e in chain):return 'dns_error'
    if isinstance(exc,(httpx.TimeoutException,TimeoutError)):return 'timeout'
    if isinstance(exc,httpx.ConnectError):return 'connection_error'
    if isinstance(exc,httpx.HTTPError):return 'transport_error'
    if isinstance(exc,OSError):return 'os_error'
    return 'invalid_response'

def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def validate_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):
        raise SourceError('URL fora da lista de fontes oficiais permitidas')
    return p

def redirect_target(current,location):
    target=urljoin(current,location);p=urlparse(target)
    # Infojuris emits an HTTP Location after its public search form. Keep transport HTTPS.
    public_paths={'/InfojurisI2/JurisprudenciaListSearch.seam','/InfojurisI2/JurisprudenciaListaBusca.seam'}
    if urlparse(current).hostname=='www.cnj.jus.br' and p.scheme=='http' and p.hostname=='www.cnj.jus.br' and not p.username and not p.password and p.port in (None,80) and p.path.split(';')[0] in public_paths:
        target=p._replace(scheme='https',netloc='www.cnj.jus.br').geturl()
    validate_url(target)
    return target

async def validate_dns(host):
    try:
        addresses=await asyncio.to_thread(socket.getaddrinfo,host,443,type=socket.SOCK_STREAM)
    except OSError:raise SourceError('DNS da fonte indisponível') from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise SourceError('Destino de rede não público')

@asynccontextmanager
async def client_scope(client,request_timeout):
    if client is not None:
        yield client
    else:
        async with httpx.AsyncClient(timeout=httpx.Timeout(min(request_timeout,25),connect=5),follow_redirects=False,headers={'User-Agent':'LegalResearchAPI/4.2 (+official-document-retrieval)'}) as owned:
            yield owned

async def fetch(url,params=None,max_bytes=6_000_000,ttl=3600,request_timeout=18,client=None,method='GET',data=None):
    request_url=str(httpx.URL(url,params=params)) if params else url
    validate_url(request_url)
    if method not in ('GET','POST') or (method=='POST' and (urlparse(request_url).hostname!='www.cnj.jus.br' or not urlparse(request_url).path.startswith('/InfojurisI2/JurisprudenciaSearch.seam'))):
        raise SourceError('Método não permitido para a fonte')
    cacheable=client is None and method=='GET' and ttl>0
    cached=CACHE.get(request_url)
    if cacheable and cached and time.monotonic()-cached[0]<ttl:
        return dict(cached[1],cache_hit=True)
    started=time.monotonic()
    current=request_url
    try:
        async with asyncio.timeout(request_timeout):
            async with client_scope(client,request_timeout) as session:
                for _ in range(4):
                    validate_url(current)  # Exact host allowlist; the configured transport/proxy resolves DNS.
                    async with session.stream(method,current,**({'data':data} if data is not None else {})) as r:
                        if r.status_code in (301,302,303,307,308):
                            if method=='POST' and r.status_code in (301,302,303):method='GET';data=None
                            current=redirect_target(current,r.headers.get('location',''));continue
                        if r.status_code!=200:
                            LOGGER.warning('official_source_http host=%s status=%s elapsed_ms=%d',urlparse(current).hostname,r.status_code,int((time.monotonic()-started)*1000))
                            raise SourceError(f'Fonte retornou HTTP {r.status_code}')
                        length=r.headers.get('content-length')
                        if length and int(length)>max_bytes:raise SourceError('Documento excede o limite de tamanho')
                        chunks=[];size=0
                        async for chunk in r.aiter_bytes():
                            size+=len(chunk)
                            if size>max_bytes:raise SourceError('Documento excede o limite de tamanho')
                            chunks.append(chunk)
                        raw=b''.join(chunks)
                        if len(raw)<5000 and any(marker in raw.lower() for marker in (b'504 gateway',b'502 bad gateway',b'503 service unavailable')):
                            raise SourceError('Fonte retornou página de erro em resposta HTTP 200')
                        if b'/_challenge' in raw or b'Verificando sua conex' in raw or b'captcha' in raw[:3000].lower():
                            raise SourceError('Fonte exige verificação de segurança; acesso automatizado indisponível')
                        result={'body':raw,'url':current,'retrieved_at':now(),'source_last_modified':r.headers.get('last-modified'),'sha256':hashlib.sha256(raw).hexdigest(),'cache_hit':False}
                        # Keep the HTTP cache bounded; large STJ resources go directly to the index.
                        if cacheable and len(raw)<=1_500_000:
                            if len(CACHE)>=32:CACHE.pop(next(iter(CACHE)))
                            CACHE[request_url]=(time.monotonic(),result)
                        return result
                raise SourceError('Excesso de redirecionamentos')
    except (httpx.HTTPError,TimeoutError,OSError,ValueError) as e:
        category=network_failure(e)
        LOGGER.warning('official_source_failure host=%s category=%s exception=%s elapsed_ms=%d',urlparse(current).hostname,category,type(e).__name__,int((time.monotonic()-started)*1000))
        raise SourceError(f'Falha de rede, tempo ou formato na fonte oficial ({category})') from None
