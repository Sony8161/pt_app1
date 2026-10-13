"""Dashboards built from projects, assignments and logged time."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg

from app.core import dates
from app.core.deps import CurrentUser
from app.domains.assignments import repository as assignments_repo
from app.domains.projects import repository as projects_repo
from app.domains.projects import service as projects_service
from app.domains.projects.schemas import ProjectOut
from app.domains.reports.schemas import (
    MyDashboard,
    Overview,
    OverviewCounts,
    OverviewTotals,
    PersonAllocation,
    ProjectRef,
)
from app.domains.time_entries import repository as time_repo
from app.domains.time_entries import service as time_service

_URGENCY = {"overdue": 0, "at_risk": 1, "on_track": 2, "done": 3}
_STATUS_ORDER = {"active": 0, "planned": 1, "completed": 2}


def _ref(row: dict[str, Any] | None) -> ProjectRef | None:
    if row is None:
        return None
    return ProjectRef(id=row["project_id"], name=row["project_name"], start_date=row["start_date"], end_date=row["end_date"])


def _people_in_scope(conn: psycopg.Connection[Any], actor: CurrentUser) -> list[dict[str, Any]]:
    """Active employees an admin or manager should see in the allocation view."""
    if actor.is_admin:
        return conn.execute(
            "SELECT u.id, u.name, u.job_title, m.name AS manager_name FROM users u "
            "LEFT JOIN users m ON m.id = u.manager_id "
            "WHERE u.role = 'employee' AND u.archived_at IS NULL ORDER BY lower(u.name)"
        ).fetchall()
    return conn.execute(
        """
        SELECT u.id, u.name, u.job_title, m.name AS manager_name FROM users u
        LEFT JOIN users m ON m.id = u.manager_id
        WHERE u.role = 'employee' AND u.archived_at IS NULL
          AND (u.manager_id = %(me)s OR EXISTS (
                SELECT 1 FROM project_assignments a JOIN projects p ON p.id = a.project_id
                WHERE a.user_id = u.id AND a.archived_at IS NULL AND p.manager_id = %(me)s))
        ORDER BY lower(u.name)
        """,
        {"me": actor.id},
    ).fetchall()


def overview(conn: psycopg.Connection[Any], actor: CurrentUser) -> Overview:
    """Health of every project in scope, money and hours totals, and who is allocated where."""
    today = dates.today()
    rows, _ = projects_repo.search(
        conn, today=today, viewer_id=actor.id, viewer_role=actor.role, include_archived=False, limit=500, offset=0
    )
    projects: list[ProjectOut] = [projects_service.present(r, actor) for r in rows]
    projects.sort(key=lambda p: (_URGENCY[p.summary.risk_level], _STATUS_ORDER.get(p.status, 9), p.end_date))

    counts = OverviewCounts(
        projects=len(projects),
        planned=sum(p.status == "planned" for p in projects),
        active=sum(p.status == "active" for p in projects),
        completed=sum(p.status == "completed" for p in projects),
        on_track=sum(p.summary.risk_level == "on_track" for p in projects),
        at_risk=sum(p.summary.risk_level == "at_risk" for p in projects),
        overdue=sum(p.summary.risk_level == "overdue" for p in projects),
    )
    budget = sum(p.budget_amount or 0 for p in projects)
    labor = sum(p.summary.labor_cost or 0 for p in projects)
    other = sum(p.summary.other_cost or 0 for p in projects)
    totals = OverviewTotals(
        budget=round(budget, 2),
        spent=round(labor + other, 2),
        labor_cost=round(labor, 2),
        other_cost=round(other, 2),
        budget_remaining=round(budget - labor - other, 2),
        hours_allocated=round(sum(p.allocated_hours for p in projects), 2),
        hours_logged=round(sum(p.summary.hours_logged for p in projects), 2),
    )

    people = _people_in_scope(conn, actor)
    ids: list[uuid.UUID] = [p["id"] for p in people]
    slots = assignments_repo.allocation_for(conn, ids, today)
    week = dates.week_start(today)
    logged = time_repo.hours_by_user(conn, ids, week, week + dt.timedelta(days=6))
    allocation = [
        PersonAllocation(
            user_id=p["id"],
            name=p["name"],
            job_title=p["job_title"],
            manager_name=p["manager_name"],
            state="allocated" if slots.get(p["id"], {}).get("current") else "available",
            current_project=_ref(slots.get(p["id"], {}).get("current")),
            next_project=_ref(slots.get(p["id"], {}).get("next")),
            hours_this_week=round(logged.get(p["id"], 0.0), 2),
            week_capacity=dates.WORK_WEEK_HOURS,
        )
        for p in people
    ]
    return Overview(
        as_of=today,
        counts=counts,
        totals=totals,
        projects=projects,
        allocation=allocation,
        available_people=sum(a.state == "available" for a in allocation),
    )


def my_dashboard(conn: psycopg.Connection[Any], actor: CurrentUser) -> MyDashboard:
    """The signed-in person's projects, today's hours and recent entries."""
    today = dates.today()
    rows, _ = projects_repo.search(
        conn, today=today, viewer_id=actor.id, viewer_role=actor.role, include_archived=False, limit=20, offset=0
    )
    projects = [projects_service.present(r, actor) for r in rows]
    slots = assignments_repo.allocation_for(conn, [actor.id], today).get(actor.id, {})
    week = dates.week_start(today)
    hours_today = time_repo.day_total(conn, actor.id, today)
    hours_week = time_repo.hours_by_user(conn, [actor.id], week, week + dt.timedelta(days=6)).get(actor.id, 0.0)
    recent = time_service.my_time(conn, actor, None, None).items[:5]
    return MyDashboard(
        as_of=today,
        current_project=_ref(slots.get("current")),
        projects=projects,
        hours_today=round(hours_today, 2),
        hours_today_remaining=round(max(dates.DAILY_HOURS - hours_today, 0), 2),
        hours_this_week=round(hours_week, 2),
        week_capacity=dates.WORK_WEEK_HOURS,
        recent_entries=recent,
    )
