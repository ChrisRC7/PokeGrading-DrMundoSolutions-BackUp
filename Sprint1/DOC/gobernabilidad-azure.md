# Gobernabilidad de Recursos en Azure — PokéGrading

---

## Alcance

Este documento extiende la configuración de gobernabilidad base del proyecto
PokéGrading definiendo la estructura completa de recursos, convenciones de
nomenclatura, etiquetas, control de acceso, políticas y bloqueos aplicados
en la suscripción de Azure del equipo.

---

## Estructura de grupos de recursos

Todos los recursos de PokéGrading se organizan en tres grupos de recursos
con responsabilidades claramente separadas:

| Grupo de recursos | Propósito | Ambiente |
|---|---|---|
| rg-pokegrading-shared | Recursos compartidos entre ambientes: Key Vault, Container Registry, Azure DevOps connection | N/A (compartido) |
| rg-pokegrading-staging | Todos los recursos del ambiente de staging: App Service, PostgreSQL, Blob Storage, Monitor | Staging |
| rg-pokegrading-prod | Todos los recursos del ambiente de producción | Producción |

### Diagrama de organización de recursos

```
Suscripcion Azure (PokéGrading)
|
+-- rg-pokegrading-shared
|     Key Vault (kv-pokegrading-shared)
|     Container Registry (crpokegrading)
|
+-- rg-pokegrading-staging
|     App Service Plan (asp-pokegrading-stg)
|     App Service / Web App (app-pokegrading-stg)
|     PostgreSQL Flexible Server (psql-pokegrading-stg)
|     Storage Account (stpokegradingstg)
|     Application Insights (appi-pokegrading-stg)
|     Log Analytics Workspace (log-pokegrading-stg)
|
+-- rg-pokegrading-prod
      App Service Plan (asp-pokegrading-prod)
      App Service / Web App (app-pokegrading-prod)
      PostgreSQL Flexible Server (psql-pokegrading-prod)
      Storage Account (stpokegradingprod)
      Application Insights (appi-pokegrading-prod)
      Log Analytics Workspace (log-pokegrading-prod)
      Azure CDN
```

### Región de despliegue

| Parámetro | Valor |
|---|---|
| Región primaria | East US 2 (o la región definida por el equipo al crear la suscripción) |
| Justificación | Menor latencia desde Costa Rica entre las regiones con todos los servicios necesarios disponibles |
| Residencia de datos | Estados Unidos; documentar si aplica restricción de Ley 8968 sobre transferencia internacional |

---

## Convenciones de nomenclatura

Formato general: `<tipo>-<proyecto>-<ambiente>[-<instancia>]`

| Tipo de recurso | Prefijo | Ejemplo staging | Ejemplo producción |
|---|---|---|---|
| App Service Plan | asp | asp-pokegrading-stg | asp-pokegrading-prod |
| App Service (Web App) | app | app-pokegrading-stg | app-pokegrading-prod |
| PostgreSQL Flexible Server | psql | psql-pokegrading-stg | psql-pokegrading-prod |
| Storage Account | st | stpokegradingstg | stpokegradingprod |
| Key Vault | kv | kv-pokegrading-shared | kv-pokegrading-shared |
| Container Registry | cr | crpokegrading | crpokegrading |
| Application Insights | appi | appi-pokegrading-stg | appi-pokegrading-prod |
| Log Analytics Workspace | log | log-pokegrading-stg | log-pokegrading-prod |
| Virtual Network (si aplica) | vnet | vnet-pokegrading-stg | vnet-pokegrading-prod |

> Nota: Los Storage Accounts no admiten guiones; usar todo en minúsculas sin separadores.
> Máximo 24 caracteres.

---

## Etiquetas obligatorias (Tags)

Todos los recursos y grupos de recursos deben tener las siguientes etiquetas.
Las etiquetas son la base para el desglose de costos en Cost Management.

