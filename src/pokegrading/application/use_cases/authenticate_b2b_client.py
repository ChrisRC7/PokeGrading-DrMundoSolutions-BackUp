from __future__ import annotations

from datetime import datetime, timezone

from pokegrading.application.ports.api_key_hasher import IApiKeyHasher
from pokegrading.domain.entities.api_key import ApiKey
from pokegrading.domain.entities.b2b_customer import B2BCustomer
from pokegrading.domain.exceptions import (
    ApiKeyExpiredError,
    ApiKeyRevokedError,
    ApiKeySuspendedError,
    B2BCustomerSuspendedError,
    InvalidApiKeyError,
)
from pokegrading.domain.repositories.api_key_repository import IApiKeyRepository
from pokegrading.domain.repositories.b2b_customer_repository import (
    IB2BCustomerRepository,
)
from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus

# Ambientes válidos en el prefijo de la llave: pkg_<env>_<prefix>_<secret>
_VALID_ENVIRONMENTS = ("live", "test")


class AuthenticateB2BClientUseCase:
    """Autentica una API key B2B y resuelve su Customer (US-005).

    Orden de verificación (Sprint3/DOC/diseno-versionamiento-seguridad-api.md §3):
    1. Formato de la llave.
    2. Validez criptográfica del secreto (verify).
    3. Estado de la llave (revoked / suspended / expired+gracia).
    4. Estado del customer.

    Así un atacante con un prefix válido pero secreto incorrecto nunca
    distingue entre "llave revocada" y "secreto incorrecto" (ambos →
    INVALID_API_KEY).
    """

    def __init__(
        self,
        api_key_repo: IApiKeyRepository,
        customer_repo: IB2BCustomerRepository,
        hasher: IApiKeyHasher,
    ) -> None:
        self._api_key_repo = api_key_repo
        self._customer_repo = customer_repo
        self._hasher = hasher

    def execute(self, raw_key: str) -> tuple[B2BCustomer, ApiKey]:
        now = datetime.now(tz=timezone.utc)

        prefix, secret = self._parse(raw_key)

        api_key = self._api_key_repo.find_by_prefix(prefix)
        if api_key is None or not self._hasher.verify(secret, api_key.hashed_secret):
            raise InvalidApiKeyError()

        self._assert_key_usable(api_key, now)

        customer = self._customer_repo.find_by_id(api_key.customer_id)
        if customer is None:
            raise InvalidApiKeyError()
        if not customer.is_active():
            raise B2BCustomerSuspendedError()

        self._api_key_repo.touch_last_used(api_key.id, now)
        return customer, api_key

    @staticmethod
    def _parse(raw_key: str) -> tuple[str, str]:
        """Extrae (prefix, secret) de ``pkg_<env>_<prefix>_<secret>``.

        Se separa en máximo 4 segmentos: el secreto (último) puede contener
        guiones bajos (alfabeto url-safe), por lo que se conserva íntegro.
        """
        if not raw_key:
            raise InvalidApiKeyError()
        parts = raw_key.split("_", 3)
        if (
            len(parts) != 4
            or parts[0] != "pkg"
            or parts[1] not in _VALID_ENVIRONMENTS
            or not parts[2]
            or not parts[3]
        ):
            raise InvalidApiKeyError()
        return parts[2], parts[3]

    @staticmethod
    def _assert_key_usable(api_key: ApiKey, now: datetime) -> None:
        if api_key.status == ApiKeyStatus.REVOKED:
            raise ApiKeyRevokedError()
        if api_key.status == ApiKeyStatus.SUSPENDED:
            raise ApiKeySuspendedError()
        # Caducidad: una llave expirada solo autentica si está en periodo de gracia.
        if api_key.status == ApiKeyStatus.EXPIRED or api_key.is_expired(now):
            if not api_key.is_in_grace(now):
                raise ApiKeyExpiredError()
