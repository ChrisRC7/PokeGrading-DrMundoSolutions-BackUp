# Diseño detallado — Preprocesar carta y Calificar carta (Sprint 4)

**Proyecto:** PokéGrading — Dr. Mundo Solutions
**Sprint:** 4
**Relacionado:** [ADR-005](./ADR-005-preprocesamiento-y-calificacion.md) · [diagramas-secuencia.md](./diagramas-secuencia.md) · [diagramas-actividad.md](./diagramas-actividad.md)

> Este documento baja el [ADR-005](./ADR-005-preprocesamiento-y-calificacion.md) a firmas concretas: entidades, value objects, puertos, casos de uso, fórmulas y esquema de BD. La Fase B (código) implementa **exactamente** estos contratos. Convención de comentarios y estilo: igual que Sprint 1–3 (docstrings + comentarios que explican el *por qué*, no el *qué*).

---

## 1. Glosario de tipos nuevos

| Tipo | Capa | Rol |
|---|---|---|
| `GradingRegion` | domain/value_objects | Enum de las 4 dimensiones: `centering`, `corners`, `edges`, `surface`. |
| `PreprocessingStatus` | domain/value_objects | Resultado del preprocesamiento: `ok`, `manual`, `recapture`. |
| `RegionImage` | domain/entities | Recorte normalizado de una región (`region`, `data: bytes`, `phash`). |
| `PreprocessedCard` | domain/entities | Imagen normalizada + las 4 `RegionImage` + metadata de corrección. |
| `Subgrade` | domain/entities (VO) | `region`, `score (1.0–10.0)`, `hamming_distance`, `confidence`. |
| `CardEvaluation` | domain/entities | Agregado **inmutable** del grado: subgrades, grado final, banda, versión, baseline usado. |
| `GradingBaseline` | domain/entities | Mapeo distancia→grado calibrado por `(set, finish)` o global. |
| `ICardPreprocessingService` | application/ports | Puerto de preprocesamiento (perspectiva, recorte, color, segmentación). |
| `IRegionGradingService` | application/ports | Puerto de cálculo de subgrade por región (recibe pHash + bytes de recortes). |
| `StructuralRegionGradingService` | infrastructure/grading | Implementación que combina pHash (parecido) + diferencia de píxeles (daño local). |
| `IEvaluationRepository` | domain/repositories | Persistencia append-only de `CardEvaluation`. |
| `IGradingBaselineRepository` | domain/repositories | Selección de baseline calibrado / global. |
| `PreprocessCardUseCase` | application/use_cases | Orquesta AC-P1..P5. |
| `GradeCardUseCase` | application/use_cases | Orquesta AC-G1..G8. |

---

## 2. Preprocesar carta

### 2.1 Puerto `ICardPreprocessingService`

```python
# application/ports/card_preprocessing_service.py
class ICardPreprocessingService(ABC):
    """Puerto para el preprocesamiento de la imagen de una carta.

    Normaliza la imagen recibida para que el cálculo de grado opere sobre datos
    consistentes y comparables (US "Preprocesar carta"). La implementación de
    desarrollo usa Pillow/NumPy; producción puede migrar a OpenCV sin tocar el
    puerto (mismo patrón que IImageQualityService / IImageHashService).
    """

    @abstractmethod
    def preprocess(self, image_data: bytes) -> PreprocessOutcome:
        """Corrige perspectiva, recorta al borde de la carta y normaliza color.

        Devuelve un PreprocessOutcome que indica:
        - status=OK + imagen normalizada + 4 regiones segmentadas, o
        - status=MANUAL (no se pudo aislar la carta del fondo), o
        - status=RECAPTURE (distorsión imposible de corregir).
        Nunca lanza para las ramas de negocio: las codifica en el outcome para
        que el use case decida el estado del Submission.
        """
```

`PreprocessOutcome` (dataclass en el mismo módulo del puerto o en `domain/entities/preprocessed_card.py`):

