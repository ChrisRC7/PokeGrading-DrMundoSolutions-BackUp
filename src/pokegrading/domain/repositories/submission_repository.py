from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from pokegrading.domain.entities.submission import Submission


class ISubmissionRepository(ABC):
    @abstractmethod
    def save(self, submission: Submission) -> Submission: ...

    @abstractmethod
    def find_by_id(self, submission_id: UUID) -> Submission | None: ...

    @abstractmethod
    def find_by_user(self, user_id: UUID) -> list[Submission]: ...

    @abstractmethod
    def find_all(self) -> list[Submission]: ...
