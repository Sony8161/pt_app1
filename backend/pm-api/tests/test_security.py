"""Passwords, usernames and tokens (no database needed)."""

from __future__ import annotations

import datetime as dt
import string

import jwt
import pytest

from app.config import get_settings
from app.core import security
from app.core.errors import AuthError, ValidationError


def test_password_hash_roundtrip():
    hashed = security.hash_password("Abcdef12")
    assert security.verify_password("Abcdef12", hashed)
    assert not security.verify_password("abcdef12", hashed)
    assert not security.verify_password("Abcdef12", "not-a-hash")


@pytest.mark.parametrize("bad", ["short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere", "A1b" + "x" * 80])
def test_weak_passwords_rejected(bad):
    with pytest.raises(ValidationError):
        security.validate_password_strength(bad)


def test_strong_password_accepted():
    security.validate_password_strength("Passw0rd-xyz")


def test_generated_password_meets_policy():
    for _ in range(25):
        security.validate_password_strength(security.generate_password())


def test_generated_username_is_six_lowercase_alphanumerics():
    allowed = set(string.ascii_lowercase + string.digits)
    for name in ["Maria Lopez", "Al", "X", "Zoë Müller", "  ", "O'Brien"]:
        username = security.generate_username(name)
        assert len(username) == 6 and set(username) <= allowed
    assert security.generate_username("Maria Lopez").startswith("ma")


def test_token_roundtrip_and_claims():
    token, expires = security.create_access_token(user_id="u-1", role="manager", token_version=3)
    claims = security.decode_access_token(token)
    assert claims["sub"] == "u-1" and claims["role"] == "manager" and claims["tv"] == 3
    assert claims["exp"] == expires


def test_expired_token_is_rejected():
    long_ago = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    token, _ = security.create_access_token(user_id="u-1", role="admin", token_version=0, now=long_ago)
    with pytest.raises(AuthError) as exc:
        security.decode_access_token(token)
    assert exc.value.code == "token_expired"


def test_token_with_wrong_signature_is_rejected():
    forged = jwt.encode({"sub": "u-1", "exp": 4102444800, "iat": 1}, "another-secret-another-secret-12", algorithm="HS256")
    with pytest.raises(AuthError) as exc:
        security.decode_access_token(forged)
    assert exc.value.code == "token_invalid"


def test_token_signed_with_none_algorithm_is_rejected():
    unsigned = jwt.encode({"sub": "u-1", "exp": 4102444800, "iat": 1}, None, algorithm="none")
    with pytest.raises(AuthError):
        security.decode_access_token(unsigned)


def test_cloud_requires_a_jwt_secret():
    from app.config import load_settings

    with pytest.raises(RuntimeError):
        load_settings({"IS_LOCAL": "false"})
    assert load_settings({"IS_LOCAL": "false", "JWT_SECRET": "x" * 40}).bootstrap_admin_password == ""
    assert get_settings().bootstrap_admin_password == "ChangeMe123!"  # local default
