from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    SUBMITTER = "submitter"
    REVIEWER = "reviewer"
    ADMIN = "admin"
    B2B_SERVICE_ACCOUNT = "b2b_service_account"
