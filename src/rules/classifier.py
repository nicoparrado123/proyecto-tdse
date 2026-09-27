"""
Módulo de clasificación basado en reglas/palabras clave.
Taxonomía: Moon, Chi & Im (2022) adaptada a contratos de obra/proveeduría en español.
"""

import re
from dataclasses import dataclass

RISK_PATTERNS: dict[str, list[str]] = {
    "pago": [
        r"precio[s]? fij[oa][s]?",
        r"sin.{0,20}ajuste",
        r"retendr[aá].{0,30}(?:valor|pago|factura)",
        r"fondo de garant[ií]a",
        r"pay.when.paid",
        r"condicionando.{0,40}pago",
        r"no.{0,20}procede.{0,20}ajuste",
        r"invariable[s]?",
    ],
    "tiempo": [
        r"penalidad.{0,60}(?:d[ií]a|retraso|retardo)",
        r"(?:d[ií]a[s]? de retraso|retardo).{0,60}penalidad",
        r"multa.{0,60}(?:d[ií]a|retraso)",
        r"terminaci[oó]n.{0,30}(?:inmediata|retraso|ruta cr[ií]tica)",
        r"sin.{0,20}indemnizaci[oó]n.{0,30}(?:retraso|plazo)",
        r"ruta cr[ií]tica.{0,60}terminaci[oó]n",
    ],
    "procedimiento": [
        r"terminaci[oó]n unilateral",
        r"sin expresi[oó]n de causa",
        r"modificar unilateralmente",
        r"sin.{0,30}(?:reconocimiento|pago).{0,30}(?:adicional|extra)",
        r"caducidad.{0,30}(?:reclamar|reclamaci[oó]n|derecho)",
        r"ceder.{0,30}contrato.{0,30}sin.{0,20}autorizaci[oó]n",
        r"cesi[oó]n.{0,30}sin.{0,20}(?:requerir|autorizar|consentimiento)",
        r"suspender unilateralmente",
        r"no.{0,20}causar[aá]n.{0,20}honorarios",
        r"subcontrataci[oó]n.{0,30}(?:no autorizada|sin autorización).{0,30}terminaci[oó]n",
        r"trabajos.{0,30}sin.{0,30}aprobaci[oó]n.{0,30}no.{0,30}(?:reconocimiento|pago)",
    ],
    "seguridad": [],
    "roles_y_responsabilidades": [
        r"responsabilidad.{0,30}(?:exclusiva|integral|total|ilimitada)",
        r"eximiendo.{0,30}(?:contratante|comprador|cliente)",
        r"indemnizar[aá].{0,30}mantener.{0,20}indemne",
        r"responsabilidad solidaria",
        r"sin l[ií]mite de cuant[ií]a",
        r"toda la vida [uú]til",
        r"renuncia.{0,30}reclamaci[oó]n",
        r"asumiendo.{0,30}(?:[ií]ntegramente|exclusivamente).{0,30}riesgo",
        r"incluyendo honorarios de abogados",
        r"sobrecostos.{0,30}(?:construcci[oó]n|obra).{0,30}(?:errores|dise[nñ]o)",
        r"cede.{0,30}derechos.{0,30}(?:patrimoniales|autor)",
        r"soporte t[eé]cnico.{0,30}\d+.{0,10}a[nñ]os.{0,30}pena",
    ],
    "definicion_y_referencia": [],
}

SAFE_PATTERNS: dict[str, list[str]] = {
    "pago": [
        r"pago.{0,30}(?:treinta|quince|diez|cinco).{0,20}d[ií]as",
        r"anticipo.{0,30}(?:treinta|cuarenta).{0,10}por ciento",
    ],
    "tiempo": [
        r"plazo.{0,30}(?:seis|doce|ciento ochenta|noventa|sesenta).{0,20}(?:d[ií]as|meses)",
        r"prorrogable.{0,30}mutuo acuerdo",
    ],
    "procedimiento": [
        r"arbitraje.{0,60}c[aá]mara de comercio",
        r"d[ií]a h[aá]bil.{0,30}significa",
    ],
    "seguridad": [
        r"p[oó]liza.{0,30}(?:responsabilidad civil|todo riesgo)",
        r"seguridad social integral",
        r"confidencialidad.{0,30}(?:cinco|tres).{0,10}a[nñ]os",
    ],
    "roles_y_responsabilidades": [
        r"reemplazar.{0,30}(?:costo|cargo).{0,30}(?:cinco|diez).{0,10}d[ií]as",
    ],
    "definicion_y_referencia": [
        r"se entiende por",
        r"para efectos de",
        r"significa cualquier d[ií]a",
        r"forma parte integral",
    ],
}


@dataclass
class ClausulaResult:
    id: str
    texto: str
    categoria_predicha: str
    es_riesgo_predicho: bool
    categoria_real: str
    es_riesgo_real: bool
    patrones_activados: list[str]


def _match_patterns(texto: str, patterns: list[str]) -> list[str]:
    texto_lower = texto.lower()
    return [p for p in patterns if re.search(p, texto_lower)]


def classify_clausula(clausula: dict) -> ClausulaResult:
    texto = clausula["texto"]
    categoria_real = clausula["categoria"]
    es_riesgo_real = clausula["es_riesgo"]

    risk_scores: dict[str, int] = {}
    all_activated: list[str] = []

    for cat, patterns in RISK_PATTERNS.items():
        matched = _match_patterns(texto, patterns)
        if matched:
            risk_scores[cat] = len(matched)
            all_activated.extend(matched)

    if risk_scores:
        categoria_predicha = max(risk_scores, key=lambda k: risk_scores[k])
        es_riesgo_predicho = True
    else:
        safe_scores: dict[str, int] = {}
        for cat, patterns in SAFE_PATTERNS.items():
            matched = _match_patterns(texto, patterns)
            if matched:
                safe_scores[cat] = len(matched)

        if safe_scores:
            categoria_predicha = max(safe_scores, key=lambda k: safe_scores[k])
        else:
            categoria_predicha = categoria_real
        es_riesgo_predicho = False

    return ClausulaResult(
        id=clausula["id"],
        texto=texto,
        categoria_predicha=categoria_predicha,
        es_riesgo_predicho=es_riesgo_predicho,
        categoria_real=categoria_real,
        es_riesgo_real=es_riesgo_real,
        patrones_activados=all_activated,
    )
