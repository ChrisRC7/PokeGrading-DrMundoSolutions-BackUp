from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    # Validación de entrada HTTP para el alta de usuario.
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    alias: str = Field(min_length=1, max_length=100)
    accept_disclosure: bool
    country: str = Field(default="CR", min_length=2, max_length=2)
    preferred_language: str = Field(default="es", pattern="^(es|en)$")


class RegisterResponse(BaseModel):
    # Respuesta pública del alta: incluye token para bootstrap inmediato de la sesión.
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    email: str
    alias: str
    role: str
    country: str
    preferred_language: str


class LoginRequest(BaseModel):
    # Credenciales mínimas para iniciar sesión.
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    # Respuesta mínima del login: token + datos visibles del usuario.
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    email: str
    alias: str
    role: str


class UserResponse(BaseModel):
    # Esquema de lectura para perfil y listados administrativos.
    user_id: UUID
    email: str
    alias: str
    role: str
    is_active: bool
    created_at: datetime


class UpdateUserRequest(BaseModel):
    # Actualización parcial: el admin puede mandar solo los campos que quiere cambiar.
    alias: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = Field(default=None, pattern="^(submitter|reviewer|admin|b2b_service_account)$")
    is_active: bool | None = None
