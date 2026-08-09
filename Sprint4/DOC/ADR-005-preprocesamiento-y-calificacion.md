# ADR-005 — Preprocesamiento de carta y calificación estimada por pHash

**Proyecto:** PokéGrading — Dr. Mundo Solutions
**Sprint:** 4
**Estado:** Propuesto (Fase A — diseño)
**Fecha:** 2026-06-22
**Relacionado:** [diseno-preprocesamiento-calificacion.md](./diseno-preprocesamiento-calificacion.md) · [diagramas-secuencia.md](./diagramas-secuencia.md) · [diagramas-actividad.md](./diagramas-actividad.md) · [ADR-003 (Sprint 2)](../../Sprint2/DOC/ADR-003-busqueda-rapida-de-carta.md) · [busqueda-phash-ocr.md (Sprint 3)](../../Sprint3/DOC/busqueda-phash-ocr.md)

> **Convención (igual que Sprint 2 y 3):** primero se documenta el diseño (Fase A) y luego el código (Fase B) se escribe **siguiendo** estos `.md`. Ninguna decisión de arquitectura se toma en el código sin estar antes en un documento de diseño. Las etiquetas de los diagramas usan los **nombres reales de archivo y clase** que tendrá el código.

---

## 1. Contexto

Sprint 1–3 dejaron el flujo hasta **identificar** la carta (búsqueda rápida por pHash + especializada por OCR) y **persistir el envío** (`SubmitCardForEvaluationUseCase`, `Submission` en estado `PENDING`). Lo que falta para cerrar el flujo de grading interno (US-003/004) son las dos etapas finales del pipeline:

1. **Preprocesar carta** — normalizar la imagen recibida para poder operar sobre datos consistentes y comparables.
2. **Calificar carta** — producir un grado estimado por métricas objetivas, con subgrades por dimensión, banda de incertidumbre, versión de algoritmo inmutable e idempotencia.

Ambas etapas ya aparecen como nodos en el [diagrama de actividad del flujo de grading (Sprint 3 §1)](../../Sprint3/DOC/diagramas-actividad.md): este ADR las desarrolla y las baja a arquitectura.

### 1.1 Historias y criterios de aceptación

**Preprocesar carta** — *Yo como sistema quiero preprocesar automáticamente las imágenes recibidas de la carta para entonces poder operar sobre datos consistentes y comparables en el cálculo posterior del grado.*

- AC-P1: Corrección de perspectiva, recorte al borde de la carta y normalización de color.
- AC-P2: Segmentación en cuatro regiones: `centering`, `corners`, `edges`, `surface`.
- AC-P3: Si el preprocesamiento es exitoso, el flujo avanza a extracción de features.
- AC-P4 (alterno): si no se puede aislar la carta del fondo → se deriva a **calificación manual**.
- AC-P5 (alterno): si la imagen tiene distorsiones imposibles de corregir → se **rechaza** y se solicita **recapturar**.

**Calificar carta** — *Yo como Submitter quiero recibir un grado estimado de mi carta basado en métricas objetivas para entonces saber si vale la pena enviarla a grading profesional.*

- AC-G1: Subgrade por dimensión (`centering`, `corners`, `edges`, `surface`) en escala **1.0–10.0**.
- AC-G2: Selección del **baseline calibrado** según `(set, finish)` cuando hay ground truth suficiente; **fallback al baseline global** registrado en el output.
- AC-G3: Regla de coherencia: el grado final **no excede el subgrade más bajo + 0.5**.
- AC-G4: El resultado incluye la **banda de incertidumbre** asociada.
- AC-G5: La evaluación se persiste con el **identificador exacto de versión del algoritmo** y queda **inmutable**: liberar una versión nueva no la modifica.
- AC-G6: La operación es **idempotente**: reintentar el envío con la misma carta y sesión no genera evaluaciones duplicadas.
- AC-G7 (alterno): si algún subgrade no puede calcularse con insumos suficientes → se deriva a **calificación manual**.
- AC-G8 (alterno): si el resultado contradice umbrales mínimos de coherencia interna → se deriva a **revisión humana**.

---

## 2. Decisión

Se implementan dos casos de uso nuevos en la capa de aplicación, cada uno orquestando puertos (interfaces) cuya implementación concreta vive en infraestructura, siguiendo exactamente el patrón **Ports & Adapters** ya usado por `IImageQualityService`/`PillowImageQualityService` e `IImageHashService`/`PHashImageHashService`.