| Etiqueta | Valores posibles | Propósito |
|---|---|---|
| Project | pokegrading | Identificar todos los recursos del proyecto |
| Environment | staging, production, shared | Separar costos y accesos por ambiente |
| CostCenter | sprint1, sprint2, ... | Rastrear gasto por sprint |
| Owner | nombre del Tech Lead | Contacto de escalación |
| ManagedBy | dr-mundo-solutions | Identificar al equipo responsable |
| CreatedDate | YYYY-MM-DD | Trazabilidad de cuándo se creó el recurso |

### Verificación de etiquetas

Antes de cada revisión de sprint, el responsable de infraestructura debe verificar
que ningún recurso carezca de las etiquetas obligatorias:

```
Portal de Azure -> Cost Management -> Tag Inventory
  o
Azure CLI: az resource list --query "[?tags == null]" --output table
```

---

## Control de acceso basado en roles (RBAC)

### Asignaciones por grupo de recursos

| Rol Azure | Identidad / Grupo | Alcance | Justificación |
|---|---|---|---|
| Owner | Tech Lead (cuenta personal de Azure del equipo) | Suscripción | Administración de la suscripción y facturación |
| Contributor | Equipo de desarrollo (cada miembro) | rg-pokegrading-staging | Desplegar y configurar recursos de staging |
| Reader | Equipo de desarrollo | rg-pokegrading-prod | Ver recursos de producción sin poder modificar |
| Contributor | Tech Lead + responsable de infraestructura | rg-pokegrading-prod | Despliegues a producción |
| Key Vault Secrets User | App Service (Managed Identity) | kv-pokegrading-shared | Lectura de secretos en tiempo de ejecución |
| Key Vault Secrets Officer | Tech Lead + responsable de infraestructura | kv-pokegrading-shared | Gestión de secretos |
| Reader | Cliente / evaluador del curso | Suscripción | Visibilidad de arquitectura sin modificar recursos |

### Principio de menor privilegio

- Ningún miembro del equipo tiene rol Owner sobre los grupos de recursos de producción.
- Los servicios de aplicación usan **Managed Identity** para acceder a Key Vault y
  Storage; no se usan connection strings con credenciales en variables de entorno.
- Las credenciales de base de datos se almacenan en Key Vault; la aplicación
  las obtiene en tiempo de arranque.

---

## Políticas de Azure (Azure Policy)

Las siguientes políticas se asignan a la suscripción o a los grupos de recursos
para forzar cumplimiento automático.

| Política | Alcance | Efecto | Propósito |
|---|---|---|---|
| Require tags on resources | Suscripción | Deny | Ningún recurso puede crearse sin las etiquetas obligatorias |
| Allowed locations | Suscripción | Deny | Solo se permiten recursos en la región definida; evita despliegues accidentales en otras regiones |
| Allowed resource types | rg-pokegrading-staging y prod | Audit | Registrar si se crean tipos de recursos no esperados |
| Storage account secure transfer | Suscripción | Deny | Forzar HTTPS en todas las cuentas de almacenamiento |
| PostgreSQL SSL enforcement | Suscripción | Audit | Verificar que SSL esté habilitado en todas las instancias de PostgreSQL |
| Key Vault soft delete | Suscripción | Deny | Impedir la eliminación permanente inmediata de secretos y claves |
| Diagnostic settings enabled | rg-pokegrading-prod | Audit | Alertar si algún recurso de producción no envía logs a Log Analytics |

### Cómo asignar una política

```
Portal de Azure -> Policy -> Assignments -> + Assign Policy
  Seleccionar scope (suscripción o grupo de recursos)
  Buscar la política por nombre
  Configurar parámetros (región, tags requeridos, etc.)
  Assign
```

---

## Bloqueos de recursos (Resource Locks)

Los bloqueos protegen recursos críticos de eliminaciones o modificaciones accidentales.

