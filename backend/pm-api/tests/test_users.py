"""People management and its role rules."""

from __future__ import annotations

import pytest

from tests.conftest import GOOD_PASSWORD

pytestmark = pytest.mark.integration


def test_admin_creates_employee_with_generated_credentials(api):
    manager = api.user("manager")
    resp = api.client.post(
        "/users",
        json={"name": "Alex Kim", "email": "alex@test.example", "role": "employee", "manager_id": manager.id,
              "salary": 42.5, "job_title": "Developer"},
        headers=api.admin.headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["user"]["username"]) == 6 and body["user"]["username"].startswith("al")
    assert body["user"]["must_change_password"] is True and body["user"]["salary"] == 42.5
    assert len(body["temporary_password"]) >= 8
    assert "password_hash" not in body["user"] and body["temporary_password"] not in str(body["user"])
    assert body["user"]["created_at"].endswith("Z")  # timestamps are UTC


def test_employee_needs_a_manager_and_admin_does_not_report_to_one(api):
    manager = api.user("manager")
    no_manager = api.client.post("/users", json={"name": "A B", "email": "a@x.example", "role": "employee"}, headers=api.admin.headers)
    assert no_manager.status_code == 400 and no_manager.json()["error"]["details"][0]["field"] == "manager_id"
    admin_with_boss = api.client.post(
        "/users", json={"name": "A B", "email": "b@x.example", "role": "admin", "manager_id": manager.id}, headers=api.admin.headers
    )
    assert admin_with_boss.status_code == 400


def test_manager_id_must_be_an_active_manager(api):
    employee = api.user("employee", manager=api.user("manager"))
    resp = api.client.post(
        "/users", json={"name": "C D", "email": "c@x.example", "role": "employee", "manager_id": employee.id}, headers=api.admin.headers
    )
    assert resp.status_code == 400


def test_duplicate_email_is_a_conflict_ignoring_case(api):
    manager = api.user("manager")
    first = {"name": "Dup One", "email": "Dup@Test.example", "role": "manager"}
    assert api.client.post("/users", json=first, headers=api.admin.headers).status_code == 201
    again = api.client.post("/users", json={**first, "name": "Dup Two", "email": "dup@test.example"}, headers=api.admin.headers)
    assert again.status_code == 409 and again.json()["error"]["details"][0]["field"] == "email"
    assert manager.id


def test_only_admins_create_users(api):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    body = {"name": "E F", "email": "e@x.example", "role": "manager"}
    assert api.client.post("/users", json=body, headers=manager.headers).status_code == 403
    assert api.client.post("/users", json=body, headers=employee.headers).status_code == 403


def test_salary_is_visible_to_admin_and_self_only(api):
    manager = api.user("manager", salary=70)
    employee = api.user("employee", manager=manager, salary=45)

    as_admin = api.client.get(f"/users/{employee.id}", headers=api.admin.headers).json()
    as_self = api.client.get(f"/users/{employee.id}", headers=employee.headers).json()
    as_manager = api.client.get(f"/users/{employee.id}", headers=manager.headers).json()
    assert as_admin["salary"] == 45 and as_self["salary"] == 45 and as_manager["salary"] is None

    listed = api.client.get("/users", headers=manager.headers).json()["items"]
    others = [u for u in listed if u["id"] != manager.id]  # your own salary is visible to you
    assert others and all(u["salary"] is None for u in others)


def test_manager_sees_non_admins_only_and_employees_cannot_list(api):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    items = api.client.get("/users", headers=manager.headers).json()["items"]
    assert {u["role"] for u in items} <= {"manager", "employee"}
    assert api.admin.id not in {u["id"] for u in items}
    assert api.client.get(f"/users/{api.admin.id}", headers=manager.headers).status_code == 404
    assert api.client.get("/users", headers=employee.headers).status_code == 403
    assert api.client.get(f"/users/{manager.id}", headers=employee.headers).status_code == 404
    assert api.client.get(f"/users/{employee.id}", headers=employee.headers).status_code == 200


def test_search_and_filters(api):
    manager = api.user("manager", "Maria Lopez")
    api.user("employee", "Alex Kim", manager=manager)
    api.user("employee", "Priya Shah", manager=manager)
    h = api.admin.headers
    assert [u["name"] for u in api.client.get("/users?q=priya", headers=h).json()["items"]] == ["Priya Shah"]
    employees = api.client.get(f"/users?role=employee&manager_id={manager.id}", headers=h).json()
    assert employees["total"] == 2


def test_manager_edits_direct_reports_within_limits(api):
    mine = api.user("manager", "Mine")
    other = api.user("manager", "Other")
    report = api.user("employee", "Report", manager=mine)
    stranger = api.user("employee", "Stranger", manager=other)

    ok = api.client.patch(f"/users/{report.id}", json={"job_title": "Senior Tester", "name": "Report Renamed"}, headers=mine.headers)
    assert ok.status_code == 200 and ok.json()["job_title"] == "Senior Tester"
    assert api.client.patch(f"/users/{stranger.id}", json={"job_title": "x"}, headers=mine.headers).status_code == 403
    for forbidden in ({"salary": 99}, {"role": "manager"}, {"manager_id": other.id}):
        assert api.client.patch(f"/users/{report.id}", json=forbidden, headers=mine.headers).status_code == 403
    assert api.client.patch(f"/users/{report.id}", json={"job_title": "x"}, headers=report.headers).status_code == 403


