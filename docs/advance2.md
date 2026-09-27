# Advance 2 — Architecture, Roadmap and Governance
## Detección de cláusulas de riesgo en contratos mediante NLP
**Equipo:** Nicolás Andrés Parrado Gonzales · Santiago Andrés García · Sebastián Duque  
**Curso:** TDSE — Prof. Luis Daniel Benavides — Escuela Colombiana de Ingeniería Julio Garavito  
**Pregunta central:** ¿Qué tan bien detecta cláusulas de riesgo un enfoque de reglas vs. un LLM, sobre el mismo corpus de contratos de obra/proveeduría en español?

---

## 12. Prototype Evidence (se presenta primero porque condiciona el resto)

### Corpus sintético

- **40 cláusulas** distribuidas en 5 contratos: obra pública, orden de compra, subcontrato, suministro de equipos, consultoría técnica.
- **23 cláusulas de riesgo** (57.5%) y **17 no-riesgo** (42.5%).
- Taxonomía Moon, Chi & Im (2022) adaptada: 7 categorías → pago, tiempo, procedimiento, seguridad, roles_y_responsabilidades, definicion_y_referencia (+ cambios de alcance absorbidos en procedimiento).
- Fuente: plantillas reales de minutas de subcontratación y órdenes de compra colombianas, anonimizadas, con cláusulas de riesgo insertadas deliberadamente.
- Archivo: `corpus/synthetic_contracts.json`

### Resultados del baseline de reglas (ejecutado sobre el corpus real)

| Métrica | Valor |
|---|---|
| Precision (detección de riesgo) | **1.0000** |
| Recall (detección de riesgo) | **0.6522** |
| F1 (detección de riesgo) | **0.7895** |
| Accuracy clasificación de riesgo | **0.8000** |
| Accuracy categoría | **0.9500** |
| TP / FP / TN / FN | 15 / 0 / 17 / 8 |

**Por categoría:**

| Categoría | Precision | Recall | F1 |
|---|---|---|---|
| pago | 1.0 | 1.0 | **1.0** |
| roles_y_responsabilidades | 1.0 | 0.667 | 0.800 |
| procedimiento | 1.0 | 0.625 | 0.769 |
| tiempo | 1.0 | 0.333 | 0.500 |
| seguridad | 0.0 | 0.0 | 0.0 |
| definicion_y_referencia | 0.0 | 0.0 | 0.0 |

> Nota: seguridad y definicion_y_referencia tienen F1=0 en detección de riesgo porque en el corpus ninguna cláusula de esas categorías es de riesgo — el clasificador las predice correctamente como no-riesgo, pero las métricas de riesgo no aplican. La accuracy de categoría (0.95) sí las incluye.

**Análisis de falsos negativos (8 FN):**
- C001-01: penalidad por retraso expresada con palabras distintas al patrón (`"cero punto cinco por ciento"` en lugar de `"penalidad"` explícita).
- C001-07: cambio de alcance sin reconocimiento — el patrón no capturó la negación implícita.
- C002-01: costos de reemplazo + desmontaje — riesgo por acumulación de obligaciones, no por una frase clave.
- C002-06: penalidad del 1% diaria — el patrón de tiempo no capturó esta variante.
- C003-05: trabajos adicionales obligatorios a precio fijo — riesgo semántico sin keyword directa.
- C003-06: responsabilidad solidaria — el patrón existe pero no matcheó por variación de redacción.
- C004-04: soporte 10 años con penalidad — el patrón de soporte técnico no matcheó por orden de palabras.
- C004-08: cesión unilateral — el patrón de cesión no capturó la variante `"ceder el presente contrato"`.

**Conclusión del prototipo:** el baseline de reglas tiene precision perfecta (0 falsos positivos) pero recall limitado (0.65). Los 8 FN son todos casos donde el riesgo es semántico o la redacción varía del patrón esperado — exactamente el tipo de caso donde un LLM debería superar a las reglas. Esto justifica la hipótesis de investigación y el diseño del componente inteligente.

---

## 1. Enterprise Architecture

**Problema de negocio → capacidad de negocio:**

