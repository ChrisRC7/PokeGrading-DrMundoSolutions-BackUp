from __future__ import annotations

from enum import Enum


class B2BCustomerStatus(str, Enum):
    """Estado de un Customer B2B (tienda).

    Un customer suspendido invalida TODAS sus API keys, sin importar el
    estado individual de cada llave (ver ADR-004 §6 → CUSTOMER_SUSPENDED).
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"
