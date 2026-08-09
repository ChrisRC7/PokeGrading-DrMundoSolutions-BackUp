# TODO — Sprint 3: API B2B de cobertura de catálogo + búsqueda por pHash/OCR

**Sprint:** 3
**Rama base:** `DevelopmentChris`
**Funcionalidad principal:** US-005 — Consultar cobertura de catálogo por API B2B (lookup de carta)
**Arquitectura:** Clean Architecture + Repository + Ports & Adapters (igual que Sprint 1 y 2)

---

## 0. Convención de trabajo

> **Este sprint se ejecuta en dos fases.**
> **Fase A — Diseño (este documento + los `.md` de `DOC/`).** Primero se documenta TODO lo solicitado: ADR, diagramas y diseño de seguridad/versionamiento/datos sensibles.
> **Fase B — Implementación.** El código se escribe **siguiendo** los `.md` de la Fase A. Ninguna decisión de arquitectura se toma en el código sin estar antes en un documento de diseño.

Los entregables documentales viven en [`Sprint3/DOC/`](./DOC/). La trazabilidad documento → código está al final de cada sección.

---

## 1. Entregables de modelado y diseño (Fase A)

| # | Entregable | Documento | Estado |
|---|---|---|---|
| 1.1 | Correcciones al diagrama de actividad del flujo completo de grading | [`DOC/diagramas-actividad.md`](./DOC/diagramas-actividad.md) §1 | [x] |
| 1.2 | Nuevo diagrama de actividad para el flujo B2B (US-005) | [`DOC/diagramas-actividad.md`](./DOC/diagramas-actividad.md) §2 | [x] |
| 1.3 | ADR del diseño del API B2B (seguridad, versionamiento, logging, contrato) | [`DOC/ADR-004-api-b2b-lookup-catalogo.md`](./DOC/ADR-004-api-b2b-lookup-catalogo.md) | [x] |
| 1.4 | Diseño para el manejo de datos sensibles | [`DOC/diseno-datos-sensibles.md`](./DOC/diseno-datos-sensibles.md) | [x] |
| 1.5 | Diseño de versionamiento y seguridad del API (estructura de llaves, periodos de gracia, revocación) | [`DOC/diseno-versionamiento-seguridad-api.md`](./DOC/diseno-versionamiento-seguridad-api.md) | [x] |
| 1.6 | Diagramas de secuencia de los escenarios de éxito del sprint | [`DOC/diagramas-secuencia.md`](./DOC/diagramas-secuencia.md) | [x] |
| 1.7 | Primera versión del diagrama físico de la solución | [`DOC/diagrama-fisico.md`](./DOC/diagrama-fisico.md) | [x] |
| 1.8 | Diseño de búsqueda rápida por pHash + búsqueda especializada por OCR | [`DOC/busqueda-phash-ocr.md`](./DOC/busqueda-phash-ocr.md) | [x] |

> **Nota sobre las wikis:** cada documento de `DOC/` se publica además en la wiki correspondiente de Azure DevOps. Los diagramas usan **Mermaid** (soportado por la wiki) salvo los de almacenamiento/físico que combinan Mermaid + ASCII para conservar el estilo de los ADR-002/003.

---

## 2. US-005 — Consultar cobertura de catálogo por API B2B (lookup de carta)

**Historia:** Yo como **Customer B2B (tienda)** quiero consultar por API si PokéGrading reconoce una o varias cartas en su catálogo, para saber cuáles puedo enviar a evaluación sin gastar consumo en cartas que no existen en el catálogo.

**Principios irrenunciables del diseño** (derivados de la US):

1. **Autenticación por API key** que identifica al Customer B2B y a la cuenta de servicio.
2. **Solo identidad, nunca imágenes**: no sube fotos ni dispara el motor de grading.
3. **Batch independiente**: una consulta = 1..N cartas; cada carta recibe su propio resultado.
4. **Solo lectura, sin cuota**: nunca descuenta cuota de evaluación.
5. **Rate limit por cantidad de cartas**, no por cantidad de llamadas.
6. **Idempotencia** por `request_id` dentro de una ventana.
7. **Validación condicional (ETag)** para no retransferir datos sin cambios.
8. **Formato de error único** con código estable + trace id.
9. **Aislamiento de datos**: solo metadata del catálogo; nunca evaluaciones ni datos de otras tiendas.

