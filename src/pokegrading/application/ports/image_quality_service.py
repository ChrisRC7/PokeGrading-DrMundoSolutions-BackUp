from __future__ import annotations

from abc import ABC, abstractmethod


class IImageQualityService(ABC):
    """Puerto para evaluación de calidad de imagen.

    Permite mockear en tests sin implementación real de ML.
    La implementación de producción delegará a un modelo de visión artificial.
    """

    @abstractmethod
    def evaluate(self, image_data: bytes) -> float:
        """Evalúa la calidad de la imagen.

        Returns:
            Puntaje de 0.0 (inutilizable) a 1.0 (calidad perfecta).
        """
        # El resultado es un score normalizado para que el use case solo compare
        # contra un umbral, sin saber cómo se calculó internamente.
        ...
