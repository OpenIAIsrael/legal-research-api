from fastapi import FastAPI, Query, Header, HTTPException
from typing import Optional, List
from datetime import datetime
import os
import re

app = FastAPI(
    title="Legal Research API",
    version="4.0.0",
    description="API jurídica estratégica com Bearer, legislação oficial e jurisprudência oficial inicial."
)

API_KEY = os.getenv("API_KEY", "troque-esta-chave-em-producao")

LEGAL_AREAS = [
    "constitucional", "administrativo", "tributario", "civil", "processual_civil",
    "penal", "processual_penal", "trabalhista", "previdenciario", "empresarial",
    "consumidor", "digital", "ambiental", "eleitoral", "familia",
    "infancia_juventude", "licitacoes_contratos", "transparencia", "compliance"
]

OFFICIAL_SOURCES = [
    {"id": "planalto", "name": "Planalto", "type": "fontes_oficiais", "official": True},
    {"id": "stf", "name": "STF", "type": "fontes_oficiais", "official": True},
    {"id": "stj", "name": "STJ", "type": "fontes_oficiais", "official": True},
    {"id": "cnj", "name": "CNJ", "type": "fontes_oficiais", "official": True},
    {"id": "tcu", "name": "TCU", "type": "fontes_oficiais", "official": True},
    {"id": "lexml", "name": "LexML", "type": "fontes_oficiais", "official": True}
]

