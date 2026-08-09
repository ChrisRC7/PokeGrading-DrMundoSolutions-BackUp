from __future__ import annotations

import uuid
from datetime import datetime

from uuid_extensions import uuid7

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus
from pokegrading.domain.value_objects.b2b_customer_status import B2BCustomerStatus
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.domain.value_objects.role import UserRole
from pokegrading.domain.value_objects.submission_status import SubmissionStatus
from pokegrading.infrastructure.persistence.database import Base


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=UserRole.SUBMITTER,
    )
    accepted_disclosure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="CR")
    preferred_language: Mapped[str] = mapped_column(String(5), nullable=False, default="es")

    cards_created: Mapped[list[CardORM]] = relationship(
        "CardORM",
        foreign_keys="CardORM.created_by",
        back_populates="creator",
    )


class CardORM(Base):
    __tablename__ = "catalog_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    set_name: Mapped[str] = mapped_column(String(100), nullable=False)
    card_number: Mapped[str] = mapped_column(String(20), nullable=False)
    edition: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    finish: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[CardStatus] = mapped_column(
        Enum(CardStatus, name="cardstatus", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=CardStatus.PENDING,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rarity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pokemon_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    illustrator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    print_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    creator: Mapped[UserORM] = relationship(
        "UserORM", foreign_keys=[created_by], back_populates="cards_created"
    )
    images: Mapped[list[CardImageORM]] = relationship(
        "CardImageORM", back_populates="card", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "set_name",
            "card_number",
            "edition",
            "language",
            "finish",
            name="uq_card_identity",
        ),
    )


class CardImageORM(Base):
    """Almacenamiento binario de imágenes de referencia de cartas.

    Diseño de BD (Sprint 2, desarrollo):
    - Los bytes de la imagen se guardan directamente en PostgreSQL como BYTEA.
    - La columna `data` usa LargeBinary (BYTEA), que en PostgreSQL puede alojar
      hasta 1 GB por fila; en la práctica se limita a 10 MB por la validación
      en dominio.
    - Una carta puede tener máximo una imagen por `side` ('front' | 'back').
    - La restricción `uq_card_image_side` garantiza unicidad (card_id, side).

    Nota de producción:
    - En producción se recomienda migrar a Azure Blob Storage:
      reemplazar `data BYTEA` por `blob_name VARCHAR(500)` y
      resolver el binario vía el SDK de Azure Storage.
    """

    __tablename__ = "card_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    side: Mapped[str] = mapped_column(String(5), nullable=False)   # 'front' | 'back'
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'image/jpeg' | 'image/png'
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    phash: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    card: Mapped[CardORM] = relationship("CardORM", back_populates="images")

    __table_args__ = (
        UniqueConstraint("card_id", "side", name="uq_card_image_side"),
    )


class SubmissionORM(Base):
    """Envío de carta física para evaluación de grado.

    Las imágenes frente y reverso se almacenan como BYTEA directamente en la fila
    (Sprint 2 — desarrollo). En producción se migrarán a Azure Blob Storage:
    reemplazar las columnas BYTEA por VARCHAR(500) con el nombre del blob.
    """

    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_cards.id"), nullable=True
    )
    image_front_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    image_back_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(
            SubmissionStatus,
            name="submissionstatus",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=SubmissionStatus.PENDING,
    )
    image_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ── B2B API (US-005) ──────────────────────────────────────────────────────────
# Tablas del API B2B de cobertura de catálogo. Ver ADR-004 §7.