| Recurso | Tipo de bloqueo | Justificación |
|---|---|---|
| rg-pokegrading-prod | CanNotDelete | Impedir borrado accidental de todo el ambiente de producción |
| psql-pokegrading-prod | CanNotDelete | Proteger la base de datos de producción con datos reales |
| kv-pokegrading-shared | CanNotDelete | El Key Vault contiene todos los secretos activos del proyecto |
| stpokegradingprod | CanNotDelete | Proteger imágenes y backups almacenados |

> El bloqueo CanNotDelete impide la eliminación pero permite modificaciones de configuración.
> El bloqueo ReadOnly impide tanto modificación como eliminación; no se aplica aquí porque
> los recursos de producción necesitan actualizaciones de configuración durante el proyecto.

### Cómo crear un bloqueo

```
Portal de Azure -> Grupo de recursos o recurso -> Locks -> + Add
  Nombre del bloqueo: lock-<nombre-recurso>-nodelete
  Tipo: CanNotDelete
  Notes: Bloqueo de gobernabilidad PokéGrading Sprint 1
  Save
```

---

## Managed Identity y acceso a servicios

| Servicio | Managed Identity | Permisos otorgados |
|---|---|---|
| app-pokegrading-stg | System-assigned | Key Vault Secrets User en kv-pokegrading-shared |
| app-pokegrading-stg | System-assigned | Storage Blob Data Contributor en stpokegradingstg |
| app-pokegrading-prod | System-assigned | Key Vault Secrets User en kv-pokegrading-shared |
| app-pokegrading-prod | System-assigned | Storage Blob Data Contributor en stpokegradingprod |

Habilitar Managed Identity en App Service:

```
Portal de Azure -> App Service -> Identity -> System assigned -> Status: On -> Save
```

Luego asignar el rol en Key Vault:

```
Key Vault -> Access control (IAM) -> + Add role assignment
  Rol: Key Vault Secrets User
  Miembro: (seleccionar la Managed Identity del App Service)
  Review + assign
```

---

## Diagnóstico y auditoría

Todos los recursos de producción deben enviar sus logs y métricas a un workspace
central de Log Analytics para auditoría y cumplimiento.

| Recurso | Categorías de log habilitadas | Workspace destino |
|---|---|---|
| app-pokegrading-prod | AppServiceHTTPLogs, AppServiceConsoleLogs, AppServiceAuditLogs | log-pokegrading-prod |
| psql-pokegrading-prod | PostgreSQLLogs, QueryStoreRuntimeStatistics | log-pokegrading-prod |
| kv-pokegrading-shared | AuditEvent (todos los accesos a secretos) | log-pokegrading-prod |
| stpokegradingprod | StorageRead, StorageWrite, StorageDelete | log-pokegrading-prod |

### Retención de logs

| Ambiente | Retención en Log Analytics | Justificación |
|---|---|---|
| Staging | 30 días | Suficiente para depuración durante el sprint |
| Producción | 90 días | Alineado con la política de retención de datos (RNF SP4) |

---

## Checklist de gobernabilidad por sprint

Al inicio de cada sprint el responsable de infraestructura verifica:

- [ ] Los tres grupos de recursos existen y tienen todas las etiquetas obligatorias.
- [ ] Los presupuestos y alertas de Azure Cost Management están configurados segun Presupuesto y Alertas en Azure.
- [ ] Las políticas de Azure están asignadas y no reportan recursos no conformes.
- [ ] Los bloqueos CanNotDelete están activos en los recursos de producción.
- [ ] Las Managed Identities de los App Services tienen acceso a Key Vault y Storage.
- [ ] Los Diagnostic Settings están configurados en todos los recursos de producción.
- [ ] Ningún recurso tiene credenciales hardcodeadas en su configuración.
- [ ] El inventario de etiquetas no muestra recursos sin etiquetar.

---

*Documento generado en mayo 2026 — PokéGrading v1.6 / Sprint 1*
