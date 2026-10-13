"""Pydantic models for reports."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.domains.projects.schemas import ProjectOut


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
    forecast_cost: float = Field(description="Cost if everyone stays assigned for the whole planned range")
    hours_allocated: float
    hours_worked: float


class WorkRef(BaseModel):
    """The milestone someone works on, with its project."""

    project_id: uuid.UUID
    project_name: str
    milestone_id: uuid.UUID
    milestone_name: str
    start_date: dt.date
    end_date: dt.date


class PersonAllocation(BaseModel):
    """Where one employee's shifts go."""

    user_id: uuid.UUID
    name: str
    job_title: str
    manager_name: str | None
    state: Literal["allocated", "available"]
    current_work: WorkRef | None
    next_work: WorkRef | None
    hours_this_week: float = Field(description="Hours worked this week up to today (working days x 8)")
    week_capacity: int = Field(description="Working hours in a full week (5 x 8)")


class Overview(BaseModel):
    """Everything the manager or admin dashboard shows."""

    as_of: dt.date
    counts: OverviewCounts
    totals: OverviewTotals
    projects: list[ProjectOut] = Field(description="Most urgent first: overdue, at risk, on track, planned, done")
    allocation: list[PersonAllocation]
    available_people: int


class MyMilestone(BaseModel):
    """A milestone the signed-in person works on."""

    project_id: uuid.UUID
    project_name: str
    milestone_id: uuid.UUID
    milestone_name: str
    status: str
    start_date: dt.date = Field(description="First day this person works on it")
    end_date: dt.date = Field(description="Last day this person works on it")
    due_date: dt.date
    deliverables_total: int
    deliverables_done: int


class MyDashboard(BaseModel):
    """The signed-in person's own view."""

    as_of: dt.date
    current_work: WorkRef | None
    my_milestones: list[MyMilestone]
    projects: list[ProjectOut]
    hours_today: float = Field(description="8 on a working day when you are on a milestone, otherwise 0")
    hours_this_week: float
    week_capacity: int
