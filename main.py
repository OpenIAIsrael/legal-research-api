from fastapi import FastAPI, Query
from typing import Optional, List
from datetime import datetime
import re

app = FastAPI(
    title="Legal Research API",
    version="3.0.0",
    description="API jurídica estratégica com base inicial de legislação federal oficial."
)

LEGAL_AREAS = [
    "constitucional",
    "administrativo",
    "tributario",
    "civil",
    "processual_civil",
    "penal",
    "processual_penal",
    "trabalhista",
    "previdenciario",
    "empresarial",
    "consumidor",
    "digital",
    "ambiental",
    "eleitoral",
    "familia",
    "infancia_juventude",
    "licitacoes_contratos",
    "transparencia",
    "compliance"
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
        "summary": "Dispõe sobre a responsabilização administrativa e civil de pessoas jurídicas pela prática de atos contra a administração pública.",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm",
        "aliases": ["lei anticorrupcao", "12846", "compliance", "integridade"],
        "themes": ["corrupcao", "responsabilizacao", "programa de integridade", "administracao publica"]
    }
]


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\\s+", " ", text)
    return text


def tokenize(text: str) -> List[str]:
    text = normalize(text)
    tokens = re.findall(r"[a-zA-Z0-9_À-ÿ]+", text)
    return [t for t in tokens if len(t) > 1]


def score_item(query: str, item: dict) -> int:
    query_tokens = tokenize(query)
    haystacks = []

    haystacks.append(normalize(item["title"]))
    haystacks.extend([normalize(alias) for alias in item.get("aliases", [])])
    haystacks.extend([normalize(theme) for theme in item.get("themes", [])])
    haystacks.append(normalize(item.get("summary", "")))
    haystacks.append(normalize(item.get("area", "")))
    haystack = " ".join(haystacks)

    score = 0

    for token in query_tokens:
        if token in haystack:
            score += 2

    if normalize(query) in haystack:
        score += 5

    return score


def filter_catalog(
    query: str,
    area: Optional[str] = None,
    official_source: Optional[str] = None,
    act_type: Optional[str] = None,
    only_current: bool = True
) -> List[dict]:
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


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "api": "Legal Research API",
        "version": "3.0.0",
        "timestamp": now_iso()
    }


@app.get("/v1/sources")
def list_sources():
    return {
        "sources": OFFICIAL_SOURCES
    }


@app.get("/v1/areas")
def list_areas():
    return {
        "areas": LEGAL_AREAS
    }


@app.get("/v1/search")
def search_legal_content(
    q: str = Query(..., min_length=2, description="Consulta jurídica livre"),
    area: Optional[str] = Query(None, description="Área do direito"),
    source_type: Optional[str] = Query(None, description="Tipo de fonte"),
    official_source: Optional[str] = Query(None, description="Fonte oficial"),
    only_current: bool = Query(True, description="Retornar apenas conteúdo vigente"),
    limit: int = Query(5, ge=1, le=20, description="Quantidade de resultados")
):
    warnings = []

    if area and area not in LEGAL_AREAS:
        return {
            "query": q,
            "area": area,
            "source_type": source_type,
            "official_source": official_source,
            "only_current": only_current,
            "results": [],
            "warnings": [f"Área inválida: {area}"],
            "meta": {
                "limit": limit,
                "strategy_mode": True,
                "vigency_focus": True,
                "official_priority": True
            }
        }

    if source_type and source_type != "legislacao" and source_type != "fontes_oficiais":
        warnings.append("Nesta versão 3 real, a integração efetiva está focada em legislação federal oficial.")

    if official_source and official_source != "planalto":
        warnings.append("Nesta versão, a base real conectada está focada no Planalto como fonte oficial principal de legislação.")

    matches = filter_catalog(
        query=q,
        area=area,
        official_source="planalto" if official_source else None,
        act_type=None,
        only_current=only_current
    )[:limit]

    results = []
    for item in matches:
        results.append(
            {
                "title": item["title"],
                "source": item["official_source"],
                "source_type": "legislacao",
                "official_source": item["official_source"],
                "area": item["area"],
                "summary": item["summary"],
                "url": item["url"],
                "vigente": item["status"] == "vigente",
                "updated_at": now_iso()
            }
        )

    return {
        "query": q,
        "area": area,
        "source_type": source_type,
        "official_source": official_source,
        "only_current": only_current,
        "results": results,
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
    q: str = Query(..., min_length=2, description="Termo de busca legislativa"),
    area: Optional[str] = Query(None, description="Área do direito"),
    official_source: Optional[str] = Query(None, description="Fonte oficial"),
    act_type: Optional[str] = Query(None, description="Tipo de ato normativo"),
    only_current: bool = Query(True, description="Retornar apenas normas vigentes"),
    include_revoked: bool = Query(False, description="Incluir normas revogadas"),
    limit: int = Query(5, ge=1, le=20)
):
    warnings = []

    if area and area not in LEGAL_AREAS:
        return {
            "query": q,
            "area": area,
            "official_source": official_source,
            "act_type": act_type,
            "only_current": only_current,
            "include_revoked": include_revoked,
            "results": [],
            "warnings": [f"Área inválida: {area}"]
        }

    if official_source and official_source != "planalto":
        warnings.append("Nesta versão, a integração real de legislação está focada na fonte oficial Planalto.")

    matches = filter_catalog(
        query=q,
        area=area,
        official_source="planalto" if official_source else None,
        act_type=act_type,
        only_current=only_current
    )[:limit]

    results = []
    for item in matches:
        results.append(
            {
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
            }
        )

    if include_revoked:
        warnings.append("A base inicial atual está priorizando atos vigentes; conteúdo revogado ainda não foi modelado nesta fase.")

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
    q: str = Query(..., min_length=2, description="Consulta jurisprudencial"),
    area: Optional[str] = Query(None, description="Área do direito"),
    tribunal: Optional[str] = Query(None, description="Tribunal prioritário"),
    precedent_only: bool = Query(False, description="Priorizar precedentes"),
    limit: int = Query(5, ge=1, le=20)
):
    warnings = [
        "A jurisprudência oficial ainda está em fase de integração real nesta versão.",
        "Use esta rota como ponto de expansão para STF, STJ, CNJ e outros tribunais."
    ]

    base_results = [
        {
            "title": "Portal de Jurisprudência do STF",
            "tribunal": "stf",
            "class": "pesquisa_oficial",
            "case_number": "",
            "area": area,
            "summary": "Acesso ao portal oficial de jurisprudência do STF.",
            "precedent": precedent_only,
            "judgment_date": None,
            "url": "https://portal.stf.jus.br/jurisprudencia/"
        },
        {
            "title": "Pesquisa de Jurisprudência do STJ",
            "tribunal": "stj",
            "class": "pesquisa_oficial",
            "case_number": "",
            "area": area,
            "summary": "Acesso ao portal oficial de jurisprudência do STJ.",
            "precedent": precedent_only,
            "judgment_date": None,
            "url": "https://scon.stj.jus.br/SCON/"
        }
    ]

    return {
        "query": q,
        "area": area,
        "tribunal": tribunal,
        "precedent_only": precedent_only,
        "results": base_results[:limit],
        "warnings": warnings
    }
