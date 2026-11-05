"""Read-only, date-matched bodyweight provenance for strength analytics."""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from app.body_composition import CompositionRow
from app.mfp import load as mfp_load


def valid_weight(value: Any) -> float | None:
    """Exclude NaN, infinity, implausible values and booleans."""
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) and 30 <= n <= 350 else None


def valid_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def normalize(rows, source: str, date_key="date", weight_key="weight_kg"):
    """Last *valid* observation for a date wins; invalid later rows cannot erase it."""
    dates: dict[date, dict] = {}
    for row in rows:
        day = valid_date(row.get(date_key))
        weight = valid_weight(row.get(weight_key))
        if day is not None and weight is not None:
            dates[day] = {"date": day.isoformat(), "source": source, "weight_kg": weight}
    return dates


def histories():
    """Load the cached MFP file once; fall back to stored manual composition rows."""
    errors = []
    try:
        mfp = normalize(mfp_load("weight"), "mfp")
    except (FileNotFoundError, OSError, ValueError) as exc:
        mfp = {}
        errors.append("MFP weight cache unavailable")
    rows = CompositionRow.query.filter_by(source="manual").order_by(
        CompositionRow.observed_on, CompositionRow.id).all()
    manual = normalize(
        [{"date": r.observed_on, "Weight": (r.payload or {}).get("Weight")} for r in rows],
        "manual", weight_key="Weight")
    return {"mfp": mfp, "manual": manual, "diagnostics": errors}


def match_weight(history, on: date, max_days: int = 14):
    """Same/earlier reading within 14 days; MFP precedence then manual."""
    for source in ("mfp", "manual"):
        candidates = [d for d in history[source] if d <= on and (on - d).days <= max_days]
        if candidates:
            d = max(candidates)
            return {**history[source][d], "age_days": (on - d).days}
    return None



def highest_weight(history, on: date, days: int = 90):
    """Maximum recorded bodyweight in the trailing 90 calendar days, inclusive.

    This is intentionally NOT the latest weigh-in. Read MFP and manual sources,
    deduplicate identical dates with MFP precedence, then select the highest
    valid measurement. Ties choose the newest day, then MFP. Never use future
    weights; keep the measurement's provenance for the UI/CSV.
    """
    if days < 1:
        raise ValueError("days must be >= 1")
    from datetime import timedelta
    start = on - timedelta(days=days - 1)
    combined = {
        day: record for day, record in history.get("manual", {}).items()
        if start <= day <= on
    }
    combined.update({
        day: record for day, record in history.get("mfp", {}).items()
        if start <= day <= on
    })
    if not combined:
        return None
    day, record = max(combined.items(), key=lambda item: (
        item[1]["weight_kg"], item[0], item[1]["source"] == "mfp"))
    return {**record, "age_days": (on - day).days, "method": "highest_90d",
            "period_start": start.isoformat(), "period_end": on.isoformat()}


def weight_state(history, on: date):
    """Missing and stale are distinct; future observations cannot satisfy either."""
    if match_weight(history, on):
        return "available"
    if any(d <= on for source in ("mfp", "manual") for d in history[source]):
        return "stale_bodyweight"
    if history.get("diagnostics") and not history["manual"]:
        return "source_unavailable"
    return "missing_bodyweight"
