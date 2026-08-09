# TODO — Implementación Sprint 1: Registrar cuenta + Agregar carta al catálogo

**Sprint:** 1 | **Fecha límite:** 18 de mayo de 2026  
**Funcionalidades:** US-001 Registrar cuenta · US-002 Agregar carta al catálogo  
**Arquitectura:** Clean Architecture + Repository + Strategy (según DoD.md)

---

## Criterios de aceptación derivados del caso de negocio

### US-001 — Registrar cuenta

| # | Criterio | RNF relacionado |
|---|---|---|
| AC-01 | Dado email válido + contraseña + alias + disclosure aceptado → 201 Created + JWT | SP1, U9 |
| AC-02 | Dado email ya registrado → 409 Conflict con mensaje descriptivo | SP1 |
| AC-03 | Dado formato de email inválido → 422 Unprocessable Entity | SP2 |
| AC-04 | Dado contraseña < 8 caracteres → 422 Unprocessable Entity | SP2 |
| AC-05 | Dado accept_disclosure = false → 400 Bad Request | U9 |
| AC-06 | La contraseña nunca se devuelve ni se almacena en texto plano | SP2, S9 |
| AC-07 | El rol asignado por defecto es Submitter | SP1 |

### US-002 — Agregar carta al catálogo

| # | Criterio | RNF relacionado |
|---|---|---|
| AC-01 | Dado token de Admin + datos válidos → 201 Created, carta en estado PENDING | R11 |
| AC-02 | Dado token de Submitter/Reviewer → 403 Forbidden | SP1 |
| AC-03 | Sin token → 401 Unauthorized | SP1 |
| AC-04 | Dado identidad de carta (set+número+edición+idioma+acabado) ya existente → 409 Conflict | R11 |
| AC-05 | La carta se crea en estado PENDING (requiere aprobación de otro Admin para activarse) | R11 |
| AC-06 | Se registran created_by, created_at y versión = 1 automáticamente | R11 |
| AC-07 | Campos de identidad obligatorios: set_name, card_number, edition, language, finish | R11 |

---

## Estructura de archivos a crear

```
pokegrading/                        <- raíz del proyecto
|
+-- src/
|   +-- pokegrading/
|       +-- __init__.py
|       +-- config.py               [1] Settings (pydantic-settings)
|       +-- main.py                 [2] FastAPI app + lifespan
|       |
|       +-- domain/
|       |   +-- __init__.py
|       |   +-- entities/
|       |   |   +-- __init__.py
|       |   |   +-- user.py         [3] User entity (dataclass)
|       |   |   +-- card.py         [4] Card entity (dataclass)
|       |   +-- value_objects/
|       |   |   +-- __init__.py
|       |   |   +-- role.py         [5] UserRole enum
|       |   |   +-- card_status.py  [6] CardStatus enum
|       |   |   +-- card_identity.py [7] CardIdentityTuple (frozen dataclass)
|       |   +-- repositories/
|       |   |   +-- __init__.py
|       |   |   +-- user_repository.py  [8] IUserRepository ABC
|       |   |   +-- card_repository.py  [9] ICardRepository ABC
|       |   +-- exceptions.py       [10] Domain exceptions
|       |
|       +-- application/
|       |   +-- __init__.py
|       |   +-- ports/
|       |   |   +-- __init__.py
|       |   |   +-- password_service.py  [11] IPasswordService ABC
|       |   +-- use_cases/
|       |       +-- __init__.py
|       |       +-- register_user.py     [12] RegisterUserUseCase
|       |       +-- add_card_to_catalog.py [13] AddCardToCatalogUseCase
|       |
|       +-- infrastructure/
|       |   +-- __init__.py
|       |   +-- persistence/
|       |   |   +-- __init__.py
|       |   |   +-- database.py          [14] SQLAlchemy engine + session
|       |   |   +-- models.py            [15] UserORM, CardORM
|       |   |   +-- user_repository.py   [16] UserRepositoryImpl
|       |   |   +-- card_repository.py   [17] CardRepositoryImpl
|       |   +-- security/
|       |       +-- __init__.py
|       |       +-- password.py          [18] BcryptPasswordService
|       |       +-- jwt.py               [19] JWTService (crear + validar tokens)
|       |
|       +-- api/
|           +-- __init__.py
|           +-- v1/
|               +-- __init__.py
|               +-- dependencies.py      [20] get_current_user, require_admin
|               +-- schemas/
|               |   +-- __init__.py
|               |   +-- auth.py          [21] RegisterRequest, RegisterResponse
|               |   +-- catalog.py       [22] AddCardRequest, CardResponse
|               +-- routers/
|                   +-- __init__.py
|                   +-- auth.py          [23] POST /api/v1/auth/register
|                   +-- catalog.py       [24] POST /api/v1/catalog/cards
|
+-- tests/
|   +-- __init__.py
|   +-- unit/
|   |   +-- __init__.py
|   |   +-- test_register_user.py        [25] Tests unitarios US-001
|   |   +-- test_add_card_to_catalog.py  [26] Tests unitarios US-002
|   +-- integration/
|       +-- __init__.py
|       +-- conftest.py                  [27] TestClient + DB en memoria
|       +-- test_auth_routes.py          [28] Tests integración US-001
|       +-- test_catalog_routes.py       [29] Tests integración US-002
|
+-- alembic/
|   +-- env.py                           [30] Config de Alembic
|   +-- script.py.mako
|   +-- versions/
|       +-- 001_create_users.py          [31] Migración tabla users
|       +-- 002_create_catalog_cards.py  [32] Migración tabla catalog_cards
|
+-- requirements.txt                     [33]
+-- pyproject.toml                       [34] ruff + black + isort + pytest config
+-- alembic.ini                          [35]
+-- .env.example                         [36]
+-- README.md                            [37]
```

