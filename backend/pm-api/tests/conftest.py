"""Shared fixtures. Integration tests use a real PostgreSQL database named ``pm_test``.

They are skipped automatically when PostgreSQL is not reachable. Connection settings come from
the usual POSTGRES_* variables (defaults match the local workshop setup).
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import psycopg
import pytest

TEST_DB = "pm_test"
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASS", "postgres123")
os.environ["POSTGRES_NAME"] = TEST_DB
os.environ["IS_LOCAL"] = "true"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["APP_ENV"] = "test"
os.environ.pop("BOOTSTRAP_ADMIN_PASSWORD", None)
os.environ["POSTGRES_CONNECT_TIMEOUT"] = "3"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.core import dates  # noqa: E402

get_settings.cache_clear()

BOOTSTRAP_USER, BOOTSTRAP_PASSWORD = "admin1", "ChangeMe123!"
GOOD_PASSWORD = "Passw0rd-xyz"
TABLES = "project_costs, time_entries, project_assignments, milestones, projects, users"


def _admin_conninfo(dbname: str = "postgres") -> str:
    s = get_settings()
    return f"host={s.pg_host} port={s.pg_port} user={s.pg_user} password={s.pg_password} dbname={dbname} connect_timeout=3"


@pytest.fixture(scope="session")
def _database() -> Iterator[None]:
    try:
        with psycopg.connect(_admin_conninfo(), autocommit=True) as conn:
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    yield


@pytest.fixture
def raw_db(_database: None) -> Iterator[psycopg.Connection[Any]]:
    """Separate autocommit connection for test setup and assertions."""
    with psycopg.connect(_admin_conninfo(TEST_DB), autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        yield conn


@pytest.fixture
def client(raw_db: psycopg.Connection[Any]) -> Iterator[TestClient]:
    """App client on a clean database; the first request re-runs migrations and creates the admin."""
    db.reset_connection()
    raw_db.execute("DROP TABLE IF EXISTS schema_migrations")  # forces a clean, re-applied schema
    raw_db.execute(f"DROP TABLE IF EXISTS {TABLES} CASCADE")
    db.reset_migration_state()
    from app.main import app

    with TestClient(app) as c:
        yield c
    db.reset_connection()


@pytest.fixture
def today(monkeypatch: pytest.MonkeyPatch) -> dt.date:
    """Freeze 'today' (a Wednesday) so date-based rules are deterministic."""
    frozen = dt.date(2026, 3, 11)
    monkeypatch.setattr(dates, "today", lambda: frozen)
    return frozen


@dataclass
class Person:
    """A signed-in test user."""

    id: str
    username: str
    name: str
    headers: dict[str, str]


class Helpers:
    """Small API helpers shared by the tests."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self._counter = 0
        self.admin = self._sign_in_admin()

    def _sign_in_admin(self) -> Person:
        resp = self.client.post("/auth/login", json={"username": BOOTSTRAP_USER, "password": BOOTSTRAP_PASSWORD})
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        changed = self.client.post(
            "/auth/change-password",
            json={"current_password": BOOTSTRAP_PASSWORD, "new_password": GOOD_PASSWORD},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert changed.status_code == 200, changed.text
        user = changed.json()["user"]
        return Person(user["id"], user["username"], user["name"], {"Authorization": f"Bearer {changed.json()['access_token']}"})

    def user(self, role: str, name: str | None = None, manager: Person | None = None, salary: float = 50) -> Person:
        """Create a user through the API as the admin, sign in and complete the first password change."""
        self._counter += 1
        name = name or f"{role.title()} {self._counter}"
        body: dict[str, Any] = {
            "name": name, "email": f"{name.lower().replace(' ', '.')}{self._counter}@test.example",
            "role": role, "salary": salary, "job_title": "Tester",
        }
        if manager is not None:
            body["manager_id"] = manager.id
        created = self.client.post("/users", json=body, headers=self.admin.headers)
        assert created.status_code == 201, created.text
        data = created.json()
        login = self.client.post(
            "/auth/login", json={"username": data["user"]["username"], "password": data["temporary_password"]}
        )
        assert login.status_code == 200, login.text
        changed = self.client.post(
            "/auth/change-password",
            json={"current_password": data["temporary_password"], "new_password": GOOD_PASSWORD},
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert changed.status_code == 200, changed.text
        return Person(
            data["user"]["id"], data["user"]["username"], name,
            {"Authorization": f"Bearer {changed.json()['access_token']}"},
        )

    def project(self, manager: Person, name: str = "Apollo", start: str = "2026-03-02", end: str = "2026-04-30",
                hours: float = 800, budget: float = 50000) -> dict[str, Any]:
        resp = self.client.post(
            "/projects",
            json={"name": name, "manager_id": manager.id, "start_date": start, "end_date": end,
                  "allocated_hours": hours, "budget_amount": budget},
            headers=self.admin.headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def assign(self, project_id: str, employee: Person, manager_headers: dict[str, str] | None = None, **dates_: str) -> Any:
        return self.client.post(
            f"/projects/{project_id}/team", json={"user_id": employee.id, **dates_},
            headers=manager_headers or self.admin.headers,
        )


@pytest.fixture
def api(client: TestClient) -> Helpers:
    return Helpers(client)


@pytest.fixture
def new_id() -> Callable[[], str]:
    return lambda: str(uuid.uuid4())
