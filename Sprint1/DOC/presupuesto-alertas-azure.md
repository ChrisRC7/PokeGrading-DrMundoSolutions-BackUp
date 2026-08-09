# Presupuesto y Alertas en Azure — PokéGrading

---

## Restricciones de presupuesto del proyecto

Los límites de gasto están definidos como requisitos no funcionales del caso de negocio:

| Ambiente | Límite mensual | Fuente |
|---|---|---|
| Staging | $80 USD/mes | RNF S11 |
| Producción | $800 USD/mes | RNF S11 |

El equipo configura alertas en Azure Cost Management para recibir avisos antes de
alcanzar estos límites y tomar acción correctiva a tiempo.

---

## Desglose estimado de costos por servicio

### Ambiente Staging

| Servicio Azure | Tier / SKU estimado | Costo estimado USD/mes | Notas |
|---|---|---|---|
| Azure App Service | B1 (Basic, 1 core, 1.75 GB RAM) | ~$13 | Backend FastAPI |
| Azure Database for PostgreSQL | Flexible Server B1ms (1 vCore, 2 GB) | ~$25 | Base de datos |
| Azure Blob Storage | LRS, 50 GB estimados | ~$1 | Imágenes de cartas |
| Azure Key Vault | Standard, < 10,000 operaciones/mes | ~$0.10 | Secretos y conexiones |
| Azure DevOps | Plan Basic hasta 5 usuarios | $0 (gratuito) | CI/CD y backlog |
| Azure Monitor / Application Insights | Plan Basic (5 GB/mes gratis) | ~$0 | Logs y métricas |
| **Total estimado staging** | | **~$39/mes** | Margen de ~$41 sobre el límite |

### Ambiente Producción

| Servicio Azure | Tier / SKU estimado | Costo estimado USD/mes | Notas |
|---|---|---|---|
| Azure App Service | P1v3 (2 cores, 8 GB RAM) | ~$138 | Backend con escala |
| Azure Database for PostgreSQL | Flexible Server D2s_v3 (2 vCores, 8 GB) | ~$185 | Alta disponibilidad |
| Azure Blob Storage | LRS, 500 GB estimados | ~$10 | Imágenes de cartas; lifecycle activo |
| Azure Key Vault | Standard, ~100,000 operaciones/mes | ~$1 | Secretos y conexiones |
| Azure CDN | 100 GB/mes outbound | ~$8 | Distribución de assets estáticos |
| Azure Monitor / Log Analytics | 10 GB/mes de ingesta | ~$23 | Retención 30 días |
| Azure DevOps | Plan Basic hasta 5 usuarios | $0 | CI/CD y backlog |
| Backup (PostgreSQL) | Locally Redundant, 7 días | ~$5 | RPO <= 24 h (RNF R9) |
| **Total estimado producción** | | **~$370/mes** | Margen de ~$430 sobre el límite |

> Los costos son estimaciones basadas en Azure Pricing Calculator (mayo 2026).
> Validar con precios actuales en https://azure.microsoft.com/pricing/calculator
> antes de cada sprint.

---

## Cómo funciona Azure Cost Management

Azure Cost Management + Billing es el servicio nativo de Azure para visualizar,
analizar y controlar el gasto en la suscripción.

### Conceptos clave

| Concepto | Descripción |
|---|---|
| Budget (Presupuesto) | Límite de gasto configurado para un período (mensual) y un alcance (suscripción o grupo de recursos) |
| Threshold (Umbral) | Porcentaje del presupuesto que, al alcanzarse, dispara una alerta; se pueden configurar múltiples umbrales |
| Action Group | Grupo de acciones (email, webhook, SMS) que se ejecutan cuando se dispara una alerta |
| Cost Analysis | Vista de desglose de costos por servicio, etiqueta, grupo de recursos o período de tiempo |
| Forecast | Proyección de gasto al cierre del período basada en la tendencia actual |

### Pasos para crear un presupuesto en Azure Portal

```
1. Portal de Azure -> Cost Management + Billing
2. Seleccionar la suscripción del proyecto
3. Budgets -> + Add
4. Scope: seleccionar el grupo de recursos (rg-pokegrading-staging o -prod)
5. Name: budget-pokegrading-staging (o -prod)
6. Reset period: Monthly
7. Amount: 80 (staging) o 800 (producción)
8. Next -> agregar Alert conditions con los umbrales y porcentajes
9. Asociar un Action Group con los correos del equipo
10. Review + create
```

---

## Configuración de presupuestos y umbrales

### Presupuesto de Staging

| Parámetro | Valor |
|---|---|
| Nombre | budget-pokegrading-staging |
| Alcance | Grupo de recursos rg-pokegrading-staging |
| Período | Mensual (reseteo el día 1 de cada mes) |
| Monto límite | $80 USD |
| Umbral 1 | 70% ($56) — Notificación informativa; revisar tendencia |
| Umbral 2 | 90% ($72) — Advertencia; analizar y reducir uso si aplica |
| Umbral 3 | 100% ($80) — Critico; escalar al Tech Lead de inmediato |

