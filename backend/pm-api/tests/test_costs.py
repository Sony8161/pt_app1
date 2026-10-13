"""Non-labor costs and how they combine with labor (calendar-based) against the budget."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

COST = {"category": "license", "description": "IDE seats", "amount": 1200.5, "incurred_on": "2026-03-05"}


@pytest.fixture
def setup(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager, salary=50)
    project = api.project(manager, budget=10000)
    ms = api.milestone(project["id"], manager, budget=5000)
    api.assign(project["id"], ms["id"], employee, manager.headers, start_date="2026-03-09")  # 3 days worked so far
    return api, manager, employee, project["id"]


def test_totals_combine_labor_and_other_costs(setup):
    api, manager, _, pid = setup
    api.client.post(f"/projects/{pid}/costs", json=COST, headers=manager.headers)
    api.client.post(f"/projects/{pid}/costs", json={**COST, "category": "technology", "description": "Hosting", "amount": 299.5}, headers=manager.headers)

    costs = api.client.get(f"/projects/{pid}/costs", headers=manager.headers).json()
    assert costs["total"] == 2 and costs["other_cost"] == 1500
    assert costs["by_category"] == {"license": 1200.5, "technology": 299.5}
    assert costs["labor_cost"] == 1200 and costs["total_cost"] == 2700 and costs["budget_remaining"] == 7300  # 3 days x 8 h x $50

    summary = api.client.get(f"/projects/{pid}", headers=manager.headers).json()["summary"]
    assert summary["other_cost"] == 1500 and summary["total_cost"] == 2700 and summary["budget_pct"] == 27.0


def test_update_and_archive(setup):
    api, manager, _, pid = setup
    cid = api.client.post(f"/projects/{pid}/costs", json=COST, headers=manager.headers).json()["id"]
    fixed = api.client.patch(f"/projects/{pid}/costs/{cid}", json={"amount": 999}, headers=manager.headers)
    assert fixed.status_code == 200 and fixed.json()["amount"] == 999
    assert api.client.patch(f"/projects/{pid}/costs/{cid}", json={"amount": None}, headers=manager.headers).status_code == 400

    archived = api.client.post(f"/projects/{pid}/costs/{cid}/archive", headers=manager.headers)
    assert archived.status_code == 200 and archived.json()["archived_at"]
    listed = api.client.get(f"/projects/{pid}/costs", headers=manager.headers).json()
    assert listed["total"] == 0 and listed["other_cost"] == 0  # archived costs no longer count
    assert api.client.post(f"/projects/{pid}/costs/{cid}/archive", headers=manager.headers).status_code == 404
    assert api.client.patch(f"/projects/{pid}/costs/{cid}", json={"amount": 1}, headers=manager.headers).status_code == 404

    admin_view = api.client.get(f"/projects/{pid}/costs?include_archived=true", headers=api.admin.headers).json()
    assert len(admin_view["items"]) == 1 and admin_view["total"] == 0 and admin_view["other_cost"] == 0


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
