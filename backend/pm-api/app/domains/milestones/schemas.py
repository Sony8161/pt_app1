"""Pydantic models for milestones."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

MilestoneStatus = Literal["pending", "in_progress", "done"]
MilestoneName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class MilestoneCreate(BaseModel):
    """A key point in the project timeline. Its dates must fall inside the project's dates."""

    name: MilestoneName
    description: Text = ""
    start_date: dt.date
    due_date: dt.date
    allocated_hours: float = Field(default=0, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        if self.due_date < self.start_date:
            raise ValueError("due_date must be on or after start_date")
        return self


class MilestoneUpdate(BaseModel):
    """Send only what changes. Set ``status`` to ``done`` when the milestone is reached."""

    name: MilestoneName | None = None
    description: Text | None = None
    start_date: dt.date | None = None
    due_date: dt.date | None = None
    allocated_hours: float | None = Field(default=None, ge=0, le=1_000_000)
    status: MilestoneStatus | None = None


class MilestoneOut(BaseModel):
    """A milestone with its progress."""

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    start_date: dt.date
    due_date: dt.date
    allocated_hours: float
    hours_logged: float
    status: MilestoneStatus
    is_overdue: bool
    completed_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime


class MilestoneList(BaseModel):
    """Milestones in timeline order."""

    items: list[MilestoneOut]
    total: int
    planned_hours: float = Field(description="Sum of the milestones' allocated hours")
