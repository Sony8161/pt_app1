"""Milestones: managers build the plan inside the project's dates and hours."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

M = {"name": "Design", "start_date": "2026-03-03", "due_date": "2026-03-20", "allocated_hours": 100}


@pytest.fixture
def setup(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project = api.project(manager, hours=300)
    api.assign(project["id"], employee)
    return api, manager, employee, project["id"]


def test_manager_creates_lists_and_updates(setup):
    api, manager, _, pid = setup
    created = api.client.post(f"/projects/{pid}/milestones", json=M, headers=manager.headers)
    assert created.status_code == 201
    mid = created.json()["id"]
    assert created.json()["status"] == "pending" and created.json()["is_overdue"] is False

    listed = api.client.get(f"/projects/{pid}/milestones", headers=manager.headers).json()
    assert listed["total"] == 1 and listed["planned_hours"] == 100

    patched = api.client.patch(f"/projects/{pid}/milestones/{mid}", json={"allocated_hours": 150, "name": "Design v2"}, headers=manager.headers)
    assert patched.status_code == 200 and patched.json()["name"] == "Design v2"


def test_marking_done_sets_and_clears_completion_time(setup):
    api, manager, _, pid = setup
    mid = api.client.post(f"/projects/{pid}/milestones", json=M, headers=manager.headers).json()["id"]
    url = f"/projects/{pid}/milestones/{mid}"
    done = api.client.patch(url, json={"status": "done"}, headers=manager.headers).json()
    assert done["status"] == "done" and done["completed_at"] and done["is_overdue"] is False
    reopened = api.client.patch(url, json={"status": "in_progress"}, headers=manager.headers).json()
    assert reopened["completed_at"] is None
    assert api.client.get(f"/projects/{pid}", headers=manager.headers).json()["summary"]["milestones_done"] == 0


def test_overdue_flag_comes_from_the_due_date(setup):
    api, manager, _, pid = setup
    past = {**M, "name": "Past", "start_date": "2026-03-02", "due_date": "2026-03-05"}
    mid = api.client.post(f"/projects/{pid}/milestones", json=past, headers=manager.headers).json()["id"]
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).json()["is_overdue"] is True
    summary = api.client.get(f"/projects/{pid}", headers=manager.headers).json()["summary"]
    assert summary["milestones_overdue"] == 1 and summary["risk_level"] == "at_risk"


def test_dates_must_be_inside_the_project_and_ordered(setup):
    api, manager, _, pid = setup
    for bad in ({"start_date": "2026-02-01"}, {"due_date": "2026-06-01"}, {"start_date": "2026-03-20", "due_date": "2026-03-10"}):
        assert api.client.post(f"/projects/{pid}/milestones", json={**M, **bad}, headers=manager.headers).status_code == 400


def test_hours_cannot_exceed_the_project_allocation(setup):
    api, manager, _, pid = setup
    assert api.client.post(f"/projects/{pid}/milestones", json={**M, "allocated_hours": 200}, headers=manager.headers).status_code == 201
    over = api.client.post(f"/projects/{pid}/milestones", json={**M, "name": "More", "allocated_hours": 150}, headers=manager.headers)
    assert over.status_code == 400 and over.json()["error"]["details"][0]["field"] == "allocated_hours"


def test_duplicate_names_conflict(setup):
    api, manager, _, pid = setup
    api.client.post(f"/projects/{pid}/milestones", json=M, headers=manager.headers)
    assert api.client.post(f"/projects/{pid}/milestones", json={**M, "name": "design"}, headers=manager.headers).status_code == 409


def test_roles(setup):
    api, manager, employee, pid = setup
    other = api.user("manager", "Other")
    url = f"/projects/{pid}/milestones"
    assert api.client.post(url, json=M, headers=employee.headers).status_code == 403
    assert api.client.get(url, headers=employee.headers).status_code == 200  # may read
    assert api.client.post(url, json=M, headers=other.headers).status_code == 404
    assert api.client.post(url, json=M, headers=api.admin.headers).status_code == 201


def test_archive_removes_it_from_the_plan_but_keeps_time_link(setup, today):
    api, manager, employee, pid = setup
    mid = api.client.post(f"/projects/{pid}/milestones", json=M, headers=manager.headers).json()["id"]
    logged = api.client.post(f"/projects/{pid}/time-entries", json={"work_date": "2026-03-11", "hours": 6, "milestone_id": mid}, headers=employee.headers)
    assert logged.status_code == 201
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).json()["hours_logged"] == 6
    assert api.client.delete(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).status_code == 204
    assert api.client.get(f"/projects/{pid}/milestones", headers=manager.headers).json()["total"] == 0
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).status_code == 404


def test_cannot_change_milestones_after_completion(setup):
    api, manager, _, pid = setup
    api.client.post(f"/projects/{pid}/complete", headers=manager.headers)
    assert api.client.post(f"/projects/{pid}/milestones", json=M, headers=manager.headers).status_code == 409
