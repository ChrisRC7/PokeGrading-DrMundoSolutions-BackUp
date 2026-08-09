# ADR-002 — Diseño de Almacenamiento del Sistema PokeGrading

**Estado:** Aceptado  
**Fecha:** 2026-05-31  
**Autores:** Equipo Dr. Mundo Solutions  
**Sprint:** 2  

---

## Contexto

PokeGrading es un sistema de graduación de cartas Pokémon TCG que involucra múltiples fuentes de datos heterogéneas: información estructurada de usuarios y cartas, imágenes binarias de referencia e imágenes de envíos, modelos de Machine Learning para OCR, y estado de sesión de usuarios en el cliente web.

Se requiere documentar de forma explícita **todas las fuentes de almacenamiento** del sistema, las decisiones tomadas sobre cómo se persisten los datos, y el plan de evolución hacia producción.

---

## Decisión

Se adopta un diseño de almacenamiento en **cuatro capas**, cada una con una tecnología y responsabilidad bien delimitada:

| Capa | Tecnología (desarrollo) | Tecnología (producción) | Responsabilidad |
|---|---|---|---|
| **Datos relacionales** | PostgreSQL 16 (puerto 5433) | PostgreSQL gestionado (Azure Database for PostgreSQL) | Usuarios, catálogo de cartas, metadatos de imágenes, envíos, historial de auditoría |
| **Imágenes binarias** | PostgreSQL BYTEA (columna `data`) | Azure Blob Storage | Imágenes de referencia de cartas e imágenes de envíos de usuarios |
| **Modelo OCR** | Sistema de archivos local (`~/.EasyOCR/`) | Imagen Docker / Azure Blob Storage | Pesos del modelo EasyOCR, descargados una sola vez por el singleton |
| **Estado de cliente** | `localStorage` del navegador (JWT + token de sesión) | Igual — sin estado en servidor | Token JWT de autenticación, datos de sesión del usuario |

---

## Fuentes de almacenamiento — Descripción detallada

### 1. PostgreSQL — Base de datos principal

**Conexión:** `postgresql+psycopg2://<user>:<password>@localhost:5433/pokegrading_dev`  
**ORM:** SQLAlchemy 2.0 con `DeclarativeBase`  
**Migraciones:** Alembic (`alembic upgrade head`)  
**Pool:** `pool_pre_ping=True` para reconexión automática

#### Tablas del sistema

```
┌─────────────────────────────────────────────────────────────────────┐
│  users                                                              │
│  ─────────────────────────────────────────────────────────────────  │
│  id            UUID (PK, uuid7)                                     │
│  email         VARCHAR(255) UNIQUE NOT NULL  [INDEX]                │
│  hashed_password VARCHAR(255) NOT NULL       [bcrypt]               │
│  alias         VARCHAR(100) NOT NULL                                │
│  role          ENUM(admin, submitter) NOT NULL                      │
│  accepted_disclosure BOOLEAN NOT NULL DEFAULT false                 │
│  is_active     BOOLEAN NOT NULL DEFAULT true                        │
│  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()                   │
│  country       VARCHAR(2) NOT NULL DEFAULT 'CR'                     │
│  preferred_language VARCHAR(5) NOT NULL DEFAULT 'es'               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  catalog_cards                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│  id            UUID (PK, uuid7)                                     │
│  name          VARCHAR(255) NOT NULL                                │
│  set_name      VARCHAR(100) NOT NULL                                │
│  card_number   VARCHAR(20)  NOT NULL                                │
│  edition       VARCHAR(100) NOT NULL                                │
│  language      VARCHAR(50)  NOT NULL                                │
│  finish        VARCHAR(50)  NOT NULL                                │
│  status        ENUM(pending, active, rejected) NOT NULL             │
│  version       INTEGER NOT NULL DEFAULT 1                           │
│  description   TEXT                                                 │
│  rarity        VARCHAR(50)                                          │
│  pokemon_type  VARCHAR(50)                                          │
│  hp            INTEGER                                              │
│  illustrator   VARCHAR(255)                                         │
│  print_year    INTEGER                                              │
│  created_by    UUID FK → users.id NOT NULL                          │
│  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()                   │
│  approved_by   UUID FK → users.id                                   │
│  approved_at   TIMESTAMPTZ                                          │
│                                                                     │
│  UNIQUE (set_name, card_number, edition, language, finish)          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  card_images                                                        │
│  ─────────────────────────────────────────────────────────────────  │
│  id            UUID (PK, uuid7)                                     │
│  card_id       UUID FK → catalog_cards.id CASCADE DELETE  [INDEX]   │
│  side          VARCHAR(5) NOT NULL  ('front' | 'back')              │
│  content_type  VARCHAR(50) NOT NULL ('image/jpeg' | 'image/png')    │
│  width         INTEGER NOT NULL                                     │
│  height        INTEGER NOT NULL                                     │
│  file_size     INTEGER NOT NULL  (bytes)                            │
│  data          BYTEA NOT NULL    (≤ 10 MB por restricción de dominio)│
│  uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()                   │
│  uploaded_by   UUID FK → users.id NOT NULL                          │
│                                                                     │
│  UNIQUE (card_id, side)                                             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  submissions                                                        │
│  ─────────────────────────────────────────────────────────────────  │
│  id                UUID (PK, uuid7)                                 │
│  user_id           UUID FK → users.id NOT NULL  [INDEX]             │
│  card_id           UUID FK → catalog_cards.id   (nullable)         │
│  image_front_data  BYTEA NOT NULL                                   │
│  image_back_data   BYTEA NOT NULL                                   │
│  status            ENUM(pending, approved, rejected) NOT NULL       │
│  image_quality_score FLOAT                                          │
│  rejection_reason  TEXT                                             │
│  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()               │
└─────────────────────────────────────────────────────────────────────┘
```

