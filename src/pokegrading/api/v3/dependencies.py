from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from pokegrading.domain.entities.user import User
from pokegrading.infrastructure.persistence.database import get_db
from pokegrading.infrastructure.persistence.repositories.user.user_repository import UserRepositoryImpl
from pokegrading.infrastructure.security.jwt import JWTService

_bearer = HTTPBearer(auto_error=False)
_jwt_service = JWTService()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # auto_error=False permite diferenciar ausencia de token de un fallo real de autenticación.
    if credentials is None:
        raise credentials_exception
    try:
        # El token debe contener un sub con el UUID del usuario autenticado.
        payload = _jwt_service.decode_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        user_uuid = UUID(user_id)
    except (ValueError, AttributeError):
        raise credentials_exception

    # El usuario debe existir y seguir activo; el JWT por sí solo no basta.
    user_repo = UserRepositoryImpl(db)
    try:
        user = user_repo.find_by_id(user_uuid)
    except Exception:
        raise credentials_exception
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    # Cualquier endpoint admin pasa por esta verificación centralizada.
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user
