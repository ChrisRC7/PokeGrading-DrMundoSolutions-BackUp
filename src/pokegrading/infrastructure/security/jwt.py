from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt

from pokegrading.config import get_settings


class JWTService:
    """Thin wrapper around python-jose for issuing and decoding HS256 tokens."""

    def create_access_token(self, user_id: UUID, role: str) -> str:
        settings = get_settings()
        expire = datetime.now(tz=timezone.utc) + timedelta(
            minutes=settings.jwt_expire_minutes
        )
        payload: dict = {
            "sub": str(user_id),
            "role": role,
            "exp": expire,
        }
        return jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )

    def decode_token(self, token: str) -> dict:
        settings = get_settings()
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError as exc:
            raise ValueError("Token inválido o expirado") from exc

        if "sub" not in payload or "role" not in payload:
            raise ValueError("Token inválido: faltan campos requeridos en el payload")

        return payload