| Decisión | Resumen |
|---|---|
| **D1 — Dos use cases separados** | `PreprocessCardUseCase` y `GradeCardUseCase`. Preprocesar e identificar/calificar son actividades distintas con resultados propios (alineado con corrección C4 del diagrama de actividad Sprint 3). |
| **D2 — Preprocesamiento detrás de un puerto** | `ICardPreprocessingService` (perspectiva + recorte + normalización de color + segmentación en 4 regiones). Implementación de desarrollo con Pillow/NumPy; producción puede migrar a OpenCV sin tocar el puerto. |
| **D3 — Calificación por dimensión detrás de un puerto** | `IRegionGradingService` calcula el subgrade de cada región. La implementación de Sprint 4 (`StructuralRegionGradingService`) **combina dos señales**: (a) la **distancia pHash** región-contra-región (parecido estructural, reutiliza `IImageHashService`) y (b) una **diferencia estructural de píxeles** que detecta daño local (rayones/marcas) que el pHash ignora por diseño. El puerto recibe además los bytes de los recortes para poder medir el daño. |
| **D3-bis — Referencia segmentada región-contra-región** | El catálogo guarda un único pHash por imagen. Para comparar "esquinas contra esquinas" (no contra la imagen completa), `GradeCardUseCase` **preprocesa y segmenta la imagen de referencia** con el mismo `ICardPreprocessingService` y recalcula su pHash por región con `IImageHashService`. Esto evita la dispersión artificial que producía comparar cada recorte contra el pHash global. |
| **D4 — Baselines como dato persistido y versionado** | `IGradingBaselineRepository` selecciona el baseline calibrado por `(set, finish)`; si no hay ground truth suficiente, cae al **baseline global**. El baseline efectivamente usado se registra en el output (AC-G2). |
| **D5 — Evaluación inmutable + versión de algoritmo** | La evaluación se persiste **append-only** con `algorithm_version`. Nunca se hace `UPDATE` de una evaluación liberada; una versión nueva crea filas nuevas (AC-G5). |
| **D6 — Idempotencia por `(submission_id, algorithm_version)`** | Reintentar con la misma carta y sesión devuelve la evaluación ya almacenada, sin recalcular ni duplicar (AC-G6). Reusa el patrón de idempotencia del API B2B (Sprint 3). |
| **D7 — Derivaciones explícitas a humano** | Estados terminales `MANUAL_REVIEW` (calificación manual) y `NEEDS_RECAPTURE` (recapturar) en `SubmissionStatus`, más `PREPROCESSED` como estado intermedio. Cada rama alterna mapea a uno de estos estados. |

---

## 3. Por qué pHash para la calificación

El enunciado del sprint indica usar pHash porque **mide qué tan lejos está la imagen de la referencia**, lo que da una base de 0 a 10 para calificar. La decisión se apoya en que el pHash ya está implementado y probado (Sprint 3):

- `IImageHashService.compute_phash(bytes) -> str` (hex de 64 bits) y `hamming_distance(a, b) -> int`.
- La distancia de Hamming `d ∈ [0, 64]` ya se usa como señal de cercanía en `QuickSearchByPHashUseCase` (confianza `1 - d/64`).

**Modelo de subgrade (desarrollo).** Para cada región se calculan dos componentes y se combinan con un peso configurable `DEFAULT_PHASH_WEIGHT` (0.35 por defecto):

1. **Parecido estructural (pHash).** Se compara el pHash del recorte del envío contra el pHash del **mismo recorte segmentado** de la imagen de referencia. La distancia de Hamming se mapea a 1.0–10.0 con el baseline (§4 del diseño): distancia 0 → 10.0, distancia alta → 1.0.
2. **Daño local (diferencia de píxeles).** Se mide la fracción de píxeles del recorte cuyo color difiere de la referencia por encima de `DAMAGE_COLOR_THRESHOLD`. Esa fracción se mapea a un score de daño (0% alterado → 10.0; `DAMAGE_FULL_FRACTION` o más → 1.0).

`subgrade = w·score_pHash + (1−w)·score_daño`.

> **Por qué el componente de daño (hallazgo de Fase B):** el pHash es **robusto a marcas locales por diseño** (reduce la imagen a su estructura de baja frecuencia). En pruebas, una carta idéntica con rayones rojos sobre toda la superficie daba distancia pHash ≈ 4/64 → nota ~9.4, lo que contradice el objetivo de "grado por estado". El pHash sirve para **identificar** la carta, no para **medir su estado**; por eso la calificación añade la señal de daño. La etapa de identificación (búsqueda pHash, US-004) **no** usa este puerto y queda intacta.

