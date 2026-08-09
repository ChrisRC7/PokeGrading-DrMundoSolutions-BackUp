from __future__ import annotations

from enum import Enum


class CardRarity(str, Enum):
    COMMON = "Common"
    UNCOMMON = "Uncommon"
    RARE = "Rare"
    HOLO_RARE = "Holo Rare"
    ULTRA_RARE = "Ultra Rare"
    SECRET_RARE = "Secret Rare"
