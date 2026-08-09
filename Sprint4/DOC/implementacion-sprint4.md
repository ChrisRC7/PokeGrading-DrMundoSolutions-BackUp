# Implementación Sprint 4 — Preprocesar carta y Calificar carta

**Proyecto:** PokéGrading — Dr. Mundo Solutions
**Sprint:** 4
**Rama:** `Development`
**Fecha:** 2026-06-24
**Estado:** ✅ Completo — 189 tests pasan · cobertura 94.93%

---

## Resumen ejecutivo

Se implementó el pipeline completo de preprocesamiento y calificación automática de cartas Pokémon siguiendo Clean Architecture (domain → application → infrastructure → api). La implementación sigue exactamente los contratos definidos en la Fase A de diseño (`diseno-preprocesamiento-calificacion.md`, `ADR-005`).

---

## Criterios de aceptación implementados

### Preprocesar carta
| # | Criterio | Estado |
|---|---|---|
| AC-P1 | Corrección de perspectiva, recorte y normalización de color (Pillow/autocontrast) | ✅ |
| AC-P2 | Segmentación en 4 regiones: centering, corners, edges, surface (proporciones deterministas) | ✅ |
| AC-P3 | Preprocesamiento exitoso → PREPROCESSED + 4 RegionImage con pHash guardadas | ✅ |
| AC-P4 | No se aísla la carta → MANUAL_REVIEW | ✅ |
| AC-P5 | Distorsión incorregible → NEEDS_RECAPTURE | ✅ |

### Calificar carta
| # | Criterio | Estado |
|---|---|---|
| AC-G1 | Subgrade por dimensión en escala 1.0–10.0 (distancia Hamming → pHash → score) | ✅ |
| AC-G2 | Baseline calibrado por (set, finish); fallback global registrado en el output | ✅ |
| AC-G3 | Regla de coherencia: final = min(candidato, peorSubgrade + 0.5) | ✅ |
| AC-G4 | Banda de incertidumbre: base 0.3 + dispersión + calibración + IQS | ✅ |
| AC-G5 | Evaluación inmutable con identificador exacto de versión `grading-v1.0.0` | ✅ |
| AC-G6 | Idempotencia: 2ª llamada con misma versión devuelve evaluación existente | ✅ |
| AC-G7 | Subgrade sin insumos (pHash vacío) → MANUAL_REVIEW | ✅ |
| AC-G8 | Dispersión entre subgrades > 2.5 → MANUAL_REVIEW | ✅ |

---

## Archivos creados / modificados

### Dominio (`domain/`)

| Archivo | Tipo | Contenido |
|---|---|---|
| `value_objects/grading_region.py` | NUEVO | Enum: `centering`, `corners`, `edges`, `surface` |
| `value_objects/preprocessing_status.py` | NUEVO | Enum: `ok`, `manual`, `recapture` |
| `value_objects/submission_status.py` | MODIFICADO | Añadido `PREPROCESSED`, `MANUAL_REVIEW`, `NEEDS_RECAPTURE` |
| `entities/preprocessed_card.py` | NUEVO | `RegionImage`, `PreprocessedCard`, `PreprocessOutcome` |
| `entities/card_evaluation.py` | NUEVO | `Subgrade` (VO) + `CardEvaluation` (frozen, append-only) |
| `entities/grading_baseline.py` | NUEVO | `GradingBaseline` con `score_for(region, d) → float` |
| `repositories/region_repository.py` | NUEVO | `IRegionRepository` (save, find_by_submission) |
| `repositories/evaluation_repository.py` | NUEVO | `IEvaluationRepository` (find_by_submission_and_version, save INSERT-only) |
| `repositories/grading_baseline_repository.py` | NUEVO | `IGradingBaselineRepository` (get_for — nunca devuelve None) |
| `exceptions.py` | MODIFICADO | +6 excepciones: `SubmissionNotFoundError`, `CardNotPreprocessedError`, `CardIsolationFailedError`, `UncorrectableDistortionError`, `InsufficientGradingInputError`, `IncoherentGradeError` |

### Aplicación (`application/`)

