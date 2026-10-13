"""Pydantic models for milestone teams."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class AssigneeAdd(BaseModel):
    """Put an employee on a milestone. Dates default to the milestone's (starting today if it has begun)."""

    user_id: uuid.UUID
    start_date: dt.date | None = None
    end_date: dt.date | None = None


class AssigneeDates(BaseModel):
    """Change when an employee works on the milestone."""

    start_date: dt.date | None = None
    end_date: dt.date | None = None


class AssigneeOut(BaseModel):
    """One person working on one milestone. Every Monday-Friday in the range is an 8-hour shift."""

    assignment_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    username: str
    email: str
    job_title: str
    milestone_id: uuid.UUID
    milestone_name: str
    project_id: uuid.UUID
    start_date: dt.date
    end_date: dt.date
    daily_hours: int = Field(description="Hours in one shift")
    days_worked: int = Field(description="Working days from the start until today (or the end)")
    hours_worked: float
    labor_cost: float | None = Field(description="Hours worked x salary so far; hidden (null) from employees")
    archived_at: dt.datetime | None


class AssigneeList(BaseModel):
    """People on a milestone or across a project."""

    items: list[AssigneeOut]
    total: int
    hours_worked: float
    labor_cost: float | None
