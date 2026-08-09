# TODO — Sprint 2: Mejoras técnicas y deuda de arquitectura

**Sprint:** 2
**Rama base:** `DevelopmentYitan`

---

## 1. UUID — Migración a UUID v7 + columna para consultas externas

**Contexto:** Actualmente todo el sistema usa `uuid4()` (aleatorio, no ordenable).
UUID v7 incluye timestamp, lo que mejora el rendimiento en índices B-tree de PostgreSQL y permite ordenar por tiempo de creación sin columna extra.

### Tareas

- [x] Evaluar si usar UUID v7 directamente como PK → **Decisión: UUID v7 directo como PK**. El tipo de columna PostgreSQL no cambia (sigue siendo `UUID`), solo cambia el generador Python.
- [x] Instalar librería: `uuid7==0.1.0` (módulo: `uuid_extensions`)
- [x] Reemplazar `uuid4()` por `uuid7()` en:
  - `application/use_cases/register_user.py`
  - `application/use_cases/add_card_to_catalog.py`
  - `infrastructure/persistence/models.py` → `UserORM` y `CardORM`
- [x] Generar migración Alembic → **No necesaria**. El tipo `UUID` en PostgreSQL es el mismo; solo cambia el valor generado en Python.
- [x] Actualizar tests afectados → **Sin cambios necesarios**. 29 passed, 92% coverage.

---

## 2. Documentación del token JWT

**Contexto:** El flujo de autenticación con Bearer token no está documentado formalmente. Un nuevo desarrollador o el equipo de QA no sabe cómo obtener ni usar el token.

### Tareas

- [x] Documentar en `/Sprint2/DOC/flujo-jwt.md` el flujo completo del token:
  - Cómo obtenerlo: `POST /api/v2/auth/login` → `access_token`
  - Cómo usarlo en Swagger UI: botón "Authorize" → `Bearer <token>`
  - Cómo usarlo en PowerShell / curl para pruebas manuales
  - Tiempo de expiración (leer de `settings.jwt_expire_minutes`)
  - Qué contiene el payload: `sub` (user_id), `role`, `exp`
- [x] Agregar descripción del esquema de seguridad en `main.py` (`SecurityScheme` en OpenAPI) para que Swagger muestre el candado correctamente

---

## 3. Actualizar diagramas con nombres de archivos/código

**Contexto:** Los diagramas actuales (secuencia, arquitectura) no referencian los nombres reales de los archivos y clases del proyecto. El "mapa no se respeta" = cuando alguien lee el diagrama y abre el código, no puede identificar dónde está cada cosa.

### Tareas

- [ ] En cada diagrama de secuencia, reemplazar etiquetas genéricas por el nombre real del archivo y clase:
  - `"Router"` → `routers/auth.py → def register()`
  - `"UseCase"` → `application/use_cases/register_user.py → RegisterUserUseCase`
  - `"Repository"` → `infrastructure/persistence/repositories/user_repository.py → UserRepositoryImpl`
  - etc.
- [ ] Actualizar diagrama de flujo de **agregar carta al catálogo** con los nombres de código reales:
  - `routers/catalog.py → def add_card()`
  - `use_cases/add_card_to_catalog.py → AddCardToCatalogUseCase`
  - `infrastructure/persistence/card_repository.py → CardRepositoryImpl`
- [ ] Guardar los diagramas actualizados en `/Sprint2/DOC/diagramas/`

---

## 4. Documentar capa API v1 en diseño

**Contexto:** La carpeta `src/pokegrading/api/v1/` no está documentada en los documentos de diseño del Sprint 1. Un nuevo integrante no sabe qué hace cada archivo ni por qué existe la versión `v1`.

### Estructura actual a documentar:
```
api/
└── v1/
    ├── dependencies.py     ← get_current_user, require_admin
    ├── routers/
    │   ├── auth.py         ← /auth/register, /auth/login
    │   └── catalog.py      ← /catalog/cards CRUD
    └── schemas/
        ├── auth.py         ← RegisterRequest/Response, LoginRequest/Response
        └── catalog.py      ← AddCardRequest, CardDetailResponse
```

### Tareas