```python
@dataclass(frozen=True)
class PreprocessOutcome:
    status: PreprocessingStatus          # OK | MANUAL | RECAPTURE
    card: PreprocessedCard | None        # presente solo si status == OK
    reason: str | None = None            # motivo legible en MANUAL/RECAPTURE
```

### 2.2 Pasos del pipeline de preprocesamiento (implementación de desarrollo)

| Paso | AC | Técnica de desarrollo (Pillow/NumPy) | Falla → |
|---|---|---|---|
| 1. Aislar carta del fondo | AC-P1/P4 | Detección de contorno rectangular dominante (umbral + bounding box del mayor contorno). | `MANUAL` |
| 2. Corrección de perspectiva | AC-P1/P5 | Transformación de los 4 vértices del contorno a un rectángulo canónico. Si los vértices no forman un cuadrilátero plausible → `RECAPTURE`. | `RECAPTURE` |
| 3. Recorte al borde | AC-P1 | Crop al bounding box corregido. | — |
| 4. Normalización de color | AC-P1 | Auto-contraste / balance de grises sobre el recorte (estabiliza iluminación). | — |
| 5. Segmentación en 4 regiones | AC-P2 | Recortes deterministas por proporción sobre la imagen normalizada (ver §2.3). | — |
| 6. pHash por región | (insumo de grading) | `IImageHashService.compute_phash` sobre cada recorte. | — |

> La implementación de desarrollo es **heurística y suficiente** para el flujo end-to-end (igual que `PillowImageQualityService` en Sprint 2). Lo importante para la arquitectura es el **contrato** del puerto, no la sofisticación del algoritmo; producción sustituye el adaptador.

### 2.3 Segmentación en 4 regiones (AC-P2)

Sobre la imagen ya recortada y normalizada (ancho `W`, alto `H`):

| Región | Definición geométrica (proporcional, reproducible) |
|---|---|
| `centering` | Banda perimetral: se mide el margen impreso vs. el borde físico en los 4 lados (relación izq/der y sup/inf). |
| `corners` | 4 cuadrantes de las esquinas (p. ej. 15% × 15% de cada esquina), combinados. |
| `edges` | Marco perimetral (franja externa, p. ej. 8% del lado), excluyendo el interior. |
| `surface` | Región interior central (resto de la carta), donde se evalúa rayones/holo. |

Cada región produce un `RegionImage(region, data, phash)`. La geometría es **determinista** para que dos corridas sobre la misma imagen normalizada den los mismos recortes (precondición de idempotencia).

### 2.4 `PreprocessCardUseCase`

```python
# application/use_cases/preprocess_card.py
@dataclass(frozen=True)
class PreprocessCardInput:
    submission_id: UUID

@dataclass(frozen=True)
class PreprocessCardOutput:
    submission_id: UUID
    status: str            # "preprocessed" | "manual_review" | "needs_recapture"
    regions_ready: bool    # True solo si status == preprocessed
    reason: str | None

class PreprocessCardUseCase:
    def __init__(self, submission_repo, preprocessing_svc, hash_svc): ...
    def execute(self, inp) -> PreprocessCardOutput:
        # 1. Cargar submission (404 → SubmissionNotFoundError)
        # 2. Marcar PROCESSING
        # 3. outcome = preprocessing_svc.preprocess(submission.image_front_data)
        # 4. match outcome.status:
        #      OK        → guardar PreprocessedCard (regiones+phash), Submission=PREPROCESSED (AC-P3)
        #      MANUAL    → Submission=MANUAL_REVIEW (AC-P4)
        #      RECAPTURE → Submission=NEEDS_RECAPTURE (AC-P5)
```

**Persistencia de regiones:** las 4 `RegionImage` (con su pHash) se guardan asociadas al `submission_id` para que `GradeCardUseCase` no recompute el preprocesamiento. Tabla `submission_regions` (§4.1).

---

## 3. Calificar carta

### 3.1 Entidades de grado

