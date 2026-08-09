# Mapa de Archivos — PokéGrading

> Índice archivo por archivo: qué hay en cada uno y para qué sirve.
> Pensado para orientarte rápido al navegar el código. Para entender los **flujos**
> completos consulta [GUIA-PROYECTO.md](GUIA-PROYECTO.md); para el flujo de búsqueda,
> [Sprint3/DOC/DiagramaQuickSearch-pHash.md](Sprint3/DOC/DiagramaQuickSearch-pHash.md).

Convención de capas: **domain** (negocio puro) → **application** (casos de uso) →
**infrastructure** (técnica) → **api** (HTTP). Las dependencias apuntan hacia adentro.

---

## Raíz del backend

| Archivo | Qué contiene |
|---|---|
| `src/pokegrading/main.py` | Arranque de FastAPI: registra routers (`/api/v3` y `/api/b2b/v1`), CORS, middleware de `trace_id`, mapeo de excepciones de dominio → códigos HTTP, handler de errores B2B (formato único) y personalización del OpenAPI (auth Bearer en Swagger). |
| `src/pokegrading/config.py` | `Settings` (Pydantic) que lee el `.env`: URL de BD, secreto/algoritmo/expiración JWT, pepper y parámetros del API B2B. `get_settings()` cacheado. |

---

## `domain/` — Capa de negocio (sin frameworks)

### `domain/entities/` — Objetos de negocio con sus reglas
| Archivo | Qué contiene |
|---|---|
| `card.py` | Entidad `Card` del catálogo. Reglas: nombre no vacío, versión ≥ 1, `approve()` (impide que el aprobador sea el creador — doble validación), `reset_to_pending()`, `is_active()`. |
| `card_image.py` | Entidad `CardImage` (imagen de referencia en binario) + constantes de validación (`ALLOWED_CONTENT_TYPES`, `MIN_WIDTH_PX`, `MAX_FILE_SIZE_BYTES`). Valida side/formato/resolución/tamaño y guarda el `phash`. |
| `user.py` | Entidad `User`: `is_admin()`, `is_reviewer()`, `has_role()`. |
| `submission.py` | Entidad `Submission`: envío de carta física (frente+reverso en binario, IQS, estado). |
| `search_result.py` | DTO `SearchResult`: un candidato de búsqueda (card_id, confidence_score, rank, nombre, set, número…). |
| `card_lookup.py` | Tipos del B2B: `CardLookupItem` (consulta de una carta), `CardLookupResult` (resultado), `InvalidReason` (motivo de invalidez). |
| `api_key.py` | Entidad `ApiKey` (B2B): `is_expired()`, `is_in_grace()`, `has_scope()`. |
| `b2b_customer.py` | Entidad `B2BCustomer` (tienda): `is_active()`. |

### `domain/value_objects/` — Tipos cerrados / enums de negocio
| Archivo | Qué contiene |
|---|---|
| `card_identity.py` | `CardIdentityTuple`: identidad única de carta (set + número + edición + idioma + finish). |
| `card_status.py` | `CardStatus`: pending / active / retired. |
| `submission_status.py` | `SubmissionStatus`. |
| `role.py` | `UserRole`: admin / submitter. |
| `language.py` | `SupportedLanguage`: en, ja, es, fr, de, it, pt, ko, zh, pl, nl, th. |
| `country.py` | `SupportedCountry`. |
| `card_edition.py` | `CardEdition`: 1st Edition / Unlimited / Shadowless. |
| `card_finish.py` | `CardFinish`: holo / reverse holo / non-holo. |
| `rarity.py` | `CardRarity`. |
| `pokemon_type.py` | `PokemonType`. |
| `api_key_status.py` | `ApiKeyStatus`: active / suspended / revoked / expired. |
| `b2b_customer_status.py` | `B2BCustomerStatus`: active / suspended. |
| `lookup_result_status.py` | `LookupResultStatus`: covered / multiple_match / not_covered / invalid_params. |
| `blocked_domains.py` | `BLOCKED_DOMAINS`: dominios de email bloqueados al registrarse. |

### `domain/repositories/` — Interfaces de persistencia (puertos de salida)
> Definen el contrato; la implementación vive en `infrastructure/persistence`.

