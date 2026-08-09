from __future__ import annotations

from abc import ABC, abstractmethod


class IApiKeyHasher(ABC):
    """Puerto para hashear/verificar el secreto de una API key B2B.

    A diferencia de las contraseñas (bcrypt), el secreto de una API key es
    de alta entropía, por lo que la implementación usa HMAC-SHA256 con un
    pepper (ver Sprint3/DOC/diseno-versionamiento-seguridad-api.md §4).
    """

    @abstractmethod
    def hash(self, secret: str) -> str:
        ...

    @abstractmethod
    def verify(self, secret: str, hashed: str) -> bool:
        """Comparación en tiempo constante (evita timing attacks)."""
        ...
