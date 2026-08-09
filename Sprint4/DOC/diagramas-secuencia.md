# Diagramas de secuencia — Preprocesar carta y Calificar carta (Sprint 4)

**Proyecto:** PokéGrading — Dr. Mundo Solutions
**Sprint:** 4
**Relacionado:** [ADR-005](./ADR-005-preprocesamiento-y-calificacion.md) · [diseno-preprocesamiento-calificacion.md](./diseno-preprocesamiento-calificacion.md) · [diagramas-actividad.md](./diagramas-actividad.md)

> Las etiquetas usan los **nombres reales de archivo y clase** que tendrá el código (Fase B), siguiendo la convención de Sprint 2/3. Diagramas en **Mermaid** (renderizables en GitHub y en la wiki de Azure DevOps).

---

## 1. Preprocesar carta — escenario de éxito (AC-P1, AC-P2, AC-P3)

`POST /api/v3/submissions/{id}/preprocess` con un envío en estado `PENDING` cuya carta se aísla correctamente del fondo.

```mermaid
sequenceDiagram
    autonumber
    participant U as Submitter
    participant R as routers/submissions.py
    participant UC as PreprocessCardUseCase
    participant SR as SubmissionRepositoryImpl
    participant PP as PillowCardPreprocessingService
    participant PH as PHashImageHashService
    participant RR as RegionRepositoryImpl

    U->>R: POST /submissions/{id}/preprocess
    R->>UC: execute(PreprocessCardInput(submission_id))
    UC->>SR: find_by_id(submission_id)
    SR-->>UC: Submission(status=PENDING)
    UC->>SR: save(status=PROCESSING)
    UC->>PP: preprocess(image_front_data)
    Note over PP: 1) aislar carta 2) corregir perspectiva<br/>3) recortar 4) normalizar color 5) segmentar 4 regiones
    PP->>PH: compute_phash(region_crop) ×4
    PH-->>PP: phash ×4
    PP-->>UC: PreprocessOutcome(status=OK, card=PreprocessedCard)
    loop por cada región (centering, corners, edges, surface)
        UC->>RR: save(RegionImage(submission_id, region, data, phash))
    end
    UC->>SR: save(status=PREPROCESSED)
    UC-->>R: PreprocessCardOutput(status=preprocessed, regions_ready=true)
    R-->>U: 200 OK { status: "preprocessed" }
```

---

## 2. Preprocesar carta — ramas alternas (AC-P4 manual, AC-P5 recapturar)

Una sola corrida resuelve según lo que devuelve el servicio de preprocesamiento.

```mermaid
sequenceDiagram
    autonumber
    participant U as Submitter
    participant UC as PreprocessCardUseCase
    participant PP as PillowCardPreprocessingService
    participant SR as SubmissionRepositoryImpl

    U->>UC: execute(submission_id)
    UC->>PP: preprocess(image_front_data)
    alt No se aísla la carta del fondo (AC-P4)
        PP-->>UC: PreprocessOutcome(status=MANUAL, reason="card not isolated")
        UC->>SR: save(status=MANUAL_REVIEW, rejection_reason)
        UC-->>U: 200 { status: "manual_review" }
    else Distorsión imposible de corregir (AC-P5)
        PP-->>UC: PreprocessOutcome(status=RECAPTURE, reason="uncorrectable distortion")
        UC->>SR: save(status=NEEDS_RECAPTURE, rejection_reason)
        UC-->>U: 200 { status: "needs_recapture" }
    else Éxito (AC-P3)
        PP-->>UC: PreprocessOutcome(status=OK, card)
        UC->>SR: save(status=PREPROCESSED)
        UC-->>U: 200 { status: "preprocessed" }
    end
```

---

## 3. Calificar carta — escenario de éxito (AC-G1..G5)

`POST /api/v3/submissions/{id}/grade` sobre un envío `PREPROCESSED`, primera vez (no hay evaluación previa con esta versión).

