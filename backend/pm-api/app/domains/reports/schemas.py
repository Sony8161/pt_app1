"""Pydantic models for reports."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.domains.projects.schemas import ProjectOut
from app.domains.time_entries.schemas import TimeEntryOut


class OverviewCounts(BaseModel):
    """Projects by lifecycle and by health."""

    projects: int
    planned: int
    active: int
    completed: int
    on_track: int
    at_risk: int
    overdue: int


class OverviewTotals(BaseModel):
    """Money and hours across the listed projects."""

    budget: float
    spent: float
    labor_cost: float
    other_cost: float
    budget_remaining: float
    hours_allocated: float
    hours_logged: float


class ProjectRef(BaseModel):
    """A project reference with its dates."""

    id: uuid.UUID
    name: str
    start_date: dt.date
    end_date: dt.date


class PersonAllocation(BaseModel):
    """Where one employee's time goes."""

    user_id: uuid.UUID
    name: str
    job_title: str
    manager_name: str | None
    state: Literal["allocated", "available"]
    current_project: ProjectRef | None
    next_project: ProjectRef | None
    hours_this_week: float
    week_capacity: int = Field(description="Working hours in a full week (5 x 8)")


class Overview(BaseModel):
    """Everything the manager or admin dashboard shows."""

    as_of: dt.date
    counts: OverviewCounts
    totals: OverviewTotals
    projects: list[ProjectOut] = Field(description="Most urgent first: overdue, at risk, on track, planned, done")
    allocation: list[PersonAllocation]
    available_people: int


class MyDashboard(BaseModel):
    """The signed-in person's own view."""

    as_of: dt.date
    current_project: ProjectRef | None
    projects: list[ProjectOut]
    hours_today: float
    hours_today_remaining: float
    hours_this_week: float
    week_capacity: int
    recent_entries: list[TimeEntryOut]
