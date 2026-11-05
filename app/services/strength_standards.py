"""Strength standards: pinned, consented movement mappings and pure scoring functions."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from flask import current_app, request, has_request_context

from app import db
from app.gymday import GymExercise, GymSession, GymSessionExercise, GymSet, bounds, e1rm
from app.services.strength_bodyweight import histories, highest_weight, weight_state

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "config" / "strength-standards" / "openprogression-v1.0.0.json"
MAPPINGS = ROOT / "config" / "strength-exercise-mapping.yaml"
TIERS = ("beginner", "beginner_plus", "intermediate", "intermediate_plus",
         "advanced", "advanced_plus", "rx")
TARGETS = (("Good", "intermediate"), ("Excellent", "advanced"), ("Elite", "rx"))
SEXES = ("male", "female")
WINDOWS = {"90d": 89, "365d": 364, "all_time": None}
SYDNEY = ZoneInfo("Australia/Sydney")


def sex_category():
    """Explicit client-selected reference profile overrides optional local .env."""
    supplied = request.args.get("sex") if has_request_context() else None
    raw = str(supplied if supplied is not None else
              current_app.config.get("STRENGTH_STANDARD_SEX") or "").strip().lower()
    if supplied is not None and raw not in SEXES:
        raise ValueError("sex must be male or female")
    return raw if raw in SEXES else None


@lru_cache(maxsize=4)
def read_benchmarks(path):
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    if content.get("provider") != "openprogression" or content.get("version") != "1.0.0":
        raise ValueError("Unsupported benchmark provider or version")
    if not content.get("source_commit") or not content.get("source_files"):
        raise ValueError("Missing pinned source provenance")
    movements = {}
    for row in content["movements"]:
        if row.get("testType") != "1rm" or row.get("unit") != "kg":
            raise ValueError("Unsupported test or units in benchmark")
        ident = row["movement"]
        if ident in movements:
            raise ValueError("Duplicate benchmark movement")
        for sex in SEXES:
            values = [row["bwMultiplier"][tier][sex] for tier in TIERS]
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v) and v > 0 for v in values):
                raise ValueError("Missing or non-positive benchmark multiplier")
            if values != sorted(values) or len(set(values)) != len(values):
                raise ValueError("Unordered benchmark tiers")
        movements[ident] = row
    if not movements:
        raise ValueError("Empty benchmark dataset")
    return content, movements


def benchmarks():
    path = current_app.config.get("STRENGTH_BENCHMARK_PATH") or SOURCE
    try:
        return read_benchmarks(str(path)), None
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return None, "Invalid or unavailable pinned benchmark dataset"


def mappings():
    path = current_app.config.get("STRENGTH_MAPPING_PATH") or MAPPINGS
    try:
        body = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(body, dict) or not isinstance(body.get("mappings"), dict):
            raise ValueError("mappings must be a dictionary")
        approved = {}
        explicit_ids = set()
        for ident, entry in body["mappings"].items():
            if not isinstance(ident, str) or not 1 <= len(ident) <= 80:
                raise ValueError("Invalid Gym Day exercise ID in mapping")
            if not isinstance(entry, dict):
                raise ValueError("Invalid ID mapping")
            explicit_ids.add(ident)
            if entry.get("approved") is not True:
                continue  # Explicit rejection blocks automatic aliases.
            if entry.get("load_convention") != "total_barbell_kg" or entry.get("benchmark_provider") != "openprogression":
                raise ValueError("Approved mapping needs provider and total_barbell_kg")
            if not isinstance(entry.get("movement"), str):
                raise ValueError("Approved mapping is missing movement ID")
            approved[ident] = entry["movement"]
        aliases = body.get("name_mappings") or {}
        if not isinstance(aliases, dict):
            raise ValueError("name_mappings must be a dictionary")
        # Only configured exact names; never substring-match or silently infer
        # Romanian/Smith/decline/single-leg/assisted or bodyweight variants.
        verified_names = {
            "Barbell Bench Press", "Barbell Squat", "Barbell Back Squat",
            "Barbell Deadlift", "Barbell Deadlifts", "Barbell Front Squat",
            "Barbell Overhead Squat", "Barbell Strict Press", "Barbell Overhead Press"}
        allowed = {"bench_press", "back_squat", "deadlift", "front_squat",
                   "overhead_squat", "strict_press"}
        if any(name not in verified_names or movement not in allowed
               for name, movement in aliases.items()):
            raise ValueError("Name mapping must use a reviewed exact barbell alias and movement")
        if aliases:
            for exercise in GymExercise.query.all():
                if exercise.id in explicit_ids or exercise.name not in aliases:
                    continue
                equipment = (exercise.equipment or "").strip().casefold()
                # A known non-barbell equipment is a hard veto. The exact
                # 'Barbell ...' name permits a blank equipment field.
                if equipment and "barbell" not in equipment:
                    continue
                approved[exercise.id] = aliases[exercise.name]
        return approved, None
    except (OSError, yaml.YAMLError, ValueError) as exc:
        return {}, "Missing or invalid strength exercise mapping configuration"


def score(one_rm, bodyweight, movement, sex, lookup):
    """Unrounded threshold decisions and next strict-higher milestone."""
    if not movement or movement not in lookup or sex not in SEXES:
        return None
    if not all(math.isfinite(v) and v > 0 for v in (one_rm, bodyweight)):
        return None
    multipliers = lookup[movement]["bwMultiplier"]
    targets = [(label, bodyweight * multipliers[tier][sex], tier) for label, tier in TARGETS]
    label = "Developing"
    for name, target, tier in targets:
        if one_rm >= target:
            label = name
    source_tier = next((tier for tier in reversed(TIERS)
                        if one_rm >= bodyweight * multipliers[tier][sex]), None)
    next_item = next(((name, target) for name, target, _ in targets if one_rm < target), None)
    return {
        "relative_strength": one_rm / bodyweight,
        "classification": {"label": label, "source_tier": source_tier,
                           "method": "source_bw_multipliers"},
        "benchmarks": {name.lower() + "_kg": round(target, 3) for name, target, _ in targets},
        "next_milestone": ({
            "label": next_item[0], "target_kg": round(next_item[1], 3),
            "gap_kg": round(max(0, next_item[1] - one_rm), 3),
            "progress_pct": round(one_rm / next_item[1] * 100, 3)
        } if next_item else None),
    }


def eligible(record):
    """Validate before using Gym Day's canonical e1rm; do not use source_onerm."""
    if not record.complete or record.warmup:
        return None
    try:
        reps = float(record.reps)
        weight = float(record.weight_kg)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (math.isfinite(reps) and math.isfinite(weight) and reps.is_integer()
            and 1 <= reps <= 10 and weight > 0):
        return None
    result = e1rm(record)
    return result if result is not None and math.isfinite(result) and result > 0 else None


