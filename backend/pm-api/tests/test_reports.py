"""Dashboards: health, allocation and the personal view."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_overview_ranks_projects_by_urgency_and_totals_money(api, today):
    manager = api.user("manager")
    busy = api.user("employee", "Busy", manager=manager, salary=50)
    api.user("employee", "Free", manager=manager)
    healthy = api.project(manager, name="Healthy", start="2026-03-01", end="2026-06-30", hours=1000, budget=10000)
    late = api.project(manager, name="Late", start="2026-01-01", end="2026-03-01", hours=100, budget=5000)
    soon = api.project(manager, name="Soon", start="2026-03-01", end="2026-06-30", hours=500, budget=20000)
    api.assign(healthy["id"], busy)
    api.client.post(f"/projects/{soon['id']}/milestones", json={"name": "Past due", "start_date": "2026-03-02", "due_date": "2026-03-05"}, headers=manager.headers)
    api.client.post(f"/projects/{healthy['id']}/costs", json={"category": "vendor", "description": "x", "amount": 400, "incurred_on": "2026-03-05"}, headers=manager.headers)
    api.client.post(f"/projects/{healthy['id']}/time-entries", json={"work_date": "2026-03-11", "hours": 8}, headers=busy.headers)

    out = api.client.get("/reports/overview", headers=manager.headers).json()
    assert [p["name"] for p in out["projects"]] == ["Late", "Soon", "Healthy"]
    assert [p["summary"]["risk_level"] for p in out["projects"]] == ["overdue", "at_risk", "on_track"]
    assert out["counts"] == {"projects": 3, "planned": 0, "active": 3, "completed": 0, "on_track": 1, "at_risk": 1, "overdue": 1}
    assert out["totals"]["budget"] == 35000 and out["totals"]["labor_cost"] == 400 and out["totals"]["other_cost"] == 400
    assert out["totals"]["spent"] == 800 and out["totals"]["budget_remaining"] == 34200
    assert out["totals"]["hours_allocated"] == 1600 and out["totals"]["hours_logged"] == 8
    assert late["id"] and out["as_of"] == "2026-03-11"


def test_allocation_shows_who_is_busy_and_who_is_free(api, today):
    manager = api.user("manager")
    busy = api.user("employee", "Busy", manager=manager)
    free = api.user("employee", "Free", manager=manager)
    soon = api.user("employee", "Soon", manager=manager)
    now_project = api.project(manager, name="Now", start="2026-03-01", end="2026-04-01")
    next_project = api.project(manager, name="Next", start="2026-05-01", end="2026-06-01")
    api.assign(now_project["id"], busy)
    api.assign(next_project["id"], soon)
    api.client.post(f"/projects/{now_project['id']}/time-entries", json={"work_date": "2026-03-10", "hours": 8}, headers=busy.headers)

    out = api.client.get("/reports/overview", headers=manager.headers).json()
    people = {p["name"]: p for p in out["allocation"]}
    assert people["Busy"]["state"] == "allocated" and people["Busy"]["current_project"]["name"] == "Now"
    assert people["Busy"]["hours_this_week"] == 0 or people["Busy"]["hours_this_week"] == 8
    assert people["Free"]["state"] == "available" and people["Free"]["current_project"] is None
    assert people["Soon"]["state"] == "available" and people["Soon"]["next_project"]["name"] == "Next"
    assert out["available_people"] == 2 and people["Free"]["week_capacity"] == 40
    assert free.id


def test_managers_only_see_their_own_scope_and_admin_sees_all(api, today):
    a, b = api.user("manager", "Alpha"), api.user("manager", "Beta")
    api.user("employee", "A Report", manager=a)
    api.user("employee", "B Report", manager=b)
    api.project(a, name="A Project")
    api.project(b, name="B Project")
    mine = api.client.get("/reports/overview", headers=a.headers).json()
    assert [p["name"] for p in mine["projects"]] == ["A Project"]
    assert [p["name"] for p in mine["allocation"]] == ["A Report"]
    everything = api.client.get("/reports/overview", headers=api.admin.headers).json()
    assert everything["counts"]["projects"] == 2 and len(everything["allocation"]) == 2


def test_archived_projects_are_left_out_and_employees_are_blocked(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    gone = api.project(manager, name="Gone")
    api.client.post(f"/projects/{gone['id']}/archive", headers=api.admin.headers)
    assert api.client.get("/reports/overview", headers=api.admin.headers).json()["counts"]["projects"] == 0
    assert api.client.get("/reports/overview", headers=employee.headers).status_code == 403


def test_my_dashboard_for_an_employee(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project = api.project(manager, budget=9999)
    api.assign(project["id"], employee, start_date="2026-03-02")
    api.client.post(f"/projects/{project['id']}/time-entries", json={"work_date": "2026-03-11", "hours": 5}, headers=employee.headers)
    api.client.post(f"/projects/{project['id']}/time-entries", json={"work_date": "2026-03-10", "hours": 8}, headers=employee.headers)

    mine = api.client.get("/reports/my-dashboard", headers=employee.headers).json()
    assert mine["current_project"]["name"] == "Apollo"
    assert mine["hours_today"] == 5 and mine["hours_today_remaining"] == 3
    assert mine["hours_this_week"] == 13 and mine["week_capacity"] == 40  # Mon 9 .. Sun 15
    assert len(mine["recent_entries"]) == 2
    assert [p["name"] for p in mine["projects"]] == ["Apollo"] and mine["projects"][0]["budget_amount"] is None


def test_my_dashboard_for_a_manager_lists_their_projects(api, today):
    manager = api.user("manager")
    api.project(manager, name="Mine")
    mine = api.client.get("/reports/my-dashboard", headers=manager.headers).json()
    assert [p["name"] for p in mine["projects"]] == ["Mine"] and mine["current_project"] is None
