from fastapi import FastAPI, Query
from typing import Optional, List
from datetime import datetime

app = FastAPI(
    title="Legal Research API",
    version="2.0.0",
    description="API jurídica para pesquisa estratégica em legislação, temas e fontes."
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
    "licitacoes_contratos"
]

LEGAL_SOURCES = [
    "legislacao",
    "jurisprudencia",
    "doutrina",
    "noticias_juridicas",
    "fontes_oficiais"
]


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "api": "Legal Research API",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@app.get("/v1/sources")
def list_sources():
    return {
        "sources": [
            {"id": "legislacao", "name": "Legislação"},
            {"id": "jurisprudencia", "name": "Jurisprudência"},
            {"id": "doutrina", "name": "Doutrina"},
            {"id": "noticias_juridicas", "name": "Notícias jurídicas"},
            {"id": "fontes_oficiais", "name": "Fontes oficiais"}
        ]
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
    limit: int = Query(5, ge=1, le=20, description="Quantidade de resultados")
):
    if area and area not in LEGAL_AREAS:
        return {
            "query": q,
            "area": area,
            "source_type": source_type,
            "results": [],
            "warnings": [f"Área inválida: {area}"],
            "suggested_areas": LEGAL_AREAS
        }

    if source_type and source_type not in LEGAL_SOURCES:
        return {
            "query": q,
            "area": area,
            "source_type": source_type,
            "results": [],
            "warnings": [f"Tipo de fonte inválido: {source_type}"],
            "suggested_source_types": LEGAL_SOURCES
        }

    results = []
    for i in range(limit):
        results.append(
            {
                "title": f"Resultado jurídico {i+1} para '{q}'",
                "source": source_type or "legislacao",
                "area": area or "geral",
                "summary": f"Resultado estruturado para a consulta '{q}', com foco em atuação estratégica.",
                "url": f"https://exemplo.com/resultado/{i+1}",
                "vigente": True,
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }
        )

    return {
        "query": q,
        "area": area,
        "source_type": source_type,
        "results": results,
        "warnings": [],
        "meta": {
            "limit": limit,
            "strategy_mode": True,
            "vigency_focus": True
        }
    }


@app.get("/v1/legislation")
def search_legislation(
    q: str = Query(..., min_length=2, description="Termo de busca legislativa"),
    area: Optional[str] = Query(None, description="Área do direito"),
    only_current: bool = Query(True, description="Retornar apenas conteúdo vigente"),
    limit: int = Query(5, ge=1, le=20)
):
    results = []
    for i in range(limit):
        results.append(
            {
                "title": f"Norma relacionada a '{q}'",
                "type": "lei",
                "number": f"10{i+1}/2025",
                "area": area or "geral",
                "status": "vigente" if only_current else "vigente/outras",
                "summary": f"Resultado legislativo estruturado sobre '{q}'.",
                "url": f"https://exemplo.com/legislacao/{i+1}",
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }
        )

    return {
        "query": q,
        "area": area,
        "only_current": only_current,
        "results": results,
        "warnings": []
    }