| Archivo | Tipo | Contenido |
|---|---|---|
| `ports/card_preprocessing_service.py` | NUEVO | `ICardPreprocessingService.preprocess(bytes) → PreprocessOutcome` |
| `ports/region_grading_service.py` | NUEVO | `IRegionGradingService.grade_region(..., submission_region_data, reference_region_data) → Subgrade` (bytes opcionales para detectar daño) |
| `use_cases/preprocess_card.py` | NUEVO | `PreprocessCardUseCase` — orquesta AC-P1..P5 |
| `use_cases/grade_card.py` | NUEVO | `GradeCardUseCase` — orquesta AC-G1..G8; deps: `submission_repo, region_repo, evaluation_repo, baseline_repo, card_repo, image_repo, preprocessing_svc, hash_svc, grading_svc`; constantes `GRADING_ALGORITHM_VERSION="grading-v1.0.0"`, `UMBRAL_INCOHERENCIA=2.5`, `PESOS` iguales 0.25. Segmenta la imagen de referencia región-contra-región. |

### Infraestructura (`infrastructure/`)

| Archivo | Tipo | Contenido |
|---|---|---|
| `preprocessing/pillow_card_preprocessing_service.py` | NUEVO | `PillowCardPreprocessingService` (Pillow) + `StubCardPreprocessingService` (tests) |
| `grading/phash_region_grading_service.py` | NUEVO | `StructuralRegionGradingService` (pHash + diferencia de píxeles → detecta daño; **el que usa el router**) + `PHashRegionGradingService` (solo pHash) + `StubRegionGradingService`. Perillas: `DEFAULT_PHASH_WEIGHT`, `DAMAGE_COLOR_THRESHOLD`, `DAMAGE_FULL_FRACTION` |
| `persistence/models.py` | MODIFICADO | +4 ORMs: `SubmissionRegionORM`, `CardEvaluationORM`, `EvaluationSubgradeORM`, `GradingBaselineORM` |
| `persistence/repositories/submission/region_repository.py` | NUEVO | `RegionRepositoryImpl` |
| `persistence/repositories/evaluation/evaluation_repository.py` | NUEVO | `EvaluationRepositoryImpl` (INSERT-only + idempotencia ante IntegrityError) |
| `persistence/repositories/grading/grading_baseline_repository.py` | NUEVO | `GradingBaselineRepositoryImpl` (calibrado si ≥ 30 ground truths; si no, global) |

### Migración y Seed

| Archivo | Tipo | Contenido |
|---|---|---|
| `alembic/versions/c1d2e3f4a5b6_create_grading_tables.py` | NUEVO | Crea `submission_regions`, `card_evaluations`, `evaluation_subgrades`, `grading_baselines`; añade 3 valores al enum `submissionstatus` |
| `scripts/seed_grading_baseline.py` | NUEVO | Siembra el baseline `global` con `(d_min, d_max)` por región; idempotente |

### API (`api/v3/`)

| Archivo | Tipo | Contenido |
|---|---|---|
| `schemas/grading.py` | NUEVO | `PreprocessResponse`, `SubgradeSchema`, `EvaluationResponse` |
| `routers/submissions.py` | MODIFICADO | +3 endpoints: `POST /{id}/preprocess`, `POST /{id}/grade`, `GET /{id}/evaluation`. `grade` cablea `CardImageRepositoryImpl` + `PillowCardPreprocessingService` + `PHashImageHashService` + `StructuralRegionGradingService`. **Fix US-003:** `submit_card` recibe `card_id` como `Form(...)` (antes lo descartaba como query param) — sin esto el envío no se vincula a la carta y la calificación deriva siempre a manual. |
| `main.py` | MODIFICADO | `SubmissionNotFoundError → 404`, `CardNotPreprocessedError → 409` en el mapa de excepciones |

### Tests

| Archivo | Tipo | Cubre |
|---|---|---|
| `tests/unit/test_grading_baseline.py` | NUEVO | `score_for` monótona; d_min→10.0; d_max→1.0; todas las regiones |
| `tests/unit/test_phash_region_grading_service.py` | NUEVO | distancia 0→10.0; distancia 64→1.0; clamp; pHash vacío→error |
| `tests/unit/test_preprocess_card.py` | NUEVO | OK→PREPROCESSED+4regiones; MANUAL; RECAPTURE; 404; pHash recomputado |
| `tests/unit/test_grade_card.py` | NUEVO | sin referencia→MANUAL; 404; 409 no preprocesado; idempotencia; coherencia; banda; versión |
| `tests/integration/test_grading_pipeline.py` | NUEVO | pipeline end-to-end; 409 sin preprocess; idempotencia; GET 404 |
| `tests/conftest.py` | MODIFICADO | Importa 4 ORMs nuevos para `Base.metadata.create_all` |

---

## Esquema de BD añadido

