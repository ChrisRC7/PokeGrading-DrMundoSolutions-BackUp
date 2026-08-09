"""Country value object — supported countries for PokéGrading accounts."""
from __future__ import annotations

from enum import Enum


class SupportedCountry(str, Enum):
    """ISO 3166-1 alpha-2 codes for countries where PokéGrading operates."""

    CR = "CR"   # Costa Rica
    PA = "PA"   # Panamá
    MX = "MX"   # México
    CO = "CO"   # Colombia
    CL = "CL"   # Chile
    AR = "AR"   # Argentina
