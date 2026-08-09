from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from pokegrading.application.ports.rate_limiter import IRateLimiter
from pokegrading.domain.entities.api_key import ApiKey
from pokegrading.domain.entities.b2b_customer import B2BCustomer
from pokegrading.domain.entities.card import Card
from pokegrading.domain.entities.card_lookup import (
    CardLookupItem,
    CardLookupResult,
    InvalidReason,
)
from pokegrading.domain.exceptions import (
    EmptyLookupQueryError,
    IdempotencyKeyReuseError,
    MalformedLookupQueryError,
    RateLimitExceededError,
)
from pokegrading.domain.repositories.b2b_audit_repository import (
    IB2BAuditRepository,
    LookupAuditRecord,
)
from pokegrading.domain.repositories.b2b_idempotency_repository import (
    IdempotencyRecord,
    IIdempotencyRepository,
)
from pokegrading.domain.repositories.card_repository import ICardRepository
from pokegrading.domain.value_objects.card_edition import CardEdition
from pokegrading.domain.value_objects.card_finish import CardFinish
from pokegrading.domain.value_objects.language import SupportedLanguage
from pokegrading.domain.value_objects.lookup_result_status import LookupResultStatus

# ── DTOs de salida (serializables: alimentan la respuesta y la idempotencia) ───


@dataclass
class OfficialIdentity:
    """Identidad oficial de catálogo devuelta por el lookup (solo metadata)."""

    card_id: str
    set_name: str
    card_number: str
    edition: str
    language: str
    finish: str


@dataclass
class LookupItemOutput:
    index: int
    status: str
    query: dict
    card: OfficialIdentity | None = None
    candidates: list[OfficialIdentity] | None = None
    reason: dict | None = None


@dataclass
class LookupResponse:
    request_id: str | None
    etag: str
    summary: dict
    results: list[LookupItemOutput] = field(default_factory=list)
    not_modified: bool = False