> El diseño completo (contrato, estados de resultado, manejo de errores, idempotencia, rate limit, ETag) está en [`ADR-004`](./DOC/ADR-004-api-b2b-lookup-catalogo.md). El detalle de llaves/revocación en [`diseno-versionamiento-seguridad-api.md`](./DOC/diseno-versionamiento-seguridad-api.md). Este TODO solo lista las tareas de implementación que se derivan de esos documentos.

### 2.1 Estados de resultado por carta

| Estado | Condición | Devuelve |
|---|---|---|
| `covered` (cubierta) | Exactamente 1 coincidencia **activa** | `card_id` + los 5 atributos en su forma oficial del catálogo |
| `multiple_match` (coincidencia múltiple) | > 1 coincidencia activa | Lista de candidatos (id + atributos oficiales) en **orden estable y reproducible** |
| `not_covered` (no cubierta) | 0 coincidencias activas (incluye cartas retiradas) | Solo el eco de los parámetros consultados |
| `invalid_params` (parámetros inválidos) | Falta `set`/`número`, u opcional fuera de listados canónicos | Motivo + campo afectado |

### 2.2 Cambios en dominio (`domain/`)

- [x] **`entities/b2b_customer.py`** → entidad `B2BCustomer` (`id`, `name`, `status`, `created_at`)
- [x] **`entities/api_key.py`** → entidad `ApiKey` (`id`, `customer_id`, `key_prefix`, `hashed_secret`, `status`, `scopes`, `created_at`, `expires_at`, `grace_period_until`, `revoked_at`, `last_used_at`) — ver estructura en [`diseno-versionamiento-seguridad-api.md`](./DOC/diseno-versionamiento-seguridad-api.md) §2
- [x] **`value_objects/api_key_status.py`** → enum `ApiKeyStatus` (`active`, `suspended`, `revoked`, `expired`)
- [x] **`value_objects/b2b_customer_status.py`** → enum `B2BCustomerStatus` (`active`, `suspended`)
- [x] **`value_objects/lookup_result_status.py`** → enum `LookupResultStatus` (`covered`, `multiple_match`, `not_covered`, `invalid_params`)
- [x] **`value_objects/card_edition.py` / `card_finish.py`** → listados canónicos de edición y acabado (opcionales de identidad)
- [x] **`entities/card_lookup.py`** → `CardLookupItem` (los 5 atributos, set+número obligatorios), `CardLookupResult` (status + payload) e `InvalidReason`
- [x] **`repositories/api_key_repository.py`** → `IApiKeyRepository` (`find_by_prefix`, `save`, `touch_last_used`)
- [x] **`repositories/b2b_customer_repository.py`** → `IB2BCustomerRepository` (`find_by_id`)
- [x] **`repositories/b2b_audit_repository.py`** → `IB2BAuditRepository` (`record_lookup`) + `LookupAuditRecord`
- [x] **`repositories/b2b_idempotency_repository.py`** → `IIdempotencyRepository` (`find_within_window`, `save`) + `IdempotencyRecord`
- [x] **`repositories/card_repository.py`** → `find_active_by_partial_identity(...)` (solo `status=active`, orden estable por `id`) + `get_catalog_fingerprint()` para el ETag
- [x] **`exceptions.py`** → excepciones nuevas (clase base `B2BError` con `code`/`http_status`/`field`/`card_ref`, mapeadas al formato de error único):
  - `InvalidApiKeyError` → 401 `INVALID_API_KEY`
  - `ApiKeyRevokedError` → 401 `API_KEY_REVOKED`
  - `ApiKeySuspendedError` → 401 `API_KEY_SUSPENDED`
  - `ApiKeyExpiredError` → 401 `API_KEY_EXPIRED`
  - `B2BCustomerSuspendedError` → 403 `CUSTOMER_SUSPENDED`
  - `EmptyLookupQueryError` → 422 `EMPTY_QUERY`
  - `RateLimitExceededError(retry_after_seconds)` → 429 `RATE_LIMIT_EXCEEDED`

### 2.3 Cambios en aplicación (`application/`)

- [x] **`ports/api_key_hasher.py`** → `IApiKeyHasher` (ABC): `hash(secret)`, `verify(secret, hashed)` — ver §4 del doc de seguridad
- [x] **`ports/rate_limiter.py`** → `IRateLimiter` (ABC): `check_and_consume(api_key, cards) -> RateLimitVerdict`
- [x] **`use_cases/authenticate_b2b_client.py`** → `AuthenticateB2BClientUseCase`
  - Resuelve `prefix` → `IApiKeyRepository.find_by_prefix`
  - Verifica secreto con `IApiKeyHasher.verify`
  - Valida estado de llave (incluyendo periodo de gracia) y estado del customer
  - Lanza las excepciones de §2.2 según corresponda
