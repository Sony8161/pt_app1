"""Non-labor costs and how they combine with labor against the budget."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

COST = {"category": "license", "description": "IDE seats", "amount": 1200.5, "incurred_on": "2026-03-05"}


@pytest.fixture
def setup(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager, salary=50)
    project = api.project(manager, budget=10000)
    api.assign(project["id"], employee, start_date="2026-03-02")
    return api, manager, employee, project["id"]


def test_totals_combine_labor_and_other_costs(setup):
    api, manager, employee, pid = setup
    api.client.post(f"/projects/{pid}/time-entries", json={"work_date": "2026-03-10", "hours": 8}, headers=employee.headers)  # 400
    api.client.post(f"/projects/{pid}/costs", json=COST, headers=manager.headers)
    api.client.post(f"/projects/{pid}/costs", json={**COST, "category": "technology", "description": "Hosting", "amount": 99.5}, headers=manager.headers)

    costs = api.client.get(f"/projects/{pid}/costs", headers=manager.headers).json()
    assert costs["total"] == 2 and costs["other_cost"] == 1300
    assert costs["by_category"] == {"license": 1200.5, "technology": 99.5}
    assert costs["labor_cost"] == 400 and costs["total_cost"] == 1700 and costs["budget_remaining"] == 8300

    summary = api.client.get(f"/projects/{pid}", headers=manager.headers).json()["summary"]
    assert summary["other_cost"] == 1300 and summary["total_cost"] == 1700 and summary["budget_pct"] == 17.0


def test_update_and_remove(setup):
    api, manager, _, pid = setup
    cid = api.client.post(f"/projects/{pid}/costs", json=COST, headers=manager.headers).json()["id"]
    fixed = api.client.patch(f"/projects/{pid}/costs/{cid}", json={"amount": 999}, headers=manager.headers)
    assert fixed.status_code == 200 and fixed.json()["amount"] == 999
    assert api.client.patch(f"/projects/{pid}/costs/{cid}", json={"amount": None}, headers=manager.headers).status_code == 400
    assert api.client.delete(f"/projects/{pid}/costs/{cid}", headers=manager.headers).status_code == 204
    assert api.client.get(f"/projects/{pid}/costs", headers=manager.headers).json()["total"] == 0
    assert api.client.delete(f"/projects/{pid}/costs/{cid}", headers=manager.headers).status_code == 404


def test_validation(setup):
    api, manager, _, pid = setup
    for bad in ({"amount": -5}, {"category": "snacks"}, {"description": ""}, {"incurred_on": "yesterday"}):
        assert api.client.post(f"/projects/{pid}/costs", json={**COST, **bad}, headers=manager.headers).status_code == 400


def test_employees_cannot_see_or_change_costs(setup):
    api, manager, employee, pid = setup
    assert api.client.get(f"/projects/{pid}/costs", headers=employee.headers).status_code == 403
    assert api.client.post(f"/projects/{pid}/costs", json=COST, headers=employee.headers).status_code == 403
    other = api.user("manager", "Other")
    assert api.client.get(f"/projects/{pid}/costs", headers=other.headers).status_code == 404
    assert api.client.post(f"/projects/{pid}/costs", json=COST, headers=api.admin.headers).status_code == 201


def test_costs_still_allowed_after_completion_but_not_after_archive(setup):
    api, manager, _, pid = setup
    api.client.post(f"/projects/{pid}/complete", headers=manager.headers)
    assert api.client.post(f"/projects/{pid}/costs", json=COST, headers=manager.headers).status_code == 201
    api.client.post(f"/projects/{pid}/archive", headers=api.admin.headers)
    assert api.client.post(f"/projects/{pid}/costs", json=COST, headers=api.admin.headers).status_code == 409
