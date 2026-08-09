from __future__ import annotations

from abc import ABC, abstractmethod


class IImageHashService(ABC):
    """Puerto para el hashing perceptual (pHash) de imágenes.

    Permite la búsqueda rápida comparando la imagen del usuario contra las
    imágenes de referencia del catálogo por similitud visual
    (ver Sprint3/DOC/busqueda-phash-ocr.md). La implementación concreta
    (imagehash + Pillow) vive en infraestructura.
    """

    @abstractmethod
    def compute_phash(self, image_data: bytes) -> str:
        """Devuelve el pHash como hex de 16 chars (64 bits).

        Retorna ``""`` si la imagen no se puede decodificar (no es una imagen
        válida), para que el caller pueda escalar a la búsqueda especializada.
        """

    @abstractmethod
    def hamming_distance(self, a: str, b: str) -> int:
        """Distancia de Hamming entre dos pHash en hex (nº de bits distintos)."""
