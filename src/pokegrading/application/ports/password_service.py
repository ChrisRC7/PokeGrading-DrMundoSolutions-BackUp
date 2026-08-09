from __future__ import annotations

from abc import ABC, abstractmethod


class IPasswordService(ABC):
    """Port for password hashing operations.

    Separates the domain/application from the concrete hashing library
    (bcrypt lives in infrastructure, not in the use case).
    """

    @abstractmethod
    def hash(self, plain_password: str) -> str:
        # El caso de uso nunca debe conocer el algoritmo de hash; solo pide un hash.
        ...

    @abstractmethod
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        # Igual de importante para login: la verificación se mantiene fuera del dominio.
        ...
