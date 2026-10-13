"""Date-based project health (pure functions)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.domains.projects.metrics import build_summary

D = dt.date


def row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "active", "start_date": D(2026, 1, 1), "end_date": D(2026, 4, 10),  # 100 days
        "allocated_hours": 1000, "budget_amount": 100000, "hours_worked": 0, "labor_cost": 0, "forecast_cost": 0, "other_cost": 0,
        "milestones_total": 0, "milestones_done": 0, "milestones_overdue": 0, "team_size": 0,
    }
    base.update(over)
    return base


def test_schedule_percentage_follows_the_calendar():
    s = build_summary(row(), D(2026, 2, 19))  # day 50 of 100
    assert s["days_total"] == 100 and s["days_elapsed"] == 50
    assert s["schedule_pct"] == 50.0 and s["days_remaining"] == 50


def test_schedule_is_clamped_before_start_and_after_end():
    assert build_summary(row(status="planned"), D(2025, 12, 1))["schedule_pct"] == 0.0
    assert build_summary(row(), D(2026, 6, 1))["schedule_pct"] == 100.0


def test_on_track_when_usage_matches_the_calendar():
    s = build_summary(row(hours_worked=480, labor_cost=40000, other_cost=5000), D(2026, 2, 19))
    assert s["risk_level"] == "on_track" and s["risk_reasons"] == []
    assert s["total_cost"] == 45000 and s["budget_remaining"] == 55000 and s["budget_pct"] == 45.0


def test_spending_ahead_of_calendar_is_at_risk():
    s = build_summary(row(labor_cost=70000), D(2026, 2, 19))  # 70% spent at 50% of the time
    assert s["risk_level"] == "at_risk"
    assert any("ahead of the calendar" in r for r in s["risk_reasons"])


def test_hours_ahead_of_calendar_is_at_risk():
    s = build_summary(row(hours_worked=700), D(2026, 2, 19))
    assert s["risk_level"] == "at_risk" and any("Hours used" in r for r in s["risk_reasons"])


def test_budget_nearly_gone_is_at_risk_even_late_in_the_project():
    s = build_summary(row(labor_cost=95000), D(2026, 4, 1))
    assert s["risk_level"] == "at_risk" and any("95% of the budget" in r for r in s["risk_reasons"])


def test_over_budget_is_reported_with_the_amount():
    s = build_summary(row(labor_cost=90000, other_cost=15000), D(2026, 4, 1))
    assert any("Over budget by $5,000.00" in r for r in s["risk_reasons"])


def test_planned_staffing_over_budget_is_flagged_before_the_money_is_spent():
    s = build_summary(row(forecast_cost=120000, labor_cost=1000), D(2026, 2, 19))
    assert s["risk_level"] == "at_risk" and s["forecast_cost"] == 120000
    assert any("Planned staffing will cost $20,000.00 more than the budget" in r for r in s["risk_reasons"])


def test_forecast_includes_other_costs_and_is_hidden_from_employees():
    assert build_summary(row(forecast_cost=60000, other_cost=45000), D(2026, 2, 19))["risk_level"] == "at_risk"
    hidden = build_summary(row(forecast_cost=999999), D(2026, 2, 19), include_costs=False)
    assert hidden["forecast_cost"] is None and hidden["risk_level"] == "on_track"


def test_overdue_milestone_makes_project_at_risk():
    s = build_summary(row(milestones_total=3, milestones_done=1, milestones_overdue=1), D(2026, 2, 19))
    assert s["risk_level"] == "at_risk" and s["milestones_pct"] == 33.3


def test_past_end_date_is_overdue():
    s = build_summary(row(), D(2026, 4, 15))
    assert s["risk_level"] == "overdue" and "5 day(s) past the end date" in s["risk_reasons"]


def test_ending_soon_with_open_milestones():
    s = build_summary(row(milestones_total=2, milestones_done=1), D(2026, 4, 5))
    assert s["risk_level"] == "at_risk" and any("Ends in 5 day(s)" in r for r in s["risk_reasons"])


def test_planned_and_finished_projects_are_never_flagged():
    assert build_summary(row(status="planned", labor_cost=999999), D(2026, 1, 1))["risk_level"] == "on_track"
    assert build_summary(row(status="completed", labor_cost=999999), D(2026, 9, 1))["risk_level"] == "done"


def test_money_is_hidden_when_costs_are_excluded():
    s = build_summary(row(labor_cost=95000), D(2026, 4, 1), include_costs=False)
    assert s["total_cost"] is None and s["budget_pct"] is None and s["labor_cost"] is None
    assert not any("budget" in r.lower() for r in s["risk_reasons"])


def test_zero_allocations_do_not_divide_by_zero():
    s = build_summary(row(allocated_hours=0, budget_amount=0), D(2026, 2, 19))
    assert s["hours_pct"] is None and s["budget_pct"] is None and s["milestones_pct"] is None
