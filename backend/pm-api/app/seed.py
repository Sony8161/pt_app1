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
from app.domains.deliverables import repository as deliverables_repo
from app.domains.milestones import repository as milestones_repo
from app.domains.projects import repository as projects_repo
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


def seed_demo(conn: psycopg.Connection[Any], admin_id: Any) -> dict[str, Any]:
    """Create two managers, six employees and four projects in different health states.

    Idempotent: if the demo accounts already exist nothing is created. The accounts get
    random one-time passwords, returned once in the response.
    """
    existing = conn.execute("SELECT 1 FROM users WHERE email LIKE %s LIMIT 1", (f"%{DEMO_DOMAIN}",)).fetchone()
    if existing:
        return {"created": False, "message": "Demo data already exists", "accounts": []}

    today = dates.today()
    d = dt.timedelta
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
    alex = make_user("Alex Kim", "employee", "Frontend Developer", 50, maria["id"])
    priya = make_user("Priya Shah", "employee", "UX Designer", 45, maria["id"])
    tom = make_user("Tom Becker", "employee", "Backend Developer", 52, james["id"])
    lena = make_user("Lena Fischer", "employee", "QA Engineer", 40, james["id"])
    omar = make_user("Omar Haddad", "employee", "Data Engineer", 60, james["id"])
    sofia = make_user("Sofia Rossi", "employee", "Business Analyst", 50, maria["id"])

    def make_project(name: str, manager: dict[str, Any], start: dt.date, end: dt.date, hours: float, budget: float) -> Any:
        return projects_repo.insert(
            conn, name=name, description=f"Demo project: {name}", manager_id=manager["id"], start_date=start,
            end_date=end, allocated_hours=hours, budget_amount=budget, created_by=admin_id,
        )

    def make_milestone(
        project_id: Any, manager: dict[str, Any], name: str, start: dt.date, due: dt.date, hours: float, budget: float,
        people: list[dict[str, Any]], deliverables: list[tuple[str, bool]], *, status: str = "pending", complete: bool = False,
    ) -> None:
        mid = milestones_repo.insert(
            conn, project_id=project_id, name=name, description="", start_date=start, due_date=due,
            allocated_hours=hours, budget_amount=budget,
        )
        if status != "pending":
            milestones_repo.update(conn, mid, {"status": status})
        for person in people:
            assignments_repo.insert(
                conn, milestone_id=mid, user_id=person["id"], start_date=start, end_date=due, assigned_by=admin_id
            )
        for item, done in deliverables:
            did = deliverables_repo.insert(conn, milestone_id=mid, name=item, description="")
            if done:
                deliverables_repo.set_done(conn, did, done=True, user_id=manager["id"])
        if complete:
            milestones_repo.complete(conn, mid, reviewer_id=manager["id"], note="Reviewed and signed off")

    def add_cost(project_id: Any, category: str, description: str, amount: float, when: dt.date) -> None:
        conn.execute(
            "INSERT INTO project_costs (project_id, category, description, amount, incurred_on, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (project_id, category, description, amount, when, admin_id),
        )

    # On track: two thirds of the time has passed, a bit over a third of the budget is used.
    p1 = make_project("Website Redesign", maria, today - d(days=60), today + d(days=30), 1200, 60000)
    make_milestone(p1, maria, "Design sign-off", today - d(days=60), today - d(days=20), 200, 8000, [priya],
                   [("Wireframes", True), ("Style guide", True)], complete=True)
    make_milestone(p1, maria, "Build", today - d(days=19), today + d(days=10), 700, 30000, [alex],
                   [("Login page", True), ("Dashboard", False)], status="in_progress")
    make_milestone(p1, maria, "Launch", today + d(days=11), today + d(days=30), 200, 9000, [], [])
    add_cost(p1, "license", "Design tool licences", 3000, today - d(days=40))
    add_cost(p1, "technology", "Hosting", 2000, today - d(days=10))

    # Overdue: the end date has passed and both milestones are late.
    p2 = make_project("Mobile App Launch", james, today - d(days=50), today - d(days=3), 400, 40000)
    make_milestone(p2, james, "Beta release", today - d(days=50), today - d(days=20), 150, 15000, [tom], [("Beta build", False)])
    make_milestone(p2, james, "Store submission", today - d(days=19), today - d(days=3), 150, 15000, [lena],
                   [("Store listing", False)])
    add_cost(p2, "vendor", "App store consultancy", 4000, today - d(days=15))

    # At risk: spending runs far ahead of the calendar and the planned staffing exceeds the budget.
    p3 = make_project("Data Platform Migration", james, today - d(days=30), today + d(days=60), 900, 30000)
    make_milestone(p3, james, "Inventory", today - d(days=30), today - d(days=10), 100, 4000, [omar],
                   [("System inventory", True)], complete=True)
    make_milestone(p3, james, "Cut-over", today - d(days=9), today + d(days=60), 600, 20000, [omar],
                   [("Data copied", False), ("Cut-over plan", False)], status="in_progress")
    add_cost(p3, "license", "Warehouse licences", 12000, today - d(days=20))

    # Planned: has not started yet.
    p4 = make_project("Customer Portal", maria, today + d(days=14), today + d(days=90), 800, 50000)
    make_milestone(
        p4, maria, "Discovery", today + d(days=14), today + d(days=40), 200, 10000, [sofia], [("Interview notes", False)]
    )

    return {"created": True, "message": "Demo data created", "accounts": accounts}