```python
# domain/entities/card_evaluation.py
@dataclass(frozen=True)
class Subgrade:
    region: GradingRegion
    score: float            # 1.0–10.0
    hamming_distance: int   # distancia pHash región-envío vs región-referencia [0..64]
    confidence: float       # 0.0–1.0 (insumo de la banda)

@dataclass(frozen=True)
class CardEvaluation:
    """Evaluación estimada e INMUTABLE de una carta (AC-G5).

    Una vez creada no se modifica: liberar una versión nueva del algoritmo
    genera otra CardEvaluation, nunca un UPDATE sobre esta.
    """
    id: UUID
    submission_id: UUID
    card_id: UUID | None
    subgrades: tuple[Subgrade, ...]      # las 4 dimensiones
    final_grade: float                   # 1.0–10.0, ya acotado por la regla de coherencia
    uncertainty: float                   # banda ± (AC-G4)
    algorithm_version: str               # identificador exacto de versión (AC-G5)
    baseline_ref: str                    # "set:finish" calibrado o "global" (AC-G2)
    created_at: datetime
```

### 3.2 Puerto `IRegionGradingService` y modelo pHash

```python
# application/ports/region_grading_service.py
class IRegionGradingService(ABC):
    @abstractmethod
    def grade_region(
        self,
        region: GradingRegion,
        submission_region_phash: str,
        reference_region_phash: str,
        baseline: GradingBaseline,
        *,
        submission_region_data: bytes = b"",   # recorte normalizado del envío
        reference_region_data: bytes = b"",    # recorte normalizado de la referencia
    ) -> Subgrade:
        """Calcula el subgrade de una región.

        Devuelve un Subgrade con score en 1.0–10.0. Si los pHashes son
        insuficientes (ausentes / región ilegible), lanza
        InsufficientGradingInputError para derivar a manual (AC-G7).

        Los bytes de los recortes son OPCIONALES (default vacío) para no romper
        a las implementaciones que solo usan pHash; las sensibles al daño comparan
        los píxeles de ambos recortes. Este puerto pertenece a CALIFICAR: la etapa
        de IDENTIFICAR carta (búsqueda pHash) no lo usa y no se ve afectada.
        """
```

**Implementaciones del puerto:**

| Servicio | Señal | Uso |
|---|---|---|
| `StructuralRegionGradingService` | pHash + **diferencia de píxeles (daño local)** | **Producción/demo** — el que usa el router |
| `PHashRegionGradingService` | solo pHash | Línea base / comparación |
| `StubRegionGradingService` | distancia fija | Tests deterministas |

**Fórmula combinada (`StructuralRegionGradingService`):**

```
# (1) Parecido estructural por pHash
d            = hamming_distance(submission_region_phash, reference_region_phash)   # 0..64
score_phash  = baseline.score_for(region, d)     # d≤d_min→10.0, d≥d_max→1.0, lineal en medio

# (2) Daño local por diferencia de píxeles (lo que el pHash ignora)
altered      = fracción de píxeles del recorte con |Δcolor| > DAMAGE_COLOR_THRESHOLD
damage_ratio = clamp(altered / DAMAGE_FULL_FRACTION, 0.0, 1.0)
score_damage = 10.0 - 9.0 * damage_ratio          # 0% alterado → 10.0; daño pleno → 1.0

# (3) Mezcla ponderada (w = DEFAULT_PHASH_WEIGHT)
score        = clamp(round(w*score_phash + (1-w)*score_damage, 1), 1.0, 10.0)
confidence   = (1 - d/64) * (1 - damage_ratio)    # baja con distancia y con daño (insumo de la banda)
```

Si falta alguno de los recortes (no decodificable), el servicio cae a **pHash puro** (sin componente de daño). El `PHashRegionGradingService` usa solo el bloque (1).

> El baseline calibrado por `(set, finish)` ajusta `d_min`/`d_max` con ground truth real; el global usa los valores sembrados. **El baseline efectivamente usado se registra** en `CardEvaluation.baseline_ref` (AC-G2).

### 3.3 Selección de baseline (AC-G2)

