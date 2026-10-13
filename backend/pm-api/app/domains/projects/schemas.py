"""Pydantic models for projects."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

ProjectStatus = Literal["planned", "active", "completed", "archived"]
RiskLevel = Literal["done", "on_track", "at_risk", "overdue"]

ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class ProjectCreate(BaseModel):
    """Admin creates a project for one manager."""

    name: ProjectName
    description: Description = ""
    manager_id: uuid.UUID = Field(description="The one manager who runs this project")
    start_date: dt.date
    end_date: dt.date = Field(description="Predicted end date")
    allocated_hours: float = Field(default=0, ge=0, le=1_000_000, description="Total hours planned for the project")
    budget_amount: float = Field(default=0, ge=0, le=1_000_000_000, description="Total budget in dollars")

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ProjectUpdate(BaseModel):
    """Send only what changes. Managers may edit everything except ``manager_id``."""

    name: ProjectName | None = None
    description: Description | None = None
    manager_id: uuid.UUID | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    allocated_hours: float | None = Field(default=None, ge=0, le=1_000_000)
    budget_amount: float | None = Field(default=None, ge=0, le=1_000_000_000)


class ProjectSummary(BaseModel):
    """Progress and health derived from dates, hours and money."""

    days_total: int
    days_elapsed: int
    days_remaining: int = Field(description="Negative when the end date has passed")
    schedule_pct: float = Field(description="Share of the calendar that has passed")
    hours_worked: float = Field(description="Working days so far x 8 x people on milestones")
    hours_remaining: float
    hours_pct: float | None
    milestones_total: int
    milestones_done: int
    milestones_overdue: int
    milestones_pct: float | None
    team_size: int
    risk_level: RiskLevel
    risk_reasons: list[str]
    # Money fields are hidden (null) from employees.
    labor_cost: float | None
    forecast_cost: float | None = Field(description="Cost if everyone stays assigned for the whole planned range")
    other_cost: float | None
    total_cost: float | None
    budget_remaining: float | None
    budget_pct: float | None


class ManagerRef(BaseModel):
    """The project's manager."""

    id: uuid.UUID
    name: str


class ProjectOut(BaseModel):
    """A project with its health summary."""

    id: uuid.UUID
    name: str
    description: str
    manager: ManagerRef
    status: ProjectStatus
    start_date: dt.date
    end_date: dt.date
    allocated_hours: float
    budget_amount: float | None = Field(description="Hidden (null) from employees")
    completed_at: dt.datetime | None
    archived_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    summary: ProjectSummary


class ProjectList(BaseModel):
    """One page of projects."""

    items: list[ProjectOut]
    total: int
    page: int
    page_size: int