class LookupCatalogCoverageUseCase:
    """US-005 — Consultar cobertura de catálogo por API B2B.

    Orquesta (ver ADR-004):
    - idempotencia por `request_id` dentro de una ventana,
    - validación condicional por ETag (`If-None-Match` → not_modified/304),
    - rate limit por cantidad de cartas,
    - resolución independiente de cada carta (covered / multiple_match /
      not_covered / invalid_params),
    - auditoría de la consulta.

    Es de solo lectura: nunca descuenta cuota de evaluación ni dispara grading.
    """

    def __init__(
        self,
        card_repo: ICardRepository,
        rate_limiter: IRateLimiter,
        audit_repo: IB2BAuditRepository,
        idempotency_repo: IIdempotencyRepository,
        *,
        idempotency_window_hours: int = 24,
        max_cards: int = 100,
    ) -> None:
        self._card_repo = card_repo
        self._rate_limiter = rate_limiter
        self._audit_repo = audit_repo
        self._idempotency_repo = idempotency_repo
        self._idempotency_window_hours = idempotency_window_hours
        self._max_cards = max_cards

    def execute(
        self,
        *,
        customer: B2BCustomer,
        api_key: ApiKey,
        items: list[CardLookupItem],
        trace_id: str,
        request_id: str | None = None,
        if_none_match: str | None = None,
    ) -> LookupResponse:
        now = datetime.now(tz=timezone.utc)

        if not items:
            raise EmptyLookupQueryError()
        if len(items) > self._max_cards:
            raise MalformedLookupQueryError(
                f"La consulta excede el máximo de {self._max_cards} cartas.",
                field="cards",
            )

        request_hash = self._hash_items(items)

        # 1) Idempotencia: un reintento dentro de la ventana devuelve la misma
        #    respuesta sin recontar rate limit ni reauditar (AC-08).
        if request_id:
            window_start = now - timedelta(hours=self._idempotency_window_hours)
            existing = self._idempotency_repo.find_within_window(
                api_key.id, request_id, window_start
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise IdempotencyKeyReuseError()
                return _response_from_json(existing.response_json)

        # 2) Validación condicional: si el catálogo no cambió → not_modified (304).
        etag = self._card_repo.get_catalog_fingerprint()
        if if_none_match is not None and self._etags_match(if_none_match, etag):
            return LookupResponse(
                request_id=request_id, etag=etag, summary={}, not_modified=True
            )

        # 3) Rate limit por cantidad de cartas (AC-07).
        verdict = self._rate_limiter.check_and_consume(api_key, len(items))
        if not verdict.allowed:
            raise RateLimitExceededError(verdict.retry_after_seconds)

        # 4) Resolver cada carta de forma independiente (AC-05).
        results = [self._resolve(i, item) for i, item in enumerate(items)]
        summary = self._summarize(results)
        response = LookupResponse(
            request_id=request_id,
            etag=etag,
            summary=summary,
            results=[self._to_output(r) for r in results],
        )

        # 5) Auditoría (AC-15) + persistir respuesta idempotente.
        self._audit_repo.record_lookup(
            LookupAuditRecord(
                api_key_id=api_key.id,
                customer_id=customer.id,
                trace_id=trace_id,
                card_count=len(items),
                covered=summary["covered"],
                multiple=summary["multiple_match"],
                not_covered=summary["not_covered"],
                invalid=summary["invalid_params"],
                request_id=request_id,
            )
        )
        if request_id:
            self._idempotency_repo.save(
                IdempotencyRecord(
                    api_key_id=api_key.id,
                    request_id=request_id,
                    request_hash=request_hash,
                    response_json=_response_to_json(response),
                )
            )

        return response

    # ── Resolución por carta ──────────────────────────────────────────────────

    def _resolve(self, index: int, item: CardLookupItem) -> CardLookupResult:
        set_name = (item.set_name or "").strip()
        number = (item.card_number or "").strip()

        if not set_name:
            return self._invalid(
                index, item, "MISSING_REQUIRED_FIELD", "set",
                "El campo 'set' es obligatorio.",
            )
        if not number:
            return self._invalid(
                index, item, "MISSING_REQUIRED_FIELD", "number",
                "El campo 'number' es obligatorio.",
            )

        edition, err = self._canonical(item.edition, CardEdition, "edition")
        if err:
            return self._invalid(index, item, *err)
        language, err = self._canonical(item.language, SupportedLanguage, "language")
        if err:
            return self._invalid(index, item, *err)
        finish, err = self._canonical(item.finish, CardFinish, "finish")
        if err:
            return self._invalid(index, item, *err)

        matches = self._card_repo.find_active_by_partial_identity(
            set_name, number, edition, language, finish
        )
        if not matches:
            return CardLookupResult(index, LookupResultStatus.NOT_COVERED, item)
        if len(matches) == 1:
            return CardLookupResult(
                index, LookupResultStatus.COVERED, item, matches=matches
            )
        return CardLookupResult(
            index, LookupResultStatus.MULTIPLE_MATCH, item, matches=matches
        )

    @staticmethod
    def _canonical(
        value: str | None, enum_cls: type, field_name: str
    ) -> tuple[str | None, tuple[str, str, str] | None]:
        """Valida un opcional contra su listado canónico (case-insensitive).

        Devuelve (valor_canónico, None) si es válido o no se proveyó, o
        (None, (code, field, message)) si está fuera del listado.
        """
        if value is None:
            return None, None
        v = value.strip()
        if not v:
            return None, None
        for member in enum_cls:
            if member.value.lower() == v.lower():
                return member.value, None
        return None, (
            "NON_CANONICAL_VALUE",
            field_name,
            f"El valor '{v}' del campo '{field_name}' no pertenece al listado canónico.",
        )

    @staticmethod
    def _invalid(
        index: int, item: CardLookupItem, code: str, field_name: str, message: str
    ) -> CardLookupResult:
        return CardLookupResult(
            index,
            LookupResultStatus.INVALID_PARAMS,
            item,
            reason=InvalidReason(code=code, field=field_name, message=message),
        )

    # ── Construcción de la respuesta ──────────────────────────────────────────

    def _to_output(self, r: CardLookupResult) -> LookupItemOutput:
        query = self._query_echo(r.query)
        if r.status == LookupResultStatus.INVALID_PARAMS and r.reason is not None:
            return LookupItemOutput(
                r.index,
                r.status.value,
                query,
                reason={
                    "code": r.reason.code,
                    "field": r.reason.field,
                    "message": r.reason.message,
                },
            )
        if r.status == LookupResultStatus.COVERED:
            return LookupItemOutput(
                r.index, r.status.value, query, card=self._official(r.matches[0])
            )
        if r.status == LookupResultStatus.MULTIPLE_MATCH:
            return LookupItemOutput(
                r.index,
                r.status.value,
                query,
                candidates=[self._official(c) for c in r.matches],
            )
        return LookupItemOutput(r.index, r.status.value, query)  # not_covered

    @staticmethod
    def _official(card: Card) -> OfficialIdentity:
        return OfficialIdentity(
            card_id=str(card.id),
            set_name=card.identity.set_name,
            card_number=card.identity.card_number,
            edition=card.identity.edition,
            language=card.identity.language,
            finish=card.identity.finish,
        )

    @staticmethod
    def _query_echo(item: CardLookupItem) -> dict:
        echo: dict = {"set": item.set_name, "number": item.card_number}
        if item.edition is not None:
            echo["edition"] = item.edition
        if item.language is not None:
            echo["language"] = item.language
        if item.finish is not None:
            echo["finish"] = item.finish
        return echo

    @staticmethod
    def _summarize(results: list[CardLookupResult]) -> dict:
        counts = Counter(r.status for r in results)
        return {
            "total": len(results),
            "covered": counts[LookupResultStatus.COVERED],
            "multiple_match": counts[LookupResultStatus.MULTIPLE_MATCH],
            "not_covered": counts[LookupResultStatus.NOT_COVERED],
            "invalid_params": counts[LookupResultStatus.INVALID_PARAMS],
        }

    @staticmethod
    def _hash_items(items: list[CardLookupItem]) -> str:
        canonical = [
            {
                "set": i.set_name,
                "number": i.card_number,
                "edition": i.edition,
                "language": i.language,
                "finish": i.finish,
            }
            for i in items
        ]
        blob = json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    @staticmethod
    def _etags_match(if_none_match: str, etag: str) -> bool:
        candidate = if_none_match.strip()
        if candidate == "*":
            return True
        return candidate.strip('"') == etag.strip('"')


# ── (De)serialización para idempotencia ───────────────────────────────────────


def _response_to_json(resp: LookupResponse) -> str:
    return json.dumps(dataclasses.asdict(resp), ensure_ascii=False)


def _response_from_json(raw: str) -> LookupResponse:
    data = json.loads(raw)
    results: list[LookupItemOutput] = []
    for r in data.get("results", []):
        card = OfficialIdentity(**r["card"]) if r.get("card") else None
        candidates = (
            [OfficialIdentity(**c) for c in r["candidates"]]
            if r.get("candidates")
            else None
        )
        results.append(
            LookupItemOutput(
                index=r["index"],
                status=r["status"],
                query=r["query"],
                card=card,
                candidates=candidates,
                reason=r.get("reason"),
            )
        )
    return LookupResponse(
        request_id=data.get("request_id"),
        etag=data["etag"],
        summary=data.get("summary", {}),
        results=results,
        not_modified=data.get("not_modified", False),
    )
