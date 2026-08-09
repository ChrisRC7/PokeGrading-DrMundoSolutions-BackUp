# Guía del Proyecto PokéGrading — Organización y Flujo del Código

> Documento de referencia para **entender, explicar y defender** el código.
> Cubre: qué contiene cada carpeta, cómo se conectan las capas y el flujo
> paso a paso de cada función importante (backend + frontend).

---

## 1. ¿Qué es el proyecto?

**PokéGrading** es un sistema para catalogar y evaluar cartas Pokémon TCG. Tiene tres grandes funciones:

1. **Catálogo de referencia** — administradores dan de alta cartas oficiales (con imagen de frente obligatoria).
2. **Búsqueda e identificación de cartas por imagen** — pHash (rápido) con escalamiento a OCR (EasyOCR).
3. **Envío de cartas físicas para evaluación de grado** — el usuario sube frente y reverso, se validan y quedan pendientes.
4. **API B2B** — tiendas externas consultan, con API key, si una carta está cubierta por el catálogo.

### Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, **FastAPI**, SQLAlchemy 2 (ORM), Pydantic v2 |
| Base de datos | PostgreSQL (producción/dev), SQLite en memoria (tests) |
| Migraciones | Alembic |
| Seguridad | JWT (python-jose), bcrypt (passwords), HMAC-SHA256 (API keys B2B) |
| Visión | `imagehash` + Pillow (pHash), EasyOCR + torch (OCR), Pillow (calidad) |
| Frontend | React + Vite (JavaScript) |
| Tests | pytest (unit + integration) |

---

## 2. La arquitectura: Clean Architecture (Arquitectura Limpia)

El código está organizado en **4 capas concéntricas**. La regla de oro: **las dependencias apuntan hacia adentro**. El dominio no sabe nada de FastAPI ni de SQLAlchemy.

```
        ┌─────────────────────────────────────────────┐
        │                  api/                         │  ← FastAPI: HTTP, routers, schemas
        │   ┌─────────────────────────────────────┐    │
        │   │           application/               │    │  ← Casos de uso (orquestación) + puertos
        │   │   ┌─────────────────────────────┐    │    │
        │   │   │         domain/             │    │    │  ← Entidades, reglas de negocio, interfaces
        │   │   └─────────────────────────────┘    │    │
        │   └─────────────────────────────────────┘    │
        └─────────────────────────────────────────────┘
                          ▲
                          │ implementa los "puertos" (interfaces)
        ┌─────────────────────────────────────────────┐
        │             infrastructure/                   │  ← BD, JWT, OCR, pHash, rate limiter
        └─────────────────────────────────────────────┘
```

### ¿Por qué esta separación? (argumento de defensa)

- **El dominio es puro**: las reglas de negocio (ej. "el aprobador no puede ser el creador") viven en entidades sin dependencias externas → fáciles de probar y de razonar.
- **Los puertos invierten la dependencia**: el caso de uso pide una interfaz (`ICardRepository`, `IImageHashService`); la infraestructura la implementa. Esto permite **cambiar PostgreSQL por otra BD, o EasyOCR por otro motor, sin tocar la lógica de negocio**.
- **Testabilidad**: en los tests inyectamos stubs (`StubImageHashService`, SQLite) sin levantar servicios pesados.

### Las 4 capas en una frase

| Capa | Responsabilidad | Ejemplo |
|---|---|---|
| `domain/` | Qué *es* el negocio y sus reglas | `Card.approve()` rechaza autoaprobación |
| `application/` | Qué *hace* el negocio (orquesta pasos) | `AddCardToCatalogUseCase` |
| `infrastructure/` | *Cómo* se hace técnicamente | `CardRepositoryImpl` (SQLAlchemy) |
| `api/` | Cómo se *expone* por HTTP | `POST /api/v3/catalog/cards` |

---

## 3. Estructura de carpetas detallada

