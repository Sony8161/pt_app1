"""Pydantic models for project costs."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

CostCategory = Literal["technology", "license", "vendor", "travel", "other"]
CostText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class CostCreate(BaseModel):
    """A non-labor expense."""

    category: CostCategory
    description: CostText
    amount: float = Field(ge=0, le=1_000_000_000, description="Dollars")
    incurred_on: dt.date


class CostUpdate(BaseModel):
    """Send only what changes."""

    category: CostCategory | None = None
    description: CostText | None = None
    amount: float | None = Field(default=None, ge=0, le=1_000_000_000)
    incurred_on: dt.date | None = None


class CostOut(BaseModel):
    """One cost line."""

    id: uuid.UUID
    project_id: uuid.UUID
    category: CostCategory
    description: str
    amount: float
    incurred_on: dt.date
    created_at: dt.datetime
    archived_at: dt.datetime | None = Field(default=None, description="Only admins can see archived costs")


class CostList(BaseModel):
    """Cost lines with totals, next to the budget they draw on."""

    items: list[CostOut]
    total: int
    other_cost: float = Field(description="Sum of the non-labor costs")
    by_category: dict[str, float]
    labor_cost: float = Field(description="Hours logged x salaries")
    total_cost: float
    budget_amount: float
    budget_remaining: float