LEGISLATION_CATALOG = [
    {
        "title": "Constituição da República Federativa do Brasil de 1988",
        "act_type": "constituicao",
        "number": "CF/1988",
        "year": 1988,
        "area": "constitucional",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Texto constitucional vigente da República Federativa do Brasil.",
        "url": "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm",
        "aliases": ["constituicao", "cf", "cf88", "constituicao federal", "constituicao de 1988"],
        "themes": ["direitos fundamentais", "organizacao do estado", "poderes", "tributacao", "ordem economica"]
    },
    {
        "title": "Emenda Constitucional nº 132/2023",
        "act_type": "emenda_constitucional",
        "number": "EC 132/2023",
        "year": 2023,
        "area": "tributario",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Emenda constitucional da reforma tributária sobre o consumo.",
        "url": "https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc132.htm",
        "aliases": ["reforma tributaria", "ec 132", "ec 132/2023", "tributaria", "ibs", "cbs", "imposto seletivo"],
        "themes": ["reforma tributaria", "consumo", "tributos", "ibs", "cbs", "imposto seletivo"]
    },
    {
        "title": "Estatuto da Criança e do Adolescente",
        "act_type": "estatuto",
        "number": "Lei 8.069/1990",
        "year": 1990,
        "area": "infancia_juventude",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Dispõe sobre o Estatuto da Criança e do Adolescente.",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/l8069.htm",
        "aliases": ["eca", "estatuto da crianca e do adolescente", "crianca", "adolescente"],
        "themes": ["infancia", "juventude", "protecao integral", "menor", "adolescente"]
    },
    {
        "title": "Lei Geral de Proteção de Dados Pessoais",
        "act_type": "lei_ordinaria",
        "number": "Lei 13.709/2018",
        "year": 2018,
        "area": "digital",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Lei Geral de Proteção de Dados Pessoais.",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm",
        "aliases": ["lgpd", "protecao de dados", "dados pessoais", "privacidade"],
        "themes": ["dados pessoais", "tratamento de dados", "privacidade", "seguranca da informacao"]
    },
    {
        "title": "Marco Civil da Internet",
        "act_type": "lei_ordinaria",
        "number": "Lei 12.965/2014",
        "year": 2014,
        "area": "digital",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Estabelece princípios, garantias, direitos e deveres para o uso da internet no Brasil.",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm",
        "aliases": ["marco civil", "internet", "marco civil da internet"],
        "themes": ["internet", "provedores", "responsabilidade civil", "dados", "rede"]
    },
    {
        "title": "Código de Defesa do Consumidor",
        "act_type": "codigo",
        "number": "Lei 8.078/1990",
        "year": 1990,
        "area": "consumidor",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Dispõe sobre a proteção do consumidor.",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",
        "aliases": ["cdc", "consumidor", "defesa do consumidor"],
        "themes": ["consumo", "fornecedor", "produto", "servico", "responsabilidade"]
    },
    {
        "title": "Consolidação das Leis do Trabalho",
        "act_type": "codigo",
        "number": "Decreto-Lei 5.452/1943",
        "year": 1943,
        "area": "trabalhista",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Consolidação das Leis do Trabalho.",
        "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm",
        "aliases": ["clt", "trabalho", "leis do trabalho", "direito do trabalho"],
        "themes": ["emprego", "contrato de trabalho", "jornada", "ferias", "salario"]
    },
    {
        "title": "Código Civil",
        "act_type": "codigo",
        "number": "Lei 10.406/2002",
        "year": 2002,
        "area": "civil",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Institui o Código Civil.",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm",
        "aliases": ["codigo civil", "cc", "civil"],
        "themes": ["obrigacoes", "contratos", "responsabilidade civil", "familia", "sucessoes"]
    },
    {
        "title": "Código de Processo Civil",
        "act_type": "codigo",
        "number": "Lei 13.105/2015",
        "year": 2015,
        "area": "processual_civil",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Código de Processo Civil.",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm",
        "aliases": ["cpc", "processo civil", "codigo de processo civil"],
        "themes": ["procedimento", "recursos", "tutela", "cumprimento de sentenca", "execucao"]
    },
    {
        "title": "Código Penal",
        "act_type": "codigo",
        "number": "Decreto-Lei 2.848/1940",
        "year": 1940,
        "area": "penal",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Código Penal brasileiro.",
        "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm",
        "aliases": ["codigo penal", "cp", "penal"],
        "themes": ["crimes", "penas", "parte geral", "parte especial"]
    },
    {
        "title": "Código de Processo Penal",
        "act_type": "codigo",
        "number": "Decreto-Lei 3.689/1941",
        "year": 1941,
        "area": "processual_penal",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Código de Processo Penal brasileiro.",
        "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689.htm",
        "aliases": ["codigo de processo penal", "cpp", "processo penal"],
        "themes": ["inquerito", "acao penal", "provas", "prisao", "recursos"]
    },
    {
        "title": "Lei de Licitações e Contratos Administrativos",
        "act_type": "lei_ordinaria",
        "number": "Lei 14.133/2021",
        "year": 2021,
        "area": "licitacoes_contratos",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Lei geral de licitações e contratos administrativos.",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm",
        "aliases": ["14133", "lei 14133", "nova lei de licitacoes", "licitacoes", "contratos administrativos"],
        "themes": ["licitacao", "contrato administrativo", "pregao", "concorrencia", "dispensa", "inexigibilidade"]
    },
    {
        "title": "Lei de Acesso à Informação",
        "act_type": "lei_ordinaria",
        "number": "Lei 12.527/2011",
        "year": 2011,
        "area": "transparencia",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Regula o acesso a informações previsto na Constituição.",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm",
        "aliases": ["lai", "lei de acesso a informacao", "acesso a informacao", "transparencia"],
        "themes": ["transparencia", "informacao publica", "dados publicos"]
    },
    {
        "title": "Lei Anticorrupção Empresarial",
        "act_type": "lei_ordinaria",
        "number": "Lei 12.846/2013",
        "year": 2013,
        "area": "compliance",
        "official_source": "planalto",
        "status": "vigente",
        "summary": "Responsabilização administrativa e civil de pessoas jurídicas por atos contra a administração pública.",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm",
        "aliases": ["lei anticorrupcao", "12846", "compliance", "integridade"],
        "themes": ["corrupcao", "responsabilizacao", "programa de integridade", "administracao publica"]
    }
]

def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def require_bearer(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.replace("Bearer ", "", 1).strip()
    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

def normalize(text: str) -> str:
    text = text.lower().strip()
    return re.sub(r"\s+", " ", text)

def tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9_À-ÿ]+", normalize(text)) if len(t) > 1]

