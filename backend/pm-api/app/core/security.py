"""
Password hashing, credential generation and JWT access tokens.

* Passwords are hashed with bcrypt.
* Usernames are 6 lowercase alphanumerics: two letters from the person's name
  plus four random characters (the repository retries on the rare collision).
* Access tokens are HS256 JWTs carrying the user id, role and ``token_version``
  so a password change or admin reset revokes every earlier token.
"""

from __future__ import annotations

import datetime as dt
import secrets
import string
from functools import lru_cache
from typing import Any

import bcrypt
import jwt

from app.config import get_settings
from app.core.errors import AuthError, ValidationError

USERNAME_LENGTH = 6
USERNAME_ALPHABET = string.ascii_lowercase + string.digits
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72  # bcrypt input limit
GENERATED_PASSWORD_LENGTH = 12


def validate_password_strength(password: str) -> None:
    """Raise :class:`ValidationError` unless the password meets the policy."""
    problems: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"at least {PASSWORD_MIN_LENGTH} characters")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        problems.append(f"at most {PASSWORD_MAX_BYTES} bytes")
    if not any(c.islower() for c in password):
        problems.append("a lowercase letter")
    if not any(c.isupper() for c in password):
        problems.append("an uppercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("a digit")
    if problems:
        raise ValidationError(
            "Password must contain " + ", ".join(problems),
            details=[{"field": "new_password", "message": "Password must contain " + ", ".join(problems)}],
        )


def hash_password(password: str) -> str:
    """Return a bcrypt hash of ``password``."""
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time check of ``password`` against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Hash of a throwaway password, computed lazily (bcrypt is too slow for import time)."""
    return hash_password("not-a-real-password-0")


def verify_against_dummy() -> None:
    """Burn the same time as a real password check so login timing does not reveal accounts."""
    bcrypt.checkpw(b"wrong", _dummy_hash().encode("ascii"))


def generate_username(full_name: str) -> str:
    """Six-character username derived from ``full_name`` plus random characters."""
    letters = [c for c in full_name.lower() if c in string.ascii_lowercase]
    prefix = "".join(letters[:2]).ljust(2, "u")
    suffix = "".join(secrets.choice(USERNAME_ALPHABET) for _ in range(USERNAME_LENGTH - len(prefix)))
    return prefix + suffix


def generate_password(length: int = GENERATED_PASSWORD_LENGTH) -> str:
    """Random initial password that satisfies :func:`validate_password_strength`."""
    alphabet = string.ascii_letters + string.digits
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
        ):
            return candidate


def create_access_token(*, user_id: str, role: str, token_version: int,
                        now: dt.datetime | None = None) -> tuple[str, int]:
    """Issue a signed access token; returns ``(token, expires_at_epoch_seconds)``."""
    settings = get_settings()
    now = now or dt.datetime.now(dt.UTC)
    expires = now + dt.timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_hex(8),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires.timestamp())


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate ``token`` and return its claims, raising :class:`AuthError` on failure."""
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Your session has expired. Please sign in again.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid authentication token", code="token_invalid") from exc