```mermaid
sequenceDiagram
    autonumber
    participant U as Submitter
    participant R as routers/submissions.py
    participant UC as GradeCardUseCase
    participant ER as EvaluationRepositoryImpl
    participant SR as SubmissionRepositoryImpl
    participant RR as RegionRepositoryImpl
    participant CR as CardRepositoryImpl
    participant IR as CardImageRepositoryImpl
    participant PP as PillowCardPreprocessingService
    participant PH as PHashImageHashService
    participant BR as GradingBaselineRepositoryImpl
    participant GS as StructuralRegionGradingService

    U->>R: POST /submissions/{id}/grade
    R->>UC: execute(GradeCardInput(submission_id))
    UC->>ER: find_by_submission_and_version(id, "grading-v1.0.0")
    ER-->>UC: None  (no existe → calcular)
    UC->>SR: find_by_id(id)
    SR-->>UC: Submission(status=PREPROCESSED)
    UC->>RR: find_by_submission(id)
    RR-->>UC: [RegionImage×4 con phash + data]
    UC->>CR: find_by_id(card_id)
    CR-->>UC: Card(identity.set, identity.finish)
    UC->>IR: find_by_card_and_side(card_id, "front")
    IR-->>UC: CardImage(bytes de referencia)
    Note over UC,PP: Referencia segmentada región-contra-región
    UC->>PP: preprocess(front_bytes)
    PP-->>UC: 4 recortes de referencia
    loop por cada región de referencia
        UC->>PH: compute_phash(recorte_ref)
        PH-->>UC: phash_ref (+ se guarda data_ref)
    end
    UC->>BR: get_for(set, finish)
    alt ground truth suficiente
        BR-->>UC: GradingBaseline(ref="set:finish", is_calibrated=true)
    else insuficiente
        BR-->>UC: GradingBaseline(ref="global", is_calibrated=false)  (AC-G2)
    end
    loop por cada región
        UC->>GS: grade_region(phash_envio, phash_ref, baseline,<br/>data_envio, data_ref)
        Note over GS: score = w·score_pHash + (1-w)·score_daño<br/>(daño = dif. de píxeles, detecta rayones)
        GS-->>UC: Subgrade(score 1.0-10.0, hamming, confidence)
    end
    Note over UC: final = min(candidato, min_subgrade + 0.5)  (AC-G3)<br/>uncertainty = banda ±  (AC-G4)
    UC->>ER: save(CardEvaluation(algorithm_version, baseline_ref, subgrades))  (append-only, AC-G5)
    ER-->>UC: CardEvaluation persistida
    UC->>SR: save(status=GRADED)
    UC-->>R: GradeCardOutput(final_grade, uncertainty, subgrades)
    R-->>U: 201 { final_grade, uncertainty, subgrades:[...] }
```

---

## 4. Calificar carta — idempotencia (AC-G6)

Reintento con la **misma carta y sesión** (mismo `submission_id`) dentro de la misma versión de algoritmo: devuelve la evaluación ya almacenada, sin recalcular ni duplicar.

```mermaid
sequenceDiagram
    autonumber
    participant U as Submitter
    participant UC as GradeCardUseCase
    participant ER as EvaluationRepositoryImpl
    participant GS as StructuralRegionGradingService

    Note over U,UC: 1ª llamada ya generó y persistió la evaluación
    U->>UC: POST /submissions/{id}/grade (reintento)
    UC->>ER: find_by_submission_and_version(id, "grading-v1.0.0")
    ER-->>UC: CardEvaluation existente
    Note over UC,GS: NO se vuelve a calcular ningún subgrade<br/>NO se inserta una fila nueva
    UC-->>U: 201 misma evaluación (mismo id, mismo grade)
```

---

## 5. Calificar carta — derivaciones a humano (AC-G7 manual, AC-G8 coherencia)

