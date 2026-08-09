# PokéGrading — DrMundoSolutions

> **Sprint 1** — CE-1116 Diseño y Calidad de Productos Tecnológicos · Instituto Tecnológico de Costa Rica

Sistema de catalogación y calificación de cartas Pokémon con arquitectura limpia (Clean Architecture), API REST con FastAPI y autenticación JWT.

---

## Tabla de contenidos

1. [Descripción del proyecto](#descripción-del-proyecto)
2. [Funcionalidades implementadas (Sprint 1)](#funcionalidades-implementadas-sprint-1)
3. [Arquitectura](#arquitectura)
4. [Estructura de directorios](#estructura-de-directorios)
5. [Requisitos previos](#requisitos-previos)
6. [Instalación y configuración](#instalación-y-configuración)
7. [Ejecución](#ejecución)
8. [Endpoints](#endpoints)
9. [Autenticación en Swagger UI](#autenticación-en-swagger-ui)
10. [Configurar primer admin](#configurar-primer-admin)
11. [Tests](#tests)
12. [Migraciones de base de datos](#migraciones-de-base-de-datos)
13. [Variables de entorno](#variables-de-entorno)

---

## Descripción del proyecto

PokéGrading es una plataforma informativa de calificación de cartas Pokémon. Proporciona estimaciones de valor y condición basadas en imágenes, **sin reemplazar** los servicios certificados de calificación profesional (PSA, BGS, CGC).

El sistema consume la API de PokéMarket para consultar precios de referencia y utiliza un catálogo interno de cartas que sirve de base para el proceso de evaluación.

---

## Funcionalidades implementadas (Sprint 1)

### US-001 — Registrar cuenta

Permite a un usuario crear una cuenta en la plataforma.

| Criterio de aceptación | Comportamiento |
|---|---|
| Email + contraseña (≥8 chars) + alias + aceptar aviso | 201 Created + JWT |
| Email duplicado | 409 Conflict |
| No aceptar aviso de servicio no certificado | 400 Bad Request |
| Contraseña < 8 caracteres | 422 Unprocessable Entity |
| Rol asignado automáticamente | `submitter` (solo lectura del catálogo) |

**Endpoint:** `POST /api/v2/auth/register`

---

### US-002 — Agregar carta al catálogo

Permite a un administrador agregar una nueva carta de referencia al catálogo interno.

| Criterio de aceptación | Comportamiento |
|---|---|
| Admin + datos válidos | 201 Created, estado `pending` |
| Token de submitter o reviewer | 403 Forbidden |
| Sin token | 401 Unauthorized |
| Identidad duplicada (set/número/edición/idioma/acabado) | 409 Conflict |
| Campo requerido faltante | 422 Unprocessable Entity |
| Estado inicial | `pending` (requiere doble validación para activarse) |

**Endpoint:** `POST /api/v2/catalog/cards`

---

## Arquitectura

El proyecto sigue **Clean Architecture** con dependencias unidireccionales hacia adentro:

```
API (FastAPI)
    └── Application (Use Cases)
            └── Domain (Entities, Value Objects, Repository Interfaces)
Infrastructure (SQLAlchemy, bcrypt, JWT) ──▶ implementa interfaces del dominio
```

### Patrones de diseño aplicados

| Patrón | Dónde |
|---|---|
| **Repository** | `IUserRepository`, `ICardRepository` (dominio) → implementaciones SQLAlchemy (infraestructura) |
| **Strategy** | `IPasswordService` permite intercambiar algoritmos de hashing sin tocar los casos de uso |
| **Factory Method** | Construcción de entidades dentro de cada Use Case |
| **Facade** | `main.py` expone una interfaz unificada de la API sobre múltiples subsistemas |

---

## Estructura de directorios

```
PokeGrading-DrMundoSolutions/
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 001_create_users.py
│       └── 002_create_catalog_cards.py
├── src/
│   └── pokegrading/
│       ├── config.py                        # Settings via pydantic-settings
│       ├── main.py                          # FastAPI app + routers + exception handlers
│       ├── domain/
│       │   ├── entities/
│       │   │   ├── user.py                  # Entidad User
│       │   │   └── card.py                  # Entidad Card
│       │   ├── value_objects/
│       │   │   ├── role.py                  # Enum UserRole
│       │   │   ├── card_status.py           # Enum CardStatus
│       │   │   └── card_identity.py         # Value object CardIdentityTuple
│       │   ├── repositories/
│       │   │   ├── user_repository.py       # IUserRepository (ABC)
│       │   │   └── card_repository.py       # ICardRepository (ABC)
│       │   └── exceptions.py                # Excepciones de dominio
│       ├── application/
│       │   ├── ports/
│       │   │   └── password_service.py      # IPasswordService (ABC)
│       │   └── use_cases/
│       │       ├── register_user.py         # US-001
│       │       └── add_card_to_catalog.py   # US-002
│       ├── infrastructure/
│       │   ├── persistence/
│       │   │   ├── database.py              # SQLAlchemy engine + SessionLocal
│       │   │   ├── models.py                # UserORM, CardORM
│       │   │   ├── user_repository.py       # UserRepositoryImpl
│       │   │   └── card_repository.py       # CardRepositoryImpl
│       │   └── security/
│       │       ├── password.py              # BcryptPasswordService
│       │       └── jwt.py                   # JWTService (HS256)
│       └── api/
│           └── v1/
│               ├── dependencies.py          # get_db, get_current_user, require_admin
│               ├── schemas/
│               │   ├── auth.py              # RegisterRequest/Response
│               │   └── catalog.py           # AddCardRequest/Response
│               └── routers/
│                   ├── auth.py              # POST /auth/register
│                   └── catalog.py           # POST /catalog/cards
├── tests/
│   ├── conftest.py                          # Fixtures SQLite in-memory + TestClient
│   ├── unit/
│   │   ├── test_domain.py                   # Entidades y value objects
│   │   ├── test_register_user.py            # Use case US-001
│   │   └── test_add_card_to_catalog.py      # Use case US-002
│   └── integration/
│       ├── test_auth_register.py            # Endpoint POST /auth/register
│       └── test_catalog_add_card.py         # Endpoint POST /catalog/cards
├── Sprint1/
│   ├── DOC/                                 # Documentación del sprint
│   └── TODO_implementacion.md               # Checklist de implementación
├── alembic.ini
├── pyproject.toml
├── requirements.txt
└── .env.example
```

---

## Requisitos previos

- Python 3.12+
- PostgreSQL 15+
- Node.js 20+
- pip

---

## Instalación y configuración

```bash
# 1. Clonar el repositorio
git clone https://github.com/Randall-BL/PokeGrading-DrMundoSolutions.git
cd PokeGrading-DrMundoSolutions

# 2. Crear y activar entorno virtual
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
pip install -e .

# 4. Configurar variables de entorno
copy .env.example .env
# Editar .env con los valores reales (DATABASE_URL, JWT_SECRET_KEY, etc.)
```

---

## Ejecución

### Backend (API)

```bash
# Desde la raíz del proyecto, con el entorno virtual activo
uvicorn pokegrading.main:app --reload
```

Documentación disponible en:
- `http://localhost:8000/docs` — Swagger UI
- `http://localhost:8000/redoc` — ReDoc

### Frontend (React + Vite)

```bash
# En otra terminal, desde la raíz del proyecto
npx --prefix .\frontend vite .\frontend --host
```

Aplicación disponible en `http://localhost:5173`.

---

## Endpoints

### Autenticación

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/api/v2/auth/register` | Registrar nueva cuenta | No |
| `POST` | `/api/v2/auth/login` | Iniciar sesión, obtener JWT | No |
| `GET` | `/api/v2/auth/me` | Ver perfil propio | Bearer |
| `GET` | `/api/v2/auth/users` | Listar todos los usuarios | Bearer — Admin |
| `PUT` | `/api/v2/auth/users/{user_id}` | Actualizar alias / rol / estado | Bearer — Admin |
| `DELETE` | `/api/v2/auth/users/{user_id}` | Eliminar usuario | Bearer — Admin |

**Body — registro:**
```json
{
  "email": "usuario@ejemplo.com",
  "password": "MiPassword1!",
  "alias": "MiAlias",
  "accept_disclosure": true
}
```

**Body — login:**
```json
{
  "email": "usuario@ejemplo.com",
  "password": "MiPassword1!"
}
```

**Respuesta login / registro (200 / 201):**
```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "user_id": "uuid",
  "email": "usuario@ejemplo.com",
  "alias": "MiAlias",
  "role": "submitter"
}
```

---

### Catálogo

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/api/v2/catalog/cards` | Agregar carta al catálogo | Bearer — Admin |
| `GET` | `/api/v2/catalog/cards` | Listar todas las cartas | Bearer |
| `GET` | `/api/v2/catalog/cards/{card_id}` | Ver detalle de una carta | Bearer |
| `PUT` | `/api/v2/catalog/cards/{card_id}` | Actualizar carta | Bearer — Admin |
| `DELETE` | `/api/v2/catalog/cards/{card_id}` | Eliminar carta | Bearer — Admin |

**Body — agregar carta:**
```json
{
  "name": "Charizard",
  "set_name": "Base Set",
  "card_number": "4/102",
  "edition": "1st Edition",
  "language": "English",
  "finish": "Holo",
  "description": "Carta icónica de la primera edición",
  "reference_image_front_url": "https://...",
  "reference_image_back_url": "https://..."
}
```

**Respuesta 201:**
```json
{
  "card_id": "uuid",
  "identity": {
    "set_name": "Base Set",
    "card_number": "4/102",
    "edition": "1st Edition",
    "language": "English",
    "finish": "Holo"
  },
  "name": "Charizard",
  "status": "pending",
  "version": 1,
  "created_by": "uuid",
  "created_at": "2026-05-17T00:00:00Z"
}
```

> **Nota sobre el estado `pending`:** Las cartas nuevas requieren aprobación de un segundo administrador (distinto del creador) para pasar a estado `active`. Esto implementa la doble validación requerida por el sistema (RNF R11).

---

## Autenticación en Swagger UI

1. Obtén un token haciendo `POST /api/v2/auth/login` con **Try it out**.
2. Copia el valor de `access_token` de la respuesta.
3. Click en el botón **Authorize** (candado arriba a la derecha).
4. Pega **solo el token** (sin `Bearer`) en el campo y click **Authorize**.
5. Todos los endpoints protegidos ya incluirán el header automáticamente.

## Obtener token desde la terminal

### curl (Linux / macOS / Git Bash)

```bash
curl -s -X POST http://localhost:8000/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"tu@email.com","password":"TuPassword1"}' \
  | python -m json.tool
```

Copia el valor de `access_token` y úsalo en requests protegidos:

```bash
TOKEN="eyJhbGci..."

curl -s http://localhost:8000/api/v2/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  | python -m json.tool
```

### PowerShell (Windows)

```powershell
# 1. Obtener el token
$resp = Invoke-RestMethod -Method Post `
    -Uri "http://localhost:8000/api/v2/auth/login" `
    -ContentType "application/json" `
    -Body '{"email":"test2@test.com","password":"password123"}'

$TOKEN = $resp.access_token
Write-Host "Token: $TOKEN"

# 2. Usar el token en cualquier endpoint protegido
Invoke-RestMethod -Uri "http://localhost:8000/api/v2/auth/me" `
    -Headers @{ Authorization = "Bearer $TOKEN" }
```

> **Tip:** Si el servidor no está corriendo, lanza primero `uvicorn pokegrading.main:app --reload` en otra terminal.

---

## Configurar primer admin

Todos los usuarios se registran con rol `submitter`. Para promover un usuario a admin, ejecuta en pgAdmin o psql:

```sql
UPDATE users SET role = 'admin' WHERE email = 'tu@email.com';
```

Luego vuelve a hacer login para obtener un JWT con `"role": "admin"`.

---

## Tests

Los tests se ejecutan con SQLite en memoria — no se requiere PostgreSQL.

```bash
# Todos los tests con reporte de cobertura
python -m pytest tests/ -v

# Solo tests unitarios
python -m pytest tests/unit -v

# Solo tests de integración
python -m pytest tests/integration -v --no-cov
```

**Resultado actual:**

```
29 passed — cobertura domain+application: 96.26% (mínimo requerido: 75%)
```

| Suite | Tests | Cubre |
|-------|-------|-------|
| `unit/test_domain.py` | 8 | Entidades, value objects, invariantes |
| `unit/test_register_user.py` | 5 | Use case US-001 (mocks) |
| `unit/test_add_card_to_catalog.py` | 6 | Use case US-002 (mocks) |
| `integration/test_auth_register.py` | 5 | Endpoint POST /auth/register |
| `integration/test_catalog_add_card.py` | 5 | Endpoint POST /catalog/cards |

---

## Migraciones de base de datos

```bash
# Aplicar migraciones (requiere PostgreSQL configurado en .env)
alembic upgrade head

# Ver historial
alembic history

# Revertir última migración
alembic downgrade -1
```

Las migraciones crean dos tablas:
- `users` — cuentas de usuario con roles y flag de aceptación del aviso
- `catalog_cards` — catálogo de referencia con restricción única por identidad `(set_name, card_number, edition, language, finish)`

---

## Variables de entorno

Ver [.env.example](.env.example) para la lista completa. Variables principales:

| Variable | Descripción | Default |
|----------|-------------|---------|
| `DATABASE_URL` | URL de conexión PostgreSQL | `postgresql+psycopg2://pokegrading:changeme@localhost:5432/pokegrading_dev` |
| `JWT_SECRET_KEY` | Clave secreta para firmar tokens JWT | **Cambiar antes de producción** |
| `JWT_ALGORITHM` | Algoritmo de firma | `HS256` |
| `JWT_EXPIRE_MINUTES` | Duración del token en minutos | `60` |
| `APP_DEBUG` | Activa logs SQL y modo debug | `false` |
