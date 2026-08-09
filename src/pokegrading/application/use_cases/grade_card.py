from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from uuid_extensions import uuid7

from pokegrading.application.ports.card_preprocessing_service import ICardPreprocessingService
from pokegrading.application.ports.image_hash_service import IImageHashService
from pokegrading.application.ports.region_grading_service import IRegionGradingService
from pokegrading.domain.entities.card_evaluation import CardEvaluation, Subgrade
from pokegrading.domain.exceptions import (
    CardNotPreprocessedError,
    IncoherentGradeError,
    InsufficientGradingInputError,
    SubmissionNotFoundError,
)
from pokegrading.domain.repositories.card_repository import ICardRepository
from pokegrading.domain.repositories.evaluation_repository import IEvaluationRepository
from pokegrading.domain.repositories.image_repository import ICardImageRepository
from pokegrading.domain.repositories.grading_baseline_repository import IGradingBaselineRepository
from pokegrading.domain.repositories.region_repository import IRegionRepository
from pokegrading.domain.repositories.submission_repository import ISubmissionRepository
from pokegrading.domain.value_objects.grading_region import GradingRegion
from pokegrading.domain.value_objects.preprocessing_status import PreprocessingStatus
from pokegrading.domain.value_objects.submission_status import SubmissionStatus

# ── Constantes de configuración ───────────────────────────────────────────────

GRADING_ALGORITHM_VERSION = "grading-v1.0.0"
MIN_GROUND_TRUTH = 30
UMBRAL_INCOHERENCIA = 5.5 #Aumentar si cartas caen mucho en revisión manual por dispersión de subgrades, bajar si se aprueban cartas incoherentes

# Pesos por región; suman 1.0 (AC-G3)
PESOS: dict[GradingRegion, float] = {
    GradingRegion.CENTERING: 0.25,
    GradingRegion.CORNERS: 0.25,
    GradingRegion.EDGES: 0.25,
    GradingRegion.SURFACE: 0.25,
}

# Piso de incertidumbre del método (AC-G4)
_BASE_BAND = 0.3
_IQS_BAND_THRESHOLD = 0.75


# ── DTOs ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GradeCardInput:
    submission_id: UUID


@dataclass(frozen=True)
class GradeCardOutput:
    evaluation_id: UUID
    submission_id: UUID
    status: str                      # "graded" | "manual_review"
    final_grade: float | None
    uncertainty: float | None
    subgrades: tuple[Subgrade, ...]
    algorithm_version: str
    baseline_ref: str | None


# ── Helpers privados ──────────────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _compute_final_grade(subgrades: list[Subgrade]) -> float:
    """Media ponderada acotada por la regla de coherencia (AC-G3).

    El grado final no puede superar el subgrade más bajo + 0.5: una región
    en muy mal estado limita el grado global, independientemente del resto.
    """
    candidate = sum(PESOS[sg.region] * sg.score for sg in subgrades)
    min_sub = min(sg.score for sg in subgrades)
    final = min(candidate, min_sub + 0.5)
    return _clamp(round(final, 1), 1.0, 10.0)


def _compute_uncertainty(
    subgrades: list[Subgrade],
    is_calibrated: bool,
    image_quality_score: float | None,
) -> float:
    """Banda de incertidumbre: refleja discordancia entre regiones, calidad de
    imagen y si el baseline usado es el global no calibrado (AC-G4)."""
    dispersion = statistics.stdev([sg.score for sg in subgrades]) if len(subgrades) > 1 else 0.0
    band = (
        _BASE_BAND
        + 0.5 * dispersion
        + (0.0 if is_calibrated else 0.4)
        + (0.3 if (image_quality_score or 1.0) < _IQS_BAND_THRESHOLD else 0.0)
    )
    return round(band, 1)


# ── Use case ──────────────────────────────────────────────────────────────────

