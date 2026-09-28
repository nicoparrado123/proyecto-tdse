"""
Pruebas de los 4 endpoints de la API.
Requiere: py -m uvicorn src.api.main:app --reload (en otra terminal)
"""

from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from api.main import app

client = TestClient(app)
HEADERS = {"X-Tenant-ID": "tenant-demo"}
HEADERS_INVALIDO = {"X-Tenant-ID": "tenant-desconocido"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_classify_riesgo():
    r = client.post("/v1/clausulas/classify", headers=HEADERS, json={
        "id": "T01",
        "texto": "El contratista pagará una penalidad del 1% por cada día de retraso sin límite máximo.",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["es_riesgo_predicho"] is True
    assert data["tenant_id"] == "tenant-demo"
    assert len(data["patrones_activados"]) > 0


def test_classify_no_riesgo():
    r = client.post("/v1/clausulas/classify", headers=HEADERS, json={
        "id": "T02",
        "texto": "El pago se realizará a 30 días calendario desde la radicación de la factura.",
    })
    assert r.status_code == 200
    assert r.json()["es_riesgo_predicho"] is False


def test_classify_tenant_invalido():
    r = client.post("/v1/clausulas/classify", headers=HEADERS_INVALIDO, json={
        "id": "T03",
        "texto": "Cualquier texto.",
    })
    assert r.status_code == 403


def test_analyze_contrato():
    r = client.post("/v1/contratos/analyze", headers=HEADERS, json={
        "contract_id": "C-TEST",
        "clausulas": [
            {"id": "T04", "texto": "El contratante podrá terminar unilateralmente sin expresión de causa."},
            {"id": "T05", "texto": "El plazo del contrato es de 6 meses prorrogables de mutuo acuerdo."},
            {"id": "T06", "texto": "El contratista asumirá responsabilidad exclusiva e integral por daños a terceros."},
        ]
    })
    assert r.status_code == 200
    data = r.json()
    assert data["total_clausulas"] == 3
    assert data["clausulas_riesgo"] >= 2
    assert data["tenant_id"] == "tenant-demo"


def test_reporte_sin_analisis_previo():
    r = client.get("/v1/contratos/INEXISTENTE/reporte", headers=HEADERS)
    assert r.status_code == 404


def test_reporte_tras_analisis():
    # Primero analiza
    client.post("/v1/contratos/analyze", headers=HEADERS, json={
        "contract_id": "C-REPORTE",
        "clausulas": [
            {"id": "T07", "texto": "Los precios son fijos e invariables sin ajuste por inflación."},
            {"id": "T08", "texto": "Para efectos de este contrato, día hábil significa lunes a viernes."},
        ]
    })
    # Luego pide el reporte
    r = client.get("/v1/contratos/C-REPORTE/reporte", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total_clausulas"] == 2
    assert data["porcentaje_riesgo"] >= 0
    niveles = [s["nivel"] for s in data["semaforo"]]
    assert all(n in ("ALTO", "BAJO") for n in niveles)


def test_aislamiento_tenant():
    """Tenant-test no puede ver contratos de tenant-demo."""
    client.post("/v1/contratos/analyze", headers=HEADERS, json={
        "contract_id": "C-PRIVADO",
        "clausulas": [{"id": "T09", "texto": "Cláusula de prueba."}]
    })
    r = client.get("/v1/contratos/C-PRIVADO/reporte", headers={"X-Tenant-ID": "tenant-test"})
    assert r.status_code == 404


if __name__ == "__main__":
    tests = [
        test_health,
        test_classify_riesgo,
        test_classify_no_riesgo,
        test_classify_tenant_invalido,
        test_analyze_contrato,
        test_reporte_sin_analisis_previo,
        test_reporte_tras_analisis,
        test_aislamiento_tenant,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} pruebas pasaron")
