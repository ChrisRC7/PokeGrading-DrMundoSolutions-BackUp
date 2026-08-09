from __future__ import annotations

from enum import Enum


class ApiKeyStatus(str, Enum):
    """Ciclo de vida de una API key B2B.

    Ver Sprint3/DOC/diseno-versionamiento-seguridad-api.md §5.
    - ACTIVE: opera normalmente.
    - SUSPENDED: pausa temporal reversible (impago, investigación).
    - REVOKED: revocada de forma inmediata e irreversible (compromiso/fuga).
    - EXPIRED: caducidad natural (fuera del periodo de gracia).
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"