| Archivo | Qué contiene |
|---|---|
| `card_repository.py` | `ICardRepository`: `find_by_identity`, `find_by_id`, `save`, `find_top_candidates` (texto/OCR), `find_active_by_partial_identity` (B2B), `find_by_phash_near` (pHash), `get_catalog_fingerprint` (ETag). |
| `image_repository.py` | `ICardImageRepository`: `save`, `find_by_card_and_side`, `has_front`, `has_back`. |
| `user_repository.py` | `IUserRepository`: `find_by_email`, `find_by_id`, `save`. |
| `submission_repository.py` | `ISubmissionRepository`: `save`, `find_by_id`, `find_by_user`, `find_all`. |
| `api_key_repository.py` | `IApiKeyRepository`: `find_by_prefix`, `save`, `touch_last_used`. |
| `b2b_customer_repository.py` | `IB2BCustomerRepository`: `find_by_id`, `save`. |
| `b2b_audit_repository.py` | `IB2BAuditRepository` + `LookupAuditRecord`: auditoría de consultas B2B. |
| `b2b_idempotency_repository.py` | `IIdempotencyRepository` + `IdempotencyRecord`: `find_within_window`, `save`. |

### `domain/exceptions.py`
Todas las excepciones de negocio (no HTTP). `PokegradingError` es la base. Incluye errores de registro/login (email duplicado, password débil, dominio bloqueado…), de catálogo (carta duplicada, no autorizado), de imágenes (formato, tamaño, polyglot, calidad) y la jerarquía **B2B** (`B2BError` con `code` y `http_status`: `INVALID_API_KEY`, `API_KEY_REVOKED/SUSPENDED/EXPIRED`, `CUSTOMER_SUSPENDED`, `EMPTY_QUERY`, `MALFORMED_QUERY`, `IDEMPOTENCY_KEY_REUSED`, `RATE_LIMIT_EXCEEDED`).

---

## `application/` — Casos de uso

### `application/use_cases/`
| Archivo | Qué contiene |
|---|---|
| `register_user.py` | `RegisterUserUseCase`: valida disclosure, dominio, fortaleza de password, país/idioma, email único; hashea y crea el usuario (rol submitter). |
| `login_user.py` | `LoginUserUseCase`: verifica credenciales y que el usuario esté activo (mismo error para no filtrar la causa). |
| `add_card_to_catalog.py` | `AddCardToCatalogUseCase`: verifica admin, normaliza/valida campos, comprueba identidad única, crea la carta en PENDING. |
| `submit_card_for_evaluation.py` | `SubmitCardForEvaluationUseCase`: valida ambas imágenes (formato, tamaño, polyglot, calidad IQS≥0.60) y crea la submission. Incluye helpers `_detect_content_type`, `_has_polyglot`, `_validate_image`. |
| `quick_search_by_phash.py` | `QuickSearchByPHashUseCase`: **etapa 1** de la búsqueda. Calcula pHash, busca cercanos, confianza = `1 - hamming/64`. Constantes de umbral (`DEFAULT_MAX_HAMMING=12`, `DEFAULT_AUTO_ACCEPT_MAX_HAMMING=6`). |
| `quick_search_card.py` | `QuickSearchCardUseCase`: **etapa 2** (OCR). Define `QuickSearchInput`/`QuickSearchOutput`. Busca por texto y calcula `auto_accepted` contra `confidence_threshold` (0.60). |
| `authenticate_b2b_client.py` | `AuthenticateB2BClientUseCase`: parsea `pkg_<env>_<prefix>_<secret>`, verifica secreto (HMAC, tiempo constante), estado de llave y de customer. |
| `lookup_catalog_coverage.py` | `LookupCatalogCoverageUseCase`: orquesta el lookup B2B (idempotencia → ETag/304 → rate limit → resolución por carta → auditoría). DTOs `OfficialIdentity`, `LookupItemOutput`, `LookupResponse` + (de)serialización JSON para idempotencia. |

### `application/ports/` — Interfaces de servicios externos (puertos)
| Archivo | Qué contiene |
|---|---|
| `password_service.py` | `IPasswordService`: `hash`, `verify`. |
| `card_matching_service.py` | `ICardMatchingService`: `extract_features` (OCR → texto de búsqueda). |
| `image_hash_service.py` | `IImageHashService`: `compute_phash`, `hamming_distance`. |
| `image_quality_service.py` | `IImageQualityService`: `evaluate` → score [0,1]. |
| `api_key_hasher.py` | `IApiKeyHasher`: `hash`, `verify`. |
| `rate_limiter.py` | `IRateLimiter` + `RateLimitVerdict`: `check_and_consume`. |

