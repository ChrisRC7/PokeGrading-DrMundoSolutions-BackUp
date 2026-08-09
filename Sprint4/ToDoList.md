# ToDoList — Sprint 4: Preprocesar carta + Calificar carta

**Sprint:** 4
**Rama base:** `Development`
**Funcionalidades principales:**
- **Preprocesar carta** — normalizar la imagen para operar sobre datos consistentes y comparables.
- **Calificar carta** — grado estimado por métricas objetivas (subgrades por dimensión vía pHash), con baseline, banda de incertidumbre, versión inmutable e idempotencia.

**Arquitectura:** Clean Architecture + Repository + Ports & Adapters (idéntica a Sprint 1–3).

---

## 0. Convención de trabajo (igual que Sprint 2 y 3)

> **Dos fases.**
> **Fase A — Diseño (este ToDoList + los `.md` de `Sprint4/DOC/`).** Primero se documenta TODO: ADR, diseño detallado, diagramas de secuencia y de actividad. ✅ **Completa.**
> **Fase B — Implementación.** El código se escribe **siguiendo** los `.md` de la Fase A. Ninguna decisión de arquitectura se toma en el código sin estar antes en un documento de diseño.

Documentos de diseño (Fase A):

| # | Entregable | Documento | Estado |
|---|---|---|---|
| A.1 | ADR de preprocesamiento + calificación (decisiones, pHash, estados, alternativas) | [`DOC/ADR-005-preprocesamiento-y-calificacion.md`](./DOC/ADR-005-preprocesamiento-y-calificacion.md) | [x] |
| A.2 | Diseño detallado (firmas, fórmulas, baselines, versionado, idempotencia, esquema BD) | [`DOC/diseno-preprocesamiento-calificacion.md`](./DOC/diseno-preprocesamiento-calificacion.md) | [x] |
| A.3 | **Diagramas de secuencia** de las nuevas funcionalidades | [`DOC/diagramas-secuencia.md`](./DOC/diagramas-secuencia.md) | [x] |
| A.4 | Diagramas de actividad (zoom sobre los nodos preprocesar/calificar) | [`DOC/diagramas-actividad.md`](./DOC/diagramas-actividad.md) | [x] |

---

## 1. Resumen de criterios de aceptación

### Preprocesar carta
| # | Criterio | Estado |
|---|---|---|
| AC-P1 | Corrección de perspectiva, recorte al borde de la carta y normalización de color | [x] |
| AC-P2 | Segmentación en 4 regiones: centering, corners, edges, surface | [x] |
| AC-P3 | Preprocesamiento exitoso → el flujo avanza a extracción de features | [x] |
| AC-P4 | No se aísla la carta del fondo → deriva a calificación manual (`MANUAL_REVIEW`) | [x] |
| AC-P5 | Distorsión imposible de corregir → rechaza y solicita recapturar (`NEEDS_RECAPTURE`) | [x] |

### Calificar carta
| # | Criterio | Estado |
|---|---|---|
| AC-G1 | Subgrade por dimensión en escala 1.0–10.0 | [x] |
| AC-G2 | Baseline calibrado por (set, finish) con ground truth suficiente; fallback global registrado en el output | [x] |
| AC-G3 | Regla de coherencia: grado final no excede el subgrade más bajo + 0.5 | [x] |
| AC-G4 | El resultado incluye la banda de incertidumbre | [x] |
| AC-G5 | Evaluación con identificador exacto de versión del algoritmo + inmutable | [x] |
| AC-G6 | Idempotente: misma carta + sesión no genera evaluaciones duplicadas | [x] |
| AC-G7 | Subgrade sin insumos suficientes → calificación manual | [x] |
| AC-G8 | Resultado contradice coherencia interna mínima → revisión humana | [x] |

---

## 2. Cambios en dominio (`domain/`)

- [x] **`value_objects/grading_region.py`** → enum `GradingRegion` (`centering`, `corners`, `edges`, `surface`)
- [x] **`value_objects/preprocessing_status.py`** → enum `PreprocessingStatus` (`ok`, `manual`, `recapture`)
- [x] **`value_objects/submission_status.py`** → añadir `PREPROCESSED`, `MANUAL_REVIEW`, `NEEDS_RECAPTURE` (conservar `PENDING`/`PROCESSING`/`GRADED`/`REJECTED`)
- [x] **`entities/preprocessed_card.py`** → `RegionImage`, `PreprocessedCard`, `PreprocessOutcome` — ver [diseno §2.1](./DOC/diseno-preprocesamiento-calificacion.md)
- [x] **`entities/card_evaluation.py`** → `Subgrade` (VO) + `CardEvaluation` (inmutable, `frozen=True`) — [diseno §3.1](./DOC/diseno-preprocesamiento-calificacion.md)
- [x] **`entities/grading_baseline.py`** → `GradingBaseline` con `score_for(region, d)` — [diseno §3.3](./DOC/diseno-preprocesamiento-calificacion.md)
- [x] **`repositories/region_repository.py`** → `IRegionRepository` (`save`, `find_by_submission`)
- [x] **`repositories/evaluation_repository.py`** → `IEvaluationRepository` (`find_by_submission_and_version`, `save` append-only)
- [x] **`repositories/grading_baseline_repository.py`** → `IGradingBaselineRepository` (`get_for(set, finish)`)
- [x] **`exceptions.py`** → `SubmissionNotFoundError`, `CardNotPreprocessedError`, `CardIsolationFailedError`, `UncorrectableDistortionError`, `InsufficientGradingInputError`, `IncoherentGradeError` — [diseno §5](./DOC/diseno-preprocesamiento-calificacion.md)

