"""Nothing is ever deleted: no DELETE endpoints, every removal archives, and only admins see the archive."""

from __future__ import annotations

import pytest

from app.core import dates

pytestmark = pytest.mark.integration


def test_the_api_has_no_delete_operations():
    from app.main import app

    verbs = {verb for ops in app.openapi()["paths"].values() for verb in ops}
    assert "delete" not in verbs


def test_delete_requests_are_rejected(api, today):
    manager = api.user("manager")
    project = api.project(manager)
    ms = api.milestone(project["id"], manager)
    for url in (f"/projects/{project['id']}", f"/projects/{project['id']}/milestones/{ms['id']}", f"/users/{manager.id}"):
        assert api.client.delete(url, headers=api.admin.headers).status_code == 405


def test_shift_hours_in_sql_match_the_constant(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project, ms = api.setup_work(manager, employee)
    member = api.client.get(f"/projects/{project['id']}/milestones/{ms['id']}/team", headers=manager.headers).json()["items"][0]
    assert member["daily_hours"] == dates.DAILY_HOURS == 8
    assert member["hours_worked"] == member["days_worked"] * dates.DAILY_HOURS


def test_archiving_keeps_every_row_and_hides_it_from_non_admins(api, raw_db, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager, salary=40)
    project = api.project(manager)
    pid = project["id"]
    ms = api.milestone(pid, manager, name="Cancelled one")
    mid = ms["id"]
    item = api.deliverable(pid, mid, "Spec")
    api.assign(pid, mid, employee, manager.headers, start_date="2026-03-16")  # starts in the future
    cost = api.client.post(
        f"/projects/{pid}/costs", json={"category": "other", "description": "x", "amount": 10, "incurred_on": "2026-03-10"},
        headers=manager.headers,
    ).json()

    h = manager.headers
    assert api.client.post(f"/projects/{pid}/milestones/{mid}/deliverables/{item['id']}/archive", headers=h).status_code == 200
    assert api.client.post(f"/projects/{pid}/milestones/{mid}/team/{employee.id}/archive", headers=h).status_code == 200
    assert api.client.post(f"/projects/{pid}/costs/{cost['id']}/archive", headers=h).status_code == 200
    assert api.client.post(f"/projects/{pid}/milestones/{mid}/archive", headers=h).status_code == 200
    assert api.client.post(f"/projects/{pid}/archive", headers=api.admin.headers).status_code == 200
    assert api.client.post(f"/users/{employee.id}/archive", headers=api.admin.headers).status_code == 200

    # every row is still in the database, marked archived
    for table, key, value in [
        ("deliverables", "id", item["id"]), ("milestone_assignments", "milestone_id", mid), ("project_costs", "id", cost["id"]),
        ("milestones", "id", mid), ("projects", "id", pid), ("users", "id", employee.id),
    ]:
        row = raw_db.execute(f"SELECT archived_at FROM {table} WHERE {key} = %s", (value,)).fetchone()  # noqa: S608
        assert row is not None and row["archived_at"] is not None, table

    # an admin can see all of it ...
    a = api.admin.headers
    assert api.client.get(f"/projects/{pid}/milestones?include_archived=true", headers=a).json()["total"] == 1
    assert api.client.get(f"/projects/{pid}/milestones/{mid}/deliverables?include_archived=true", headers=a).json()["items"]
    assert api.client.get(f"/projects/{pid}/milestones/{mid}/team?include_archived=true", headers=a).json()["items"]
    assert api.client.get(f"/projects/{pid}/costs?include_archived=true", headers=a).json()["items"]
    assert api.client.get("/projects?include_archived=true", headers=a).json()["total"] == 1
    assert api.client.get("/users?include_archived=true&q=employee", headers=a).json()["total"] >= 1


def test_only_admins_can_see_archived_records(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project, ms = api.setup_work(manager, employee)
    pid, mid = project["id"], ms["id"]
    item = api.deliverable(pid, mid, "Spec")
    cost = api.client.post(
        f"/projects/{pid}/costs", json={"category": "other", "description": "x", "amount": 10, "incurred_on": "2026-03-10"},
        headers=manager.headers,
    ).json()
    api.client.post(f"/projects/{pid}/milestones/{mid}/deliverables/{item['id']}/archive", headers=manager.headers)
    api.client.post(f"/projects/{pid}/costs/{cost['id']}/archive", headers=manager.headers)
    api.client.post(f"/projects/{pid}/milestones/{mid}/archive", headers=manager.headers)

    assert api.client.get(f"/projects/{pid}/milestones?include_archived=true", headers=manager.headers).json()["total"] == 0
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).status_code == 404
    # the employee's only milestone is archived, so the whole project is gone from their view
    assert api.client.get(f"/projects/{pid}/milestones?include_archived=true", headers=employee.headers).status_code == 404
    assert api.client.get(f"/projects/{pid}", headers=employee.headers).status_code == 404
    # the flag is silently ignored for managers (it never widens what they may see)
    costs = api.client.get(f"/projects/{pid}/costs?include_archived=true", headers=manager.headers).json()
    assert costs["items"] == [] and costs["total"] == 0
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=api.admin.headers).status_code == 200