---

## `infrastructure/` — Implementaciones técnicas

### `infrastructure/persistence/`
| Archivo | Qué contiene |
|---|---|
| `database.py` | Motor SQLAlchemy, `SessionLocal`, `Base` y `get_db()` (dependencia de sesión por request). |
| `models.py` | Todos los modelos ORM (tablas): `UserORM`, `CardORM`, `CardImageORM`, `SubmissionORM`, `B2BCustomerORM`, `ApiKeyORM`, `B2BLookupAuditORM`, `B2BIdempotencyORM`, `B2BRateLimitCounterORM`. Define índices y restricciones únicas. |

#### `infrastructure/persistence/repositories/`
| Archivo | Qué contiene |
|---|---|
| `card/card_repository.py` | `CardRepositoryImpl`: implementa `ICardRepository`. Incluye el ranking por texto (`difflib.SequenceMatcher` en `find_top_candidates`), la búsqueda por pHash (XOR + popcount en `find_by_phash_near`) y la huella ETag (`get_catalog_fingerprint`). |
| `card/image_repository.py` | `CardImageRepositoryImpl`: upsert manual de imágenes (una por card_id+side), portable PostgreSQL/SQLite. |
| `user/user_repository.py` | `UserRepositoryImpl`: CRUD de usuarios + `find_all`, `delete`, mapeo ORM→entidad. |
| `submission_repository.py` | `SubmissionRepositoryImpl`: persistencia de envíos. |
| `b2b/api_key_repository.py` | `ApiKeyRepositoryImpl`: busca por prefijo, guarda, `touch_last_used`. |
| `b2b/customer_repository.py` | `B2BCustomerRepositoryImpl`: busca/guarda customers. |
| `b2b/audit_repository.py` | `B2BAuditRepositoryImpl`: registra auditoría de cada lookup. |
| `b2b/idempotency_repository.py` | `IdempotencyRepositoryImpl`: busca respuesta previa en ventana y la guarda. |

### `infrastructure/matching/` — Visión
| Archivo | Qué contiene |
|---|---|
| `phash_image_hash_service.py` | `PHashImageHashService` (pHash real con `imagehash`+Pillow) y `StubImageHashService` (determinista para tests). |
| `easyocr_card_matching_service.py` | `EasyOCRCardMatchingService`: OCR con EasyOCR (singleton lazy). `extract_tokens_raw` (tokens crudos) y `extract_features` (query filtrada). |
| `stub_card_matching_service.py` | `StubCardMatchingService`: OCR falso para tests/dev (devuelve features sin modelo). |

### `infrastructure/services/`
| Archivo | Qué contiene |
|---|---|
| `pillow_image_quality_service.py` | `PillowImageQualityService`: score de calidad = nitidez(0.55) + exposición(0.30) + resolución(0.15). Helpers `_sharpness`, `_brightness`, `_resolution`. |

### `infrastructure/security/`
| Archivo | Qué contiene |
|---|---|
| `jwt.py` | `JWTService`: emite/decodifica JWT HS256 (con `sub` y `role`). |
| `password.py` | `BcryptPasswordService`: hash/verify de contraseñas con bcrypt. |
| `api_key.py` | `Sha256ApiKeyHasher` (HMAC-SHA256 + pepper, comparación en tiempo constante) y `generate_api_key()` (genera `pkg_<env>_<prefix>_<secret>`). |

### `infrastructure/ratelimit/`
| Archivo | Qué contiene |
|---|---|
| `fixed_window_rate_limiter.py` | `FixedWindowRateLimiter`: rate limit por **cartas** en ventana fija alineada al epoch; maneja concurrencia con `IntegrityError`. |

---

## `api/` — Capa HTTP

