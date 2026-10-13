"""
Application settings loaded from environment variables.

The deployment injects ``IS_LOCAL``, ``POSTGRES_*``, ``APP_ENV`` and ``JWT_SECRET``
(see ``infra/locals.tf``). Everything else has a sensible default so the API
also runs under plain ``uvicorn`` and under ``pytest``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from psycopg.conninfo import make_conninfo

SERVICE_NAME = "pm-api"
API_PREFIX = f"/api/{SERVICE_NAME}"

# Only acceptable when IS_LOCAL=true; cloud deployments must provide JWT_SECRET.
_INSECURE_LOCAL_SECRET = "insecure-local-development-secret"  # noqa: S105  # nosec B105
_LOCAL_BOOTSTRAP_PASSWORD = "ChangeMe123!"  # noqa: S105  # nosec B105


def _as_bool(value: str | None, default: bool) -> bool:
    """Parse a boolean-ish environment value."""
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    app_env: str
    is_local: bool
    jwt_secret: str
    jwt_algorithm: str
    access_token_ttl_minutes: int
    bcrypt_rounds: int
    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    pg_database: str
    pg_connect_timeout: int
    auto_migrate: bool
    bootstrap_admin_username: str
    bootstrap_admin_password: str

    @property
    def pg_conninfo(self) -> str:
        """libpq connection string; Aurora requires SSL, local PostgreSQL has none."""
        params: dict[str, str | int] = {
            "host": self.pg_host,
            "port": self.pg_port,
            "user": self.pg_user,
            "password": self.pg_password,
            "dbname": self.pg_database,
            "connect_timeout": self.pg_connect_timeout,
            "application_name": SERVICE_NAME,
        }
        if not self.is_local:
            params["sslmode"] = "require"
        return make_conninfo(**params)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from ``env`` (defaults to ``os.environ``)."""
    env = os.environ if env is None else env
    is_local = _as_bool(env.get("IS_LOCAL"), default=True)

    jwt_secret = env.get("JWT_SECRET", "").strip()
    if not jwt_secret:
        if not is_local:
            raise RuntimeError("JWT_SECRET must be set when IS_LOCAL is false")
        jwt_secret = _INSECURE_LOCAL_SECRET

    return Settings(
        app_env=env.get("APP_ENV", "local").strip() or "local",
        is_local=is_local,
        jwt_secret=jwt_secret,
        jwt_algorithm="HS256",
        access_token_ttl_minutes=int(env.get("ACCESS_TOKEN_TTL_MINUTES", "480")),
        bcrypt_rounds=int(env.get("BCRYPT_ROUNDS", "12")),
        pg_host=env.get("POSTGRES_HOST", "localhost"),
        pg_port=int(env.get("POSTGRES_PORT", "5432")),
        pg_user=env.get("POSTGRES_USER", "postgres"),
        pg_password=env.get("POSTGRES_PASS", "postgres123"),
        pg_database=env.get("POSTGRES_NAME", "postgres"),
        pg_connect_timeout=int(env.get("POSTGRES_CONNECT_TIMEOUT", "10")),
        auto_migrate=_as_bool(env.get("AUTO_MIGRATE"), default=True),
        bootstrap_admin_username=env.get("BOOTSTRAP_ADMIN_USERNAME", "admin1").strip(),
        # Local development gets a documented default; cloud deployments must supply a
        # secret (Terraform generates one) so a public default never protects a real admin.
        bootstrap_admin_password=env.get("BOOTSTRAP_ADMIN_PASSWORD", "").strip()
        or (_LOCAL_BOOTSTRAP_PASSWORD if is_local else ""),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings (cached; tests call ``cache_clear``)."""
    return load_settings()