> **Límite consciente (igual que Sprint 2/3):** sigue siendo un **grado estimado**, no una medición física certificada. La diferencia de píxeles funciona mejor cuando el envío está bien alineado con la referencia; con fotos de distinto ángulo/luz convendría alinear/usar SSIM. En producción cada `IRegionGradingService` se reemplaza por un modelo de visión por dimensión sin cambiar el puerto ni el use case. Coherente con el descargo legal del dominio (`DisclosureNotAcceptedError`).

---

## 4. Arquitectura — capas afectadas

```
domain/
  value_objects/grading_region.py      → GradingRegion (CENTERING, CORNERS, EDGES, SURFACE)
  value_objects/submission_status.py   → + PREPROCESSED, MANUAL_REVIEW, NEEDS_RECAPTURE
  value_objects/preprocessing_status.py→ PreprocessingStatus (OK, MANUAL, RECAPTURE)
  entities/preprocessed_card.py        → PreprocessedCard (imagen normalizada + 4 RegionImage)
  entities/card_evaluation.py          → CardEvaluation (inmutable) + Subgrade (VO)
  entities/grading_baseline.py         → GradingBaseline (por set/finish o global)
  repositories/evaluation_repository.py→ IEvaluationRepository
  repositories/grading_baseline_repository.py → IGradingBaselineRepository
  exceptions.py                        → + excepciones de preprocesamiento/calificación

application/
  ports/card_preprocessing_service.py  → ICardPreprocessingService
  ports/region_grading_service.py      → IRegionGradingService (recibe pHash + bytes de recortes)
  use_cases/preprocess_card.py         → PreprocessCardUseCase
  use_cases/grade_card.py              → GradeCardUseCase
        (deps: submission_repo, region_repo, evaluation_repo, baseline_repo,
         card_repo, image_repo, preprocessing_svc, hash_svc, grading_svc)

infrastructure/
  preprocessing/pillow_card_preprocessing_service.py → PillowCardPreprocessingService (+ Stub)
  grading/phash_region_grading_service.py            → StructuralRegionGradingService (pHash + daño),
                                                       PHashRegionGradingService (solo pHash), Stub
  persistence/models.py                → CardEvaluationORM, SubgradeORM, GradingBaselineORM
  persistence/repositories/evaluation/evaluation_repository.py
  persistence/repositories/grading/grading_baseline_repository.py
  (Alembic migration + seed de baseline global)

api/v3/
  schemas/grading.py                   → schemas de preprocess/grade
  routers/submissions.py               → + POST /{id}/preprocess y POST /{id}/grade
```

El flujo nunca cruza con el API B2B (Sprint 3): el B2B es solo lectura del catálogo y jamás entra a este pipeline (ver [diagramas-actividad.md §3 de Sprint 3](../../Sprint3/DOC/diagramas-actividad.md)).

---

## 5. Reglas de negocio clave

### 5.1 Regla de coherencia del grado final (AC-G3)

```
final_grade ≤ min(subgrades) + 0.5
```

Se calcula un grado candidato (media ponderada de los 4 subgrades; los pesos `PESOS` son **iguales 0.25** por defecto, configurables) y luego se **acota** a `min_subgrade + 0.5`. El peor eslabón domina: una carta con una esquina dañada no puede recibir un grado alto aunque las otras dimensiones sean perfectas. El grado se redondea a un decimal en `[1.0, 10.0]`.

### 5.2 Banda de incertidumbre (AC-G4)

La incertidumbre se deriva de: (a) la dispersión de las distancias pHash entre regiones, (b) si se usó baseline calibrado o global (el global es menos preciso → banda más ancha), y (c) la calidad de imagen (IQS) ya disponible en el `Submission`. Se reporta como `± delta` alrededor del grado final (p. ej. `8.0 ± 0.7`).

### 5.3 Inmutabilidad y versión (AC-G5)

- `algorithm_version` es una constante de código (p. ej. `GRADING_ALGORITHM_VERSION = "grading-v1.0.0"`).
- La tabla de evaluaciones es **append-only**: el repositorio nunca actualiza una fila existente; solo inserta.
- Liberar `grading-v1.1.0` no modifica evaluaciones previas; produce filas nuevas con la versión nueva.

### 5.4 Idempotencia (AC-G6)

- **Sesión = el `Submission`**. "Misma carta y sesión" se materializa como el mismo `submission_id`.
- Clave única `(submission_id, algorithm_version)` en la tabla de evaluaciones.
- `GradeCardUseCase` primero busca una evaluación existente con esa clave; si existe, la devuelve tal cual (sin recalcular). Esto hace el reintento seguro y barato (mismo patrón que la idempotencia B2B de Sprint 3).

### 5.5 Coherencia interna mínima (AC-G8)