- [x] Crear documento `/Sprint2/DOC/diseno-api-v2.md` que explique:
  - Por qué se versiona en `v2` (compatibilidad futura)
  - Qué hace `dependencies.py` y el patrón `Depends()`
  - Diferencia entre schemas (Pydantic / HTTP) y entidades de dominio
  - Cómo se conecta router → use case → repository
- [ ] Relacionar con los diagramas de secuencia del punto 3

---

## 5. Programación Defensiva

**Contexto:** El código confía en que los datos llegan bien desde capas superiores. Hay lugares donde una entrada inesperada podría causar un error no controlado o comportamiento silencioso.

### Tareas

- [x] **`register_user.py`:** Validar que `email` y `alias` no estén vacíos después del `.strip()` antes de continuar
- [x] **`add_card_to_catalog.py`:** Validar que `set_name`, `card_number` y campos de identidad no sean strings vacíos
- [x] **`catalog.py` (router) → `update_card`:** Validar que el `status` recibido sea un valor válido del enum `CardStatus` antes de procesarlo → try/except con 422
- [x] **`user_repository.py` → `save()`:** Manejar IntegrityError en `db.commit()` → relanza `EmailAlreadyExistsError`
- [x] **`jwt.py` → `decode_token()`:** Verificar que el payload contenga `sub` y `role` antes de retornar; lanza ValueError si faltan
- [x] **`dependencies.py` → `get_current_user()`:** Validar que el UUID en `sub` sea parseable antes de la consulta a BD → captura ValueError/AttributeError
- [x] Agregar tests unitarios para los casos defensivos nuevos → **+13 tests** (42 total, 93% cobertura)

---

## 6. Modularización del código — mejor estructura de carpetas

**Contexto:** Actualmente los repositorios, schemas, routers y use cases son archivos sueltos. A medida que el proyecto crece (más entidades), esto se vuelve difícil de navegar. La propuesta es un archivo por módulo dentro de una carpeta por capa.

### Estructura propuesta:

```
src/pokegrading/
│
├── infrastructure/
│   ├── persistence/
│   │   ├── repositories/          ← NUEVA carpeta
│   │   │   ├── __init__.py
│   │   │   ├── user_repository.py     (movido desde persistence/)
│   │   │   └── card_repository.py     (movido desde persistence/)
│   │   ├── models.py
│   │   ├── database.py
│   │   └── __init__.py
│   └── security/
│       ├── jwt.py
│       └── password.py
│
├── api/
│   └── v1/
│       ├── routers/               ← ya es carpeta, OK
│       │   ├── auth.py
│       │   └── catalog.py
│       ├── schemas/               ← ya es carpeta, OK
│       │   ├── auth.py
│       │   └── catalog.py
│       └── dependencies.py
│
├── application/
│   ├── use_cases/                 ← ya es carpeta, OK
│   │   ├── register_user.py
│   │   ├── login_user.py
│   │   └── add_card_to_catalog.py
│   └── ports/
│       └── password_service.py
│
└── domain/
    ├── entities/
    │   ├── user.py
    │   └── card.py
    ├── repositories/              ← interfaces ABC
    │   ├── user_repository.py
    │   └── card_repository.py
    └── value_objects/
        ├── role.py
        ├── card_status.py
        └── card_identity.py
```

### Tareas

- [x] Crear carpeta `infrastructure/persistence/repositories/` y mover `user_repository.py` y `card_repository.py` ahí
- [x] Actualizar todos los imports que referencian las rutas viejas:
  - `routers/auth.py`
  - `routers/catalog.py`
  - `tests/conftest.py`
  - cualquier otro archivo con `from pokegrading.infrastructure.persistence.user_repository import ...`
- [x] Verificar que los tests sigan pasando tras el refactor: `python -m pytest tests/ -v` → **29 passed, 92% coverage**
- [x] Evaluar si `models.py` conviene separarse en `models/user_model.py` y `models/card_model.py` cuando haya más entidades (dejar como nota para Sprint 3+)

---

---

## 7. US-001 — Actualizar: Registrar cuenta (requisitos extendidos)