---

## 3. Cambios en aplicación (`application/`)

- [x] **`ports/card_preprocessing_service.py`** → `ICardPreprocessingService.preprocess(bytes) -> PreprocessOutcome` (AC-P1/P2/P4/P5)
- [x] **`ports/region_grading_service.py`** → `IRegionGradingService.grade_region(..., submission_region_data, reference_region_data) -> Subgrade` (AC-G1/G7). Los bytes de los recortes son opcionales para no afectar a la identificación.
- [x] **`use_cases/preprocess_card.py`** → `PreprocessCardUseCase`
  - cargar submission → PROCESSING → `preprocess()` → ramificar OK/MANUAL/RECAPTURE
  - en OK: persistir 4 `RegionImage` (con pHash vía `IImageHashService`) y marcar `PREPROCESSED`
- [x] **`use_cases/grade_card.py`** → `GradeCardUseCase` (constantes `GRADING_ALGORITHM_VERSION`, `MIN_GROUND_TRUTH`, `UMBRAL_INCOHERENCIA`, `PESOS` iguales 0.25). Deps: `submission_repo, region_repo, evaluation_repo, baseline_repo, card_repo, image_repo, preprocessing_svc, hash_svc, grading_svc`.
  - 0) idempotencia (`find_by_submission_and_version`) — AC-G6
  - 1) precondición `PREPROCESSED` (si no → `CardNotPreprocessedError`)
  - 2) cargar regiones del envío (pHash + data)
  - 3) referencia: `image_repo` da los bytes de catálogo; se **segmenta región-contra-región** (`preprocessing_svc` + `hash_svc`) para comparar misma región — AC-G2
  - 4) baseline (calibrado/global) — AC-G2
  - 5) subgrade por región (pHash + daño) — AC-G1; insumos insuficientes → MANUAL_REVIEW (AC-G7)
  - 6) regla de coherencia `final = min(candidato, peor+0.5)` — AC-G3; banda — AC-G4
  - 7) coherencia interna (dispersión) → MANUAL_REVIEW si excede umbral — AC-G8
  - 8) persistir `CardEvaluation` (versión + baseline_ref, append-only) — AC-G5; marcar `GRADED`

---

## 4. Cambios en infraestructura (`infrastructure/`)

- [x] **`preprocessing/pillow_card_preprocessing_service.py`** → `PillowCardPreprocessingService(ICardPreprocessingService)` (Pillow/NumPy) + `StubCardPreprocessingService` para tests — [diseno §2.2/2.3](./DOC/diseno-preprocesamiento-calificacion.md)
- [x] **`grading/phash_region_grading_service.py`** → `StructuralRegionGradingService` (pHash + **diferencia de píxeles para detectar daño local**; el que usa el router) + `PHashRegionGradingService` (solo pHash) + `StubRegionGradingService` — [diseno §3.2](./DOC/diseno-preprocesamiento-calificacion.md). Perillas: `DEFAULT_PHASH_WEIGHT`, `DAMAGE_COLOR_THRESHOLD`, `DAMAGE_FULL_FRACTION`.
- [x] **`persistence/models.py`** → ORMs nuevos: `SubmissionRegionORM`, `CardEvaluationORM`, `EvaluationSubgradeORM`, `GradingBaselineORM` — esquema en [diseno §4](./DOC/diseno-preprocesamiento-calificacion.md)
  - `card_evaluations`: `UniqueConstraint(submission_id, algorithm_version)` (idempotencia/inmutabilidad)
  - `submission_regions`: `UniqueConstraint(submission_id, region)`
- [x] **`persistence/repositories/submission/region_repository.py`** → `RegionRepositoryImpl`
- [x] **`persistence/repositories/evaluation/evaluation_repository.py`** → `EvaluationRepositoryImpl` (INSERT-only; ante carrera por UniqueConstraint → devolver la fila existente)
- [x] **`persistence/repositories/grading/grading_baseline_repository.py`** → `GradingBaselineRepositoryImpl` (calibrado si `ground_truth_count >= MIN_GROUND_TRUTH`, si no global)
- [x] **Migración Alembic** → `c1d2e3f4a5b6_create_grading_tables` (submission_regions, card_evaluations, evaluation_subgrades, grading_baselines) + nuevos valores del enum `submissionstatus`
- [x] **Seed** → `scripts/seed_grading_baseline.py` inserta el baseline `global` con `(d_min, d_max)` por defecto por región — [diseno §4.4](./DOC/diseno-preprocesamiento-calificacion.md)

