from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from uuid_extensions import uuid7

from pokegrading.application.ports.rate_limiter import IRateLimiter, RateLimitVerdict
from pokegrading.domain.entities.api_key import ApiKey
from pokegrading.infrastructure.persistence.models import B2BRateLimitCounterORM


class FixedWindowRateLimiter(IRateLimiter):
    """Rate limiter de ventana fija sobre `b2b_rate_limit_counters` (US-005, AC-07).

    El límite se mide en CARTAS por ventana (no en llamadas). La ventana se
    alinea al epoch: ``window_start = floor(now / window) * window``.

    Es la implementación de desarrollo. En producción se reemplaza por Redis
    (`INCR` + `EXPIRE`) sin cambiar el puerto `IRateLimiter` (ver ADR-004 §4).
    Bajo alta concurrencia hay contención conocida en la fila del contador.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def check_and_consume(self, api_key: ApiKey, cards: int) -> RateLimitVerdict:
        if cards <= 0:
            return RateLimitVerdict(allowed=True)

        window_size = api_key.rate_limit_window_seconds
        limit = api_key.rate_limit_cards_per_window

        now_ts = int(datetime.now(tz=timezone.utc).timestamp())
        window_start_ts = (now_ts // window_size) * window_size
        window_start = datetime.fromtimestamp(window_start_ts, tz=timezone.utc)

        row = self._get_or_create_counter(api_key, window_start)

        if row.cards_consumed + cards > limit:
            retry_after = window_start_ts + window_size - now_ts
            return RateLimitVerdict(allowed=False, retry_after_seconds=max(retry_after, 1))

        row.cards_consumed += cards
        self._db.commit()
        return RateLimitVerdict(allowed=True)

    def _get_or_create_counter(
        self, api_key: ApiKey, window_start: datetime
    ) -> B2BRateLimitCounterORM:
        row = (
            self._db.query(B2BRateLimitCounterORM)
            .filter(
                B2BRateLimitCounterORM.api_key_id == api_key.id,
                B2BRateLimitCounterORM.window_start == window_start,
            )
            .first()
        )
        if row is not None:
            return row

        row = B2BRateLimitCounterORM(
            id=uuid7(),
            api_key_id=api_key.id,
            window_start=window_start,
            cards_consumed=0,
        )
        self._db.add(row)
        try:
            self._db.flush()
        except IntegrityError:
            # Otra request creó la misma ventana en paralelo: reusar la existente.
            self._db.rollback()
            row = (
                self._db.query(B2BRateLimitCounterORM)
                .filter(
                    B2BRateLimitCounterORM.api_key_id == api_key.id,
                    B2BRateLimitCounterORM.window_start == window_start,
                )
                .first()
            )
        return row