#### Relaciones entre tablas

```
users (1) ──────────────< catalog_cards (N)   [created_by, approved_by]
users (1) ──────────────< card_images   (N)   [uploaded_by]
users (1) ──────────────< submissions   (N)   [user_id]
catalog_cards (1) ──────< card_images   (N)   [card_id]  CASCADE DELETE
catalog_cards (0,1) ────< submissions   (N)   [card_id]  (nullable)
```

#### Forma de interacción

```
API Router
   │
   ▼
Use Case (application/)
   │   recibe ICardRepository / ICardImageRepository / ...
   ▼
RepositoryImpl (infrastructure/persistence/repositories/)
   │   SQLAlchemy Session inyectada por FastAPI Depends(get_db)
   ▼
PostgreSQL
```

El `Session` de SQLAlchemy se crea por request HTTP y se cierra en el `finally` del generador `get_db()`. No se comparte estado entre requests.

---

### 2. Imágenes binarias — BYTEA en PostgreSQL (desarrollo)

**Estado actual:** Las imágenes de cartas (`card_images.data`) y de envíos (`submissions.image_front_data`, `submissions.image_back_data`) se almacenan como BYTEA directamente en filas de PostgreSQL.

**Validaciones previas al almacenamiento** (dominio + infraestructura):

| Validación | Valor |
|---|---|
| Dimensión mínima | 150 × 150 px |
| Tamaño máximo | 10 MB |
| Formatos aceptados | JPEG, PNG |
| Servicio de validación | `PillowImageQualityService` (Pillow) |

**Flujo de almacenamiento de imágenes:**

```
Cliente (multipart/form-data)
   │
   ▼  FastAPI UploadFile.read()
   │
   ▼  PillowImageQualityService.validate()
      ├─ Verifica dimensiones (mínimo 150×150)
      ├─ Verifica tamaño (máximo 10 MB)
      └─ Detecta formato (JPEG / PNG)
   │
   ▼  CardImageRepositoryImpl.save()
      └─ INSERT INTO card_images (data = :bytes, ...)
```

**Acceso a imágenes:**

```
GET /api/v2/catalog/cards/{card_id}/images/{side}
   │
   ▼  CardImageRepositoryImpl.find_by_card_and_side()
      └─ SELECT data FROM card_images WHERE card_id = ? AND side = ?
   │
   ▼  Response(content=bytes, media_type=content_type)
```

**Nota de producción:**  
La columna `data BYTEA` se reemplazará por `blob_name VARCHAR(500)`. Los bytes se leerán y escribirán vía el SDK de Azure Storage (`azure-storage-blob`). El cambio es local a `CardImageRepositoryImpl`; ninguna otra capa se modifica.

---

### 3. Modelo OCR — Sistema de archivos local

