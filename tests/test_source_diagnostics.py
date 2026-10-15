import asyncio
import logging
import socket

import httpx
import pytest

import official_http


@pytest.mark.parametrize('error,category',[
    (httpx.ConnectError('secret-token'), 'connection_error'),
    (httpx.ReadTimeout('secret-token'), 'timeout'),
    (ValueError('secret-token'), 'invalid_response'),
])
def test_transport_failure_is_diagnosable_without_secret(monkeypatch,caplog,error,category):
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):raise error
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(official_http.httpx,'AsyncClient',Client)
    monkeypatch.setattr(official_http,'CACHE',{})
    with caplog.at_level(logging.WARNING),pytest.raises(official_http.SourceError) as caught:
        asyncio.run(official_http.fetch('https://www.camara.leg.br/test?token=secret-token'))
    assert category in str(caught.value)
    assert 'host=www.camara.leg.br' in caplog.text
    assert category in caplog.text
    assert 'secret-token' not in caplog.text+str(caught.value)
    assert '/test' not in caplog.text


def test_dns_error_nested_under_transport():
    underlying=socket.gaierror('private DNS details')
    error=httpx.ConnectError('private connection details')
    error.__cause__=underlying
    assert official_http.network_failure(error)=='dns_error'


def test_http_denial_logged_without_response_body(monkeypatch,caplog):
    class Response:
        status_code=403
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def stream(self,*args,**kwargs):return Response()
    monkeypatch.setattr(official_http.httpx,'AsyncClient',Client)
    monkeypatch.setattr(official_http,'CACHE',{})
    with caplog.at_level(logging.WARNING),pytest.raises(official_http.SourceError,match='HTTP 403'):
        asyncio.run(official_http.fetch('https://dadosabertos.web.stj.jus.br/test?token=secret-token'))
    assert 'status=403' in caplog.text
    assert 'secret-token' not in caplog.text
