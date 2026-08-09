from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pokegrading.api.v3.dependencies import get_current_user, require_admin
from pokegrading.config import get_settings
from pokegrading.domain.entities.user import User
from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus
from pokegrading.domain.value_objects.b2b_customer_status import B2BCustomerStatus
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.domain.value_objects.role import UserRole
from pokegrading.infrastructure.persistence.database import Base, get_db
from pokegrading.infrastructure.persistence.models import (  # noqa: F401
    ApiKeyORM,
    B2BCustomerORM,
    CardEvaluationORM,
    CardORM,
    EvaluationSubgradeORM,
    GradingBaselineORM,
    SubmissionORM,
    SubmissionRegionORM,
    UserORM,
)
from pokegrading.infrastructure.security.api_key import (
    Sha256ApiKeyHasher,
    generate_api_key,
)
from pokegrading.infrastructure.security.password import BcryptPasswordService
from pokegrading.main import app

# ── SQLite in-memory test DB ─────────────────────────────────────────────────

_TEST_DB_URL = "sqlite:///:memory:?check_same_thread=False"

engine_test = create_engine(
    _TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# SQLite does not support ENUM natively — map to VARCHAR for tests
from sqlalchemy import String  # noqa: E402


@event.listens_for(engine_test, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(scope="session", autouse=True)
def create_tables() -> None:
    # Re-create metadata with VARCHAR instead of PG ENUM
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql

    # Patch UUID type for SQLite
    from sqlalchemy import TypeDecorator

    Base.metadata.create_all(bind=engine_test)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    connection = engine_test.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ──────────────────────────────────────────────────────────────────

_pwd = BcryptPasswordService()


def _make_user(
    db: Session,
    *,
    email: str = "user@example.com",
    alias: str = "testuser",
    role: UserRole = UserRole.SUBMITTER,
    password: str = "Secret1234!",
) -> UserORM:
    row = UserORM(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_pwd.hash(password),
        alias=alias,
        role=role,
        accepted_disclosure=True,
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def admin_user(db: Session) -> UserORM:
    return _make_user(db, email="admin@example.com", alias="admin", role=UserRole.ADMIN)


@pytest.fixture()
def submitter_user(db: Session) -> UserORM:
    return _make_user(
        db, email="submitter@example.com", alias="submitter", role=UserRole.SUBMITTER
    )


def _token_for(user_orm: UserORM) -> str:
    from pokegrading.infrastructure.security.jwt import JWTService

    return JWTService().create_access_token(
        user_id=user_orm.id, role=user_orm.role.value
    )


@pytest.fixture()
def admin_token(admin_user: UserORM) -> str:
    return _token_for(admin_user)


@pytest.fixture()
def submitter_token(submitter_user: UserORM) -> str:
    return _token_for(submitter_user)


# ── Helpers B2B (US-005) ──────────────────────────────────────────────────────


def _make_active_card(
    db: Session,
    creator_id: uuid.UUID,
    *,
    set_name: str = "Base Set",
    card_number: str = "58/102",
    edition: str = "Unlimited",
    language: str = "en",
    finish: str = "holo",
    name: str = "Pikachu",
    status: CardStatus = CardStatus.ACTIVE,
) -> CardORM:
    row = CardORM(
        id=uuid.uuid4(),
        name=name,
        set_name=set_name,
        card_number=card_number,
        edition=edition,
        language=language,
        finish=finish,
        status=status,
        version=1,
        created_by=creator_id,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_b2b_key(
    db: Session,
    *,
    status: ApiKeyStatus = ApiKeyStatus.ACTIVE,
    customer_status: B2BCustomerStatus = B2BCustomerStatus.ACTIVE,
    environment: str = "live",
    rate_cards: int = 1000,
    rate_window: int = 3600,
) -> tuple[str, B2BCustomerORM, ApiKeyORM]:
    """Crea un Customer + ApiKey y devuelve la llave en claro para usarla en tests."""
    hasher = Sha256ApiKeyHasher(get_settings().b2b_api_key_pepper)
    full_key, prefix, secret = generate_api_key(environment)

    customer = B2BCustomerORM(
        id=uuid.uuid4(),
        name="Tienda Test",
        status=customer_status,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    key = ApiKeyORM(
        id=uuid.uuid4(),
        customer_id=customer.id,
        key_prefix=prefix,
        hashed_secret=hasher.hash(secret),
        status=status,
        scopes="catalog:lookup",
        rate_limit_cards_per_window=rate_cards,
        rate_limit_window_seconds=rate_window,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return full_key, customer, key


@pytest.fixture()
def b2b_api_key(db: Session) -> str:
    """API key B2B activa lista para autenticar."""
    full_key, _, _ = _make_b2b_key(db)
    return full_key
