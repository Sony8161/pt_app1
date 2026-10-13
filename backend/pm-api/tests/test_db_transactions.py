"""The request-transaction rules: migrations survive error responses, failed requests roll back."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_error_on_first_request_does_not_undo_migrations(client):
    # A health ping opens the shared connection without running migrations ...
    assert client.get("/health").status_code == 200
    # ... then the first API call is rejected (no token). Its migrations must still persist.
    assert client.get("/users").status_code == 401
    # ... yet the schema and the bootstrap admin must still exist afterwards.
    assert client.get("/health").json()["database"] == "ok"
    login = client.post("/auth/login", json={"username": "admin1", "password": "ChangeMe123!"})
    assert login.status_code == 200


def test_failed_request_rolls_back_its_writes(client, api, raw_db):
    manager = api.user("manager")
    before = raw_db.execute("SELECT count(*) AS n FROM users").fetchone()["n"]
    # Creating an employee under an unknown manager fails validation: nothing may be stored.
    resp = client.post(
        "/users",
        json={"name": "Ghost", "email": "ghost@test.example", "role": "employee",
              "manager_id": "00000000-0000-0000-0000-000000000000"},
        headers=api.admin.headers,
    )
    assert resp.status_code == 400
    assert raw_db.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == before
    assert manager.id


def test_successful_request_is_committed(client, api, raw_db):
    api.user("manager", "Committed Manager")
    row = raw_db.execute("SELECT 1 FROM users WHERE name = 'Committed Manager'").fetchone()
    assert row is not None


def test_error_envelope_shape(client):
    resp = client.get("/projects")
    assert resp.status_code == 401
    body = resp.json()["error"]
    assert set(body) == {"code", "message", "details"}
    assert resp.headers["www-authenticate"] == "Bearer"


def test_api_prefix_is_accepted(client):
    assert client.get("/api/pm-api/health").status_code == 200
    assert client.get("/health").status_code == 200