```
PokeGrading-DrMundoSolutions/
├── src/pokegrading/          ← TODO el backend
│   ├── main.py               ← Arranque FastAPI: routers, CORS, manejo de errores, OpenAPI
│   ├── config.py             ← Settings (lee .env): BD, JWT, B2B
│   │
│   ├── domain/               ← CAPA 1: dominio puro (sin frameworks)
│   │   ├── entities/         ← Objetos de negocio con reglas
│   │   ├── value_objects/    ← Tipos cerrados / enums de negocio
│   │   ├── repositories/     ← INTERFACES de persistencia (puertos de salida)
│   │   └── exceptions.py     ← Excepciones de negocio (no HTTP)
│   │
│   ├── application/          ← CAPA 2: casos de uso
│   │   ├── use_cases/        ← Un archivo por historia de usuario
│   │   └── ports/            ← INTERFACES de servicios externos (hash, OCR, calidad…)
│   │
│   ├── infrastructure/       ← CAPA 3: implementaciones técnicas
│   │   ├── persistence/      ← SQLAlchemy: models.py, database.py, repositories/
│   │   ├── security/         ← jwt.py, password.py, api_key.py
│   │   ├── matching/         ← pHash y OCR (phash_..., easyocr_..., stub_...)
│   │   ├── services/         ← pillow_image_quality_service.py
│   │   └── ratelimit/        ← fixed_window_rate_limiter.py
│   │
│   └── api/                  ← CAPA 4: HTTP
│       ├── v3/               ← API interna (app web)
│       │   ├── routers/      ← auth, catalog, search, submissions
│       │   ├── schemas/      ← Pydantic request/response
│       │   └── dependencies.py ← get_current_user, require_admin
│       └── b2b/v1/           ← API pública para tiendas (separada, versionada aparte)
│           ├── routers/lookup.py
│           ├── schemas/
│           └── dependencies.py
│
├── frontend/src/             ← React + Vite
│   ├── api.js                ← Todas las llamadas HTTP al backend (BASE = '/api/v3')
│   ├── App.jsx               ← Raíz: maneja sesión y pestañas (admin vs submitter)
│   └── components/           ← Un componente por pantalla/formulario
│
├── tests/
│   ├── unit/                 ← Prueban casos de uso y servicios aislados
│   └── integration/          ← Prueban endpoints HTTP completos (TestClient + SQLite)
│
├── alembic/versions/         ← Migraciones de BD (historial del esquema)
├── requirements.txt          ← Dependencias backend
├── start.sh / start.ps1      ← Scripts de arranque (backend + frontend)
└── Sprint1/ Sprint2/ Sprint3 ← Documentación de diseño por sprint
```

### Detalle de `domain/value_objects/`

Son tipos **cerrados** que validan contra listas canónicas. Defienden la integridad de los datos:

- `role.py` — `UserRole` (admin / submitter)
- `card_status.py` — `CardStatus` (pending / active / retired)
- `submission_status.py` — `SubmissionStatus`
- `card_identity.py` — `CardIdentityTuple` (set + número + edición + idioma + finish = **identidad única** de una carta)
- `language.py`, `country.py`, `rarity.py`, `pokemon_type.py`, `card_edition.py`, `card_finish.py` — enums de catálogo
- `api_key_status.py`, `b2b_customer_status.py`, `lookup_result_status.py` — estados del flujo B2B
- `blocked_domains.py` — dominios de email bloqueados al registrarse

---

## 4. Modelo de datos (tablas)

Definidas en [models.py](src/pokegrading/infrastructure/persistence/models.py):

| Tabla | Entidad | Notas clave |
|---|---|---|
| `users` | `UserORM` | email único, rol, país, idioma, `hashed_password` (bcrypt) |
| `catalog_cards` | `CardORM` | **UNIQUE** sobre (set, número, edición, idioma, finish); `status`, `version`, `created_by`, `approved_by` |
| `card_images` | `CardImageORM` | binario en BYTEA (`data`), `phash` (16 hex, indexado), UNIQUE (card_id, side) |
| `submissions` | `SubmissionORM` | frente+reverso BYTEA, `image_quality_score`, `status` |
| `b2b_customers` | `B2BCustomerORM` | tiendas que consumen el API B2B |
| `api_keys` | `ApiKeyORM` | `key_prefix` público indexado + `hashed_secret` (HMAC) |
| `b2b_lookup_audit` | `B2BLookupAuditORM` | auditoría de cada consulta B2B |
| `b2b_idempotency` | `B2BIdempotencyORM` | respuesta guardada por (api_key, request_id) |
| `b2b_rate_limit_counters` | `B2BRateLimitCounterORM` | cartas consumidas por ventana |

