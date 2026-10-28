"""Read-only MyFitnessPal CSV analytics from a local sandbox-scripts checkout."""
from __future__ import annotations
import csv
import os
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from flask import Blueprint, current_app, jsonify, render_template, request

mfp_pages = Blueprint("mfp_pages", __name__)
mfp_api = Blueprint("mfp_api", __name__, url_prefix="/api/v1/fitness/mfp")
FILES = {"weight": "myfitnesspal_weight_history.csv", "daily": "mfp_2026_apr_oct_daily.csv",
         "foods": "mfp_2026_apr_oct_foods.csv", "meals": "mfp_2026_apr_oct_meals.csv"}
NUMBERS = {"weight_kg", "calories", "carbs_g", "fat_g", "protein_g", "sodium_mg", "sugar_g",
           "goal_calories", "remaining_calories", "food_entries", "summed_food_calories", "calorie_difference"}
_cache = {}


def source_dir():
    configured = current_app.config.get("MFP_DATA_DIR")
    if configured:
        return Path(str(configured).strip().strip('"')).expanduser()
    # Conventional checkout path. Environment setting wins for other layouts.
    return Path.home() / "OneDrive" / "Documents" / "Codebases" / "sandbox-scripts" / "fitness_health" / "myfitnesspal" / "data"


def load(kind):
    if kind not in FILES:
        raise ValueError("Unsupported dataset")
    path = source_dir() / FILES[kind]
    if not path.is_file():
        raise FileNotFoundError(f"Missing {FILES[kind]}; configure LIFE_MFP_DATA_DIR to the local CSV directory")
    stamp = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
    cached = _cache.get(kind)
    if cached and cached[0] == stamp:
        return cached[1]
    if path.stat().st_size > 50_000_000:
        raise ValueError("CSV exceeds 50 MB safety limit")
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        expected = {"weight": {"date", "weight_kg"}, "daily": {"date", "calories", "protein_g"},
                    "foods": {"date", "meal", "food", "calories"}, "meals": {"date", "meal", "calories"}}[kind]
        if not expected.issubset(reader.fieldnames or []):
            raise ValueError(f"{FILES[kind]} is missing required columns")
        for row in reader:
            try:
                day = date.fromisoformat(row["date"])
            except (ValueError, TypeError):
                continue
            clean = {"date": day.isoformat()}
            for key, value in row.items():
                if key == "date":
                    continue
                if key in NUMBERS:
                    try:
                        clean[key] = float(value) if value not in (None, "") else None
                    except ValueError:
                        clean[key] = None
                else:
                    clean[key] = value
            rows.append(clean)
    _cache[kind] = (stamp, rows)
    return rows


def filters():
    start = request.args.get("from")
    end = request.args.get("to")
    year = request.args.get("year")
    month = request.args.get("month")
    try:
        start = date.fromisoformat(start) if start else None
        end = date.fromisoformat(end) if end else None
        if year:
            y = int(year)
            if y < 1900 or y > 2200:
                raise ValueError()
            m = int(month) if month and month != "all" else None
            if m and m not in range(1, 13):
                raise ValueError()
            lower = date(y, m or 1, 1)
            upper = date(y + (m == 12), (m % 12 + 1) if m else 1, 1) - timedelta(days=1) if m else date(y, 12, 31)
            start = max(start, lower) if start else lower
            end = min(end, upper) if end else upper
        elif month and month != "all":
            raise ValueError()
    except (ValueError, OverflowError):
        raise ValueError("Invalid date filters")
    if start and end and start > end:
        raise ValueError("from must be on or before to")
    return start, end


def filtered(kind):
    start, end = filters()
    rows = load(kind)
    return [r for r in rows if (not start or r["date"] >= start.isoformat())
            and (not end or r["date"] <= end.isoformat())]


def avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def round_or_none(v):
    return round(v, 2) if v is not None else None


@mfp_api.errorhandler(ValueError)
def bad_filter(e):
    return jsonify(error={"message": str(e)}), 400


@mfp_api.errorhandler(FileNotFoundError)
def missing(e):
    return jsonify(error={"message": str(e)}), 404


