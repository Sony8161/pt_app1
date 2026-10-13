"""Teams: one project at a time per person, dates drive everything."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_assign_defaults_to_today_for_a_running_project(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project = api.project(manager, start="2026-03-02", end="2026-04-30")
    resp = api.assign(project["id"], employee, manager.headers)
    assert resp.status_code == 201
    member = resp.json()
    assert member["start_date"] == "2026-03-11" and member["end_date"] == "2026-04-30" and member["daily_hours"] == 8
    assert member["labor_cost"] == 0 and member["name"] == employee.name


def test_future_project_defaults_to_its_own_dates(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project = api.project(manager, start="2026-04-01", end="2026-05-01")
    member = api.assign(project["id"], employee).json()
    assert member["start_date"] == "2026-04-01" and member["end_date"] == "2026-05-01"


def test_a_person_cannot_be_on_two_projects_at_once(api, today):
    manager = api.user("manager")
    employee = api.user("employee", "Busy Bee", manager=manager)
    first = api.project(manager, name="First", end="2026-04-10")
    second = api.project(manager, name="Second", start="2026-03-02", end="2026-06-30")
    assert api.assign(first["id"], employee).status_code == 201

    clash = api.assign(second["id"], employee, start_date="2026-04-01", end_date="2026-05-01")
    assert clash.status_code == 409
    error = clash.json()["error"]
    assert error["code"] == "assignment_overlap" and "Busy Bee" in error["message"] and "'First'" in error["message"]

    # the very next day is fine: several projects over time, one at a time
    assert api.assign(second["id"], employee, start_date="2026-04-11").status_code == 201


def test_different_people_can_share_a_project(api, today):
    manager = api.user("manager")
    project = api.project(manager)
    for i in range(5):
        assert api.assign(project["id"], api.user("employee", f"Person {i}", manager=manager)).status_code == 201
    assert api.client.get(f"/projects/{project['id']}/team", headers=manager.headers).json()["total"] == 5


def test_only_active_employees_can_be_assigned(api, today):
    manager = api.user("manager")
    other_manager = api.user("manager", "Second")
    project = api.project(manager)
    assert api.assign(project["id"], other_manager).status_code == 400
    archived = api.user("employee", manager=manager)
    api.client.post(f"/users/{archived.id}/archive", headers=api.admin.headers)
    assert api.assign(project["id"], archived).status_code == 400
    ghost = api.client.post(f"/projects/{project['id']}/team", json={"user_id": "00000000-0000-0000-0000-000000000000"}, headers=manager.headers)
    assert ghost.status_code == 400


def test_dates_must_be_inside_the_project(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project = api.project(manager, start="2026-03-02", end="2026-04-30")
    assert api.assign(project["id"], employee, start_date="2026-02-01").status_code == 400
    assert api.assign(project["id"], employee, end_date="2026-06-01").status_code == 400
    assert api.assign(project["id"], employee, start_date="2026-04-01", end_date="2026-03-20").status_code == 400


def test_adding_twice_is_a_conflict_and_removal_frees_the_person(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    a = api.project(manager, name="A")
    b = api.project(manager, name="B")
    assert api.assign(a["id"], employee).status_code == 201
    assert api.assign(a["id"], employee).status_code == 409
    assert api.assign(b["id"], employee).status_code == 409

    assert api.client.delete(f"/projects/{a['id']}/team/{employee.id}", headers=manager.headers).status_code == 204
    assert api.client.get(f"/projects/{a['id']}", headers=employee.headers).status_code == 404  # no longer visible
    assert api.assign(b["id"], employee).status_code == 201
    assert api.client.delete(f"/projects/{a['id']}/team/{employee.id}", headers=manager.headers).status_code == 404


def test_changing_dates_checks_overlap_and_logged_time(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    a = api.project(manager, name="A", start="2026-03-02", end="2026-04-30")
    b = api.project(manager, name="B", start="2026-03-02", end="2026-06-30")
    api.assign(a["id"], employee, start_date="2026-03-02", end_date="2026-03-31")
    api.assign(b["id"], employee, start_date="2026-04-01", end_date="2026-04-30")

    grow = api.client.patch(f"/projects/{a['id']}/team/{employee.id}", json={"end_date": "2026-04-05"}, headers=manager.headers)
    assert grow.status_code == 409  # would overlap B
    ok = api.client.patch(f"/projects/{a['id']}/team/{employee.id}", json={"end_date": "2026-03-30"}, headers=manager.headers)
    assert ok.status_code == 200 and ok.json()["end_date"] == "2026-03-30"

    api.client.post(f"/projects/{a['id']}/time-entries", json={"work_date": "2026-03-05", "hours": 8}, headers=employee.headers)
    cut = api.client.patch(f"/projects/{a['id']}/team/{employee.id}", json={"start_date": "2026-03-10"}, headers=manager.headers)
    assert cut.status_code == 409 and "already logged" in cut.json()["error"]["message"]


def test_roles(api, today):
    manager, other = api.user("manager"), api.user("manager", "Other")
    employee = api.user("employee", manager=manager)
    mate = api.user("employee", "Mate", manager=manager)
    project = api.project(manager)
    pid = project["id"]
    assert api.assign(pid, employee, other.headers).status_code == 404
    assert api.assign(pid, mate, employee.headers).status_code == 403
    assert api.assign(pid, employee, manager.headers).status_code == 201


def test_employee_sees_the_team_without_costs(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager, salary=40)
    mate = api.user("employee", "Mate", manager=manager)
    project = api.project(manager)
    api.assign(project["id"], employee)
    api.assign(project["id"], mate)
    api.client.post(f"/projects/{project['id']}/time-entries", json={"work_date": "2026-03-11", "hours": 8}, headers=employee.headers)

    mine = api.client.get(f"/projects/{project['id']}/team", headers=employee.headers).json()
    assert mine["total"] == 2 and all(m["labor_cost"] is None for m in mine["items"])
    managed = api.client.get(f"/projects/{project['id']}/team", headers=manager.headers).json()
    by_name = {m["name"]: m for m in managed["items"]}
    assert by_name[employee.name]["hours_logged"] == 8 and by_name[employee.name]["labor_cost"] == 320
