from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pokegrading.domain.entities.user import User
from pokegrading.domain.exceptions import EmailAlreadyExistsError
from pokegrading.domain.repositories.user_repository import IUserRepository
from pokegrading.domain.value_objects.role import UserRole
from pokegrading.infrastructure.persistence.models import UserORM


class UserRepositoryImpl(IUserRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def find_by_email(self, email: str) -> User | None:
        # Consulta directa por el campo único de email; si no hay fila, el use case decide.
        row = self._db.query(UserORM).filter(UserORM.email == email).first()
        return self._to_entity(row) if row else None

    def find_by_id(self, user_id: UUID) -> User | None:
        # Misma idea que find_by_email, pero usando la PK del agregado User.
        row = self._db.query(UserORM).filter(UserORM.id == user_id).first()
        return self._to_entity(row) if row else None

    def find_all(self) -> list[User]:
        # Se ordena por created_at descendente para mostrar primero los registros más recientes.
        rows = self._db.query(UserORM).order_by(UserORM.created_at.desc()).all()
        return [self._to_entity(r) for r in rows]

    def delete(self, user_id: UUID) -> bool:
        # Eliminación simple: si la fila no existe, no hay nada que borrar.
        row = self._db.query(UserORM).filter(UserORM.id == user_id).first()
        if row is None:
            return False
        self._db.delete(row)
        self._db.commit()
        return True

    def save(self, user: User) -> User:
        # Patrón upsert manual: si ya existe la fila, se actualiza; si no, se inserta.
        row = self._db.query(UserORM).filter(UserORM.id == user.id).first()
        if row is None:
            row = UserORM(
                id=user.id,
                email=user.email,
                hashed_password=user.hashed_password,
                alias=user.alias,
                role=user.role,
                accepted_disclosure=user.accepted_disclosure,
                is_active=user.is_active,
                created_at=user.created_at,
                country=user.country,
                preferred_language=user.preferred_language,
            )
            self._db.add(row)
        else:
            # Se actualizan solo los campos mutables del agregado User.
            row.email = user.email
            row.hashed_password = user.hashed_password
            row.alias = user.alias
            row.role = user.role
            row.accepted_disclosure = user.accepted_disclosure
            row.is_active = user.is_active
            row.country = user.country
            row.preferred_language = user.preferred_language
        try:
            self._db.commit()
        except IntegrityError:
            # El único conflicto esperado aquí es la unicidad del email; se traduce a error de dominio.
            self._db.rollback()
            raise EmailAlreadyExistsError(user.email)
        self._db.refresh(row)
        return self._to_entity(row)

    @staticmethod
    def _to_entity(row: UserORM) -> User:
        # Conversión ORM -> entidad de dominio sin arrastrar detalles de SQLAlchemy al resto del sistema.
        return User(
            id=row.id,
            email=row.email,
            hashed_password=row.hashed_password,
            alias=row.alias,
            role=UserRole(row.role) if isinstance(row.role, str) else row.role,
            accepted_disclosure=row.accepted_disclosure,
            is_active=row.is_active,
            created_at=row.created_at,
            country=getattr(row, "country", "CR") or "CR",
            preferred_language=getattr(row, "preferred_language", "es") or "es",
        )
