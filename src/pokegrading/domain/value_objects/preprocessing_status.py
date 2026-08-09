from __future__ import annotations

from enum import Enum


class PreprocessingStatus(str, Enum):
    OK = "ok"
    MANUAL = "manual"
    RECAPTURE = "recapture"
