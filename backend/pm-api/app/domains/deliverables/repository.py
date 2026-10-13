"""SQL access for ``deliverables`` (the checklist a manager reviews before completing a milestone)."""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
from psycopg import sql

_EDITABLE = frozenset({"name", "description"})


def list_for_milestone(
    conn: psycopg.Connection[Any], milestone_id: uuid.UUID, *, include_archived: bool = False
) -> list[dict[str, Any]]:
    """Deliverables of a milestone in creation order; archived ones only when asked (admins)."""
    return conn.execute(
        "SELECT * FROM deliverables WHERE milestone_id = %s AND (%s OR archived_at IS NULL) ORDER BY created_at, lower(name)",
        (milestone_id, include_archived),
    ).fetchall()


def get(
    conn: psycopg.Connection[Any], milestone_id: uuid.UUID, deliverable_id: uuid.UUID, *, include_archived: bool = False
) -> dict[str, Any] | None:
    """One deliverable of a milestone."""
    return conn.execute(
        "SELECT * FROM deliverables WHERE id = %s AND milestone_id = %s AND (%s OR archived_at IS NULL)",
        (deliverable_id, milestone_id, include_archived),
    ).fetchone()


def name_taken(
    conn: psycopg.Connection[Any], milestone_id: uuid.UUID, name: str, *, exclude_id: uuid.UUID | None = None
) -> bool:
    """True when the milestone already has a live deliverable with this name (case-insensitive)."""
    return (
        conn.execute(
            "SELECT 1 FROM deliverables WHERE milestone_id = %s AND lower(name) = lower(%s) AND archived_at IS NULL "
            "AND (%s::uuid IS NULL OR id <> %s)",
            (milestone_id, name, exclude_id, exclude_id),
        ).fetchone()
        is not None
    )


def insert(conn: psycopg.Connection[Any], *, milestone_id: uuid.UUID, name: str, description: str) -> uuid.UUID:
    """Add a deliverable and return its id."""
    row = conn.execute(
        "INSERT INTO deliverables (milestone_id, name, description) VALUES (%s, %s, %s) RETURNING id",
        (milestone_id, name, description),
    ).fetchone()
    if row is None:  # pragma: no cover - RETURNING always yields the inserted row
        raise RuntimeError("INSERT INTO deliverables returned no row")
    return row["id"]


def update(conn: psycopg.Connection[Any], deliverable_id: uuid.UUID, fields: dict[str, Any]) -> None:
    """Edit name or description."""
    clean = {k: v for k, v in fields.items() if k in _EDITABLE}
    if not clean:
        return
    sets = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in clean)
    conn.execute(sql.SQL("UPDATE deliverables SET {sets} WHERE id = %s").format(sets=sets), (*clean.values(), deliverable_id))


def set_done(conn: psycopg.Connection[Any], deliverable_id: uuid.UUID, *, done: bool, user_id: uuid.UUID) -> None:
    """Tick or untick a deliverable, recording who and when."""
    conn.execute(
        "UPDATE deliverables SET done = %s, done_at = CASE WHEN %s THEN now() END, "
        "done_by = CASE WHEN %s THEN %s::uuid END WHERE id = %s",
        (done, done, done, user_id, deliverable_id),
    )


def archive(conn: psycopg.Connection[Any], deliverable_id: uuid.UUID) -> None:
    """Remove a deliverable from the checklist (archived, never deleted)."""
    conn.execute("UPDATE deliverables SET archived_at = now() WHERE id = %s", (deliverable_id,))


def open_names(conn: psycopg.Connection[Any], milestone_id: uuid.UUID) -> list[str]:
    """Names of live deliverables that are not ticked yet."""
    rows = conn.execute(
        "SELECT name FROM deliverables WHERE milestone_id = %s AND archived_at IS NULL AND NOT done ORDER BY created_at",
        (milestone_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def count_live(conn: psycopg.Connection[Any], milestone_id: uuid.UUID) -> int:
    """Number of live deliverables on a milestone."""
    row = conn.execute(
        "SELECT count(*) AS n FROM deliverables WHERE milestone_id = %s AND archived_at IS NULL", (milestone_id,)
    ).fetchone()
    return int(row["n"]) if row else 0