```python
# domain/entities/grading_baseline.py
@dataclass(frozen=True)
class GradingBaseline:
    ref: str                          # "set:finish" o "global"
    is_calibrated: bool               # True si proviene de ground truth suficiente
    params_by_region: dict[GradingRegion, tuple[int, int]]   # (d_min, d_max) por región
    ground_truth_count: int

    def score_for(self, region, d) -> float: ...
```

```python
# domain/repositories/grading_baseline_repository.py
class IGradingBaselineRepository(ABC):
    @abstractmethod
    def get_for(self, set_name: str, finish: str) -> GradingBaseline:
        """Devuelve el baseline calibrado de (set, finish) si tiene ground truth
        suficiente (>= MIN_GROUND_TRUTH); de lo contrario, el baseline GLOBAL.
        Nunca devuelve None: el global siempre existe (sembrado)."""
```

`MIN_GROUND_TRUTH` (umbral de "ground truth suficiente") se define como constante de aplicación, p. ej. `MIN_GROUND_TRUTH = 30`.

### 3.4 Grado final y regla de coherencia (AC-G3)

```python
PESOS = {CENTERING: 0.25, CORNERS: 0.25, EDGES: 0.25, SURFACE: 0.25}  # iguales por defecto

candidate = sum(PESOS[sg.region] * sg.score for sg in subgrades)
min_sub   = min(sg.score for sg in subgrades)
final     = round(min(candidate, min_sub + 0.5), 1)     # AC-G3: nunca excede el peor + 0.5
final     = clamp(final, 1.0, 10.0)
```

### 3.5 Banda de incertidumbre (AC-G4)

```
dispersion = stdev([sg.score for sg in subgrades])
base_band  = 0.3                                  # piso de incertidumbre del método
band  = base_band
       + 0.5 * dispersion                         # regiones discordantes → más incertidumbre
       + (0.0 if baseline.is_calibrated else 0.4) # baseline global → banda más ancha
       + (0.3 if submission.image_quality_score < 0.75 else 0.0)
uncertainty = round(band, 1)
# Output: f"{final} ± {uncertainty}"
```

### 3.6 Inmutabilidad, versión e idempotencia (AC-G5/G6)

```python
GRADING_ALGORITHM_VERSION = "grading-v1.0.0"   # constante de código

# IEvaluationRepository
class IEvaluationRepository(ABC):
    @abstractmethod
    def find_by_submission_and_version(self, submission_id, algorithm_version) -> CardEvaluation | None: ...
    @abstractmethod
    def save(self, evaluation: CardEvaluation) -> CardEvaluation:
        """INSERT-only (append-only). Nunca actualiza una fila existente.
        Si la BD detecta violación de la clave única (submission_id, algorithm_version)
        en una carrera, el repositorio devuelve la fila ya existente (idempotencia)."""
```

- **Idempotencia (AC-G6):** `GradeCardUseCase` arranca con `find_by_submission_and_version(submission_id, GRADING_ALGORITHM_VERSION)`. Si existe → la devuelve sin recalcular ni insertar (sesión = `submission_id`).
- **Inmutabilidad (AC-G5):** la tabla tiene la versión en la PK lógica; `save` solo inserta. Una versión nueva produce una fila distinta, dejando intacta la anterior.

### 3.7 `GradeCardUseCase`

