"""Authenticated MCP resource server; legacy REST remains available.

OAuth issuer, JWKS and owner subject must be configured before MCP is enabled.
No production credentials are stored in this module or the plugin bundle.
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlparse
import asyncio
import os

import httpx
import jwt
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.responses import JSONResponse

SCOPE = "legal:read"

@dataclass(frozen=True)
class Settings:
    issuer: str
    jwks_url: str
    resource: str
    owner_subject: str

    @classmethod
    def from_env(cls):
        values = [os.getenv(name, "").strip() for name in (
            "MCP_OAUTH_ISSUER", "MCP_OAUTH_JWKS_URL", "MCP_RESOURCE_URL", "MCP_OWNER_SUBJECT")]
        if not all(values):
            return None
        for value in values[:3]:
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("MCP URLs must be explicit HTTPS URLs without credentials, query or fragment")
        if urlparse(values[2]).path != "/mcp":
            raise ValueError("MCP_RESOURCE_URL must end in /mcp")
        return cls(*values)

class OwnerTokenVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys = jwt.PyJWKClient(settings.jwks_url, cache_keys=True, timeout=5)

    async def verify_token(self, token: str):
        if len(token) > 16384:
            return None
        try:
            key = await asyncio.to_thread(self.keys.get_signing_key_from_jwt, token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"],
                issuer=self.settings.issuer, audience=self.settings.resource,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]})
            scopes = claims.get("scope", "")
            if not isinstance(scopes, str) or SCOPE not in scopes.split():
                return None
            if claims["sub"] != self.settings.owner_subject:
                return None
            return AccessToken(token=token, client_id=claims.get("azp", claims.get("client_id", "owner")),
                scopes=scopes.split(), expires_at=claims["exp"], resource=self.settings.resource,
                subject=claims["sub"], claims={"iss": claims["iss"]})
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, OSError):
            return None


def build_mcp(rest_app: FastAPI, settings: Settings):
    verifier = OwnerTokenVerifier(settings)
    origin = urlparse(settings.resource)
    mcp = FastMCP("Legal Research API", stateless_http=True, json_response=True,
        token_verifier=verifier,
        auth=AuthSettings(issuer_url=settings.issuer, resource_server_url=settings.resource,
            required_scopes=[SCOPE], validate_token_resource=True),
        transport_security=TransportSecuritySettings(
            allowed_hosts=[origin.netloc], allowed_origins=[f"{origin.scheme}://{origin.netloc}", "https://chatgpt.com"]),
        instructions="Catálogo estático de legislação e links de portais. Confirme vigência e decisões nas fontes oficiais.")
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    async def call(path, params=None):
        key = os.getenv("API_KEY", "")
        if not key:
            raise ValueError("REST authentication is not configured")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=rest_app), base_url="http://internal", timeout=15) as client:
            response = await client.get(path, params={k:v for k,v in (params or {}).items() if v is not None and k in {"q", "area", "source_type", "official_source", "only_current", "limit", "act_type", "include_revoked", "tribunal", "precedent_only"}},
                headers={"Authorization": "Bearer " + key})
        if response.status_code != 200:
            # Never echo request headers, key or arbitrary upstream exception details.
            raise ValueError(f"REST operation failed (HTTP {response.status_code})")
        return response.json()

    @mcp.tool(annotations=annotations)
    async def getHealth() -> dict:
        """Verifica disponibilidade da API jurídica autenticada."""
        return await call("/health")

    @mcp.tool(annotations=annotations)
    async def listSources() -> dict:
        """Lista as fontes cadastradas, sem garantir consulta em tempo real."""
        return await call("/v1/sources")

    @mcp.tool(annotations=annotations)
    async def listAreas() -> dict:
        """Lista as áreas jurídicas reconhecidas pela API."""
        return await call("/v1/areas")

    @mcp.tool(annotations=annotations)
    async def searchLegalContent(q: Annotated[str, Field(min_length=2)], area: str | None=None,
        source_type: str | None=None, official_source: str | None=None, only_current: bool=True,
        limit: Annotated[int, Field(ge=1, le=20)]=5) -> dict:
        """Pesquisa catálogo fixo e links de portais; os filtros mantêm as limitações da REST original."""
        return await call("/v1/search", locals())

    @mcp.tool(annotations=annotations)
    async def searchLegislation(q: Annotated[str, Field(min_length=2)], area: str | None=None,
        official_source: str | None=None, act_type: str | None=None, only_current: bool=True,
        include_revoked: bool=False, limit: Annotated[int, Field(ge=1, le=20)]=5) -> dict:
        """Pesquisa 14 normas cadastradas. Datas de resposta não comprovam verificação de vigência."""
        return await call("/v1/legislation", locals())

    @mcp.tool(annotations=annotations)
    async def searchJurisprudence(q: Annotated[str, Field(min_length=2)], area: str | None=None,
        tribunal: str | None=None, precedent_only: bool=False,
        limit: Annotated[int, Field(ge=1, le=20)]=5) -> dict:
        """Retorna links de portais oficiais, NÃO acórdãos ou precedentes efetivamente pesquisados."""
        return await call("/v1/jurisprudence", locals())

    return mcp, verifier


def install_mcp(app: FastAPI):
    try:
        settings = Settings.from_env()
    except ValueError:
        settings = None
    if settings is None or not os.getenv("API_KEY", ""):
        @app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
        async def unavailable():
            return JSONResponse({"error": "MCP authentication setup required"}, status_code=503)
        return None
    mcp, verifier = build_mcp(app, settings)
    mcp_app = mcp.streamable_http_app()
    previous = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            async with mcp.session_manager.run():
                yield
    app.router.lifespan_context = lifespan
    # Mount last: existing /health and /v1 routes retain their behavior.
    app.mount("/", mcp_app)
    return mcp
