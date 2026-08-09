# Diagramas de actividad — Sprint 3

**Proyecto:** PokéGrading — Dr. Mundo Solutions
**Sprint:** 3
**Relacionado:** [ADR-004](./ADR-004-api-b2b-lookup-catalogo.md), [diagramas-secuencia.md](./diagramas-secuencia.md)

> Diagramas en **Mermaid** (renderizables en la wiki de Azure DevOps y en GitHub).

---

## 1. Flujo completo de grading de una carta — versión corregida

### 1.1 Correcciones aplicadas respecto a la versión anterior

| # | Corrección | Motivo |
|---|---|---|
| C1 | La **búsqueda rápida** ahora usa **pHash** (no OCR). El OCR pasa a la **búsqueda especializada/detallada**. | Alinear con el diseño de [busqueda-phash-ocr.md](./busqueda-phash-ocr.md): pHash es más rápido para el primer intento. |
| C2 | Se explicita la rama **"imagen no identificable"** → deriva a entrada **manual** de atributos. | El flujo anterior no mostraba la salida de `ImageNotIdentifiableError`. |
| C3 | Se añade el **gate de calidad de imagen (IQS ≥ 0.60)** antes de cualquier identificación. | Coincide con `SubmitCardForEvaluationUseCase` (US-003); el diagrama viejo validaba calidad después. |
| C4 | Se separa **identificación** (qué carta es) de **envío a evaluación** (persistir submission). | Eran un solo nodo ambiguo; ahora son dos actividades con su propio resultado. |
| C5 | Se marca explícitamente que la **cuota de evaluación** se descuenta **solo** al confirmar el envío, no durante la búsqueda. | Evita la confusión con el lookup B2B (que nunca toca cuota). |
| C6 | Estados terminales nombrados (`GRADED`, `REJECTED`, `PENDING`) según `SubmissionStatus`. | El diagrama viejo terminaba en "fin" genérico. |

### 1.2 Diagrama

```mermaid
flowchart TD
    start([Submitter inicia envío]) --> cap[Capturar imagen frente y reverso]
    cap --> val{Formato JPEG/PNG, ≤10MB, no polyglot?}
    val -- no --> rej1[Rechazar: formato/seguridad inválido]:::err
    val -- si --> iqs{IQS ≥ 0.60?}
    iqs -- no --> rej2[Rechazar: calidad insuficiente]:::err

    iqs -- si --> quick[Búsqueda RÁPIDA por pHash]
    quick --> qd{pHash dist ≤ umbral?}
    qd -- si, 1 candidato fuerte --> auto[Auto-aceptar carta identificada]
    qd -- no/ambiguo --> spec[Búsqueda ESPECIALIZADA por OCR]

    spec --> sd{OCR identifica candidatos?}
    sd -- si --> choose[Mostrar candidatos → usuario elige]
    sd -- imagen no identificable --> manual[Entrada MANUAL de atributos]
    sd -- sin coincidencia --> manual

    auto --> confirm[Confirmar carta del catálogo]
    choose --> confirm
    manual --> confirm

    confirm --> submit[Crear Submission status=PENDING]
    submit --> quota[Descontar cuota de evaluación]
    quota --> grade[Motor de grading procesa]
    grade --> result{Resultado}
    result -- ok --> graded([Submission GRADED]):::ok
    result -- no apta --> rejected([Submission REJECTED]):::err

    classDef err fill:#ffe0e0,stroke:#c00;
    classDef ok fill:#e0ffe0,stroke:#0a0;
```

> **Nota:** la cuota solo se descuenta en el nodo `quota`, **después** de confirmar la carta. Ni la búsqueda rápida ni la especializada consumen cuota — y el **lookup B2B (§2) nunca llega a este flujo**.

---

## 2. Flujo B2B — Consultar cobertura de catálogo (US-005)

Diagrama de actividad del nuevo requerimiento. Refleja el diseño de [ADR-004](./ADR-004-api-b2b-lookup-catalogo.md): autenticación → idempotencia → rate limit → resolución por carta → auditoría.

