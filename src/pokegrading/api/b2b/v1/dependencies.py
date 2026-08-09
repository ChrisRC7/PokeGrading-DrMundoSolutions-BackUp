from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from pokegrading.application.use_cases.authenticate_b2b_client import (
    AuthenticateB2BClientUseCase,
)
from pokegrading.config import get_settings
from pokegrading.domain.entities.api_key import ApiKey
from pokegrading.domain.entities.b2b_customer import B2BCustomer
from pokegrading.domain.exceptions import InvalidApiKeyError
from pokegrading.infrastructure.persistence.database import get_db
from pokegrading.infrastructure.persistence.repositories.b2b.api_key_repository import (
    ApiKeyRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.b2b.customer_repository import (
    B2BCustomerRepositoryImpl,
)
from pokegrading.infrastructure.security.api_key import Sha256ApiKeyHasher


@dataclass(frozen=True)
class B2BClient:
    """Cliente B2B autenticado: el customer y la llave con la que entró."""

    customer: B2BCustomer
    api_key: ApiKey


def get_current_b2b_client(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> B2BClient:
    """Autentica la API key del header `X-API-Key`.

    Cualquier fallo de autenticación lanza una excepción B2B que el handler
    global convierte al formato de error único (rechazo total, AC-10).
    """
    if not x_api_key:
        raise InvalidApiKeyError()

    settings = get_settings()
    use_case = AuthenticateB2BClientUseCase(
        api_key_repo=ApiKeyRepositoryImpl(db),
        customer_repo=B2BCustomerRepositoryImpl(db),
        hasher=Sha256ApiKeyHasher(settings.b2b_api_key_pepper),
    )
    customer, api_key = use_case.execute(x_api_key)
    return B2BClient(customer=customer, api_key=api_key)
