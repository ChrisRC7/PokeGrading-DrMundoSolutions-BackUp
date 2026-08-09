from __future__ import annotations

from abc import ABC, abstractmethod

from pokegrading.domain.entities.preprocessed_card import PreprocessOutcome


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
