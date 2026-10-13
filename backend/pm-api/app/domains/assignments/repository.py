"""SQL access for ``project_assignments``."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg


def lock_user(conn: psycopg.Connection[Any], user_id: uuid.UUID) -> None:
    """Serialise concurrent changes for one person (assignments and time entries)."""
    conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))


def get(conn: psycopg.Connection[Any], assignment_id: uuid.UUID) -> dict[str, Any] | None:
    """One assignment row."""
    return conn.execute("SELECT * FROM project_assignments WHERE id = %s", (assignment_id,)).fetchone()


def get_active(conn: psycopg.Connection[Any], project_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any] | None:
    """The live (not archived) assignment of ``user_id`` on ``project_id``."""
    return conn.execute(
        "SELECT * FROM project_assignments WHERE project_id = %s AND user_id = %s AND archived_at IS NULL",
        (project_id, user_id),
    ).fetchone()


def covering(
    conn: psycopg.Connection[Any], project_id: uuid.UUID, user_id: uuid.UUID, day: dt.date
) -> dict[str, Any] | None:
    """The live assignment of ``user_id`` on ``project_id`` that includes ``day``."""
    return conn.execute(
        "SELECT * FROM project_assignments WHERE project_id = %s AND user_id = %s AND archived_at IS NULL "
        "AND start_date <= %s AND end_date >= %s",
        (project_id, user_id, day, day),
    ).fetchone()


def list_for_project(conn: psycopg.Connection[Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Team of a project with each member's logged hours and labor cost."""
    return conn.execute(
        """
        SELECT a.id, a.project_id, a.user_id, a.start_date, a.end_date, a.created_at,
               u.name, u.username, u.email, u.job_title,
               COALESCE(t.hours, 0) AS hours_logged,
               COALESCE(t.hours, 0) * u.salary AS labor_cost
        FROM project_assignments a
        JOIN users u ON u.id = a.user_id
        LEFT JOIN LATERAL (
            SELECT sum(hours) AS hours FROM time_entries
            WHERE project_id = a.project_id AND user_id = a.user_id AND archived_at IS NULL
        ) t ON true
        WHERE a.project_id = %s AND a.archived_at IS NULL
        ORDER BY a.start_date, lower(u.name)
        """,
        (project_id,),
    ).fetchall()


def find_overlap(
    conn: psycopg.Connection[Any],
    user_id: uuid.UUID,
    start: dt.date,
    end: dt.date,
    *,
    exclude_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Another live assignment of this person that overlaps ``start``..``end`` (with project info)."""
    return conn.execute(
        """
        SELECT a.id, a.start_date, a.end_date, p.id AS project_id, p.name AS project_name
        FROM project_assignments a JOIN projects p ON p.id = a.project_id
        WHERE a.user_id = %s AND a.archived_at IS NULL AND p.archived_at IS NULL
          AND a.start_date <= %s AND a.end_date >= %s
          AND (%s::uuid IS NULL OR a.id <> %s)
        ORDER BY a.start_date LIMIT 1
        """,
        (user_id, end, start, exclude_id, exclude_id),
    ).fetchone()


def insert(
    conn: psycopg.Connection[Any],
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    start_date: dt.date,
    end_date: dt.date,
    assigned_by: uuid.UUID,
) -> dict[str, Any]:
    """Create an assignment."""
    row = conn.execute(
        """
        INSERT INTO project_assignments (project_id, user_id, start_date, end_date, assigned_by)
        VALUES (%s, %s, %s, %s, %s) RETURNING *
        """,
        (project_id, user_id, start_date, end_date, assigned_by),
    ).fetchone()
    if row is None:  # pragma: no cover - RETURNING always yields the inserted row
        raise RuntimeError("INSERT INTO project_assignments returned no row")
    return row


def update_dates(
    conn: psycopg.Connection[Any], assignment_id: uuid.UUID, start_date: dt.date, end_date: dt.date
) -> None:
    """Change the date range of an assignment."""
    conn.execute(
        "UPDATE project_assignments SET start_date = %s, end_date = %s WHERE id = %s",
        (start_date, end_date, assignment_id),
    )


def archive(conn: psycopg.Connection[Any], assignment_id: uuid.UUID) -> None:
    """Remove a person from a project (the row is kept as history)."""
    conn.execute("UPDATE project_assignments SET archived_at = now() WHERE id = %s", (assignment_id,))


def archive_for_user(conn: psycopg.Connection[Any], user_id: uuid.UUID) -> int:
    """Archive every live assignment of a person (used when the account is archived)."""
    cur = conn.execute(
        "UPDATE project_assignments SET archived_at = now() WHERE user_id = %s AND archived_at IS NULL", (user_id,)
    )
    return cur.rowcount


def release_project(conn: psycopg.Connection[Any], project_id: uuid.UUID, today: dt.date) -> None:
    """End a finished project's assignments today so those people are free for new work."""
    conn.execute(
        """
        UPDATE project_assignments
        SET end_date = GREATEST(start_date, LEAST(end_date, %s))
        WHERE project_id = %s AND archived_at IS NULL
        """,
        (today, project_id),
    )


def bounds_for_project(conn: psycopg.Connection[Any], project_id: uuid.UUID) -> dict[str, Any]:
    """Earliest start and latest end among a project's live assignments (for date-range checks)."""
    row = conn.execute(
        "SELECT min(start_date) AS first_start, max(end_date) AS last_end FROM project_assignments "
        "WHERE project_id = %s AND archived_at IS NULL",
        (project_id,),
    ).fetchone()
    return row or {"first_start": None, "last_end": None}


def allocation_for(
    conn: psycopg.Connection[Any], user_ids: list[uuid.UUID], today: dt.date
) -> dict[uuid.UUID, dict[str, Any]]:
    """Per person: current project (if any) and the next upcoming one."""
    if not user_ids:
        return {}
    rows = conn.execute(
        """
        SELECT a.user_id, a.start_date, a.end_date, p.id AS project_id, p.name AS project_name
        FROM project_assignments a JOIN projects p ON p.id = a.project_id
        WHERE a.user_id = ANY(%s) AND a.archived_at IS NULL AND p.archived_at IS NULL
          AND p.status <> 'completed' AND a.end_date >= %s
        ORDER BY a.start_date
        """,
        (user_ids, today),
    ).fetchall()
    result: dict[uuid.UUID, dict[str, Any]] = {}
    for row in rows:
        entry = result.setdefault(row["user_id"], {"current": None, "next": None})
        if row["start_date"] <= today and entry["current"] is None:
            entry["current"] = row
        elif row["start_date"] > today and entry["next"] is None:
            entry["next"] = row
    return result
