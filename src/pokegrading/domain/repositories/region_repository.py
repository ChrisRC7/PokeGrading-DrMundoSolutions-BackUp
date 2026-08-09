from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from pokegrading.domain.entities.preprocessed_card import RegionImage


class IRegionRepository(ABC):
    @abstractmethod
    def save(self, submission_id: UUID, regions: list[RegionImage]) -> None: ...

    @abstractmethod
    def find_by_submission(self, submission_id: UUID) -> list[RegionImage]: ...
