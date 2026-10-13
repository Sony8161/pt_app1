"""SQL access for the ``users`` table (queries composed with ``psycopg.sql``)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

import psycopg
from psycopg import sql

# Columns safe to expose to the API layer (never the password hash).
USER_COLUMN_NAMES = (
    "id", "username", "name", "email", "job_title", "role", "manager_id", "salary",
    "must_change_password", "token_version", "archived_at", "created_at", "updated_at",
)
USER_COLUMNS = sql.SQL(", ").join(sql.Identifier(c) for c in USER_COLUMN_NAMES)

# Fields an UPDATE may touch; everything else goes through dedicated functions.
UPDATABLE_FIELDS = frozenset({"name", "email", "job_title", "role", "manager_id", "salary"})


def get_by_id(conn: psycopg.Connection[Any], user_id: uuid.UUID) -> dict[str, Any] | None:
    """Fetch one user (including archived) by id."""
    query = sql.SQL("SELECT {cols} FROM users WHERE id = %s").format(cols=USER_COLUMNS)
    return conn.execute(query, (user_id,)).fetchone()


def get_auth_by_username(conn: psycopg.Connection[Any], username: str) -> dict[str, Any] | None:
    """Fetch the columns needed to authenticate ``username`` (includes the hash)."""
    query = sql.SQL("SELECT {cols}, password_hash FROM users WHERE username = %s").format(cols=USER_COLUMNS)
    return conn.execute(query, (username.lower(),)).fetchone()


def username_exists(conn: psycopg.Connection[Any], username: str) -> bool:
    """True when ``username`` is already taken."""
    return conn.execute("SELECT 1 FROM users WHERE username = %s", (username,)).fetchone() is not None


def email_exists(conn: psycopg.Connection[Any], email: str, *, exclude_id: uuid.UUID | None = None) -> bool:
    """True when another user already has ``email`` (case-insensitive)."""
    row = conn.execute(
        "SELECT 1 FROM users WHERE lower(email) = lower(%s) AND (%s::uuid IS NULL OR id <> %s)",
        (email, exclude_id, exclude_id),
    ).fetchone()
    return row is not None


def count_by_role(conn: psycopg.Connection[Any], role: str, *, include_archived: bool = False) -> int:
    """Number of users with ``role``."""
    query = "SELECT count(*) AS n FROM users WHERE role = %s"
    if not include_archived:
        query += " AND archived_at IS NULL"
    row = conn.execute(query, (role,)).fetchone()
    return int(row["n"]) if row else 0


def list_users(
    conn: psycopg.Connection[Any],
    *,
    q: str | None = None,
    role: str | None = None,
    manager_id: uuid.UUID | None = None,
    include_archived: bool = False,
    exclude_roles: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Filtered, name-ordered list of users."""
    conditions: list[sql.Composable] = [sql.SQL("TRUE")]
    params: list[Any] = []
    if not include_archived:
        conditions.append(sql.SQL("archived_at IS NULL"))
    if role:
        conditions.append(sql.SQL("role = %s"))
        params.append(role)
    if manager_id is not None:
        conditions.append(sql.SQL("manager_id = %s"))
        params.append(manager_id)
    excluded = list(exclude_roles)
    if excluded:
        conditions.append(sql.SQL("role <> ALL(%s)"))
        params.append(excluded)
    if q:
        conditions.append(
            sql.SQL("(name ILIKE %s OR email ILIKE %s OR username ILIKE %s OR job_title ILIKE %s)")
        )
        like = f"%{q}%"
        params.extend([like, like, like, like])

    query = sql.SQL("SELECT {cols} FROM users WHERE {where} ORDER BY name, username").format(
        cols=USER_COLUMNS, where=sql.SQL(" AND ").join(conditions)
    )
    return conn.execute(query, params).fetchall()


def insert(
    conn: psycopg.Connection[Any],
    *,
    username: str,
    password_hash: str,
    name: str,
    email: str,
    job_title: str,
    role: str,
    manager_id: uuid.UUID | None,
    salary: float,
    must_change_password: bool = True,
) -> dict[str, Any]:
    """Create a user and return the stored row."""
    query = sql.SQL(
        """
        INSERT INTO users (username, password_hash, name, email, job_title, role, manager_id,
                           salary, must_change_password)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING {cols}
        """
    ).format(cols=USER_COLUMNS)
    row = conn.execute(
        query,
        (username, password_hash, name, email, job_title, role, manager_id, salary, must_change_password),
    ).fetchone()
    if row is None:  # pragma: no cover - RETURNING always yields the inserted row
        raise RuntimeError("INSERT INTO users returned no row")
    return row


def update(conn: psycopg.Connection[Any], user_id: uuid.UUID, fields: dict[str, Any]) -> dict[str, Any] | None:
    """Update the given profile fields (only ``UPDATABLE_FIELDS``) and return the row."""
    clean = {key: value for key, value in fields.items() if key in UPDATABLE_FIELDS}
    if not clean:
        return get_by_id(conn, user_id)
    assignments = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(key)) for key in clean
    )
    query = sql.SQL("UPDATE users SET {sets} WHERE id = %s RETURNING {cols}").format(
        sets=assignments, cols=USER_COLUMNS
    )
    return conn.execute(query, (*clean.values(), user_id)).fetchone()


def set_password(
    conn: psycopg.Connection[Any],
    user_id: uuid.UUID,
    password_hash: str,
    *,
    must_change_password: bool,
) -> dict[str, Any] | None:
    """Store a new hash and bump ``token_version`` so older tokens are revoked."""
    query = sql.SQL(
        """
        UPDATE users
        SET password_hash = %s, must_change_password = %s, token_version = token_version + 1
        WHERE id = %s
        RETURNING {cols}
        """
    ).format(cols=USER_COLUMNS)
    return conn.execute(query, (password_hash, must_change_password, user_id)).fetchone()


def set_archived(conn: psycopg.Connection[Any], user_id: uuid.UUID, *, archived: bool) -> dict[str, Any] | None:
    """Archive (or restore) a user; archiving also revokes their tokens."""
    query = sql.SQL(
        """
        UPDATE users
        SET archived_at = CASE WHEN %s THEN now() ELSE NULL END,
            token_version = token_version + 1
        WHERE id = %s
        RETURNING {cols}
        """
    ).format(cols=USER_COLUMNS)
    return conn.execute(query, (archived, user_id)).fetchone()
