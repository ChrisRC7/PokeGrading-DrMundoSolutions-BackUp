# Diseño para el manejo de datos sensibles

**Proyecto:** PokéGrading — Dr. Mundo Solutions
**Sprint:** 3
**Relacionado:** [ADR-004](./ADR-004-api-b2b-lookup-catalogo.md), [diseno-versionamiento-seguridad-api.md](./diseno-versionamiento-seguridad-api.md), [cumplimiento-regulatorio.md](../../Sprint1/DOC/cumplimiento-regulatorio.md)

---

## 1. Objetivo

Documentar **qué datos sensibles** maneja PokéGrading, **cómo se protegen** en reposo, en tránsito y en logs, y **quién** puede acceder a ellos. Este diseño cubre tanto el sistema existente (usuarios, cartas, envíos) como el nuevo API B2B (llaves, auditoría).

---

## 2. Inventario y clasificación de datos sensibles

| Dato | Dónde vive | Clasificación | Protección |
|---|---|---|---|
| Contraseña de usuario | `users.hashed_password` | **Crítico** | bcrypt (12 rounds), nunca en claro ni en logs |
| **Secreto de API key B2B** | `api_keys.hashed_secret` | **Crítico** | HMAC-SHA256 + pepper, nunca en claro ni en logs |
| Pepper de API keys | env var / Key Vault | **Crítico** | Fuera de la BD y del repositorio |
| `JWT_SECRET_KEY` | env var / Key Vault | **Crítico** | Fuera del repositorio; rota-ble |
| Credenciales de BD | env var (`DATABASE_URL`) | **Crítico** | `.env` (gitignored) / Key Vault |
| Email del usuario | `users.email` | **PII** | Cifrado en reposo (gestionado), redactado en logs |
| Alias, país, idioma | `users.alias/country/...` | **PII** | Cifrado en reposo (gestionado) |
| Imágenes de envío | `submissions.image_*_data` | **PII / propiedad del usuario** | BYTEA (dev) / Blob privado (prod); acceso solo por dueño/admin |
| Datos de evaluación | `submissions.*` | **Confidencial por tienda/usuario** | **Nunca** expuestos por el API B2B |
| Auditoría B2B | `b2b_lookup_audit` | **Operacional** | Sin secretos; solo `key_prefix`, contadores |
| Token JWT (cliente) | `localStorage` navegador | **Sensible en cliente** | Riesgo XSS conocido (ver ADR-002 §4) |

---

## 3. Principios de manejo

1. **Hashing irreversible** para todo secreto verificable (contraseñas, secretos de API key). Nunca cifrado reversible para estos.
2. **Pepper/secretos fuera de la BD**: si la base de datos se filtra, los hashes no son crackeables sin el pepper, que vive en Key Vault.
3. **Mínima exposición**: el API B2B devuelve **solo** metadata de catálogo. Ninguna respuesta, log o error filtra evaluaciones, PII de usuarios ni datos de otras tiendas (AC-12).
4. **Redacción en logs**: ningún secreto, contraseña, email completo ni payload de imagen entra a los logs.
5. **Aislamiento por tenant**: una API key solo "ve" el catálogo (compartido y público entre tiendas). No existe ninguna ruta que cruce datos entre customers B2B.
6. **Defensa en profundidad**: validación en API (Pydantic) + dominio (value objects) + BD (constraints).

---

## 4. Protección en reposo y en tránsito

### En reposo

| Capa | Mecanismo |
|---|---|
| Secretos verificables | Hash (bcrypt / HMAC-SHA256), nunca texto plano |
| Cifrado de disco de la BD | Azure Database for PostgreSQL — cifrado transparente (TDE) gestionado |
| Imágenes (producción) | Azure Blob Storage, contenedor **privado**, acceso por SAS de corta duración |
| Secretos de configuración | Azure Key Vault (pepper, `JWT_SECRET_KEY`, `DATABASE_URL`) |

### En tránsito

| Tramo | Mecanismo |
|---|---|
| Cliente ↔ API | HTTPS/TLS obligatorio en producción |
| Tienda B2B ↔ API | HTTPS/TLS; API key en header `X-API-Key` (nunca en query string) |
| API ↔ PostgreSQL | Conexión TLS (`sslmode=require` en producción) |

---

## 5. Logging y redacción

**Regla de oro:** *si no puedes mostrárselo a un tercero, no lo loggees.*

### Qué SÍ se loggea (log estructurado JSON, por request B2B)

