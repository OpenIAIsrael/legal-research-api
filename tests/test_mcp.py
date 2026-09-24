import asyncio
import os
import time
from types import SimpleNamespace
import secrets

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from starlette.testclient import TestClient

os.environ['API_KEY'] = secrets.token_urlsafe(32)  # synthetic test-only credential
import main
from mcp_integration import Settings, OwnerTokenVerifier, build_mcp, install_mcp

CONFIG = Settings('https://identity.example.test/', 'https://identity.example.test/jwks',
    'https://legal.example.test/mcp', 'owner-test')
PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = PRIVATE.public_key()


def token(**overrides):
    claims = dict(iss=CONFIG.issuer, aud=CONFIG.resource, sub=CONFIG.owner_subject,
        iat=int(time.time()), exp=int(time.time())+300, scope='legal:read', azp='test-client')
    claims.update(overrides)
    return jwt.encode(claims, PRIVATE, algorithm='RS256')


def fixture_server():
    mcp, verifier = build_mcp(main.app, CONFIG)
    verifier.keys = SimpleNamespace(get_signing_key_from_jwt=lambda value: SimpleNamespace(key=PUBLIC))
    return mcp, verifier


def test_fail_closed_without_configuration():
    app = FastAPI()
    install_mcp(app)
    with TestClient(app) as c:
        assert c.post('/mcp').status_code == 503

@pytest.mark.parametrize('changes', [dict(aud='wrong'),dict(iss='https://attacker.test/'),
    dict(sub='other-user'),dict(scope='other:read'),dict(exp=1)])
def test_reject_invalid_identity(changes):
    _, verifier = fixture_server()
    assert asyncio.run(verifier.verify_token(token(**changes))) is None


def test_reject_signature_and_algorithm():
    _, verifier = fixture_server()
    bad = jwt.encode(dict(sub='owner-test'), 'synthetic-test-secret-only-32chars', algorithm='HS256')
    assert asyncio.run(verifier.verify_token(bad)) is None


def test_oauth_metadata_and_access_control():
    mcp, _ = fixture_server()
    with TestClient(mcp.streamable_http_app(), base_url='https://legal.example.test') as c:
        r = c.post('/mcp', json={})
        assert r.status_code == 401
        assert 'resource_metadata=' in r.headers['www-authenticate']
        md = c.get('/.well-known/oauth-protected-resource/mcp').json()
        assert md['resource'] == CONFIG.resource
        assert md['authorization_servers'] == [CONFIG.issuer]


def test_all_six_operations_over_mcp():
    mcp, _ = fixture_server()
    with TestClient(mcp.streamable_http_app(), base_url='https://legal.example.test') as c:
        headers = {'Authorization':'Bearer '+token(), 'Accept':'application/json, text/event-stream'}
        def rpc(method, params=None):
            r=c.post('/mcp', headers=headers, json=dict(jsonrpc='2.0',id=1,method=method,params=params or {}))
            assert r.status_code == 200
            return r.json()['result']
        assert rpc('initialize',dict(protocolVersion='2025-11-25',capabilities={},clientInfo=dict(name='test',version='1')))['serverInfo']['name']=='Legal Research API'
        tools = rpc('tools/list')['tools']
        assert {t['name'] for t in tools} == {'getHealth','listSources','listAreas','searchLegalContent','searchLegislation','searchJurisprudence'}
        for name,args in [('getHealth',{}),('listSources',{}),('listAreas',{}),
            ('searchLegalContent',{'q':'compliance','limit':2}),('searchLegislation',{'q':'LGPD','limit':1}),
            ('searchJurisprudence',{'q':'tributario','tribunal':'stj','limit':1})]:
            result = rpc('tools/call',dict(name=name,arguments=args))
            assert not result.get('isError'), result
            assert os.environ['API_KEY'] not in str(result)
        assert rpc('tools/call',dict(name='searchLegislation',arguments={'q':'a'}))['isError']
        assert rpc('tools/call',dict(name='searchLegislation',arguments={'q':'LGPD','limit':21}))['isError']


def test_rest_still_protected():
    with TestClient(main.app) as c:
        assert c.get('/health').status_code == 401
        assert c.get('/v1/sources', headers={'Authorization':'Bearer invalid'}).status_code == 403
        assert c.get('/health', headers={'Authorization':'Bearer '+os.environ['API_KEY']}).status_code == 200