```
submission_regions
  id (UUID PK), submission_id (FK submissions), region (VARCHAR12),
  data (BYTEA), phash (VARCHAR16), created_at
  UNIQUE(submission_id, region)

card_evaluations
  id (UUID PK), submission_id (FK submissions), card_id (FK catalog_cards nullable),
  final_grade (FLOAT), uncertainty (FLOAT), algorithm_version (VARCHAR32),
  baseline_ref (VARCHAR64), created_at
  UNIQUE(submission_id, algorithm_version)   ← garantiza immutabilidad + idempotencia

evaluation_subgrades
  id (UUID PK), evaluation_id (FK card_evaluations CASCADE),
  region (VARCHAR12), score (FLOAT), hamming_distance (INT), confidence (FLOAT)
  UNIQUE(evaluation_id, region)

grading_baselines
  id (UUID PK), ref (VARCHAR64 UNIQUE), is_calibrated (BOOL),
  ground_truth_count (INT), params_json (TEXT), created_at
```

---

## Endpoints nuevos

```
POST /api/v3/submissions/{id}/preprocess
  → 200 { status: "preprocessed"|"manual_review"|"needs_recapture", regions_ready, reason }
  → 404 (submission no existe)

POST /api/v3/submissions/{id}/grade
  → 200 { status: "graded"|"manual_review", final_grade, uncertainty ±, subgrades[], algorithm_version, baseline_ref }
  → 404 (submission no existe)
  → 409 (submission no está en PREPROCESSED)

GET /api/v3/submissions/{id}/evaluation
  → 200 evaluación existente
  → 404 (sin evaluación)
```

---

## Fórmulas clave

**Subgrade por región (`StructuralRegionGradingService`) = parecido pHash + daño local:**
```
# (1) parecido estructural (pHash), región-contra-su-misma-región
d           = hamming_distance(phash_envío, phash_referencia)   # 0..64
score_phash = 10.0 - 9.0 * (d - d_min) / (d_max - d_min)        # lineal entre d_min y d_max

# (2) daño local (lo que el pHash ignora): fracción de píxeles con Δcolor alto
altered      = fracción de píxeles con |Δcolor| > DAMAGE_COLOR_THRESHOLD (40)
damage_ratio = clamp(altered / DAMAGE_FULL_FRACTION, 0, 1)       # DAMAGE_FULL_FRACTION = 0.12
score_damage = 10.0 - 9.0 * damage_ratio

# (3) mezcla ponderada (w = DEFAULT_PHASH_WEIGHT = 0.35)
score      = clamp(round(w*score_phash + (1-w)*score_damage, 1), 1.0, 10.0)
confidence = (1 - d/64) * (1 - damage_ratio)
```
> Si faltan los bytes de los recortes, cae a pHash puro. El `PHashRegionGradingService` usa solo el bloque (1).

**Grado final (AC-G3):**
```
candidate = Σ(peso[región] × score[región])       # PESOS iguales: 0.25 c/u
min_sub   = min(scores)
final     = clamp(round(min(candidate, min_sub + 0.5), 1), 1.0, 10.0)
```

**Banda de incertidumbre (AC-G4):**
```
band = 0.3
     + 0.5 × stdev(scores)
     + (0.0 si calibrado; 0.4 si baseline global)
     + (0.3 si IQS < 0.75)
```

---

## Cómo ejecutar el pipeline

```bash
# 1. Migración (ya aplicada)
alembic upgrade head

# 2. Seed del baseline global (ya aplicado)
python scripts/seed_grading_baseline.py

# 3. Tests (189 pasan, cobertura 94.93%)
pytest tests/

# 4. Probar pipeline vía API (servidor corriendo en :8000)
# Enviar carta
curl -X POST http://localhost:8000/api/v3/submissions \
  -H "Authorization: Bearer <token>" \
  -F "image_front=@carta.jpg" \
  -F "image_back=@reverso.jpg"

# Preprocesar
curl -X POST http://localhost:8000/api/v3/submissions/<id>/preprocess \
  -H "Authorization: Bearer <token>"

# Calificar
curl -X POST http://localhost:8000/api/v3/submissions/<id>/grade \
  -H "Authorization: Bearer <token>"

# Ver evaluación
curl http://localhost:8000/api/v3/submissions/<id>/evaluation \
  -H "Authorization: Bearer <token>"
```

---

*Documento generado Sprint 4 — PokéGrading — Dr. Mundo Solutions.*