**Tecnología:** EasyOCR v1.7.2 con backend PyTorch (CPU)  
**Ubicación de los pesos:** `C:\Users\<user>\.EasyOCR\model\` (descarga automática en primera ejecución)  
**Patrón de acceso:** Singleton lazy dentro de `EasyOCRCardMatchingService`

```python
class EasyOCRCardMatchingService:
    _reader: ClassVar[object | None] = None   # singleton de proceso

    @classmethod
    def _get_reader(cls):
        if cls._reader is None:
            import easyocr
            cls._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return cls._reader
```

**Forma de interacción:**

```
POST /api/v2/search/quick  (o  /search/ocr-extract)
   │
   ▼  EasyOCRCardMatchingService._get_reader()
      └─ carga pesos desde ~/.EasyOCR/ en memoria RAM (primera vez ~5 s)
   │
   ▼  reader.readtext(np.array(imagen), detail=0, paragraph=False)
      └─ retorna lista[str] de tokens reconocidos
   │
   ▼  _parse_card_tokens(tokens)
      └─ extrae: name, hp, card_number
```

El modelo **no se almacena en PostgreSQL**. Los pesos son archivos ONNX/PyTorch en disco gestionados por EasyOCR.

**Nota de producción:**  
Los pesos se incluirán en la imagen Docker (`COPY ~/.EasyOCR /root/.EasyOCR`) o se montarán desde Azure Blob Storage, eliminando la descarga al arrancar.

---

### 4. Estado de cliente — localStorage

**Tecnología:** Web Storage API (`localStorage`) del navegador  
**Implementación:** `frontend/src/api.js`

| Clave | Contenido | Vida útil |
|---|---|---|
| `token` | JWT firmado con HS256 (exp: 60 min) | Hasta logout o expiración |
| (implícito en token) | `user_id`, `role`, `email` en claims | Hasta expiración del token |

**Flujo de autenticación:**

```
POST /api/v2/auth/login
   │  retorna { access_token, token_type }
   ▼
localStorage.setItem('token', access_token)

Cada request siguiente:
   Authorization: Bearer <token>
   │
   ▼  HTTPBearer(auto_error=False) → JWTService.decode()
      └─ verifica firma y expiración
