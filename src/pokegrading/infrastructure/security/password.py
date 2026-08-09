from __future__ import annotations

import bcrypt

from pokegrading.application.ports.password_service import IPasswordService


class BcryptPasswordService(IPasswordService):
    """Password hashing using bcrypt directly (bcrypt 4+ compatible)."""

    _ROUNDS = 12

    def hash(self, plain_password: str) -> str:
        hashed = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt(rounds=self._ROUNDS))
        return hashed.decode()

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
