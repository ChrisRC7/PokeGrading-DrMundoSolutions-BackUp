from __future__ import annotations

from abc import ABC, abstractmethod

from pokegrading.domain.entities.grading_baseline import GradingBaseline


class IGradingBaselineRepository(ABC):
    @abstractmethod
    def get_for(self, set_name: str, finish: str) -> GradingBaseline:
        """Devuelve el baseline calibrado de (set_name, finish) si tiene
        ground truth suficiente; si no, el baseline GLOBAL.
        Nunca devuelve None: el baseline global siempre existe (sembrado)."""
