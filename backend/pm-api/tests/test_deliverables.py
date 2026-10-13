"""Deliverables: the checklist a manager ticks off before completing a milestone."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def setup(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project, ms = api.setup_work(manager, employee)
    return api, manager, employee, project["id"], ms["id"]


def test_checklist_lifecycle(setup):
    api, manager, _, pid, mid = setup
    base = f"/projects/{pid}/milestones/{mid}/deliverables"
    empty = api.client.get(base, headers=manager.headers).json()
    assert empty["total"] == 0 and empty["ready_to_complete"] is False

    a = api.client.post(base, json={"name": "Design file", "description": "Figma export"}, headers=manager.headers)
    assert a.status_code == 201 and a.json()["done"] is False and a.json()["done_at"] is None
    b = api.client.post(base, json={"name": "Test report"}, headers=manager.headers).json()

    ticked = api.client.patch(f"{base}/{a.json()['id']}", json={"done": True}, headers=manager.headers).json()
    assert ticked["done"] is True and ticked["done_at"] and ticked["done_by"] == manager.id
    state = api.client.get(base, headers=manager.headers).json()
    assert state["total"] == 2 and state["done"] == 1 and state["ready_to_complete"] is False

    api.client.patch(f"{base}/{b['id']}", json={"done": True}, headers=manager.headers)
    assert api.client.get(base, headers=manager.headers).json()["ready_to_complete"] is True
    unticked = api.client.patch(f"{base}/{b['id']}", json={"done": False}, headers=manager.headers).json()
    assert unticked["done"] is False and unticked["done_at"] is None and unticked["done_by"] is None
    assert api.client.get(f"/projects/{pid}/milestones/{mid}", headers=manager.headers).json()["deliverables_done"] == 1


def test_rename_validation_and_duplicates(setup):
    api, manager, _, pid, mid = setup
    base = f"/projects/{pid}/milestones/{mid}/deliverables"
    first = api.client.post(base, json={"name": "Spec"}, headers=manager.headers).json()
    assert api.client.post(base, json={"name": "spec"}, headers=manager.headers).status_code == 409
    assert api.client.post(base, json={"name": "  "}, headers=manager.headers).status_code == 400
    assert api.client.patch(f"{base}/{first['id']}", json={"name": "Spec v2"}, headers=manager.headers).json()["name"] == "Spec v2"
    assert api.client.patch(f"{base}/{first['id']}", json={"name": None}, headers=manager.headers).status_code == 400


def test_employees_can_read_but_not_review(setup):
    api, manager, employee, pid, mid = setup
    base = f"/projects/{pid}/milestones/{mid}/deliverables"
    item = api.deliverable(pid, mid, "Spec", manager=manager)
    assert api.client.get(base, headers=employee.headers).json()["total"] == 1
    assert api.client.post(base, json={"name": "Sneaky"}, headers=employee.headers).status_code == 403
    assert api.client.patch(f"{base}/{item['id']}", json={"done": True}, headers=employee.headers).status_code == 403
    other = api.user("manager", "Other")
    assert api.client.get(base, headers=other.headers).status_code == 404
    assert api.client.patch(f"{base}/{item['id']}", json={"done": True}, headers=other.headers).status_code == 404


def test_archiving_a_deliverable_removes_it_from_the_checklist(setup):
    api, manager, _, pid, mid = setup
    base = f"/projects/{pid}/milestones/{mid}/deliverables"
    keep = api.deliverable(pid, mid, "Keep", done=True, manager=manager)
    drop = api.deliverable(pid, mid, "Drop", manager=manager)
    archived = api.client.post(f"{base}/{drop['id']}/archive", headers=manager.headers)
    assert archived.status_code == 200 and archived.json()["archived_at"]

    state = api.client.get(base, headers=manager.headers).json()
    assert [i["id"] for i in state["items"]] == [keep["id"]] and state["ready_to_complete"] is True  # the archived one no longer blocks
    admin_view = api.client.get(f"{base}?include_archived=true", headers=api.admin.headers).json()
    assert {i["id"] for i in admin_view["items"]} == {keep["id"], drop["id"]} and admin_view["total"] == 1
    assert api.client.patch(f"{base}/{drop['id']}", json={"done": True}, headers=manager.headers).status_code == 404
    assert api.client.patch(f"{base}/{drop['id']}", json={"done": True}, headers=api.admin.headers).status_code == 409
    assert api.client.post(f"/projects/{pid}/milestones/{mid}/complete", json={}, headers=manager.headers).status_code == 200


def test_no_changes_after_the_milestone_is_archived(setup):
    api, manager, _, pid, mid = setup
    api.deliverable(pid, mid, "Spec", done=True, manager=manager)
    api.client.post(f"/projects/{pid}/milestones/{mid}/complete", json={}, headers=manager.headers)
    base = f"/projects/{pid}/milestones/{mid}/deliverables"
    assert api.client.post(base, json={"name": "Late"}, headers=manager.headers).status_code == 404
    assert api.client.post(base, json={"name": "Late"}, headers=api.admin.headers).status_code == 409
    assert api.client.get(base, headers=manager.headers).status_code == 404
    assert api.client.get(base, headers=api.admin.headers).json()["total"] == 1