**Contexto:** La US-001 actual cubre los criterios básicos. La versión actualizada agrega validaciones de país, reglas de contraseña más estrictas, bloqueo de dominios descartables, campos nuevos (país, idioma) y mensajes de error por campo.

### Cambios en dominio (`domain/`)

- [x] **`entities/user.py`:** Agregar campos `country: str` e `preferred_language: str` (default `"es"`) a la entidad `User`
- [x] **`value_objects/`:** Crear `country.py` con enum/listado de países soportados: `CR, PA, MX, CO, CL, AR`
- [x] **`value_objects/`:** Crear `language.py` con enum `es` (default) / `en`
- [x] **`exceptions.py`:** Agregar excepciones nuevas:
  - `CountryNotSupportedError`
  - `PasswordTooWeakError` (longitud mínima + al menos 1 mayúscula + al menos 1 dígito)
  - `BlockedEmailDomainError` (dominios descartables / no autorizados)

### Cambios en aplicación (`application/`)

- [x] **`use_cases/register_user.py` → `RegisterUserInput`:** Agregar campos `country` y `preferred_language`
- [x] **`use_cases/register_user.py` → `execute()`:** Agregar validaciones en orden:
  1. `accept_disclosure == False` → `DisclosureNotAcceptedError`
  2. Dominio del correo en lista bloqueada → `BlockedEmailDomainError`
  3. Formato de contraseña (longitud + mayúscula + dígito) → `PasswordTooWeakError`
  4. País no soportado → `CountryNotSupportedError`
  5. Email duplicado → `EmailAlreadyExistsError`
- [x] Crear lista de dominios bloqueados en `domain/value_objects/blocked_domains.py`

### Cambios en infraestructura (`infrastructure/`)

- [x] **`persistence/models.py` → `UserORM`:** Agregar columnas `country` (String(2)) y `preferred_language` (String(5), default `"es"`)
- [x] **`persistence/user_repository.py` → `save()` y `_to_entity()`:** Mapear los campos nuevos
- [x] Generar migración Alembic: `add_country_language_to_users` (revision `5b9c8ddf442f`)

### Cambios en API (`api/v2/`)

- [x] **`schemas/auth.py` → `RegisterRequest`:** Agregar `country: str` y `preferred_language: str = "es"`
- [x] **`schemas/auth.py` → `RegisterResponse`:** Incluir `country` y `preferred_language` en respuesta
- [x] **`routers/auth.py` → `register()`:** Mapear campos nuevos al `RegisterUserInput`; capturar `CountryNotSupportedError` → 422, `PasswordTooWeakError` → 422, `BlockedEmailDomainError` → 422

### Cambios en tests (`tests/`)

- [x] Agregar tests para cada nuevo criterio de aceptación — **+8 tests** (50 total, 94% cobertura):
  - `test_register_with_unsupported_country_raises`
  - `test_register_with_blocked_email_domain_raises`
  - `test_register_password_too_short_raises`
  - `test_register_password_no_uppercase_raises`
  - `test_register_password_no_digit_raises`
  - `test_register_with_valid_country_and_language`
  - `test_register_default_language_is_spanish`
  - `test_register_country_case_insensitive`

### Criterios de aceptación actualizados

| # | Criterio |
|---|---|
| AC-01 | email válido + password válida + alias + país soportado + disclosure → 201 + JWT |
| AC-02 | Email duplicado → 409 |
| AC-03 | Formato email inválido → 422 |
| AC-04 | Contraseña sin longitud mínima, sin mayúscula o sin dígito → 422 con campo específico |
| AC-05 | `accept_disclosure = false` → 400 |
| AC-06 | País no en listado `[CR, PA, MX, CO, CL, AR]` → 422 |
| AC-07 | Dominio de correo descartable/bloqueado → 422 |
| AC-08 | Idioma preferido default = `"es"`; alternativo `"en"` |
| AC-09 | Rol default = Submitter; cuenta activa sin confirmación por correo |
| AC-10 | Contraseña nunca devuelta ni almacenada en texto plano |

---

## 8. US-002 — Actualizar: Agregar carta al catálogo (requisitos extendidos)