```python
# application/use_cases/grade_card.py
@dataclass(frozen=True)
class GradeCardInput:
    submission_id: UUID

@dataclass(frozen=True)
class GradeCardOutput:
    evaluation_id: UUID
    submission_id: UUID
    status: str                 # "graded" | "manual_review"
    final_grade: float | None
    uncertainty: float | None
    subgrades: tuple[Subgrade, ...]
    algorithm_version: str
    baseline_ref: str | None

class GradeCardUseCase:
    def __init__(self, submission_repo, region_repo, evaluation_repo, baseline_repo,
                 card_repo, image_repo, preprocessing_svc, hash_svc, grading_svc): ...
    def execute(self, inp) -> GradeCardOutput:
        # 0. IDEMPOTENCIA: evaluation_repo.find_by_submission_and_version(...) → si existe, return (AC-G6)
        # 1. Cargar submission; debe estar PREPROCESSED (si no, CardNotPreprocessedError 409)
        # 2. Cargar las 4 RegionImage del submission (regiones + phash + data)
        # 3. Resolver carta de referencia (submission.card_id → card_repo):
        #      - set/finish ← card.identity (selecciona el baseline)
        #      - image_repo.find_by_card_and_side(card.id, "front") → bytes de la referencia
        #      - REFERENCIA SEGMENTADA: preprocessing_svc.preprocess(front_bytes) →
        #        por cada región: hash_svc.compute_phash(recorte) y se guarda el recorte
        #        (así se compara región-contra-su-misma-región, no contra la imagen completa)
        #      - fallback: si la referencia no se segmenta, se usa su phash global en todas
        # 4. baseline = baseline_repo.get_for(set_name, finish)   (AC-G2)
        # 5. Para cada región: grade_region(phash_envío, phash_ref, baseline,
        #        data_envío, data_ref) → Subgrade (AC-G1)
        #      - si falta pHash/región → MANUAL_REVIEW (AC-G7)
        # 6. final = regla de coherencia (AC-G3); uncertainty = banda (AC-G4)
        # 7. COHERENCIA INTERNA: si dispersión > UMBRAL_INCOHERENCIA → MANUAL_REVIEW (AC-G8)
        # 8. Construir CardEvaluation (algorithm_version, baseline.ref) y evaluation_repo.save (AC-G5)
        # 9. Submission=GRADED; return GradeCardOutput
```

> **Nota sobre los insumos del envío (US-003).** Para que `submission.card_id` quede vinculado, el endpoint de envío recibe `card_id` como campo de formulario (`Form(...)`), no como query param. Sin esa vinculación no hay carta de referencia y la calificación deriva a manual (AC-G7).

---

## 4. Persistencia (esquema)

### 4.1 `submission_regions` — recortes y pHash por región (producto del preprocesamiento)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | `uuid7` |
| `submission_id` | UUID FK → submissions | indexado |
| `region` | String(12) | `centering`/`corners`/`edges`/`surface` |
| `data` | LargeBinary | recorte normalizado (BYTEA; producción → Blob) |
| `phash` | String(16) | pHash del recorte |
| `created_at` | DateTime(tz) | |
| | | `UniqueConstraint(submission_id, region)` |

### 4.2 `card_evaluations` — evaluación inmutable (append-only)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | `uuid7` |
| `submission_id` | UUID FK → submissions | indexado |
| `card_id` | UUID FK → catalog_cards (nullable) | |
| `final_grade` | Float | 1.0–10.0 |
| `uncertainty` | Float | banda ± |
| `algorithm_version` | String(32) | AC-G5 |
| `baseline_ref` | String(64) | `"set:finish"` o `"global"` (AC-G2) |
| `created_at` | DateTime(tz) | |
| | | `UniqueConstraint(submission_id, algorithm_version)` → idempotencia/inmutabilidad (AC-G6) |

### 4.3 `evaluation_subgrades` — un subgrade por dimensión

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `evaluation_id` | UUID FK → card_evaluations (CASCADE) | |
| `region` | String(12) | |
| `score` | Float | 1.0–10.0 |
| `hamming_distance` | Integer | 0..64 |
| `confidence` | Float | 0.0–1.0 |
| | | `UniqueConstraint(evaluation_id, region)` |

### 4.4 `grading_baselines` — baseline calibrado/global

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `ref` | String(64) unique | `"set:finish"` o `"global"` |
| `is_calibrated` | Boolean | |
| `ground_truth_count` | Integer | |
| `params_json` | Text | `{region: [d_min, d_max]}` (JSON portable PG/SQLite, como B2B idempotency) |
| `created_at` | DateTime(tz) | |

> **Seed:** `scripts/seed_grading_baseline.py` inserta el baseline `global` con los `(d_min, d_max)` por defecto, igual que el seed de llave B2B del Sprint 3. Sin él, `get_for` no tendría fallback.

---

## 5. Excepciones nuevas (`domain/exceptions.py`)

