"""Integration tests for POST /api/v3/auth/register (US-001)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_register_success(client: TestClient):
    """AC-01: valid payload -> 201 + JWT."""
    resp = client.post(
        "/api/v3/auth/register",
        json={
            "email": "new@example.com",
            "password": "Secret1234!",
            "alias": "NewUser",
            "accept_disclosure": True,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["email"] == "new@example.com"
    assert data["role"] == "submitter"


def test_register_duplicate_email(client: TestClient):
    """AC-02: duplicate email -> 409."""
    payload = {
        "email": "dup@example.com",
        "password": "Secret1234!",
        "alias": "Dup",
        "accept_disclosure": True,
    }
    client.post("/api/v3/auth/register", json=payload)
    resp = client.post("/api/v3/auth/register", json=payload)
    assert resp.status_code == 409


def test_register_disclosure_not_accepted(client: TestClient):
    """AC-05: accept_disclosure=False -> 400."""
    resp = client.post(
        "/api/v3/auth/register",
        json={
            "email": "nodisclosure@example.com",
            "password": "Secret1234!",
            "alias": "ND",
            "accept_disclosure": False,
        },
    )
    assert resp.status_code == 400


def test_register_short_password(client: TestClient):
    """Password < 8 chars -> 422 Unprocessable Entity (Pydantic validation)."""
    resp = client.post(
        "/api/v3/auth/register",
        json={
            "email": "short@example.com",
            "password": "abc",
            "alias": "s",
            "accept_disclosure": True,
        },
    )
    assert resp.status_code == 422


def test_register_invalid_email(client: TestClient):
    """Invalid email format -> 422."""
    resp = client.post(
        "/api/v3/auth/register",
        json={
            "email": "not-an-email",
            "password": "Secret1234!",
            "alias": "x",
            "accept_disclosure": True,
        },
    )
    assert resp.status_code == 422