- [x] **`use_cases/lookup_catalog_coverage.py`** → `LookupCatalogCoverageUseCase`
  - Input: `customer`, `api_key`, lista de `CardLookupItem`, `request_id?`
  - 1) Si la lista está vacía → `EmptyLookupQueryError`
  - 2) Idempotencia: si `request_id` ya existe en ventana → devolver respuesta almacenada (sin recontar rate limit ni reauditar)
  - 3) Rate limit por cantidad de cartas → `RateLimitExceededError` si excede
  - 4) Por cada carta: validar requeridos + opcionales canónicos → `invalid_params`; si válida → `find_active_by_partial_identity` → 0/1/N → `not_covered`/`covered`/`multiple_match`
  - 5) Registrar auditoría (`IB2BAuditRepository`) y guardar respuesta idempotente
  - 6) Calcular `catalog_etag` para validación condicional
  - Output: `LookupResponse` (resultados + `etag` + contadores)

### 2.4 Cambios en infraestructura (`infrastructure/`)

- [x] **`persistence/models.py`** → ORMs nuevos: `B2BCustomerORM`, `ApiKeyORM`, `B2BLookupAuditORM`, `B2BIdempotencyORM`, `B2BRateLimitCounterORM` (esquema en [`ADR-004`](./DOC/ADR-004-api-b2b-lookup-catalogo.md) §7)
- [x] **`persistence/repositories/b2b/api_key_repository.py`** → `ApiKeyRepositoryImpl`
- [x] **`persistence/repositories/b2b/customer_repository.py`** → `B2BCustomerRepositoryImpl`
- [x] **`persistence/repositories/b2b/audit_repository.py`** → `B2BAuditRepositoryImpl`
- [x] **`persistence/repositories/b2b/idempotency_repository.py`** → `IdempotencyRepositoryImpl`
- [x] **`persistence/repositories/card/card_repository.py`** → `find_active_by_partial_identity` + `get_catalog_fingerprint`
- [x] **`security/api_key.py`** → `Sha256ApiKeyHasher(IApiKeyHasher)` (HMAC-SHA256 con pepper) + `generate_api_key()`
- [x] **`ratelimit/fixed_window_rate_limiter.py`** → `FixedWindowRateLimiter(IRateLimiter)` sobre tabla `b2b_rate_limit_counters` (ventana fija; Redis en producción — ADR-004 §4)
- [x] **Migración Alembic** → `f1a2b3c4d5e6_create_b2b_tables` (customers, api_keys, audit, idempotency, rate_limit_counters)
- [x] **Seed de llaves** (sin endpoint de aprovisionamiento): `scripts/seed_b2b_api_key.py` inserta 1 Customer + 1 ApiKey e imprime la llave en claro **una sola vez**. Ver [`diseno-versionamiento-seguridad-api.md`](./DOC/diseno-versionamiento-seguridad-api.md) §6

### 2.5 Cambios en API (`api/b2b/v1/`)

> El API B2B se versiona de forma **independiente** del API interno `/api/v2`. Ruta base: `/api/b2b/v1`. Justificación en [`diseno-versionamiento-seguridad-api.md`](./DOC/diseno-versionamiento-seguridad-api.md) §1.

- [x] **`api/b2b/v1/dependencies.py`** → `get_current_b2b_client` (lee header `X-API-Key`, delega en `AuthenticateB2BClientUseCase`) + `B2BClient`
- [x] **`api/b2b/v1/schemas/lookup.py`** → `LookupRequest`, `LookupItemRequest`, `LookupResponseSchema`, `LookupItemResultSchema`, `OfficialIdentitySchema`, `B2BErrorResponse`
- [x] **`api/b2b/v1/routers/lookup.py`** →
  - `POST /api/b2b/v1/catalog/lookup` (header `X-API-Key`, opcional `Idempotency-Key`/`request_id`, opcional `If-None-Match`)
  - Devuelve `200` con resultados, `304` si el ETag coincide, o el formato de error único en rechazos
