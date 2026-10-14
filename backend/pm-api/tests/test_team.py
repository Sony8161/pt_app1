"""Teams: people work on milestones, several per milestone, but one milestone per person per day."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def plan(api, today):
    """Two managers, two projects, each with one milestone covering today."""
    m1, m2 = api.user("manager", "Maria"), api.user("manager", "James")
    p1, p2 = api.project(m1, name="Apollo"), api.project(m2, name="Borealis")
    ms1 = api.milestone(p1["id"], m1, name="Build")
    ms2 = api.milestone(p2["id"], m2, name="Migrate")
    return api, (m1, p1, ms1), (m2, p2, ms2)


def url(project, milestone, *tail):
    return "/".join([f"/projects/{project['id']}/milestones/{milestone['id']}/team", *tail])


def test_assignment_defaults_to_today_for_a_running_milestone(plan):
    api, (m1, p1, ms1), _ = plan
    employee = api.user("employee", "Alex Kim", manager=m1, salary=40)
    resp = api.client.post(url(p1, ms1), json={"user_id": employee.id}, headers=m1.headers)
    assert resp.status_code == 201
    member = resp.json()
    assert member["name"] == "Alex Kim" and member["milestone_name"] == "Build" and member["daily_hours"] == 8
    assert member["start_date"] == "2026-03-11" and member["end_date"] == "2026-03-27"
    assert member["days_worked"] == 1 and member["hours_worked"] == 8 and member["labor_cost"] == 320


def test_a_future_milestone_defaults_to_its_own_dates(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project = api.project(manager)
    ms = api.milestone(project["id"], manager, start="2026-04-01", due="2026-04-10")
    member = api.assign(project["id"], ms["id"], employee, manager.headers).json()
    assert member["start_date"] == "2026-04-01" and member["end_date"] == "2026-04-10" and member["hours_worked"] == 0


def test_several_people_can_work_one_milestone(plan):
    api, (m1, p1, ms1), _ = plan
    for i in range(4):
        person = api.user("employee", f"Person {i}", manager=m1)
        assert api.client.post(url(p1, ms1), json={"user_id": person.id}, headers=m1.headers).status_code == 201
    team = api.client.get(url(p1, ms1), headers=m1.headers).json()
    assert team["total"] == 4 and team["hours_worked"] == 32 and team["labor_cost"] == 4 * 8 * 50


def test_one_milestone_per_person_per_day(plan):
    api, (m1, p1, ms1), (m2, p2, ms2) = plan
    busy = api.user("employee", "Busy Bee", manager=m1)
    assert api.client.post(url(p1, ms1), json={"user_id": busy.id}, headers=m1.headers).status_code == 201

    clash = api.client.post(url(p2, ms2), json={"user_id": busy.id}, headers=m2.headers)
    assert clash.status_code == 409
    error = clash.json()["error"]
    assert error["code"] == "assignment_overlap"
    assert "Busy Bee" in error["message"] and "'Build'" in error["message"] and "'Apollo'" in error["message"]

    # a different employee is fine, and so is the same person on dates after the first milestone
    assert api.client.post(url(p2, ms2), json={"user_id": api.user("employee", "Other", manager=m2).id}, headers=m2.headers).status_code == 201
    ms3 = api.milestone(p2["id"], m2, name="Later", start="2026-03-30", due="2026-04-10", hours=10, budget=100)
    assert api.client.post(url(p2, ms3), json={"user_id": busy.id}, headers=m2.headers).status_code == 201


def test_overlap_is_checked_per_day_across_edges(plan):
    api, (m1, p1, ms1), (m2, p2, ms2) = plan
    person = api.user("employee", manager=m1)
    api.assign(p1["id"], ms1["id"], person, m1.headers, start_date="2026-03-11", end_date="2026-03-15")
    assert api.assign(p2["id"], ms2["id"], person, m2.headers, start_date="2026-03-15", end_date="2026-03-20").status_code == 409  # shares the 15th
    assert api.assign(p2["id"], ms2["id"], person, m2.headers, start_date="2026-03-16", end_date="2026-03-20").status_code == 201  # next day


def test_only_active_employees_can_be_assigned(plan):
    api, (m1, p1, ms1), _ = plan
    assert api.client.post(url(p1, ms1), json={"user_id": api.user("manager", "Boss").id}, headers=m1.headers).status_code == 400
    archived = api.user("employee", manager=m1)
    api.client.post(f"/users/{archived.id}/archive", headers=api.admin.headers)
    assert api.client.post(url(p1, ms1), json={"user_id": archived.id}, headers=m1.headers).status_code == 400
    ghost = api.client.post(url(p1, ms1), json={"user_id": "00000000-0000-0000-0000-000000000000"}, headers=m1.headers)
    assert ghost.status_code == 400


def test_dates_must_be_inside_the_milestone_and_in_order(plan):
    api, (m1, p1, ms1), _ = plan
    person = api.user("employee", manager=m1)
    for bad in ({"start_date": "2026-03-02"}, {"end_date": "2026-04-30"}, {"start_date": "2026-03-20", "end_date": "2026-03-12"}):
        assert api.client.post(url(p1, ms1), json={"user_id": person.id, **bad}, headers=m1.headers).status_code == 400


def test_adding_twice_is_a_conflict(plan):
    api, (m1, p1, ms1), _ = plan
    person = api.user("employee", manager=m1)
    assert api.assign(p1["id"], ms1["id"], person, m1.headers).status_code == 201
    assert api.assign(p1["id"], ms1["id"], person, m1.headers).status_code == 409


def test_changing_dates_checks_the_overlap_again(plan):
    api, (m1, p1, ms1), (m2, p2, ms2) = plan
    person = api.user("employee", manager=m1)
    api.assign(p1["id"], ms1["id"], person, m1.headers, start_date="2026-03-11", end_date="2026-03-13")
    api.assign(p2["id"], ms2["id"], person, m2.headers, start_date="2026-03-16", end_date="2026-03-20")
    grow = api.client.patch(url(p1, ms1, person.id), json={"end_date": "2026-03-17"}, headers=m1.headers)
    assert grow.status_code == 409
    ok = api.client.patch(url(p1, ms1, person.id), json={"end_date": "2026-03-15"}, headers=m1.headers)
    assert ok.status_code == 200 and ok.json()["end_date"] == "2026-03-15"
    assert api.client.patch(url(p1, ms1, person.id), json={"end_date": None}, headers=m1.headers).status_code == 400
    assert api.client.patch(url(p1, ms1, api.user("employee", manager=m1).id), json={"end_date": "2026-03-15"}, headers=m1.headers).status_code == 404


def test_removing_someone_who_started_ends_their_work_today(plan):
    api, (m1, p1, ms1), (m2, p2, ms2) = plan
    person = api.user("employee", manager=m1, salary=40)
    api.assign(p1["id"], ms1["id"], person, m1.headers, start_date="2026-03-09")  # worked Mon, Tue, Wed so far
    gone = api.client.post(url(p1, ms1, person.id, "archive"), headers=m1.headers)
    assert gone.status_code == 200 and gone.json()["end_date"] == "2026-03-11" and gone.json()["hours_worked"] == 24
    assert gone.json()["archived_at"] is None  # the days they worked stay on record and keep counting
    # freed from tomorrow
    assert api.assign(p2["id"], ms2["id"], person, m2.headers, start_date="2026-03-11").status_code == 409
    assert api.assign(p2["id"], ms2["id"], person, m2.headers, start_date="2026-03-12").status_code == 201
    assert api.client.post(url(p1, ms1, api.user("employee", manager=m1).id, "archive"), headers=m1.headers).status_code == 404


def test_removing_someone_who_never_started_archives_the_row(plan):
    api, (m1, p1, ms1), _ = plan
    person = api.user("employee", manager=m1)
    api.assign(p1["id"], ms1["id"], person, m1.headers, start_date="2026-03-20")
    gone = api.client.post(url(p1, ms1, person.id, "archive"), headers=m1.headers)
    assert gone.status_code == 200 and gone.json()["archived_at"]
    assert api.client.get(url(p1, ms1), headers=m1.headers).json()["total"] == 0
    assert api.client.get(url(p1, ms1) + "?include_archived=true", headers=api.admin.headers).json()["total"] == 1
    assert api.client.get(url(p1, ms1) + "?include_archived=true", headers=m1.headers).json()["total"] == 0  # flag ignored for managers


def test_project_team_lists_everyone_across_milestones(plan):
    api, (m1, p1, ms1), _ = plan
    ms_b = api.milestone(p1["id"], m1, name="Test", start="2026-03-30", due="2026-04-10", hours=20, budget=500)
    a, b = api.user("employee", "Anna", manager=m1), api.user("employee", "Ben", manager=m1)
    api.assign(p1["id"], ms1["id"], a, m1.headers)
    api.assign(p1["id"], ms_b["id"], b, m1.headers)
    team = api.client.get(f"/projects/{p1['id']}/team", headers=m1.headers).json()
    assert {(i["name"], i["milestone_name"]) for i in team["items"]} == {("Anna", "Build"), ("Ben", "Test")}
    assert api.client.get(f"/projects/{p1['id']}", headers=m1.headers).json()["summary"]["team_size"] == 2


def test_roles_and_money_visibility(plan):
    api, (m1, p1, ms1), (m2, _, _) = plan
    employee = api.user("employee", manager=m1, salary=40)
    mate = api.user("employee", "Mate", manager=m1)
    outsider = api.user("employee", "Outsider", manager=m2)
    api.assign(p1["id"], ms1["id"], employee, m1.headers)

    assert api.assign(p1["id"], ms1["id"], mate, m2.headers).status_code == 404  # another manager cannot see it
    assert api.assign(p1["id"], ms1["id"], mate, employee.headers).status_code == 403
    assert api.assign(p1["id"], ms1["id"], mate, api.admin.headers).status_code == 201

    mine = api.client.get(url(p1, ms1), headers=employee.headers).json()
    assert mine["total"] == 2 and mine["labor_cost"] is None and all(i["labor_cost"] is None for i in mine["items"])
    assert api.client.get(url(p1, ms1), headers=outsider.headers).status_code == 404
    assert api.client.get(url(p1, ms1), headers=m1.headers).json()["labor_cost"] == 2 * 8 * 40 - 8 * 40 + 8 * 50


def test_completing_the_project_ends_everyones_work_today(plan):
    api, (m1, p1, ms1), (m2, p2, ms2) = plan
    person = api.user("employee", manager=m1)
    api.assign(p1["id"], ms1["id"], person, m1.headers)
    api.client.post(f"/projects/{p1['id']}/complete", headers=m1.headers)
    member = api.client.get(f"/projects/{p1['id']}/team", headers=api.admin.headers).json()["items"][0]
    assert member["end_date"] == "2026-03-11"
    assert api.assign(p2["id"], ms2["id"], person, m2.headers, start_date="2026-03-12").status_code == 201


def test_someone_who_was_removed_stops_seeing_the_project_once_their_work_has_ended(plan, monkeypatch):
    import datetime as dt

    from app.core import dates

    api, (m1, p1, ms1), _ = plan
    person = api.user("employee", manager=m1)
    api.assign(p1["id"], ms1["id"], person, m1.headers, start_date="2026-03-09")
    project_url = f"/projects/{p1['id']}"
    assert api.client.get(project_url, headers=person.headers).status_code == 200

    api.client.post(url(p1, ms1, person.id, "archive"), headers=m1.headers)  # their work ends today (Wed 11 March)
    assert api.client.get(project_url, headers=person.headers).status_code == 200  # still on it today

    monkeypatch.setattr(dates, "today", lambda: dt.date(2026, 3, 12))  # tomorrow
    assert api.client.get(project_url, headers=person.headers).status_code == 404
    assert api.client.get("/projects", headers=person.headers).json()["total"] == 0
    assert api.client.get(f"{project_url}/milestones", headers=person.headers).status_code == 404
    assert api.client.get(f"{project_url}/team", headers=person.headers).status_code == 404
    assert api.client.get(project_url, headers=m1.headers).status_code == 200  # the manager still does
