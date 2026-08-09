# Diseño de la capa API v2

**Ruta:** `src/pokegrading/api/v2/`  
**Prefijo de rutas:** `/api/v2`

---

## Estructura de archivos

```
api/
└── v2/
    ├── dependencies.py       ← inyección de usuario autenticado
    ├── routers/
    │   ├── auth.py           ← /auth/register, /auth/login, gestión de usuarios
    │   └── catalog.py        ← /catalog/cards CRUD
    └── schemas/
        ├── auth.py           ← modelos Pydantic de request/response para auth
        └── catalog.py        ← modelos Pydantic de request/response para catálogo
```

---

## Por qué versionar en `v2`

La carpeta se llama `v2` (y el prefijo de rutas es `/api/v2`) para aislar contratos HTTP. Si en el futuro se necesita un cambio breaking — por ejemplo, renombrar un campo en la respuesta o cambiar la forma del body — se crea una carpeta `v3/` sin romper los clientes que usan `v2`. Los clientes eligen explícitamente qué versión consumen.

Regla práctica:
- Cambio **non-breaking** (campo nuevo opcional, endpoint nuevo): no incrementa versión
- Cambio **breaking** (campo requerido nuevo, campo eliminado, tipo cambiado): nueva versión

---

## `dependencies.py` — el patrón `Depends()`

FastAPI tiene un sistema de **inyección de dependencias** basado en la función `Depends()`. Cuando un endpoint declara un parámetro con `Depends(alguna_función)`, FastAPI llama a esa función automáticamente antes de ejecutar el handler y pasa el resultado como argumento.

`dependencies.py` define dos dependencias reutilizables:

### `get_current_user()`

```python
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
```

**Qué hace, paso a paso:**
1. `HTTPBearer(auto_error=False)` extrae el token del header `Authorization: Bearer <token>`. Si no hay header, devuelve `None` (no lanza error todavía).
2. Si `credentials` es `None` → lanza `401 Unauthorized`.
3. Llama a `JWTService.decode_token()` → obtiene el payload `{sub, role, exp}`.
4. Extrae el `sub` (UUID del usuario).
5. Consulta `UserRepositoryImpl.find_by_id()` → obtiene la entidad `User`.
6. Si no existe o está inactivo → lanza `401`.
7. Devuelve el `User` al handler.

### `require_admin()`

```python
def require_admin(current_user: User = Depends(get_current_user)) -> User:
```

Encadena `get_current_user` y además verifica que el usuario tenga rol `admin`. Si no → `403 Forbidden`.

**Cómo se usan en los routers:**

```python
# Endpoint público (sin autenticación)
@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    ...

# Endpoint autenticado (cualquier usuario logueado)
@router.get("/cards")
def list_cards(current_user: User = Depends(get_current_user)):
    ...

# Endpoint solo admin
@router.delete("/cards/{card_id}")
def delete_card(current_user: User = Depends(require_admin)):
    ...
```

---

## `schemas/` — diferencia con las entidades de dominio

Existen **dos representaciones** de los mismos datos:

| Concepto | Dónde vive | Para qué sirve |
|----------|-----------|----------------|
| **Schema Pydantic** | `api/v2/schemas/` | Define el contrato HTTP: qué acepta el request, qué devuelve el response. Incluye validaciones de formato (`min_length`, `EmailStr`, `pattern`). Solo existe en la capa API. |
| **Entidad de dominio** | `domain/entities/` | Representa la lógica de negocio. No sabe nada de HTTP ni de JSON. Contiene las reglas del negocio (`is_admin()`, invariantes). |

**Ejemplo — registro de usuario:**

```
RegisterRequest (schema)        →   RegisterUserInput (use case DTO)   →   User (entidad)
  email: "a@b.com"                    email: "a@b.com"                       id: UUID7
  password: "abc12345"                password: "abc12345"                   email: "a@b.com"
  alias: "Randall"                    alias: "Randall"                       hashed_password: "$2b$..."
  accept_disclosure: true             accept_disclosure: True                role: UserRole.SUBMITTER
```

El router convierte `RegisterRequest` → `RegisterUserInput`. El use case convierte el input → `User`. El router convierte `RegisterUserOutput` → `RegisterResponse`. **El dominio nunca ve ni importa Pydantic.**

---

## Flujo completo: router → use case → repository

### US-001 — Registrar usuario

```
POST /api/v2/auth/register
         │
         ▼
routers/auth.py → def register(body: RegisterRequest)
    │   Construye RegisterUserInput desde el body
    │   Instancia RegisterUserUseCase(user_repo, password_service)
    ▼
application/use_cases/register_user.py → RegisterUserUseCase.execute()
    │   Verifica que el email no exista (user_repo.find_by_email)
    │   Hashea la contraseña (password_service.hash)
    │   Crea User con id=uuid7(), role=SUBMITTER
    │   Persiste (user_repo.save)
    ▼
infrastructure/persistence/repositories/user/user_repository.py → UserRepositoryImpl.save()
    │   INSERT en tabla users
    ▼
    Retorna RegisterUserOutput al router
         │
         ▼
    Serializa a RegisterResponse (JSON) → HTTP 201
```

### US-002 — Agregar carta al catálogo

```
POST /api/v2/catalog/cards
    Authorization: Bearer <token>
         │
         ▼
Depends(get_current_user) → verifica JWT → devuelve User
         │
         ▼
routers/catalog.py → def add_card(body: AddCardRequest, current_user: User)
    │   Construye AddCardInput desde body + current_user.id
    │   Instancia AddCardToCatalogUseCase(card_repo, user_repo)
    ▼
application/use_cases/add_card_to_catalog.py → AddCardToCatalogUseCase.execute()
    │   Verifica que el usuario existe y está activo
    │   Verifica unicidad por identidad (set+number+edition+language+finish)
    │   Crea Card con id=uuid7(), status=PENDING
    │   Persiste (card_repo.save)
    ▼
infrastructure/persistence/repositories/card/card_repository.py → CardRepositoryImpl.save()
    │   INSERT en tabla catalog_cards
    ▼
    Retorna AddCardOutput al router
         │
         ▼
    Serializa a CardDetailResponse (JSON) → HTTP 201
```

---

## Endpoints disponibles

### Auth (`/api/v2/auth/`)

| Método | Ruta | Auth requerida | Descripción |
|--------|------|---------------|-------------|
| POST | `/register` | No | Crear cuenta nueva (US-001) |
| POST | `/login` | No | Obtener JWT |
| GET | `/users` | Admin | Listar todos los usuarios |
| GET | `/users/me` | Cualquier usuario | Ver mi perfil |
| PATCH | `/users/{user_id}` | Admin | Modificar usuario |
| DELETE | `/users/{user_id}` | Admin | Desactivar usuario |

### Catalog (`/api/v2/catalog/`)

| Método | Ruta | Auth requerida | Descripción |
|--------|------|---------------|-------------|
| POST | `/cards` | Cualquier usuario | Agregar carta (US-002) |
| GET | `/cards` | Cualquier usuario | Listar cartas |
| GET | `/cards/{card_id}` | Cualquier usuario | Ver carta por ID |
| PATCH | `/cards/{card_id}` | Admin | Actualizar carta |
| DELETE | `/cards/{card_id}` | Admin | Eliminar carta |
