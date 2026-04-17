from fastapi import FastAPI, Query
from typing import Optional

app = FastAPI(
    title="Legal Research API",
    version="1.0.0"
)

@app.get("/")
def root():
    return {
        "name": "Legal Research API",
        "version": "1.0.0",
        "status": "ok",
        "endpoints": ["/health", "/v1/search"]
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/v1/search")
def search_legal_content(
    q: str = Query(..., min_length=2, description="Consulta jurídica livre"),
    area: Optional[str] = Query(None, description="Área do direito"),
):
    return {
        "query": q,
        "area": area,
        "results": [
            {
                "title": f"Resultado jurídico para: {q}",
                "source": "fonte_interna",
                "summary": f"Esta é uma resposta de teste para a consulta '{q}'.",
                "url": "https://exemplo.com/resultado"
            }
        ],
        "warnings": []
    }
