from __future__ import annotations

from enum import Enum


class CardEdition(str, Enum):
    """Listado canónico de ediciones de impresión (US-005, opcional de identidad).

    Sirve para desambiguar variantes en el lookup B2B. Si una tienda envía
    una edición fuera de este listado, la carta se marca `invalid_params`.
    """

    FIRST_EDITION = "1st Edition"
    UNLIMITED = "Unlimited"
    SHADOWLESS = "Shadowless"
