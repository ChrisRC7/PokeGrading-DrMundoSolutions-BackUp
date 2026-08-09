from __future__ import annotations

from pokegrading.application.ports.card_matching_service import ICardMatchingService


class StubCardMatchingService(ICardMatchingService):
    """Implementación stub del motor de matching visual — Sprint 2 (desarrollo).

    Siempre retorna ``""`` (sin features extraíbles de la imagen).

    **Cómo funciona el flujo de búsqueda en modo dev:**

    El router ``POST /search/quick`` aplica un fallback automático:
    si ``extract_features`` devuelve ``""`` Y no se envió el parámetro ``q``,
    el router extrae el stem del nombre del archivo de imagen y lo usa como
    ``query_hint``.  Esto simula lo que haría un OCR real en producción.

    Ejemplo::

        pikachu.jpg          → busca "pikachu"
        charizard_vmax.png   → busca "charizard vmax"
        Vivid_Voltage_025.jpg → busca "Vivid Voltage 025"
        IMG_20260531.jpg     → sin fallback (token puramente numérico)

    En producción esta clase será reemplazada por una implementación real que:
    1. Pasa la imagen por un modelo de visión artificial (OCR + clasificación).
    2. Extrae el nombre, número de carta y set del texto impreso en la carta.
    3. Retorna una cadena de consulta como "Pikachu 025/185".
    """

    def extract_features(self, image_data: bytes) -> str:
        """Retorna '' — el stub no extrae features de la imagen.

        Para búsquedas en modo desarrollo, usar el parámetro ``q`` en el endpoint
        ``POST /api/v3/search/quick``.
        """
        return ""
