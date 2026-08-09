"""Blocked email domains — disposable / unauthorized providers.

This list is intentionally short. Add more entries as needed.
"""
from __future__ import annotations

BLOCKED_DOMAINS: frozenset[str] = frozenset(
    {
        # Generic disposable services
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.net",
        "guerrillamail.org",
        "throwam.com",
        "trashmail.com",
        "trashmail.net",
        "trashmail.at",
        "tempmail.com",
        "temp-mail.org",
        "10minutemail.com",
        "10minutemail.net",
        "yopmail.com",
        "yopmail.fr",
        "sharklasers.com",
        "dispostable.com",
        "fakeinbox.com",
        "maildrop.cc",
        "mailnull.com",
        "spamgourmet.com",
        "spamgourmet.net",
        "getairmail.com",
        "filzmail.com",
        "discard.email",
        "spamherr.com",
        "mailnesia.com",
    }
)