**Contexto:** La US-002 actual cubre identidad + estado PENDING. La versión actualizada agrega campos de display (nombre, rareza, tipo, HP, ilustrador, año), subida de imagen de referencia, auditoría completa y más validaciones canónicas.

### Cambios en dominio (`domain/`)

- [x] **`entities/card.py`:** Agregar campos de display opcionales:
  - `rarity: str | None` — enum canónico: `Common, Uncommon, Rare, Holo Rare, Ultra Rare, Secret Rare`
  - `pokemon_type: str | None` — tipos válidos de Pokémon
  - `hp: int | None` — numérico
  - `illustrator: str | None`
  - `print_year: int | None`
  - `reference_image_front_url: str | None`
  - `reference_image_back_url: str | None`
- [x] **`value_objects/`:** Crear `rarity.py` con enum de rarezas canónicas → `CardRarity`
- [x] **`value_objects/`:** Crear `pokemon_type.py` con enum de tipos válidos → `PokemonType`
- [x] **`exceptions.py`:** Agregar:
  - `InvalidRarityError`
  - `InvalidPokemonTypeError`
  - `InvalidImageError` → **diferido a Sprint 3** (requiere lógica de subida real de archivos)

### Cambios en aplicación (`application/`)

- [x] **`use_cases/add_card_to_catalog.py` → `AddCardInput`:** Agregar campos de display
- [x] **`use_cases/add_card_to_catalog.py` → `execute()`:** Agregar validaciones:
  1. Identidad completa (campos requeridos no vacíos)
  2. Rareza dentro del enum canónico → `InvalidRarityError`
  3. Tipo dentro de los tipos válidos → `InvalidPokemonTypeError`
  4. HP numérico positivo si se provee
  6. Duplicado de identidad → `CardAlreadyExistsError`
- [x] **Auditoría:** `created_by`, `created_at` y `version=1` se generan en el use case; inmutables

### Cambios en infraestructura (`infrastructure/`)

- [x] **`persistence/models.py` → `CardORM`:** Agregar columnas `rarity`, `pokemon_type`, `hp`, `illustrator`, `print_year`
- [ ] **Subida de imágenes:** Interfaz `IImageStorage` → **diferido a Sprint 3** (ya documentado en decisiones-diseno.md sección 10)
- [x] Migración Alembic `25aa234c2b99`: `add_display_fields_to_cards` — aplicada
- [x] **`persistence/repositories/card/card_repository.py`:** Mapear campos nuevos en `save()` y `_to_entity()`

### Cambios en API (`api/v2/`)

- [x] **`schemas/catalog.py` → `AddCardRequest`:** Agregar campos de display; eliminar URL fields (imágenes van por endpoint dedicado)
- [x] **`schemas/catalog.py` → `CardDetailResponse`:** Incluir todos los campos nuevos + `has_image_front`/`has_image_back: bool`; agregar `ImageUploadResponse`
- [x] **`routers/catalog.py` → `add_card()`:** Capturar `InvalidRarityError`, `InvalidPokemonTypeError`, `InvalidLanguageError`, `ValueError` → 422; responde `CardDetailResponse`
- [x] **`routers/catalog.py` → `add_card()`:** Auditoría: `created_by` = usuario autenticado, `created_at` autogenerado
- [x] **`routers/catalog.py`:** Nuevo endpoint `POST /cards/{card_id}/images/{side}` — upload binario (JPEG/PNG, ≥400×400, ≤10 MB), validación magic bytes + Pillow
- [x] **`routers/catalog.py`:** Nuevo endpoint `GET /cards/{card_id}/images/{side}` — retorna binario con content-type correcto

### Cambios en infraestructura — Imágenes (nuevos)

- [x] **`entities/card_image.py`:** Entidad `CardImage` con `id, card_id, side, content_type, width, height, file_size, data: bytes, uploaded_at, uploaded_by`
- [x] **`repositories/image_repository.py`:** Interfaz `ICardImageRepository` (puerto de dominio)
- [x] **`persistence/models.py` → `CardImageORM`:** Tabla `card_images` con columna `data BYTEA` (LargeBinary); restricción `uq_card_image_side (card_id, side)`
- [x] **`repositories/card/image_repository.py`:** `CardImageRepositoryImpl` — upsert por `(card_id, side)`
- [x] **Migración Alembic `bd596323e1ca`:** `add_card_images_table_and_remove_url_cols` — aplicada