- [x] **`main.py`** → registra el router B2B (`/api/b2b/v1`) + handler de `B2BError` que emite el **formato de error único** con `trace_id` (precede a `PokegradingError` por MRO)
- [x] **Middleware de `trace_id`** → genera/propaga `trace_id` por request en `X-Trace-Id`; la auditoría persiste prefijo de llave (nunca el secreto), customer y contadores (ver [`diseno-datos-sensibles.md`](./DOC/diseno-datos-sensibles.md) §5)

### 2.6 Tests (`tests/`)

**Unitarios** (`tests/unit/`):
- [x] `test_authenticate_b2b_client.py`: llave válida / inválida / revocada / suspendida / expirada / en gracia; customer suspendido; touch last_used
- [x] `test_lookup_catalog_coverage.py`: covered, multiple_match, not_covered, invalid_params; carta retirada → not_covered; consulta vacía → EmptyLookupQueryError; mezcla de estados en un mismo batch; orden estable en multiple_match; idempotencia + reuse; ETag 304; rate limit
- [x] `test_api_key_hasher.py`: hash/verify; resistencia a llave equivocada; formato de llave generada
- [x] `test_fixed_window_rate_limiter.py`: cuenta por cartas, no por llamadas; excede → bloquea con `retry_after`

**Integración** (`tests/integration/`):
- [x] `test_b2b_lookup.py`:
  - AC felices: lookup 1 carta cubierta → 200; lookup N cartas con estados mixtos → 200
  - Idempotencia: misma `request_id` dentro de ventana → misma respuesta, sin recontar (auditoría = 1)
  - ETag: segunda consulta con `If-None-Match` → 304
  - Sin API key / key inválida / revocada → 401 formato único
  - Customer suspendido → 403 formato único
  - Consulta sin cartas → 422 formato único
  - Rate limit excedido → 429 con `Retry-After`
  - Aislamiento: la respuesta solo expone los 6 campos de metadata del catálogo

> **Resultado:** `pytest` → **140 passed, cobertura 96%** (dominio+aplicación, umbral 75%).

### 2.7 Criterios de aceptación

| # | Criterio | Estado |
|---|---|---|
| AC-01 | API key válida + ≥1 carta → 200 con un resultado por carta | [x] |
| AC-02 | Carta con única coincidencia activa → `covered` + `card_id` + 5 atributos oficiales | [x] |
| AC-03 | Carta con varias coincidencias → `multiple_match` con candidatos en orden estable y reproducible | [x] |
| AC-04 | Carta inexistente o **retirada** → `not_covered` | [x] |
| AC-05 | Carta sin `set`/`número` u opcional fuera de listados canónicos → `invalid_params` con motivo, **sin** afectar a las demás cartas del batch | [x] |
| AC-06 | La consulta nunca descuenta cuota de evaluación | [x] (por diseño: el lookup es solo lectura, no hay ningún camino que toque cuota) |
| AC-07 | Rate limit calculado sobre cantidad de **cartas**, no de llamadas; al exceder → 429 con cuándo reintentar | [x] |
| AC-08 | Mismo `request_id` dentro de la ventana → misma respuesta, sin recontar ni reauditar | [x] |
| AC-09 | Validación condicional (ETag/`If-None-Match`) evita retransferir datos sin cambios → 304 | [x] |
| AC-10 | API key inválida/revocada/suspendida o customer suspendido → rechazo total con formato de error único, ninguna carta procesada | [x] |
| AC-11 | Todos los rechazos: código estable + mensaje legible + campo/carta afectada + `trace_id` | [x] |
| AC-12 | La respuesta solo expone metadata del catálogo: nunca evaluaciones ni datos de otras tiendas | [x] |
| AC-13 | Cuota mensual agotada **no** bloquea la consulta | [x] (por diseño: el lookup no consulta ni consume cuota) |
| AC-14 | Fallo temporal → formato único + consulta reintentable sin estado parcial | [x] El router envuelve excepciones inesperadas en `INTERNAL_ERROR` (500) con el formato único; auditoría/idempotencia se persisten solo al final → sin estado parcial |
| AC-15 | Cada consulta queda registrada para auditoría asociada a la API key | [x] |

---

## 3. Búsqueda rápida por pHash + búsqueda especializada por OCR

**Contexto:** en Sprint 2 la búsqueda rápida (US-004) usaba EasyOCR. En Sprint 3 se reorganiza:
- **Búsqueda rápida** → **pHash** (perceptual hash de la imagen contra las imágenes de referencia del catálogo). Rápida y barata.
- **Búsqueda detallada/especializada** → **OCR** (EasyOCR, ya implementado) cuando el pHash no resuelve con confianza.

