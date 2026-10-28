"""Offset account history and illustrative 12-month projection."""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from pathlib import Path

from flask import current_app
from openpyxl import load_workbook

from app.finance import money
from app.importer import parse_date


def project_offset(snapshots, horizon=12):
    """Project using the mean calendar-month slope of observations, not guessed deposits."""
    ordered = sorted({d: Decimal(str(v)) for d, v in snapshots}.items())
    if not ordered:
        return dict(status="no_data", history=[], projection=[], average_monthly_change_aud=None)
    history = [dict(as_of=d.isoformat(), balance_aud=money(v)) for d,v in ordered]
    changes = []
    # Use at most the previous 12 months to avoid ancient account trends dominating.
    last_day, last_value = ordered[-1]
    for (before, b), (after, a) in zip(ordered, ordered[1:]):
        days = (after-before).days
        if days > 0 and (last_day-after).days <= 366:
            changes.append((a-b)*Decimal("30.4375")/Decimal(days))
    rate = sum(changes, Decimal(0))/len(changes) if changes else Decimal(0)
    projection = []
    for step in range(1, horizon+1):
        year = last_day.year + (last_day.month-1+step)//12
        month = (last_day.month-1+step)%12+1
        projected_day = date(year, month, min(last_day.day, monthrange(year,month)[1]))
        projection.append(dict(as_of=projected_day.isoformat(),
                               balance_aud=money(max(Decimal(0), last_value+rate*step))))
    return dict(status="ok", history=history, projection=projection,
                latest_as_of=last_day.isoformat(), current_balance_aud=money(last_value),
                average_monthly_change_aud=money(rate),
                projected_12mo_aud=projection[-1]["balance_aud"],
                assumptions="Illustrative extrapolation of observed average calendar-month offset balance change over the last 12 months; no assumed deposits, withdrawals or interest credits. Not a guaranteed forecast.")


def offset_history():
    """Use the same authorised finance workbook/cache as mortgage tracking."""
    if current_app.config.get("LIFE_DATA_SOURCE") == "onedrive":
        cached = current_app.config.get("GRAPH_FINANCE_CACHE_PATH")
        source = cached if cached and Path(cached).is_file() else (
            current_app.config.get("SOURCE_WORKBOOK")
            if current_app.config.get("LIFE_SYNC_LOCAL_FALLBACK") else None)
    else:
        source = current_app.config.get("SOURCE_WORKBOOK")
    if not source:
        return dict(status="not_configured", history=[], projection=[],
                    message="Finance workbook not configured.")
    path = Path(str(source).strip().strip('"'))
    if not path.is_file():
        return dict(status="source_not_found", history=[], projection=[],
                    message="Finance workbook not available to the running application.")
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if "Net Worth Tracking" not in wb:
            return dict(status="unavailable", history=[], projection=[],
                        message="Net Worth Tracking worksheet not found.")
        rows = list(wb["Net Worth Tracking"].values)
        if not rows:
            return dict(status="no_data", history=[], projection=[])
        candidates = ("WBC Choice (Offset)", "Offset Balance", "Mortgage Offset")
        offset_row = next((row for row in rows if row and str(row[0] or "").strip().casefold() in
                           {v.casefold() for v in candidates}), None)
        if offset_row is None:
            return dict(status="unavailable", history=[], projection=[],
                        message="Offset account label not found in Net Worth Tracking.")
        values = []
        for col in range(1, min(len(rows[0]), len(offset_row))):
            try:
                day = parse_date(rows[0][col], wb.epoch)
                if day > date.today() or offset_row[col] is None or isinstance(offset_row[col], bool):
                    continue
                value = Decimal(str(offset_row[col]).replace("$","").replace(",",""))
                if value.is_finite():
                    values.append((day, value))
            except (ValueError, TypeError, ArithmeticError):
                continue
        return project_offset(values)
    finally:
        wb.close()