class GradeCardUseCase:
    """US Sprint-4: Califica una carta a partir de sus regiones preprocesadas.

    Flujo:
    0. Idempotencia: si ya existe evaluación con la misma versión, devolverla (AC-G6)
    1. Cargar submission; debe estar PREPROCESSED (AC-precondición)
    2. Cargar 4 RegionImage del submission
    3. Resolver carta de referencia y su pHash por región
    4. Seleccionar baseline calibrado / global (AC-G2)
    5. Subgrade por región (AC-G1); sin insumos → MANUAL_REVIEW (AC-G7)
    6. Regla de coherencia + banda de incertidumbre (AC-G3/G4)
    7. Coherencia interna: dispersión > umbral → MANUAL_REVIEW (AC-G8)
    8. Persistir CardEvaluation inmutable (AC-G5) y marcar GRADED
    """

    def __init__(
        self,
        submission_repo: ISubmissionRepository,
        region_repo: IRegionRepository,
        evaluation_repo: IEvaluationRepository,
        baseline_repo: IGradingBaselineRepository,
        card_repo: ICardRepository,
        image_repo: ICardImageRepository,
        preprocessing_svc: ICardPreprocessingService,
        hash_svc: IImageHashService,
        grading_svc: IRegionGradingService,
    ) -> None:
        self._submission_repo = submission_repo
        self._region_repo = region_repo
        self._evaluation_repo = evaluation_repo
        self._baseline_repo = baseline_repo
        self._card_repo = card_repo
        self._image_repo = image_repo
        self._preprocessing_svc = preprocessing_svc
        self._hash_svc = hash_svc
        self._grading_svc = grading_svc

    def execute(self, inp: GradeCardInput) -> GradeCardOutput:
        # 0. Idempotencia (AC-G6): reutilizar evaluación existente para esta versión
        existing = self._evaluation_repo.find_by_submission_and_version(
            inp.submission_id, GRADING_ALGORITHM_VERSION
        )
        if existing is not None:
            return self._to_output(existing, "graded")

        # 1. Cargar submission y verificar precondición
        submission = self._submission_repo.find_by_id(inp.submission_id)
        if submission is None:
            raise SubmissionNotFoundError(inp.submission_id)
        if submission.status != SubmissionStatus.PREPROCESSED:
            raise CardNotPreprocessedError(inp.submission_id)

        # 2. Cargar regiones
        regions = self._region_repo.find_by_submission(inp.submission_id)
        region_map = {r.region: r for r in regions}

        # 3. Resolver carta de referencia y sus pHashes por región
        ref_phash_by_region: dict[GradingRegion, str] = {}
        ref_data_by_region: dict[GradingRegion, bytes] = {}
        set_name = "unknown"
        finish = "unknown"

        if submission.card_id is not None:
            card = self._card_repo.find_by_id(submission.card_id)
            if card is not None:
                # La identidad de catálogo (set, acabado) selecciona el baseline (AC-G2).
                set_name = card.identity.set_name
                finish = card.identity.finish
                front_img = self._image_repo.find_by_card_and_side(card.id, "front")
                if front_img is not None and front_img.data:
                    # Para que la comparación sea región-contra-región, la imagen de
                    # referencia se preprocesa y segmenta igual que el envío: así el
                    # pHash de "esquinas" se compara con el de "esquinas", etc. Esto
                    # evita la dispersión artificial de comparar cada recorte contra
                    # el pHash de la imagen completa.
                    ref_outcome = self._preprocessing_svc.preprocess(front_img.data)
                    if (
                        ref_outcome.status == PreprocessingStatus.OK
                        and ref_outcome.card is not None
                    ):
                        # El servicio entrega los recortes sin pHash; se calcula aquí
                        # sobre cada recorte de referencia, igual que PreprocessCardUseCase
                        # hace con el envío, para comparar región contra su misma región.
                        for ref_region in ref_outcome.card.regions:
                            ref_phash = self._hash_svc.compute_phash(ref_region.data)
                            if ref_phash:
                                ref_phash_by_region[ref_region.region] = ref_phash
                                # Se conservan los bytes del recorte de referencia para
                                # que el servicio pueda medir daño local (rayones/marcas)
                                # comparando píxeles región-contra-región.
                                ref_data_by_region[ref_region.region] = ref_region.data
                    elif front_img.phash:
                        # Fallback: si la referencia no se puede segmentar, se reutiliza
                        # su pHash global para todas las regiones.
                        for region in GradingRegion:
                            ref_phash_by_region[region] = front_img.phash

        # 4. Baseline calibrado / global (AC-G2)
        baseline = self._baseline_repo.get_for(set_name, finish)

        # 5. Subgrade por región (AC-G1/G7)
        subgrades: list[Subgrade] = []
        for region in GradingRegion:
            sub_region = region_map.get(region)
            ref_phash = ref_phash_by_region.get(region, "")

            if not sub_region or not sub_region.phash or not ref_phash:
                # Sin insumos suficientes → derivar a revisión manual (AC-G7)
                submission.status = SubmissionStatus.MANUAL_REVIEW
                self._submission_repo.save(submission)
                return GradeCardOutput(
                    evaluation_id=uuid7(),
                    submission_id=inp.submission_id,
                    status=SubmissionStatus.MANUAL_REVIEW.value,
                    final_grade=None,
                    uncertainty=None,
                    subgrades=tuple(subgrades),
                    algorithm_version=GRADING_ALGORITHM_VERSION,
                    baseline_ref=baseline.ref,
                )

            try:
                sg = self._grading_svc.grade_region(
                    region=region,
                    submission_region_phash=sub_region.phash,
                    reference_region_phash=ref_phash,
                    baseline=baseline,
                    submission_region_data=sub_region.data,
                    reference_region_data=ref_data_by_region.get(region, b""),
                )
            except InsufficientGradingInputError:
                submission.status = SubmissionStatus.MANUAL_REVIEW
                self._submission_repo.save(submission)
                return GradeCardOutput(
                    evaluation_id=uuid7(),
                    submission_id=inp.submission_id,
                    status=SubmissionStatus.MANUAL_REVIEW.value,
                    final_grade=None,
                    uncertainty=None,
                    subgrades=tuple(subgrades),
                    algorithm_version=GRADING_ALGORITHM_VERSION,
                    baseline_ref=baseline.ref,
                )

            subgrades.append(sg)

        # 6. Grado final y banda (AC-G3/G4)
        final_grade = _compute_final_grade(subgrades)
        uncertainty = _compute_uncertainty(
            subgrades, baseline.is_calibrated, submission.image_quality_score
        )

        # 7. Coherencia interna: dispersión excesiva → revisión manual (AC-G8)
        dispersion = statistics.stdev([sg.score for sg in subgrades]) if len(subgrades) > 1 else 0.0
        if dispersion > UMBRAL_INCOHERENCIA:
            submission.status = SubmissionStatus.MANUAL_REVIEW
            self._submission_repo.save(submission)
            return GradeCardOutput(
                evaluation_id=uuid7(),
                submission_id=inp.submission_id,
                status=SubmissionStatus.MANUAL_REVIEW.value,
                final_grade=final_grade,
                uncertainty=uncertainty,
                subgrades=tuple(subgrades),
                algorithm_version=GRADING_ALGORITHM_VERSION,
                baseline_ref=baseline.ref,
            )

        # 8. Persistir evaluación inmutable (AC-G5) y marcar GRADED
        evaluation = CardEvaluation(
            id=uuid7(),
            submission_id=inp.submission_id,
            card_id=submission.card_id,
            subgrades=tuple(subgrades),
            final_grade=final_grade,
            uncertainty=uncertainty,
            algorithm_version=GRADING_ALGORITHM_VERSION,
            baseline_ref=baseline.ref,
            created_at=datetime.now(tz=timezone.utc),
        )
        saved_eval = self._evaluation_repo.save(evaluation)

        submission.status = SubmissionStatus.GRADED
        self._submission_repo.save(submission)

        return self._to_output(saved_eval, "graded")

    @staticmethod
    def _to_output(evaluation: CardEvaluation, status: str) -> GradeCardOutput:
        return GradeCardOutput(
            evaluation_id=evaluation.id,
            submission_id=evaluation.submission_id,
            status=status,
            final_grade=evaluation.final_grade,
            uncertainty=evaluation.uncertainty,
            subgrades=evaluation.subgrades,
            algorithm_version=evaluation.algorithm_version,
            baseline_ref=evaluation.baseline_ref,
        )
