# Diagramas de secuencia — escenarios de éxito (Sprint 3)

**Proyecto:** PokéGrading — Dr. Mundo Solutions
**Sprint:** 3
**Relacionado:** [ADR-004](./ADR-004-api-b2b-lookup-catalogo.md), [diseno-versionamiento-seguridad-api.md](./diseno-versionamiento-seguridad-api.md)

> Las etiquetas usan los **nombres reales de archivo y clase** del código (Fase B), siguiendo la convención adoptada en Sprint 2 (TODO §3).

---

## 1. Lookup de cobertura — escenario de éxito (carta cubierta)

`POST /api/b2b/v1/catalog/lookup` con una API key válida y una carta que existe activa.

```mermaid
sequenceDiagram
    autonumber
    participant T as Tienda B2B
    participant R as routers/lookup.py
    participant DEP as dependencies.py<br/>get_current_b2b_client
    participant AUTH as AuthenticateB2BClientUseCase
    participant KR as ApiKeyRepositoryImpl
    participant H as Sha256ApiKeyHasher
    participant UC as LookupCatalogCoverageUseCase
    participant IDEM as IdempotencyRepositoryImpl
    participant RL as SlidingWindowRateLimiter
    participant CR as CardRepositoryImpl
    participant AUD as B2BAuditRepositoryImpl

    T->>R: POST /catalog/lookup<br/>X-API-Key, {cards:[{set,number}]}
    R->>DEP: resolver cliente B2B
    DEP->>AUTH: execute(api_key)
    AUTH->>KR: find_by_prefix(prefix)
    KR-->>AUTH: ApiKey(active)
    AUTH->>H: verify(secret, hashed_secret)
    H-->>AUTH: true
    AUTH-->>DEP: (B2BCustomer, ApiKey)
    DEP-->>R: cliente autenticado

    R->>UC: execute(customer, api_key, cards, request_id)
    UC->>IDEM: find_within_window(api_key_id, request_id)
    IDEM-->>UC: None (miss)
    UC->>RL: check_and_consume(api_key_id, cards=1)
    RL-->>UC: OK (1 token consumido)
    UC->>CR: find_active_by_partial_identity(set, number)
    CR-->>UC: [Card] (1 activa)
    Note over UC: 1 coincidencia → status=covered
    UC->>AUD: record_lookup(trace_id, counts)
    UC->>IDEM: save(api_key_id, request_id, hash, response)
    UC-->>R: LookupResponse(results, etag)
    R-->>T: 200 OK + ETag + X-Trace-Id
```

---

## 2. Lookup batch con estados mixtos (covered + multiple + not_covered + invalid)

Un solo request con varias cartas; cada una resuelve de forma independiente (AC-05).

```mermaid
sequenceDiagram
    autonumber
    participant T as Tienda B2B
    participant UC as LookupCatalogCoverageUseCase
    participant CR as CardRepositoryImpl

    T->>UC: cards = [C0 ok-única, C1 ambigua, C2 inexistente, C3 sin set]
    loop por cada carta
        alt C0: set+number válidos, 1 activa
            UC->>CR: find_active_by_partial_identity(C0)
            CR-->>UC: [card] → covered
        else C1: faltan opcionales, varias activas
            UC->>CR: find_active_by_partial_identity(C1)
            CR-->>UC: [cardA, cardB] → multiple_match (orden por id)
        else C2: válida pero sin coincidencia / retirada
            UC->>CR: find_active_by_partial_identity(C2)
            CR-->>UC: [] → not_covered
        else C3: falta 'set'
            Note over UC: no consulta BD → invalid_params (MISSING_REQUIRED_FIELD)
        end
    end
    UC-->>T: 200 OK<br/>summary{covered:1, multiple:1, not_covered:1, invalid:1}
```

---

## 3. Idempotencia — reintento con el mismo `request_id`

Segunda llamada idéntica dentro de la ventana: misma respuesta, sin recontar ni reauditar (AC-08).

```mermaid
sequenceDiagram
    autonumber
    participant T as Tienda B2B
    participant UC as LookupCatalogCoverageUseCase
    participant IDEM as IdempotencyRepositoryImpl
    participant RL as SlidingWindowRateLimiter
    participant AUD as B2BAuditRepositoryImpl

    Note over T,UC: 1ª llamada ya ocurrió y se guardó la respuesta
    T->>UC: POST {request_id=R1, cards} (reintento)
    UC->>IDEM: find_within_window(api_key_id, R1)
    IDEM-->>UC: respuesta almacenada (hash coincide)
    Note over UC,RL: NO se consume rate limit
    Note over UC,AUD: NO se vuelve a auditar
    UC-->>T: 200 OK (misma respuesta, mismo ETag)
```

