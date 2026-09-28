"""
Clasificador basado en LLM (Google Gemini API — free tier).
Usa prompt estructurado con la taxonomía Moon et al. (2022) adaptada.
"""

import json
import os
import time
from dataclasses import dataclass

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


SYSTEM_PROMPT = """Eres un experto en análisis de contratos de obra pública y proveeduría en Colombia.
Tu tarea es clasificar cláusulas contractuales según la siguiente taxonomía de riesgo (adaptada de Moon, Chi & Im, 2022):

Categorías:
- pago: condiciones de pago, precios, retenciones, ajustes
- tiempo: plazos, penalidades por retraso, prórrogas
- procedimiento: modificaciones, terminación, cesión, subcontratación, reclamaciones
- seguridad: seguros, garantías, seguridad social, confidencialidad
- roles_y_responsabilidades: indemnizaciones, responsabilidades, obligaciones de las partes
- definicion_y_referencia: definiciones contractuales, referencias a anexos

Responde ÚNICAMENTE con un JSON con esta estructura exacta (sin markdown, sin bloques de código):
{"categoria": "<una de las seis categorías>", "es_riesgo": <true o false>, "razon": "<máximo 20 palabras>"}

Una cláusula ES de riesgo si contiene: penalidades desproporcionadas, transferencia unilateral de responsabilidad,
terminación sin indemnización, precios fijos sin ajuste, retenciones prolongadas, obligaciones ilimitadas,
renuncia a derechos, o condiciones que favorecen desproporcionadamente a una parte."""

USER_PROMPT_TEMPLATE = 'Clasifica esta cláusula contractual:\n\n"{texto}"'


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


def classify_clausula_llm(clausula: dict, client=None, model: str = "gemini-3.8-flash") -> LLMResult:
    if not GEMINI_AVAILABLE or client is None:
        return LLMResult(
            id=clausula["id"], texto=clausula["texto"],
            categoria_predicha="", es_riesgo_predicho=False,
            categoria_real=clausula["categoria"], es_riesgo_real=clausula["es_riesgo"],
            razon="", tokens_usados=0, error="Gemini client no disponible",
        )

    try:
        prompt = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT_TEMPLATE.format(texto=clausula['texto'])}"
        for attempt in range(4):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0),
                )
                break
            except Exception as e:
                if attempt == 3:
                    raise
                wait = 15 * (attempt + 1)
                print(f"  [{clausula['id']}] reintento {attempt+1}/3 en {wait}s ({e})")
                time.sleep(wait)
        raw = response.text.strip()
        # Limpiar posibles bloques markdown que el modelo agregue
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        tokens = response.usage_metadata.total_token_count if response.usage_metadata else 0
        return LLMResult(
            id=clausula["id"], texto=clausula["texto"],
            categoria_predicha=parsed.get("categoria", ""),
            es_riesgo_predicho=bool(parsed.get("es_riesgo", False)),
            categoria_real=clausula["categoria"], es_riesgo_real=clausula["es_riesgo"],
            razon=parsed.get("razon", ""), tokens_usados=tokens,
        )
    except Exception as e:
        return LLMResult(
            id=clausula["id"], texto=clausula["texto"],
            categoria_predicha="", es_riesgo_predicho=False,
            categoria_real=clausula["categoria"], es_riesgo_real=clausula["es_riesgo"],
            razon="", tokens_usados=0, error=str(e),
        )


def get_client(api_key: str | None = None):
    if not GEMINI_AVAILABLE:
        return None
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    return genai.Client(api_key=key)
