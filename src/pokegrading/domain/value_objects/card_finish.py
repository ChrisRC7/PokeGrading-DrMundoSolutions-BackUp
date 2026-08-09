from __future__ import annotations

from enum import Enum


class CardFinish(str, Enum):
    """Listado canónico de acabados (US-005, opcional de identidad).

    Sirve para desambiguar variantes en el lookup B2B. Si una tienda envía
    un acabado fuera de este listado, la carta se marca `invalid_params`.
    """

    HOLO = "holo"
    REVERSE_HOLO = "reverse holo"
    NON_HOLO = "non-holo"