```mermaid
sequenceDiagram
    autonumber
    participant UC as GradeCardUseCase
    participant GS as StructuralRegionGradingService
    participant SR as SubmissionRepositoryImpl

    UC->>GS: grade_region(region, ...)
    alt Insumos insuficientes para un subgrade (AC-G7)
        GS-->>UC: InsufficientGradingInputError(region)
        UC->>SR: save(status=MANUAL_REVIEW, reason="insufficient input: <region>")
        UC-->>UC: return { status: manual_review }
    else Subgrades calculados pero incoherentes (AC-G8)
        GS-->>UC: Subgrade×4
        Note over UC: stdev(subgrades) > UMBRAL_INCOHERENCIA
        UC->>SR: save(status=MANUAL_REVIEW, reason="incoherent grade")
        UC-->>UC: return { status: manual_review }
    end
```

---

## 6. Pipeline completo — encadenamiento de los dos use cases

Visión de extremo a extremo: del envío validado (US-003) al grado estimado, mostrando dónde encajan las dos nuevas actividades dentro del [flujo de grading de Sprint 3](../../Sprint3/DOC/diagramas-actividad.md).

```mermaid
sequenceDiagram
    autonumber
    participant U as Submitter
    participant SUBMIT as SubmitCardForEvaluationUseCase
    participant PRE as PreprocessCardUseCase
    participant GRADE as GradeCardUseCase

    U->>SUBMIT: enviar imágenes (US-003)
    SUBMIT-->>U: Submission PENDING
    U->>PRE: preprocess(submission_id)
    alt preprocesamiento OK (AC-P3)
        PRE-->>U: PREPROCESSED → avanza a calificación
        U->>GRADE: grade(submission_id)
        alt subgrades OK y coherentes
            GRADE-->>U: GRADED (grado ± banda)
        else AC-G7 / AC-G8
            GRADE-->>U: MANUAL_REVIEW
        end
    else AC-P4
        PRE-->>U: MANUAL_REVIEW
    else AC-P5
        PRE-->>U: NEEDS_RECAPTURE (recapturar)
    end
```

---

## 7. Trazabilidad secuencia → código (Fase B)

| Participante en diagramas | Archivo de código a implementar |
|---|---|
| `routers/submissions.py` (+preprocess/+grade) | `api/v3/routers/submissions.py` |
| `PreprocessCardUseCase` | `application/use_cases/preprocess_card.py` |
| `GradeCardUseCase` | `application/use_cases/grade_card.py` |
| `PillowCardPreprocessingService` | `infrastructure/preprocessing/pillow_card_preprocessing_service.py` |
| `StructuralRegionGradingService` / `PHashRegionGradingService` | `infrastructure/grading/phash_region_grading_service.py` |
| `PHashImageHashService` | `infrastructure/matching/phash_image_hash_service.py` (ya existe) |
| `SubmissionRepositoryImpl` | `infrastructure/persistence/repositories/submission_repository.py` (ya existe) |
| `RegionRepositoryImpl` | `infrastructure/persistence/repositories/submission/region_repository.py` |
| `EvaluationRepositoryImpl` | `infrastructure/persistence/repositories/evaluation/evaluation_repository.py` |
| `GradingBaselineRepositoryImpl` | `infrastructure/persistence/repositories/grading/grading_baseline_repository.py` |
| `CardRepositoryImpl` | `infrastructure/persistence/repositories/card/card_repository.py` (ya existe) |
| `CardImageRepositoryImpl` | `infrastructure/persistence/repositories/card/image_repository.py` (ya existe) |
| `PillowCardPreprocessingService` (referencia) | `infrastructure/preprocessing/pillow_card_preprocessing_service.py` |

---

## Referencias

- [ADR-005 — Preprocesamiento y calificación](./ADR-005-preprocesamiento-y-calificacion.md)
- [Diseño detallado](./diseno-preprocesamiento-calificacion.md)
- [Diagramas de actividad (Sprint 4)](./diagramas-actividad.md)
- [Diagramas de secuencia (Sprint 3)](../../Sprint3/DOC/diagramas-secuencia.md)
