from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pokegrading.application.ports.card_preprocessing_service import ICardPreprocessingService
from pokegrading.application.ports.image_hash_service import IImageHashService
from pokegrading.domain.entities.preprocessed_card import RegionImage
from pokegrading.domain.exceptions import SubmissionNotFoundError
from pokegrading.domain.repositories.region_repository import IRegionRepository
from pokegrading.domain.repositories.submission_repository import ISubmissionRepository
from pokegrading.domain.value_objects.preprocessing_status import PreprocessingStatus
from pokegrading.domain.value_objects.submission_status import SubmissionStatus


@dataclass(frozen=True)
class PreprocessCardInput:
    submission_id: UUID


@dataclass(frozen=True)
class PreprocessCardOutput:
    submission_id: UUID
    status: str           # "preprocessed" | "manual_review" | "needs_recapture"
    regions_ready: bool   # True solo si status == preprocessed
    reason: str | None


class PreprocessCardUseCase:
    """US Sprint-4: Normaliza la imagen de un envío y extrae las 4 regiones de grading.

    Flujo:
    1. Cargar submission → 404 si no existe
    2. Marcar PROCESSING
    3. preprocessing_svc.preprocess(image_front_data)
    4. Ramificar por outcome.status:
       OK        → guardar 4 RegionImage con pHash, Submission=PREPROCESSED (AC-P3)
       MANUAL    → Submission=MANUAL_REVIEW (AC-P4)
       RECAPTURE → Submission=NEEDS_RECAPTURE (AC-P5)
    """

    def __init__(
        self,
        submission_repo: ISubmissionRepository,
        region_repo: IRegionRepository,
        preprocessing_svc: ICardPreprocessingService,
        hash_svc: IImageHashService,
    ) -> None:
        self._submission_repo = submission_repo
        self._region_repo = region_repo
        self._preprocessing_svc = preprocessing_svc
        self._hash_svc = hash_svc

    def execute(self, inp: PreprocessCardInput) -> PreprocessCardOutput:
        submission = self._submission_repo.find_by_id(inp.submission_id)
        if submission is None:
            raise SubmissionNotFoundError(inp.submission_id)

        # Marcar PROCESSING antes de ejecutar el pipeline para que relecturas
        # concurrentes no vean el submission en PENDING mientras procesa.
        submission.status = SubmissionStatus.PROCESSING
        self._submission_repo.save(submission)

        outcome = self._preprocessing_svc.preprocess(submission.image_front_data)

        if outcome.status == PreprocessingStatus.OK:
            assert outcome.card is not None  # garantizado por el contrato del puerto

            # Recompute pHash por región para garantizar que el hash que se persiste
            # corresponde al recorte normalizado, no a la imagen original.
            regions_with_phash: list[RegionImage] = []
            for region_img in outcome.card.regions:
                phash = self._hash_svc.compute_phash(region_img.data)
                regions_with_phash.append(
                    RegionImage(
                        region=region_img.region,
                        data=region_img.data,
                        phash=phash,
                    )
                )

            self._region_repo.save(inp.submission_id, regions_with_phash)

            submission.status = SubmissionStatus.PREPROCESSED
            self._submission_repo.save(submission)

            return PreprocessCardOutput(
                submission_id=inp.submission_id,
                status=SubmissionStatus.PREPROCESSED.value,
                regions_ready=True,
                reason=None,
            )

        if outcome.status == PreprocessingStatus.MANUAL:
            submission.status = SubmissionStatus.MANUAL_REVIEW
            self._submission_repo.save(submission)
            return PreprocessCardOutput(
                submission_id=inp.submission_id,
                status=SubmissionStatus.MANUAL_REVIEW.value,
                regions_ready=False,
                reason=outcome.reason,
            )

        # RECAPTURE
        submission.status = SubmissionStatus.NEEDS_RECAPTURE
        self._submission_repo.save(submission)
        return PreprocessCardOutput(
            submission_id=inp.submission_id,
            status=SubmissionStatus.NEEDS_RECAPTURE.value,
            regions_ready=False,
            reason=outcome.reason,
        )