```
PyME firma contrato
       ↓
[Ingestión] PDF/Word → texto por cláusula
       ↓
[Clasificación] reglas / LLM → etiqueta de riesgo por cláusula
       ↓
[Reporte] semáforo de riesgo comprensible para gerente de proyecto
       ↓
PyME negocia o rechaza cláusulas antes de firmar
```

**Capacidades de negocio habilitadas:**
1. Revisión contractual sin abogado interno — reduce tiempo de revisión de días a minutos.
2. Estandarización del criterio de riesgo — misma taxonomía para todos los contratos de la organización.
3. Trazabilidad — registro de qué cláusulas fueron marcadas, cuándo y por qué método.

**Modelo de negocio:** SaaS multi-tenant. Cada PyME es un tenant. Precio por contrato analizado o suscripción mensual por volumen. No compite con CLMs enterprise (sin firma electrónica, sin flujos de aprobación).

**Stakeholders:**
- Gerente de proyecto PyME: consume el reporte de riesgo.
- Administrador de la organización: gestiona usuarios y contratos del tenant.
- Operador del servicio (equipo TDSE): mantiene el modelo y la plataforma.

---

## 2. Data Architecture

### Modelo de datos

```
Tenant
  ├── id (UUID)
  ├── nombre
  ├── plan (free | pro)
  └── created_at

Contrato
  ├── id (UUID)
  ├── tenant_id → Tenant.id
  ├── nombre_archivo
  ├── hash_sha256 (integridad)
  ├── texto_extraido (cifrado en reposo)
  ├── estado (pendiente | procesado | error)
  └── created_at

Clausula
  ├── id (UUID)
  ├── contrato_id → Contrato.id
  ├── tenant_id → Tenant.id  ← desnormalizado para RLS
  ├── texto (cifrado en reposo)
  ├── categoria
  ├── es_riesgo (bool)
  ├── metodo (rules | llm)
  ├── confianza (float)
  ├── patrones_activados (JSON)
  └── created_at

AuditLog
  ├── id
  ├── tenant_id
  ├── usuario_id
  ├── accion (upload | analyze | export)
  ├── contrato_id
  └── timestamp
```

### Aislamiento multi-tenant a nivel de datos

- **Row-Level Security (RLS)** en PostgreSQL: cada query lleva `WHERE tenant_id = :current_tenant`.
- **Cifrado en reposo**: columnas `texto_extraido` y `texto` de cláusula cifradas con AES-256 usando clave por tenant (AWS KMS, una CMK por tenant en plan pro).
- **Almacenamiento de archivos**: S3 con prefijo `s3://bucket/{tenant_id}/contratos/{contrato_id}.pdf`. Bucket policy niega acceso cross-tenant.
- **Corpus de entrenamiento/evaluación**: almacenado en bucket separado, sin datos de producción, acceso solo al equipo operador.

### Política de datos sensibles

El texto de los contratos **no se envía a APIs de terceros** en el modo `rules`. En el modo `llm`, el texto se envía a la API de OpenAI solo si el tenant ha aceptado explícitamente la política de datos y tiene plan pro. En plan free, solo se usa el clasificador de reglas local.

---

## 3. Application Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Cliente (Web/API)                  │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS + JWT + X-Tenant-ID
┌──────────────────────▼──────────────────────────────┐
│                  API Gateway (FastAPI)                │
│  POST /v1/contratos/analyze                          │
│  POST /v1/clausulas/classify                         │
│  GET  /v1/contratos/{id}/reporte                     │
└──────┬───────────────┬──────────────────────────────┘
       │               │
┌──────▼──────┐  ┌─────▼──────────────────────────────┐
│  Ingestión  │  │         Clasificación               │
│  PDF→texto  │  │  ┌──────────┐   ┌────────────────┐  │
│  (pdfminer) │  │  │  Reglas  │   │  LLM (OpenAI)  │  │
└──────┬──────┘  │  │ local    │   │  solo plan pro │  │
       │         │  └──────────┘   └────────────────┘  │
       │         └─────┬──────────────────────────────┘
       │               │
