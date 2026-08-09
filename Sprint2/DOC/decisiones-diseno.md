# Documentación de Decisiones de Diseño — PokeGrading

**Proyecto:** PokeGrading — Dr. Mundo Solutions  
**Última actualización:** Sprint 2  
**Audiencia:** Equipo de desarrollo, futuros colaboradores

---

## Índice

1. [Arquitectura general — Clean Architecture](#1-arquitectura-general--clean-architecture)
2. [Identificadores — UUID v4 y migración a v7](#2-identificadores--uuid-v4-y-migración-a-v7)
3. [Autenticación — JWT con python-jose](#3-autenticación--jwt-con-python-jose)
4. [Contraseñas — bcrypt directo sin passlib](#4-contraseñas--bcrypt-directo-sin-passlib)
5. [Base de datos — PostgreSQL puerto 5433](#5-base-de-datos--postgresql-puerto-5433)
6. [Seguridad HTTP — HTTPBearer auto_error=False](#6-seguridad-http--httpbearer-auto_errorfalse)
7. [Versionado de API — /api/v2](#7-versionado-de-api--apiv2)
8. [Tests — SQLite en memoria](#8-tests--sqlite-en-memoria)
9. [Estructura de carpetas — Modularización](#9-estructura-de-carpetas--modularización)
10. [Manejo de imágenes — Estrategia futura](#10-manejo-de-imágenes--estrategia-futura)
16. [US-003 — Enviar carta para evaluación](#16-us-003--enviar-carta-para-evaluación)
17. [US-004 — Búsqueda rápida de carta](#17-us-004--búsqueda-rápida-de-carta)

---

## 1. Arquitectura general — Clean Architecture

**Decisión:** Organizar el código en cuatro capas: `domain`, `application`, `infrastructure`, `api`.

**Razón:**
- El dominio (`domain/`) no depende de ninguna librería externa. Se puede probar sin base de datos, sin FastAPI, sin nada.
- Si se cambia de PostgreSQL a MongoDB mañana, solo cambia `infrastructure/persistence/`. El dominio no se toca.
- Los casos de uso (`application/use_cases/`) son la única capa que orquesta lógica de negocio. Los routers solo delegan; no deciden.
- Facilita el testeo unitario: los tests de dominio y use cases usan repositorios falsos (in-memory) sin infraestructura real.

**Evidencia en código:**
- `domain/repositories/*.py` → interfaces `ABC`, sin SQLAlchemy
- `infrastructure/persistence/repositories/*.py` → implementaciones con SQLAlchemy
- `application/use_cases/*.py` → reciben interfaces, no implementaciones concretas

---

## 2. Identificadores — UUID v4 y migración a v7

**Decisión actual (Sprint 2):** `uuid7()` de la librería `uuid_extensions` (paquete `uuid7==0.1.0`). Devuelve `uuid.UUID` — completamente compatible con todo el código existente y con PostgreSQL.

**Razón de la elección inicial (Sprint 1):**
- Simple, disponible en la librería estándar de Python.
- No requiere dependencias adicionales.
- Suficiente para un Sprint 1 donde el volumen de datos es bajo.

**Problema identificado:**
- UUID v4 es completamente aleatorio. En PostgreSQL, un índice B-tree sobre una columna `UUID` con valores aleatorios genera muchas páginas fragmentadas, lo que degrada el rendimiento a medida que la tabla crece.
- No permite ordenar por tiempo de creación usando el propio UUID; se necesita una columna `created_at` separada para ese fin.

**Decisión futura — UUID v7 (implementado en Sprint 2):**
- UUID v7 incluye un timestamp de 48 bits en los bits más significativos. Esto hace que los UUIDs sean secuenciales en el tiempo.
- Las inserciones siempre van al final del índice B-tree → menos fragmentación → mejor rendimiento.
- Permite ordenar por `id` y obtener orden cronológico sin necesidad de columna adicional.
- Se usa la librería `uuid7` (módulo `uuid_extensions`), que devuelve `uuid.UUID` estándar — sin cambios en el tipo de columna PostgreSQL ni en Alembic.

**Archivos modificados:**
- `application/use_cases/register_user.py`
- `application/use_cases/add_card_to_catalog.py`
- `infrastructure/persistence/models.py` (default de `UserORM` y `CardORM`)

---

## 3. Autenticación — JWT con python-jose

**Decisión:** Usar `python-jose` con algoritmo `HS256` para emitir y verificar tokens Bearer.

**Razón de elegir python-jose sobre PyJWT:**
- `python-jose` tiene una API más expresiva para los claims estándar (`sub`, `exp`, `iat`).
- Maneja de forma nativa la validación de expiración dentro del `decode()`, sin lógica manual adicional.
- Tiene soporte para JWK y múltiples algoritmos (útil si en el futuro se migra a RS256 para verificación pública sin compartir el secreto).

**Estructura del payload:**
```json
{
  "sub": "<user_id UUID>",
  "role": "submitter | admin",
  "exp": <timestamp UNIX>
}
```

**Tiempo de expiración:** configurable via `JWT_EXPIRE_MINUTES` en `.env` (default: 60 minutos).

**Ubicación:** `infrastructure/security/jwt.py → JWTService`

---

## 4. Contraseñas — bcrypt directo sin passlib

**Decisión:** Usar el paquete `bcrypt` directamente, con 12 rounds de cost factor. No se usa `passlib`.

**Razón:**
- `passlib` es una librería de alto nivel que envuelve varios backends (bcrypt, argon2, scrypt, etc.). Para este proyecto solo se necesita bcrypt.
- Las versiones recientes de `passlib` tienen conflictos de compatibilidad con `bcrypt >= 4.0` (errores de import o warnings en tests).
- Usar `bcrypt` directamente elimina la capa de indirección y los problemas de versiones.
- 12 rounds es el balance recomendado entre seguridad y latencia (~300ms por hash en hardware promedio), siguiendo las guías de OWASP para almacenamiento de contraseñas.

**Ubicación:** `infrastructure/security/password.py → BcryptPasswordService`

---

## 5. Base de datos — PostgreSQL puerto 5433

**Decisión:** PostgreSQL en puerto `5433` (no el default `5432`).

**Razón:**
- El puerto estándar `5432` ya estaba ocupado por otra instancia de PostgreSQL en la máquina de desarrollo.
- Se eligió `5433` para evitar conflictos sin reconfigurar la instancia existente.
- Esto se documenta explícitamente para que cualquier nuevo integrante sepa que **el puerto no es el default**.

**Credenciales de desarrollo:**
- Host: `localhost:5433`
- DB: `pokegrading_dev`
- User: `pokegrading`
- Password: definida en `.env` (no en código)

**Nota:** `.env` puede desaparecer en OneDrive por políticas de sync. El script `start.ps1` lo recrea automáticamente si no existe.

---

## 6. Seguridad HTTP — HTTPBearer auto_error=False

**Decisión:** `HTTPBearer(auto_error=False)` → el token opcional llega como `None` → se lanza `401` manualmente.

**Razón:**
- El comportamiento default de `HTTPBearer(auto_error=True)` lanza `403 Forbidden` cuando no hay token, lo cual es semánticamente incorrecto. `403` significa "autenticado pero sin permisos". Sin token = no autenticado = `401 Unauthorized`.
- Con `auto_error=False`, FastAPI devuelve `None` en lugar de lanzar error. La dependencia `get_current_user()` detecta el `None` y lanza `401` con mensaje descriptivo.
- Esto sigue la especificación HTTP correctamente y es compatible con clientes que esperan `401` para redirigir al login.

**Ubicación:** `api/v2/dependencies.py → get_current_user()`

---

## 7. Versionado de API — /api/v2

**Decisión:** Todas las rutas tienen el prefijo `/api/v2/`.

**Razón:**
- Permite introducir cambios breaking (nuevos campos requeridos, cambios en estructura de respuesta) en una versión futura (`/api/v3`) sin romper clientes que usan `v2`.
- Es una práctica estándar en APIs públicas y comerciales.
- Aunque el proyecto es interno, el versionado desde el inicio evita deuda técnica cuando se necesite evolucionar el contrato.

**Convención de cambio de versión:**
- Cambios non-breaking (nuevos campos opcionales, nuevos endpoints): no incrementan versión.
- Cambios breaking (campos requeridos nuevos, eliminación de campos, cambio de tipos): requieren nueva versión.

---

## 8. Tests — SQLite en memoria

**Decisión:** Los tests de integración usan SQLite en memoria (`sqlite:///:memory:`), no PostgreSQL.

**Razón:**
- No requiere infraestructura externa. Los tests corren en cualquier máquina sin instalar PostgreSQL.
- SQLite en memoria es extremadamente rápido (todos los 29 tests en ~1.4 segundos).
- Permite correr tests en CI/CD sin configurar una base de datos de test.

**Trade-off conocido:**
- SQLite no soporta algunos tipos nativos de PostgreSQL (ej. el tipo `UUID` nativo). Se usa `String` como fallback en tests.
- Si se agregan consultas con sintaxis PostgreSQL-específica (ej. `ANY`, arrays, JSON operators), los tests pueden divergir del comportamiento real.
- **Mitigación futura:** tests de contrato o smoke tests apuntando a una BD real en CI.

**Cobertura actual:** 92% (29 tests).

---

## 9. Estructura de carpetas — Modularización

**Decisión (Sprint 2):** Los repositorios de infraestructura se movieron a una subcarpeta `repositories/` dentro de `persistence/`.

**Razón:**
- Cuando haya más entidades (órdenes, evaluaciones, envíos), la carpeta `persistence/` tendría muchos archivos sueltos.
- Separar `repositories/` dentro de `persistence/` agrupa las implementaciones ORM de forma predecible.
- Sigue el mismo patrón ya existente en `domain/repositories/` (interfaces) y `domain/entities/`.

**Estructura resultante:**
```
infrastructure/persistence/
├── repositories/
│   ├── __init__.py
│   ├── user_repository.py    ← UserRepositoryImpl
│   └── card_repository.py    ← CardRepositoryImpl
├── models.py                 ← UserORM, CardORM (SQLAlchemy)
├── database.py               ← engine, SessionLocal, Base
└── __init__.py
```

**Nota para Sprint 3+:** Evaluar si `models.py` debe separarse en `models/user_model.py` y `models/card_model.py` cuando haya más de 3-4 entidades.

---

## 12. US-001 extendida — País, idioma, contraseña y dominios bloqueados

**Contexto:** La US-001 original registraba usuario con email, contraseña y alias. Para cumplir con los requisitos del Sprint 2, se agregaron: país de origen, idioma preferido, reglas de seguridad de contraseña y bloqueo de dominios de correo desechables.

### Decisiones tomadas

**País (`country`):**
- Enum `SupportedCountry` en `domain/value_objects/country.py` con 6 valores: `CR, PA, MX, CO, CL, AR`
- Se normaliza a mayúsculas en el use case antes de validar → `"mx"` → `"MX"`
- Columna `country VARCHAR(2) NOT NULL DEFAULT 'CR'` en PostgreSQL

**Idioma preferido (`preferred_language`):**
- Enum `SupportedLanguage` en `domain/value_objects/language.py`: `es` (default) / `en`
- Si se recibe un valor no reconocido (no `es`/`en`), se silencia y se usa `"es"` como fallback
- Columna `preferred_language VARCHAR(5) NOT NULL DEFAULT 'es'` en PostgreSQL

**Contraseña (reglas de seguridad):**
- Mínimo 8 caracteres + al menos 1 mayúscula + al menos 1 dígito
- Validado en `register_user.py` con regex (`re.compile`) antes de hashear
- Lanza `PasswordTooWeakError` con mensaje descriptivo por cada caso
- La validación de formato Pydantic (`min_length=8`) sigue en la capa API para feedback temprano

**Dominios bloqueados:**
- Lista `BLOCKED_DOMAINS` (frozenset) en `domain/value_objects/blocked_domains.py`
- ~25 dominios desechables conocidos (mailinator, guerrillamail, tempmail, yopmail, etc.)
- Validado en use case extrayendo el dominio con `email.split("@")[-1]`
- Lanza `BlockedEmailDomainError`

**Migración:**
- `alembic revision --autogenerate -m "add_country_language_to_users"` → revision `5b9c8ddf442f`
- Columnas agregadas con `server_default` temporal para filas existentes, luego se remueve el default

**Cobertura de tests:** +8 tests → 50 total, 94% cobertura

---

## 11. Programación defensiva — Sprint 2

**Contexto:** Los casos de uso y la infraestructura asumían que los datos de entrada llegaban ya validados desde la capa HTTP (Pydantic). Esto es correcto para el flujo HTTP, pero expone el sistema a comportamientos silenciosos si los use cases se invocan directamente (tests de integración, scripts, futuros workers).

**Decisión de diseño:** Añadir guardas defensivas a nivel de use case e infraestructura que no dependen de Pydantic.

### Cambios aplicados

| Archivo | Guardia añadida |
|---------|----------------|
| `register_user.py` | `email.strip()` vacío → `ValueError`; `alias.strip()` vacío → `ValueError` |
| `add_card_to_catalog.py` | Loop sobre 6 campos de identidad: vacíos después de `.strip()` → `ValueError` |
| `user_repository.py → save()` | `IntegrityError` en `commit()` → rollback + `EmailAlreadyExistsError` |
| `jwt.py → decode_token()` | Verifica que `sub` y `role` existan en el payload → `ValueError` descriptivo |
| `dependencies.py → get_current_user()` | `UUID(user_id)` envuelto en try/except `(ValueError, AttributeError)` → 401 |
| `catalog.py → update_card` | `CardStatus(body.status)` envuelto en try/except `ValueError` → HTTP 422 |

### Criterio de elevación de error

- Errores en **dominio/use case** → `ValueError` o excepción de dominio
- Errores en **infraestructura** (repos) → excepción de dominio (`EmailAlreadyExistsError`)
- Errores en **capa API** (routers) → `HTTPException` con código HTTP apropiado

### Cobertura de tests

Los 7 cambios están cubiertos por +13 tests nuevos en `tests/unit/`. Total: 42 tests, 93% de cobertura.

---

## 10. Manejo de imágenes — Estrategia futura

**Contexto:** El catálogo de cartas (`CardORM`) tiene columnas `reference_image_front_url` y `reference_image_back_url` que actualmente almacenan URLs como strings. No hay lógica de carga de archivos aún.

**Decisión de diseño (a implementar en Sprint futuro):**

### Principio: separar almacenamiento de metadatos

Las imágenes **nunca se almacenan en la base de datos** (no `BYTEA`, no base64). La BD solo guarda URLs. Los archivos viven en un sistema de almacenamiento dedicado.

### Ambientes

| Ambiente | Solución de almacenamiento |
|----------|---------------------------|
| Desarrollo local | Carpeta `media/` en el servidor (servida como estático por FastAPI) |
| Producción | Azure Blob Storage (contenedor privado con SAS tokens para lectura) |

### Interfaz de abstracción (Clean Architecture)

Se creará un puerto en `application/ports/`:

```python
# application/ports/image_storage.py
class IImageStorage(ABC):
    @abstractmethod
    async def upload(self, file_bytes: bytes, filename: str) -> str:
        """Sube la imagen y retorna la URL pública o path relativo."""
        ...

    @abstractmethod
    async def delete(self, url: str) -> None:
        ...
```

Implementaciones:
- `infrastructure/storage/local_image_storage.py → LocalImageStorage`
- `infrastructure/storage/azure_blob_image_storage.py → AzureBlobImageStorage`

La inyección de dependencia decidirá cuál implementación usar según el entorno (variable `IMAGE_STORAGE_BACKEND=local|azure`).

### Validaciones al subir imagen

- Formato permitido: `jpg`, `jpeg`, `png`, `webp`
- Tamaño máximo: 5 MB por imagen
- Verificación de tipo real (magic bytes), no solo extensión del nombre, para prevenir upload de archivos maliciosos disfrazados de imágenes
- Nombres de archivo: UUID v7 + extensión (evita colisiones y path traversal)

### Flujo de carga (diseño preliminar)

```
Cliente → POST /api/v2/catalog/cards/{id}/images
        → Router recibe multipart/form-data
        → Valida formato y tamaño
        → Llama a IImageStorage.upload()
        → Recibe URL
        → Llama a UpdateCardImagesUseCase(card_id, front_url, back_url)
        → Persiste URLs en BD
        → Retorna CardDetailResponse con las URLs nuevas
```

### Consideraciones de seguridad

- En producción (Azure Blob), las imágenes estarán en un contenedor privado. El acceso se dará mediante SAS tokens de corta duración generados en el backend, no exponiendo la URL directa del blob.
- No permitir que el cliente especifique el nombre del archivo destino (evita path traversal).
- Escaneo de malware: evaluar Azure Defender for Storage para blobs en producción.

---

*Este documento es vivo. Cada decisión de diseño tomada en el proyecto debe registrarse aquí con su contexto y razón.*

---

## 13. US-002 extendida — Campos de display, rareza, tipo Pokémon y auditoría

**Contexto:** La US-002 original solo cubría identidad + estado PENDING. La versión extendida agrega campos de display opcionales, validación de valores canónicos (rareza, tipo Pokémon, HP) y campos de auditoría obligatorios.

### Campos de display agregados a `Card` y `CardORM`

| Campo | Tipo | Validación |
|-------|------|-----------|
| `rarity` | `str \| None` | Debe estar en enum `CardRarity` si se provee |
| `pokemon_type` | `str \| None` | Debe estar en enum `PokemonType` si se provee |
| `hp` | `int \| None` | Entero positivo > 0 si se provee |
| `illustrator` | `str \| None` | Sin validación de formato |
| `print_year` | `int \| None` | Entre 1996 y 2100 (validado en schema Pydantic) |

### Value objects nuevos

- `domain/value_objects/rarity.py → CardRarity` (Enum): `Common, Uncommon, Rare, Holo Rare, Ultra Rare, Secret Rare`
- `domain/value_objects/pokemon_type.py → PokemonType` (Enum): 12 tipos válidos del TCG (Fire, Water, Grass, Electric, Psychic, Fighting, Darkness, Metal, Fairy, Dragon, Colorless, Normal)

### Excepciones nuevas

- `InvalidRarityError(rarity: str)` → HTTP 422
- `InvalidPokemonTypeError(pokemon_type: str)` → HTTP 422

### Decisión de diseño: validación en use case, no en entidad

Los campos de display son opcionales. La validación de rareza y tipo se hace en `AddCardToCatalogUseCase.execute()` antes de crear la entidad `Card`, no en `__post_init__` de la entidad. Razón: la entidad debe poder construirse desde BD sin revalidar (al igual que `accepted_disclosure` en `User`).

### Auditoría

`created_by`, `created_at`, `version=1` se generan automáticamente en el use case — el cliente no puede pasarlos. Son inmutables después de la creación (solo `approved_by`/`approved_at` cambian al aprobar).

### Migración Alembic

Revisión `25aa234c2b99`: agrega `rarity VARCHAR(50)`, `pokemon_type VARCHAR(50)`, `hp INTEGER`, `illustrator VARCHAR(255)`, `print_year INTEGER` a `catalog_cards`. Todas nullables para compatibilidad con filas existentes.

### Respuesta API

`POST /api/v2/catalog/cards` ahora devuelve `CardDetailResponse` (antes `CardResponse`) con todos los campos de display incluidos en la respuesta 201.

### Tests

+6 tests unitarios en `tests/unit/test_add_card_to_catalog.py`:
- `test_add_card_with_display_fields_returns_201`
- `test_add_card_with_invalid_rarity_raises`
- `test_add_card_with_invalid_pokemon_type_raises`
- `test_add_card_with_negative_hp_raises`
- `test_add_card_audit_fields_are_set`
- `test_add_card_duplicate_identity_returns_409`

Total: 56 tests, 95% de cobertura.

---

## 14. Almacenamiento de imágenes de referencia — BYTEA en PostgreSQL (Sprint 2) / Azure Blob (producción)

**Fecha:** Sprint 2  
**Contexto:** La US-002 extendida requiere que el Admin suba imágenes de referencia (frente y reverso opcional) de cada carta. El requisito explícito es que la imagen se almacene como **archivo real**, no como una URL externa.

### Problema con URLs externas

Almacenar solo una URL implica dependencia de un servicio externo (CDN, S3, etc.) que puede no estar disponible durante el desarrollo y cuya integridad no está garantizada. Si la URL externa deja de existir, la imagen se pierde.

### Decisión adoptada — Sprint 2 (desarrollo)

**Almacenamiento binario en PostgreSQL como BYTEA.**

| Componente | Decisión |
|---|---|
| Tabla | `card_images` (separada de `catalog_cards`) |
| Columna de datos | `data BYTEA NOT NULL` (SQLAlchemy `LargeBinary`) |
| Cardinalidad | Máximo 1 imagen por `(card_id, side)` — restricción `uq_card_image_side` |
| Formatos válidos | `image/jpeg`, `image/png` |
| Validación de formato | Magic bytes: JPEG = `\xFF\xD8\xFF`, PNG = `\x89PNG\r\n\x1a\n` |
| Resolución mínima | 400×400 px (Pillow 11.1.0) |
| Tamaño máximo | 10 MB |
| Separación del modelo | `catalog_cards` no tiene FKs hacia `card_images` — se evita referencia circular |
| Indicador en `Card` | `has_image_front: bool` y `has_image_back: bool` (derivados de `card_images`) |

### Por qué tabla separada y no columna en `catalog_cards`

- Una fila con BYTEA grande en la tabla principal degrada los escaneos de índice (PostgreSQL carga toda la fila en memoria al hacer `SELECT`).
- La tabla separada permite recuperar solo los metadatos (`content_type`, `width`, `height`, `file_size`) sin traer el binario.
- El binario se recupera únicamente al acceder a `GET /api/v2/catalog/cards/{card_id}/images/{side}`.

### Endpoints

| Método | Path | Descripción |
|---|---|---|
| `POST` | `/api/v2/catalog/cards/{card_id}/images/{side}` | Subir imagen (multipart/form-data) |
| `GET` | `/api/v2/catalog/cards/{card_id}/images/{side}` | Recuperar imagen binaria |

### Flujo de subida

1. Cliente envía `multipart/form-data` con `UploadFile`.
2. API valida content-type declarado → solo `image/jpeg` o `image/png`.
3. API lee los bytes y valida magic bytes (previene spoofing de content-type).
4. API valida resolución con Pillow (≥ 400×400 px).
5. API valida tamaño (≤ 10 MB).
6. Si todo es válido, se persiste en `card_images` vía upsert por `(card_id, side)`.
7. Se retorna `ImageUploadResponse` con metadatos (sin el binario).

### Decisión futura — Producción (Sprint 3+)

En producción se recomienda migrar a **Azure Blob Storage**:
- Reemplazar la columna `data BYTEA` por `blob_name VARCHAR(500)` en `card_images`.
- Crear `infrastructure/storage/IImageStorage` (ABC) con implementación `AzureBlobImageStorage`.
- La implementación de desarrollo (`LocalDBImageStorage`) ya sigue el contrato de `ICardImageRepository` para facilitar la migración.
- La decisión de interfaz (`ICardImageRepository`) ya está en `domain/repositories/image_repository.py`.

### Tests relacionados

- `test_add_card_with_invalid_language_raises` — idioma fuera del listado → `InvalidLanguageError`
- Total acumulado: **57 tests, 93% de cobertura**

---

## 15. Almacenamiento de imágenes de envío — BYTEA inline en tabla `submissions` (US-003)

**Fecha:** Sprint 2  
**Contexto:** La US-003 requiere que el usuario envíe dos imágenes (frente y reverso) de su carta física para solicitar una evaluación de grado. A diferencia de las imágenes de referencia del catálogo (US-002), las imágenes de envío son **parte integral e inseparable** del envío.

### Diseño adoptado — inline BYTEA en `submissions`

| Componente | Decisión |
|---|---|
| Tabla | `submissions` (una sola tabla) |
| Columnas de imagen | `image_front_data BYTEA NOT NULL` y `image_back_data BYTEA NOT NULL` |
| Cardinalidad | Exactamente 2 imágenes por envío — siempre presentes, nunca opcionales |
| Formatos válidos | JPEG (`\xFF\xD8\xFF`) y PNG (`\x89PNG\r\n\x1a\n`) |
| Tamaño máximo | 10 MB por imagen |
| Validación de seguridad | Magic bytes + detección de polyglot (patrones: `PK\x05\x06`, `%PDF-`, `\x7fELF`) |
| Calidad de imagen | IQS ≥ 0.60 (stub devuelve 0.85 en Sprint 2) |

### Por qué inline y no tabla separada (`submission_images`)

La decisión de usar columnas BYTEA directamente en `submissions` (en lugar de una tabla auxiliar como en US-002) se justifica en:

1. **Cardinalidad fija**: Un envío **siempre** tiene exactamente 2 imágenes (frente y reverso). No hay variabilidad — no existe un envío válido sin ambas.
2. **Nunca se accede por separado**: Las imágenes de envío no tienen endpoint de descarga individual como las imágenes de referencia del catálogo. Se consumen como unidad atómica por el proceso de evaluación.
3. **Simplicidad**: Una tabla `submission_images` con `side = 'front' | 'back'` requeriría 2 filas por envío y complicaría las queries sin beneficio real.
4. **Diferencia con `card_images`**: Las imágenes de referencia del catálogo son opcionales, reutilizables y se sirven vía GET individualizado — por eso tienen tabla separada. Las imágenes de envío no tienen ninguna de estas características.

### Validación de seguridad — Polyglot detection

Los archivos políglotas son archivos que son válidos en dos formatos simultáneamente (e.g., JPEG + ZIP). Se detectan buscando firmas de formatos no-imagen dentro del cuerpo del archivo:

| Patrón | Formato malicioso |
|---|---|
| `PK\x05\x06` | ZIP / JAR / DOCX |
| `%PDF-` | PDF |
| `\x7fELF` | ELF binary (Linux) |

### Decisión futura — Producción (Sprint 3+)

Migrar a **Azure Blob Storage**:
- Reemplazar `image_front_data BYTEA` / `image_back_data BYTEA` por `blob_name_front VARCHAR(500)` / `blob_name_back VARCHAR(500)`.
- Crear implementación `AzureBlobSubmissionStorage` que implemente `IImageQualityService` o un nuevo contrato de almacenamiento.
- El contrato de dominio (`ISubmissionRepository`) no cambia — sólo la infraestructura.

### Tests relacionados

- `test_submit_without_front_image_raises` → `BothImagesRequiredError`
- `test_submit_without_back_image_raises` → `BothImagesRequiredError`
- `test_submit_with_invalid_front_format_raises` → `InvalidFileFormatError`
- `test_submit_with_invalid_back_format_raises` → `InvalidFileFormatError`
- `test_submit_exceeding_size_raises` → `FileTooLargeError`
- `test_submit_polyglot_raises` → `PolyglotDetectedError`
- `test_submit_low_quality_raises` → `ImageQualityBelowThresholdError`
- `test_submit_valid_returns_pending_submission` → `status = "pending"`, `evaluation_id` presente
- `test_submit_without_token_returns_401` — integración
- `test_submit_valid_returns_201` — integración
- Total acumulado: **67 tests, 94.55% de cobertura**

---

## 16. US-003 — Enviar carta para evaluación

**Fecha:** Sprint 2  
**Historia de usuario:** US-003  
**Endpoint:** `POST /api/v2/submissions`

### Contexto

El submitter necesita enviar las dos fotografías de su carta física (frente y reverso) para que el sistema registre la solicitud de evaluación de grado. El sistema no evalúa la calidad de la carta directamente, sino que valida que las imágenes sean técnicamente utilizables para el proceso de revisión posterior.

### Decisiones clave

#### 1. Flujo de validación determinista (orden fijo)

El use case `SubmitCardForEvaluationUseCase` aplica las validaciones siempre en el mismo orden para garantizar mensajes de error predecibles al cliente:

| Paso | Validación | Error si falla |
|---|---|---|
| 1 | Imagen presente (no `None`) | `BothImagesRequiredError` → HTTP 422 |
| 2 | Formato JPEG o PNG (magic bytes) | `InvalidFileFormatError` → HTTP 422 |
| 3 | Tamaño ≤ 10 MB | `FileTooLargeError` → HTTP 413 |
| 4 | Sin firmas de archivos incrustados (polyglot) | `PolyglotDetectedError` → HTTP 422 |
| 5 | IQS ≥ 0.60 (calidad de imagen) | `ImageQualityBelowThresholdError` → HTTP 422 |

El orden importa: si una imagen falta (paso 1), no tiene sentido leer sus bytes para el paso 2. Validar polyglot antes que calidad evita procesar con Pillow archivos potencialmente maliciosos.

#### 2. Detección de archivos políglotas (seguridad OWASP)

Un archivo políglotas es válido en dos formatos simultáneamente (ej. JPEG + ZIP). La búsqueda de firmas maliciosas se acota a:
- **Primeros 256 bytes**: encabezado donde se inyectan firmas alternativas.
- **Últimos 4096 bytes**: zona de End-of-Central-Directory de ZIP y trailers de PDF.

Buscar en el cuerpo completo produciría falsos positivos porque los datos comprimidos de imágenes reales pueden contener casualmente cualquier secuencia de 4 bytes.

#### 3. Image Quality Score (IQS)

El score **no es una calificación de la carta**: mide si la fotografía es suficientemente clara para ser procesada. Se calcula con `PillowImageQualityService` como media ponderada de tres componentes:

$$
\text{IQS} = 0.55 \cdot \text{sharpness} + 0.30 \cdot \text{brightness} + 0.15 \cdot \text{resolution}
$$

El score final es el **promedio** entre frente y reverso. Si cualquiera de los dos queda por debajo del umbral (0.60), el envío se rechaza con indicación de qué lado falló.

#### 4. Las imágenes se almacenan inline en `submissions`

Ver [sección 15](#15-almacenamiento-de-imágenes-de-envío--bytea-inline-en-tabla-submissions-us-003) para la justificación completa.

#### 5. `card_id` es opcional en el momento del envío

El submitter puede enviar la carta sin identificarla previamente (flujo rápido) o con `card_id` ya conocido tras haber completado la búsqueda rápida (US-004). Si `card_id` es `None`, el envío queda en estado `PENDING` y el admin debe asociarlo manualmente.

### Criterios de aceptación implementados

| AC | Descripción | Implementación |
|---|---|---|
| AC-01 | Imágenes válidas → 201, `evaluation_id` en respuesta | `SubmitCardForEvaluationUseCase.execute()` → `SubmitCardOutput` |
| AC-02 | Sin imagen frente o reverso → 422 | `BothImagesRequiredError` → `HTTP 422` |
| AC-03 | Formato inválido → 422 | `InvalidFileFormatError` → `HTTP 422` |
| AC-04 | Imagen > 10 MB → 413 | `FileTooLargeError` → `HTTP 413` |
| AC-05 | Sin token → 401 | `Depends(get_current_user)` → `HTTP 401` |
| AC-06 | IQS < 0.60 → 422 con score | `ImageQualityBelowThresholdError` → `HTTP 422` |

### Archivos clave

| Archivo | Responsabilidad |
|---|---|
| `api/v2/routers/submissions.py → submit_card()` | Leer bytes, construir input, mapear errores a HTTP |
| `application/use_cases/submit_card_for_evaluation.py → SubmitCardForEvaluationUseCase` | Orquestar validaciones y persistencia |
| `infrastructure/services/pillow_image_quality_service.py → PillowImageQualityService` | Calcular IQS con Pillow |
| `infrastructure/persistence/repositories/submission_repository.py → SubmissionRepositoryImpl` | Persistir agregado Submission |

### Tests relacionados

- Total acumulado al cierre: **67 tests, 94.55% de cobertura**
- Tests unitarios: `tests/unit/test_submit_card_for_evaluation.py`
- Tests de integración: `tests/integration/test_submissions.py`

---

## 17. US-004 — Búsqueda rápida de carta

**Fecha:** Sprint 2  
**Historia de usuario:** US-004  
**Endpoints:** `POST /api/v2/search/quick`, `POST /api/v2/search/ocr-extract`

### Contexto

Antes de enviar una carta para evaluación, el submitter necesita identificar exactamente qué carta está enviando (set, edición, idioma, acabado). Dado que el catálogo puede tener múltiples variantes del mismo Pokémon, se implementa un mecanismo de identificación automática por imagen.

### Pipeline de tres etapas

```
Imagen de la carta
       │
       ▼ Etapa 1 — Extracción OCR
  EasyOCRCardMatchingService.extract_tokens_raw()  →  lista[str]
  _parse_card_tokens()  →  { name, hp, card_number }
  focused_q = name + card_number
       │
       ▼ Etapa 2 — Búsqueda en catálogo
  CardRepositoryImpl.find_top_candidates(focused_q, limit=3)
  SQL LIKE (recall amplio) → re-ranking Python SequenceMatcher
       │
       ▼ Etapa 3 — Decisión de auto-aceptación
  QuickSearchCardUseCase
  auto_accepted = candidates[0].confidence_score >= 0.60
```

### Decisiones clave

#### 1. OCR como fuente de identidad (no comparación visual pixel a pixel)

EasyOCR lee el texto impreso en la carta para extraer nombre, HP y número. Esto evita mantener una base de datos de imágenes de referencia, tolera variaciones de iluminación y ángulo, y funciona offline sin llamadas a servicios externos.

#### 2. Separación entre tokens crudos y query enfocada

`extract_tokens_raw()` devuelve **todo** el texto OCR (incluyendo ataques, habilidades, reglas). Si se buscase con todo ese texto, los nombres de ataques nunca coincidirían con los nombres del catálogo.

`_parse_card_tokens()` extrae solo las partes discriminantes:

| Campo | Estrategia |
|---|---|
| `card_number` | Regex `\b\d{1,3}/\d{1,3}\b` sobre el texto completo |
| `hp` | Número adyacente al token `"HP"` |
| `name` | Primeros 1–3 tokens significativos antes del HP/número/stage |

La query final se construye como `name + card_number` para maximizar la precisión sin añadir ruido.

#### 3. `SequenceMatcher` en lugar de tiers fijos

El diseño previo asignaba scores fijos (1.0 / 0.85 / 0.70). Con múltiples variantes del mismo Pokémon, todas obtenían el mismo score y el ranking no era determinista.

`difflib.SequenceMatcher.ratio()` produce un score continuo:

| Query | Carta | Score |
|---|---|---|
| `"pikachu"` | `"Pikachu"` | **1.000** |
| `"pikachu"` | `"Pikachu V"` | **0.875** |
| `"pikachu"` | `"Pikachu ex"` | **0.824** |
| `"pikachu"` | `"Pikachu VMAX"` | **0.737** |

Cada candidato obtiene un score único y el ranking es completamente determinista.

#### 4. `query_hint` para evitar doble OCR

El router pre-procesa la imagen con `extract_tokens_raw()` + `_parse_card_tokens()` y construye `focused_q` antes de llamar al use case. El use case recibe `focused_q` como `query_hint` y no vuelve a correr OCR. Sin este mecanismo, el mismo modelo se ejecutaría dos veces por request.

#### 5. Singleton lazy de EasyOCR

El modelo (~500 MB de pesos PyTorch) se carga **una sola vez por proceso** mediante `_reader: ClassVar[object | None] = None`. El import de `easyocr` es diferido (dentro de `_get_reader()`) para no penalizar el arranque del servidor (~5 s en la primera request).

#### 6. Las imágenes de búsqueda NO se almacenan

Los bytes de `image_front` se leen en memoria para OCR y se descartan. No hay persistencia durante la búsqueda. El almacenamiento de la imagen ocurre únicamente en `POST /submissions` una vez que el usuario confirma la carta identificada.

### Criterios de aceptación implementados

| AC | Descripción | Implementación |
|---|---|---|
| AC-01 | Devuelve hasta 3 candidatos ordenados por confianza desc | `find_top_candidates(limit=3)` + sort SequenceMatcher |
| AC-02 | Si top ≥ umbral → `auto_accepted=True` | `candidates[0].score >= confidence_threshold` |
| AC-03 | Sin coincidencias → 404 | `NoMatchFoundError` → `HTTP 404` |
| AC-04 | Imagen no identificable → 422 | `ImageNotIdentifiableError` → `HTTP 422` |
| AC-05 | Sin token → 401 | `Depends(get_current_user)` → `HTTP 401` |

### Archivos clave

| Archivo | Responsabilidad |
|---|---|
| `api/v2/routers/search.py → quick_search()` | Validar imagen, correr OCR, construir `focused_q`, mapear errores |
| `api/v2/routers/search.py → _parse_card_tokens()` | Extraer name/hp/card_number de tokens OCR crudos |
| `application/use_cases/quick_search_card.py → QuickSearchCardUseCase` | Buscar candidatos y decidir auto-aceptación |
| `infrastructure/matching/easyocr_card_matching_service.py → EasyOCRCardMatchingService` | Singleton OCR, extracción de tokens |
| `infrastructure/persistence/repositories/card/card_repository.py → find_top_candidates()` | SQL LIKE + re-ranking SequenceMatcher |

### Tests relacionados

- Tests de integración de búsqueda: `tests/integration/test_search.py`
- Tests del use case: `tests/unit/test_quick_search_card.py`
- En modo test se usa `StubCardMatchingService` (retorna `""`) para no depender de EasyOCR
- Ver [ADR-003](./ADR-003-busqueda-rapida-de-carta.md) para el diseño detallado con tablas de ventajas/desventajas