Si tras calcular los subgrades el resultado es internamente incoherente (p. ej. dispersión extrema entre regiones por encima de un umbral, o un subgrade que el baseline marca como atípico para ese `(set, finish)`), la carta **no** se autocalifica: se persiste el envío como `MANUAL_REVIEW` con la razón, para revisión humana.

---

## 6. Mapa de estados de `Submission`

| Estado | Significado | Cómo se llega |
|---|---|---|
| `PENDING` | Envío creado, imágenes validadas (US-003) | `SubmitCardForEvaluationUseCase` |
| `PROCESSING` | Preprocesamiento/calificación en curso | inicio de `PreprocessCardUseCase` |
| `PREPROCESSED` | Imagen normalizada y segmentada; lista para calificar | `PreprocessCardUseCase` éxito (AC-P3) |
| `GRADED` | Evaluación estimada generada | `GradeCardUseCase` éxito |
| `MANUAL_REVIEW` | Derivada a calificación/revisión manual | AC-P4, AC-G7, AC-G8 |
| `NEEDS_RECAPTURE` | Rechazada; se pide recapturar | AC-P5 |
| `REJECTED` | Rechazo de validación previa (US-003) | ya existente |

---

## 7. Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| Calcular el grado dentro de `SubmitCardForEvaluationUseCase` | Mezcla responsabilidades (validación de carga vs. cálculo de grado) y rompe el patrón de un use case por actividad. |
| Modelo de visión por dimensión ya en Sprint 4 | Fuera de alcance/tiempo; el puerto `IRegionGradingService` permite introducirlo después sin reescribir el use case. |
| Evaluaciones mutables (UPDATE al regradar) | Viola AC-G5 (inmutabilidad) y elimina trazabilidad histórica por versión. |
| Idempotencia por `(user_id, card_id)` | Una misma carta puede reenviarse legítimamente en sesiones distintas; la sesión correcta es el `Submission`. |
| pHash global de la carta completa para el grado | Pierde el detalle por dimensión exigido por AC-G1; se segmenta y se hashea por región. |

---

## 8. Consecuencias

**Positivas:** cierra el pipeline de grading interno; reusa pHash ya probado; mantiene Clean Architecture y testabilidad (puertos mockeables); evaluaciones auditables e inmutables por versión.

**Negativas / deuda asumida:** el grado es una **estimación** basada en similitud visual, no una medición física (se reemplaza por modelos de visión vía los puertos); el baseline global inicial se siembra a mano hasta acumular ground truth por `(set, finish)`.

---

## 9. Trazabilidad documento → código (Fase B)

| Decisión / AC | Documento de detalle | Archivo de código |
|---|---|---|
| D1, AC-P* | [diseno §2](./diseno-preprocesamiento-calificacion.md) | `application/use_cases/preprocess_card.py` |
| D1, AC-G* | [diseno §3](./diseno-preprocesamiento-calificacion.md) | `application/use_cases/grade_card.py` |
| D2 | [diseno §2.1](./diseno-preprocesamiento-calificacion.md) | `application/ports/card_preprocessing_service.py` + `infrastructure/preprocessing/pillow_card_preprocessing_service.py` |
| D3, §3 | [diseno §3.2](./diseno-preprocesamiento-calificacion.md) | `application/ports/region_grading_service.py` + `infrastructure/grading/phash_region_grading_service.py` |
| D4, AC-G2 | [diseno §3.3](./diseno-preprocesamiento-calificacion.md) | `domain/entities/grading_baseline.py` + `.../grading/grading_baseline_repository.py` |
| D5, AC-G5 | [diseno §3.5](./diseno-preprocesamiento-calificacion.md) | `domain/entities/card_evaluation.py` + `.../evaluation/evaluation_repository.py` |
| D6, AC-G6 | [diseno §3.6](./diseno-preprocesamiento-calificacion.md) | `application/use_cases/grade_card.py` (idempotencia) |
| D7 | [ADR §6](#6-mapa-de-estados-de-submission) | `domain/value_objects/submission_status.py` |

---

## Referencias

- [Diseño detallado — preprocesamiento y calificación](./diseno-preprocesamiento-calificacion.md)
- [Diagramas de secuencia (Sprint 4)](./diagramas-secuencia.md)
- [Diagramas de actividad (Sprint 4)](./diagramas-actividad.md)
- [ADR-003 — Búsqueda rápida (Sprint 2)](../../Sprint2/DOC/ADR-003-busqueda-rapida-de-carta.md)
- [busqueda-phash-ocr.md (Sprint 3)](../../Sprint3/DOC/busqueda-phash-ocr.md)
- [diagramas-actividad.md (Sprint 3) — flujo de grading](../../Sprint3/DOC/diagramas-actividad.md)
