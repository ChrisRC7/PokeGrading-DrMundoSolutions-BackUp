from __future__ import annotations

import hashlib
import hmac
import secrets

from pokegrading.application.ports.api_key_hasher import IApiKeyHasher

# Prefijo de producto y longitudes (ver diseno-versionamiento-seguridad-api.md §2)
_PRODUCT_PREFIX = "pkg"
_PREFIX_BYTES = 4   # token_hex(4) → 8 chars hex
_SECRET_BYTES = 24  # token_urlsafe(24) → ~32 chars url-safe


class Sha256ApiKeyHasher(IApiKeyHasher):
    """Hashing de secretos de API key con HMAC-SHA256 + pepper.

    No se usa bcrypt: el secreto es de alta entropía y se verifica en cada
    request, por lo que un hash lento sería un cuello de botella. El pepper
    vive fuera de la BD (variable de entorno / Key Vault); si la tabla
    `api_keys` se filtra, los hashes no son crackeables sin él.
    """

    def __init__(self, pepper: str) -> None:
        self._pepper = pepper.encode()

    def hash(self, secret: str) -> str:
        return hmac.new(self._pepper, secret.encode(), hashlib.sha256).hexdigest()

    def verify(self, secret: str, hashed: str) -> bool:
        return hmac.compare_digest(self.hash(secret), hashed)  # tiempo constante


def generate_api_key(environment: str = "live") -> tuple[str, str, str]:
    """Genera una nueva API key.

    Devuelve ``(full_key, key_prefix, secret)``:
    - ``full_key``: ``pkg_<env>_<prefix>_<secret>`` (se entrega a la tienda una vez).
    - ``key_prefix``: identificador público a almacenar en `api_keys.key_prefix`.
    - ``secret``: a hashear con `Sha256ApiKeyHasher.hash` (nunca se persiste en claro).
    """
    if environment not in ("live", "test"):
        raise ValueError("environment debe ser 'live' o 'test'")
    key_prefix = secrets.token_hex(_PREFIX_BYTES)
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    full_key = f"{_PRODUCT_PREFIX}_{environment}_{key_prefix}_{secret}"
    return full_key, key_prefix, secret
