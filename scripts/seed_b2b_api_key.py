"""Siembra un Customer B2B y una API key (US-005).

Sprint 3 NO incluye aprovisionamiento self-service, pero las llaves deben
existir para que la autenticación funcione. Este script es la única vía de
creación de llaves en este sprint
(ver Sprint3/DOC/diseno-versionamiento-seguridad-api.md §6).

Uso:
    python scripts/seed_b2b_api_key.py --customer "Tienda Demo" --env live

Imprime la API key EN CLARO una sola vez: la BD solo guarda su hash. Entregue
la llave a la tienda por un canal seguro; no se puede recuperar después.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from uuid_extensions import uuid7

from pokegrading.config import get_settings
from pokegrading.domain.entities.api_key import ApiKey
from pokegrading.domain.entities.b2b_customer import B2BCustomer
from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus
from pokegrading.domain.value_objects.b2b_customer_status import B2BCustomerStatus
from pokegrading.infrastructure.persistence.database import SessionLocal
from pokegrading.infrastructure.persistence.repositories.b2b.api_key_repository import (
    ApiKeyRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.b2b.customer_repository import (
    B2BCustomerRepositoryImpl,
)
from pokegrading.infrastructure.security.api_key import (
    Sha256ApiKeyHasher,
    generate_api_key,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Siembra un Customer B2B + API key.")
    parser.add_argument("--customer", default="Tienda Demo", help="Nombre del Customer B2B")
    parser.add_argument("--env", default="live", choices=["live", "test"], help="Ambiente de la llave")
    parser.add_argument(
        "--rate-cards", type=int, default=1000, help="Límite de cartas por ventana"
    )
    parser.add_argument(
        "--rate-window", type=int, default=3600, help="Tamaño de ventana en segundos"
    )
    args = parser.parse_args()

    settings = get_settings()
    hasher = Sha256ApiKeyHasher(settings.b2b_api_key_pepper)
    now = datetime.now(tz=timezone.utc)

    db = SessionLocal()
    try:
        customer = B2BCustomerRepositoryImpl(db).save(
            B2BCustomer(
                id=uuid7(),
                name=args.customer,
                status=B2BCustomerStatus.ACTIVE,
                created_at=now,
            )
        )

        full_key, key_prefix, secret = generate_api_key(args.env)
        ApiKeyRepositoryImpl(db).save(
            ApiKey(
                id=uuid7(),
                customer_id=customer.id,
                key_prefix=key_prefix,
                hashed_secret=hasher.hash(secret),
                status=ApiKeyStatus.ACTIVE,
                scopes="catalog:lookup",
                rate_limit_cards_per_window=args.rate_cards,
                rate_limit_window_seconds=args.rate_window,
                created_at=now,
            )
        )
    finally:
        db.close()

    print("=" * 60)
    print("Customer B2B y API key creados.")
    print(f"  Customer : {args.customer} ({customer.id})")
    print(f"  Prefix   : {key_prefix}")
    print("  API KEY  (guárdela ahora; no se puede recuperar):")
    print(f"    {full_key}")
    print("=" * 60)


if __name__ == "__main__":
    main()
