"""Dashboards built from projects and milestone assignments.

Hours are never logged: every Monday-Friday inside an assignment is one 8-hour shift.
"""

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
    MyMilestone,
    Overview,
    OverviewCounts,
    OverviewTotals,
    PersonAllocation,
    WorkRef,
)

_URGENCY = {"overdue": 0, "at_risk": 1, "on_track": 2, "done": 3}
_STATUS_ORDER = {"active": 0, "planned": 1, "completed": 2}


def _ref(row: dict[str, Any] | None) -> WorkRef | None:
    if row is None:
        return None
    return WorkRef(
        project_id=row["project_id"],
        project_name=row["project_name"],
        milestone_id=row["milestone_id"],
        milestone_name=row["milestone_name"],
        start_date=row["start_date"],
        end_date=row["end_date"],
    )


def _week_hours(conn: psycopg.Connection[Any], ids: list[uuid.UUID], today: dt.date) -> dict[uuid.UUID, float]:
    """Hours worked from Monday of this week up to today."""
    return assignments_repo.hours_between(conn, ids, dates.week_start(today), today)


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
                SELECT 1 FROM milestone_assignments a
                JOIN milestones ms ON ms.id = a.milestone_id
                JOIN projects p ON p.id = ms.project_id
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
        forecast_cost=round(sum(p.summary.forecast_cost or 0 for p in projects), 2),
        hours_allocated=round(sum(p.allocated_hours for p in projects), 2),
        hours_worked=round(sum(p.summary.hours_worked for p in projects), 2),
    )

    people = _people_in_scope(conn, actor)
    ids: list[uuid.UUID] = [p["id"] for p in people]
    slots = assignments_repo.allocation_for(conn, ids, today)
    worked = _week_hours(conn, ids, today)
    allocation = [
        PersonAllocation(
            user_id=p["id"],
            name=p["name"],
            job_title=p["job_title"],
            manager_name=p["manager_name"],
            state="allocated" if slots.get(p["id"], {}).get("current") else "available",
            current_work=_ref(slots.get(p["id"], {}).get("current")),
            next_work=_ref(slots.get(p["id"], {}).get("next")),
            hours_this_week=round(worked.get(p["id"], 0.0), 2),
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
    """The signed-in person's projects, milestones and shifts."""
    today = dates.today()
    rows, _ = projects_repo.search(
        conn, today=today, viewer_id=actor.id, viewer_role=actor.role, include_archived=False, limit=20, offset=0
    )
    projects = [projects_service.present(r, actor) for r in rows]
    slots = assignments_repo.allocation_for(conn, [actor.id], today).get(actor.id, {})
    current = slots.get("current")
    work = assignments_repo.my_work(conn, actor.id, today)
    week = _week_hours(conn, [actor.id], today).get(actor.id, 0.0)
    return MyDashboard(
        as_of=today,
        current_work=_ref(current),
        my_milestones=[
            MyMilestone(
                project_id=w["project_id"],
                project_name=w["project_name"],
                milestone_id=w["milestone_id"],
                milestone_name=w["milestone_name"],
                status=w["milestone_status"],
                start_date=w["start_date"],
                end_date=w["end_date"],
                due_date=w["due_date"],
                deliverables_total=int(w["deliverables_total"]),
                deliverables_done=int(w["deliverables_done"]),
            )
            for w in work
        ],
        projects=projects,
        hours_today=float(dates.DAILY_HOURS) if current and today.weekday() < 5 else 0.0,
        hours_this_week=round(week, 2),
        week_capacity=dates.WORK_WEEK_HOURS,
    )
