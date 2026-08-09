from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pokegrading.domain.entities.api_key import ApiKey


@dataclass(frozen=True)
class RateLimitVerdict:
    """Resultado de evaluar el rate limit de una consulta B2B.

    `retry_after_seconds` solo es relevante cuando `allowed` es False.
    """

    allowed: bool
    retry_after_seconds: int = 0


class IRateLimiter(ABC):
    """Puerto de rate limiting del API B2B (US-005, AC-07).

    El límite se calcula sobre la CANTIDAD DE CARTAS consultadas, no sobre
    la cantidad de llamadas.
    """

    @abstractmethod
    def check_and_consume(self, api_key: ApiKey, cards: int) -> RateLimitVerdict:
        """Intenta consumir `cards` tokens para la llave dada.

        Si la operación cabe en la ventana actual, los consume y devuelve
        `allowed=True`. Si no, no consume nada y devuelve `allowed=False`
        con el tiempo de espera hasta la próxima ventana.
        """
        ...
