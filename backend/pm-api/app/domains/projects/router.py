"""HTTP endpoints for projects."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import ActiveUser, AdminUser, DbConn, ManagerOrAdmin
from app.domains.projects import service
from app.domains.projects.schemas import ProjectCreate, ProjectList, ProjectOut, ProjectStatus, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectList)
def list_projects(
    actor: ActiveUser,
    conn: DbConn,
    q: str | None = None,
    status: ProjectStatus | None = None,
    manager_id: uuid.UUID | None = None,
    include_archived: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ProjectList:
    """Projects you may see, with their health summary. Search by project or manager name."""
    return service.list_projects(
        conn, actor, q=q, status=status, manager_id=manager_id,
        include_archived=include_archived, page=page, page_size=page_size,
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, actor: AdminUser, conn: DbConn) -> ProjectOut:
    """Admin creates a project and picks its one manager."""
    return service.create_project(conn, actor, payload)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, actor: ActiveUser, conn: DbConn) -> ProjectOut:
    """One project with progress, cost and risk."""
    return service.get_project(conn, actor, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, payload: ProjectUpdate, actor: ManagerOrAdmin, conn: DbConn) -> ProjectOut:
    """Edit dates, hours, budget or text. Only an admin can change the manager."""
    return service.update_project(conn, actor, project_id, payload)


@router.post("/{project_id}/complete", response_model=ProjectOut)
def complete_project(project_id: uuid.UUID, actor: ManagerOrAdmin, conn: DbConn) -> ProjectOut:
    """Mark the project finished. The team becomes free for new work today."""
    return service.complete_project(conn, actor, project_id)


@router.post("/{project_id}/archive", response_model=ProjectOut)
def archive_project(project_id: uuid.UUID, actor: AdminUser, conn: DbConn) -> ProjectOut:
    """Archive a project. Nothing is deleted."""
    return service.archive_project(conn, actor, project_id)


@router.post("/{project_id}/unarchive", response_model=ProjectOut)
def unarchive_project(project_id: uuid.UUID, actor: AdminUser, conn: DbConn) -> ProjectOut:
    """Restore an archived project."""
    return service.unarchive_project(conn, actor, project_id)
