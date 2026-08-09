"""Unit tests for domain entities and value objects."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from pokegrading.domain.entities.card import Card
from pokegrading.domain.entities.user import User
from pokegrading.domain.value_objects.card_identity import CardIdentityTuple
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.domain.value_objects.role import UserRole


def _make_identity() -> CardIdentityTuple:
    return CardIdentityTuple(
        set_name="Base Set",
        card_number="4/102",
        edition="1st Edition",
        language="English",
        finish="Holo",
    )


def _make_card(created_by=None) -> Card:
    return Card(
        id=uuid4(),
        identity=_make_identity(),
        name="Charizard",
        status=CardStatus.PENDING,
        version=1,
        created_by=created_by or uuid4(),
        created_at=datetime.now(tz=timezone.utc),
    )


# ── CardIdentityTuple ─────────────────────────────────────────────────────────


def test_card_identity_str():
    identity = _make_identity()
    assert str(identity) == "Base Set/4/102/1st Edition/English/Holo"


def test_card_identity_empty_field_raises():
    with pytest.raises(ValueError):
        CardIdentityTuple(
            set_name="", card_number="4/102", edition="1st", language="EN", finish="Holo"
        )


def test_card_identity_frozen():
    identity = _make_identity()
    with pytest.raises(Exception):
        identity.set_name = "New"  # type: ignore[misc]


# ── Card entity ───────────────────────────────────────────────────────────────


def test_card_approve_changes_status():
    creator_id = uuid4()
    approver_id = uuid4()
    card = _make_card(created_by=creator_id)
    assert card.is_pending()
    card.approve(approver_id=approver_id, approved_at=datetime.now(tz=timezone.utc))
    assert card.is_active()
    assert card.approved_by == approver_id


def test_card_approve_same_user_raises():
    uid = uuid4()
    card = _make_card(created_by=uid)
    with pytest.raises(ValueError, match="dual validation"):
        card.approve(approver_id=uid, approved_at=datetime.now(tz=timezone.utc))


def test_card_approve_non_pending_raises():
    card = _make_card()
    approver = uuid4()
    card.approve(approver_id=approver, approved_at=datetime.now(tz=timezone.utc))
    with pytest.raises(ValueError, match="PENDING"):
        card.approve(approver_id=uuid4(), approved_at=datetime.now(tz=timezone.utc))


# ── User entity ───────────────────────────────────────────────────────────────


def test_user_is_admin():
    user = User(
        id=uuid4(),
        email="a@a.com",
        hashed_password="x",
        alias="a",
        role=UserRole.ADMIN,
        accepted_disclosure=True,
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    assert user.is_admin()
    assert not user.is_reviewer()


def test_user_invalid_email_raises():
    with pytest.raises(ValueError):
        User(
            id=uuid4(),
            email="not-an-email",
            hashed_password="x",
            alias="a",
            role=UserRole.SUBMITTER,
            accepted_disclosure=True,
            is_active=True,
            created_at=datetime.now(tz=timezone.utc),
        )
