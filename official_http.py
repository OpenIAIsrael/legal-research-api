"""Bounded HTTPS requests to an explicit set of public official hosts."""
import asyncio
import hashlib
import ipaddress
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
import httpx

HOSTS={'www.lexml.gov.br','www.planalto.gov.br','www.camara.leg.br','www2.camara.leg.br','dadosabertos.web.stj.jus.br','scon.stj.jus.br','processo.stj.jus.br'}
CACHE={}
class SourceError(Exception):pass

def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def validate_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):
        raise SourceError('URL fora da lista de fontes oficiais permitidas')
    return p

async def validate_dns(host):
    try:
        addresses=await asyncio.to_thread(socket.getaddrinfo,host,443,type=socket.SOCK_STREAM)
    except OSError:raise SourceError('DNS da fonte indisponível') from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise SourceError('Destino de rede não público')

async def fetch(url,params=None,max_bytes=6_000_000,ttl=3600,request_timeout=18):
    request_url=str(httpx.URL(url,params=params)) if params else url
    validate_url(request_url)
    cached=CACHE.get(request_url)
    if cached and time.monotonic()-cached[0]<ttl:
        return dict(cached[1],cache_hit=True)
    try:
        async with asyncio.timeout(request_timeout):
            async with httpx.AsyncClient(timeout=httpx.Timeout(min(request_timeout,25),connect=5),follow_redirects=False,headers={'User-Agent':'LegalResearchAPI/4.1 (+official-document-retrieval)'}) as client:
                current=request_url
                for _ in range(4):
                    validate_url(current)  # Exact host allowlist; the configured transport/proxy resolves DNS.
                    async with client.stream('GET',current) as r:
                        if r.status_code in (301,302,303,307,308):
                            current=urljoin(current,r.headers.get('location',''));continue
                        if r.status_code!=200:raise SourceError(f'Fonte retornou HTTP {r.status_code}')
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
                        if len(raw)<=1_500_000:
                            if len(CACHE)>=32:CACHE.pop(next(iter(CACHE)))
                            CACHE[request_url]=(time.monotonic(),result)
                        return result
                raise SourceError('Excesso de redirecionamentos')
    except (httpx.HTTPError,TimeoutError,OSError,ValueError) as e:
        raise SourceError('Falha de rede, tempo ou formato na fonte oficial') from None
