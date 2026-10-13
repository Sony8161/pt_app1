"""Pydantic models for deliverables."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import BaseModel, StringConstraints

DeliverableName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class DeliverableCreate(BaseModel):
    """Something the milestone must produce, e.g. 'Design file' or 'Test report'."""

    name: DeliverableName
    description: Text = ""


class DeliverableUpdate(BaseModel):
    """Send only what changes. Set ``done`` to tick or untick the deliverable after reviewing it."""

    name: DeliverableName | None = None
    description: Text | None = None
    done: bool | None = None


class DeliverableOut(BaseModel):
    """One checklist item."""

    id: uuid.UUID
    milestone_id: uuid.UUID
    name: str
    description: str
    done: bool
    done_at: dt.datetime | None
    done_by: uuid.UUID | None
    archived_at: dt.datetime | None
    created_at: dt.datetime


class DeliverableList(BaseModel):
    """A milestone's checklist."""

    items: list[DeliverableOut]
    total: int
    done: int
    ready_to_complete: bool
