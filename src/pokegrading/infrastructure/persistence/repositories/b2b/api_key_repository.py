from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from pokegrading.domain.entities.api_key import ApiKey
from pokegrading.domain.repositories.api_key_repository import IApiKeyRepository
from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus
from pokegrading.infrastructure.persistence.models import ApiKeyORM


class ApiKeyRepositoryImpl(IApiKeyRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def find_by_prefix(self, key_prefix: str) -> ApiKey | None:
        row = (
            self._db.query(ApiKeyORM)
            .filter(ApiKeyORM.key_prefix == key_prefix)
            .first()
        )
        return self._to_entity(row) if row else None

    def save(self, api_key: ApiKey) -> ApiKey:
        row = (
            self._db.query(ApiKeyORM).filter(ApiKeyORM.id == api_key.id).first()
        )
        if row is None:
            row = ApiKeyORM(
                id=api_key.id,
                customer_id=api_key.customer_id,
                key_prefix=api_key.key_prefix,
                hashed_secret=api_key.hashed_secret,
                status=api_key.status,
                scopes=api_key.scopes,
                rate_limit_cards_per_window=api_key.rate_limit_cards_per_window,
                rate_limit_window_seconds=api_key.rate_limit_window_seconds,
                created_at=api_key.created_at,
                expires_at=api_key.expires_at,
                grace_period_until=api_key.grace_period_until,
                revoked_at=api_key.revoked_at,
                last_used_at=api_key.last_used_at,
            )
            self._db.add(row)
        else:
            row.status = api_key.status
            row.scopes = api_key.scopes
            row.rate_limit_cards_per_window = api_key.rate_limit_cards_per_window
            row.rate_limit_window_seconds = api_key.rate_limit_window_seconds
            row.expires_at = api_key.expires_at
            row.grace_period_until = api_key.grace_period_until
            row.revoked_at = api_key.revoked_at
            row.last_used_at = api_key.last_used_at
        self._db.commit()
        self._db.refresh(row)
        return self._to_entity(row)

    def touch_last_used(self, api_key_id: UUID, when: datetime) -> None:
        row = self._db.query(ApiKeyORM).filter(ApiKeyORM.id == api_key_id).first()
        if row is not None:
            row.last_used_at = when
            self._db.commit()

    @staticmethod
    def _to_entity(row: ApiKeyORM) -> ApiKey:
        return ApiKey(
            id=row.id,
            customer_id=row.customer_id,
            key_prefix=row.key_prefix,
            hashed_secret=row.hashed_secret,
            status=ApiKeyStatus(row.status)
            if isinstance(row.status, str)
            else row.status,
            scopes=row.scopes,
            rate_limit_cards_per_window=row.rate_limit_cards_per_window,
            rate_limit_window_seconds=row.rate_limit_window_seconds,
            created_at=row.created_at,
            expires_at=row.expires_at,
            grace_period_until=row.grace_period_until,
            revoked_at=row.revoked_at,
            last_used_at=row.last_used_at,
        )
