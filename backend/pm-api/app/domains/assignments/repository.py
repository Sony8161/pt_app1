"""SQL access for ``milestone_assignments``.

An assignment puts one employee on one milestone for a date range. Every Monday-Friday in that
range is one 8-hour shift, so hours and labor cost are calculated (``working_days(...) * 8``)
rather than logged. Worked time only counts up to *today*.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg

# The 8 in these queries is core.dates.DAILY_HOURS (a test keeps them in step).
_ROW = """
    SELECT a.id, a.milestone_id, m.name AS milestone_name, m.project_id, m.archived_at AS milestone_archived_at,
           a.user_id, u.name, u.username, u.email, u.job_title,
           a.start_date, a.end_date, a.archived_at, a.created_at,
           working_days(a.start_date, LEAST(a.end_date, %(today)s))             AS days_worked,
           working_days(a.start_date, LEAST(a.end_date, %(today)s))* 8              AS hours_worked,
           working_days(a.start_date, LEAST(a.end_date, %(today)s))* 8 * u.salary   AS labor_cost
    FROM milestone_assignments a
    JOIN milestones m ON m.id = a.milestone_id
    JOIN users u ON u.id = a.user_id
"""

# Ends work today: assignments that have started stop at today, ones that never started are archived.
_END = """
    UPDATE milestone_assignments
    SET archived_at = CASE WHEN start_date > %(today)s THEN now() ELSE archived_at END,
        end_date    = CASE WHEN start_date > %(today)s THEN end_date ELSE LEAST(end_date, %(today)s) END
    WHERE archived_at IS NULL AND
"""


def lock_user(conn: psycopg.Connection[Any], user_id: uuid.UUID) -> None:
    """Serialise concurrent assignment changes for one person."""
    conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))


def get_active(conn: psycopg.Connection[Any], milestone_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any] | None:
    """The live assignment of ``user_id`` on ``milestone_id``."""
    return conn.execute(
        "SELECT * FROM milestone_assignments WHERE milestone_id = %s AND user_id = %s AND archived_at IS NULL",
        (milestone_id, user_id),
    ).fetchone()


def list_for_milestone(
    conn: psycopg.Connection[Any], milestone_id: uuid.UUID, today: dt.date, *, include_archived: bool = False
) -> list[dict[str, Any]]:
    """People on a milestone with the hours and cost they have accumulated so far."""
    return conn.execute(
        _ROW + " WHERE a.milestone_id = %(mid)s AND (%(arch)s OR a.archived_at IS NULL) ORDER BY a.start_date, lower(u.name)",
        {"today": today, "mid": milestone_id, "arch": include_archived},
    ).fetchall()


def list_for_project(
    conn: psycopg.Connection[Any], project_id: uuid.UUID, today: dt.date, *, include_archived: bool = False
) -> list[dict[str, Any]]:
    """Everyone working on any milestone of a project (archived milestones only when asked)."""
    return conn.execute(
        _ROW
        + " WHERE m.project_id = %(pid)s AND (%(arch)s OR (a.archived_at IS NULL AND m.archived_at IS NULL))"
        " ORDER BY m.start_date, lower(m.name), lower(u.name)",
        {"today": today, "pid": project_id, "arch": include_archived},
    ).fetchall()


def has_live_on_project(conn: psycopg.Connection[Any], project_id: uuid.UUID, user_id: uuid.UUID, today: dt.date) -> bool:
    """True when the person is on, or about to start, a current (not archived) milestone of the project.

    Someone who was removed or whose assignment ended keeps the row (their worked days stay on record) but no
    longer sees the project: the work must end today or later.
    """
    return (
        conn.execute(
            "SELECT 1 FROM milestone_assignments a JOIN milestones m ON m.id = a.milestone_id "
            "WHERE m.project_id = %s AND a.user_id = %s AND a.archived_at IS NULL AND m.archived_at IS NULL "
            "AND a.end_date >= %s",
            (project_id, user_id, today),
        ).fetchone()
        is not None
    )


def find_overlap(
    conn: psycopg.Connection[Any],
    user_id: uuid.UUID,
    start: dt.date,
    end: dt.date,
    *,
    exclude_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Another live assignment of this person overlapping ``start``..``end`` (one milestone per day)."""
    return conn.execute(
        """
        SELECT a.id, a.start_date, a.end_date, m.id AS milestone_id, m.name AS milestone_name,
               p.id AS project_id, p.name AS project_name
        FROM milestone_assignments a
        JOIN milestones m ON m.id = a.milestone_id
        JOIN projects p ON p.id = m.project_id
        WHERE a.user_id = %s AND a.archived_at IS NULL
          AND a.start_date <= %s AND a.end_date >= %s
          AND (%s::uuid IS NULL OR a.id <> %s)
        ORDER BY a.start_date LIMIT 1
        """,
        (user_id, end, start, exclude_id, exclude_id),
    ).fetchone()


def insert(
    conn: psycopg.Connection[Any],
    *,
    milestone_id: uuid.UUID,
    user_id: uuid.UUID,
    start_date: dt.date,
    end_date: dt.date,
    assigned_by: uuid.UUID,
) -> dict[str, Any]:
    """Create an assignment."""
    row = conn.execute(
        "INSERT INTO milestone_assignments (milestone_id, user_id, start_date, end_date, assigned_by) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING *",
        (milestone_id, user_id, start_date, end_date, assigned_by),
    ).fetchone()
    if row is None:  # pragma: no cover - RETURNING always yields the inserted row
        raise RuntimeError("INSERT INTO milestone_assignments returned no row")
    return row


