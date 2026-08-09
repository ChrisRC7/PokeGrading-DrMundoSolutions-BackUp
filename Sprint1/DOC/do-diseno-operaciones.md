# DO: Diseño de Operaciones — PokéGrading

---

## Alcance

Este documento define la estrategia de operaciones de PokéGrading: ambientes de
despliegue, pipeline de CI/CD, estrategia de releases, procedimientos de rollback,
objetivos de nivel de servicio (SLA) y runbook de respuesta a incidentes.

La configuración técnica de presupuestos, alertas de Azure Monitor y responsables
de monitoreo se documenta en **Presupuesto y Alertas en Azure**.

---

## Ambientes

| Ambiente | Propósito | URL base | Protección |
|---|---|---|---|
| Local (dev) | Desarrollo individual; cada desarrollador corre la aplicación en su máquina | http://localhost:8000 | Sin restricciones |
| Staging | Validación integrada del sprint; pruebas del equipo y demo al cliente | https://app-pokegrading-stg.azurewebsites.net | Acceso solo al equipo |
| Producción | Versión estable al cierre de sprint; acceso del cliente final | https://app-pokegrading-prod.azurewebsites.net | Acceso público controlado |

### Diferencias entre ambientes

| Aspecto | Local | Staging | Producción |
|---|---|---|---|
| Base de datos | PostgreSQL local (Docker) | psql-pokegrading-stg | psql-pokegrading-prod |
| Almacenamiento de imágenes | Carpeta local temporal | stpokegradingstg | stpokegradingprod |
| Secretos | Archivo .env local (excluido de Git) | Azure Key Vault | Azure Key Vault |
| Logs | Consola | Application Insights stg | Application Insights prod + Log Analytics |
| Escala | 1 instancia manual | 1 instancia fija (B1) | 1 instancia escalable (P1v3) |
| Datos | Datos de prueba sintéticos | Datos de prueba sintéticos | Datos reales del cliente |

---

## Pipeline de CI/CD (Azure DevOps)

Cada push a una rama `Develop<Nombre>` o a `develop` desencadena el pipeline de CI.
El despliegue a staging se activa al hacer merge a `develop`; el despliegue a
producción al hacer merge a `main`.

### Etapas del pipeline

```
Push a Develop<Nombre> o develop
  |
  Stage 1: Lint
    ruff check src/ tests/
    black --check src/ tests/
    isort --check src/ tests/
    |
    (falla -> PR bloqueado)
  |
  Stage 2: Test
    pytest tests/unit/ tests/integration/ --cov=src --cov-fail-under=75
    |
    (falla -> PR bloqueado)
  |
  Stage 3: Build
    docker build -t crpokegrading.azurecr.io/pokegrading-api:<sha> .
    docker push crpokegrading.azurecr.io/pokegrading-api:<sha>

Push a develop (merge aprobado)
  |
  Stage 4: Deploy Staging
    az webapp config container set ... (imagen del stage 3)
    az webapp restart --name app-pokegrading-stg
    Health check: GET /api/v1/health -> 200 OK

Push a main (merge aprobado al cierre de sprint)
  |
  Stage 5: Deploy Producción
    (mismos pasos que staging pero sobre app-pokegrading-prod)
    Tag de versión automático: git tag vX.Y.Z
    Health check: GET /api/v1/health -> 200 OK
```

### Variables y secretos del pipeline

Ninguna credencial se almacena en el repositorio ni en la configuración del pipeline
en texto plano. Todos los valores sensibles se configuran como:

| Variable | Origen | Usado en |
|---|---|---|
| AZURE_SUBSCRIPTION_ID | Azure DevOps variable group (secreto) | Todos los stages de deploy |
| ACR_USERNAME / ACR_PASSWORD | Azure DevOps variable group (secreto) | Stage Build |
| DATABASE_URL | Azure Key Vault | Runtime de la aplicación (no en pipeline) |
| AZURE_STORAGE_CONNECTION_STRING | Azure Key Vault | Runtime de la aplicación |