def test_anyone_can_edit_their_own_name_and_email_only(api):
    employee = api.user("employee", manager=api.user("manager"))
    resp = api.client.patch("/users/me", json={"name": "New Name", "email": "new@test.example"}, headers=employee.headers)
    assert resp.status_code == 200 and resp.json()["name"] == "New Name"
    # salary / role are not part of the self-service schema and are ignored
    sneaky = api.client.patch("/users/me", json={"salary": 999, "role": "admin"}, headers=employee.headers)
    assert sneaky.status_code == 200 and sneaky.json()["role"] == "employee" and sneaky.json()["salary"] == 50
    assert api.client.patch("/users/me", json={"email": "not-an-email"}, headers=employee.headers).status_code == 400


def test_admin_moves_employee_to_another_manager(api):
    a, b = api.user("manager", "Boss A"), api.user("manager", "Boss B")
    employee = api.user("employee", manager=a)
    resp = api.client.patch(f"/users/{employee.id}", json={"manager_id": b.id}, headers=api.admin.headers)
    assert resp.status_code == 200 and resp.json()["manager_id"] == b.id
    assert api.client.patch(f"/users/{employee.id}", json={"manager_id": None}, headers=api.admin.headers).status_code == 400


def test_role_changes_are_guarded(api):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    h = api.admin.headers
    assert api.client.patch(f"/users/{api.admin.id}", json={"role": "manager"}, headers=h).status_code == 400  # self
    # a manager with direct reports cannot become something else
    assert api.client.patch(f"/users/{manager.id}", json={"role": "employee", "manager_id": manager.id}, headers=h).status_code in {400, 409}
    # promote employee to manager: manager link may stay (a manager can report to a manager)
    promoted = api.client.patch(f"/users/{employee.id}", json={"role": "manager"}, headers=h)
    assert promoted.status_code == 200 and promoted.json()["role"] == "manager"


def test_reporting_loops_are_rejected(api):
    a = api.user("manager", "Loop A")
    b = api.user("manager", "Loop B", manager=a)
    resp = api.client.patch(f"/users/{a.id}", json={"manager_id": b.id}, headers=api.admin.headers)
    assert resp.status_code == 400 and "loop" in resp.json()["error"]["message"]


def test_cannot_archive_self_or_last_admin(api):
    resp = api.client.post(f"/users/{api.admin.id}/archive", headers=api.admin.headers)
    assert resp.status_code == 400
    second = api.user("manager")
    api.client.patch(f"/users/{second.id}", json={"role": "admin", "manager_id": None}, headers=api.admin.headers)
    assert api.client.post(f"/users/{second.id}/archive", headers=api.admin.headers).status_code == 200


def test_cannot_archive_manager_with_projects_or_reports(api):
    manager = api.user("manager")
    report = api.user("employee", manager=manager)
    blocked = api.client.post(f"/users/{manager.id}/archive", headers=api.admin.headers)
    assert blocked.status_code == 409 and "direct report" in blocked.json()["error"]["message"]
    api.client.post(f"/users/{report.id}/archive", headers=api.admin.headers)
    api.project(manager)
    blocked = api.client.post(f"/users/{manager.id}/archive", headers=api.admin.headers)
    assert blocked.status_code == 409 and "project" in blocked.json()["error"]["message"]


def test_archive_and_unarchive_employee_keeps_history(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager)
    project, ms = api.setup_work(manager, employee)

    archived = api.client.post(f"/users/{employee.id}/archive", headers=api.admin.headers).json()
    assert archived["archived_at"] is not None
    # their work ends today and the days they worked stay on record
    team = api.client.get(f"/projects/{project['id']}/milestones/{ms['id']}/team", headers=api.admin.headers).json()
    assert team["total"] == 1 and team["items"][0]["end_date"] == "2026-03-11" and team["items"][0]["hours_worked"] == 8
    assert employee.id not in {u["id"] for u in api.client.get("/users", headers=api.admin.headers).json()["items"]}
    listed = api.client.get("/users?include_archived=true", headers=api.admin.headers).json()["items"]
    assert employee.id in {u["id"] for u in listed}

    restored = api.client.post(f"/users/{employee.id}/unarchive", headers=api.admin.headers).json()
    assert restored["archived_at"] is None


def test_admin_resets_password(api):
    employee = api.user("employee", manager=api.user("manager"))
    reset = api.client.post(f"/users/{employee.id}/reset-password", headers=api.admin.headers)
    assert reset.status_code == 200
    temp = reset.json()["temporary_password"]
    assert api.client.get("/auth/me", headers=employee.headers).status_code == 401  # old token revoked
    login = api.client.post("/auth/login", json={"username": employee.username, "password": temp})
    assert login.status_code == 200 and login.json()["user"]["must_change_password"] is True
    assert api.client.post("/auth/login", json={"username": employee.username, "password": GOOD_PASSWORD}).status_code == 401
    boss = api.user("manager")
    assert api.client.post(f"/users/{employee.id}/reset-password", headers=boss.headers).status_code == 403


def test_unknown_user_is_404(api, new_id):
    assert api.client.get(f"/users/{new_id()}", headers=api.admin.headers).status_code == 404
    assert api.client.get("/users/not-a-uuid", headers=api.admin.headers).status_code == 400
