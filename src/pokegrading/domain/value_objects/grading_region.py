from __future__ import annotations

from enum import Enum


class GradingRegion(str, Enum):
    CENTERING = "centering"
    CORNERS = "corners"
    EDGES = "edges"
    SURFACE = "surface"
