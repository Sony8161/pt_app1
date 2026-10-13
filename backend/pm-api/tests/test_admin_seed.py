"""Demo data and the first-admin bootstrap."""

from __future__ import annotations

import pytest

from tests.conftest import GOOD_PASSWORD

pytestmark = pytest.mark.integration


def test_seed_demo_is_admin_only_and_idempotent(api, today):
    manager = api.user("manager")
    assert api.client.post("/admin/seed-demo", headers=manager.headers).status_code == 403

    first = api.client.post("/admin/seed-demo", headers=api.admin.headers)
    assert first.status_code == 200 and first.json()["created"] is True
    accounts = first.json()["accounts"]
    assert len(accounts) == 8 and {a["role"] for a in accounts} == {"manager", "employee"}

    second = api.client.post("/admin/seed-demo", headers=api.admin.headers).json()
    assert second["created"] is False and second["accounts"] == []


def test_demo_data_shows_every_health_state_and_available_people(api, today):
    api.client.post("/admin/seed-demo", headers=api.admin.headers)
    out = api.client.get("/reports/overview", headers=api.admin.headers).json()
    names = {p["name"]: p for p in out["projects"]}
    assert set(names) == {"Website Redesign", "Mobile App Launch", "Data Platform Migration", "Customer Portal"}
    assert names["Website Redesign"]["summary"]["risk_level"] == "on_track"
    assert names["Mobile App Launch"]["summary"]["risk_level"] == "overdue"
    assert names["Data Platform Migration"]["summary"]["risk_level"] == "at_risk"
    assert names["Customer Portal"]["status"] == "planned"
    assert out["available_people"] >= 1 and out["totals"]["spent"] > 0


def test_demo_accounts_can_sign_in(api, today):
    accounts = api.client.post("/admin/seed-demo", headers=api.admin.headers).json()["accounts"]
    employee = next(a for a in accounts if a["role"] == "employee")
    login = api.client.post("/auth/login", json={"username": employee["username"], "password": employee["temporary_password"]})
    assert login.status_code == 200 and login.json()["user"]["must_change_password"] is True
    assert GOOD_PASSWORD  # accounts keep one-time passwords; they must change them at first login
