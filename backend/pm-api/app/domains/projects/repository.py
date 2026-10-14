"""SQL access for ``projects``.

Reads go through one query (``PROJECT_ROWS``) that also returns the numbers every
screen needs: hours, labor cost, other costs, milestone counts and team size. A project
whose stored status is ``planned`` is reported as ``active`` once its start date has
arrived, so nobody has to flip the status by hand.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg
from psycopg import sql

PROJECT_ROWS = sql.SQL(
    """
    SELECT p.id, p.name, p.description, p.manager_id, mu.name AS manager_name,
           CASE WHEN p.status = 'planned' AND p.start_date <= %(today)s THEN 'active' ELSE p.status END AS status,
           p.start_date, p.end_date, p.allocated_hours, p.budget_amount,
           p.completed_at, p.archived_at, p.created_by, p.created_at, p.updated_at,
           COALESCE(t.hours, 0)         AS hours_worked,
           COALESCE(t.labor, 0)         AS labor_cost,
           COALESCE(t.forecast, 0)      AS forecast_cost,
           COALESCE(c.total, 0)         AS other_cost,
           COALESCE(ms.total, 0)        AS milestones_total,
           COALESCE(ms.done, 0)         AS milestones_done,
           COALESCE(ms.overdue, 0)      AS milestones_overdue,
           COALESCE(t.people, 0)        AS team_size
    FROM projects p
    JOIN users mu ON mu.id = p.manager_id
    LEFT JOIN LATERAL (
        -- Every Monday-Friday of an assignment is an 8-hour shift; worked time counts up to today,
        -- the forecast counts the whole planned range.
        SELECT sum(working_days(a.start_date, LEAST(a.end_date, %(today)s))) * 8                      AS hours,
               sum(working_days(a.start_date, LEAST(a.end_date, %(today)s)) * 8 * u.salary)            AS labor,
               sum(working_days(a.start_date, a.end_date) * 8 * u.salary)                              AS forecast,
               count(DISTINCT a.user_id)                                                               AS people
        FROM milestone_assignments a
        JOIN milestones m ON m.id = a.milestone_id
        JOIN users u ON u.id = a.user_id
        WHERE m.project_id = p.id AND a.archived_at IS NULL
    ) t ON true
    LEFT JOIN LATERAL (
        SELECT sum(amount) AS total FROM project_costs
        WHERE project_id = p.id AND archived_at IS NULL
    ) c ON true
    LEFT JOIN LATERAL (
        -- Completed milestones are archived but still count; cancelled ones (archived, not completed) do not.
        SELECT count(*) FILTER (WHERE archived_at IS NULL OR status = 'completed')                    AS total,
               count(*) FILTER (WHERE status = 'completed')                                           AS done,
               count(*) FILTER (WHERE status <> 'completed' AND archived_at IS NULL AND due_date < %(today)s) AS overdue
        FROM milestones WHERE project_id = p.id
    ) ms ON true
    """
)

_EDITABLE = frozenset({"name", "description", "manager_id", "start_date", "end_date", "allocated_hours", "budget_amount"})


def get(conn: psycopg.Connection[Any], project_id: uuid.UUID, today: dt.date) -> dict[str, Any] | None:
    """One project with its rollup numbers (no permission check)."""
    query = sql.SQL("SELECT * FROM ({rows}) q WHERE q.id = %(id)s").format(rows=PROJECT_ROWS)
    return conn.execute(query, {"today": today, "id": project_id}).fetchone()


def search(
    conn: psycopg.Connection[Any],
    *,
    today: dt.date,
    viewer_id: uuid.UUID,
    viewer_role: str,
    q: str | None = None,
    status: str | None = None,
    manager_id: uuid.UUID | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Projects the viewer may see, filtered and paged. Returns ``(rows, total)``."""
    params: dict[str, Any] = {"today": today, "viewer": viewer_id, "limit": limit, "offset": offset}
    where: list[sql.Composable] = [sql.SQL("TRUE")]

    if viewer_role == "manager":
        where.append(sql.SQL("q.manager_id = %(viewer)s"))
    elif viewer_role == "employee":
        where.append(
            sql.SQL(
                "EXISTS (SELECT 1 FROM milestone_assignments a JOIN milestones m ON m.id = a.milestone_id "
                "WHERE m.project_id = q.id AND a.user_id = %(viewer)s AND a.archived_at IS NULL AND m.archived_at IS NULL "
                "AND a.end_date >= %(today)s)"
            )
        )
    if not include_archived:
        where.append(sql.SQL("q.archived_at IS NULL"))
    if status:
        where.append(sql.SQL("q.status = %(status)s"))
        params["status"] = status
    if manager_id is not None:
        where.append(sql.SQL("q.manager_id = %(manager_id)s"))
        params["manager_id"] = manager_id
    if q:
        where.append(sql.SQL("(q.name ILIKE %(like)s OR q.description ILIKE %(like)s OR q.manager_name ILIKE %(like)s)"))
        params["like"] = f"%{q}%"

    condition = sql.SQL(" AND ").join(where)
    count_query = sql.SQL("SELECT count(*) AS n FROM ({rows}) q WHERE {cond}").format(rows=PROJECT_ROWS, cond=condition)
    total_row = conn.execute(count_query, params).fetchone()
    page_query = sql.SQL(
        "SELECT * FROM ({rows}) q WHERE {cond} ORDER BY q.end_date, lower(q.name) LIMIT %(limit)s OFFSET %(offset)s"
    ).format(rows=PROJECT_ROWS, cond=condition)
    return conn.execute(page_query, params).fetchall(), int(total_row["n"]) if total_row else 0