---

## 4. Validación condicional — `304 Not Modified`

La tienda reenvía `If-None-Match` y el catálogo no cambió (AC-09).

```mermaid
sequenceDiagram
    autonumber
    participant T as Tienda B2B
    participant R as routers/lookup.py
    participant UC as LookupCatalogCoverageUseCase

    T->>R: POST /catalog/lookup<br/>If-None-Match: "cat-v2026061301"
    R->>UC: execute(..., if_none_match)
    UC->>UC: calcular catalog_etag actual
    alt etag == if_none_match
        UC-->>R: NOT_MODIFIED
        R-->>T: 304 Not Modified (sin cuerpo, sin recontar)
    else cambió
        UC-->>R: LookupResponse + nuevo etag
        R-->>T: 200 OK + ETag nuevo
    end
```

---

## 5. Autenticación B2B con periodo de gracia (rotación de llave)

La llave vieja, dentro de su periodo de gracia, sigue autenticando con advertencia (ver [seguridad §5](./diseno-versionamiento-seguridad-api.md)).

```mermaid
sequenceDiagram
    autonumber
    participant T as Tienda (llave vieja)
    participant AUTH as AuthenticateB2BClientUseCase
    participant KR as ApiKeyRepositoryImpl

    T->>AUTH: X-API-Key (llave vieja)
    AUTH->>KR: find_by_prefix(prefix_viejo)
    KR-->>AUTH: ApiKey(status=active, expires_at<now, grace_period_until>now)
    Note over AUTH: expirada pero DENTRO de gracia → autentica
    AUTH-->>T: OK (log key_in_grace=true, header Deprecation)
```

---

## 6. Búsqueda rápida por pHash con escalamiento a OCR (flujo interno)

Escenario de éxito del nuevo diseño de búsqueda (ver [busqueda-phash-ocr.md](./busqueda-phash-ocr.md)).

```mermaid
sequenceDiagram
    autonumber
    participant U as Submitter
    participant R as routers/search.py
    participant QS as QuickSearchCardUseCase
    participant PH as PHashImageHashService
    participant CR as CardRepositoryImpl
    participant SP as SpecializedSearchCardUseCase
    participant OCR as EasyOCRCardMatchingService

    U->>R: POST /search/quick (image_front)
    R->>QS: execute(image_data)
    QS->>PH: compute_phash(image_data)
    PH-->>QS: phash
    QS->>CR: find_by_phash_near(phash, max_hamming)
    alt candidato fuerte (Hamming ≤ umbral)
        CR-->>QS: [card] → auto_accepted
        QS-->>U: 200 candidato identificado (pHash)
    else ambiguo / sin coincidencia
        QS-->>R: escalar a especializada
        R->>SP: execute(image_data)
        SP->>OCR: extract_features(image_data)
        OCR-->>SP: tokens/texto
        SP->>CR: find_top_candidates(query)
        CR-->>SP: [candidatos]
        SP-->>U: 200 candidatos (OCR) o 422 manual
    end
```

---

## 7. Trazabilidad secuencia → código (Fase B)

| Participante en diagramas | Archivo de código a implementar |
|---|---|
| `routers/lookup.py` | `api/b2b/v1/routers/lookup.py` |
| `dependencies.py / get_current_b2b_client` | `api/b2b/v1/dependencies.py` |
| `AuthenticateB2BClientUseCase` | `application/use_cases/authenticate_b2b_client.py` |
| `LookupCatalogCoverageUseCase` | `application/use_cases/lookup_catalog_coverage.py` |
| `ApiKeyRepositoryImpl` / `Sha256ApiKeyHasher` | `infrastructure/persistence/repositories/b2b/api_key_repository.py` / `infrastructure/security/api_key.py` |
| `IdempotencyRepositoryImpl` / `B2BAuditRepositoryImpl` | `infrastructure/persistence/repositories/b2b/*` |
| `SlidingWindowRateLimiter` | `infrastructure/ratelimit/sliding_window_rate_limiter.py` |
| `CardRepositoryImpl.find_active_by_partial_identity` | `infrastructure/persistence/repositories/card/card_repository.py` |
| `PHashImageHashService` / `QuickSearchCardUseCase` | `infrastructure/matching/phash_image_hash_service.py` / `application/use_cases/quick_search_card.py` |

---

## Referencias

- [ADR-004 — API B2B](./ADR-004-api-b2b-lookup-catalogo.md)
- [diseno-versionamiento-seguridad-api.md](./diseno-versionamiento-seguridad-api.md)
- [busqueda-phash-ocr.md](./busqueda-phash-ocr.md)
- [diagramas-actividad.md](./diagramas-actividad.md)