### `api/v3/` — API interna (app web)
| Archivo | Qué contiene |
|---|---|
| `dependencies.py` | `get_current_user` (valida JWT + usuario activo en BD) y `require_admin` (exige rol admin). |
| `routers/auth.py` | Endpoints `/auth`: register, login, me, users (listar/actualizar/borrar). |
| `routers/catalog.py` | Endpoints `/catalog`: alta de carta multipart con imagen+pHash (`add_card`), listar/detalle/actualizar/borrar, subir/obtener imágenes. Helpers `_read_image`, `_store_card_image`, `_validate_magic_bytes`. |
| `routers/search.py` | Endpoints `/search`: `quick` (pHash→OCR), `specialized` (OCR), `ocr-extract`. Parser `_parse_card_tokens` y helper `_specialized_search`. |
| `routers/submissions.py` | Endpoints `/submissions`: crear envío, listar (admin), estado, obtener imagen (admin). |
| `schemas/auth.py` | Pydantic de auth: `RegisterRequest/Response`, `LoginRequest/Response`, `UserResponse`, `UpdateUserRequest`. |
| `schemas/catalog.py` | Pydantic de catálogo: `AddCardRequest`, `UpdateCardRequest`, `CardResponse`, `CardDetailResponse`, `ImageUploadResponse`, `CardIdentityResponse`. |
| `schemas/search.py` | Pydantic de búsqueda: `OcrDetectedFields`, `OcrExtractResponse`, `CardCandidateResponse`, `QuickSearchResponse`. |
| `schemas/submission.py` | Pydantic de envíos: `SubmissionResponse`, `SubmissionStatusResponse`, `SubmissionListItem`. |

### `api/b2b/v1/` — API pública para tiendas (versionada aparte)
| Archivo | Qué contiene |
|---|---|
| `dependencies.py` | `get_current_b2b_client` (autentica `X-API-Key`) + dataclass `B2BClient`. |
| `routers/lookup.py` | Endpoint `POST /catalog/lookup`: arma items, ejecuta el use case, maneja ETag/304 y traduce a schemas. |
| `schemas/lookup.py` | Pydantic B2B: `LookupItemRequest`/`LookupRequest`, `OfficialIdentitySchema`, `LookupItemResultSchema`, `LookupResponseSchema`, `B2BErrorDetail`/`B2BErrorResponse`. |

---

## `frontend/src/` — React + Vite
| Archivo | Qué contiene |
|---|---|
| `api.js` | Todas las llamadas HTTP al backend (`BASE='/api/v3'`): auth, catálogo, envíos, búsqueda, OCR. |
| `App.jsx` | Raíz: maneja sesión y pestañas (admin: revisar / agregar / envíos; submitter: enviar). |
| `main.jsx` | Punto de entrada de React. |
| `components/RegisterForm.jsx` | Formulario de registro. |
| `components/LoginForm.jsx` | Formulario de login. |
| `components/AddCardForm.jsx` | Alta de carta: imagen de frente → OCR pre-rellena → admin edita → envía multipart. |
| `components/CardReviewList.jsx` | Admin revisa/aprueba cartas; muestra sus imágenes (`CardImages`). |
| `components/SubmitCardForm.jsx` | Submitter sube frente+reverso para evaluación (con rating previo). |
| `components/SubmissionsAdminList.jsx` | Admin lista todos los envíos (`StatusBadge`). |
| `styles.css`, `App.css`, `index.css` | Estilos. |

---

## Otros directorios

| Ruta | Qué contiene |
|---|---|
| `alembic/versions/` | Migraciones de BD (historial del esquema): usuarios, catálogo, imágenes, submissions, pHash, tablas B2B. |
| `tests/unit/` | Pruebas de casos de uso y servicios aislados (con stubs). |
| `tests/integration/` | Pruebas de endpoints completos (TestClient + SQLite en memoria). |
| `tests/conftest.py` | Fixtures de tests (db, client, usuarios/tokens, helpers de carta y key B2B). |
| `scripts/seed_b2b_api_key.py` | Crea un customer B2B + API key (imprime la llave una sola vez). |
| `scripts/backfill_phash.py` | Recalcula el pHash de imágenes ya guardadas. |
| `scripts/test_b2b_errors.sh` | Prepara/revierte cada escenario de error del API B2B para probar en Swagger. |
| `Sprint1/ Sprint2/ Sprint3/` | Documentación de diseño por sprint (ADRs, diagramas, decisiones). |
| `start.sh`, `start.ps1` | Scripts de arranque (backend + frontend). |