### Cambios en tests (`tests/`)

- [x] `test_add_card_with_invalid_rarity_raises` → `InvalidRarityError`
- [x] `test_add_card_with_invalid_pokemon_type_raises` → `InvalidPokemonTypeError`
- [x] `test_add_card_with_negative_hp_raises` → `ValueError`
- [x] `test_add_card_with_display_fields_returns_201`
- [x] `test_add_card_audit_fields_are_set` (created_by, created_at, version=1)
- [x] `test_add_card_duplicate_identity_returns_409`
- [x] `test_add_card_with_invalid_language_raises` → `InvalidLanguageError`
- [x] Tests de idioma actualizados: `language="English"` → `language="en"` (código ISO 639-1)

### Criterios de aceptación actualizados

| # | Criterio |
|---|---|
| AC-01 | Admin + identidad completa + datos válidos → 201, carta activa, auditoría registrada |
| AC-02 | Submitter/Reviewer → 403 |
| AC-03 | Sin token → 401 |
| AC-04 | Identidad duplicada (set+número+edición+idioma+acabado) → 409 |
| AC-05 | Rareza fuera del listado canónico → 422 |
| AC-06 | Tipo Pokémon inválido → 422 |
| AC-07 | HP no numérico o negativo → 422 |
| AC-08 | Imagen: formato no JPEG/PNG, resolución < 400×400 px o tamaño > 10 MB → 422 ✅ |
| AC-09 | `card_id`, `created_by`, `created_at`, `version=1` autogenerados e inmutables |
| AC-10 | Campos requeridos incompletos → 422 con indicación del campo afectado |
| AC-11 | Idioma fuera de la lista canónica (en, ja, es, fr, de, it, pt, ko, zh, pl, nl, th) → 422 ✅ |

---

## 9. US-003 — Nueva: Enviar carta para evaluación ✅ COMPLETADO

**Historia:** Yo como Submitter quiero enviar mi carta capturada para evaluación para entonces obtener un grado estimado y una recomendación.

### Cambios en dominio (`domain/`)

- [x] **`entities/`:** Crear entidad `Submission` con campos:
  - `id: UUID` (autogenerado, inmutable)
  - `user_id: UUID` (FK al submitter)
  - `card_id: UUID | None` (FK a catálogo, puede ser null si no se identificó)
  - `image_front_data: bytes` (BYTEA inline — ver decisión 15)
  - `image_back_data: bytes`
  - `status: SubmissionStatus` (enum: `PENDING`, `PROCESSING`, `GRADED`, `REJECTED`)
  - `image_quality_score: float | None`
  - `rejection_reason: str | None`
  - `created_at: datetime`
- [x] **`value_objects/`:** Crear `submission_status.py` con el enum anterior
- [x] **`repositories/`:** Crear interfaz `ISubmissionRepository` (ABC) con `save()`, `find_by_id()`, `find_by_user()`
- [x] **`exceptions.py`:** Agregar:
  - `InvalidFileFormatError` (formato no JPEG/PNG)
  - `FileTooLargeError` (supera 10 MB)
  - `PolyglotDetectedError` (archivo malicioso disfrazado de imagen)
  - `ImageQualityBelowThresholdError` (IQS bajo el mínimo 0.60)
  - `BothImagesRequiredError` (intento de envío sin frente y reverso)

### Cambios en aplicación (`application/`)

- [x] **`use_cases/`:** Crear `submit_card_for_evaluation.py` → `SubmitCardForEvaluationUseCase`
  - Input: `user_id`, `image_front_data` (bytes), `image_back_data` (bytes), `card_id` (opcional)
  - Validaciones en orden:
    1. Ambas imágenes presentes → `BothImagesRequiredError`
    2. Formato JPEG/PNG (magic bytes) → `InvalidFileFormatError`
    3. Tamaño ≤ 10 MB → `FileTooLargeError`
    4. Detección de polyglot (PK\x05\x06, %PDF-, \x7fELF) → `PolyglotDetectedError`
    5. Image Quality Score ≥ 0.60 → `ImageQualityBelowThresholdError`
  - Al pasar validaciones: crea `Submission`, persiste, retorna `evaluation_id` + `status=PENDING`
  - Output: `evaluation_id`, `status = "pending"`, timestamp de recepción
