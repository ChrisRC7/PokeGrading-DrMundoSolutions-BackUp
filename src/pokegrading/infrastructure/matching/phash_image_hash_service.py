from __future__ import annotations

import io
import logging

from pokegrading.application.ports.image_hash_service import IImageHashService

logger = logging.getLogger(__name__)


class PHashImageHashService(IImageHashService):
    """pHash perceptual con la librería ``imagehash`` + Pillow (CPU, sin modelo).

    El pHash de 64 bits se representa como 16 caracteres hexadecimales. Dos
    imágenes visualmente similares producen hashes con distancia de Hamming
    baja, tolerando cambios de escala, compresión e iluminación leve.
    """

    def compute_phash(self, image_data: bytes) -> str:
        try:
            import imagehash
            from PIL import Image

            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            return str(imagehash.phash(img))
        except Exception as exc:
            logger.debug("pHash: no se pudo procesar la imagen: %s", exc)
            return ""

    def hamming_distance(self, a: str, b: str) -> int:
        import imagehash

        return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


class StubImageHashService(IImageHashService):
    """Stub determinista para tests: pHash = primeros 16 hex del sha256.

    No mide similitud visual real (la distancia de Hamming entre imágenes
    distintas será alta), pero permite probar el flujo sin dependencias
    pesadas: dos veces la misma imagen → mismo pHash → distancia 0.
    """

    def compute_phash(self, image_data: bytes) -> str:
        import hashlib

        if not image_data:
            return ""
        return hashlib.sha256(image_data).hexdigest()[:16]

    def hamming_distance(self, a: str, b: str) -> int:
        x = int(a, 16) ^ int(b, 16)
        return bin(x).count("1")
