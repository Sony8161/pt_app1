"""Pydantic models for project teams."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class TeamMemberAdd(BaseModel):
    """Put an employee on the project team. Dates default to the project's (or today, if it has started)."""

    user_id: uuid.UUID
    start_date: dt.date | None = None
    end_date: dt.date | None = None


class TeamMemberDates(BaseModel):
    """Change when an employee works on the project."""

    start_date: dt.date | None = None
    end_date: dt.date | None = None


class TeamMemberOut(BaseModel):
    """One person on a project team."""

    assignment_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    username: str
    email: str
    job_title: str
    start_date: dt.date
    end_date: dt.date
    daily_hours: int = Field(description="Hours per working day this person gives the project")
    hours_logged: float
    labor_cost: float | None = Field(description="Hidden (null) from employees")


class TeamList(BaseModel):
    """The project team."""

    items: list[TeamMemberOut]
    total: int
