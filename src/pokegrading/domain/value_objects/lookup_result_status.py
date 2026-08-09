from __future__ import annotations

from enum import Enum


class LookupResultStatus(str, Enum):
    """Estado del resultado de UNA carta dentro de una consulta B2B (US-005).

    Ver ADR-004 §2. La resolución de cada carta es independiente del resto
    del batch.
    - COVERED: exactamente una coincidencia activa en el catálogo.
    - MULTIPLE_MATCH: más de una coincidencia activa (la tienda debe desambiguar).
    - NOT_COVERED: ninguna coincidencia activa (incluye cartas retiradas).
    - INVALID_PARAMS: faltan requeridos u opcional fuera de listado canónico.
    """

    COVERED = "covered"
    MULTIPLE_MATCH = "multiple_match"
    NOT_COVERED = "not_covered"
    INVALID_PARAMS = "invalid_params"
