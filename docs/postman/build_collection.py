#!/usr/bin/env python3
"""Build the Postman collection, environments and README for the ACME Project Tracker API.

One declarative spec below describes every request: method, path, body, who calls it, the
expected status and the assertions. The same spec is used twice:

1. It is turned into Postman test scripts (pm.test ...) so the collection verifies itself.
2. It is executed against a running API (a mini collection runner) so the *expected JSON
   responses* saved in the collection are real captured output, not hand-written guesses.

Usage (run against an EMPTY database, the flow creates its own users and projects):

    cd backend/pm-api && source .venv/bin/activate
    uvicorn app.main:app --port 8001            # with a fresh POSTGRES_NAME
    python ../../docs/postman/build_collection.py --base-url http://127.0.0.1:8001

Use ``--no-run`` to generate the files without calling the API (examples are then omitted).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).parent
COLLECTION_NAME = "ACME Project Tracker API"

# ---------------------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------------------
INITIAL_ADMIN = "admin1"
INITIAL_PASSWORD = "ChangeMe123!"  # nosec - documented local bootstrap default
NEW_PASSWORD = "Passw0rd-xyz"  # nosec - test password used by the flow

DATE_OFFSETS = {  # collection variables recomputed before every request
    "today": 0, "yesterday": -1, "tomorrow": 1, "future_date": 5,
    "before_project": -30, "project_start": -10, "project_end": 60, "after_project": 90,
    "milestone1_due": 14, "milestone2_start": 15, "milestone2_due": 40,
}

PRE_REQUEST_JS = """\
// Dates are relative to today so the flow works on any day. run_id keeps names/emails unique per run.
const day = (n) => { const d = new Date(); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const offsets = %s;
Object.keys(offsets).forEach((k) => pm.collectionVariables.set(k, day(offsets[k])));
if (!pm.collectionVariables.get('run_id')) {
  pm.collectionVariables.set('run_id', Math.random().toString(36).slice(2, 8));
}
""" % json.dumps(DATE_OFFSETS)

# ---------------------------------------------------------------------------------------
# Spec model
# ---------------------------------------------------------------------------------------


@dataclass
class Req:
    name: str
    method: str
    path: str
    auth: str | None = "admin_token"  # name of the variable holding the bearer token, None = no auth
    body: dict[str, Any] | None = None
    query: dict[str, str] = field(default_factory=dict)
    status: int = 200
    check: list[tuple] = field(default_factory=list)  # (json_path, op, value)
    save: list[tuple[str, str]] = field(default_factory=list)  # (variable, json_path)
    desc: str = ""


@dataclass
class Folder:
    name: str
    desc: str
    items: list[Req]


def R(*a: Any, **k: Any) -> Req:
    return Req(*a, **k)


ERR = lambda code: ("error.code", "eq", code)  # noqa: E731
VALID_ENVELOPE = [("error.message", "type", "string"), ("error.details", "type", "array")]


def login_and_change(who: str, user_var: str, label: str) -> list[Req]:
    """Sign a freshly created user in with the one-time password and set a real one."""
    return [
        R(f"Sign in as {label} (one-time password)", "POST", "/auth/login", auth=None,
          body={"username": "{{%s_username}}" % user_var, "password": "{{%s_temp_password}}" % user_var},
          check=[("user.must_change_password", "eq", True), ("user.role", "eq", who),
                 ("access_token", "type", "string"), ("token_type", "eq", "bearer")],
          save=[(f"{user_var}_token_temp", "access_token")],
          desc=f"First login with the generated one-time password. The account is flagged `must_change_password`."),
        R(f"{label.title()} sets a new password", "POST", "/auth/change-password", auth=f"{user_var}_token_temp",
          body={"current_password": "{{%s_temp_password}}" % user_var, "new_password": "{{new_password}}"},
          check=[("user.must_change_password", "eq", False)],
          save=[(f"{user_var}_token", "access_token")],
          desc="Returns a NEW token: the one-time token stops working as soon as the password changes."),
    ]


def create_user(label: str, var: str, body: dict[str, Any], **extra: Any) -> Req:
    role = body["role"]
    checks = [("user.role", "eq", role), ("user.username", "matches", "^[a-z0-9]{6}$"),
              ("user.must_change_password", "eq", True), ("temporary_password", "type", "string"),
              ("user.created_at", "matches", "Z$")]
    return R(label, "POST", "/users", body=body, status=201, check=checks + extra.pop("check", []),
             save=[(f"{var}_id", "user.id"), (f"{var}_username", "user.username"),
                   (f"{var}_temp_password", "temporary_password")],
             desc="Admin only. The 6-character username and a one-time password are generated; the password is shown once.",
             **extra)


SPEC: list[Folder] = [
    Folder("00 Health", "No sign-in needed.", [
        R("Health check", "GET", "/health", auth=None,
          check=[("status", "eq", "ok"), ("database", "eq", "ok"), ("service", "eq", "pm-api")],
          desc="Liveness plus a database check. Returns 503 with `database: error` when the database is unreachable."),
    ]),

    Folder("01 Auth", "First login of the bootstrap admin, password rules and token revocation.", [
        R("Sign in as admin (first login)", "POST", "/auth/login", auth=None,
          body={"username": "{{initial_admin_username}}", "password": "{{initial_admin_password}}"},
          check=[("user.role", "eq", "admin"), ("user.must_change_password", "eq", True),
                 ("expires_at", "type", "number")],
          save=[("admin_token_initial", "access_token"), ("admin_id", "user.id")],
          desc="Run these against an EMPTY database: the first admin is created automatically on the first request."),
        R("Wrong password is rejected", "POST", "/auth/login", auth=None, status=401,
          body={"username": "{{initial_admin_username}}", "password": "definitely-wrong"},
          check=[ERR("invalid_credentials")] + VALID_ENVELOPE,
          desc="Unknown usernames return the identical response, so accounts cannot be probed."),
        R("Validation errors use the same envelope", "POST", "/auth/login", auth=None, status=400,
          body={"username": ""},
          check=[ERR("validation_error"), ("error.details.0.field", "type", "string")],
          desc="Field-level problems come back in `error.details`."),
        R("Blocked until the password is changed", "GET", "/projects", auth="admin_token_initial", status=403,
          check=[ERR("password_change_required")],
          desc="A user with a one-time password can only call /auth/me, /auth/refresh and /auth/change-password."),
        R("Who am I (still allowed)", "GET", "/auth/me", auth="admin_token_initial",
          check=[("username", "eq", "{{initial_admin_username}}"), ("role", "eq", "admin")]),
        R("Weak password is rejected", "POST", "/auth/change-password", auth="admin_token_initial", status=400,
          body={"current_password": "{{initial_admin_password}}", "new_password": "weak"},
          check=[ERR("validation_error"), ("error.details.0.field", "eq", "new_password")],
          desc="Policy: 8+ characters with upper case, lower case and a digit."),
        R("Change the admin password", "POST", "/auth/change-password", auth="admin_token_initial",
          body={"current_password": "{{initial_admin_password}}", "new_password": "{{new_password}}"},
          check=[("user.must_change_password", "eq", False), ("access_token", "type", "string")],
          save=[("admin_token", "access_token")],
          desc="Returns a new token and revokes every older one."),
        R("The old token is revoked", "GET", "/auth/me", auth="admin_token_initial", status=401,
          check=[ERR("token_revoked")]),
        R("Refresh the token", "POST", "/auth/refresh", auth="admin_token",
          check=[("access_token", "type", "string"), ("user.role", "eq", "admin")],
          save=[("admin_token", "access_token")]),
        R("No token is rejected", "GET", "/projects", auth=None, status=401,
          check=[ERR("unauthenticated")] + VALID_ENVELOPE),
    ]),

    Folder("02 Users", "Admin creates accounts; managers see non-admins; salary is only visible to admins and the person.", [
        create_user("Create manager: Maria Lopez", "manager", {
            "name": "Maria Lopez", "email": "maria.{{run_id}}@acme.example", "job_title": "Engineering Manager",
            "role": "manager", "salary": 70}),
        create_user("Create second manager: James Carter", "manager2", {
            "name": "James Carter", "email": "james.{{run_id}}@acme.example", "job_title": "Delivery Manager",
            "role": "manager", "salary": 75}),
        create_user("Create employee: Alex Kim", "employee", {
            "name": "Alex Kim", "email": "alex.{{run_id}}@acme.example", "job_title": "Developer", "role": "employee",
            "manager_id": "{{manager_id}}", "salary": 45},
            check=[("user.manager_id", "eq", "{{manager_id}}"), ("user.salary", "eq", 45)]),
        create_user("Create employee: Priya Shah", "employee2", {
            "name": "Priya Shah", "email": "priya.{{run_id}}@acme.example", "job_title": "Designer", "role": "employee",
            "manager_id": "{{manager_id}}", "salary": 40}),
        R("Employee needs a manager", "POST", "/users", status=400,
          body={"name": "No Boss", "email": "noboss.{{run_id}}@acme.example", "role": "employee"},
          check=[ERR("validation_error"), ("error.details.0.field", "eq", "manager_id")]),
        R("Duplicate email is a conflict", "POST", "/users", status=409,
          body={"name": "Copycat", "email": "ALEX.{{run_id}}@acme.example", "role": "manager"},
          check=[ERR("conflict"), ("error.details.0.field", "eq", "email")],
          desc="Emails are unique ignoring case."),
        *login_and_change("manager", "manager", "Maria"),
        *login_and_change("manager", "manager2", "James"),
        *login_and_change("employee", "employee", "Alex"),
        *login_and_change("employee", "employee2", "Priya"),
        R("Managers cannot create users", "POST", "/users", auth="manager_token", status=403,
          body={"name": "Nope", "email": "nope.{{run_id}}@acme.example", "role": "employee", "manager_id": "{{manager_id}}"},
          check=[ERR("forbidden")]),
        R("List people (admin)", "GET", "/users", check=[("items", "type", "array"), ("total", "gte", 5)],
          desc="Admins see everyone, with salaries."),
        R("List people (manager)", "GET", "/users", auth="manager_token",
          check=[("items", "type", "array"), ("total", "gte", 4)],
          desc="Managers never see admins or archived accounts, and never see other people's salary."),
        R("Employees cannot list people", "GET", "/users", auth="employee_token", status=403, check=[ERR("forbidden")]),
        R("Search people", "GET", "/users", query={"q": "alex"}, check=[("total", "eq", 1), ("items.0.name", "eq", "Alex Kim")],
          desc="Matches name, email, username and job title."),
        R("Filter people by role and manager", "GET", "/users", query={"role": "employee", "manager_id": "{{manager_id}}"},
          check=[("total", "eq", 2)]),
        R("Get a person (admin sees salary)", "GET", "/users/{{employee_id}}",
          check=[("name", "eq", "Alex Kim"), ("salary", "eq", 45)]),
        R("Get a person (manager does not see salary)", "GET", "/users/{{employee_id}}", auth="manager_token",
          check=[("name", "eq", "Alex Kim"), ("salary", "null", None)]),
        R("Admin edits any field", "PATCH", "/users/{{employee_id}}", body={"job_title": "Senior Developer", "salary": 50},
          check=[("job_title", "eq", "Senior Developer"), ("salary", "eq", 50)],
          desc="Only admins can change role, manager or salary."),
        R("Manager edits a direct report", "PATCH", "/users/{{employee_id}}", auth="manager_token",
          body={"job_title": "Frontend Developer"}, check=[("job_title", "eq", "Frontend Developer")],
          desc="Managers can change name, email and job title of people who report to them."),
        R("Manager cannot change salary", "PATCH", "/users/{{employee_id}}", auth="manager_token", status=403,
          body={"salary": 999}, check=[ERR("forbidden")]),
        R("Manager cannot edit someone else's report", "PATCH", "/users/{{employee_id}}", auth="manager2_token", status=403,
          body={"job_title": "Hacker"}, check=[ERR("forbidden")]),
        R("Edit my own profile", "PATCH", "/users/me", auth="employee_token",
          body={"name": "Alex Kim", "email": "alex.{{run_id}}@acme.example"},
          check=[("name", "eq", "Alex Kim"), ("role", "eq", "employee")],
          desc="Everyone can change their own name and email, nothing else."),
        R("Invalid email is rejected", "PATCH", "/users/me", auth="employee_token", status=400,
          body={"email": "not-an-email"}, check=[ERR("validation_error")]),
        R("Unknown person", "GET", "/users/00000000-0000-0000-0000-000000000000", status=404, check=[ERR("not_found")]),
        R("Malformed id", "GET", "/users/not-a-uuid", status=400, check=[ERR("validation_error")]),
        create_user("Create a throw-away employee", "throwaway", {
            "name": "Temp Person", "email": "temp.{{run_id}}@acme.example", "job_title": "Contractor", "role": "employee",
            "manager_id": "{{manager_id}}", "salary": 30}),
        R("Reset a password", "POST", "/users/{{throwaway_id}}/reset-password",
          check=[("temporary_password", "type", "string")],
          desc="Admin only. The person must change it at next login; their old tokens stop working."),
        R("Archive a person", "POST", "/users/{{throwaway_id}}/archive", check=[("archived_at", "type", "string")],
          desc="Nothing is deleted: archived people keep their history but cannot sign in."),
        R("Archived people are hidden by default", "GET", "/users", query={"q": "Temp Person"}, check=[("total", "eq", 0)]),
        R("...but admins can include them", "GET", "/users", query={"q": "Temp Person", "include_archived": "true"},
          check=[("total", "eq", 1)]),
        R("Restore a person", "POST", "/users/{{throwaway_id}}/unarchive", check=[("archived_at", "null", None)]),
        R("Admins cannot archive themselves", "POST", "/users/{{admin_id}}/archive", status=400,
          check=[ERR("validation_error")]),
    ]),

    Folder("03 Projects", "Admin creates a project for exactly one manager; visibility depends on role.", [
        R("Create project: Apollo", "POST", "/projects", status=201,
          body={"name": "Apollo {{run_id}}", "description": "Customer website rebuild", "manager_id": "{{manager_id}}",
                "start_date": "{{project_start}}", "end_date": "{{project_end}}", "allocated_hours": 800,
                "budget_amount": 50000},
          check=[("status", "eq", "active"), ("manager.id", "eq", "{{manager_id}}"), ("manager.name", "eq", "Maria Lopez"),
                 ("summary.risk_level", "eq", "on_track"), ("summary.days_total", "eq", 71),
                 ("summary.total_cost", "eq", 0), ("summary.team_size", "eq", 0)],
          save=[("project_id", "id"), ("project_name", "name")],
          desc="Status follows the dates: a project whose start date has arrived is `active` automatically. "
               "The summary (progress, cost, risk) is computed from start/end dates, hours and money."),
        R("Create project: Borealis (other manager)", "POST", "/projects", status=201,
          body={"name": "Borealis {{run_id}}", "description": "Data migration", "manager_id": "{{manager2_id}}",
                "start_date": "{{project_start}}", "end_date": "{{project_end}}", "allocated_hours": 500,
                "budget_amount": 20000},
          check=[("manager.id", "eq", "{{manager2_id}}")], save=[("project2_id", "id")]),
        R("Managers cannot create projects", "POST", "/projects", auth="manager_token", status=403,
          body={"name": "Rogue", "manager_id": "{{manager_id}}", "start_date": "{{project_start}}", "end_date": "{{project_end}}"},
          check=[ERR("forbidden")]),
        R("The project manager must be a manager", "POST", "/projects", status=400,
          body={"name": "Bad boss", "manager_id": "{{employee_id}}", "start_date": "{{project_start}}", "end_date": "{{project_end}}"},
          check=[ERR("validation_error"), ("error.details.0.field", "eq", "manager_id")]),
        R("Duplicate project name", "POST", "/projects", status=409,
          body={"name": "apollo {{run_id}}", "manager_id": "{{manager_id}}", "start_date": "{{project_start}}", "end_date": "{{project_end}}"},
          check=[ERR("conflict")], desc="Names are unique among non-archived projects, ignoring case."),
        R("End date before start date", "POST", "/projects", status=400,
          body={"name": "Backwards", "manager_id": "{{manager_id}}", "start_date": "{{project_end}}", "end_date": "{{project_start}}"},
          check=[ERR("validation_error")]),
        R("List projects (admin sees all)", "GET", "/projects", check=[("total", "eq", 2), ("items", "type", "array"),
                                                                    ("page", "eq", 1), ("page_size", "eq", 25)]),
        R("List projects (a manager sees only their own)", "GET", "/projects", auth="manager_token",
          check=[("total", "eq", 1), ("items.0.id", "eq", "{{project_id}}")]),
        R("List projects (an unassigned employee sees none)", "GET", "/projects", auth="employee2_token",
          check=[("total", "eq", 0)]),
        R("Search and filter projects", "GET", "/projects",
          query={"q": "maria", "status": "active", "manager_id": "{{manager_id}}", "page": "1", "page_size": "10"},
          check=[("total", "eq", 1)], desc="`q` matches project name, description and manager name."),
        R("Get one project", "GET", "/projects/{{project_id}}",
          check=[("id", "eq", "{{project_id}}"), ("budget_amount", "eq", 50000), ("summary.schedule_pct", "type", "number"),
                 ("summary.risk_reasons", "type", "array")]),
        R("Another manager gets 404, not 403", "GET", "/projects/{{project_id}}", auth="manager2_token", status=404,
          check=[ERR("not_found")], desc="A project you may not see is reported as not found."),
        R("Manager adjusts the budget", "PATCH", "/projects/{{project_id}}", auth="manager_token",
          body={"budget_amount": 60000, "allocated_hours": 800}, check=[("budget_amount", "eq", 60000)]),
        R("Only an admin can reassign the manager", "PATCH", "/projects/{{project_id}}", auth="manager_token", status=403,
          body={"manager_id": "{{manager2_id}}"}, check=[ERR("forbidden")]),
        R("Empty name is rejected", "PATCH", "/projects/{{project_id}}", status=400, body={"name": None},
          check=[ERR("validation_error")]),
    ]),

    Folder("04 Milestones", "Key points in the timeline. Dates and hours must fit inside the project.", [
        R("Add milestone: Design", "POST", "/projects/{{project_id}}/milestones", auth="manager_token", status=201,
          body={"name": "Design", "description": "Wireframes and sign-off", "start_date": "{{project_start}}",
                "due_date": "{{milestone1_due}}", "allocated_hours": 200},
          check=[("status", "eq", "pending"), ("is_overdue", "eq", False), ("hours_logged", "eq", 0)],
          save=[("milestone_id", "id")]),
        R("Add milestone: Build", "POST", "/projects/{{project_id}}/milestones", auth="manager_token", status=201,
          body={"name": "Build", "start_date": "{{milestone2_start}}", "due_date": "{{milestone2_due}}", "allocated_hours": 400},
          save=[("milestone2_id", "id")]),
        R("Milestone outside the project dates", "POST", "/projects/{{project_id}}/milestones", auth="manager_token", status=400,
          body={"name": "Too early", "start_date": "{{before_project}}", "due_date": "{{milestone1_due}}"},
          check=[ERR("validation_error")]),
        R("Milestone hours beyond the project's hours", "POST", "/projects/{{project_id}}/milestones", auth="manager_token", status=400,
          body={"name": "Too big", "start_date": "{{project_start}}", "due_date": "{{milestone1_due}}", "allocated_hours": 300},
          check=[ERR("validation_error"), ("error.details.0.field", "eq", "allocated_hours")],
          desc="200 + 400 hours are planned; the project only has 800."),
        R("Duplicate milestone name", "POST", "/projects/{{project_id}}/milestones", auth="manager_token", status=409,
          body={"name": "design", "start_date": "{{project_start}}", "due_date": "{{milestone1_due}}"}, check=[ERR("conflict")]),
        R("List milestones", "GET", "/projects/{{project_id}}/milestones", auth="manager_token",
          check=[("total", "eq", 2), ("planned_hours", "eq", 600), ("items.0.name", "eq", "Design")]),
        R("Start the Build milestone", "PATCH", "/projects/{{project_id}}/milestones/{{milestone2_id}}", auth="manager_token",
          body={"status": "in_progress"}, check=[("status", "eq", "in_progress"), ("completed_at", "null", None)]),
        R("Reach the Design milestone", "PATCH", "/projects/{{project_id}}/milestones/{{milestone_id}}", auth="manager_token",
          body={"status": "done"}, check=[("status", "eq", "done"), ("completed_at", "type", "string")],
          desc="Setting `done` records when the manager said the milestone was reached."),
        R("Get one milestone", "GET", "/projects/{{project_id}}/milestones/{{milestone_id}}", auth="manager_token",
          check=[("name", "eq", "Design")]),
    ]),

    Folder("05 Team", "An employee gives ONE project their full 8-hour day; assignments of one person can never overlap.", [
        R("Put Alex on Apollo", "POST", "/projects/{{project_id}}/team", auth="manager_token", status=201,
          body={"user_id": "{{employee_id}}"},
          check=[("name", "eq", "Alex Kim"), ("daily_hours", "eq", 8), ("start_date", "eq", "{{today}}"),
                 ("end_date", "eq", "{{project_end}}"), ("labor_cost", "eq", 0)],
          desc="Dates default to today (the project has started) until the project's end date."),
        R("Adding the same person twice", "POST", "/projects/{{project_id}}/team", auth="manager_token", status=409,
          body={"user_id": "{{employee_id}}"}, check=[ERR("conflict")]),
        R("Only employees can be on a team", "POST", "/projects/{{project_id}}/team", auth="manager_token", status=400,
          body={"user_id": "{{manager2_id}}"}, check=[ERR("validation_error"), ("error.details.0.field", "eq", "user_id")]),
        R("One project at a time (overlap)", "POST", "/projects/{{project2_id}}/team", auth="manager2_token", status=409,
          body={"user_id": "{{employee_id}}"},
          check=[ERR("assignment_overlap"), ("error.message", "contains", "Apollo")],
          desc="Alex is already on Apollo for these dates; the error names the clashing project and its dates."),
        R("Put Priya on Borealis", "POST", "/projects/{{project2_id}}/team", auth="manager2_token", status=201,
          body={"user_id": "{{employee2_id}}"}, check=[("name", "eq", "Priya Shah")],
          desc="Managers may staff their own project with any employee, whoever the employee reports to."),
        R("Dates outside the project", "POST", "/projects/{{project2_id}}/team", auth="manager2_token", status=400,
          body={"user_id": "{{employee_id}}", "start_date": "{{before_project}}"}, check=[ERR("validation_error")]),
        R("Team (manager sees labor cost)", "GET", "/projects/{{project_id}}/team", auth="manager_token",
          check=[("total", "eq", 1), ("items.0.labor_cost", "eq", 0), ("items.0.hours_logged", "eq", 0)]),
        R("Team (employee does not see labor cost)", "GET", "/projects/{{project_id}}/team", auth="employee_token",
          check=[("total", "eq", 1), ("items.0.labor_cost", "null", None)]),
        R("Change a person's dates", "PATCH", "/projects/{{project_id}}/team/{{employee_id}}", auth="manager_token",
          body={"start_date": "{{today}}"}, check=[("start_date", "eq", "{{today}}")]),
        R("Employees cannot change the plan", "POST", "/projects/{{project_id}}/milestones", auth="employee_token", status=403,
          body={"name": "Sneaky", "start_date": "{{project_start}}", "due_date": "{{milestone1_due}}"}, check=[ERR("forbidden")]),
        R("Employees can read the plan", "GET", "/projects/{{project_id}}/milestones", auth="employee_token",
          check=[("total", "eq", 2)]),
        R("Employee sees the project without money", "GET", "/projects/{{project_id}}", auth="employee_token",
          check=[("budget_amount", "null", None), ("summary.total_cost", "null", None), ("summary.team_size", "eq", 1)],
          desc="Employees never see budget or cost figures."),
    ]),

    Folder("06 Time", "Employees log hours: only inside their assignment dates, never the future, at most 8 hours a day.", [
        R("Alex logs 5 hours", "POST", "/projects/{{project_id}}/time-entries", auth="employee_token", status=201,
          body={"work_date": "{{today}}", "hours": 5, "milestone_id": "{{milestone2_id}}", "notes": "Built the login page"},
          check=[("hours", "eq", 5), ("labor_cost", "null", None), ("user_name", "eq", "Alex Kim")],
          save=[("entry_id", "id")], desc="Labor cost is hours x salary, hidden from the employee."),
        R("A day holds at most 8 hours", "POST", "/projects/{{project_id}}/time-entries", auth="employee_token", status=409,
          body={"work_date": "{{today}}", "hours": 4}, check=[ERR("daily_limit"), ("error.message", "contains", "3 h are left")]),
        R("Cannot log the future", "POST", "/projects/{{project_id}}/time-entries", auth="employee_token", status=400,
          body={"work_date": "{{future_date}}", "hours": 2}, check=[ERR("validation_error"), ("error.details.0.field", "eq", "work_date")]),
        R("Cannot log before the assignment started", "POST", "/projects/{{project_id}}/time-entries", auth="employee_token", status=409,
          body={"work_date": "{{yesterday}}", "hours": 2}, check=[ERR("not_assigned")]),
        R("Employees log only for themselves", "POST", "/projects/{{project_id}}/time-entries", auth="employee_token", status=403,
          body={"work_date": "{{today}}", "hours": 1, "user_id": "{{employee2_id}}"}, check=[ERR("forbidden")]),
        R("The manager logs for Alex", "POST", "/projects/{{project_id}}/time-entries", auth="manager_token", status=201,
          body={"work_date": "{{today}}", "hours": 3, "user_id": "{{employee_id}}", "notes": "Pairing session"},
          check=[("hours", "eq", 3), ("labor_cost", "eq", 150)], save=[("entry2_id", "id")],
          desc="Managers see labor cost: 3 h x $50."),
        R("The day is now full", "POST", "/projects/{{project_id}}/time-entries", auth="manager_token", status=409,
          body={"work_date": "{{today}}", "hours": 1, "user_id": "{{employee_id}}"}, check=[ERR("daily_limit")]),
        R("A person outside the team cannot log", "POST", "/projects/{{project_id}}/time-entries", auth="employee2_token", status=404,
          body={"work_date": "{{today}}", "hours": 1}, check=[ERR("not_found")]),
        R("Project time (manager)", "GET", "/projects/{{project_id}}/time-entries", auth="manager_token",
          check=[("total", "eq", 2), ("total_hours", "eq", 8), ("items.0.labor_cost", "type", "number")]),
        R("Project time (employee sees their own entries, without cost)", "GET", "/projects/{{project_id}}/time-entries",
          auth="employee_token", check=[("total", "eq", 2), ("total_hours", "eq", 8), ("items.0.labor_cost", "null", None)],
          desc="Employees only ever see their own entries (including ones a manager logged for them), never the cost."),
        R("Filter by date range", "GET", "/projects/{{project_id}}/time-entries", auth="manager_token",
          query={"from": "{{yesterday}}", "to": "{{today}}", "user_id": "{{employee_id}}"}, check=[("total", "eq", 2)]),
        R("My time with daily totals", "GET", "/time-entries/me", auth="employee_token",
          check=[("total_hours", "eq", 8), ("daily_totals.0.hours", "eq", 8), ("daily_totals.0.remaining", "eq", 0)]),
        R("My time with a bad range", "GET", "/time-entries/me", auth="employee_token", status=400,
          query={"from": "{{today}}", "to": "{{yesterday}}"}, check=[ERR("validation_error")]),
        R("Remove an entry (manager)", "DELETE", "/projects/{{project_id}}/time-entries/{{entry2_id}}", auth="manager_token",
          status=204, desc="Entries are archived, never deleted."),
        R("Removing it twice", "DELETE", "/projects/{{project_id}}/time-entries/{{entry2_id}}", auth="manager_token", status=404,
          check=[ERR("not_found")]),
    ]),

    Folder("07 Costs", "Non-labor spend. Visible only to the project's manager and admins.", [
        R("Add a license cost", "POST", "/projects/{{project_id}}/costs", auth="manager_token", status=201,
          body={"category": "license", "description": "IDE seats", "amount": 1200, "incurred_on": "{{today}}"},
          check=[("amount", "eq", 1200), ("category", "eq", "license")], save=[("cost_id", "id")]),
        R("Add a technology cost", "POST", "/projects/{{project_id}}/costs", auth="manager_token", status=201,
          body={"category": "technology", "description": "Hosting", "amount": 300, "incurred_on": "{{today}}"},
          save=[("cost2_id", "id")]),
        R("Invalid cost", "POST", "/projects/{{project_id}}/costs", auth="manager_token", status=400,
          body={"category": "snacks", "description": "", "amount": -5, "incurred_on": "{{today}}"}, check=[ERR("validation_error")]),
        R("Costs and totals against the budget", "GET", "/projects/{{project_id}}/costs", auth="manager_token",
          check=[("total", "eq", 2), ("other_cost", "eq", 1500), ("labor_cost", "eq", 250), ("total_cost", "eq", 1750),
                 ("budget_amount", "eq", 60000), ("budget_remaining", "eq", 58250), ("by_category.license", "eq", 1200)],
          desc="Labor 250 (5 h x $50) + other 1,500 = 1,750 spent of 60,000."),
        R("Correct a cost", "PATCH", "/projects/{{project_id}}/costs/{{cost2_id}}", auth="manager_token",
          body={"amount": 400}, check=[("amount", "eq", 400)]),
        R("Remove a cost", "DELETE", "/projects/{{project_id}}/costs/{{cost_id}}", auth="manager_token", status=204),
        R("Employees cannot see costs", "GET", "/projects/{{project_id}}/costs", auth="employee_token", status=403, check=[ERR("forbidden")]),
        R("Another manager cannot see them either", "GET", "/projects/{{project_id}}/costs", auth="manager2_token", status=404,
          check=[ERR("not_found")]),
    ]),

    Folder("08 Reports", "The dashboards that answer the business questions.", [
        R("Overview (manager)", "GET", "/reports/overview", auth="manager_token",
          check=[("counts.projects", "eq", 1), ("counts.active", "eq", 1), ("totals.budget", "eq", 60000),
                 ("totals.labor_cost", "eq", 250), ("totals.other_cost", "eq", 400), ("totals.spent", "eq", 650),
                 ("totals.budget_remaining", "eq", 59350), ("projects.0.name", "eq", "{{project_name}}"),
                 ("allocation", "type", "array"), ("available_people", "type", "number")],
          desc="Project health ordered by urgency, money and hours totals, and who is allocated where."),
        R("Overview (admin sees all projects)", "GET", "/reports/overview",
          check=[("counts.projects", "eq", 2), ("projects", "type", "array"), ("allocation", "type", "array")]),
        R("Employees have no overview", "GET", "/reports/overview", auth="employee_token", status=403, check=[ERR("forbidden")]),
        R("My dashboard (employee)", "GET", "/reports/my-dashboard", auth="employee_token",
          check=[("current_project.name", "eq", "{{project_name}}"), ("hours_today", "eq", 5), ("hours_today_remaining", "eq", 3),
                 ("week_capacity", "eq", 40), ("projects.0.budget_amount", "null", None), ("recent_entries", "type", "array")]),
        R("My dashboard (manager)", "GET", "/reports/my-dashboard", auth="manager_token",
          check=[("projects.0.id", "eq", "{{project_id}}"), ("current_project", "null", None)]),
    ]),

    Folder("09 Project lifecycle", "Complete, archive and restore. Nothing is deleted.", [
        R("Complete the project", "POST", "/projects/{{project_id}}/complete", auth="manager_token",
          check=[("status", "eq", "completed"), ("completed_at", "type", "string"), ("summary.risk_level", "eq", "done")],
          desc="The manager says the project is done. The team is released: assignments end today."),
        R("Completing twice", "POST", "/projects/{{project_id}}/complete", auth="manager_token", status=409, check=[ERR("conflict")]),
        R("A finished project cannot be edited", "PATCH", "/projects/{{project_id}}", auth="manager_token", status=409,
          body={"budget_amount": 1}, check=[ERR("conflict")]),
        R("Alex is free again from tomorrow", "POST", "/projects/{{project2_id}}/team", auth="manager2_token", status=201,
          body={"user_id": "{{employee_id}}", "start_date": "{{tomorrow}}"}, check=[("start_date", "eq", "{{tomorrow}}")],
          desc="Several projects over time, one at a time."),
        R("Managers cannot archive", "POST", "/projects/{{project_id}}/archive", auth="manager_token", status=403, check=[ERR("forbidden")]),
        R("Admin archives the project", "POST", "/projects/{{project_id}}/archive",
          check=[("status", "eq", "archived"), ("archived_at", "type", "string")]),
        R("Archived projects are hidden", "GET", "/projects", check=[("total", "eq", 1)]),
        R("...unless asked for", "GET", "/projects", query={"include_archived": "true"}, check=[("total", "eq", 2)]),
        R("A manager can no longer see it", "GET", "/projects/{{project_id}}", auth="manager_token", status=404, check=[ERR("not_found")]),
        R("Restore the project", "POST", "/projects/{{project_id}}/unarchive",
          check=[("archived_at", "null", None), ("status", "eq", "completed")]),
    ]),

    Folder("10 Admin", "Admin-only operations.", [
        R("Seeding demo data is admin only", "POST", "/admin/seed-demo", auth="manager_token", status=403, check=[ERR("forbidden")]),
        R("Seed demo data", "POST", "/admin/seed-demo",
          check=[("created", "eq", True), ("accounts", "type", "array"), ("accounts.0.temporary_password", "type", "string")],
          desc="Creates 2 managers, 6 employees and 4 projects in different health states. The one-time passwords are shown once."),
        R("Seeding twice does nothing", "POST", "/admin/seed-demo", check=[("created", "eq", False), ("accounts", "len_eq", 0)]),
        R("Overview shows every health state", "GET", "/reports/overview",
          check=[("counts.overdue", "gte", 1), ("counts.at_risk", "gte", 1), ("counts.planned", "gte", 1)]),
    ]),
]

# ---------------------------------------------------------------------------------------
# Variable substitution, JSON-path helpers and assertions (shared by runner and generator)
# ---------------------------------------------------------------------------------------
VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def subst(text: str, variables: dict[str, str]) -> str:
    return VAR_RE.sub(lambda m: variables.get(m.group(1), m.group(0)), text)


def get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def evaluate(op: str, actual: Any, expected: Any) -> bool:
    kinds = {"array": list, "string": str, "object": dict, "boolean": bool}
    if op == "eq":
        return actual == expected
    if op == "null":
        return actual is None
    if op == "type":
        if expected == "number":
            return isinstance(actual, (int, float)) and not isinstance(actual, bool)
        return isinstance(actual, kinds[expected])
    if op == "matches":
        return isinstance(actual, str) and re.search(expected, actual) is not None
    if op == "contains":
        return isinstance(actual, str) and expected in actual
    if op == "gte":
        return isinstance(actual, (int, float)) and actual >= expected
    if op == "len_eq":
        return isinstance(actual, list) and len(actual) == expected
    raise ValueError(op)


def mask(body: Any) -> Any:
    """Replace tokens in saved examples; they are secrets and expire anyway."""
    if isinstance(body, dict):
        return {k: ("<JWT access token>" if k == "access_token" else mask(v)) for k, v in body.items()}
    if isinstance(body, list):
        return [mask(v) for v in body]
    return body


# ---------------------------------------------------------------------------------------
# Runner: executes the spec against a live API and records the responses
# ---------------------------------------------------------------------------------------
def run_spec(base_url: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    import httpx

    variables: dict[str, str] = {
        "initial_admin_username": INITIAL_ADMIN, "initial_admin_password": INITIAL_PASSWORD, "new_password": NEW_PASSWORD,
        "run_id": uuid.uuid4().hex[:6],
    }
    today = dt.datetime.now(dt.UTC).date()
    variables.update({k: (today + dt.timedelta(days=n)).isoformat() for k, n in DATE_OFFSETS.items()})

    recorded: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    with httpx.Client(base_url=base_url, timeout=30) as client:
        for folder in SPEC:
            for req in folder.items:
                key = f"{folder.name}/{req.name}"
                path = subst(req.path, variables)
                params = {k: subst(v, variables) for k, v in req.query.items()}
                headers = {}
                if req.auth and variables.get(req.auth):
                    headers["Authorization"] = f"Bearer {variables[req.auth]}"
                body_text = subst(json.dumps(req.body, indent=2), variables) if req.body is not None else None
                if body_text:
                    headers["Content-Type"] = "application/json"
                resp = client.request(req.method, path, params=params, headers=headers, content=body_text)
                try:
                    data = resp.json() if resp.content else None
                except ValueError:
                    data = None
                problems = []
                if resp.status_code != req.status:
                    problems.append(f"status {resp.status_code} != {req.status}")
                if data is not None:
                    for jpath, op, expected in req.check:
                        want = subst(expected, variables) if isinstance(expected, str) and op in {"eq", "contains"} else expected
                        if not evaluate(op, get_path(data, jpath), want):
                            problems.append(f"{jpath} {op} {want!r} (got {get_path(data, jpath)!r})")
                elif req.check:
                    problems.append("expected a JSON body")
                for var, jpath in req.save:
                    value = get_path(data, jpath) if data is not None else None
                    if value is None:
                        problems.append(f"cannot save {var} from {jpath}")
                    else:
                        variables[var] = str(value)
                if problems:
                    failures.append(f"{key}: " + "; ".join(problems))
                recorded[key] = {
                    "code": resp.status_code, "reason": resp.reason_phrase,
                    "body": json.dumps(mask(data), indent=2) if data is not None else "",
                    "sent_path": path, "sent_params": params, "sent_body": body_text,
                }
    return recorded, failures


# ---------------------------------------------------------------------------------------
# Postman generation
# ---------------------------------------------------------------------------------------
JS_HELPERS = "const get = (o, p) => p.split('.').reduce((a, k) => (a === null || a === undefined ? undefined : a[k]), o);"


def js_literal(value: Any) -> str:
    return json.dumps(value)


def test_script(req: Req) -> list[str]:
    lines = [f'pm.test("Status code is {req.status}", function () {{ pm.response.to.have.status({req.status}); }});']
    if req.status == 204:
        return lines
    lines += [JS_HELPERS, "let json = null;", "try { json = pm.response.json(); } catch (e) { json = null; }"]
    if req.check:
        lines.append('pm.test("Response is JSON", function () { pm.expect(json).to.not.equal(null); });')
    for jpath, op, expected in req.check:
        title = f"{jpath} {op}" + ("" if op == "null" else f" {expected}")
        actual = f"get(json, {js_literal(jpath)})"
        exp = f"pm.variables.replaceIn({js_literal(expected)})" if isinstance(expected, str) and op in {"eq", "contains"} else js_literal(expected)
        body = {
            "eq": f"pm.expect({actual}).to.eql({exp});",
            "null": f"pm.expect({actual}).to.equal(null);",
            "type": (f"pm.expect({actual}).to.be.a('number');" if expected == "number"
                     else f"pm.expect({actual}).to.be.an({js_literal(expected)});"),
            "matches": f"pm.expect({actual}).to.match(new RegExp({js_literal(expected)}));",
            "contains": f"pm.expect({actual}).to.include({exp});",
            "gte": f"pm.expect({actual}).to.be.at.least({exp});",
            "len_eq": f"pm.expect({actual}).to.have.lengthOf({exp});",
        }[op]
        lines.append(f"pm.test({js_literal(title)}, function () {{ {body} }});")
    for var, jpath in req.save:
        lines.append(f"if (json) {{ pm.collectionVariables.set({js_literal(var)}, get(json, {js_literal(jpath)})); }}")
    return lines


def bearer(var: str) -> dict[str, Any]:
    return {"type": "bearer", "bearer": [{"key": "token", "value": "{{%s}}" % var, "type": "string"}]}


def url_obj(path: str, query: dict[str, str]) -> dict[str, Any]:
    raw = "{{baseUrl}}" + path + ("?" + "&".join(f"{k}={v}" for k, v in query.items()) if query else "")
    return {
        "raw": raw, "host": ["{{baseUrl}}"], "path": [p for p in path.split("/") if p],
        "query": [{"key": k, "value": v} for k, v in query.items()],
    }


def item_for(req: Req, folder: str, recorded: dict[str, dict[str, Any]]) -> dict[str, Any]:
    header = [{"key": "Content-Type", "value": "application/json"}] if req.body is not None else []
    request: dict[str, Any] = {
        "auth": bearer(req.auth) if req.auth else {"type": "noauth"},
        "method": req.method, "header": header, "url": url_obj(req.path, req.query),
        "description": req.desc or req.name,
    }
    if req.body is not None:
        request["body"] = {"mode": "raw", "raw": json.dumps(req.body, indent=2),
                           "options": {"raw": {"language": "json"}}}
    item: dict[str, Any] = {
        "name": req.name,
        "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": test_script(req)}}],
        "request": request,
        "response": [],
    }
    rec = recorded.get(f"{folder}/{req.name}")
    if rec:
        sent = {**request, "url": {**request["url"], "raw": "{{baseUrl}}" + rec["sent_path"]}}
        if rec["sent_body"]:
            sent["body"] = {"mode": "raw", "raw": rec["sent_body"], "options": {"raw": {"language": "json"}}}
        item["response"].append({
            "name": f"{rec['code']} {rec['reason']}", "originalRequest": sent, "status": rec["reason"], "code": rec["code"],
            "_postman_previewlanguage": "json", "header": [{"key": "Content-Type", "value": "application/json"}] if rec["body"] else [],
            "cookie": [], "body": rec["body"],
        })
    return item


def build_collection(recorded: dict[str, dict[str, Any]]) -> dict[str, Any]:
    description = (
        "Full test flow for the ACME Project Tracker API (FastAPI on AWS Lambda).\n\n"
        "**How to use**\n"
        "1. Import this collection and one environment (local / localstack / aws).\n"
        "2. Point the API at an EMPTY database (the first admin is created on the first request).\n"
        "3. Run the collection in order (Collection Runner or `newman run`). Every request checks its own response and "
        "stores ids/tokens for the next one.\n\n"
        "**Roles used**: admin, two managers (Maria, James), two employees (Alex, Priya). Tokens are kept in "
        "collection variables (`admin_token`, `manager_token`, ...).\n\n"
        "Each request has saved example responses showing the expected JSON."
    )
    variables = [{"key": "baseUrl", "value": "http://localhost:8000"}]
    variables += [{"key": "initial_admin_username", "value": INITIAL_ADMIN},
                  {"key": "initial_admin_password", "value": INITIAL_PASSWORD},
                  {"key": "new_password", "value": NEW_PASSWORD}]
    return {
        "info": {"_postman_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "acme-pm-api")), "name": COLLECTION_NAME,
                 "description": description, "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "auth": bearer("admin_token"),
        "event": [{"listen": "prerequest", "script": {"type": "text/javascript", "exec": PRE_REQUEST_JS.splitlines()}}],
        "variable": variables,
        "item": [{"name": f.name, "description": f.desc, "item": [item_for(r, f.name, recorded) for r in f.items]} for f in SPEC],
    }


def build_environment(name: str, base_url: str) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"acme-pm-api-env-{name}")), "name": f"ACME PM API - {name}",
        "values": [
            {"key": "baseUrl", "value": base_url, "type": "default", "enabled": True},
            {"key": "initial_admin_username", "value": INITIAL_ADMIN, "type": "default", "enabled": True},
            {"key": "initial_admin_password", "value": INITIAL_PASSWORD if name != "aws" else "<terraform output -raw bootstrap_admin_password>",
             "type": "secret", "enabled": True},
            {"key": "new_password", "value": NEW_PASSWORD, "type": "secret", "enabled": True},
        ],
        "_postman_variable_scope": "environment",
    }


ENVIRONMENTS = {
    "local": "http://localhost:8000",  # uvicorn app.main:app --port 8000
    "localstack": "http://localhost:3001/api/pm-api",  # ./bin/start-dev.sh (proxy)
    "aws": "https://<your-cloudfront-domain>/api/pm-api",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="API to run the flow against")
    parser.add_argument("--no-run", action="store_true", help="generate files without calling the API")
    args = parser.parse_args()

    recorded: dict[str, dict[str, Any]] = {}
    if not args.no_run:
        recorded, failures = run_spec(args.base_url)
        total = sum(len(f.items) for f in SPEC)
        print(f"Ran {total} requests against {args.base_url}: {total - len(failures)} passed, {len(failures)} failed")
        for line in failures:
            print("  FAIL", line)
        if failures:
            return 1

    (OUT_DIR / "acme-pm-api.postman_collection.json").write_text(json.dumps(build_collection(recorded), indent=2) + "\n")
    for name, url in ENVIRONMENTS.items():
        (OUT_DIR / f"{name}.postman_environment.json").write_text(json.dumps(build_environment(name, url), indent=2) + "\n")
    print(f"Wrote collection ({sum(len(f.items) for f in SPEC)} requests) and {len(ENVIRONMENTS)} environments to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