---

## Estrategia de releases

| Evento | Acción | Responsable |
|---|---|---|
| Fin de sprint | PR develop -> main; tag vX.Y.Z; despliegue a producción | Tech Lead |
| Hotfix urgente | Rama hotfix/descripcion desde main; PR directo a main con 2 aprobaciones | Tech Lead + 1 reviewer |
| Feature incompleta al fin de sprint | Permanece en develop; no se incluye en el release | Scrum Master decide |

### Versionado

Formato: `vMAYOR.MENOR.PARCHE` (Semantic Versioning)

- MAYOR: cambio de arquitectura o ruptura de compatibilidad de API
- MENOR: nueva funcionalidad al cierre de sprint
- PARCHE: hotfix en producción

Ejemplo: `v1.0.0` al primer release de Sprint 1; `v1.1.0` al cierre de Sprint 2.

---

## Procedimiento de rollback

### Rollback de aplicación (App Service)

Si el despliegue a producción introduce un error crítico:

```
1. Portal de Azure -> app-pokegrading-prod -> Deployment Center
2. Identificar el slot o la imagen anterior en el historial de despliegues
3. Volver a la imagen anterior:
   az webapp config container set \
     --name app-pokegrading-prod \
     --resource-group rg-pokegrading-prod \
     --docker-custom-image-name crpokegrading.azurecr.io/pokegrading-api:<sha-anterior>
4. Verificar health check: GET /api/v1/health -> 200 OK
5. Notificar al equipo y abrir issue en Azure DevOps con causa raíz
```

### Rollback de base de datos (Alembic)

Si una migración introduce un error en esquema:

```
alembic downgrade -1
```

Para volver a una revisión específica:

```
alembic downgrade <revision_id>
```

> Las migraciones de producción siempre deben ser reversibles.
> Antes de desplegar a producción, verificar que `alembic downgrade -1` no pierde datos.

---

## Objetivos de nivel de servicio (SLA)

| Métrica | Objetivo | Medición |
|---|---|---|
| Disponibilidad de la API | >= 99% mensual en producción | Azure Monitor availability tests |
| Latencia de evaluación completa | p95 <= 30 s (RNF P1) | Application Insights |
| Latencia de respuesta de API | p95 <= 2 s para endpoints de consulta (RNF P2) | Application Insights |
| Tiempo de recuperación (RTO) | <= 4 h ante fallo de plataforma (RNF R8) | Simulacro por sprint |
| Punto de recuperación (RPO) | <= 24 h de pérdida máxima de datos (RNF R9) | Backup PostgreSQL diario |
| Tiempo de revisión humana | p95 <= 24 h (RNF S13) | Azure DevOps work item tracking |

---

## Runbook de respuesta a incidentes

### Niveles de severidad

| Nivel | Descripción | Tiempo de respuesta | Notificación |
|---|---|---|---|
| SEV 1 — Critico | Producción caída o datos corruptos | 30 min | Tech Lead + todo el equipo |
| SEV 2 — Alto | Degradación significativa en producción (latencia alta, errores 5xx) | 2 h | Tech Lead + responsable de infraestructura |
| SEV 3 — Medio | Degradación menor o fallo en staging | 24 h | Responsable de infraestructura |
| SEV 4 — Bajo | Alerta informativa; sin impacto en usuario | Próximo sprint | Equipo en general |

### Proceso de respuesta SEV 1

```
1. Detectar: alerta de Azure Monitor o reporte de usuario
2. Confirmar: verificar en Application Insights que el problema es real
3. Comunicar: notificar al equipo en el canal de comunicación del proyecto
4. Contener: ejecutar rollback de aplicación si el despliegue reciente es la causa
5. Investigar: revisar logs en Log Analytics; identificar causa raíz
6. Resolver: aplicar fix; desplegar; verificar health check
7. Postmortem: documentar causa raíz, línea de tiempo y acciones preventivas
               en Azure DevOps como tarea de tipo "Postmortem"
```

