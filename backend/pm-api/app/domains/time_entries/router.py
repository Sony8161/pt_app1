"""HTTP endpoints for time tracking."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.deps import ActiveUser, DbConn
from app.domains.time_entries import service
from app.domains.time_entries.schemas import MyTimeList, TimeEntryCreate, TimeEntryList, TimeEntryOut

router = APIRouter(prefix="/projects/{project_id}/time-entries", tags=["time"])
my_router = APIRouter(prefix="/time-entries", tags=["time"])


@router.get("", response_model=TimeEntryList)
def list_project_time(
    project_id: uuid.UUID,
    actor: ActiveUser,
    conn: DbConn,
    user_id: uuid.UUID | None = None,
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
) -> TimeEntryList:
    """Time logged on a project (employees see only their own)."""
    return service.list_project_time(conn, actor, project_id, user_id=user_id, start=date_from, end=date_to)


@router.post("", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
def log_time(project_id: uuid.UUID, payload: TimeEntryCreate, actor: ActiveUser, conn: DbConn) -> TimeEntryOut:
    """Log hours. Needs an assignment covering that date, and at most 8 hours per person per day."""
    return service.log_time(conn, actor, project_id, payload)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(project_id: uuid.UUID, entry_id: uuid.UUID, actor: ActiveUser, conn: DbConn) -> Response:
    """Remove a time entry (archived, not deleted)."""
    service.delete_entry(conn, actor, project_id, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@my_router.get("/me", response_model=MyTimeList)
def my_time(
    actor: ActiveUser,
    conn: DbConn,
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
) -> MyTimeList:
    """Your own logged time across projects, with a per-day tally."""
    return service.my_time(conn, actor, date_from, date_to)