---

## Checklist de tareas

### Fase 1 — Setup del proyecto

- [ ] **[1]** `requirements.txt` con todas las dependencias fijadas
- [ ] **[2]** `pyproject.toml` con configuración de ruff, black, isort, pytest y coverage
- [ ] **[3]** `.env.example` con todas las variables de entorno necesarias
- [ ] **[4]** `alembic.ini` con la ruta correcta al módulo de modelos
- [ ] **[5]** `src/pokegrading/config.py` con `Settings` usando pydantic-settings

### Fase 2 — Capa de dominio

- [ ] **[6]** `domain/value_objects/role.py` — `UserRole` enum
- [ ] **[7]** `domain/value_objects/card_status.py` — `CardStatus` enum
- [ ] **[8]** `domain/value_objects/card_identity.py` — `CardIdentityTuple` (frozen dataclass)
- [ ] **[9]** `domain/entities/user.py` — `User` entity con `is_admin()`, `has_role()`
- [ ] **[10]** `domain/entities/card.py` — `Card` entity con `approve()`, `is_publishable()`
- [ ] **[11]** `domain/repositories/user_repository.py` — `IUserRepository` ABC
- [ ] **[12]** `domain/repositories/card_repository.py` — `ICardRepository` ABC
- [ ] **[13]** `domain/exceptions.py` — todas las excepciones de dominio

### Fase 3 — Capa de aplicación

- [ ] **[14]** `application/ports/password_service.py` — `IPasswordService` ABC
- [ ] **[15]** `application/use_cases/register_user.py` — `RegisterUserUseCase` con input/output DTOs
- [ ] **[16]** `application/use_cases/add_card_to_catalog.py` — `AddCardToCatalogUseCase` con input/output DTOs

### Fase 4 — Infraestructura

