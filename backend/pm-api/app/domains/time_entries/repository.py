"""SQL access for ``time_entries``."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg

_ENTRY_SELECT = """
    SELECT te.id, te.project_id, p.name AS project_name, te.user_id, u.name AS user_name,
           te.milestone_id, te.work_date, te.hours, te.notes, te.created_at,
           te.hours * u.salary AS labor_cost
    FROM time_entries te
    JOIN users u ON u.id = te.user_id
    JOIN projects p ON p.id = te.project_id
"""


def day_total(
    conn: psycopg.Connection[Any], user_id: uuid.UUID, day: dt.date, *, exclude_id: uuid.UUID | None = None
) -> float:
    """Hours a person already logged on ``day`` across all projects."""
    row = conn.execute(
        "SELECT COALESCE(sum(hours), 0) AS n FROM time_entries WHERE user_id = %s AND work_date = %s "
        "AND archived_at IS NULL AND (%s::uuid IS NULL OR id <> %s)",
        (user_id, day, exclude_id, exclude_id),
    ).fetchone()
    return float(row["n"]) if row else 0.0


def insert(
    conn: psycopg.Connection[Any],
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    milestone_id: uuid.UUID | None,
    work_date: dt.date,
    hours: float,
    notes: str,
) -> uuid.UUID:
    """Log time and return the entry id."""
    row = conn.execute(
        """
        INSERT INTO time_entries (project_id, user_id, milestone_id, work_date, hours, notes)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (project_id, user_id, milestone_id, work_date, hours, notes),
    ).fetchone()
    if row is None:  # pragma: no cover - RETURNING always yields the inserted row
        raise RuntimeError("INSERT INTO time_entries returned no row")
    return row["id"]


def get(conn: psycopg.Connection[Any], project_id: uuid.UUID, entry_id: uuid.UUID) -> dict[str, Any] | None:
    """One live entry of a project."""
    return conn.execute(
        _ENTRY_SELECT + " WHERE te.id = %s AND te.project_id = %s AND te.archived_at IS NULL",
        (entry_id, project_id),
    ).fetchone()


def list_for_project(
    conn: psycopg.Connection[Any],
    project_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None,
    start: dt.date | None,
    end: dt.date | None,
) -> list[dict[str, Any]]:
    """Live entries of a project, newest first, optionally for one person and date range."""
    return conn.execute(
        _ENTRY_SELECT
        + """
        WHERE te.project_id = %s AND te.archived_at IS NULL
          AND (%s::uuid IS NULL OR te.user_id = %s)
          AND (%s::date IS NULL OR te.work_date >= %s)
          AND (%s::date IS NULL OR te.work_date <= %s)
        ORDER BY te.work_date DESC, te.created_at DESC
        """,
        (project_id, user_id, user_id, start, start, end, end),
    ).fetchall()


def list_for_user(
    conn: psycopg.Connection[Any], user_id: uuid.UUID, start: dt.date, end: dt.date
) -> list[dict[str, Any]]:
    """A person's live entries across projects in a date range, newest first."""
    return conn.execute(
        _ENTRY_SELECT
        + " WHERE te.user_id = %s AND te.archived_at IS NULL AND te.work_date >= %s AND te.work_date <= %s "
        "ORDER BY te.work_date DESC, te.created_at DESC",
        (user_id, start, end),
    ).fetchall()


def archive(conn: psycopg.Connection[Any], entry_id: uuid.UUID) -> None:
    """Remove an entry (archived, not deleted)."""
    conn.execute("UPDATE time_entries SET archived_at = now() WHERE id = %s", (entry_id,))


def date_range(conn: psycopg.Connection[Any], project_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
    """First and last day a person logged time on a project."""
    row = conn.execute(
        "SELECT min(work_date) AS first, max(work_date) AS last FROM time_entries "
        "WHERE project_id = %s AND user_id = %s AND archived_at IS NULL",
        (project_id, user_id),
    ).fetchone()
    return row or {"first": None, "last": None}


def hours_by_user(
    conn: psycopg.Connection[Any], user_ids: list[uuid.UUID], start: dt.date, end: dt.date
) -> dict[uuid.UUID, float]:
    """Hours each person logged in a date range (all projects)."""
    if not user_ids:
        return {}
    rows = conn.execute(
        "SELECT user_id, sum(hours) AS n FROM time_entries WHERE user_id = ANY(%s) AND archived_at IS NULL "
        "AND work_date >= %s AND work_date <= %s GROUP BY user_id",
        (user_ids, start, end),
    ).fetchall()
    return {r["user_id"]: float(r["n"]) for r in rows}
