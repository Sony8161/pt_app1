"""Project health, computed from dates, hours and money. Pure functions, no database.

The idea: a project has a start and an end date, so after X% of the calendar has passed
we expect roughly X% of the hours and budget to be used and the matching milestones to be
done. Spending or hours running well ahead of the calendar, milestones past their due date,
or a passed end date all raise a flag.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# How far (in percentage points) hours or spend may run ahead of the calendar before we warn.
AHEAD_MARGIN = 15.0
# Warn when this much of the budget is gone, however early or late it is.
BUDGET_WARNING_PCT = 90.0
# Warn when the end is this close and milestones are still open.
ENDING_SOON_DAYS = 7

FINISHED = {"completed", "archived"}


def _pct(part: float, whole: float) -> float | None:
    return round(100.0 * part / whole, 1) if whole > 0 else None


def build_summary(row: dict[str, Any], today: dt.date, *, include_costs: bool = True) -> dict[str, Any]:
    """Derive progress numbers and a risk level for one project row (see ``projects.repository``)."""
    start, end = row["start_date"], row["end_date"]
    total_days = (end - start).days + 1
    elapsed_days = min(max((today - start).days + 1, 0), total_days)
    schedule_pct = round(100.0 * elapsed_days / total_days, 1)
    days_remaining = (end - today).days

    allocated = float(row["allocated_hours"])
    logged = float(row["hours_logged"])
    hours_pct = _pct(logged, allocated)

    labor = float(row["labor_cost"])
    other = float(row["other_cost"])
    budget = float(row["budget_amount"])
    total_cost = labor + other
    budget_pct = _pct(total_cost, budget)

    m_total, m_done, m_overdue = int(row["milestones_total"]), int(row["milestones_done"]), int(row["milestones_overdue"])

    level, reasons = _assess(
        status=row["status"],
        schedule_pct=schedule_pct,
        days_remaining=days_remaining,
        hours_pct=hours_pct,
        budget_pct=budget_pct if include_costs else None,
        overspend=total_cost - budget,
        milestones_open=m_total - m_done,
        milestones_overdue=m_overdue,
    )

    summary: dict[str, Any] = {
        "days_total": total_days,
        "days_elapsed": elapsed_days,
        "days_remaining": days_remaining,
        "schedule_pct": schedule_pct,
        "hours_logged": round(logged, 2),
        "hours_remaining": round(allocated - logged, 2),
        "hours_pct": hours_pct,
        "milestones_total": m_total,
        "milestones_done": m_done,
        "milestones_overdue": m_overdue,
        "milestones_pct": _pct(m_done, m_total),
        "team_size": int(row["team_size"]),
        "risk_level": level,
        "risk_reasons": reasons,
        "labor_cost": None,
        "other_cost": None,
        "total_cost": None,
        "budget_remaining": None,
        "budget_pct": None,
    }
    if include_costs:
        summary.update(
            labor_cost=round(labor, 2),
            other_cost=round(other, 2),
            total_cost=round(total_cost, 2),
            budget_remaining=round(budget - total_cost, 2),
            budget_pct=budget_pct,
        )
    return summary


def _assess(
    *,
    status: str,
    schedule_pct: float,
    days_remaining: int,
    hours_pct: float | None,
    budget_pct: float | None,
    overspend: float,
    milestones_open: int,
    milestones_overdue: int,
) -> tuple[str, list[str]]:
    """Return ``(risk_level, reasons)``; level is done / on_track / at_risk / overdue."""
    if status in FINISHED:
        return "done", []
    if status == "planned":
        return "on_track", []

    reasons: list[str] = []
    overdue = days_remaining < 0
    if overdue:
        reasons.append(f"{-days_remaining} day(s) past the end date")
    if milestones_overdue:
        reasons.append(f"{milestones_overdue} milestone(s) past their due date")
    if budget_pct is not None:
        if budget_pct > 100:
            reasons.append(f"Over budget by ${overspend:,.2f}")
        elif budget_pct >= BUDGET_WARNING_PCT:
            reasons.append(f"{budget_pct:.0f}% of the budget is used")
        elif budget_pct > schedule_pct + AHEAD_MARGIN:
            reasons.append(f"Spending ({budget_pct:.0f}%) is ahead of the calendar ({schedule_pct:.0f}%)")
    if hours_pct is not None:
        if hours_pct > 100:
            reasons.append("More hours logged than allocated")
        elif hours_pct > schedule_pct + AHEAD_MARGIN:
            reasons.append(f"Hours used ({hours_pct:.0f}%) are ahead of the calendar ({schedule_pct:.0f}%)")
    if 0 <= days_remaining <= ENDING_SOON_DAYS and milestones_open > 0:
        reasons.append(f"Ends in {days_remaining} day(s) with {milestones_open} milestone(s) still open")

    if overdue:
        return "overdue", reasons
    return ("at_risk" if reasons else "on_track"), reasons
