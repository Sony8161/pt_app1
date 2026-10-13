"""Time tracking: 8-hour days, assignment dates, and who may log for whom."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def team(api, today):
    manager = api.user("manager")
    employee = api.user("employee", "Dev One", manager=manager, salary=40)
    project = api.project(manager, start="2026-03-02", end="2026-04-30")
    api.assign(project["id"], employee, start_date="2026-03-02")
    return api, manager, employee, project["id"]


def log(api, who, pid, day="2026-03-10", hours=4, **extra):
    return api.client.post(f"/projects/{pid}/time-entries", json={"work_date": day, "hours": hours, **extra}, headers=who.headers)


def test_employee_logs_time_and_labor_cost_uses_salary(team):
    api, manager, employee, pid = team
    entry = log(api, employee, pid, hours=5, notes="Built the thing")
    assert entry.status_code == 201
    assert entry.json()["labor_cost"] is None and entry.json()["project_name"] == "Apollo"  # hidden from the employee
    as_manager = api.client.get(f"/projects/{pid}/time-entries", headers=manager.headers).json()
    assert as_manager["items"][0]["labor_cost"] == 200

    project = api.client.get(f"/projects/{pid}", headers=manager.headers).json()
    assert project["summary"]["hours_logged"] == 5 and project["summary"]["labor_cost"] == 200
    assert project["summary"]["total_cost"] == 200 and project["summary"]["budget_remaining"] == 49800


def test_a_day_holds_at_most_eight_hours(team):
    api, _, employee, pid = team
    assert log(api, employee, pid, hours=5).status_code == 201
    over = log(api, employee, pid, hours=4)
    assert over.status_code == 409 and over.json()["error"]["code"] == "daily_limit"
    assert "3 h are left" in over.json()["error"]["message"]
    assert log(api, employee, pid, hours=3).status_code == 201
    assert log(api, employee, pid, hours=0.25).status_code == 409
    assert log(api, employee, pid, day="2026-03-09", hours=8).status_code == 201  # another day is fresh
    assert log(api, employee, pid, hours=9).status_code == 400  # a single entry is capped too
    assert log(api, employee, pid, hours=0).status_code == 400


def test_only_inside_the_assignment_dates_and_never_in_the_future(team):
    api, _, employee, pid = team
    before = log(api, employee, pid, day="2026-03-01")
    assert before.status_code == 409 and before.json()["error"]["code"] == "not_assigned"
    future = log(api, employee, pid, day="2026-03-12")
    assert future.status_code == 400 and future.json()["error"]["details"][0]["field"] == "work_date"


def test_unassigned_people_and_planned_projects_cannot_log(api, today):
    manager = api.user("manager")
    outsider = api.user("employee", manager=manager)
    later = api.project(manager, name="Later", start="2026-04-01", end="2026-05-01")
    assert log(api, outsider, later["id"]).status_code == 404  # cannot even see it
    member = api.user("employee", "Member", manager=manager)
    api.assign(later["id"], member)
    not_started = log(api, member, later["id"])
    assert not_started.status_code == 409 and "not started" in not_started.json()["error"]["message"]


def test_employees_log_only_for_themselves(team):
    api, manager, employee, pid = team
    mate = api.user("employee", "Mate", manager=manager)
    api.assign(pid, mate, start_date="2026-03-02")
    assert log(api, employee, pid, user_id=mate.id).status_code == 403
    for_mate = log(api, manager, pid, user_id=mate.id)  # the project's manager may
    assert for_mate.status_code == 201 and for_mate.json()["user_id"] == mate.id
    assert log(api, api.admin, pid, user_id=employee.id).status_code == 201
    other = api.user("manager", "Other")
    assert log(api, other, pid, user_id=mate.id).status_code == 404


def test_milestone_must_belong_to_the_project(team):
    api, manager, employee, pid = team
    other_project = api.project(manager, name="Other")
    ms = api.client.post(
        f"/projects/{other_project['id']}/milestones",
        json={"name": "Elsewhere", "start_date": "2026-03-03", "due_date": "2026-03-10"}, headers=manager.headers,
    ).json()
    assert log(api, employee, pid, milestone_id=ms["id"]).status_code == 400


def test_listing_scope_and_filters(team):
    api, manager, employee, pid = team
    mate = api.user("employee", "Mate", manager=manager)
    api.assign(pid, mate, start_date="2026-03-02")
    log(api, employee, pid, day="2026-03-09", hours=3)
    log(api, employee, pid, day="2026-03-10", hours=2)
    log(api, mate, pid, day="2026-03-10", hours=6)

    everyone = api.client.get(f"/projects/{pid}/time-entries", headers=manager.headers).json()
    assert everyone["total"] == 3 and everyone["total_hours"] == 11
    only_mine = api.client.get(f"/projects/{pid}/time-entries?user_id={mate.id}", headers=employee.headers).json()
    assert only_mine["total"] == 2 and all(e["user_id"] == employee.id for e in only_mine["items"])  # filter ignored for employees
    assert all(e["labor_cost"] is None for e in only_mine["items"])
    ranged = api.client.get(f"/projects/{pid}/time-entries?from=2026-03-10&to=2026-03-10", headers=manager.headers).json()
    assert ranged["total"] == 2
    one = api.client.get(f"/projects/{pid}/time-entries?user_id={mate.id}", headers=manager.headers).json()
    assert one["total_hours"] == 6


def test_my_time_has_daily_totals(team):
    api, _, employee, pid = team
    log(api, employee, pid, day="2026-03-10", hours=3)
    log(api, employee, pid, day="2026-03-10", hours=2.5)
    log(api, employee, pid, day="2026-03-09", hours=8)
    mine = api.client.get("/time-entries/me", headers=employee.headers).json()
    assert mine["total_hours"] == 13.5
    assert mine["daily_totals"][0] == {"date": "2026-03-10", "hours": 5.5, "remaining": 2.5}
    assert api.client.get("/time-entries/me?from=2026-03-11&to=2026-03-01", headers=employee.headers).status_code == 400


def test_removing_entries(team):
    api, manager, employee, pid = team
    mate = api.user("employee", "Mate", manager=manager)
    api.assign(pid, mate, start_date="2026-03-02")
    mine = log(api, employee, pid).json()["id"]
    theirs = log(api, mate, pid).json()["id"]
    assert api.client.delete(f"/projects/{pid}/time-entries/{theirs}", headers=employee.headers).status_code == 403
    assert api.client.delete(f"/projects/{pid}/time-entries/{mine}", headers=employee.headers).status_code == 204
    assert api.client.delete(f"/projects/{pid}/time-entries/{mine}", headers=employee.headers).status_code == 404
    assert api.client.delete(f"/projects/{pid}/time-entries/{theirs}", headers=manager.headers).status_code == 204
    assert api.client.get(f"/projects/{pid}/time-entries", headers=manager.headers).json()["total"] == 0
    # the freed hours can be used again
    assert log(api, employee, pid, hours=8).status_code == 201


def test_no_logging_after_the_project_is_completed(team):
    api, manager, employee, pid = team
    api.client.post(f"/projects/{pid}/complete", headers=manager.headers)
    resp = log(api, employee, pid)
    assert resp.status_code == 409 and "completed" in resp.json()["error"]["message"]
