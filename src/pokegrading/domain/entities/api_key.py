from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus


@dataclass
class ApiKey:
    """API key B2B.

    Estructura: ``pkg_<env>_<key_prefix>_<secret>`` (ver
    Sprint3/DOC/diseno-versionamiento-seguridad-api.md §2).

    - ``key_prefix`` es público e indexado: localiza la llave en O(1).
    - ``hashed_secret`` es el HMAC-SHA256 del secreto; el secreto en claro
      nunca se almacena.

    Las predicados de tiempo (`is_expired`, `is_in_grace`) ayudan al
    caso de uso de autenticación a decidir, pero el lanzamiento de
    excepciones vive en `AuthenticateB2BClientUseCase`.
    """

    id: UUID
    customer_id: UUID
    key_prefix: str
    hashed_secret: str
    status: ApiKeyStatus
    scopes: str
    rate_limit_cards_per_window: int
    rate_limit_window_seconds: int
    created_at: datetime
    expires_at: datetime | None = None
    grace_period_until: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at

    def is_in_grace(self, now: datetime) -> bool:
        return self.grace_period_until is not None and now < self.grace_period_until

    def has_scope(self, scope: str) -> bool:
        return scope in {s.strip() for s in self.scopes.split(",") if s.strip()}
