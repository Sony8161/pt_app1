"""Pydantic models for time tracking."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class TimeEntryCreate(BaseModel):
    """Log hours. Employees log for themselves; admins and the project's manager may log for someone else."""

    work_date: dt.date
    hours: float = Field(gt=0, le=8, description="Hours worked; a person's day holds at most 8")
    milestone_id: uuid.UUID | None = None
    notes: Notes = ""
    user_id: uuid.UUID | None = Field(default=None, description="Defaults to you")


class TimeEntryOut(BaseModel):
    """One block of logged time."""

    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    user_id: uuid.UUID
    user_name: str
    milestone_id: uuid.UUID | None
    work_date: dt.date
    hours: float
    notes: str
    labor_cost: float | None = Field(description="Hidden (null) from employees")
    created_at: dt.datetime


class TimeEntryList(BaseModel):
    """Entries plus their total."""

    items: list[TimeEntryOut]
    total: int
    total_hours: float


class DayTotal(BaseModel):
    """Hours logged on one day."""

    date: dt.date
    hours: float
    remaining: float = Field(description="Hours left of the 8-hour day")


class MyTimeList(TimeEntryList):
    """Your own entries, with a per-day tally."""

    daily_totals: list[DayTotal]
