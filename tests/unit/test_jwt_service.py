"""Unit tests for JWTService — defensive programming (Sprint 2)."""
from __future__ import annotations

import pytest

from pokegrading.infrastructure.security.jwt import JWTService


@pytest.fixture()
def jwt_service() -> JWTService:
    return JWTService()


def test_decode_valid_token(jwt_service: JWTService) -> None:
    """Token válido se decodifica y devuelve sub y role."""
    from uuid_extensions import uuid7
    token = jwt_service.create_access_token(user_id=uuid7(), role="admin")
    payload = jwt_service.decode_token(token)
    assert "sub" in payload
    assert "role" in payload
    assert payload["role"] == "admin"


def test_decode_invalid_token_raises(jwt_service: JWTService) -> None:
    """Token malformado lanza ValueError."""
    with pytest.raises(ValueError, match="inv"):
        jwt_service.decode_token("esto.no.es.un.jwt")


def test_decode_expired_token_raises(jwt_service: JWTService) -> None:
    """Token expirado lanza ValueError."""
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from jose import jwt
    from pokegrading.config import get_settings

    settings = get_settings()
    payload = {
        "sub": str(uuid4()),
        "role": "submitter",
        "exp": datetime.now(tz=timezone.utc) - timedelta(seconds=1),
    }
    expired_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(ValueError, match="inv"):
        jwt_service.decode_token(expired_token)


def test_decode_token_missing_sub_raises(jwt_service: JWTService) -> None:
    """Token sin campo 'sub' lanza ValueError."""
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from pokegrading.config import get_settings

    settings = get_settings()
    payload = {
        "role": "admin",
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=60),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(ValueError, match="payload"):
        jwt_service.decode_token(token)


def test_decode_token_missing_role_raises(jwt_service: JWTService) -> None:
    """Token sin campo 'role' lanza ValueError."""
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from jose import jwt
    from pokegrading.config import get_settings

    settings = get_settings()
    payload = {
        "sub": str(uuid4()),
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=60),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(ValueError, match="payload"):
        jwt_service.decode_token(token)