def to_record(session, record, value):
    return {"date": session.local_date.isoformat(), "session_id": session.id,
            "set_id": record.id, "weight_kg": record.weight_kg, "reps": int(record.reps),
            "one_rm_kg": value,
            "one_rm_kind": "observed" if record.reps == 1 else "estimated"}


def _key(row):
    return (row["weight_kg"], row["one_rm_kg"], row["date"], row["session_id"], row["set_id"])


def selection_period():
    window = request.args.get("window", "90d")
    if window not in WINDOWS:
        raise ValueError("window must be 90d, 365d or all_time")
    today = datetime.now(SYDNEY).date()
    as_of = request.args.get("as_of")
    try:
        end = date.fromisoformat(as_of) if as_of else today
    except ValueError:
        raise ValueError("Invalid as_of (YYYY-MM-DD)")
    if end > today:
        raise ValueError("as_of cannot be in the future")
    lower, upper = bounds()
    window_lower = end - timedelta(days=WINDOWS[window]) if WINDOWS[window] is not None else None
    if window_lower:
        lower = max(lower, window_lower) if lower else window_lower
    upper = min(upper, end) if upper else end
    return {"window": window, "from": lower.isoformat() if lower else None,
            "to": upper.isoformat(), "as_of": end.isoformat()}, lower, upper, end