**Punto de defensa**: las imágenes se guardan como BYTEA en la BD (suficiente para desarrollo). En producción se migrarían a Azure Blob Storage cambiando `data BYTEA` por `blob_name VARCHAR` — sin tocar el dominio, porque el dominio solo conoce la entidad `CardImage`, no cómo se persiste.

---

## 5. Flujo de cada endpoint (paso a paso)

> Patrón común en TODOS los endpoints:
> **Router** (HTTP, valida formato, traduce errores a status) → **Use Case** (reglas de negocio) → **Repository/Service** (técnica) → **BD**.
> El router atrapa excepciones de dominio y las convierte en códigos HTTP. El mapeo central está en [main.py](src/pokegrading/main.py#L85) (`_DOMAIN_STATUS_MAP`).

### 5.1 Autenticación — [auth.py](src/pokegrading/api/v3/routers/auth.py)

#### `POST /auth/register` (US-001)
1. Recibe JSON (`RegisterRequest`).
2. Llama `RegisterUserUseCase.execute()` → [register_user.py](src/pokegrading/application/use_cases/register_user.py):
   - Verifica que aceptó el disclosure (si no → `DisclosureNotAcceptedError`).
   - Normaliza email/alias.
   - Bloquea dominios de email prohibidos.
   - Valida fortaleza de contraseña (≥8, 1 mayúscula, 1 dígito).
   - Valida país contra `SupportedCountry`; idioma cae a `es` si no es válido.
   - Verifica email no duplicado.
   - Hashea la contraseña con bcrypt (`BcryptPasswordService`).
   - Crea `User` con rol `SUBMITTER` y lo persiste.
3. El router genera un **JWT** y lo devuelve junto al perfil.

#### `POST /auth/login`
1. `LoginUserUseCase` busca por email normalizado.
2. Verifica password con bcrypt; si falla **o** usuario inactivo → `InvalidCredentialsError` (mismo error para no filtrar qué parte falló).
3. Devuelve JWT.

#### `GET /auth/me`, `GET/PUT/DELETE /auth/users`
- `me` devuelve el usuario del token.
- Los de `/users` requieren `require_admin`. `delete` impide borrarse a sí mismo.

#### Autenticación interna — [dependencies.py](src/pokegrading/api/v3/dependencies.py)
- `get_current_user`: lee el header `Bearer`, decodifica el JWT, extrae `sub` (UUID), **verifica que el usuario exista y esté activo en BD** (el JWT por sí solo no basta). Sin token → 401.
- `require_admin`: encima de `get_current_user`, exige `role == admin` o lanza 403.

---

### 5.2 Catálogo — [catalog.py](src/pokegrading/api/v3/routers/catalog.py)

#### `POST /catalog/cards` (US-002) — **el flujo integrado más importante**
Petición `multipart/form-data`: campos de identidad + `image_front` (**obligatoria**) + `image_back` (opcional).

Orden (importa para no dejar cartas sin imagen):
1. **Valida las imágenes ANTES de crear la carta** con `_read_image()`:
   - content-type permitido (jpeg/png),
   - tamaño ≤ 10 MB,
   - **magic bytes** coinciden con el tipo declarado (`_validate_magic_bytes`),
   - resolución mínima 150×150 px (con Pillow).
2. Crea la carta con `AddCardToCatalogUseCase.execute()` → [add_card_to_catalog.py](src/pokegrading/application/use_cases/add_card_to_catalog.py):
   - Verifica que el creador sea **admin** (defensa en profundidad, no confía solo en el router).
   - Normaliza campos, valida idioma/rareza/tipo/HP.
   - Construye la `CardIdentityTuple` y verifica que **no exista** ya (si existe → 409).
   - La carta nace en estado **PENDING** (requiere doble validación para pasar a ACTIVE).
3. Guarda la imagen con `_store_card_image()`:
   - calcula el **pHash** (`PHashImageHashService.compute_phash`),
   - persiste `CardImage` con su pHash.
4. Devuelve el detalle con `has_image_front = true`.

> **Punto clave de defensa**: la **misma** imagen de frente sirve para (a) pre-rellenar el formulario por OCR antes de enviar, (b) guardarse como referencia y (c) generar el pHash que permite la búsqueda rápida. Antes estaban separados y por eso una carta podía quedar sin huella → no buscable.

#### Otros endpoints de catálogo
- `GET /catalog/cards` y `GET /catalog/cards/{id}` — listar / detalle (requieren login).
- `PUT /catalog/cards/{id}` — actualizar (admin). Si el nuevo estado es ACTIVE llama `card.approve()` (que **rechaza que el aprobador sea el creador** — doble validación).
- `DELETE /catalog/cards/{id}` — borrar (admin).
- `POST /catalog/cards/{id}/images/{side}` — reemplazar/subir imagen posterior (reutiliza `_read_image` + `_store_card_image`).
- `GET /catalog/cards/{id}/images/{side}` — devuelve el binario de la imagen.

---

### 5.3 Búsqueda por imagen — [search.py](src/pokegrading/api/v3/routers/search.py)

Esta es la pieza con la lógica de **pHash → OCR → revisión manual**.

#### `POST /search/quick` (US-004) — búsqueda rápida con escalamiento
1. Lee y valida la imagen (jpeg/png por magic bytes).
2. **Etapa 1 — pHash** (`QuickSearchByPHashUseCase`) → [quick_search_by_phash.py](src/pokegrading/application/use_cases/quick_search_by_phash.py):
   - calcula el pHash de la imagen subida,
   - busca cartas activas con pHash cercano (`find_by_phash_near`),
   - si hay candidatos → responde `match_engine = "phash"`.
3. Si el pHash no resuelve (sin coincidencias o imagen ilegible) → **Etapa 2 — OCR** (`_specialized_search`):
   - corre EasyOCR, parsea nombre + número, busca por texto,
   - responde `match_engine = "ocr"`.
4. Si tampoco hay match → 404 → el frontend lo trata como **"revisión manual"**.

##### ¿Cómo funciona el umbral del pHash? (pregunta típica de defensa)
El pHash es un hash perceptual de **64 bits**. La similitud entre dos imágenes se mide con la **distancia de Hamming** (cuántos bits difieren). La confianza:

```
confidence = 1.0 - (distancia_hamming / 64)
```

Dos umbrales (constantes en [quick_search_by_phash.py](src/pokegrading/application/use_cases/quick_search_by_phash.py#L17-L18)):

| Umbral | Constante | Hamming máx | Similitud mínima |
|---|---|---|---|
| Aparece como candidato | `DEFAULT_MAX_HAMMING = 12` | ≤ 12 bits | ≥ **81.25 %** |
| Auto-aceptado | `DEFAULT_AUTO_ACCEPT_MAX_HAMMING = 6` | ≤ 6 bits | ≥ **90.6 %** |

- Misma imagen → Hamming 0 → 100 %.
- Para ajustar la sensibilidad se cambian esas constantes (bajar `max_hamming` = menos falsos positivos; subirlo = más recall).

#### `POST /search/specialized` — búsqueda solo por OCR
Igual que la etapa 2 anterior; se usa cuando ya se sabe que el pHash no sirve.

#### `POST /search/ocr-extract` — extraer texto (admin, no persiste)
- Corre EasyOCR sobre la imagen y devuelve `raw_text` + `detected` (nombre, HP, número).
- Lo usa el formulario de alta para **pre-rellenar** los campos.

##### El parser OCR — `_parse_card_tokens()`
A partir de los tokens crudos de EasyOCR extrae:
- **card_number**: patrón `\d+/\d+` (ej. "025/185"),
- **hp**: número adyacente al token "HP",
- **name**: primeros tokens significativos (salta indicadores de stage y números).

---

### 5.4 Envíos para evaluación — [submissions.py](src/pokegrading/api/v3/routers/submissions.py)

#### `POST /submissions` (US-003)
1. Lee bytes de frente y reverso.
2. `SubmitCardForEvaluationUseCase.execute()` → [submit_card_for_evaluation.py](src/pokegrading/application/use_cases/submit_card_for_evaluation.py), validación en orden determinista:
   1. ambas imágenes presentes,
   2. formato JPEG/PNG (por magic bytes),
   3. tamaño ≤ 10 MB,
   4. **sin polyglot** (`_has_polyglot`: busca firmas de ZIP/PDF/ELF/PE en cabecera y cola — defensa contra archivos camuflados como imagen),
   5. **calidad de imagen** (IQS) ≥ 0.60 en ambas caras.
3. Guarda la submission en estado PENDING con el IQS promedio.

#### Otros
- `GET /submissions` — lista (admin).
- `GET /submissions/{id}` — estado de un envío.
- `GET /submissions/{id}/images/{side}` — imagen del envío (admin; infiere content-type por magic bytes).

##### Calidad de imagen — [pillow_image_quality_service.py](src/pokegrading/infrastructure/services/pillow_image_quality_service.py)
Score [0,1] = media ponderada de tres métricas:
- **Nitidez** (55 %): varianza del filtro de bordes (aproxima el Laplaciano). Borrosa → bajo.
- **Exposición** (30 %): brillo medio; penaliza solo extremos (<30 o >225).
- **Resolución** (15 %): penaliza por debajo de 150 px de lado menor.

---

### 5.5 API B2B — [lookup.py](src/pokegrading/api/b2b/v1/routers/lookup.py)

Está **separada** del API interna: vive en `/api/b2b/v1` y se versiona aparte. Es de **solo lectura** (nunca dispara grading ni descuenta cuota).

#### `POST /api/b2b/v1/catalog/lookup` (US-005)
1. Autentica la API key (`get_current_b2b_client` → `AuthenticateB2BClientUseCase`):
   - parsea `pkg_<env>_<prefix>_<secret>`,
   - busca por prefix (indexado, O(1)) y verifica el secreto con **HMAC-SHA256 + pepper** en tiempo constante,
   - revisa estado de la llave (revoked/suspended/expired+gracia) y del customer.
   - **Defensa**: prefix válido + secreto incorrecto y llave revocada devuelven el **mismo** error → no se filtra información.
2. `LookupCatalogCoverageUseCase.execute()` → [lookup_catalog_coverage.py](src/pokegrading/application/use_cases/lookup_catalog_coverage.py):
   1. **Idempotencia**: si llega un `request_id` ya visto en la ventana → devuelve la misma respuesta sin recontar (si el contenido difiere → 409).
   2. **ETag / If-None-Match**: si el catálogo no cambió → 304 Not Modified.
   3. **Rate limit** por cantidad de cartas (`FixedWindowRateLimiter`, ventana fija alineada al epoch).
   4. **Resuelve cada carta** independientemente → `covered` / `multiple_match` / `not_covered` / `invalid_params`.
   5. **Audita** la consulta y guarda la respuesta idempotente.
3. Devuelve el resumen + resultado por carta, con `ETag`.

**Formato de error único**: cualquier `B2BError` se serializa igual (code, message, field, card_ref, trace_id) por el handler en [main.py](src/pokegrading/main.py#L103). Errores inesperados se envuelven en `INTERNAL_ERROR` (500) sin dejar estado parcial.

---

## 6. Servicios de infraestructura clave

| Servicio | Archivo | Qué hace | Puerto (interfaz) |
|---|---|---|---|
| pHash | [phash_image_hash_service.py](src/pokegrading/infrastructure/matching/phash_image_hash_service.py) | hash perceptual 64 bits + distancia Hamming | `IImageHashService` |
| OCR | [easyocr_card_matching_service.py](src/pokegrading/infrastructure/matching/easyocr_card_matching_service.py) | lee texto con EasyOCR (singleton lazy) | `ICardMatchingService` |
| Calidad | [pillow_image_quality_service.py](src/pokegrading/infrastructure/services/pillow_image_quality_service.py) | score nitidez/brillo/resolución | `IImageQualityService` |
| JWT | [jwt.py](src/pokegrading/infrastructure/security/jwt.py) | emite/decodifica HS256 | — |
| Password | [password.py](src/pokegrading/infrastructure/security/password.py) | bcrypt | `IPasswordService` |
| API key | [api_key.py](src/pokegrading/infrastructure/security/api_key.py) | genera/hashea con HMAC+pepper | `IApiKeyHasher` |
| Rate limit | [fixed_window_rate_limiter.py](src/pokegrading/infrastructure/ratelimit/fixed_window_rate_limiter.py) | ventana fija por cartas | `IRateLimiter` |

### Notas de defensa sobre los servicios

- **EasyOCR es un singleton lazy**: el modelo (torch, ~64MB) se carga **en la primera petición**, no al arrancar, para no penalizar el startup. Por eso la primera búsqueda OCR tarda unos segundos y las siguientes son rápidas.
- **El pHash usa `imagehash` (CPU, sin modelo de ML)**: tolera cambios de escala, compresión e iluminación leve. Es barato y exacto para imágenes limpias de frente.
- **¿Por qué HMAC-SHA256 y no bcrypt para las API keys?** El secreto es de alta entropía y se verifica en cada request; bcrypt (lento a propósito) sería un cuello de botella. El **pepper** vive fuera de la BD: si se filtra la tabla, los hashes no son crackeables.
- **El matching de texto** (`find_top_candidates`) usa SQL `LIKE` para recall amplio y luego re-rankea en Python con `difflib.SequenceMatcher` (similitud continua 0–1). Nombre exacto → 1.0; número exacto → ≥0.90.

---

## 7. Frontend (React + Vite)

- [api.js](frontend/src/api.js) — **toda** la comunicación con el backend. `BASE = '/api/v3'`. Cada función mapea a un endpoint y traduce errores. `quickSearchCard` trata 404/422 como "no encontrada → revisión manual".
- [App.jsx](frontend/src/App.jsx) — raíz. Maneja sesión (`user`) y pestañas: si es **admin** muestra Revisar / Agregar / Envíos; si es **submitter** muestra el formulario de envío.
- `components/`:
  - `RegisterForm.jsx`, `LoginForm.jsx` — autenticación.
  - `AddCardForm.jsx` — alta de carta: selecciona frente → OCR pre-rellena → admin edita → envía multipart con la misma imagen.
  - `CardReviewList.jsx` — admin revisa/aprueba cartas; muestra sus imágenes.
  - `SubmitCardForm.jsx` — submitter sube frente+reverso para evaluación.
  - `SubmissionsAdminList.jsx` — admin ve todos los envíos.

El proxy de Vite enruta `/api` hacia el backend, por eso el frontend usa rutas relativas.

---

## 8. Tests

- `tests/unit/` — prueban casos de uso y servicios **aislados** (sin HTTP), inyectando stubs.
- `tests/integration/` — prueban endpoints completos con `TestClient` de FastAPI sobre **SQLite en memoria** ([conftest.py](tests/conftest.py)). Los enums PostgreSQL se mapean a VARCHAR para que SQLite funcione.
- Fixtures clave en `conftest.py`: `db`, `client`, `admin_user/token`, `submitter_user/token`, `_make_active_card`, `_make_b2b_key`.

Correr: `pytest` (verde es requisito antes de integrar).

---

## 9. Preguntas frecuentes de defensa (respuestas rápidas)

**¿Por qué Clean Architecture y no todo en los routers?**
Para aislar las reglas de negocio de los frameworks. Puedo cambiar la BD, el motor OCR o exponer el mismo caso de uso por CLI sin reescribir lógica. Y puedo testear sin levantar PostgreSQL.

**¿Qué es un "puerto" y un "adaptador"?**
El puerto es una interfaz (ej. `IImageHashService`) declarada en `application/ports`. El adaptador es la implementación concreta en `infrastructure` (ej. `PHashImageHashService`). El caso de uso depende del puerto, no del adaptador → inversión de dependencias.

**¿Cómo identifica el sistema una carta por foto?**
Primero por **pHash** (similitud visual, rápido). Si no hay imagen de referencia cercana, escala a **OCR** (lee el texto y busca por nombre/número). Si ninguno resuelve, va a revisión manual.

**¿Por qué la carta nace en PENDING?**
Por la regla de **doble validación** (RNF R11): un segundo admin debe aprobarla, y `Card.approve()` impide que sea el mismo que la creó.

**¿Cómo se evita subir un archivo malicioso disfrazado de imagen?**
Validación de **magic bytes** (no se confía en la extensión ni el content-type) + detección de **polyglot** (firmas ZIP/PDF/ELF/PE en cabecera y cola del archivo).

**¿Las imágenes en la BD no son un problema?**
En desarrollo se guardan como BYTEA por simplicidad. En producción se migran a Azure Blob Storage cambiando solo el repositorio/columna; el dominio (`CardImage`) no cambia.

**¿Por qué dos APIs (`v3` interna y `b2b/v1`)?**
Tienen públicos, contratos y ciclos de versión distintos. La interna usa JWT; la B2B usa API keys, rate limit, idempotencia y ETag. Separarlas permite versionarlas de forma independiente.
