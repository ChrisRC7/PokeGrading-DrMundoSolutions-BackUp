from __future__ import annotations

from enum import Enum


class CardStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    RETIRED = "retired"
