from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from uuid_extensions import uuid7

from pokegrading.application.use_cases.authenticate_b2b_client import (
    AuthenticateB2BClientUseCase,
)
from pokegrading.domain.entities.api_key import ApiKey
from pokegrading.domain.entities.b2b_customer import B2BCustomer
from pokegrading.domain.exceptions import (
    ApiKeyExpiredError,
    ApiKeyRevokedError,
    ApiKeySuspendedError,
    B2BCustomerSuspendedError,
    InvalidApiKeyError,
)
from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus
from pokegrading.domain.value_objects.b2b_customer_status import B2BCustomerStatus
from pokegrading.infrastructure.security.api_key import (
    Sha256ApiKeyHasher,
    generate_api_key,
)

_NOW = datetime.now(tz=timezone.utc)
_HASHER = Sha256ApiKeyHasher("test-pepper")


class FakeApiKeyRepo:
    def __init__(self, keys: list[ApiKey]) -> None:
        self._by_prefix = {k.key_prefix: k for k in keys}
        self.touched: list = []

    def find_by_prefix(self, prefix):
        return self._by_prefix.get(prefix)

    def save(self, key):
        self._by_prefix[key.key_prefix] = key
        return key

    def touch_last_used(self, api_key_id, when):
        self.touched.append(api_key_id)


class FakeCustomerRepo:
    def __init__(self, customers: list[B2BCustomer]) -> None:
        self._by_id = {c.id: c for c in customers}

    def find_by_id(self, customer_id):
        return self._by_id.get(customer_id)

    def save(self, c):
        self._by_id[c.id] = c
        return c


def _build(
    *,
    key_status=ApiKeyStatus.ACTIVE,
    customer_status=B2BCustomerStatus.ACTIVE,
    expires_at=None,
    grace_until=None,
):
    full_key, prefix, secret = generate_api_key("live")
    customer = B2BCustomer(
        id=uuid7(), name="Tienda", status=customer_status, created_at=_NOW
    )
    api_key = ApiKey(
        id=uuid7(),
        customer_id=customer.id,
        key_prefix=prefix,
        hashed_secret=_HASHER.hash(secret),
        status=key_status,
        scopes="catalog:lookup",
        rate_limit_cards_per_window=1000,
        rate_limit_window_seconds=3600,
        created_at=_NOW,
        expires_at=expires_at,
        grace_period_until=grace_until,
    )
    uc = AuthenticateB2BClientUseCase(
        api_key_repo=FakeApiKeyRepo([api_key]),
        customer_repo=FakeCustomerRepo([customer]),
        hasher=_HASHER,
    )
    return uc, full_key, customer, api_key


def test_valid_key_returns_customer_and_key():
    uc, full_key, customer, api_key = _build()
    got_customer, got_key = uc.execute(full_key)
    assert got_customer.id == customer.id
    assert got_key.id == api_key.id


def test_wrong_secret_raises_invalid():
    uc, full_key, _, _ = _build()
    tampered = full_key[:-3] + "zzz"
    with pytest.raises(InvalidApiKeyError):
        uc.execute(tampered)


def test_unknown_prefix_raises_invalid():
    uc, _, _, _ = _build()
    with pytest.raises(InvalidApiKeyError):
        uc.execute("pkg_live_00000000_secretsecret")


@pytest.mark.parametrize("bad", ["", "garbage", "pkg_live_only", "abc_live_p_s"])
def test_malformed_key_raises_invalid(bad):
    uc, _, _, _ = _build()
    with pytest.raises(InvalidApiKeyError):
        uc.execute(bad)


def test_revoked_key_raises():
    uc, full_key, _, _ = _build(key_status=ApiKeyStatus.REVOKED)
    with pytest.raises(ApiKeyRevokedError):
        uc.execute(full_key)


def test_suspended_key_raises():
    uc, full_key, _, _ = _build(key_status=ApiKeyStatus.SUSPENDED)
    with pytest.raises(ApiKeySuspendedError):
        uc.execute(full_key)


def test_expired_key_without_grace_raises():
    uc, full_key, _, _ = _build(expires_at=_NOW - timedelta(hours=1))
    with pytest.raises(ApiKeyExpiredError):
        uc.execute(full_key)


def test_expired_key_within_grace_authenticates():
    uc, full_key, customer, _ = _build(
        expires_at=_NOW - timedelta(hours=1),
        grace_until=_NOW + timedelta(days=1),
    )
    got_customer, _ = uc.execute(full_key)
    assert got_customer.id == customer.id


def test_suspended_customer_raises():
    uc, full_key, _, _ = _build(customer_status=B2BCustomerStatus.SUSPENDED)
    with pytest.raises(B2BCustomerSuspendedError):
        uc.execute(full_key)


def test_valid_key_touches_last_used():
    uc, full_key, _, api_key = _build()
    uc.execute(full_key)
    assert uc._api_key_repo.touched == [api_key.id]  # type: ignore[attr-defined]