def score_item(query: str, item: dict) -> int:
    query_tokens = tokenize(query)
    haystacks = [normalize(item["title"]), normalize(item.get("summary", "")), normalize(item.get("area", ""))]
    haystacks.extend(normalize(x) for x in item.get("aliases", []))
    haystacks.extend(normalize(x) for x in item.get("themes", []))
    haystack = " ".join(haystacks)
    score = 0
    for token in query_tokens:
        if token in haystack:
            score += 2
    if normalize(query) in haystack:
        score += 5
    return score

def filter_catalog(query: str, area: Optional[str] = None, official_source: Optional[str] = None,
                   act_type: Optional[str] = None, only_current: bool = True) -> List[dict]:
    matches = []
    for item in LEGISLATION_CATALOG:
        if area and item["area"] != area:
            continue
        if official_source and item["official_source"] != official_source:
            continue
        if act_type and item["act_type"] != act_type:
            continue
        if only_current and item["status"] != "vigente":
            continue
        score = score_item(query, item)
        if score > 0:
            enriched = dict(item)
            enriched["_score"] = score
            matches.append(enriched)
    matches.sort(key=lambda x: (-x["_score"], -x["year"], x["title"]))
    return matches

def official_jurisprudence_results(query: str, area: Optional[str], tribunal: Optional[str], precedent_only: bool):
    results = []

    if tribunal in (None, "stf"):
        results.append({
            "title": f"Pesquisa oficial STF para: {query}",
            "tribunal": "stf",
            "class": "pesquisa_oficial",
            "case_number": "",
            "area": area,
            "summary": "Portal oficial de jurisprudência do STF com busca direcionada.",
            "precedent": precedent_only,
            "judgment_date": None,
            "url": "https://portal.stf.jus.br/jurisprudencia/"
        })

    if tribunal in (None, "stj"):
        results.append({
            "title": f"Pesquisa oficial STJ para: {query}",
            "tribunal": "stj",
            "class": "pesquisa_oficial",
            "case_number": "",
            "area": area,
            "summary": "Portal oficial de jurisprudência do STJ com busca direcionada.",
            "precedent": precedent_only,
            "judgment_date": None,
            "url": "https://scon.stj.jus.br/SCON/"
        })

    if tribunal == "cnj":
        results.append({
            "title": f"Pesquisa oficial CNJ para: {query}",
            "tribunal": "cnj",
            "class": "pesquisa_oficial",
            "case_number": "",
            "area": area,
            "summary": "Portal institucional do CNJ para pesquisa e acompanhamento de conteúdos oficiais.",
            "precedent": precedent_only,
            "judgment_date": None,
            "url": "https://www.cnj.jus.br/"
        })

    if tribunal == "tcu":
        results.append({
            "title": f"Pesquisa oficial TCU para: {query}",
            "tribunal": "tcu",
            "class": "pesquisa_oficial",
            "case_number": "",
            "area": area,
            "summary": "Portal oficial do TCU para pesquisa institucional e jurisprudencial.",
            "precedent": precedent_only,
            "judgment_date": None,
            "url": "https://pesquisa.apps.tcu.gov.br/"
        })

    return results

@app.get("/health")
def health(authorization: Optional[str] = Header(default=None)):
    require_bearer(authorization)
    return {
        "status": "healthy",
        "api": "Legal Research API",
        "version": "4.0.0",
        "timestamp": now_iso()
    }

@app.get("/v1/sources")
def list_sources(authorization: Optional[str] = Header(default=None)):
    require_bearer(authorization)
    return {"sources": OFFICIAL_SOURCES}

@app.get("/v1/areas")
def list_areas(authorization: Optional[str] = Header(default=None)):
    require_bearer(authorization)
    return {"areas": LEGAL_AREAS}