def name_taken(conn: psycopg.Connection[Any], name: str, *, exclude_id: uuid.UUID | None = None) -> bool:
    """True when another non-archived project already uses ``name`` (case-insensitive)."""
    row = conn.execute(
        "SELECT 1 FROM projects WHERE lower(name) = lower(%s) AND archived_at IS NULL "
        "AND (%s::uuid IS NULL OR id <> %s)",
        (name, exclude_id, exclude_id),
    ).fetchone()
    return row is not None


def insert(
    conn: psycopg.Connection[Any],
    *,
    name: str,
    description: str,
    manager_id: uuid.UUID,
    start_date: dt.date,
    end_date: dt.date,
    allocated_hours: float,
    budget_amount: float,
    created_by: uuid.UUID,
) -> uuid.UUID:
    """Create a project and return its id."""
    row = conn.execute(
        """
        INSERT INTO projects (name, description, manager_id, start_date, end_date,
                              allocated_hours, budget_amount, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (name, description, manager_id, start_date, end_date, allocated_hours, budget_amount, created_by),
    ).fetchone()
    if row is None:  # pragma: no cover - RETURNING always yields the inserted row
        raise RuntimeError("INSERT INTO projects returned no row")
    return row["id"]


def update(conn: psycopg.Connection[Any], project_id: uuid.UUID, fields: dict[str, Any]) -> None:
    """Update editable columns (anything else is ignored)."""
    clean = {k: v for k, v in fields.items() if k in _EDITABLE}
    if not clean:
        return
    sets = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in clean)
    conn.execute(sql.SQL("UPDATE projects SET {sets} WHERE id = %s").format(sets=sets), (*clean.values(), project_id))


def set_status(
    conn: psycopg.Connection[Any],
    project_id: uuid.UUID,
    status: str,
    *,
    completed_at: dt.datetime | None = None,
    archived_at: dt.datetime | None = None,
) -> None:
    """Set lifecycle status together with its timestamps."""
    conn.execute(
        "UPDATE projects SET status = %s, completed_at = %s, archived_at = %s WHERE id = %s",
        (status, completed_at, archived_at, project_id),
    )


def count_open_owned(conn: psycopg.Connection[Any], manager_id: uuid.UUID) -> int:
    """Non-archived projects a manager owns."""
    row = conn.execute(
        "SELECT count(*) AS n FROM projects WHERE manager_id = %s AND archived_at IS NULL", (manager_id,)
    ).fetchone()
    return int(row["n"]) if row else 0