┌──────▼───────────────▼──────────────────────────────┐
│              Capa de datos (PostgreSQL + S3)          │
│  RLS por tenant_id · Cifrado AES-256 · Audit log     │
└─────────────────────────────────────────────────────┘
```

**Flujo de una solicitud de análisis:**
1. Cliente sube PDF → API extrae texto por cláusula (heurística: separación por numeración o saltos dobles).
2. API persiste el contrato cifrado en S3 y el registro en PostgreSQL.
3. Para cada cláusula: si tenant es free → clasificador de reglas local; si es pro y aceptó política → LLM.
4. Resultados persistidos en tabla `Clausula`.
5. API retorna reporte con semáforo de riesgo por cláusula.

---

## 4. Technology Architecture

| Capa | Tecnología | Justificación |
|---|---|---|
| API | FastAPI (Python 3.13) | Async, tipado, OpenAPI automático |
| Clasificador reglas | Python stdlib (re) | Sin dependencias externas, ejecutable offline |
| Clasificador LLM | OpenAI API (gpt-4o-mini) | Menor costo, suficiente para clasificación binaria |
| Ingestión PDF | pdfminer.six | Open source, sin llamadas externas |
| Base de datos | PostgreSQL 16 (AWS RDS) | RLS nativo, ACID, extensión pgcrypto |
| Almacenamiento | AWS S3 | Prefijos por tenant, bucket policies, versionado |
| Cifrado de claves | AWS KMS | CMK por tenant en plan pro |
| Contenedor | Docker + AWS ECS Fargate | Sin gestión de servidores |
| CI/CD | GitHub Actions | Build → test → deploy a ECS |
| Monitoreo | AWS CloudWatch | Logs, métricas, alertas |
| Nube | AWS (región us-east-1) | Disponibilidad, servicios gestionados, costo |

**Nube elegida: AWS.** Justificación: RDS con RLS, KMS para cifrado por tenant, S3 con bucket policies, ECS Fargate para contenedores sin servidor, todo integrado con IAM. Alternativa GCP descartada por menor familiaridad del equipo con Cloud SQL y KMS equivalente.

---

## 5. Intelligent Component Design

### Decisión de diseño basada en evidencia del prototipo

El prototipo muestra que el clasificador de reglas tiene **precision = 1.0** (nunca genera falsas alarmas) pero **recall = 0.65** (pierde 8 de 23 cláusulas de riesgo). Los 8 falsos negativos son todos casos de riesgo semántico o variación de redacción — exactamente donde un LLM debería superar a las reglas.

**Hipótesis a validar en Advance 3:** el LLM alcanzará recall ≥ 0.85 con precision ≥ 0.90, superando el F1 de 0.79 del baseline de reglas.

### Arquitectura del componente

```
Texto de cláusula
       │
       ▼
┌─────────────────┐
│ Clasificador    │  → siempre disponible, sin costo, sin datos externos
│ de Reglas       │  → precision 1.0, recall 0.65, F1 0.79
└────────┬────────┘
         │ si tenant=pro AND política aceptada AND confianza_reglas < umbral
         ▼
┌─────────────────┐
│ Clasificador    │  → gpt-4o-mini, prompt estructurado con taxonomía
│ LLM             │  → hipótesis: recall ≥ 0.85, F1 ≥ 0.87
└────────┬────────┘
         │
         ▼
  Resultado final + método usado + confianza
