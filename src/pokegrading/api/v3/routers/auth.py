from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pokegrading.api.v3.dependencies import get_current_user, require_admin
from pokegrading.api.v3.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UpdateUserRequest,
    UserResponse,
)
from pokegrading.application.use_cases.login_user import LoginUserInput, LoginUserUseCase
from pokegrading.application.use_cases.register_user import (
    RegisterUserInput,
    RegisterUserUseCase,
)
from pokegrading.domain.entities.user import User
from pokegrading.domain.exceptions import (
    BlockedEmailDomainError,
    CountryNotSupportedError,
    DisclosureNotAcceptedError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    PasswordTooWeakError,
)
from pokegrading.domain.value_objects.role import UserRole
from pokegrading.infrastructure.persistence.database import get_db
from pokegrading.infrastructure.persistence.repositories.user.user_repository import UserRepositoryImpl
from pokegrading.infrastructure.security.jwt import JWTService
from pokegrading.infrastructure.security.password import BcryptPasswordService

router = APIRouter(prefix="/auth", tags=["auth"])

_jwt_service = JWTService()


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="US-001 — Registrar cuenta",
)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    use_case = RegisterUserUseCase(
        user_repo=UserRepositoryImpl(db),
        password_service=BcryptPasswordService(),
    )
    try:
        result = use_case.execute(
            RegisterUserInput(
                email=body.email,
                password=body.password,
                alias=body.alias,
                accept_disclosure=body.accept_disclosure,
                country=body.country,
                preferred_language=body.preferred_language,
            )
        )
    except DisclosureNotAcceptedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except (BlockedEmailDomainError, PasswordTooWeakError, CountryNotSupportedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    access_token = _jwt_service.create_access_token(
        user_id=result.user_id, role=result.role.value
    )
    return RegisterResponse(
        access_token=access_token,
        user_id=result.user_id,
        email=result.email,
        alias=result.alias,
        role=result.role.value,
        country=result.country,
        preferred_language=result.preferred_language,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión",
)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    use_case = LoginUserUseCase(
        user_repo=UserRepositoryImpl(db),
        password_service=BcryptPasswordService(),
    )
    try:
        result = use_case.execute(LoginUserInput(email=body.email, password=body.password))
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    access_token = _jwt_service.create_access_token(
        user_id=result.user_id, role=result.role.value
    )
    return LoginResponse(
        access_token=access_token,
        user_id=result.user_id,
        email=result.email,
        alias=result.alias,
        role=result.role.value,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Perfil del usuario autenticado",
)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        user_id=current_user.id,
        email=current_user.email,
        alias=current_user.alias,
        role=current_user.role.value,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )


@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="Listar todos los usuarios (admin)",
)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[UserResponse]:
    users = UserRepositoryImpl(db).find_all()
    return [
        UserResponse(
            user_id=u.id,
            email=u.email,
            alias=u.alias,
            role=u.role.value,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.put(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Actualizar usuario (admin)",
)
def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserResponse:
    repo = UserRepositoryImpl(db)
    user = repo.find_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.alias is not None:
        user.alias = body.alias
    if body.role is not None:
        user.role = UserRole(body.role)
    if body.is_active is not None:
        user.is_active = body.is_active

    saved = repo.save(user)
    return UserResponse(
        user_id=saved.id,
        email=saved.email,
        alias=saved.alias,
        role=saved.role.value,
        is_active=saved.is_active,
        created_at=saved.created_at,
    )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Eliminar usuario (admin)",
)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    deleted = UserRepositoryImpl(db).delete(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