### Escalación

| Situación | Escala a |
|---|---|
| Tech Lead no disponible | Miembro senior del equipo asume temporalmente |
| Fallo de plataforma Azure (no del equipo) | Abrir ticket en Azure Support; seguir estado en https://status.azure.com |
| Brecha de seguridad o fuga de datos | Tech Lead notifica al profesor del curso y sigue protocolo de Ley 8968 |

---

## Health check endpoint

La aplicación expone un endpoint estándar de salud que el pipeline y Azure Monitor
usan para verificar que el servicio está operativo:

```
GET /api/v1/health
```

Respuesta esperada (HTTP 200):

```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "connected",
  "storage": "connected"
}
```

Si alguna dependencia falla, el endpoint responde HTTP 503 con el componente
que falló identificado en el cuerpo.

---

*Documento generado en mayo 2026 — PokéGrading v1.6 / Sprint 1*

### Pasos para crear un presupuesto

```
1. Portal de Azure -> Cost Management + Billing
2. Seleccionar la suscripción del proyecto
3. Budgets -> + Add
4. Scope: seleccionar el grupo de recursos correspondiente
           (rg-pokegrading-staging o rg-pokegrading-prod)
5. Name: budget-pokegrading-staging (o -prod)
6. Reset period: Monthly
7. Creation date: primer día del sprint activo
8. Expiration date: último día del proyecto
9. Amount: 80 (staging) o 800 (producción)
10. Next -> agregar Alert conditions (thresholds)
11. Asociar un Action Group existente o crear uno nuevo (ver sección siguiente)
12. Review + create
```

### Parámetros de los presupuestos

#### budget-pokegrading-staging

| Parámetro | Valor |
|---|---|
| Nombre | budget-pokegrading-staging |
| Alcance | rg-pokegrading-staging |
| Período | Monthly |
| Monto | $80 USD |
| Threshold 1 | 70% — tipo Actual — Action Group: ag-pokegrading-staging-info |
| Threshold 2 | 90% — tipo Actual — Action Group: ag-pokegrading-staging-warn |
| Threshold 3 | 100% — tipo Actual — Action Group: ag-pokegrading-critical |

#### budget-pokegrading-prod

| Parámetro | Valor |
|---|---|
| Nombre | budget-pokegrading-prod |
| Alcance | rg-pokegrading-prod |
| Período | Monthly |
| Monto | $800 USD |
| Threshold 1 | 60% — tipo Actual — Action Group: ag-pokegrading-prod-info |
| Threshold 2 | 80% — tipo Actual — Action Group: ag-pokegrading-prod-info |
| Threshold 3 | 95% — tipo Actual — Action Group: ag-pokegrading-critical |

---

## Action Groups — configuración de notificaciones

Los Action Groups definen quién recibe la notificación y por qué canal cuando
se dispara una alerta (de costo u operativa).

### Crear un Action Group

```
Portal de Azure -> Monitor -> Alerts -> Action groups -> + Create
  Subscription: (suscripción del proyecto)
  Resource group: rg-pokegrading-shared
  Action group name: ag-pokegrading-<nombre>
  Display name: (mismo, máx. 12 caracteres)
  -> Notifications tab: agregar Email/SMS/Push/Voice con correos del equipo
  -> Actions tab: agregar webhook de Teams si aplica
  Review + create
```

### Action Groups del proyecto

| Action Group | Tipo de notificación | Destinatarios | Cuándo se usa |
|---|---|---|---|
| ag-pokegrading-staging-info | Email | Todos los miembros del equipo | Umbral 70% staging |
| ag-pokegrading-staging-warn | Email + Teams webhook | Tech Lead + responsable de infraestructura | Umbral 90% staging |
| ag-pokegrading-critical | Email | Tech Lead | Umbral 100% staging; 95% producción |
| ag-pokegrading-prod-info | Email | Tech Lead + responsable de infraestructura | Umbral 60% y 80% producción |

---

