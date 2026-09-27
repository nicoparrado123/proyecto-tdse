"""
API REST del servicio de detección de cláusulas de riesgo.
FastAPI — diseño multi-tenant con tenant_id en header.

Estado de implementación (Advance 2):
  IMPLEMENTADO:  /health, /v1/clausulas/classify, /v1/contratos/analyze
  STUB:          /v1/contratos/{id}/reporte  — estructura target implementada,
                 persistencia en memoria (no PostgreSQL). Ver nota en respuesta.
  DISEÑO TARGET: autenticación JWT, RLS PostgreSQL, cifrado KMS — documentados
                 en docs/advance2.md sección 9. No implementados en este prototipo;
                 la validación de tenant usa header directo (X-Tenant-ID).
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rules.classifier import classify_clausula

app = FastAPI(
    title="TDSE Risk Clause Detector",
    description="Detección de cláusulas de riesgo en contratos de obra/proveeduría (Colombia)",
    version="0.1.0",
)

# Prototipo: validación de tenant por header directo.
# Diseño target (Advance 3): JWT con claims de tenant + RLS en PostgreSQL.
VALID_TENANTS = {"tenant-demo", "tenant-test"}

# Caché en memoria para el stub de reporte (reemplazar por PostgreSQL en Advance 3)
_cache_contratos: dict[str, dict] = {}


class ClausulaRequest(BaseModel):
    id: str
    texto: str
    categoria: str = "desconocida"
    es_riesgo: bool = False


class ClausulaResponse(BaseModel):
    id: str
    categoria_predicha: str
    es_riesgo_predicho: bool
    patrones_activados: list[str]
    tenant_id: str


class ContractRequest(BaseModel):
    contract_id: str
    clausulas: list[ClausulaRequest]


class ContractResponse(BaseModel):
    contract_id: str
    tenant_id: str
    total_clausulas: int
    clausulas_riesgo: int
    resultados: list[ClausulaResponse]


class ClausulaSemaforo(BaseModel):
    id: str
    categoria: str
    es_riesgo: bool
    nivel: str          # "ALTO" | "BAJO"
    patrones: list[str]


class ReporteResponse(BaseModel):
    contract_id: str
    tenant_id: str
    total_clausulas: int
    clausulas_riesgo: int
    porcentaje_riesgo: float
    semaforo: list[ClausulaSemaforo]
    nota: str


def get_tenant(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    if x_tenant_id not in VALID_TENANTS:
        raise HTTPException(status_code=403, detail=f"Tenant '{x_tenant_id}' no autorizado")
    return x_tenant_id


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/v1/clausulas/classify", response_model=ClausulaResponse)
def classify_single(req: ClausulaRequest, tenant_id: str = Depends(get_tenant)):
    result = classify_clausula(req.model_dump())
    return ClausulaResponse(
        id=result.id,
        categoria_predicha=result.categoria_predicha,
        es_riesgo_predicho=result.es_riesgo_predicho,
        patrones_activados=result.patrones_activados,
        tenant_id=tenant_id,
    )


@app.post("/v1/contratos/analyze", response_model=ContractResponse)
def analyze_contract(req: ContractRequest, tenant_id: str = Depends(get_tenant)):
    resultados = []
    for c in req.clausulas:
        result = classify_clausula(c.model_dump())
        resultados.append(ClausulaResponse(
            id=result.id,
            categoria_predicha=result.categoria_predicha,
            es_riesgo_predicho=result.es_riesgo_predicho,
            patrones_activados=result.patrones_activados,
            tenant_id=tenant_id,
        ))
    clausulas_riesgo = sum(1 for r in resultados if r.es_riesgo_predicho)
    resp = ContractResponse(
        contract_id=req.contract_id,
        tenant_id=tenant_id,
        total_clausulas=len(resultados),
        clausulas_riesgo=clausulas_riesgo,
        resultados=resultados,
    )
    # Guardar en caché para el endpoint de reporte
    _cache_contratos[f"{tenant_id}:{req.contract_id}"] = resp.model_dump()
    return resp


@app.get("/v1/contratos/{contract_id}/reporte", response_model=ReporteResponse)
def get_reporte(contract_id: str, tenant_id: str = Depends(get_tenant)):
    """
    [STUB — Advance 2] Reporte de riesgo del contrato analizado.
    Diseño target: lee de PostgreSQL con RLS por tenant_id.
    Prototipo: usa caché en memoria; requiere haber llamado POST /v1/contratos/analyze antes.
    """
    key = f"{tenant_id}:{contract_id}"
    cached = _cache_contratos.get(key)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="Contrato no encontrado. Llame primero a POST /v1/contratos/analyze.",
        )
    semaforo = [
        ClausulaSemaforo(
            id=r["id"],
            categoria=r["categoria_predicha"],
            es_riesgo=r["es_riesgo_predicho"],
            nivel="ALTO" if r["es_riesgo_predicho"] else "BAJO",
            patrones=r["patrones_activados"],
        )
        for r in cached["resultados"]
    ]
    pct = round(cached["clausulas_riesgo"] / cached["total_clausulas"] * 100, 1) if cached["total_clausulas"] else 0.0
    return ReporteResponse(
        contract_id=contract_id,
        tenant_id=tenant_id,
        total_clausulas=cached["total_clausulas"],
        clausulas_riesgo=cached["clausulas_riesgo"],
        porcentaje_riesgo=pct,
        semaforo=semaforo,
        nota="[STUB] Persistencia en memoria. Diseño target: PostgreSQL con RLS por tenant_id.",
    )
