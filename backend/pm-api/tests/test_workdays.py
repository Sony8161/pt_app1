"""The calendar maths behind every shift: Monday-Friday are 8-hour days, weekends are not."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2026-03-09", "2026-03-13", 5),  # Mon-Fri
        ("2026-03-09", "2026-03-15", 5),  # Mon-Sun: the weekend adds nothing
        ("2026-03-14", "2026-03-15", 0),  # Sat-Sun
        ("2026-03-11", "2026-03-11", 1),  # a single working day
        ("2026-03-14", "2026-03-14", 0),  # a single Saturday
        ("2026-03-09", "2026-03-20", 10),  # two full weeks
        ("2026-03-13", "2026-03-16", 2),  # Fri and Mon
        ("2026-03-20", "2026-03-09", 0),  # reversed range
    ],
)
def test_working_days(api, raw_db, start, end, expected):
    row = raw_db.execute("SELECT working_days(%s::date, %s::date) AS n", (start, end)).fetchone()
    assert row["n"] == expected


def test_weekend_assignments_cost_nothing(api, today):
    manager = api.user("manager")
    employee = api.user("employee", manager=manager, salary=40)
    project = api.project(manager)
    ms = api.milestone(project["id"], manager, start="2026-03-14", due="2026-03-15")  # Sat-Sun
    api.assign(project["id"], ms["id"], employee, manager.headers)
    summary = api.client.get(f"/projects/{project['id']}", headers=manager.headers).json()["summary"]
    assert summary["hours_worked"] == 0 and summary["forecast_cost"] == 0


def test_hours_and_cost_follow_the_calendar(api, today):
    """Today is Wednesday 11 March: Mon, Tue and Wed of the assignment have been worked."""
    manager = api.user("manager")
    employee = api.user("employee", manager=manager, salary=40)
    project = api.project(manager)
    ms = api.milestone(project["id"], manager)  # milestone Mon 9 - Fri 27 March (15 working days)
    api.assign(project["id"], ms["id"], employee, manager.headers, start_date="2026-03-09")
    summary = api.client.get(f"/projects/{project['id']}", headers=manager.headers).json()["summary"]
    assert summary["hours_worked"] == 24  # 3 days x 8
    assert summary["labor_cost"] == 960  # 24 h x $40
    assert summary["forecast_cost"] == 4800  # 15 days x 8 h x $40
    detail = api.client.get(f"/projects/{project['id']}/milestones/{ms['id']}", headers=manager.headers).json()
    assert detail["hours_worked"] == 24 and detail["labor_cost"] == 960 and detail["assignees"] == 1