## Alertas operativas en Azure Monitor

Además de las alertas de costo, se configuran alertas de métricas sobre los
recursos de producción para detectar degradación de servicio.

### Crear una alerta de métrica

```
Portal de Azure -> Monitor -> Alerts -> + Create -> Alert rule
  Scope: seleccionar el recurso (App Service, PostgreSQL, etc.)
  Condition: seleccionar la señal (métrica)
  Threshold: configurar el valor y la ventana de tiempo
  Action group: seleccionar el Action Group correspondiente
  Alert rule name: alert-pokegrading-<descripcion>
  Severity: 0 (Critical) a 4 (Verbose)
  Review + create
```

### Alertas configuradas en producción

| Nombre de alerta | Recurso | Métrica | Condición | Severidad | Action Group |
|---|---|---|---|---|---|
| alert-app-cpu-high | app-pokegrading-prod | CPU Percentage | > 85% durante 5 min | Sev 2 | ag-pokegrading-prod-info |
| alert-db-storage-high | psql-pokegrading-prod | Storage Percent | > 80% | Sev 2 | ag-pokegrading-prod-info |
| alert-api-5xx | app-pokegrading-prod | Http5xx | > 10 en 5 min | Sev 1 | ag-pokegrading-critical |
| alert-api-latency | app-pokegrading-prod | HttpResponseTime | p95 > 2 s en 5 min | Sev 2 | ag-pokegrading-prod-info |
| alert-blob-capacity | stpokegradingprod | Used Capacity | > 80% del límite | Sev 3 | ag-pokegrading-prod-info |

### Alertas configuradas en staging

| Nombre de alerta | Recurso | Métrica | Condición | Severidad | Action Group |
|---|---|---|---|---|---|
| alert-app-cpu-stg | app-pokegrading-stg | CPU Percentage | > 90% durante 10 min | Sev 3 | ag-pokegrading-staging-info |
| alert-api-5xx-stg | app-pokegrading-stg | Http5xx | > 20 en 10 min | Sev 2 | ag-pokegrading-staging-warn |

---

## Diagnóstico y Log Analytics

### Habilitar Diagnostic Settings en un recurso

```
Portal de Azure -> recurso (App Service, PostgreSQL, Key Vault, Storage)
  -> Diagnostic settings -> + Add diagnostic setting
  Name: diag-<nombre-recurso>
  Destination: Send to Log Analytics workspace
  Workspace: log-pokegrading-prod (o -stg)
  Categorías a habilitar: (ver tabla siguiente)
  Save
```

### Categorías de log por recurso

| Recurso | Categorías habilitadas |
|---|---|
| app-pokegrading-prod | AppServiceHTTPLogs, AppServiceConsoleLogs, AppServiceAuditLogs |
| psql-pokegrading-prod | PostgreSQLLogs, QueryStoreRuntimeStatistics |
| kv-pokegrading-shared | AuditEvent |
| stpokegradingprod | StorageRead, StorageWrite, StorageDelete |

### Retención de logs

| Ambiente | Workspace | Retención |
|---|---|---|
| Staging | log-pokegrading-stg | 30 días |
| Producción | log-pokegrading-prod | 90 días |

---

## Checklist de operaciones por sprint

Al inicio de cada sprint el responsable de infraestructura verifica:

- [ ] Los presupuestos budget-pokegrading-staging y budget-pokegrading-prod están activos.
- [ ] Los tres umbrales de cada presupuesto tienen un Action Group asignado.
- [ ] Los Action Groups tienen los correos del equipo actualizados.
- [ ] Las alertas de Azure Monitor están activas en los recursos de producción.
- [ ] Los Diagnostic Settings están configurados y enviando logs a Log Analytics.
- [ ] Los workspaces de Log Analytics tienen la retención correcta (30/90 días).
- [ ] Se verificó en Cost Analysis que el gasto del mes anterior estuvo dentro del límite.

---

*Documento generado en mayo 2026 — PokéGrading v1.6 / Sprint 1*