def session_records(start, end, exercise_id=None):
    """One bounded set query; heaviest eligible set per session/exercise, no N+1 queries."""
    q = (db.session.query(GymSession, GymSessionExercise, GymSet)
         .join(GymSessionExercise, GymSession.id == GymSessionExercise.session_id)
         .join(GymSet, GymSet.session_exercise_id == GymSessionExercise.id)
         .filter(GymSession.active.is_(True), GymSession.local_date.isnot(None),
                 GymSet.complete.is_(True), GymSet.warmup.is_(False)))
    if start:
        q = q.filter(GymSession.local_date >= start)
    if end:
        q = q.filter(GymSession.local_date <= end)
    if exercise_id:
        q = q.filter(GymSessionExercise.exercise_id == exercise_id)
    rows = q.limit(100001).all()
    if len(rows) > 100000:
        raise ValueError("Too many training sets for one standards request; narrow the dates")
    best = {}
    for session, se, s in rows:
        value = eligible(s)
        if value is None:
            continue
        key = (se.exercise_id, session.id)
        candidate = to_record(session, s, value)
        if key not in best or _key(candidate) > _key(best[key]):
            best[key] = candidate
    by_exercise = defaultdict(list)
    for (eid, _), record in best.items():
        by_exercise[eid].append(record)
    for records in by_exercise.values():
        records.sort(key=lambda r: (r["date"], r["session_id"], r["set_id"]))
    return by_exercise


def meta(period=None):
    data, error = benchmarks()
    source = data[0] if data else {}
    return {"provider": "openprogression", "provider_version": source.get("version"),
            "source_commit": source.get("source_commit"),
            "source_files": source.get("source_files", []),
            "source_dataset_date": source.get("source_dataset_date"),
            "standard_label_map_version": "1",
            "label_mapping": {"below_intermediate": "Developing",
                              "intermediate": "Good", "intermediate_plus": "Good",
                              "advanced": "Excellent", "advanced_plus": "Excellent",
                              "rx": "Elite"},
            "units": "kg", "sex_category": sex_category(),
            "source_note": "Simplified Life Dashboard categories; not population percentiles",
            "bodyweight_method": "highest_90d", "set_selection": "heaviest_load",
            "population_note": "OpenProgression reference standards; not representative gym-goer percentiles",
            "source_error": error, "as_of": period["as_of"] if period else None}


def summary_for(exercise, records, history, period, approved, source):
    sex = sex_category()
    source_data, error = source
    lookup = source_data[1] if source_data else {}
    movement = approved.get(exercise.id)
    result = {"exercise": {"id": exercise.id, "name": exercise.name,
                           "movement": movement, "rated": bool(movement in lookup and sex)},
              "period": period, "best_set": None, "bodyweight": None,
              "relative_strength": None, "classification": None, "benchmarks": None,
              "next_milestone": None, "status": "no_valid_sets", "reason": None}
    on = date.fromisoformat(period["as_of"])
    bw = highest_weight(history, on)
    if bw:
        result["bodyweight"] = {**bw, "match_type": "highest_90d"}
    # Weight provenance is useful even when the chosen exercise has no valid sets.
    if not records:
        result["reason"] = "No completed non-warmup sets with 1–10 whole reps and valid kg in the selected period"
        return result
    best = max(records, key=_key)
    result["best_set"] = best
    if bw:
        result["relative_strength"] = best["one_rm_kg"] / bw["weight_kg"]
    if not movement:
        result.update(status="unrated_exercise", reason="Exercise ID has no approved barbell mapping")
    elif not sex:
        result.update(status="configuration_required", reason="Set LIFE_STRENGTH_STANDARD_SEX to male or female")
    elif error or movement not in lookup:
        result.update(status="benchmark_unavailable", reason="Mapped movement has no verified benchmark source")
    elif not bw:
        result.update(status=weight_state(history, on),
                      reason="No valid recorded bodyweight within the preceding 90 days")
    else:
        rating = score(best["one_rm_kg"], bw["weight_kg"], movement, sex, lookup)
        result.update(rating or {})
        result["status"] = "rated"
        if period["window"] == "all_time":
            result["reason"] = "All-time heaviest set at trailing 90-day peak bodyweight (contextual only)"
    return result


def progress_for(exercise_id, records, history, approved, source):
    source_data, _ = source
    lookup = source_data[1] if source_data else {}
    sex = sex_category()
    movement = approved.get(exercise_id)
    out = []
    for record in records:
        bw = highest_weight(history, date.fromisoformat(record["date"]))
        rating = score(record["one_rm_kg"], bw["weight_kg"], movement, sex, lookup) if bw else None
        out.append({**record, "bodyweight": bw,
                    "relative_strength": record["one_rm_kg"] / bw["weight_kg"] if bw else None,
                    "classification": rating["classification"] if rating else None,
                    "status": ("rated" if rating else ("missing_bodyweight" if not bw else
                               "configuration_required" if movement and not sex else
                               "benchmark_unavailable" if movement and movement not in lookup else
                               "unrated_exercise"))})
    return out
