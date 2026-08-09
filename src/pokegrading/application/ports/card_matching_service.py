from __future__ import annotations

from abc import ABC, abstractmethod


class ICardMatchingService(ABC):
    """Puerto para el motor de matching visual de cartas Pokémon TCG.

    Permite mockear en tests sin una implementación real de ML.

    En desarrollo: el stub retorna `""` (sin features extraíbles de la imagen).
    En producción: un modelo de visión artificial extrae el nombre, set y número
    de la carta a partir de la imagen, retornando una cadena de consulta.

    Pokémon TCG — campos identificadores relevantes para matching:
    ─────────────────────────────────────────────────────────────
    • name        — Nombre de la carta (igual en inglés y español para la mayoría:
                    "Pikachu", "Charizard V", "Mewtwo GX").
    • set_name    — Nombre del set: EN "Vivid Voltage" / ES puede usar el mismo.
    • card_number — Número impreso en la carta: "025/185".
    • language    — "en" (inglés) o "es" (español/Latam); algunos sets solo existen
                    en inglés, los sets latinoamericanos tienen texto en español.
    • Types (EN): Fire, Water, Grass, Lightning, Psychic, Fighting, Darkness,
                  Metal, Fairy, Dragon, Colorless.
      Types (ES): Fuego, Agua, Planta, Rayo, Psíquico, Lucha, Oscuridad, Metal,
                  Hada, Dragón, Incoloro.
    • Subtypes (EN): Basic, Stage 1, Stage 2, EX, GX, V, VMAX, VSTAR, Tera ex.
      Subtypes (ES): Básico, Fase 1, Fase 2 (+ special markers remain in English).
    """

    @abstractmethod
    def extract_features(self, image_data: bytes) -> str:
        """Extrae características de búsqueda de la imagen de una carta.

        Parameters
        ----------
        image_data:
            Bytes crudos de la imagen (JPEG o PNG) de la cara delantera.

        Returns
        -------
        Cadena de consulta derivada de la imagen (ej. "Pikachu" o "Pikachu 025/185"),
        o `""` si el motor no puede identificar la carta.
        """
        # El contrato devuelve texto de búsqueda, no objetos complejos, para que
        # el use case siga desacoplado del motor concreto de OCR / visión artificial.
        ...
