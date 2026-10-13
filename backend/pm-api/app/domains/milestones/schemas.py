"""Pydantic models for milestones."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

MilestoneStatus = Literal["pending", "in_progress", "completed"]
EditableStatus = Literal["pending", "in_progress"]
MilestoneName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class MilestoneCreate(BaseModel):
    """A building block of the project. Its dates must fall inside the project's dates."""

    name: MilestoneName
    description: Text = ""
    start_date: dt.date
    due_date: dt.date
    allocated_hours: float = Field(default=0, ge=0, le=1_000_000, description="Hours planned for this milestone")
    budget_amount: float = Field(default=0, ge=0, le=1_000_000_000, description="Budget planned for this milestone")

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        if self.due_date < self.start_date:
            raise ValueError("due_date must be on or after start_date")
        return self


class MilestoneUpdate(BaseModel):
    """Send only what changes. Completing a milestone has its own endpoint (it needs the deliverables reviewed)."""

    name: MilestoneName | None = None
    description: Text | None = None
    start_date: dt.date | None = None
    due_date: dt.date | None = None
    allocated_hours: float | None = Field(default=None, ge=0, le=1_000_000)
    budget_amount: float | None = Field(default=None, ge=0, le=1_000_000_000)
    status: EditableStatus | None = None


class MilestoneComplete(BaseModel):
    """The manager's sign-off after reviewing the deliverables."""

    review_note: Text = Field(default="", description="What was reviewed, e.g. 'Wireframes signed off by the client'")


class MilestoneOut(BaseModel):
    """A milestone with its progress. Money is hidden (null) from employees."""

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    start_date: dt.date
    due_date: dt.date
    status: MilestoneStatus
    is_overdue: bool
    allocated_hours: float = Field(description="Planned hours")
    hours_worked: float = Field(description="Working days so far x 8 x people on it")
    budget_amount: float | None
    labor_cost: float | None = Field(description="Hours worked x salaries so far")
    budget_pct: float | None
    assignees: int
    deliverables_total: int
    deliverables_done: int
    completed_at: dt.datetime | None
    review_note: str
    archived_at: dt.datetime | None = Field(description="Set once completed or cancelled; admin-visible only")
    created_at: dt.datetime
    updated_at: dt.datetime


class MilestoneList(BaseModel):
    """Milestones in timeline order."""

    items: list[MilestoneOut]
    total: int
    planned_hours: float = Field(description="Sum of the milestones' planned hours")
    planned_budget: float | None