- [ ] **[17]** `infrastructure/persistence/database.py` — engine, `SessionLocal`, `Base`
- [ ] **[18]** `infrastructure/persistence/models.py` — `UserORM`, `CardORM` con `UniqueConstraint` en `CardORM`
- [ ] **[19]** `infrastructure/persistence/user_repository.py` — `UserRepositoryImpl(IUserRepository)`
- [ ] **[20]** `infrastructure/persistence/card_repository.py` — `CardRepositoryImpl(ICardRepository)`
- [ ] **[21]** `infrastructure/security/password.py` — `BcryptPasswordService(IPasswordService)`
- [ ] **[22]** `infrastructure/security/jwt.py` — `JWTService` con `create_access_token` y `decode_token`

### Fase 5 — API layer

- [ ] **[23]** `api/v1/schemas/auth.py` — `RegisterRequest` (Pydantic), `RegisterResponse`
- [ ] **[24]** `api/v1/schemas/catalog.py` — `AddCardRequest` (Pydantic), `CardResponse`
- [ ] **[25]** `api/v1/dependencies.py` — `get_current_user`, `require_admin`
- [ ] **[26]** `api/v1/routers/auth.py` — `POST /api/v1/auth/register`
- [ ] **[27]** `api/v1/routers/catalog.py` — `POST /api/v1/catalog/cards`
- [ ] **[28]** `main.py` — app con lifespan, include routers, CORS, exception handlers

### Fase 6 — Migraciones Alembic

- [ ] **[29]** `alembic/env.py` — configurado con `target_metadata = Base.metadata`
- [ ] **[30]** `alembic/versions/001_create_users.py` — tabla `users`
- [ ] **[31]** `alembic/versions/002_create_catalog_cards.py` — tabla `catalog_cards`

### Fase 7 — Tests unitarios

- [ ] **[32]** `tests/unit/test_register_user.py`
  - [ ] Registro exitoso
  - [ ] Email duplicado lanza EmailAlreadyExistsError
  - [ ] Disclosure no aceptado lanza DisclosureNotAcceptedError
  - [ ] Rol asignado es SUBMITTER por defecto
  - [ ] Password en output nunca en texto plano
- [ ] **[33]** `tests/unit/test_add_card_to_catalog.py`
  - [ ] Adición exitosa por Admin
  - [ ] No-Admin lanza UnauthorizedError
  - [ ] Identidad duplicada lanza CardAlreadyExistsError
  - [ ] Estado inicial es PENDING
  - [ ] version = 1, created_by correcto

### Fase 8 — Tests de integración

- [ ] **[34]** `tests/integration/conftest.py` — TestClient + SQLite en memoria + fixtures
- [ ] **[35]** `tests/integration/test_auth_routes.py`
  - [ ] POST /api/v1/auth/register → 201 + token
  - [ ] POST /api/v1/auth/register email duplicado → 409
  - [ ] POST /api/v1/auth/register email inválido → 422
  - [ ] POST /api/v1/auth/register sin disclosure → 400
- [ ] **[36]** `tests/integration/test_catalog_routes.py`
  - [ ] POST /api/v1/catalog/cards como admin → 201
  - [ ] POST /api/v1/catalog/cards como submitter → 403
  - [ ] POST /api/v1/catalog/cards sin token → 401
  - [ ] POST /api/v1/catalog/cards identidad duplicada → 409

---

## Orden de implementación recomendado

```
requirements.txt → pyproject.toml → .env.example → alembic.ini
→ config.py → domain/* → application/* → infrastructure/*
→ api/* → main.py → alembic/env.py → alembic/versions/*
→ tests/unit/* → tests/integration/*
```

---

## Notas técnicas

- JWT: `python-jose[cryptography]` — HS256, expiración configurable (default 60 min)
- Password: `passlib[bcrypt]` — bcrypt rounds = 12
- DB para tests: SQLite en memoria con `create_all` en fixture (no corre Alembic en tests)
- Tests sin side effects: cada test usa su propia sesión de DB aislada
- Cobertura mínima: 75% en `domain/` y `application/` (RNF S4)
- Ninguna credencial en código fuente (RNF S9)
- Separadores de tablas ADO-compatibles en este archivo: `|---|---|`

---

*Documento generado Sprint 1 — PokéGrading v1.6 — mayo 2026*
