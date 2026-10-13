"""Business rules for deliverables: a checklist the manager ticks off while reviewing a milestone."""

from __future__ import annotations

import uuid
from typing import Any

import psycopg

from app.core.deps import CurrentUser
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domains.deliverables import repository as repo
from app.domains.deliverables.schemas import DeliverableCreate, DeliverableList, DeliverableOut, DeliverableUpdate
from app.domains.milestones import service as milestones
from app.domains.projects import service as projects


def _out(row: dict[str, Any]) -> DeliverableOut:
    return DeliverableOut.model_validate(row)


def _load(
    conn: psycopg.Connection[Any], actor: CurrentUser, milestone_id: uuid.UUID, deliverable_id: uuid.UUID
) -> dict[str, Any]:
    row = repo.get(conn, milestone_id, deliverable_id, include_archived=actor.is_admin)
    if row is None:
        raise NotFoundError("Deliverable not found")
    return row


def list_deliverables(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID, *, include_archived: bool
) -> DeliverableList:
    """The checklist of a milestone you can see. Only admins can include archived deliverables."""
    projects.get_visible(conn, actor, project_id)
    milestones.load(conn, actor, project_id, milestone_id)
    rows = repo.list_for_milestone(conn, milestone_id, include_archived=include_archived and actor.is_admin)
    live = [r for r in rows if r["archived_at"] is None]
    done = sum(1 for r in live if r["done"])
    return DeliverableList(
        items=[_out(r) for r in rows], total=len(live), done=done, ready_to_complete=bool(live) and done == len(live)
    )


def _open_milestone(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> None:
    projects.get_manageable(conn, actor, project_id)
    milestones.load_live(conn, actor, project_id, milestone_id)


def add_deliverable(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID, payload: DeliverableCreate
) -> DeliverableOut:
    """Add an item to the milestone's checklist."""
    _open_milestone(conn, actor, project_id, milestone_id)
    if repo.name_taken(conn, milestone_id, payload.name):
        raise ConflictError(
            "This milestone already has a deliverable with that name", details=[{"field": "name", "message": "Already in use"}]
        )
    new_id = repo.insert(conn, milestone_id=milestone_id, name=payload.name, description=payload.description)
    return _out(_load(conn, actor, milestone_id, new_id))


def update_deliverable(
    conn: psycopg.Connection[Any],
    actor: CurrentUser,
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    payload: DeliverableUpdate,
) -> DeliverableOut:
    """Rename a deliverable, or tick it off after review (``done: true``) / reopen it (``done: false``)."""
    _open_milestone(conn, actor, project_id, milestone_id)
    current = _load(conn, actor, milestone_id, deliverable_id)
    if current["archived_at"] is not None:
        raise ConflictError("This deliverable is archived and can no longer be changed")
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if value is None:
            raise ValidationError("This field cannot be empty", details=[{"field": key, "message": "This field cannot be empty"}])
    done = fields.pop("done", None)
    if "name" in fields and fields["name"].lower() != current["name"].lower() and repo.name_taken(
        conn, milestone_id, fields["name"], exclude_id=deliverable_id
    ):
        raise ConflictError(
            "This milestone already has a deliverable with that name", details=[{"field": "name", "message": "Already in use"}]
        )
    repo.update(conn, deliverable_id, fields)
    if done is not None:
        repo.set_done(conn, deliverable_id, done=done, user_id=actor.id)
    return _out(_load(conn, actor, milestone_id, deliverable_id))


def archive_deliverable(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID, deliverable_id: uuid.UUID
) -> DeliverableOut:
    """Take an item off the checklist (archived, never deleted; admins can still see it)."""
    _open_milestone(conn, actor, project_id, milestone_id)
    _load(conn, actor, milestone_id, deliverable_id)
    repo.archive(conn, deliverable_id)
    row = repo.get(conn, milestone_id, deliverable_id, include_archived=True)
    if row is None:  # pragma: no cover - just archived
        raise NotFoundError("Deliverable not found")
    return _out(row)