def update_dates(conn: psycopg.Connection[Any], assignment_id: uuid.UUID, start_date: dt.date, end_date: dt.date) -> None:
    """Change the date range of an assignment."""
    conn.execute(
        "UPDATE milestone_assignments SET start_date = %s, end_date = %s WHERE id = %s",
        (start_date, end_date, assignment_id),
    )


def end_assignment(conn: psycopg.Connection[Any], assignment_id: uuid.UUID, today: dt.date) -> None:
    """Take one person off a milestone: they work until today, or the row is archived if they never started."""
    conn.execute(_END + "id = %(id)s", {"today": today, "id": assignment_id})


def end_for_milestone(conn: psycopg.Connection[Any], milestone_id: uuid.UUID, today: dt.date) -> None:
    """End everyone's work on a milestone (completed or cancelled)."""
    conn.execute(_END + "milestone_id = %(id)s", {"today": today, "id": milestone_id})


def end_for_project(conn: psycopg.Connection[Any], project_id: uuid.UUID, today: dt.date) -> None:
    """End everyone's work on a project (completed or archived)."""
    where = "milestone_id IN (SELECT id FROM milestones WHERE project_id = %(id)s)"
    conn.execute(_END + where, {"today": today, "id": project_id})  # noqa: S608 - constant SQL fragments only


def end_for_user(conn: psycopg.Connection[Any], user_id: uuid.UUID, today: dt.date) -> None:
    """End all of a person's work (their account was archived)."""
    conn.execute(_END + "user_id = %(id)s", {"today": today, "id": user_id})


def bounds_for_milestone(conn: psycopg.Connection[Any], milestone_id: uuid.UUID) -> dict[str, Any]:
    """Earliest start and latest end among a milestone's live assignments."""
    row = conn.execute(
        "SELECT min(start_date) AS first_start, max(end_date) AS last_end FROM milestone_assignments "
        "WHERE milestone_id = %s AND archived_at IS NULL",
        (milestone_id,),
    ).fetchone()
    return row or {"first_start": None, "last_end": None}


_WORK_REF = """
    SELECT a.user_id, a.start_date, a.end_date, m.id AS milestone_id, m.name AS milestone_name,
           p.id AS project_id, p.name AS project_name
    FROM milestone_assignments a
    JOIN milestones m ON m.id = a.milestone_id
    JOIN projects p ON p.id = m.project_id
    WHERE a.archived_at IS NULL AND m.archived_at IS NULL AND p.archived_at IS NULL
      AND p.status <> 'completed' AND a.end_date >= %(today)s AND a.user_id = ANY(%(ids)s)
    ORDER BY a.start_date
"""


def allocation_for(
    conn: psycopg.Connection[Any], user_ids: list[uuid.UUID], today: dt.date
) -> dict[uuid.UUID, dict[str, Any]]:
    """Per person: the milestone they work on today (if any) and the next one."""
    if not user_ids:
        return {}
    rows = conn.execute(_WORK_REF, {"today": today, "ids": user_ids}).fetchall()
    result: dict[uuid.UUID, dict[str, Any]] = {}
    for row in rows:
        entry = result.setdefault(row["user_id"], {"current": None, "next": None})
        if row["start_date"] <= today and entry["current"] is None:
            entry["current"] = row
        elif row["start_date"] > today and entry["next"] is None:
            entry["next"] = row
    return result


def hours_between(
    conn: psycopg.Connection[Any], user_ids: list[uuid.UUID], start: dt.date, end: dt.date
) -> dict[uuid.UUID, float]:
    """Scheduled hours (working days x 8) each person has inside ``start``..``end``, across all milestones."""
    if not user_ids:
        return {}
    rows = conn.execute(
        "SELECT user_id, sum(working_days(GREATEST(start_date, %s), LEAST(end_date, %s))) * 8 AS n "
        "FROM milestone_assignments WHERE user_id = ANY(%s) AND archived_at IS NULL GROUP BY user_id",
        (start, end, user_ids),
    ).fetchall()
    return {r["user_id"]: float(r["n"]) for r in rows}


def my_work(conn: psycopg.Connection[Any], user_id: uuid.UUID, today: dt.date) -> list[dict[str, Any]]:
    """A person's current and upcoming milestones with deliverable progress."""
    return conn.execute(
        """
        SELECT a.start_date, a.end_date, m.id AS milestone_id, m.name AS milestone_name, m.status AS milestone_status,
               m.due_date, p.id AS project_id, p.name AS project_name,
               (SELECT count(*) FROM deliverables d WHERE d.milestone_id = m.id AND d.archived_at IS NULL) AS deliverables_total,
               (SELECT count(*) FROM deliverables d WHERE d.milestone_id = m.id AND d.archived_at IS NULL AND d.done)
                   AS deliverables_done
        FROM milestone_assignments a
        JOIN milestones m ON m.id = a.milestone_id
        JOIN projects p ON p.id = m.project_id
        WHERE a.user_id = %(uid)s AND a.archived_at IS NULL AND m.archived_at IS NULL AND p.archived_at IS NULL
          AND a.end_date >= %(today)s
        ORDER BY a.start_date
        """,
        {"uid": user_id, "today": today},
    ).fetchall()