> **Estado:** ✅ **implementado y probado.** Diseño en [`DOC/busqueda-phash-ocr.md`](./DOC/busqueda-phash-ocr.md). Tareas:

- [x] **`application/ports/image_hash_service.py`** → `IImageHashService` (ABC): `compute_phash(image_data) -> str`, `hamming_distance(a, b) -> int`
- [x] **`infrastructure/matching/phash_image_hash_service.py`** → `PHashImageHashService` (`imagehash` + Pillow) + `StubImageHashService` (tests)
- [x] **`persistence/models.py`** → columna `phash String(16)` (hex de 64 bits) en `card_images`, indexada; campo `phash` en la entidad `CardImage`
- [x] **Migración Alembic** → `a7b8c9d0e1f2_add_phash_to_card_images`
- [x] **Backfill**: `scripts/backfill_phash.py` calcula el pHash de las imágenes ya cargadas
- [x] **`use_cases/quick_search_by_phash.py`** → `QuickSearchByPHashUseCase`: primer intento por pHash (Hamming ≤ umbral); sin coincidencia → `NoMatchFoundError`, imagen ilegible → `ImageNotIdentifiableError` (señal de escalar a OCR)
- [x] **Flujo OCR especializado**: se reutiliza `QuickSearchCardUseCase` (EasyOCR) existente — el endpoint lo expone como búsqueda detallada
- [x] **`api/v2/routers/search.py`** → `POST /search/quick` (pHash → escala a OCR) y `POST /search/specialized` (OCR). Respuesta incluye `match_engine` (`phash`/`ocr`); upload de imágenes calcula y persiste el pHash
- [x] **`ICardRepository.find_by_phash_near`** + impl (join `card_images` front con `phash`, Hamming en Python, orden por cercanía)
- [x] Tests: pHash exacto/cercano (auto-aceptación), lejano (no auto), sin coincidencia, escalamiento a OCR, endpoint especializado, sin token → **+13 tests** (total **153 passed, 96%**)

---

## 4. Orden de implementación recomendado (Fase B)

```
Fase A (docs) ────────────────────────────────────────────────┐
  diagramas-actividad → ADR-004 → diseno-versionamiento-seguridad-api
  → diseno-datos-sensibles → diagramas-secuencia → diagrama-fisico
  → busqueda-phash-ocr                                          │
                                                                ▼
Fase B (código)
  domain (entities, VOs, repos, exceptions)
  → application (ports, use cases)
  → infrastructure (models, repos, hasher, rate limiter, migración, seed)
  → api/b2b/v1 (deps, schemas, router) + main.py (error único, logging)
  → tests unit → tests integración
  → pHash/OCR (ports, servicio, migración, backfill, use cases, router, tests)
```

---

## 5. Resumen de prioridades

| # | Tarea | Prioridad | Esfuerzo | Estado |
|---|---|---|---|---|
| 1.x | Documentos de diseño (ADR, diagramas, seguridad, datos sensibles, físico) | Alta | Alto | ✅ Completo |
| 2.x | US-005 API B2B lookup (dominio → API → tests) | Alta | Muy alto | ✅ Completo |
| 3.x | Búsqueda rápida pHash + especializada OCR | Media | Alto | ✅ Completo |

---

## 6. Estado general

- **Fase A (diseño):** ✅ completa — 8 documentos en [`DOC/`](./DOC/).
- **Fase B (US-005 API B2B):** ✅ implementada y probada, incluyendo AC-14 (catch-all → formato único).
- **Búsqueda pHash/OCR:** ✅ implementada y probada — pHash como búsqueda rápida con escalamiento a OCR (especializada).
- **Suite completa:** **154 tests, 96% cobertura** (umbral 75%).
- **Verificación contra PostgreSQL 18 real (puerto 5433):**
  - Dump del equipo restaurado (`pg_restore`) → 11 usuarios, 4 cartas, 8 imágenes, 15 envíos.
  - `alembic upgrade head` aplica las migraciones nuevas (B2B + phash) sobre la BD real sin errores.
  - Backfill de pHash poblado (8/8 imágenes).
  - `/health`, `/api/v2/*` (401 sin token) y `/api/b2b/v1/catalog/lookup` (covered/not_covered + formato de error único) verificados end-to-end con datos reales.

---

*Documento generado Sprint 3 — PokéGrading — Dr. Mundo Solutions.*
