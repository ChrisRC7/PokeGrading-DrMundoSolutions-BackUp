from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from uuid_extensions import uuid7

from pokegrading.domain.entities.api_key import ApiKey
from pokegrading.domain.entities.b2b_customer import B2BCustomer
from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus
from pokegrading.domain.value_objects.b2b_customer_status import B2BCustomerStatus
from pokegrading.infrastructure.persistence.repositories.b2b.api_key_repository import (
    ApiKeyRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.b2b.customer_repository import (
    B2BCustomerRepositoryImpl,
)
from pokegrading.infrastructure.ratelimit.fixed_window_rate_limiter import (
    FixedWindowRateLimiter,
)


def _persist_key(db: Session, *, rate_cards: int) -> ApiKey:
    now = datetime.now(tz=timezone.utc)
    customer = B2BCustomerRepositoryImpl(db).save(
        B2BCustomer(id=uuid7(), name="T", status=B2BCustomerStatus.ACTIVE, created_at=now)
    )
    return ApiKeyRepositoryImpl(db).save(
        ApiKey(
            id=uuid7(),
            customer_id=customer.id,
            key_prefix=uuid.uuid4().hex[:8],
            hashed_secret="x",
            status=ApiKeyStatus.ACTIVE,
            scopes="catalog:lookup",
            rate_limit_cards_per_window=rate_cards,
            rate_limit_window_seconds=3600,
            created_at=now,
        )
    )


def test_counts_cards_and_blocks_over_limit(db: Session):
    api_key = _persist_key(db, rate_cards=3)
    limiter = FixedWindowRateLimiter(db)

    assert limiter.check_and_consume(api_key, 2).allowed  # 2/3

    blocked = limiter.check_and_consume(api_key, 2)  # 2+2=4 > 3
    assert not blocked.allowed
    assert blocked.retry_after_seconds >= 1

    assert limiter.check_and_consume(api_key, 1).allowed  # 2+1=3 cabe


def test_zero_cards_is_always_allowed(db: Session):
    api_key = _persist_key(db, rate_cards=1)
    limiter = FixedWindowRateLimiter(db)
    assert limiter.check_and_consume(api_key, 0).allowed
