# Proceso de Trabajo del Equipo — PokéGrading

---

## Stack Tecnológico

### Backend

| Tecnología | Rol | Justificación |
|---|---|---|
| Python 3.12+ | Lenguaje principal del backend y procesamiento de imágenes | Ecosistema maduro para visión por computador (OpenCV, Pillow) y ciencia de datos; compatibilidad nativa con las bibliotecas de procesamiento de imágenes requeridas por el caso de negocio. |
| FastAPI | Framework REST API — async nativo, documentación automática (OpenAPI) | Soporte async necesario para el flujo de evaluación multi-etapa; generación automática de OpenAPI alineada con el RNF S8 de documentación viva. |
| OpenCV | Procesamiento clásico de imágenes — detección de bordes, ROI, centering | Biblioteca de referencia para las operaciones clásicas exigidas por el caso de negocio: edge detection, extracción de contornos y cálculo de centering ratio (RNF SP3). |
| Pillow | Manipulación de imágenes — preprocesamiento, normalización de color | Complementa OpenCV para las etapas de corrección de perspectiva, normalización de color y recorte al borde de la carta (Etapa 3 del flujo de evaluación). |

### Base de Datos

| Tecnología | Rol | Justificación |
|---|---|---|
| PostgreSQL | Almacenamiento de evaluaciones, catálogo y usuarios en todos los ambientes | Motor relacional con soporte nativo para JSONB (outputs intermedios de subgrades), transacciones ACID requeridas por el RNF R7 y disponible como servicio gestionado en Azure (Azure Database for PostgreSQL). |
| SQLAlchemy | ORM — abstrae el motor y facilita migraciones | Desacopla el modelo de dominio del motor de base de datos; permite implementar el patrón Repository sin SQL ad-hoc disperso en la capa de aplicación. |
| Alembic | Gestión de migraciones de esquema de base de datos | Herramienta estándar del ecosistema SQLAlchemy; garantiza evolución controlada del esquema y trazabilidad de cambios estructurales (RNF R4 — inmutabilidad de evaluaciones históricas). |

### Infraestructura y DevOps

| Tecnología | Rol | Justificación |
|---|---|---|
| Azure | Plataforma cloud obligatoria por restricción del proyecto | Requerido por restricción técnica del proyecto; provee los servicios gestionados necesarios dentro del presupuesto de $800/mes (RNF S11). |
| Azure Blob Storage | Almacenamiento de imágenes subidas (frente y reverso) con retención 90 días | Almacenamiento de objetos de bajo costo para imágenes grandes; retención configurable alineada con la política de privacidad de 90 días (RNF SP4) y RPO ≤ 24 h (RNF R9). |
| Azure DevOps | Gestión del proyecto — backlog, sprints, CI/CD | Requerido por restricción del proyecto; centraliza backlog, pipelines de CI y wikis en una sola plataforma. |
| GitHub | Control de versiones centralizado (Git como base) | Requerido por restricción del proyecto; facilita revisión de PRs y bloqueo automático de secretos en el pipeline (RNF S9). |

### Testing y Calidad

| Tecnología | Rol | Justificación |
|---|---|---|
| pytest | Suite de tests unitarios e integración — cobertura >= 75% en capa de dominio | Estándar de facto en el ecosistema Python; soporta fixtures reutilizables para el dataset de calibración y pruebas parametrizadas sobre las heurísticas de scoring (RNF S4, S5). |
| pre-commit + detect-secrets | Bloqueo de secretos en commits (RNF S9, SP8) | Automatiza el rechazo de credenciales en el repositorio antes de que lleguen al servidor remoto; cumple con los RNF de seguridad sin depender de revisión manual. |

---

## Patrones de Diseño

Los siguientes patrones estructuran la solución y son de cumplimiento obligatorio en la implementación.

| Patrón | Capa | Aplicación en PokéGrading |
|---|---|---|
| **Repository** | Persistencia | Abstrae el acceso a PostgreSQL para `Evaluation`, `Card` y `User`; el dominio nunca importa SQLAlchemy directamente. |
| **Strategy** | Dominio — Scoring | Cada versión del algoritmo de grading es una estrategia intercambiable (`ScoringStrategyV1`, `ScoringStrategyV2`…). Permite cumplir el RNF R4 (inmutabilidad histórica) y S10 (feature flags). |
| **Pipeline / Chain of Responsibility** | Dominio — Flujo de evaluación | Cada etapa del flujo (identificación → validación de calidad → preprocesamiento → extracción de features → scoring → consulta precio → recomendación) es un paso encadenado; un fallo en cualquier etapa detiene el avance con estado trazable. |
| **Factory Method** | Dominio — Identificación | `CardIdentifierFactory` construye el identificador correcto (búsqueda rápida o especializada) según la confianza obtenida en la etapa anterior (RNF P9). |
| **Circuit Breaker** | Integración externa | Envuelve la llamada a la API de PokéMarket; al tercer fallo consecutivo abre el circuito y devuelve la evaluación en modo degradado (sin estimación de valor), cumpliendo RNF OE-4 y SP5. |
| **Facade** | API — Capa de aplicación | `EvaluationService` expone una interfaz simple al controlador FastAPI, ocultando la complejidad del pipeline multi-etapa y los repositorios internos. |
| **Observer / Event** | Infraestructura | Eventos de dominio (`EvaluationCompleted`, `EvaluationFailed`) notifican a consumidores (logger estructurado, cola de revisión humana) sin acoplar el dominio a la infraestructura. |

---

## Modelo de Dominio

Entidades y value objects centrales del sistema, derivados del caso de negocio v1.6.