Todas heredan de `PokegradingError` (igual que el resto del dominio), para que el router las mapee a HTTP sin acoplarse a infraestructura:

| Excepción | HTTP sugerido | Cuándo |
|---|---|---|
| `SubmissionNotFoundError(id)` | 404 | submission inexistente en preprocess/grade |
| `CardNotPreprocessedError(id)` | 409 | grade sobre un submission que no está `PREPROCESSED` |
| `CardIsolationFailedError` | (no HTTP: rama de negocio → `MANUAL_REVIEW`) | no se aísla la carta del fondo (AC-P4) |
| `UncorrectableDistortionError` | (rama de negocio → `NEEDS_RECAPTURE`) | distorsión imposible de corregir (AC-P5) |
| `InsufficientGradingInputError(region)` | (rama de negocio → `MANUAL_REVIEW`) | subgrade sin insumos suficientes (AC-G7) |
| `IncoherentGradeError` | (rama de negocio → `MANUAL_REVIEW`) | viola coherencia interna mínima (AC-G8) |

> Las ramas de negocio (P4/P5/G7/G8) se prefieren modeladas como **outcome/estado del `Submission`**, no como excepción que aborta; las excepciones listadas existen para los casos que un use case sí debe cortar (404/409) o para señalización interna entre servicio y use case.

---

## 6. Endpoints (API v3)

| Método | Ruta | Use case | Respuestas |
|---|---|---|---|
| `POST` | `/api/v3/submissions/{id}/preprocess` | `PreprocessCardUseCase` | 200 `{status: preprocessed\|manual_review\|needs_recapture}` · 404 |
| `POST` | `/api/v3/submissions/{id}/grade` | `GradeCardUseCase` | 200/201 evaluación (idempotente) · 200 `{status: manual_review}` · 404 · 409 (no preprocesada) |
| `GET` | `/api/v3/submissions/{id}/evaluation` | `IEvaluationRepository` | 200 evaluación · 404 |

Schemas en `api/v3/schemas/grading.py`. El router reusa `get_current_user` (cualquier rol autenticado) como el resto de `/submissions`.

---

## 7. Constantes de configuración (centralizadas)

| Constante | Valor inicial | Ubicación | Efecto |
|---|---|---|---|
| `GRADING_ALGORITHM_VERSION` | `"grading-v1.0.0"` | `grade_card.py` | versión inmutable de la evaluación |
| `MIN_GROUND_TRUTH` | `30` | `grade_card.py` | mínimo de ground truth para usar baseline calibrado |
| `UMBRAL_INCOHERENCIA` (stdev subgrades) | `2.5` | `grade_card.py` | dispersión que deriva a revisión humana (AC-G8) |
| `PESOS` por región | centering/corners/edges/surface = `.25` c/u | `grade_card.py` | peso de cada región en la media |
| `_BASE_BAND` / `_IQS_BAND_THRESHOLD` | `0.3` / `0.75` | `grade_card.py` | ancho base de la banda de incertidumbre |
| `DEFAULT_PHASH_WEIGHT` | `0.35` | `phash_region_grading_service.py` | peso pHash vs daño; bajar = penaliza más el daño |
| `DAMAGE_COLOR_THRESHOLD` | `40` | `phash_region_grading_service.py` | Δcolor por píxel para contar como marca |
| `DAMAGE_FULL_FRACTION` | `0.12` | `phash_region_grading_service.py` | fracción alterada que implica daño total |
| `(d_min, d_max)` global por región | centering `(4,20)`, corners `(2,18)`, edges `(3,22)`, surface `(4,28)` | tabla `grading_baselines` (seed) | tolerancia de distancia pHash por región |

---

## Referencias

- [ADR-005](./ADR-005-preprocesamiento-y-calificacion.md)
- [diagramas-secuencia.md](./diagramas-secuencia.md)
- [diagramas-actividad.md](./diagramas-actividad.md)
- [busqueda-phash-ocr.md (Sprint 3)](../../Sprint3/DOC/busqueda-phash-ocr.md)
