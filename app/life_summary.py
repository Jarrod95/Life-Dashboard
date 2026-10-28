"""Bounded read-only summaries of existing Gym Day and MyFitnessPal sources."""
from datetime import date, timedelta
from sqlalchemy import func

from app import db

def other_sources():
    result = {}
    try:
        from app.gymday import GymSession, GymSessionExercise, GymSet
        end = date.today()
        start = end - timedelta(days=29)
        sessions = GymSession.query.filter(
            GymSession.active.is_(True), GymSession.local_date >= start,
            GymSession.local_date <= end).all()
        ids = [s.id for s in sessions]
        volume = None
        if ids:
            value = db.session.query(func.sum(GymSet.weight_kg * GymSet.reps)).join(
                GymSessionExercise, GymSet.session_exercise_id == GymSessionExercise.id).filter(
                    GymSessionExercise.session_id.in_(ids), GymSet.complete.is_(True),
                    GymSet.warmup.is_(False), GymSet.weight_kg.isnot(None),
                    GymSet.reps.isnot(None)).scalar()
            volume = round(float(value), 1) if value is not None else None
        result["strength"] = {"status": "ready", "workouts_30d": len(sessions),
                              "volume_kg_30d": volume,
                              "last_workout": max((s.local_date.isoformat() for s in sessions), default=None)}
    except Exception:
        result["strength"] = {"status": "unavailable"}
    try:
        from app.mfp import load, nutrition_goals
        daily = load("daily")
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=29)).isoformat()
        logged = [r for r in daily if start <= r["date"] <= end and (r.get("food_entries") or 0) > 0]
        def average(field):
            values = [r[field] for r in logged if r.get(field) is not None]
            return round(sum(values)/len(values), 1) if values else None
        result["nutrition"] = {"status": "ready", "logged_days_30d": len(logged),
                               "average_calories": average("calories"),
                               "average_protein_g": average("protein_g"),
                               "goals": nutrition_goals(),
                               "last_logged": max((r["date"] for r in logged), default=None)}
    except Exception:
        result["nutrition"] = {"status": "unavailable"}
    try:
        from app.mfp import load
        weights = sorted((r for r in load("weight") if r.get("weight_kg") is not None),key=lambda r:r["date"])
        if weights:
            last=weights[-1]
            earlier=[r for r in weights[:-1] if r["date"] >= (date.fromisoformat(last["date"])-timedelta(days=30)).isoformat()]
            result["weight"]={"status":"ready","latest_kg":last["weight_kg"],
                              "date":last["date"],
                              "change_30d_kg":round(last["weight_kg"]-earlier[0]["weight_kg"],2) if earlier else None}
        else:
            result["weight"]={"status":"unavailable"}
    except Exception:
        result["weight"]={"status":"unavailable"}
    return result