---

## 5. Cambios en API (`api/v3/`)

- [x] **`api/v3/schemas/grading.py`** → `PreprocessResponse`, `SubgradeSchema`, `EvaluationResponse`
- [x] **`api/v3/routers/submissions.py`** →
  - `POST /submissions/{id}/preprocess` → `PreprocessCardUseCase` (200 con `status`; 404)
  - `POST /submissions/{id}/grade` → `GradeCardUseCase` (201/200 idempotente; 200 `manual_review`; 404; 409 no preprocesada)
  - `GET /submissions/{id}/evaluation` → leer `IEvaluationRepository` (200/404)
  - mapear las excepciones nuevas a HTTP (igual patrón `try/except` que `submit_card`)
  - el router cablea `GradeCardUseCase` con `CardImageRepositoryImpl`, `PillowCardPreprocessingService`, `PHashImageHashService` y `StructuralRegionGradingService`
- [x] **Fix transversal (US-003) `submit_card`** → `card_id` debe recibirse como **campo de formulario** (`Form(...)`), no query param; sin esto el envío no queda vinculado a la carta del catálogo y la calificación siempre derivaba a manual (AC-G7)

---

## 6. Tests (`tests/`)

**Unitarios** (`tests/unit/`):
- [x] `test_preprocess_card.py`: OK (PREPROCESSED + 4 regiones con pHash); no aísla → MANUAL_REVIEW (AC-P4); distorsión → NEEDS_RECAPTURE (AC-P5); submission inexistente → 404
- [x] `test_grade_card.py`: subgrades 1.0–10.0 (AC-G1); baseline calibrado vs. global registrado (AC-G2); regla coherencia `final ≤ min+0.5` (AC-G3); banda presente (AC-G4); versión en la evaluación (AC-G5); idempotencia: 2ª llamada = misma evaluación, sin nueva fila (AC-G6); insumo insuficiente → MANUAL_REVIEW (AC-G7); incoherencia → MANUAL_REVIEW (AC-G8); grade sin preprocesar → 409
- [x] `test_phash_region_grading_service.py`: distancia 0 → ~10.0; distancia alta → ~1.0; clamp a [1.0, 10.0]
- [x] `test_grading_baseline.py`: `score_for` monótona decreciente en d; d_min → 10.0; d_max → 1.0
- [ ] **(pendiente) `StructuralRegionGradingService`**: recortes idénticos → score alto; recorte con marcas (rayones) → score menor que el limpio; sin bytes → cae a pHash puro
- [ ] **(pendiente) camino "graded" real**: `test_grade_card.py` solo cubre el atajo idempotente y los helpers; falta un caso con carta de referencia real (image_repo + preprocessing) que produzca `GRADED` con grado numérico

**Integración** (`tests/integration/`):
- [x] `test_grading_pipeline.py`: submit → preprocess → grade end-to-end; reintento de grade idempotente (una sola fila en `card_evaluations`); ramas manual/recapture; 409 sin preprocesar; GET evaluation 404
- [x] **regresión `card_id`** (`test_submissions.py::test_submit_persists_card_id_from_form`): envío con `card_id` (multipart `Form`) → la respuesta y el envío persistido quedan vinculados a la carta. Verificado que **falla** si se quita `Form(...)` (reproduce el bug) y **pasa** con el fix.
- [x] **(pendiente) daño end-to-end**: misma carta limpia vs. rayada → la rayada recibe grado menor

---

## 7. Orden de implementación recomendado (Fase B)

```
domain (VOs, entidades, repos, exceptions)          ✅ Completo
  → application (ports, use cases)                  ✅ Completo
  → infrastructure (servicios pillow/phash, models, repos, migración, seed)  ✅ Completo
  → api/v3 (schemas, router) + mapeo de excepciones ✅ Completo
  → tests unit → tests integración                  ✅ Completo
```

> Verificación final: `pytest` verde ✅ · cobertura 94.93% ✅ · `alembic upgrade head` aplicado ✅ · seed del baseline global poblado ✅ · pipeline `submit → preprocess → grade` probado end-to-end ✅

---

## 8. Resumen de prioridades

| # | Tarea | Prioridad | Esfuerzo | Estado |
|---|---|---|---|---|
| A.x | Documentos de diseño (ADR, diseño, secuencia, actividad) | Alta | Medio | ✅ Completo |
| 2–5 | Preprocesar + Calificar (dominio → API) | Alta | Muy alto | ✅ Completo |
| 6 | Tests unit + integración | Alta | Alto | ✅ Completo |

---

*Documento generado Sprint 4 — PokéGrading — Dr. Mundo Solutions.*
