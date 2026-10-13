"""Projects: who can create/see/change them, date-driven status, lifecycle and archive."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_only_admin_creates_projects_and_manager_must_be_a_manager(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    body = {"name": "Nope", "manager_id": manager.id, "start_date": "2026-03-02", "end_date": "2026-04-30"}
    assert api.client.post("/projects", json=body, headers=manager.headers).status_code == 403
    assert api.client.post("/projects", json=body, headers=employee.headers).status_code == 403
    not_a_manager = api.client.post("/projects", json={**body, "manager_id": employee.id}, headers=api.admin.headers)
    assert not_a_manager.status_code == 400 and not_a_manager.json()["error"]["details"][0]["field"] == "manager_id"


def test_create_returns_summary_built_from_dates(api, today):
    manager = api.user("manager")
    project = api.project(manager, start="2026-03-01", end="2026-04-09", hours=400, budget=20000)  # 40 days, 11 elapsed
    assert project["status"] == "active" and project["manager"]["id"] == manager.id
    s = project["summary"]
    assert s["days_total"] == 40 and s["days_elapsed"] == 11 and s["schedule_pct"] == 27.5
    assert s["days_remaining"] == 29 and s["risk_level"] == "on_track" and s["total_cost"] == 0


def test_status_follows_start_date_without_manual_changes(api, today):
    manager = api.user("manager")
    future = api.project(manager, name="Later", start="2026-03-12", end="2026-05-01")
    started = api.project(manager, name="Started", start="2026-03-11", end="2026-05-01")
    assert future["status"] == "planned" and started["status"] == "active"
    planned = api.client.get("/projects?status=planned", headers=api.admin.headers).json()
    assert [p["name"] for p in planned["items"]] == ["Later"]


def test_validation_and_duplicate_names(api, today):
    manager = api.user("manager")
    api.project(manager, name="Apollo")
    base = {"manager_id": manager.id, "start_date": "2026-03-02", "end_date": "2026-04-30"}
    assert api.client.post("/projects", json={**base, "name": "apollo"}, headers=api.admin.headers).status_code == 409
    backwards = api.client.post("/projects", json={**base, "name": "X", "end_date": "2026-03-01"}, headers=api.admin.headers)
    assert backwards.status_code == 400
    assert api.client.post("/projects", json={**base, "name": "  "}, headers=api.admin.headers).status_code == 400
    assert api.client.post("/projects", json={**base, "name": "Y", "budget_amount": -1}, headers=api.admin.headers).status_code == 400


def test_visibility_by_role_returns_404_not_403(api, today):
    mine, other = api.user("manager", "Mine"), api.user("manager", "Other")
    on_it = api.user("employee", "On It", manager=mine)
    not_on_it = api.user("employee", "Not On It", manager=mine)
    project, _ = api.setup_work(mine, on_it)
    url = f"/projects/{project['id']}"

    assert api.client.get(url, headers=api.admin.headers).status_code == 200
    assert api.client.get(url, headers=mine.headers).status_code == 200
    assert api.client.get(url, headers=on_it.headers).status_code == 200
    assert api.client.get(url, headers=other.headers).status_code == 404
    assert api.client.get(url, headers=not_on_it.headers).status_code == 404

    assert api.client.get("/projects", headers=other.headers).json()["total"] == 0
    assert api.client.get("/projects", headers=not_on_it.headers).json()["total"] == 0
    assert api.client.get("/projects", headers=on_it.headers).json()["total"] == 1


def test_employee_never_sees_money(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project, _ = api.setup_work(manager, employee)
    seen = api.client.get(f"/projects/{project['id']}", headers=employee.headers).json()
    assert seen["budget_amount"] is None
    money = ("labor_cost", "other_cost", "total_cost", "budget_remaining", "budget_pct", "forecast_cost")
    assert all(seen["summary"][k] is None for k in money)
    assert api.client.get(f"/projects/{project['id']}", headers=manager.headers).json()["budget_amount"] == 50000


def test_search_filter_and_paging(api, today):
    m1, m2 = api.user("manager", "Ann Lee"), api.user("manager", "Bob Ray")
    for i, m in enumerate([m1, m1, m2]):
        api.project(m, name=f"Project {i}")
    h = api.admin.headers
    assert api.client.get("/projects?q=ann", headers=h).json()["total"] == 2  # matches manager name
    assert api.client.get(f"/projects?manager_id={m2.id}", headers=h).json()["total"] == 1
    page = api.client.get("/projects?page=2&page_size=2", headers=h).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["page"] == 2
    assert api.client.get("/projects?page_size=1000", headers=h).status_code == 400


def test_manager_edits_budget_but_cannot_reassign_or_touch_others(api, today):
    mine, other = api.user("manager", "Mine"), api.user("manager", "Other")
    project = api.project(mine)
    url = f"/projects/{project['id']}"
    ok = api.client.patch(url, json={"budget_amount": 75000, "allocated_hours": 900}, headers=mine.headers)
    assert ok.status_code == 200 and ok.json()["budget_amount"] == 75000
    assert api.client.patch(url, json={"manager_id": other.id}, headers=mine.headers).status_code == 403
    assert api.client.patch(url, json={"budget_amount": 1}, headers=other.headers).status_code == 404
    moved = api.client.patch(url, json={"manager_id": other.id}, headers=api.admin.headers)
    assert moved.status_code == 200 and moved.json()["manager"]["id"] == other.id
    assert api.client.patch(url, json={"name": None}, headers=api.admin.headers).status_code == 400


def test_employee_cannot_edit(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project, _ = api.setup_work(manager, employee)
    assert api.client.patch(f"/projects/{project['id']}", json={"budget_amount": 1}, headers=employee.headers).status_code == 403
    assert api.client.post(f"/projects/{project['id']}/complete", headers=employee.headers).status_code == 403


def test_dates_cannot_shrink_past_milestones(api, today):
    manager = api.user("manager")
    project = api.project(manager, start="2026-03-02", end="2026-04-30")
    pid = project["id"]
    api.milestone(pid, manager, name="M1", start="2026-03-10", due="2026-04-20", hours=10, budget=100)
    url = f"/projects/{pid}"
    assert api.client.patch(url, json={"end_date": "2026-04-10"}, headers=manager.headers).status_code == 400
    assert api.client.patch(url, json={"start_date": "2026-03-12"}, headers=manager.headers).status_code == 400
    assert api.client.patch(url, json={"start_date": "2026-03-01", "end_date": "2026-05-15"}, headers=manager.headers).status_code == 200


def test_completing_ends_everyones_work_today_and_freezes_the_project(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    first, ms1 = api.setup_work(manager, employee, project="First")
    second = api.project(manager, name="Second", start="2026-03-02", end="2026-06-30")
    ms2 = api.milestone(second["id"], manager, name="Next", start="2026-03-09", due="2026-06-30")
    assert api.assign(second["id"], ms2["id"], employee, manager.headers).status_code == 409  # still busy on First

    done = api.client.post(f"/projects/{first['id']}/complete", headers=manager.headers)
    assert done.status_code == 200 and done.json()["status"] == "completed" and done.json()["completed_at"]
    assert done.json()["summary"]["risk_level"] == "done"

    # busy until today inclusive; free from tomorrow
    assert api.assign(second["id"], ms2["id"], employee, manager.headers).status_code == 409
    assert api.assign(second["id"], ms2["id"], employee, manager.headers, start_date="2026-03-12").status_code == 201

    frozen = api.client.patch(f"/projects/{first['id']}", json={"budget_amount": 1}, headers=manager.headers)
    assert frozen.status_code == 409
    assert api.client.post(f"/projects/{first['id']}/complete", headers=manager.headers).status_code == 409
    assert ms1["id"]


def test_cannot_complete_a_project_that_has_not_started(api, today):
    manager = api.user("manager")
    project = api.project(manager, start="2026-04-01", end="2026-05-01")
    assert api.client.post(f"/projects/{project['id']}/complete", headers=manager.headers).status_code == 409


def test_archive_is_admin_only_hides_the_project_and_can_be_undone(api, today):
    manager = api.user("manager")
    project = api.project(manager)
    pid = project["id"]
    assert api.client.post(f"/projects/{pid}/archive", headers=manager.headers).status_code == 403

    archived = api.client.post(f"/projects/{pid}/archive", headers=api.admin.headers)
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    assert api.client.get("/projects", headers=api.admin.headers).json()["total"] == 0
    assert api.client.get("/projects?include_archived=true", headers=api.admin.headers).json()["total"] == 1
    assert api.client.get("/projects?include_archived=true", headers=manager.headers).json()["total"] == 0
    assert api.client.get(f"/projects/{pid}", headers=manager.headers).status_code == 404
    assert api.client.get(f"/projects/{pid}", headers=api.admin.headers).status_code == 200

    # the name is free again while archived, but restoring then clashes
    api.project(manager, name=project["name"])
    assert api.client.post(f"/projects/{pid}/unarchive", headers=api.admin.headers).status_code == 409


def test_unarchive_restores_state(api, today):
    manager = api.user("manager")
    project = api.project(manager)
    pid = project["id"]
    api.client.post(f"/projects/{pid}/archive", headers=api.admin.headers)
    restored = api.client.post(f"/projects/{pid}/unarchive", headers=api.admin.headers).json()
    assert restored["archived_at"] is None and restored["status"] == "active"


def test_unknown_or_malformed_id(api, new_id):
    assert api.client.get(f"/projects/{new_id()}", headers=api.admin.headers).status_code == 404
    assert api.client.get("/projects/nope", headers=api.admin.headers).status_code == 400