@mfp_api.get("/weight")
def weight_api():
    data = sorted(filtered("weight"), key=lambda r: r["date"])
    values = [r for r in data if r.get("weight_kg") is not None]
    weights = [r["weight_kg"] for r in values]
    trend = []
    for i, row in enumerate(values):
        recent = weights[max(0, i-6):i+1]
        trend.append({"date": row["date"], "weight_kg": row["weight_kg"], "rolling_7": avg(recent)})
    summary = {"entries": len(values), "first_kg": weights[0] if weights else None,
               "latest_kg": weights[-1] if weights else None,
               "min_kg": min(weights) if weights else None,
               "max_kg": max(weights) if weights else None,
               "average_kg": avg(weights),
               "change_kg": round(weights[-1] - weights[0], 2) if len(weights) > 1 else None}
    months = defaultdict(list)
    for r in values:
        months[r["date"][:7]].append(r["weight_kg"])
    return jsonify(data={"summary": summary, "history": trend,
                         "monthly": [{"month": m, "average_kg": avg(v), "min_kg": min(v), "max_kg": max(v)}
                                     for m, v in sorted(months.items())]},
                   meta={"source": FILES["weight"], "unit": "kg"})


@mfp_api.get("/food")
def food_api():
    daily = sorted(filtered("daily"), key=lambda r: r["date"])
    foods = filtered("foods")
    meals = filtered("meals")
    meal = request.args.get("meal", "")
    query = request.args.get("q", "").lower().strip()
    if meal:
        foods = [r for r in foods if (r.get("meal") or "").lower() == meal.lower()]
        meals = [r for r in meals if (r.get("meal") or "").lower() == meal.lower()]
    if query:
        foods = [r for r in foods if query in (r.get("food") or "").lower()]
    metrics = ["calories", "protein_g", "carbs_g", "fat_g", "sodium_mg", "sugar_g"]
    # A day with zero entries is not a confirmed zero-calorie consumption day.
    logged = [r for r in daily if (r.get("food_entries") or 0) > 0]
    summary = {"calendar_days": len(daily), "logged_days": len(logged),
               "total_entries": len(filtered("foods")),
               **{"avg_" + k: avg([r.get(k) for r in logged]) for k in metrics}}
    by_meal = defaultdict(lambda: defaultdict(float))
    for row in meals:
        for k in metrics:
            by_meal[row["meal"]][k] += row.get(k) or 0
    top = defaultdict(lambda: {"count": 0, "calories": 0.0, "protein_g": 0.0})
    for r in foods:
        item = top[r.get("food") or "Unnamed food"]
        item["count"] += 1
        item["calories"] += r.get("calories") or 0
        item["protein_g"] += r.get("protein_g") or 0
    try:
        page = int(request.args.get("page", 1))
        size = int(request.args.get("page_size", 100))
    except ValueError:
        raise ValueError("Invalid pagination")
    if page < 1 or not 1 <= size <= 200:
        raise ValueError("page >= 1 and page_size must be 1–200")
    foods.sort(key=lambda r: (r["date"], r.get("meal") or "", r.get("food") or ""), reverse=True)
    return jsonify(data={"summary": summary, "daily": daily, "meals": [
        {"meal": k, **{metric: round(v.get(metric, 0), 2) for metric in metrics}} for k, v in sorted(by_meal.items())],
        "top_foods": [{"food": name, **values} for name, values in
                      sorted(top.items(), key=lambda x: x[1]["count"], reverse=True)[:30]],
        "entries": foods[(page-1)*size:page*size]},
        meta={"total": len(foods), "page": page, "page_size": size, "source": "local MyFitnessPal CSV exports",
              "note": "Averages exclude unlogged days; food table is filtered by meal/search."})


@mfp_api.get("/status")
def status_api():
    folder = source_dir()
    return jsonify(data={"configured": current_app.config.get("MFP_DATA_DIR") is not None,
                         "files": [{"name": v, "available": (folder / v).is_file()} for v in FILES.values()]})


@mfp_pages.get("/fitness/weight")
@mfp_pages.get("/fitness/food-diary")
def page():
    is_weight = request.path.endswith("weight")
    return render_template("mfp.html", title="Weight history" if is_weight else "Food diary",
                           section="mfp-weight" if is_weight else "mfp-food", view="weight" if is_weight else "food")
