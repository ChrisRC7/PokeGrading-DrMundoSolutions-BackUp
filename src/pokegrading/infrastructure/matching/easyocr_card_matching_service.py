from __future__ import annotations

import io
import logging
from typing import ClassVar

import numpy as np
from PIL import Image

from pokegrading.application.ports.card_matching_service import ICardMatchingService

logger = logging.getLogger(__name__)

# Tokens de ruido frecuente en cartas Pokémon TCG que no aportan a la búsqueda
# Estos tokens aparecen con mucha frecuencia en el texto OCR, pero no ayudan a
# distinguir una carta concreta. Se filtran solo en extract_features();
# extract_tokens_raw() los conserva para parsing estructurado (HP, número, nombre).
_STOPWORDS: frozenset[str] = frozenset({
    "hp", "the", "a", "of", "in", "on", "at", "to", "stage",
    "basic", "level", "put", "lv", "no",
})


class EasyOCRCardMatchingService(ICardMatchingService):
    """Extrae el texto visible en la imagen de una carta mediante EasyOCR (CPU, inglés).

    El lector se inicializa de forma diferida la primera vez que se necesita
    (lazy class-level singleton) para no penalizar el tiempo de arranque del servidor.

    Pokémon TCG — texto identificador esperado en la imagen:
    ─────────────────────────────────────────────────────────
    • Nombre (parte superior): "Pikachu", "Charizard V", "Mewtwo VMAX"
    • HP (parte superior derecha): "120 HP"
    • Número de carta (esquina inferior derecha): "025/185"
    • Nombre del set (parte inferior): "Vivid Voltage"

    La query resultante combina los tokens más informativos para que
    ``ICardRepository.find_top_candidates`` pueda localizar la carta.
    """

    # Singleton de proceso: EasyOCR carga pesos grandes y no conviene instanciarlo por request.
    _reader: ClassVar[object | None] = None  # easyocr.Reader — tipo diferido

    @classmethod
    def _get_reader(cls) -> object:
        """Carga el modelo EasyOCR una sola vez (singleton de clase).

        El import se hace aquí y no arriba para evitar que el arranque del servicio
        pague el costo de importar torch/easyocr aunque nunca se use OCR.
        """
        if cls._reader is None:
            import easyocr  # importación diferida: torch tarda varios segundos al importar
            logger.info("EasyOCR: cargando modelo (primera petición)…")
            cls._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            logger.info("EasyOCR: modelo cargado.")
        return cls._reader

    def extract_tokens_raw(self, image_data: bytes) -> list[str]:
        """Devuelve todos los tokens OCR sin filtrar stopwords.

        Útil para parsear campos estructurados (HP, número de carta, nombre).
        """
        # Esta variante conserva todo el texto porque el router la usa para extraer
        # campos estructurados antes de construir la query enfocada.
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            arr = np.array(img)
        except Exception as exc:
            logger.debug("EasyOCR (raw): no se pudo decodificar la imagen: %s", exc)
            return []
        try:
            # detail=0 devuelve solo strings; paragraph=False evita agrupar bloques grandes.
            return self._get_reader().readtext(arr, detail=0, paragraph=False)  # type: ignore[union-attr]
        except Exception as exc:
            logger.debug("EasyOCR (raw): error al leer texto: %s", exc)
            return []

    def extract_features(self, image_data: bytes) -> str:
        """Devuelve el texto legible de la imagen como query de búsqueda.

        Retorna ``""`` si la imagen no contiene texto reconocible, no es válida,
        o si EasyOCR lanza una excepción inesperada.
        """
        # 1. Decodificar imagen.
        # Si Pillow no puede abrirla, no tiene sentido seguir: el flujo de negocio
        # interpreta eso como una imagen no identificable y no como un fallo técnico.
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            arr = np.array(img)
        except Exception as exc:
            logger.debug("EasyOCR: no se pudo decodificar la imagen: %s", exc)
            return ""

        # 2. Leer texto con el singleton OCR.
        # Aquí se usa la misma ruta que en extract_tokens_raw(), pero orientada a
        # construir una query compacta para matching cuando no hay parsing externo.
        try:
            results: list[str] = self._get_reader().readtext(  # type: ignore[union-attr]
                arr, detail=0, paragraph=False
            )
        except Exception as exc:
            logger.debug("EasyOCR: error al leer texto de la imagen: %s", exc)
            return ""

        # 3. Filtrar stopwords y tokens vacíos.
        # El objetivo no es reconstruir todo el texto de la carta, sino quedarse con
        # las piezas que ayudan a localizarla en el catálogo. El texto de ataques,
        # reglas o frases descriptivas solo mete ruido.
        tokens = [
            t.strip()
            for t in results
            if t.strip() and t.strip().lower() not in _STOPWORDS
        ]

        # La query final se entrega como string simple para que la capa de repositorio
        # pueda hacer búsqueda flexible por similitud sin depender de la estructura OCR.
        query = " ".join(tokens)
        logger.debug("EasyOCR: texto extraído → %r", query)
        return query