@app.get("/v1/search")
def search_legal_content(
    q: str = Query(..., min_length=2),
    area: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    official_source: Optional[str] = Query(None),
    only_current: bool = Query(True),
    limit: int = Query(5, ge=1, le=20),
    authorization: Optional[str] = Header(default=None)
):
    require_bearer(authorization)

    warnings = []
    if area and area not in LEGAL_AREAS:
        return {
            "query": q, "area": area, "source_type": source_type, "official_source": official_source,
            "only_current": only_current, "results": [],
            "warnings": [f"Área inválida: {area}"],
            "meta": {"limit": limit, "strategy_mode": True, "vigency_focus": True, "official_priority": True}
        }

    if source_type and source_type not in ("legislacao", "jurisprudencia", "fontes_oficiais"):
        warnings.append("Nesta versão, os resultados reais estão concentrados em legislação e jurisprudência oficiais.")

    results = []
    legislation = filter_catalog(
        query=q,
        area=area,
        official_source=official_source if official_source == "planalto" else None,
        act_type=None,
        only_current=only_current
    )[:limit]

    for item in legislation:
        results.append({
            "title": item["title"],
            "source": item["official_source"],
            "source_type": "legislacao",
            "official_source": item["official_source"],
            "area": item["area"],
            "summary": item["summary"],
            "url": item["url"],
            "vigente": item["status"] == "vigente",
            "updated_at": now_iso()
        })

    if len(results) < limit:
        jur_results = official_jurisprudence_results(q, area, None, False)
        for jr in jur_results[: max(0, limit - len(results))]:
            results.append({
                "title": jr["title"],
                "source": jr["tribunal"],
                "source_type": "jurisprudencia",
                "official_source": jr["tribunal"],
                "area": jr["area"],
                "summary": jr["summary"],
                "url": jr["url"],
                "vigente": True,
                "updated_at": now_iso()
            })

    return {
        "query": q,
        "area": area,
        "source_type": source_type,
        "official_source": official_source,
        "only_current": only_current,
        "results": results[:limit],
        "warnings": warnings,
        "meta": {
            "limit": limit,
            "strategy_mode": True,
            "vigency_focus": True,
            "official_priority": True
        }
    }

@app.get("/v1/legislation")
def search_legislation(
    q: str = Query(..., min_length=2),
    area: Optional[str] = Query(None),
    official_source: Optional[str] = Query(None),
    act_type: Optional[str] = Query(None),
    only_current: bool = Query(True),
    include_revoked: bool = Query(False),
    limit: int = Query(5, ge=1, le=20),
    authorization: Optional[str] = Header(default=None)
):
    require_bearer(authorization)

    warnings = []
    if area and area not in LEGAL_AREAS:
        return {
            "query": q, "area": area, "official_source": official_source, "act_type": act_type,
            "only_current": only_current, "include_revoked": include_revoked,
            "results": [], "warnings": [f"Área inválida: {area}"]
        }

    if official_source and official_source != "planalto":
        warnings.append("Nesta versão, a legislação oficial real está centrada no Planalto.")

    matches = filter_catalog(
        query=q,
        area=area,
        official_source="planalto" if official_source else None,
        act_type=act_type,
        only_current=only_current
    )[:limit]

    results = [{
        "title": item["title"],
        "act_type": item["act_type"],
        "number": item["number"],
        "year": item["year"],
        "area": item["area"],
        "official_source": item["official_source"],
        "status": item["status"],
        "summary": item["summary"],
        "url": item["url"],
        "last_checked_at": now_iso()
    } for item in matches]

    if include_revoked:
        warnings.append("Conteúdo revogado ainda não foi modelado nesta fase.")

    return {
        "query": q,
        "area": area,
        "official_source": official_source,
        "act_type": act_type,
        "only_current": only_current,
        "include_revoked": include_revoked,
        "results": results,
        "warnings": warnings
    }

@app.get("/v1/jurisprudence")
def search_jurisprudence(
    q: str = Query(..., min_length=2),
    area: Optional[str] = Query(None),
    tribunal: Optional[str] = Query(None),
    precedent_only: bool = Query(False),
    limit: int = Query(5, ge=1, le=20),
    authorization: Optional[str] = Header(default=None)
):
    require_bearer(authorization)

    warnings = []
    if tribunal and tribunal not in {"stf", "stj", "cnj", "tcu"}:
        warnings.append("Tribunal fora da integração inicial. Use stf, stj, cnj ou tcu.")

    results = official_jurisprudence_results(q, area, tribunal, precedent_only)[:limit]

    if not results:
        warnings.append("Nenhum resultado configurado para o filtro informado.")

    return {
        "query": q,
        "area": area,
        "tribunal": tribunal,
        "precedent_only": precedent_only,
        "results": results,
        "warnings": warnings
    }
