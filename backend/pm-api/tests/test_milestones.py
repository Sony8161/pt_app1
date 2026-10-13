"""Milestones: the building blocks of a project, planned inside its dates, hours and budget."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

M = {"name": "Design", "start_date": "2026-03-03", "due_date": "2026-03-20", "allocated_hours": 100, "budget_amount": 4000}


@pytest.fixture
def setup(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager, salary=50)
    project = api.project(manager, hours=300, budget=12000)
    return api, manager, employee, project["id"]


def test_manager_plans_a_milestone(setup):
    api, manager, _, pid = setup
    created = api.client.post(f"/projects/{pid}/milestones", json=M, headers=manager.headers)
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending" and body["is_overdue"] is False
    assert body["allocated_hours"] == 100 and body["budget_amount"] == 4000
    assert body["hours_worked"] == 0 and body["labor_cost"] == 0 and body["assignees"] == 0
    assert body["archived_at"] is None and body["deliverables_total"] == 0

    listed = api.client.get(f"/projects/{pid}/milestones", headers=manager.headers).json()
    assert listed["total"] == 1 and listed["planned_hours"] == 100 and listed["planned_budget"] == 4000

    patched = api.client.patch(
        f"/projects/{pid}/milestones/{body['id']}", json={"name": "Design v2", "status": "in_progress", "budget_amount": 5000},
        headers=manager.headers,
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Design v2" and patched.json()["status"] == "in_progress" and patched.json()["budget_amount"] == 5000


def test_status_cannot_be_set_to_completed_by_patch(setup):
    api, manager, _, pid = setup
    mid = api.milestone(pid, manager)["id"]
    resp = api.client.patch(f"/projects/{pid}/milestones/{mid}", json={"status": "completed"}, headers=manager.headers)
    assert resp.status_code == 400  # completing needs the deliverables reviewed: POST /complete


def test_progress_is_derived_from_the_people_on_it(setup):
    api, manager, employee, pid = setup
    other = api.user("employee", "Second", manager=manager, salary=30)
    mid = api.milestone(pid, manager)["id"]  # Mon 9 - Fri 27 March
    api.assign(pid, mid, employee, manager.headers)
    api.assign(pid, mid, other, manager.headers, start_date="2026-03-10")
    detail = api.client.get(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).json()
    # employee: Wed 11th only counted from today (default start today) = 1 day; other: Tue+Wed = 2 days
    assert detail["assignees"] == 2 and detail["hours_worked"] == 24
    assert detail["labor_cost"] == 8 * 50 * 1 + 8 * 30 * 2
    assert detail["budget_pct"] == round(100 * detail["labor_cost"] / 10000, 1)


def test_overdue_comes_from_the_due_date(setup):
    api, manager, _, pid = setup
    mid = api.milestone(pid, manager, name="Late", start="2026-03-02", due="2026-03-05")["id"]
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).json()["is_overdue"] is True
    summary = api.client.get(f"/projects/{pid}", headers=manager.headers).json()["summary"]
    assert summary["milestones_overdue"] == 1 and summary["risk_level"] == "at_risk"


def test_dates_must_be_inside_the_project_and_ordered(setup):
    api, manager, _, pid = setup
    for bad in ({"start_date": "2026-02-01"}, {"due_date": "2026-06-01"}, {"start_date": "2026-03-20", "due_date": "2026-03-10"}):
        assert api.client.post(f"/projects/{pid}/milestones", json={**M, **bad}, headers=manager.headers).status_code == 400


def test_planned_hours_and_budget_must_fit_the_project(setup):
    api, manager, _, pid = setup
    api.milestone(pid, manager, hours=200, budget=8000)
    over_hours = api.client.post(
        f"/projects/{pid}/milestones", json={**M, "allocated_hours": 150, "budget_amount": 100}, headers=manager.headers
    )
    assert over_hours.status_code == 400 and over_hours.json()["error"]["details"][0]["field"] == "allocated_hours"
    over_budget = api.client.post(
        f"/projects/{pid}/milestones", json={**M, "allocated_hours": 10, "budget_amount": 5000}, headers=manager.headers
    )
    assert over_budget.status_code == 400 and over_budget.json()["error"]["details"][0]["field"] == "budget_amount"
    # the project cannot shrink below what the milestones plan either
    assert api.client.patch(f"/projects/{pid}", json={"budget_amount": 7000}, headers=manager.headers).status_code == 400
    assert api.client.patch(f"/projects/{pid}", json={"allocated_hours": 150}, headers=manager.headers).status_code == 400


def test_duplicate_names_conflict(setup):
    api, manager, _, pid = setup
    api.client.post(f"/projects/{pid}/milestones", json=M, headers=manager.headers)
    assert api.client.post(f"/projects/{pid}/milestones", json={**M, "name": "design"}, headers=manager.headers).status_code == 409


def test_milestone_dates_must_still_cover_the_people_on_it(setup):
    api, manager, employee, pid = setup
    mid = api.milestone(pid, manager)["id"]
    api.assign(pid, mid, employee, manager.headers, start_date="2026-03-16", end_date="2026-03-20")
    url = f"/projects/{pid}/milestones/{mid}"
    assert api.client.patch(url, json={"due_date": "2026-03-18"}, headers=manager.headers).status_code == 400
    assert api.client.patch(url, json={"start_date": "2026-03-17"}, headers=manager.headers).status_code == 400
    assert api.client.patch(url, json={"due_date": "2026-04-03"}, headers=manager.headers).status_code == 200


def test_roles(setup):
    api, manager, employee, pid = setup
    other = api.user("manager", "Other")
    mid = api.milestone(pid, manager, budget=5000)["id"]
    api.assign(pid, mid, employee, manager.headers)
    url = f"/projects/{pid}/milestones"
    assert api.client.post(url, json=M, headers=employee.headers).status_code == 403
    assert api.client.post(url, json=M, headers=other.headers).status_code == 404
    assert api.client.post(url, json=M, headers=api.admin.headers).status_code == 201
    seen = api.client.get(url, headers=employee.headers).json()  # employees may read, without money
    assert seen["total"] == 2 and seen["planned_budget"] is None
    assert all(i["budget_amount"] is None and i["labor_cost"] is None for i in seen["items"])


def test_complete_requires_reviewed_deliverables(setup):
    api, manager, _, pid = setup
    mid = api.milestone(pid, manager)["id"]
    url = f"/projects/{pid}/milestones/{mid}/complete"
    none_yet = api.client.post(url, json={}, headers=manager.headers)
    assert none_yet.status_code == 409 and none_yet.json()["error"]["code"] == "no_deliverables"

    api.deliverable(pid, mid, "Design file", done=True, manager=manager)
    api.deliverable(pid, mid, "Test report", manager=manager)
    open_items = api.client.post(url, json={}, headers=manager.headers)
    assert open_items.status_code == 409
    err = open_items.json()["error"]
    assert err["code"] == "deliverables_incomplete" and "Test report" in err["message"] and "Design file" not in err["message"]


def test_completing_archives_the_milestone_and_frees_the_team(setup):
    api, manager, employee, pid = setup
    mid = api.milestone(pid, manager)["id"]
    api.assign(pid, mid, employee, manager.headers)
    api.deliverable(pid, mid, "Design file", done=True, manager=manager)

    done = api.client.post(f"/projects/{pid}/milestones/{mid}/complete", json={"review_note": "Signed off by the client"}, headers=manager.headers)
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "completed" and body["completed_at"] and body["archived_at"]
    assert body["review_note"] == "Signed off by the client"

    # archived: invisible to the manager and the employee, visible to the admin
    assert api.client.get(f"/projects/{pid}/milestones", headers=manager.headers).json()["total"] == 0
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).status_code == 404
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=employee.headers).status_code == 404
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=api.admin.headers).json()["status"] == "completed"
    assert api.client.get(f"/projects/{pid}/milestones?include_archived=true", headers=api.admin.headers).json()["total"] == 1
    # ... yet it still counts in the project's progress
    summary = api.client.get(f"/projects/{pid}", headers=manager.headers).json()["summary"]
    assert summary["milestones_total"] == 1 and summary["milestones_done"] == 1 and summary["milestones_pct"] == 100
    assert summary["hours_worked"] == 8  # the employee worked today, then was freed

    # the employee is free from tomorrow, not today
    nxt = api.milestone(pid, manager, name="Next", start="2026-03-11", due="2026-03-27", hours=50, budget=1000)
    assert api.assign(pid, nxt["id"], employee, manager.headers, start_date="2026-03-11").status_code == 409
    assert api.assign(pid, nxt["id"], employee, manager.headers, start_date="2026-03-12").status_code == 201


def test_a_completed_milestone_cannot_be_changed(setup):
    api, manager, _, pid = setup
    mid = api.milestone(pid, manager)["id"]
    api.deliverable(pid, mid, "Design file", done=True, manager=manager)
    api.client.post(f"/projects/{pid}/milestones/{mid}/complete", json={}, headers=manager.headers)
    url = f"/projects/{pid}/milestones/{mid}"
    assert api.client.patch(url, json={"name": "Renamed"}, headers=api.admin.headers).status_code == 409
    assert api.client.post(f"{url}/complete", json={}, headers=api.admin.headers).status_code == 409
    assert api.client.post(f"{url}/archive", headers=api.admin.headers).status_code == 409


def test_cancelling_archives_without_counting_towards_the_project(setup):
    api, manager, _, pid = setup
    mid = api.milestone(pid, manager, name="By mistake")["id"]
    assert api.client.get(f"/projects/{pid}", headers=manager.headers).json()["summary"]["milestones_total"] == 1
    cancelled = api.client.post(f"/projects/{pid}/milestones/{mid}/archive", headers=manager.headers)
    assert cancelled.status_code == 200 and cancelled.json()["archived_at"] and cancelled.json()["status"] == "pending"
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).status_code == 404
    assert api.client.get(f"/projects/{pid}", headers=manager.headers).json()["summary"]["milestones_total"] == 0
    assert api.milestone(pid, manager, name="By mistake")  # the name is free again


def test_no_changes_once_the_project_is_completed(setup):
    api, manager, _, pid = setup
    api.client.post(f"/projects/{pid}/complete", headers=manager.headers)
    assert api.client.post(f"/projects/{pid}/milestones", json=M, headers=manager.headers).status_code == 409