```

El servidor es **stateless**: no hay sesiones en Redis ni cookies de sesión. El estado de autenticación vive exclusivamente en el cliente.

---

## Diagrama de almacenamiento completo

```
┌──────────────────────────────────────────────────────────────────────┐
│                        CLIENTE (React + Vite)                        │
│                                                                      │
│   localStorage                                                       │
│   ├── token: "eyJhbGci..."   (JWT HS256, 60 min)                     │
│   └── (sin más estado persistido en cliente)                         │
│                                                                      │
│   Memoria de React (useState)                                        │
│   └── candidates, selectedCard, searchMsg, debugResponse, ...       │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ HTTPS / HTTP (dev: localhost:5173)
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI + Uvicorn)                      │
│                                                                      │
│   Memoria de proceso                                                 │
│   └── EasyOCR Reader singleton (pesos cargados en RAM ~500 MB)       │
│                                                                      │
│   Sistema de archivos local                                          │
│   └── ~/.EasyOCR/model/*.onnx  (pesos OCR, descarga automática)      │
│                                                                      │
│   SQLAlchemy Session (por request, efímera)                          │
│   └── pool_pre_ping=True → reconexión automática                     │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ psycopg2 / TCP 5433
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   PostgreSQL 16 (puerto 5433)                        │
│                   Base de datos: pokegrading_dev                     │
│                                                                      │
│   ┌─────────────┐   ┌──────────────────┐   ┌─────────────────────┐  │
│   │   users     │   │  catalog_cards   │   │   card_images       │  │
│   │  (auth +    │──▶│  (catálogo TCG,  │──▶│  (BYTEA, ≤10 MB,    │  │
│   │   perfiles) │   │   metadatos)     │   │   front / back)     │  │
│   └─────────────┘   └──────────────────┘   └─────────────────────┘  │
│          │                  │                                        │
│          │                  ▼                                        │
│          │          ┌──────────────────┐                             │
│          └─────────▶│   submissions    │                             │
│                     │  (envíos usuario,│                             │
│                     │   BYTEA × 2)     │                             │
│                     └──────────────────┘                             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Gestión de migraciones de esquema

Las migraciones de base de datos se gestionan con **Alembic**:

```bash
# Crear nueva migración
alembic revision --autogenerate -m "descripcion del cambio"

# Aplicar todas las migraciones pendientes
alembic upgrade head

# Revertir una migración
alembic downgrade -1
```

El archivo `alembic.ini` apunta a la misma `database_url` que usa la aplicación. Las migraciones se almacenan en `alembic/versions/`.

---

## Restricciones e índices de búsqueda

Las búsquedas de cartas (`find_top_candidates`) usan `LIKE '%query%'` sobre `catalog_cards.name`, `set_name`, y `card_number`. En la escala actual (catálogo de referencia, cientos a miles de cartas) esto es suficiente.

Para escalar se recomienda añadir índices de texto completo en PostgreSQL:

```sql
-- Índice tsvector para búsqueda full-text sobre nombre y set
CREATE INDEX idx_cards_fts ON catalog_cards
  USING GIN (to_tsvector('english', name || ' ' || set_name));
```

Esto se documenta como tarea de Sprint 3+.

---

## Análisis de ventajas y desventajas por componente

### 1. PostgreSQL como única base de datos relacional

| | Detalle |
|---|---|
| ✅ **Consistencia ACID** | Todas las operaciones (registro, aprobación de carta, envío) son transaccionales. No hay riesgo de estado inconsistente entre tablas. |
| ✅ **Un solo sistema a operar** | No hay necesidad de sincronizar PostgreSQL con un segundo store (Redis, Elasticsearch). El equipo solo necesita conocer una tecnología. |
| ✅ **Migraciones controladas con Alembic** | El esquema es versionado; cualquier desarrollador puede reproducir el estado de la BD con `alembic upgrade head`. |
| ✅ **Tipado fuerte con SQLAlchemy 2.0** | Los modelos ORM mapean directamente a las entidades de dominio. Los errores de tipo se detectan en tiempo de desarrollo. |
| ❌ **Escalabilidad de lectura limitada** | PostgreSQL escala verticalmente (más CPU/RAM). Para cargas de lectura muy altas (miles de búsquedas simultáneas) se necesitaría replicación de lectura o un caché. |
| ❌ **Búsqueda `LIKE '%query%'` no usa índices B-tree** | Los `LIKE` con comodín al inicio fuerzan un full scan. Con un catálogo pequeño es aceptable; con decenas de miles de cartas degradaría. |
| ❌ **Sin caché de consultas** | Cada búsqueda de candidatos va directo a disco. Consultas repetidas idénticas no se benefician de ningún caché en memoria. |

---

### 2. Imágenes binarias en BYTEA (PostgreSQL)

| | Detalle |
|---|---|
| ✅ **Sin infraestructura adicional** | Las imágenes se guardan en la misma BD que los metadatos. No se necesita configurar Azure Blob Storage, S3 ni un servidor de archivos para desarrollo. |
| ✅ **Consistencia con los metadatos** | Una transacción puede insertar la fila de metadatos y los bytes de la imagen de forma atómica. No es posible tener una carta con metadatos pero sin imagen (o viceversa). |
| ✅ **Backups unificados** | Un `pg_dump` incluye tanto metadatos como imágenes. No se necesita coordinar backups entre dos sistemas. |
| ✅ **Acceso directo sin URL firmadas** | El endpoint `GET /images/{side}` lee los bytes directamente de la fila sin pasar por un servicio externo. Útil para desarrollo offline. |
| ❌ **Inflado del WAL (Write-Ahead Log)** | Cada INSERT/UPDATE de imagen escribe los bytes completos en el WAL de PostgreSQL. Con muchas imágenes, los backups incrementales crecen rápidamente. |
| ❌ **Memoria RAM del servidor PostgreSQL** | PostgreSQL intenta cachear páginas activas en `shared_buffers`. Las columnas BYTEA grandes compiten con el caché de datos relacionales y degradan el rendimiento general. |
| ❌ **Latencia de lectura mayor que Blob Storage** | Leer 5 MB de BYTEA desde PostgreSQL es más lento que leer el mismo archivo desde Azure Blob Storage con CDN, especialmente si el cliente está geográficamente distante. |
| ❌ **No escala a producción** | Con cientos de usuarios enviando cartas, el volumen de BYTEA puede superar fácilmente los cientos de GB. PostgreSQL no está diseñado para ser un object store. |

---

### 3. Modelo OCR en sistema de archivos local (singleton en RAM)

| | Detalle |
|---|---|
| ✅ **Sin latencia de red para inferencia** | El modelo corre en el mismo proceso que la API. La inferencia OCR no depende de un servicio externo; funciona offline. |
| ✅ **Cero costo operacional en desarrollo** | EasyOCR descarga los pesos automáticamente en `~/.EasyOCR/`. No se necesita configurar ningún endpoint de ML. |
| ✅ **Singleton garantiza carga única** | Los ~500 MB de pesos se cargan una sola vez por proceso. Las requests subsiguientes reutilizan el reader ya inicializado. |
| ❌ **~500 MB de RAM ocupados permanentemente** | El singleton permanece en memoria durante toda la vida del proceso Uvicorn. En un servidor con 1-2 GB de RAM disponible, esto es significativo. |
| ❌ **Tiempo de arranque lento (primera request)** | La primera llamada a `_get_reader()` tarda ~5 segundos en inicializar PyTorch y cargar el modelo. Las requests subsiguientes son rápidas. |
| ❌ **Pesos no versionados en el repositorio** | Los archivos `.onnx` están en `~/.EasyOCR/` fuera del control de versiones. Si EasyOCR actualiza el modelo, el comportamiento del OCR puede cambiar entre entornos sin que quede trazabilidad en Git. |
| ❌ **No escala horizontalmente** | Si se levantan múltiples instancias de Uvicorn (balanceo de carga), cada instancia carga sus propios ~500 MB. No hay modelo compartido entre procesos. |

---

### 4. Estado de sesión en localStorage (JWT stateless)

| | Detalle |
|---|---|
| ✅ **Backend completamente stateless** | El servidor no necesita Redis ni una tabla de sesiones. Cualquier instancia puede validar cualquier token sin coordinarse con las demás. |
| ✅ **Escala horizontalmente sin cambios** | Añadir más instancias del backend no requiere sincronización de sesiones. |
| ✅ **Implementación mínima** | `python-jose` firma y verifica el JWT. No hay dependencias de infraestructura adicionales. |
| ❌ **Tokens no revocables antes de expirar** | Si un usuario cierra sesión o un admin desactiva su cuenta, el token JWT sigue siendo válido hasta su expiración (60 min). No hay blacklist. |
| ❌ **localStorage es vulnerable a XSS** | Si un script malicioso inyectado en la página accede a `localStorage`, puede robar el token. La mitigación recomendada para producción es usar `httpOnly cookies`, que son inaccesibles desde JavaScript. |
| ❌ **Sin renovación automática** | Cuando el token expira, el usuario debe volver a iniciar sesión. No hay mecanismo de refresh token implementado. |

---

## Consecuencias

### Resumen ejecutivo

El diseño actual optimiza para **velocidad de desarrollo y simplicidad operacional** en el contexto de Sprint 2. Las desventajas identificadas son conocidas y aceptadas conscientemente para este sprint, con un plan de mitigación claro para producción.

| Componente | Decisión | Veredicto Sprint 2 | Acción requerida para producción |
|---|---|---|---|
| PostgreSQL relacional | Único store relacional | ✅ Correcto | Sin cambio mayor |
| BYTEA para imágenes | Almacenamiento en BD | ⚠️ Aceptable | Migrar a Azure Blob Storage |
| EasyOCR en proceso | Singleton en RAM | ⚠️ Aceptable | Contenedor de inferencia dedicado |
| JWT en localStorage | Stateless, sin blacklist | ⚠️ Aceptable | Evaluar httpOnly cookies + refresh token |

---

## Plan de evolución a producción

| Componente | Cambio |
|---|---|
| `card_images.data BYTEA` | → `blob_name VARCHAR(500)` + Azure Blob Storage |
| `submissions.image_*_data BYTEA` | → `blob_front_name` / `blob_back_name` + Azure Blob Storage |
| `EasyOCR` singleton en proceso | → Contenedor dedicado de inferencia (Azure Container Apps) |
| `localStorage` JWT | → Sin cambio; el backend ya es stateless |
| Búsqueda `LIKE` | → Índice GIN `tsvector` o Azure Cognitive Search |
| PostgreSQL local | → Azure Database for PostgreSQL Flexible Server |

---

## Referencias

- [SQLAlchemy 2.0 — ORM Quickstart](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)  
- [Alembic — Auto-generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)  
- [EasyOCR — GitHub](https://github.com/JaidedAI/EasyOCR)  
- [Azure Blob Storage — Python SDK](https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-python)  
- [ADR-001 — Decisiones de Diseño Generales](./decisiones-diseno.md)