- [x] **`ports/`:** Crear `IImageQualityService` (ABC) — stub devuelve 0.85 en Sprint 2

### Cambios en infraestructura (`infrastructure/`)

- [x] **`persistence/models.py`:** Agregar `SubmissionORM` con columnas correspondientes
- [x] **`persistence/repositories/`:** Crear `submission_repository.py` → `SubmissionRepositoryImpl`
- [x] Migración Alembic: `e269249ec3a9_create_submissions_table.py` — aplicada ✅

### Cambios en API (`api/v2/`)

- [x] **`schemas/`:** Crear `submission.py` con `SubmissionResponse` y `SubmissionStatusResponse`
- [x] **`routers/`:** Crear `submissions.py` con:
  - `POST /submissions` — acepta `multipart/form-data` con `image_front` e `image_back`; requiere token (cualquier rol)
  - `GET /submissions/{evaluation_id}` — consulta estado del envío
- [x] Registrar el router en `main.py` (`prefix="/api/v2"`)
- [x] Capturar todas las excepciones nuevas → códigos HTTP apropiados (422 / 413)

### Cambios en tests (`tests/`)

- [x] `test_submit_without_front_image_raises` → `BothImagesRequiredError`
- [x] `test_submit_without_back_image_raises` → `BothImagesRequiredError`
- [x] `test_submit_with_invalid_front_format_raises` → `InvalidFileFormatError`
- [x] `test_submit_with_invalid_back_format_raises` → `InvalidFileFormatError`
- [x] `test_submit_exceeding_size_raises` → `FileTooLargeError`
- [x] `test_submit_polyglot_raises` → `PolyglotDetectedError`
- [x] `test_submit_low_quality_raises` → `ImageQualityBelowThresholdError`
- [x] `test_submit_valid_returns_pending_submission` → `status="pending"`, `evaluation_id` presente
- [x] `test_submit_without_token_returns_401` (integración)
- [x] `test_submit_valid_returns_201` (integración)

**Total tests: 67, cobertura: 94.55%**

### Criterios de aceptación

| # | Criterio |
|---|---|
| AC-01 | Frente + reverso + formato válido + IQS ≥ umbral → 201, `evaluation_id` único generado |
| AC-02 | Falta frente o reverso → 422 indicando imagen faltante |
| AC-03 | Formato no JPEG/PNG → 422 con causa |
| AC-04 | Archivo > 10 MB → 413 con causa |
| AC-05 | Polyglot detectado → 422 con mensaje de seguridad + entrada en auditoría |
| AC-06 | IQS bajo umbral → 422 indicando causa (borroso/encuadre/iluminación) |
| AC-07 | Sistema saturado → 202 Accepted con tiempo estimado |
| AC-08 | Imágenes almacenadas según política de retención |
| AC-09 | Sin token → 401 |

---

## 10. US-004 — Nueva: Realizar búsqueda rápida de carta

**Historia:** Yo como Submitter quiero que el sistema identifique automáticamente mi carta con una búsqueda rápida para entonces no tener que ingresar manualmente sus atributos.

### Cambios en dominio (`domain/`)

- [x] **`entities/`:** Crear entidad `SearchResult` (value object o entidad ligera):
  - `candidate_card_id: UUID`
  - `confidence_score: float` (0.0 – 1.0)
  - `rank: int` (1, 2, 3)
- [x] **`repositories/`:** Agregar método `find_top_candidates(image_features, limit=3)` a `ICardRepository`
- [x] **`exceptions.py`:** Agregar:
  - `NoMatchFoundError` (ningún candidato supera el umbral mínimo)
  - `ImageNotIdentifiableError` (imagen no permite identificación visual → deriva a flujo manual)

### Cambios en aplicación (`application/`)

