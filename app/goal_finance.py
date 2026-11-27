"""Authoritative portfolio value series from the finance workbook subtotal."""
from datetime import date
from pathlib import Path
from flask import current_app
from openpyxl import load_workbook
from app.importer import parse_date


def investment_history(today=None):
    today = today or date.today()
    cfg=current_app.config
    source=cfg.get("SOURCE_WORKBOOK")
    if cfg.get("LIFE_DATA_SOURCE")=="onedrive":
        cache=cfg.get("GRAPH_FINANCE_CACHE_PATH")
        source=cache if cache and Path(cache).is_file() else (
            source if cfg.get("LIFE_SYNC_LOCAL_FALLBACK") else None)
    if not source:
        return []
    path=Path(str(source).strip().strip('"'))
    if not path.is_file():
        return []
    wb=load_workbook(path,read_only=True,data_only=True)
    try:
        if "Net Worth Tracking" not in wb:
            return []
        rows=list(wb["Net Worth Tracking"].values)
        if not rows:
            return []
        matches=[r for r in rows if r and str(r[0] or "").strip().casefold()=="total investments"]
        if len(matches)!=1:
            return []
        result={}
        for stamp,value in zip(rows[0][1:],matches[0][1:]):
            if value is None or isinstance(value,bool):
                continue
            try:
                d=parse_date(stamp,wb.epoch)
                v=float(value)
                if d<=today and 0<=v<1e12:
                    result[d]=v
            except (ValueError,TypeError,OverflowError):
                continue
        return sorted(result.items())
    finally:
        wb.close()
