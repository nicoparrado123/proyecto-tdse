"""
Clasificador basado en LLM (OpenAI-compatible API).
Usa prompt estructurado con la taxonomía Moon et al. (2022) adaptada.
"""

import json
import os
import time
from dataclasses import dataclass

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


SYSTEM_PROMPT = """Eres un experto en análisis de contratos de obra pública y proveeduría en Colombia.
Tu tarea es clasificar cláusulas contractuales según la siguiente taxonomía de riesgo (adaptada de Moon, Chi & Im, 2022):

Categorías:
- pago: condiciones de pago, precios, retenciones, ajustes
- tiempo: plazos, penalidades por retraso, prórrogas
- procedimiento: modificaciones, terminación, cesión, subcontratación, reclamaciones
- seguridad: seguros, garantías, seguridad social, confidencialidad
- roles_y_responsabilidades: indemnizaciones, responsabilidades, obligaciones de las partes
- definicion_y_referencia: definiciones contractuales, referencias a anexos

Responde ÚNICAMENTE con un JSON con esta estructura exacta:
{
  "categoria": "<una de las seis categorías>",
  "es_riesgo": <true o false>,
  "razon": "<explicación breve en máximo 20 palabras>"
}

Una cláusula ES de riesgo si contiene: penalidades desproporcionadas, transferencia unilateral de responsabilidad,
terminación sin indemnización, precios fijos sin ajuste, retenciones prolongadas, obligaciones ilimitadas,
renuncia a derechos, o condiciones que favorecen desproporcionadamente a una parte."""

USER_PROMPT_TEMPLATE = """Clasifica esta cláusula contractual:

"{texto}"
"""


@dataclass
class LLMResult:
    id: str
    texto: str
    categoria_predicha: str
    es_riesgo_predicho: bool
    categoria_real: str
    es_riesgo_real: bool
    razon: str
    tokens_usados: int
    error: str | None = None


def classify_clausula_llm(clausula: dict, client=None, model: str = "gpt-4o-mini") -> LLMResult:
    if not OPENAI_AVAILABLE or client is None:
        return LLMResult(
            id=clausula["id"],
            texto=clausula["texto"],
            categoria_predicha="",
            es_riesgo_predicho=False,
            categoria_real=clausula["categoria"],
            es_riesgo_real=clausula["es_riesgo"],
            razon="",
            tokens_usados=0,
            error="OpenAI client no disponible",
        )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(texto=clausula["texto"])},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)
        return LLMResult(
            id=clausula["id"],
            texto=clausula["texto"],
            categoria_predicha=parsed.get("categoria", ""),
            es_riesgo_predicho=parsed.get("es_riesgo", False),
            categoria_real=clausula["categoria"],
            es_riesgo_real=clausula["es_riesgo"],
            razon=parsed.get("razon", ""),
            tokens_usados=response.usage.total_tokens,
        )
    except Exception as e:
        return LLMResult(
            id=clausula["id"],
            texto=clausula["texto"],
            categoria_predicha="",
            es_riesgo_predicho=False,
            categoria_real=clausula["categoria"],
            es_riesgo_real=clausula["es_riesgo"],
            razon="",
            tokens_usados=0,
            error=str(e),
        )


def get_client(api_key: str | None = None) -> "OpenAI | None":
    if not OPENAI_AVAILABLE:
        return None
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAI(api_key=key)