- [x] **`use_cases/`:** Crear `quick_search_card.py` → `QuickSearchCardUseCase`
  - Input: `image_front` (bytes o features extraídos), `confidence_threshold: float`
  - Lógica:
    1. Extraer features de la imagen (delegado a `ICardMatchingService`)
    2. Consultar `ICardRepository.find_top_candidates()` → lista de hasta 3 candidatos
    3. Si candidato #1 supera `confidence_threshold` → aceptación automática, avanza al siguiente paso
    4. Si ninguno supera umbral → `NoMatchFoundError` (escala a búsqueda especializada)
    5. Si imagen no es identificable → `ImageNotIdentifiableError` (deriva a flujo manual)
  - Output: lista de `SearchResult` + flag `auto_accepted: bool`
- [x] **`ports/`:** Crear `ICardMatchingService` (ABC) — interfaz para el motor de matching visual; permite mockear en tests

### Cambios en infraestructura (`infrastructure/`)

- [x] **`persistence/repositories/card_repository.py`:** Implementar `find_top_candidates()` — en desarrollo puede ser búsqueda por texto/nombre; en producción se conecta al servicio de ML
- [x] **`matching/`:** Crear carpeta `infrastructure/matching/` con implementación stub de `ICardMatchingService` para desarrollo/tests

### Cambios en API (`api/v2/`)

- [x] **`schemas/`:** Agregar `CardCandidateResponse` y `QuickSearchResponse` (lista de candidatos con `candidate_card_id`, `confidence_score`, `rank`, `name`, `set_name`)
- [x] **`routers/search.py`:** Nuevo endpoint:
  - `POST /search/quick` — acepta imagen JPEG/PNG + `q` opcional; requiere token; devuelve top 3 candidatos
- [x] Manejar `NoMatchFoundError` → 404 con indicación de escalar a búsqueda especializada
- [x] Manejar `ImageNotIdentifiableError` → 422 con indicación de flujo manual

### Cambios en tests (`tests/`)

- [x] `test_quick_search_returns_candidates` (unit + integración)
- [x] `test_quick_search_auto_accepted_when_exact_match` / `test_auto_accepted_when_top_exceeds_threshold`
- [x] `test_quick_search_query_no_match_returns_404` / `test_query_hint_no_match_raises_no_match_found`
- [x] `test_quick_search_no_features_no_query_returns_422` / `test_no_query_hint_and_stub_raises_not_identifiable`
- [x] `test_quick_search_without_token_returns_401`
- [x] `test_quick_search_with_ml_features_override` (override de `ICardMatchingService`)
- [x] `test_quick_search_only_returns_active_cards`
- [x] `test_spanish_card_found_by_same_name`

**Total tests: 94, cobertura: 95.10%**

### Criterios de aceptación

| # | Criterio |
|---|---|
| AC-01 | Imagen válida → devuelve hasta 3 candidatos con `card_id` y `confidence_score` |
| AC-02 | Candidato #1 supera umbral → `auto_accepted = true`, avanza al siguiente paso |
| AC-03 | Ningún candidato supera umbral → 404, indicación de búsqueda especializada |
| AC-04 | Imagen no identificable visualmente → 422, deriva a flujo manual |
| AC-05 | Sin token → 401 |
| AC-06 | `confidence_threshold` configurable (no hardcodeado) |

---

## Resumen de prioridades

| # | Tarea | Prioridad | Esfuerzo estimado |
|---|---|---|---|
| 1 | UUID v7 | Media | Medio |
| 2 | Documentar token JWT | Alta | Bajo |
| 3 | Diagramas con nombres de código | Alta | Bajo |
| 4 | Documentar capa API v1 | Media | Bajo |
| 5 | Programación defensiva | Alta | Medio |
| 6 | Modularización de carpetas | Media | Medio |
| 7 | US-001 actualizada (país, idioma, dominios bloqueados) | Alta | Alto |
| 8 | US-002 actualizada (display, imagen, auditoría, rarezas) | Alta | Alto |
| 9 | US-003 nueva (enviar carta para evaluación) | Alta | Muy alto |
| 10 | US-004 nueva (búsqueda rápida de carta) | Alta | Muy alto |