```

**Modo de operación:**
- `rules_only`: plan free, o cuando el tenant no ha aceptado política de datos externos.
- `llm_only`: experimental, para comparación en investigación.
- `hybrid`: reglas primero; si no hay match y el texto supera umbral de longitud, escala a LLM.

**Prompt del LLM:** ver `src/llm/classifier.py`. Incluye la taxonomía completa, ejemplos de qué constituye riesgo, y fuerza respuesta JSON estructurada con `temperatura=0` para reproducibilidad.

### Limitaciones conocidas del baseline de reglas

1. No captura riesgo por acumulación de obligaciones (C002-01: reemplazo + desmontaje + transporte).
2. No captura negación implícita (C001-07: "no tendrá derecho" sin keyword de riesgo directa).
3. Sensible al orden de palabras en patrones de más de 2 tokens.
4. Categorías `seguridad` y `definicion_y_referencia` no tienen patrones de riesgo (F1=0 en esas categorías para riesgo, correcto porque en el corpus esas categorías no tienen cláusulas de riesgo).

---

## 6. API Design

### Endpoints implementados (Advance 2)

| Endpoint | Estado | Notas |
|---|---|---|
| `GET /health` | ✅ Implementado | |
| `POST /v1/clausulas/classify` | ✅ Implementado | Clasificador de reglas |
| `POST /v1/contratos/analyze` | ✅ Implementado | Reglas, guarda en caché |
| `GET /v1/contratos/{id}/reporte` | ⚠️ Stub | Persistencia en memoria, no PostgreSQL |

```
GET  /health
     → {"status": "ok", "version": "0.1.0"}

POST /v1/clausulas/classify
     Header: X-Tenant-ID: tenant-demo
     Body: {"id": "c1", "texto": "El contratista pagará penalidad..."}
     Response: {"id", "categoria_predicha", "es_riesgo_predicho", "patrones_activados", "tenant_id"}

POST /v1/contratos/analyze
     Header: X-Tenant-ID: tenant-demo
     Body: {"contract_id": "C001", "clausulas": [...]}
     Response: {"contract_id", "tenant_id", "total_clausulas", "clausulas_riesgo", "resultados"}

GET  /v1/contratos/{contract_id}/reporte
     Header: X-Tenant-ID: tenant-demo
     Response: {"semaforo": [{"id", "categoria", "es_riesgo", "nivel": "ALTO|BAJO", "patrones"}],
                "porcentaje_riesgo", "nota": "[STUB]..."}
     Requiere: haber llamado POST /v1/contratos/analyze antes (caché en memoria)
```

### Decisiones de diseño

- `X-Tenant-ID` en header (no en URL) para no exponer tenant en logs de proxy.
- Prototipo valida tenant contra set fijo; diseño target (Advance 3): JWT con claims de tenant.
- Respuestas siempre incluyen `tenant_id` para auditoría en el cliente.
- Versión en URL (`/v1/`) para evolución sin romper clientes existentes.
- `response_format: json_object` en llamadas al LLM para garantizar parseo determinístico.
- El endpoint de reporte es un stub funcional: retorna la estructura target completa pero sin persistencia real.

---

## 7. Cloud Deployment Plan

### Infraestructura AWS

```
Internet
    │
    ▼
AWS ALB (Application Load Balancer)
    │ HTTPS (ACM certificate)
    ▼
ECS Fargate (cluster: tdse-prod)
    │ Task: tdse-api (FastAPI, 0.5 vCPU, 1 GB RAM)
    │ Auto-scaling: 1-4 tasks según CPU > 70%
    ├── RDS PostgreSQL 16 (db.t3.micro, Multi-AZ en prod)
    │   └── Subnet privada, SG solo desde ECS
    ├── S3 bucket: tdse-contratos-prod
    │   └── Prefijo /{tenant_id}/, versionado ON, cifrado SSE-KMS
    └── KMS: una CMK por tenant (plan pro)

GitHub Actions CI/CD:
    push main → build Docker → push ECR → update ECS service