class B2BCustomerORM(Base):
    """Customer B2B (tienda) que consume el API de cobertura de catálogo."""

    __tablename__ = "b2b_customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[B2BCustomerStatus] = mapped_column(
        Enum(
            B2BCustomerStatus,
            name="b2bcustomerstatus",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=B2BCustomerStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    api_keys: Mapped[list[ApiKeyORM]] = relationship(
        "ApiKeyORM", back_populates="customer", cascade="all, delete-orphan"
    )


class ApiKeyORM(Base):
    """API key B2B. El secreto nunca se almacena en claro (solo HMAC-SHA256).

    `key_prefix` es público e indexado: localiza la llave en O(1) sin exponer
    el secreto (ver Sprint3/DOC/diseno-versionamiento-seguridad-api.md §2).
    """

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("b2b_customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_prefix: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    hashed_secret: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[ApiKeyStatus] = mapped_column(
        Enum(
            ApiKeyStatus,
            name="apikeystatus",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=ApiKeyStatus.ACTIVE,
    )
    scopes: Mapped[str] = mapped_column(
        String(255), nullable=False, default="catalog:lookup"
    )
    rate_limit_cards_per_window: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1000
    )
    rate_limit_window_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    grace_period_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    customer: Mapped[B2BCustomerORM] = relationship(
        "B2BCustomerORM", back_populates="api_keys"
    )


class B2BLookupAuditORM(Base):
    """Auditoría de cada consulta B2B (AC-15). Sin secretos ni datos de evaluación."""

    __tablename__ = "b2b_lookup_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("b2b_customers.id"), nullable=False
    )
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    card_count: Mapped[int] = mapped_column(Integer, nullable=False)
    covered: Mapped[int] = mapped_column(Integer, nullable=False)
    multiple: Mapped[int] = mapped_column(Integer, nullable=False)
    not_covered: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class B2BIdempotencyORM(Base):
    """Respuesta almacenada por `(api_key_id, request_id)` para idempotencia (AC-08).

    `response_json` se guarda como texto (JSON) para portabilidad entre
    PostgreSQL y SQLite (tests). En producción puede migrarse a JSONB.
    """

    __tablename__ = "b2b_idempotency"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("api_key_id", "request_id", name="uq_b2b_idempotency"),
    )


class B2BRateLimitCounterORM(Base):
    """Contador de cartas consumidas por ventana de rate limit (AC-07)."""

    __tablename__ = "b2b_rate_limit_counters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False, index=True
    )
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cards_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "api_key_id", "window_start", name="uq_b2b_rate_window"
        ),
    )


# ── Sprint 4: Preprocesamiento y Calificación ─────────────────────────────────


class SubmissionRegionORM(Base):
    """Recorte normalizado de una región de carta y su pHash (AC-P2/P3).

    Producido por PreprocessCardUseCase y consumido por GradeCardUseCase.
    La combinación (submission_id, region) es única: reejecutar el
    preprocesamiento sobre el mismo submission sobreescribe la fila vía merge.
    """

    __tablename__ = "submission_regions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    region: Mapped[str] = mapped_column(String(12), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    phash: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("submission_id", "region", name="uq_submission_region"),
    )


class CardEvaluationORM(Base):
    """Evaluación estimada e INMUTABLE de una carta (AC-G5/G6).

    append-only: nunca se actualiza una fila existente. Una nueva versión del
    algoritmo genera una fila distinta (submission_id, algorithm_version únicas).
    """

    __tablename__ = "card_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id"), nullable=False, index=True
    )
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalog_cards.id"), nullable=True
    )
    final_grade: Mapped[float] = mapped_column(Float, nullable=False)
    uncertainty: Mapped[float] = mapped_column(Float, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    baseline_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    subgrades: Mapped[list[EvaluationSubgradeORM]] = relationship(
        "EvaluationSubgradeORM", back_populates="evaluation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "submission_id", "algorithm_version", name="uq_evaluation_version"
        ),
    )


class EvaluationSubgradeORM(Base):
    """Subgrade por dimensión de una evaluación (AC-G1)."""

    __tablename__ = "evaluation_subgrades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("card_evaluations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region: Mapped[str] = mapped_column(String(12), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    hamming_distance: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    evaluation: Mapped[CardEvaluationORM] = relationship(
        "CardEvaluationORM", back_populates="subgrades"
    )

    __table_args__ = (
        UniqueConstraint("evaluation_id", "region", name="uq_subgrade_region"),
    )


class GradingBaselineORM(Base):
    """Baseline calibrado o global para mapear distancia pHash → grado (AC-G2).

    `params_json` almacena `{region: [d_min, d_max]}` como JSON portátil
    (PostgreSQL y SQLite), igual que B2B idempotency.
    """

    __tablename__ = "grading_baselines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_calibrated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ground_truth_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    params_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