### Entidades principales

| Entidad | Descripción | Invariante clave |
|---|---|---|
| `Evaluation` | Resultado persistido de una sesión de pre-grading. Contiene inputs, outputs intermedios (subgrades), output final y metadatos de trazabilidad. | Una vez creada, sus campos de resultado son inmutables. Una re-evaluación genera una nueva `Evaluation` vinculada, nunca modifica la original (RNF R4, R5). |
| `Card` | Entrada del catálogo de referencia. Identidad: `(set, número, edición, idioma, acabado)` — el `CardIdentityTuple` del caso de negocio. | No puede eliminarse si tiene evaluaciones asociadas (RNF R11). Altas y modificaciones requieren validación dual. |
| `User` | Cuenta registrada con rol (`Submitter`, `Reviewer`, `Admin`, `B2BServiceAccount`). | El rol determina el scope de acceso; un `Submitter` solo accede a sus propias evaluaciones (RNF SP1). |
| `AlgorithmVersion` | Versión versionada del algoritmo de scoring con sus parámetros, pesos y métricas de calibración. | Cada `Evaluation` referencia exactamente una versión; la versión no puede modificarse después de liberar evaluaciones bajo ella (RNF OE-2). |
| `HumanReviewTask` | Tarea generada cuando el `confidence_score` cae por debajo del umbral configurado. | SLA p95 ≤ 24 h; se prioriza por antigüedad y grado estimado (RNF S13). |
| `ManualValuationTask` | Tarea generada cuando la API de PokéMarket no puede resolver el valor de mercado. | SLA p95 ≤ 48 h; se persiste con `value_source = "manual"` (Etapa 7 del flujo). |

### Value Objects

| Value Object | Descripción |
|---|---|
| `CardIdentityTuple` | `(set, número, edición, idioma, acabado)` — llave de identidad única de una carta como activo. |
| `Subgrade` | Score numérico 1.0–10.0 para un criterio (`Centering`, `Corners`, `Edges`, `Surface`) con su confianza individual. |
| `GradingResult` | Resultado final: `final_grade`, `overall_confidence`, lista de `Subgrade`, versión del algoritmo, baseline utilizado. |
| `ImageQualityScore` | Métrica calculada sobre la imagen de entrada (0–1) con razón de rechazo si no supera el threshold mínimo. |
| `IdentificationConfidence` | Score 0–1 emitido por cada paso de búsqueda (rápida o especializada) para el candidato top. |
| `ActionableRecommendation` | Resultado del motor de recomendación: acción sugerida, ganancia esperada, distribución de probabilidad por grado PSA. |

### Relaciones clave

```
User (1) ──── (*) Evaluation
Evaluation (*) ──── (1) Card
Evaluation (*) ──── (1) AlgorithmVersion
Evaluation (1) ──── (0..1) HumanReviewTask
Evaluation (1) ──── (0..1) ManualValuationTask
Evaluation agregates ──── GradingResult
GradingResult contains ──── Subgrade[4]
```

---

## Definition of Done (DoD)

Una historia de usuario o tarea se considera **terminada** cuando cumple todos los
criterios de su capa correspondiente.

---

### Capa de Código

- [ ] El código está en GitHub en la rama correspondiente al sprint, aprobado mediante
      Pull Request con al menos una revisión de otro integrante del equipo.
- [ ] No existen credenciales, tokens ni contraseñas en el código ni en el historial
      de commits (verificado por pre-commit / detect-secrets).
- [ ] El código pasa lint sin errores bloqueantes (flake8 o ruff).
- [ ] Toda lógica de dominio (scoring, reglas de recomendación, validaciones) tiene
      tests unitarios con cobertura >= 75% en esa capa.
- [ ] Los tests pasan en CI (Azure DevOps pipeline) antes del merge a main.

---

### Capa de Funcionalidad

- [ ] La historia cumple los criterios de aceptación definidos en Azure DevOps,
      verificados manualmente por un integrante distinto al que la implementó.
- [ ] Si la historia involucra el flujo de evaluación, el resultado queda persistido con:
      identificador único, versión exacta del algoritmo, correlation ID trazable y
      estado de la evaluación.
- [ ] Si la historia modifica el algoritmo de scoring, se ejecutó la suite de regresión
      sobre el dataset de calibración y la degradación no supera 3% respecto a la
      versión activa.
- [ ] Los estados de error y casos límite (imagen rechazada, API de PokéMarket no
      disponible, identificación fallida) tienen respuesta explícita y no dejan la UI
      en blanco.

---

### Capa de Documentación

- [ ] Si la historia representa una decisión de arquitectura mayor, existe un ADR
      documentado antes del merge.
- [ ] Si la historia introduce o modifica una versión del algoritmo, el Algorithm
      Playbook está actualizado con: pesos usados, dataset de validación, métricas
      de calidad, motivo del cambio y autor.
- [ ] Los endpoints nuevos o modificados están reflejados en la documentación del API
      (OpenAPI/Swagger generado por FastAPI).
- [ ] El README sigue siendo suficiente para levantar el ambiente local en <= 20
      minutos (RNF S1).

---

### Capa de Despliegue

- [ ] La funcionalidad corre en el ambiente de staging sin errores bloqueantes.
- [ ] El pipeline de CI en Azure DevOps completa lint -> tests -> build exitosamente.
- [ ] El gasto de infraestructura no supera los límites del sprint: <= $80/mes en
      staging, <= $800/mes en producción (RNF S11).

---

*Documento generado en mayo 2026 — PokéGrading v1.6 / Sprint 1*