```

### Estimación de costo (escenario inicial: 10 tenants, 100 contratos/mes)

| Servicio | Costo estimado/mes |
|---|---|
| ECS Fargate (1 task 24/7) | ~$15 |
| RDS t3.micro | ~$15 |
| S3 (1 GB) | ~$0.02 |
| KMS (10 CMKs) | ~$1 |
| ALB | ~$16 |
| OpenAI API (plan pro, ~500 cláusulas × 300 tokens) | ~$0.02 |
| **Total** | **~$47/mes** |

### Pasos de despliegue

1. `docker build -t tdse-api .` → `docker push {ecr_uri}/tdse-api:latest`
2. `aws ecs update-service --cluster tdse-prod --service tdse-api --force-new-deployment`
3. Migraciones de BD: Alembic en entrypoint antes de arrancar uvicorn.
4. Variables de entorno: `DATABASE_URL`, `OPENAI_API_KEY`, `AWS_KMS_KEY_ID` → AWS Secrets Manager.

---

## 8. Quality Attribute Scenarios

### QA-1: Desempeño (latencia)

- **Estímulo:** gerente de proyecto sube contrato de 20 cláusulas.
- **Respuesta esperada:** análisis completo retornado en < 3 segundos (modo rules).
- **Medición:** p95 de latencia en CloudWatch. Baseline actual: ~50ms por cláusula en reglas (estimado).
- **Modo LLM:** < 30 segundos para 20 cláusulas (1.5s por llamada a OpenAI, secuencial).

### QA-2: Precisión del clasificador

- **Estímulo:** 40 cláusulas del corpus sintético.
- **Respuesta esperada (reglas):** F1 ≥ 0.75, precision ≥ 0.95 (no generar falsas alarmas).
- **Resultado real obtenido:** F1 = 0.7895, precision = 1.0 ✓
- **Respuesta esperada (LLM):** F1 ≥ 0.87, recall ≥ 0.85 (hipótesis a validar en Advance 3).

### QA-3: Disponibilidad

- **Estímulo:** falla de una instancia ECS.
- **Respuesta esperada:** servicio disponible en < 60 segundos (ECS reemplaza la tarea automáticamente).
- **Medición:** uptime mensual ≥ 99.5% (CloudWatch alarm si downtime > 3.6h/mes).

### QA-4: Aislamiento de datos entre tenants

- **Estímulo:** tenant A intenta acceder a contratos de tenant B (ataque de enumeración de IDs).
- **Respuesta esperada:** HTTP 403 o resultado vacío; ningún dato de tenant B expuesto.
- **Medición:** test de integración automatizado en CI que verifica RLS con dos tenants distintos.

### QA-5: Costo por análisis

- **Estímulo:** 100 contratos/mes de 20 cláusulas cada uno (2000 cláusulas).
- **Respuesta esperada:** costo total < $50/mes (modo rules) o < $55/mes (modo híbrido).
- **Medición:** AWS Cost Explorer con tag `project=tdse`.

---

## 9. Security Design

### Riesgo central identificado en Advance 1

Exposición de contratos sensibles a APIs de terceros (OpenAI). Mitigación:

| Riesgo | Control |
|---|---|
| Texto del contrato enviado a OpenAI sin consentimiento | LLM solo disponible en plan pro con aceptación explícita de política de datos |
| Acceso cross-tenant a contratos | RLS en PostgreSQL + prefijos S3 por tenant + validación JWT vs. X-Tenant-ID |
| Exfiltración de archivos desde S3 | Bucket policy niega `s3:GetObject` fuera del rol ECS task; no hay URLs públicas |
| Credenciales en código | Secrets Manager para `OPENAI_API_KEY`, `DATABASE_URL`, `KMS_KEY_ID` |
| Inyección en texto de contrato | El texto se pasa como string en el prompt, no como instrucción; temperatura=0 |
| Acceso no autorizado a la API | JWT con expiración de 1h; refresh token con rotación |
| Pérdida de datos | RDS automated backups (7 días), S3 versionado |

### Aislamiento multi-tenant

```
Nivel 1 — Aplicación: X-Tenant-ID validado contra JWT claims
Nivel 2 — Base de datos: RLS con SET app.current_tenant = :tenant_id en cada conexión
Nivel 3 — Almacenamiento: S3 prefix /{tenant_id}/ + bucket policy
Nivel 4 — Cifrado: KMS CMK por tenant (plan pro); clave compartida AES-256 (plan free)
```

### Qué se envía y qué no a terceros

| Dato | Reglas (free) | LLM (pro, con consentimiento) |
|---|---|---|
| Texto de cláusula | No sale del servidor | Enviado a OpenAI API (TLS 1.3) |
| Nombre del contrato | No | No |
| Nombre del tenant/empresa | No | No |
| Metadatos de clasificación | No | No |

---

## 10. Roadmap

### Advance 3 / Final Delivery (Week 15)

| Semana | Tarea | Responsable |
|---|---|—|
| 11 | Ejecutar comparación LLM completa (40 cláusulas) + análisis de resultados | Nicolás |
| 11 | Ampliar corpus a 80 cláusulas (variantes de redacción para los 8 FN) | Santiago |
| 12 | Análisis estadístico (McNemar test reglas vs. LLM) | Sebastián |
| 12 | Despliegue en AWS ECS Fargate (entorno de demo) | Nicolás |
| 13 | Módulo de ingestón PDF (pdfminer.six) | Sebastián |
| 13 | Reemplazar stub de reporte por persistencia real (PostgreSQL) | Santiago |
| 14 | Pruebas de integración (RLS, aislamiento tenant, latencia) | Todos |
| 14 | Documentación final + video demo | Todos |
| 15 | Entrega Final | — |

### Decisiones pendientes

1. ¿Usar modo híbrido (reglas + LLM) o solo LLM en plan pro? → depende de resultados de Advance 3.
2. ¿Ampliar corpus con contratos reales de una PyME piloto? → requiere acuerdo de confidencialidad.
3. ¿Agregar categoría "cambios de alcance" explícita? → revisar si los FN de C001-07 y C003-05 justifican una categoría nueva.

---

## 11. Governance Model

### Propiedad del dato

- Cada tenant es propietario exclusivo de sus contratos y cláusulas.
- El operador del servicio (equipo TDSE) no puede acceder al contenido de contratos de producción sin autorización explícita del tenant (break-glass procedure documentado).
- Los datos del corpus sintético de investigación son propiedad del equipo y no contienen datos reales de ningún tenant.

### Qué se comparte entre tenants

**Nada del contenido.** Lo único compartido entre tenants es:
- El modelo de clasificación (reglas y prompt del LLM) — no contiene datos de ningún tenant.
- La infraestructura de cómputo (ECS cluster) — aislada a nivel de proceso y red.

### Decisiones de gobernanza

| Decisión | Quién decide |
|---|---|
| Activar modo LLM para un tenant | El administrador del tenant (opt-in explícito) |
| Actualizar las reglas de clasificación | Equipo operador, con versionado y changelog |
| Actualizar el prompt del LLM | Equipo operador, con prueba A/B en corpus de evaluación antes de producción |
| Retención de datos de contratos | Configurable por tenant (mínimo 30 días, máximo 5 años) |
| Eliminación de datos (derecho al olvido) | Solicitud del administrador del tenant → eliminación en 72h (S3 + BD) |
| Acceso de investigadores al corpus sintético | Equipo TDSE, sin datos de producción |

### Auditoría

- Toda acción sobre contratos (upload, analyze, export, delete) queda en `AuditLog` con timestamp, usuario y tenant.
- Logs de CloudWatch retenidos 90 días.
- Alertas automáticas si un usuario intenta acceder a contratos de otro tenant (RLS violation log).

---

## Estructura del repositorio

```
proyecto-tdse/
├── corpus/
│   └── synthetic_contracts.json     # 40 cláusulas, 5 contratos, etiquetadas
├── src/
│   ├── rules/
│   │   └── classifier.py            # Baseline de reglas (regex)
│   ├── llm/
│   │   └── classifier.py            # Clasificador LLM (OpenAI)
│   ├── evaluation/
│   │   └── evaluate.py              # Comparación reglas vs. LLM
│   └── api/
│       └── main.py                  # API REST (FastAPI)
├── results/
│   └── evaluation_results.json      # Resultados reales del prototipo
├── docs/
│   └── advance2.md                  # Este documento
├── requirements.txt
└── README.md
```

## Cómo ejecutar el prototipo

```bash
# Instalar dependencias
py -m pip install -r requirements.txt

# Ejecutar evaluación solo con reglas
py src/evaluation/evaluate.py

# Ejecutar evaluación con LLM (requiere OPENAI_API_KEY)
set OPENAI_API_KEY=sk-...
py src/evaluation/evaluate.py --llm

# Levantar API local
py -m uvicorn src.api.main:app --reload
# → http://localhost:8000/docs
```
