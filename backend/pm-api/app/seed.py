"""First-admin bootstrap and the optional demo dataset."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import psycopg

from app.config import get_settings
from app.core import dates, security
from app.db import MIGRATION_LOCK_ID
from app.domains.assignments import repository as assignments_repo
from app.domains.milestones import repository as milestones_repo
from app.domains.projects import repository as projects_repo
from app.domains.time_entries import repository as time_repo
from app.domains.users import repository as users_repo

logger = logging.getLogger(__name__)

DEMO_DOMAIN = "@demo.acme.example"


def ensure_bootstrap_admin(conn: psycopg.Connection[Any]) -> None:
    """Create the first admin when the system has none. Safe to run on every cold start."""
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
    if users_repo.count_by_role(conn, "admin", include_archived=True) > 0:
        return
    settings = get_settings()
    if not settings.bootstrap_admin_password:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be set to create the first admin account")
    security.validate_password_strength(settings.bootstrap_admin_password)
    users_repo.insert(
        conn,
        username=settings.bootstrap_admin_username,
        password_hash=security.hash_password(settings.bootstrap_admin_password),
        name="System Admin",
        email="admin@acme.example",
        job_title="Administrator",
        role="admin",
        manager_id=None,
        salary=0,
        must_change_password=True,
    )
    logger.info("Created bootstrap admin '%s' (password change required at first login)", settings.bootstrap_admin_username)


def _weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1) if (start + dt.timedelta(days=i)).weekday() < 5]


def seed_demo(conn: psycopg.Connection[Any], admin_id: Any) -> dict[str, Any]:
    """Create two managers, six employees and four projects in different health states.

    Idempotent: if the demo accounts already exist nothing is created. The accounts get
    random one-time passwords, returned once in the response.
    """
    existing = conn.execute("SELECT 1 FROM users WHERE email LIKE %s LIMIT 1", (f"%{DEMO_DOMAIN}",)).fetchone()
    if existing:
        return {"created": False, "message": "Demo data already exists", "accounts": []}

    today = dates.today()
    accounts: list[dict[str, str]] = []

    def make_user(name: str, role: str, title: str, salary: float, manager_id: Any = None) -> dict[str, Any]:
        password = security.generate_password()
        for _ in range(20):
            username = security.generate_username(name)
            if not users_repo.username_exists(conn, username):
                break
        email = name.lower().replace(" ", ".") + DEMO_DOMAIN
        row = users_repo.insert(
            conn, username=username, password_hash=security.hash_password(password), name=name, email=email,
            job_title=title, role=role, manager_id=manager_id, salary=salary,
        )
        accounts.append({"name": name, "role": role, "username": username, "temporary_password": password})
        return row

    maria = make_user("Maria Lopez", "manager", "Engineering Manager", 70)
    james = make_user("James Carter", "manager", "Delivery Manager", 75)
    staff = [
        make_user("Alex Kim", "employee", "Frontend Developer", 48, maria["id"]),
        make_user("Priya Shah", "employee", "UX Designer", 45, maria["id"]),
        make_user("Tom Becker", "employee", "Backend Developer", 52, james["id"]),
        make_user("Lena Fischer", "employee", "QA Engineer", 40, james["id"]),
        make_user("Omar Haddad", "employee", "Data Engineer", 60, james["id"]),
        make_user("Sofia Rossi", "employee", "Business Analyst", 50, maria["id"]),
    ]

    def make_project(name: str, manager: dict[str, Any], start: dt.date, end: dt.date, hours: float, budget: float,
                     team: list[dict[str, Any]], milestones: list[tuple[str, dt.date, dt.date, float, str]],
                     costs: list[tuple[str, str, float, dt.date]]) -> None:
        project_id = projects_repo.insert(
            conn, name=name, description=f"Demo project: {name}", manager_id=manager["id"], start_date=start,
            end_date=end, allocated_hours=hours, budget_amount=budget, created_by=admin_id,
        )
        ids = {}
        for m_name, m_start, m_due, m_hours, m_status in milestones:
            mid = milestones_repo.insert(
                conn, project_id=project_id, name=m_name, description="", start_date=m_start, due_date=m_due,
                allocated_hours=m_hours,
            )
            ids[m_name] = mid
            if m_status != "pending":
                milestones_repo.update(conn, mid, {
                    "status": m_status, "completed_at": dates.now() if m_status == "done" else None})
        for person in team:
            assignments_repo.insert(
                conn, project_id=project_id, user_id=person["id"], start_date=start, end_date=end, assigned_by=admin_id
            )
            for day in _weekdays(start, min(end, today - dt.timedelta(days=1))):
                time_repo.insert(conn, project_id=project_id, user_id=person["id"], milestone_id=None,
                                 work_date=day, hours=8, notes="")
        for category, description, amount, when in costs:
            conn.execute(
                "INSERT INTO project_costs (project_id, category, description, amount, incurred_on, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (project_id, category, description, amount, when, admin_id),
            )

    d = dt.timedelta
    make_project(
        "Website Redesign", maria, today - d(days=60), today + d(days=30), 1200, 60000, staff[0:2],
        [("Design sign-off", today - d(days=60), today - d(days=20), 200, "done"),
         ("Build", today - d(days=19), today + d(days=10), 700, "in_progress"),
         ("Launch", today + d(days=11), today + d(days=30), 200, "pending")],
        [("license", "Design tool licences", 3000, today - d(days=40)), ("technology", "Hosting", 2000, today - d(days=10))],
    )
    make_project(
        "Mobile App Launch", james, today - d(days=50), today - d(days=3), 400, 40000, staff[2:4],
        [("Beta release", today - d(days=50), today - d(days=20), 150, "pending"),
         ("Store submission", today - d(days=19), today - d(days=3), 150, "pending")],
        [("vendor", "App store consultancy", 4000, today - d(days=15))],
    )
    make_project(
        "Data Platform Migration", james, today - d(days=30), today + d(days=60), 900, 30000, staff[4:5],
        [("Inventory", today - d(days=30), today - d(days=10), 100, "done"),
         ("Cut-over", today - d(days=9), today + d(days=60), 600, "in_progress")],
        [("license", "Warehouse licences", 12000, today - d(days=20))],
    )
    make_project(
        "Customer Portal", maria, today + d(days=14), today + d(days=90), 800, 50000, staff[5:6],
        [("Discovery", today + d(days=14), today + d(days=40), 200, "pending")], [],
    )
    return {"created": True, "message": "Demo data created", "accounts": accounts}