```json
{
  "trace_id": "9b2e7c1a-...",
  "ts": "2026-06-13T12:00:00Z",
  "route": "POST /api/b2b/v1/catalog/lookup",
  "customer_id": "c0ffee...",
  "api_key_prefix": "a1b2c3d4",
  "card_count": 30,
  "result": { "covered": 12, "multiple_match": 3, "not_covered": 14, "invalid_params": 1 },
  "status_code": 200,
  "latency_ms": 48,
  "idempotent_hit": false,
  "rate_limited": false,
  "key_in_grace": false
}
```

### Qué NUNCA se loggea

- El **secreto** de la API key (solo `api_key_prefix`).
- Contraseñas, hashes, pepper, `JWT_SECRET_KEY`, `DATABASE_URL`.
- **Email completo** del usuario → redactar (`j***@gmail.com`) si fuese necesario registrarlo.
- Bytes de imágenes de envío.
- Cualquier dato de evaluación o de otra tienda.

### Trazabilidad

- Cada request genera/propaga un `trace_id` (UUID) en `X-Trace-Id`, en el log y en el `error.trace_id` del formato único — el soporte correlaciona sin acceder a datos sensibles.
- La **auditoría persistente** (`b2b_lookup_audit`) es la fuente legal/operacional de "cada consulta queda registrada" (AC-15). Es independiente del log de aplicación (que puede rotarse/borrarse) y **no contiene secretos**.

---

## 6. Control de acceso

| Recurso | Quién accede | Cómo |
|---|---|---|
| Catálogo (lectura B2B) | Cualquier API key activa | `X-API-Key` válida + scope `catalog:lookup` |
| Imágenes de envío | Dueño del envío + Admin | JWT de usuario (`/api/v2`) |
| Datos de evaluación | Dueño + Admin | JWT; **jamás** vía API B2B |
| Tablas B2B (`api_keys`, etc.) | Operación (DBA) | Acceso directo a BD, auditado |
| Secretos de config | Pipeline / runtime | Key Vault con identidad gestionada |

> El catálogo es **compartido y no confidencial** entre tiendas (es la lista de cartas que PokéGrading reconoce). Por eso el lookup no necesita particionar datos por tenant: no hay datos de un customer que otro no pueda ver, porque solo se expone catálogo.

---

## 7. Retención y minimización

| Dato | Retención propuesta |
|---|---|
| `b2b_idempotency` | Ventana de idempotencia (24 h) + margen → limpieza programada |
| `b2b_rate_limit_counters` | Ventana de rate limit; ventanas viejas purgables |
| `b2b_lookup_audit` | Retención larga (requisito de auditoría) — sin secretos, bajo costo |
| Logs de aplicación | Rotación estándar (p.ej. 30–90 días) |
| Imágenes de envío | Según política de retención de US-003 |

Minimización: el API B2B **no** persiste las imágenes (no las recibe) ni copia datos de catálogo — solo lee.

---

## 8. Mapeo a cumplimiento

Este diseño da soporte a los controles descritos en [cumplimiento-regulatorio.md](../../Sprint1/DOC/cumplimiento-regulatorio.md):

- **Confidencialidad de credenciales** → hashing + pepper + Key Vault.
- **Trazabilidad/auditoría** → `trace_id` + `b2b_lookup_audit`.
- **Minimización de PII** → el API B2B no maneja PII; el resto redacta en logs.
- **Aislamiento** → solo se expone catálogo; nunca evaluaciones ni datos cruzados.

---

## 9. Checklist (Fase B)

- [ ] `hashed_secret` y `hashed_password` nunca salen de la BD en claro.
- [ ] Pepper y `JWT_SECRET_KEY` en env/Key Vault, no en repo.
- [ ] Middleware de logging redacta secretos y solo registra `api_key_prefix`.
- [ ] El serializador de respuesta B2B excluye por construcción cualquier campo de evaluación.
- [ ] `trace_id` presente en log, header y formato de error.
- [ ] TLS forzado en producción (cliente, B2B y BD).
- [ ] Tests verifican que la respuesta B2B no contiene campos prohibidos.

---

## Referencias

- [diseno-versionamiento-seguridad-api.md](./diseno-versionamiento-seguridad-api.md)
- [ADR-004 — API B2B](./ADR-004-api-b2b-lookup-catalogo.md)
- [ADR-002 — Almacenamiento](../../Sprint2/DOC/ADR-002-diseno-almacenamiento.md)
- [cumplimiento-regulatorio.md](../../Sprint1/DOC/cumplimiento-regulatorio.md)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
