# Detección de cláusulas de riesgo en contratos — TDSE

**Equipo:** Nicolás Andrés Parrado Gonzales · Santiago Andrés García · Sebastián Duque

## Qué hace este proyecto

Servicio de revisión contractual para PyMEs de obra pública y proveeduría en Colombia. Detecta cláusulas de riesgo (penalidades, responsabilidades, terminación unilateral, precios fijos, etc.) usando un clasificador de reglas y/o un LLM, comparando ambos enfoques sobre un corpus sintético en español.

## Resultados del prototipo (Advance 2)

Corpus: 40 cláusulas, 5 contratos, 23 de riesgo / 17 no-riesgo.

| Método | Precision | Recall | F1 |
|---|---|---|---|
| Reglas (baseline) | **1.0000** | 0.6522 | 0.7895 |
| LLM (hipótesis) | ≥ 0.90 | ≥ 0.85 | ≥ 0.87 |

El baseline tiene precision perfecta (0 falsas alarmas) pero pierde 8 de 23 cláusulas de riesgo por variación semántica en la redacción.

## Estructura

```
corpus/          → corpus sintético etiquetado (JSON)
src/rules/       → clasificador de reglas (regex, sin dependencias externas)
src/llm/         → clasificador LLM (OpenAI API)
src/evaluation/  → comparación reglas vs. LLM con métricas
src/api/         → API REST FastAPI (multi-tenant)
results/         → resultados de evaluación
docs/advance2.md → arquitectura completa (Advance 2)
```

## Ejecución rápida

```bash
py -m pip install -r requirements.txt
py src/evaluation/evaluate.py                    # solo reglas
py src/evaluation/evaluate.py --llm              # reglas + LLM (requiere OPENAI_API_KEY)
py -m uvicorn src.api.main:app --reload          # API en localhost:8000
```

## Documentación

Ver [`docs/advance2.md`](docs/advance2.md) para la arquitectura completa del Advance 2:
enterprise architecture, data architecture, application architecture, technology stack,
intelligent component design, API design, cloud deployment, quality attributes,
security design, roadmap y governance model.