```mermaid
flowchart TD
    start([Tienda B2B envía POST /api/b2b/v1/catalog/lookup]) --> auth{API key válida?}
    auth -- no --> eAuth[Error único: INVALID_API_KEY / REVOKED / SUSPENDED / EXPIRED]:::err
    auth -- si --> cust{Customer activo?}
    cust -- no --> eCust[Error único: CUSTOMER_SUSPENDED 403]:::err

    cust -- si --> empty{cards no vacío y bien formado?}
    empty -- no --> eEmpty[Error único: EMPTY_QUERY / MALFORMED_QUERY 422]:::err

    empty -- si --> idem{request_id ya visto en ventana?}
    idem -- si, mismo hash --> stored[Devolver respuesta almacenada]:::ok2
    idem -- si, hash distinto --> eConf[Error único: IDEMPOTENCY_KEY_REUSED 409]:::err

    idem -- no --> etag{If-None-Match coincide con catalog_etag?}
    etag -- si --> notmod[304 Not Modified - sin recontar]:::ok2

    etag -- no --> rate{rate limit por nº de cartas OK?}
    rate -- no --> eRate[Error único: RATE_LIMIT_EXCEEDED 429 + Retry-After]:::err

    rate -- si --> loop[Por CADA carta del batch]
    loop --> perCard{set y number presentes y opcionales canónicos?}
    perCard -- no --> inv[Resultado carta: invalid_params + motivo]
    perCard -- si --> find[find_active_by_partial_identity]
    find --> count{coincidencias activas}
    count -- 0 --> nc[Resultado carta: not_covered]
    count -- 1 --> cov[Resultado carta: covered + 5 atributos oficiales]
    count -- mayor a 1 --> mm[Resultado carta: multiple_match - orden estable]

    inv --> agg[Agregar resultados del batch]
    nc --> agg
    cov --> agg
    mm --> agg

    agg --> audit[Registrar auditoría + guardar respuesta idempotente]
    audit --> ok([200 OK: results + ETag + summary]):::ok

    classDef err fill:#ffe0e0,stroke:#c00;
    classDef ok fill:#e0ffe0,stroke:#0a0;
    classDef ok2 fill:#e0f0ff,stroke:#06c;
```

### 2.1 Puntos clave del flujo B2B

| Característica | Reflejado en el diagrama |
|---|---|
| Solo lectura, sin cuota | No existe nodo de descuento de cuota; nunca entra al flujo de grading (§1) |
| Resolución independiente por carta | El bucle `loop` resuelve cada carta; `invalid_params` no aborta el batch (AC-05) |
| Carta retirada → `not_covered` | `find_active_by_partial_identity` solo cuenta activas; retiradas caen en `count = 0` |
| Idempotencia y ETag antes del rate limit | Un hit idempotente o un `304` **no** consumen tokens (AC-08/AC-09) |
| Formato de error único | Todas las ramas `:::err` emiten el mismo formato con `trace_id` (AC-11) |
| Auditoría siempre | El nodo `audit` se ejecuta en todo `200` real (AC-15) |

---

## 3. Comparación de los dos flujos (por qué no se cruzan)

```mermaid
flowchart LR
    subgraph Interno["Flujo interno (US-003/004) — usuario humano"]
      A1[JWT de usuario] --> A2[Imágenes] --> A3[Identificación pHash/OCR] --> A4[Submission + cuota + grading]
    end
    subgraph B2B["Flujo B2B (US-005) — sistema de tienda"]
      B1[API key] --> B2[Solo identidad, sin imágenes] --> B3[Lookup solo lectura] --> B4[Sin cuota, sin grading]
    end
    Interno -. comparten .-> CAT[(catalog_cards)]
    B2B -. solo lee .-> CAT
```

Ambos flujos comparten **únicamente** la tabla `catalog_cards`: el interno la usa para identificar y luego evaluar; el B2B **solo la lee** para reportar cobertura.

---

## Referencias

- [ADR-004 — API B2B](./ADR-004-api-b2b-lookup-catalogo.md)
- [busqueda-phash-ocr.md](./busqueda-phash-ocr.md)
- [diagramas-secuencia.md](./diagramas-secuencia.md)
- [ADR-003 — Búsqueda rápida (Sprint 2)](../../Sprint2/DOC/ADR-003-busqueda-rapida-de-carta.md)
