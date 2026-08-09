# Documentación del flujo JWT — PokeGrading API

**Versión API:** v2  
**Algoritmo:** HS256  
**Librería:** `python-jose`

---

## ¿Qué es el token?

Cuando un usuario hace login, el backend devuelve un **JWT (JSON Web Token)**. Este token es una cadena que el cliente debe incluir en cada request a endpoints protegidos.

El token tiene tres partes separadas por puntos (`header.payload.signature`). El payload contiene:

```json
{
  "sub": "06a1b9d6-ae0d-79c8-8000-bef42f1fda96",
  "role": "admin",
  "exp": 1748650800
}
```

| Campo | Descripción |
|-------|-------------|
| `sub` | UUID del usuario (UUID v7 desde Sprint 2) |
| `role` | `submitter` o `admin` |
| `exp` | Timestamp UNIX de expiración |

**Tiempo de expiración:** configurable con `JWT_EXPIRE_MINUTES` en `.env` (default: 60 minutos).

---

## Paso 1 — Obtener el token

```
POST /api/v2/auth/login
Content-Type: application/json

{
  "email": "usuario@example.com",
  "password": "contraseña"
}
```

**Respuesta exitosa (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errores posibles:**
- `401` — credenciales inválidas
- `422` — body malformado

---

## Paso 2 — Usar el token

El token se envía en el header `Authorization` con el esquema `Bearer`:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### En Swagger UI (`/docs`)

1. Abre `http://localhost:8000/docs`
2. Haz login con `POST /api/v2/auth/login` desde la misma interfaz
3. Copia el valor de `access_token` (sin comillas)
4. Haz clic en el botón **Authorize** (candado 🔓) en la esquina superior derecha
5. Pega el token en el campo **BearerAuth** → clic en **Authorize**
6. Todos los requests siguientes incluirán el header automáticamente

> La sesión persiste mientras tengas la pestaña abierta (`persistAuthorization: true`).

### En PowerShell

```powershell
# 1. Login y guardar token
$body = '{"email":"admin@example.com","password":"admin1234"}'
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v2/auth/login" `
    -Method POST -Body $body -ContentType "application/json"
$token = $response.access_token

# 2. Usar el token en un request protegido
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Uri "http://localhost:8000/api/v2/catalog/cards" `
    -Method GET -Headers $headers
```

### En curl

```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin1234"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Usar token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/catalog/cards
```

---

## ¿Qué pasa si el token expira?

El backend devuelve `401 Unauthorized` con el mensaje `"Token inválido o expirado"`. El cliente debe volver al paso 1 y hacer login de nuevo.

No existe refresh token en esta versión. El flujo es: login → usar token → expiró → login de nuevo.

---

## Flujo completo resumido

```
Cliente                          Backend
  |                                 |
  |-- POST /api/v2/auth/login ----> |
  |                                 |-- verifica email + bcrypt
  |                                 |-- genera JWT (sub, role, exp)
  |<-- 200 { access_token } ------- |
  |                                 |
  |-- GET /api/v2/catalog/cards --> |
  |   Authorization: Bearer <token> |-- HTTPBearer extrae token
  |                                 |-- JWTService.decode_token()
  |                                 |-- UserRepository.find_by_id(sub)
  |                                 |-- inyecta User en el handler
  |<-- 200 [ ...cards ] ----------- |
```

---

## Dónde está el código

| Responsabilidad | Archivo |
|-----------------|---------|
| Generar el token | `infrastructure/security/jwt.py → JWTService.create_access_token()` |
| Verificar el token | `infrastructure/security/jwt.py → JWTService.decode_token()` |
| Extraer usuario del token | `api/v2/dependencies.py → get_current_user()` |
| Requerir rol admin | `api/v2/dependencies.py → require_admin()` |
| Configuración (secreto, expiración) | `config.py → Settings` + `.env` |
