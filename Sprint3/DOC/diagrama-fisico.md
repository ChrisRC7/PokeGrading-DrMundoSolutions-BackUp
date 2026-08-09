# Diagrama físico de la solución — primera versión (Sprint 3)

**Proyecto:** PokéGrading — Dr. Mundo Solutions
**Sprint:** 3
**Relacionado:** [ADR-002 — Almacenamiento](../../Sprint2/DOC/ADR-002-diseno-almacenamiento.md), [ADR-004 — API B2B](./ADR-004-api-b2b-lookup-catalogo.md)

> Primera versión del **diagrama físico** (vista de despliegue): nodos de hardware/runtime, los artefactos que corren en cada uno y los protocolos de comunicación. Se presenta el estado de **desarrollo** y la **proyección a producción (Azure)**.

---

## 1. Vista de despliegue — Desarrollo (local)

```mermaid
flowchart TB
    subgraph DevMachine["Máquina de desarrollo (Linux/Windows)"]
        subgraph Browser["Navegador"]
            FE["React + Vite SPA<br/>localStorage: JWT<br/>:5173"]
        end
        subgraph Node["Proceso Node (pnpm/vite dev)"]
            VITE["Vite dev server<br/>proxy /api → :8000"]
        end
        subgraph Py["Proceso Python (uvicorn)"]
            API["FastAPI app<br/>/api/v2 (usuarios)<br/>/api/b2b/v1 (B2B)<br/>:8000"]
            OCR["EasyOCR Reader<br/>singleton ~500MB RAM"]
            PHASH["pHash service<br/>imagehash + Pillow"]
        end
        subgraph PG["Proceso PostgreSQL"]
            DB[("PostgreSQL<br/>pokegrading_dev<br/>:5432")]
        end
        OCRW["~/.EasyOCR/model/<br/>(pesos en disco)"]
    end

    ExtStore["Sistema de Tienda B2B<br/>(cliente máquina-a-máquina)"]

    FE -->|HTTP :5173| VITE
    VITE -->|proxy HTTP :8000| API
    ExtStore -->|HTTPS + X-API-Key| API
    API --> OCR
    API --> PHASH
    OCR -.carga pesos.-> OCRW
    API -->|psycopg2 TCP :5432| DB
```

| Nodo | Artefacto | Puerto/Protocolo |
|---|---|---|
| Navegador | SPA React (build Vite) | HTTP :5173 |
| Proceso Node | Vite dev server (proxy a `/api`) | :5173 → :8000 |
| Proceso Python | FastAPI + Uvicorn (`pokegrading.main:app`) | :8000 |
| — | EasyOCR singleton (búsqueda especializada) | en-proceso |
| — | pHash service (búsqueda rápida) | en-proceso |
| Proceso PostgreSQL | BD relacional + BYTEA de imágenes | TCP :5432 |
| Disco | Pesos EasyOCR (`~/.EasyOCR/`) | filesystem |
| Externo | Sistema de tienda B2B | HTTPS + `X-API-Key` |

---

## 2. Vista de despliegue — Producción (Azure, proyección)

```mermaid
flowchart TB
    subgraph Internet
        UserBrowser["Usuario (navegador)"]
        Store["Tienda B2B (sistema)"]
    end

    subgraph Edge["Borde"]
        FD["Azure Front Door / App Gateway<br/>TLS, WAF"]
    end

    subgraph Static["Hosting estático"]
        SPA["SPA React<br/>Azure Static Web Apps / Blob+CDN"]
    end

    subgraph Compute["Cómputo (Azure Container Apps)"]
        APIc["FastAPI app (contenedor)<br/>/api/v2 + /api/b2b/v1<br/>autoescala N réplicas"]
        OCRc["Servicio OCR dedicado<br/>(contenedor inferencia)"]
    end

    subgraph Data["Datos gestionados"]
        PGc[("Azure Database for PostgreSQL<br/>Flexible Server, TLS")]
        BLOB["Azure Blob Storage<br/>imágenes (contenedor privado)"]
        REDIS[("Azure Cache for Redis<br/>rate limit + idempotencia")]
        KV["Azure Key Vault<br/>pepper, JWT_SECRET, DB creds"]
    end

    UserBrowser -->|HTTPS| FD
    Store -->|HTTPS + X-API-Key| FD
    FD --> SPA
    FD --> APIc
    APIc -->|TLS| PGc
    APIc --> BLOB
    APIc --> REDIS
    APIc -->|managed identity| KV
    APIc -->|gRPC/HTTP| OCRc
```

### 2.1 Diferencias dev → producción

| Componente | Desarrollo | Producción |
|---|---|---|
| SPA | Vite dev server | Static Web Apps / Blob + CDN |
| API | Uvicorn local | Container Apps (autoescala) |
| OCR | Singleton en-proceso | Contenedor de inferencia dedicado |
| Imágenes | BYTEA en PostgreSQL | Azure Blob Storage privado (SAS) |
| Rate limit / idempotencia | Tablas en PostgreSQL | Azure Cache for Redis |
| Secretos | `.env` | Azure Key Vault + managed identity |
| TLS | Opcional (localhost) | Obligatorio (Front Door / App Gateway) |

> Coherente con el "Plan de evolución a producción" de [ADR-002](../../Sprint2/DOC/ADR-002-diseno-almacenamiento.md). El API B2B (§ ADR-004) añade Redis para rate limit/idempotencia como única infraestructura nueva respecto a Sprint 2.

---

## 3. Artefactos desplegables

```mermaid
flowchart LR
    subgraph Repo["Monorepo"]
        BE["Backend Python<br/>src/pokegrading (pip install -e .)"]
        FEsrc["Frontend<br/>frontend/ (pnpm build)"]
        MIG["Migraciones Alembic<br/>alembic/versions/"]
        SEED["scripts/seed_b2b_api_key.py"]
    end
    BE --> IMG["Imagen Docker API"]
    FEsrc --> DIST["dist/ estático"]
    IMG --> CA["Container Apps"]
    DIST --> SWA["Static Web Apps"]
    MIG -->|alembic upgrade head| PGprod[("PostgreSQL")]
    SEED -->|inserta llave B2B| PGprod
```

| Artefacto | Cómo se produce | Dónde corre |
|---|---|---|
| Imagen Docker del API | `Dockerfile` sobre `src/pokegrading` | Container Apps |
| Bundle estático SPA | `pnpm build` → `frontend/dist` | Static Web Apps / CDN |
| Migraciones | `alembic upgrade head` | Job previo al despliegue |
| Seed de llave B2B | `python scripts/seed_b2b_api_key.py` | Job manual/operación |

---

## 4. Nota de evolución

Esta es la **primera versión** del diagrama físico. Pendiente de refinar en sprints futuros:

- Topología de red (VNet, subredes privadas, private endpoints para PostgreSQL/Blob).
- Estrategia de réplicas de lectura de PostgreSQL si la carga de lookup crece.
- Observabilidad (Azure Monitor / App Insights) y correlación por `trace_id`.
- Estrategia de despliegue (blue/green o canary) para el contrato B2B versionado.

---

## Referencias

- [ADR-002 — Almacenamiento del sistema](../../Sprint2/DOC/ADR-002-diseno-almacenamiento.md)
- [ADR-004 — API B2B](./ADR-004-api-b2b-lookup-catalogo.md)
- [diseno-versionamiento-seguridad-api.md](./diseno-versionamiento-seguridad-api.md)
