"""Admin-only endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import AdminUser, DbConn
from app.seed import seed_demo

router = APIRouter(prefix="/admin", tags=["admin"])


class DemoAccount(BaseModel):
    """A demo login, shown once."""

    name: str
    role: str
    username: str
    temporary_password: str


class DemoSeedResult(BaseModel):
    """Outcome of seeding demo data."""

    created: bool
    message: str
    accounts: list[DemoAccount]


@router.post("/seed-demo", response_model=DemoSeedResult)
def seed_demo_data(actor: AdminUser, conn: DbConn) -> DemoSeedResult:
    """Create sample managers, employees and projects. Safe to call twice: it only creates data once."""
    return DemoSeedResult(**seed_demo(conn, actor.id))
