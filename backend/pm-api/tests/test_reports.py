"""Dashboards: health, allocation and the personal view (hours come from the calendar, not from logs)."""

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
    ms = api.milestone(healthy["id"], manager, start="2026-03-09", due="2026-03-20", hours=100, budget=4000)  # 10 working days
    api.assign(healthy["id"], ms["id"], busy, manager.headers, start_date="2026-03-09")  # worked Mon, Tue, Wed
    api.milestone(soon["id"], manager, name="Past due", start="2026-03-02", due="2026-03-05", hours=10, budget=100)
    api.client.post(f"/projects/{healthy['id']}/costs", json={"category": "vendor", "description": "x", "amount": 400, "incurred_on": "2026-03-05"}, headers=manager.headers)

    out = api.client.get("/reports/overview", headers=manager.headers).json()
    assert [p["name"] for p in out["projects"]] == ["Late", "Soon", "Healthy"]
    assert [p["summary"]["risk_level"] for p in out["projects"]] == ["overdue", "at_risk", "on_track"]
    assert out["counts"] == {"projects": 3, "planned": 0, "active": 3, "completed": 0, "on_track": 1, "at_risk": 1, "overdue": 1}
    totals = out["totals"]
    assert totals["budget"] == 35000 and totals["labor_cost"] == 1200 and totals["other_cost"] == 400
    assert totals["spent"] == 1600 and totals["budget_remaining"] == 33400
    assert totals["hours_allocated"] == 1600 and totals["hours_worked"] == 24
    assert totals["forecast_cost"] == 10 * 8 * 50 + 400  # the whole planned range plus other costs
    assert late["id"] and out["as_of"] == "2026-03-11"


def test_allocation_shows_who_is_busy_and_who_is_free(api, today):
    manager = api.user("manager")
    busy = api.user("employee", "Busy", manager=manager)
    api.user("employee", "Free", manager=manager)
    soon = api.user("employee", "Soon", manager=manager)
    now_project = api.project(manager, name="Now", start="2026-03-01", end="2026-04-01")
    next_project = api.project(manager, name="Next", start="2026-05-01", end="2026-06-01")
    ms_now = api.milestone(now_project["id"], manager, name="Now work", start="2026-03-09", due="2026-03-27")
    ms_next = api.milestone(next_project["id"], manager, name="Next work", start="2026-05-04", due="2026-05-29")
    api.assign(now_project["id"], ms_now["id"], busy, manager.headers, start_date="2026-03-09")
    api.assign(next_project["id"], ms_next["id"], soon, manager.headers)

    out = api.client.get("/reports/overview", headers=manager.headers).json()
    people = {p["name"]: p for p in out["allocation"]}
    assert people["Busy"]["state"] == "allocated"
    assert people["Busy"]["current_work"]["milestone_name"] == "Now work" and people["Busy"]["current_work"]["project_name"] == "Now"
    assert people["Busy"]["hours_this_week"] == 24  # Mon, Tue, Wed
    assert people["Free"]["state"] == "available" and people["Free"]["current_work"] is None
    assert people["Soon"]["state"] == "available" and people["Soon"]["next_work"]["milestone_name"] == "Next work"
    assert out["available_people"] == 2 and people["Free"]["week_capacity"] == 40


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
    ms = api.milestone(project["id"], manager, hours=100, budget=500)
    api.deliverable(project["id"], ms["id"], "Spec", done=True, manager=manager)
    api.deliverable(project["id"], ms["id"], "Tests", manager=manager)
    api.assign(project["id"], ms["id"], employee, manager.headers, start_date="2026-03-09")

    mine = api.client.get("/reports/my-dashboard", headers=employee.headers).json()
    assert mine["current_work"]["milestone_name"] == "Build" and mine["current_work"]["project_name"] == "Apollo"
    assert mine["hours_today"] == 8 and mine["hours_this_week"] == 24 and mine["week_capacity"] == 40
    assert len(mine["my_milestones"]) == 1
    work = mine["my_milestones"][0]
    assert work["milestone_name"] == "Build" and work["deliverables_total"] == 2 and work["deliverables_done"] == 1
    assert [p["name"] for p in mine["projects"]] == ["Apollo"] and mine["projects"][0]["budget_amount"] is None


def test_weekends_are_not_shifts(api, today, monkeypatch):
    from app.core import dates

    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    api.setup_work(manager, employee)
    monkeypatch.setattr(dates, "today", lambda: __import__("datetime").date(2026, 3, 14))  # a Saturday
    mine = api.client.get("/reports/my-dashboard", headers=employee.headers).json()
    assert mine["hours_today"] == 0


def test_my_dashboard_for_a_manager_lists_their_projects(api, today):
    manager = api.user("manager")
    api.project(manager, name="Mine")
    mine = api.client.get("/reports/my-dashboard", headers=manager.headers).json()
    assert [p["name"] for p in mine["projects"]] == ["Mine"] and mine["current_work"] is None and mine["my_milestones"] == []
