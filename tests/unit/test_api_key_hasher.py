from __future__ import annotations

from pokegrading.infrastructure.security.api_key import (
    Sha256ApiKeyHasher,
    generate_api_key,
)


def test_hash_and_verify_roundtrip():
    hasher = Sha256ApiKeyHasher("pepper")
    hashed = hasher.hash("super-secret")
    assert hasher.verify("super-secret", hashed)


def test_verify_rejects_wrong_secret():
    hasher = Sha256ApiKeyHasher("pepper")
    hashed = hasher.hash("super-secret")
    assert not hasher.verify("not-the-secret", hashed)


def test_different_pepper_produces_different_hash():
    assert Sha256ApiKeyHasher("p1").hash("s") != Sha256ApiKeyHasher("p2").hash("s")


def test_generated_key_has_expected_format():
    full, prefix, secret = generate_api_key("live")
    assert full == f"pkg_live_{prefix}_{secret}"
    assert len(prefix) == 8
    assert secret  # no vacío


def test_generated_keys_are_unique():
    a, _, _ = generate_api_key("live")
    b, _, _ = generate_api_key("live")
    assert a != b