### Presupuesto de Producción

| Parámetro | Valor |
|---|---|
| Nombre | budget-pokegrading-prod |
| Alcance | Grupo de recursos rg-pokegrading-prod |
| Período | Mensual |
| Monto límite | $800 USD |
| Umbral 1 | 60% ($480) — Notificación informativa |
| Umbral 2 | 80% ($640) — Advertencia; revisar servicios de mayor costo |
| Umbral 3 | 95% ($760) — Critico; pausar despliegues no esenciales |

---

## Action Groups — configuración de notificaciones

Los Action Groups definen quién recibe la notificación y por qué canal.

### Crear un Action Group

```
Portal de Azure -> Monitor -> Alerts -> Action groups -> + Create
  Resource group: rg-pokegrading-shared
  Action group name: ag-pokegrading-<nombre>
  -> Notifications: agregar Email con correos del equipo
  -> Actions: agregar webhook de Teams si aplica
  Review + create
```

### Catálogo de Action Groups

| Action Group | Destinatarios | Canal | Cuándo se activa |
|---|---|---|---|
| ag-pokegrading-staging-info | Todos los miembros del equipo | Email | Umbral 70% staging |
| ag-pokegrading-staging-warn | Tech Lead + responsable de infraestructura | Email + Teams webhook | Umbral 90% staging |
| ag-pokegrading-critical | Tech Lead | Email | Umbral 100% staging; 95% producción |
| ag-pokegrading-prod-info | Tech Lead + responsable de infraestructura | Email | Umbral 60% y 80% producción |

---

## Alertas operativas en Azure Monitor

Además de las alertas de costo, se configuran alertas de métricas sobre los recursos
de producción para detectar degradación de servicio.

### Crear una alerta de métrica

```
Portal de Azure -> Monitor -> Alerts -> + Create -> Alert rule
  Scope: seleccionar el recurso (App Service, PostgreSQL, etc.)
  Condition: seleccionar señal (métrica)
  Threshold: configurar valor y ventana de tiempo
  Action group: seleccionar el Action Group correspondiente
  Alert rule name: alert-pokegrading-<descripcion>
  Severity: 0 (Critical) a 4 (Verbose)
  Review + create
```

### Alertas configuradas en producción

| Nombre de alerta | Recurso | Métrica | Condición | Severidad | Action Group |
|---|---|---|---|---|---|
| alert-app-cpu-high | app-pokegrading-prod | CPU Percentage | > 85% por 5 min | Sev 2 | ag-pokegrading-prod-info |
| alert-db-storage-high | psql-pokegrading-prod | Storage Percent | > 80% | Sev 2 | ag-pokegrading-prod-info |
| alert-api-5xx | app-pokegrading-prod | Http5xx | > 10 en 5 min | Sev 1 | ag-pokegrading-critical |
| alert-api-latency | app-pokegrading-prod | HttpResponseTime | p95 > 2 s en 5 min | Sev 2 | ag-pokegrading-prod-info |
| alert-blob-capacity | stpokegradingprod | Used Capacity | > 80% del límite | Sev 3 | ag-pokegrading-prod-info |

### Alertas configuradas en staging

| Nombre de alerta | Recurso | Métrica | Condición | Severidad | Action Group |
|---|---|---|---|---|---|
| alert-app-cpu-stg | app-pokegrading-stg | CPU Percentage | > 90% por 10 min | Sev 3 | ag-pokegrading-staging-info |
| alert-api-5xx-stg | app-pokegrading-stg | Http5xx | > 20 en 10 min | Sev 2 | ag-pokegrading-staging-warn |

---

## Responsables de monitoreo

| Rol | Responsabilidad | Frecuencia mínima de revisión |
|---|---|---|
| Tech Lead | Revisar Cost Analysis general; tomar decisiones de escala o reducción | Semanal |
| Responsable de infraestructura | Verificar que presupuestos y alertas están activos; revisar recursos huérfanos | Semanal |
| Todo el equipo | Atender notificaciones de alertas y reportar anomalías al Tech Lead | Cuando llega alerta |
| Scrum Master | Incluir estado del presupuesto en la revisión de sprint | Por sprint |

### Proceso ante una alerta de costo

```
1. Identificar el servicio de mayor costo en Cost Management -> Cost Analysis
2. Evaluar si el costo es esperado (carga real) o anomalía (recurso mal configurado)
3a. Si es anomalía: apagar o redimensionar el recurso; notificar al equipo
3b. Si es crecimiento real: documentar en revisión de sprint; ajustar tier si hay margen
4. Registrar el evento en el backlog de Azure DevOps como tarea de operaciones
```

---

*Documento generado en mayo 2026 — PokéGrading v1.6 / Sprint 1*
