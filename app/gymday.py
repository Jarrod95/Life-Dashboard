"""Gym Day local ZIP analytics. All Gym Day data is read-only."""
from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, render_template, request
from sqlalchemy import or_
from app import db

SYDNEY = ZoneInfo("Australia/Sydney")
IMPORT_VERSION = "2"
gym_pages = Blueprint("gym_pages", __name__)
gym_api = Blueprint("gym_api", __name__, url_prefix="/api/v1/fitness/strength")


class GymImport(db.Model):
    __tablename__ = "gym_import_run"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    digest = db.Column(db.String(64), nullable=False, index=True)
    version = db.Column(db.String(16), nullable=False)
    started = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), nullable=False)
    counts = db.Column(db.JSON, default=dict)
    warnings = db.Column(db.JSON, default=list)


class GymSession(db.Model):
    __tablename__ = "gym_workout_session"
    id = db.Column(db.String(80), primary_key=True)
    name = db.Column(db.String(240))
    started = db.Column(db.DateTime(timezone=True))
    ended = db.Column(db.DateTime(timezone=True))
    local_date = db.Column(db.Date, index=True)
    duration = db.Column(db.Integer)
    active = db.Column(db.Boolean, default=True, nullable=False)


class GymExercise(db.Model):
    __tablename__ = "gym_exercise"
    id = db.Column(db.String(80), primary_key=True)
    name = db.Column(db.String(240), index=True)
    category = db.Column(db.String(100))
    equipment = db.Column(db.String(150))
    primary_muscles = db.Column(db.JSON, default=list)
    secondary_muscles = db.Column(db.JSON, default=list)


class GymSessionExercise(db.Model):
    __tablename__ = "gym_session_exercise"
    id = db.Column(db.String(80), primary_key=True)
    session_id = db.Column(db.String(80), db.ForeignKey("gym_workout_session.id"), nullable=False, index=True)
    exercise_id = db.Column(db.String(80), db.ForeignKey("gym_exercise.id"), nullable=False, index=True)
    position = db.Column(db.Integer)
    type = db.Column(db.String(80))


class GymSet(db.Model):
    __tablename__ = "gym_set"
    id = db.Column(db.String(80), primary_key=True)
    session_exercise_id = db.Column(db.String(80), db.ForeignKey("gym_session_exercise.id"), nullable=False, index=True)
    ordinal = db.Column(db.Integer)
    weight = db.Column(db.Float)
    unit = db.Column(db.String(40))
    weight_kg = db.Column(db.Float)
    reps = db.Column(db.Float)
    source_onerm = db.Column(db.Float)
    rest = db.Column(db.Float)
    complete = db.Column(db.Boolean, nullable=False, default=False)
    warmup = db.Column(db.Boolean, nullable=False, default=False)
    drop_set = db.Column(db.Boolean, nullable=False, default=False)
    failure = db.Column(db.Boolean, nullable=False, default=False)


def as_rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "items", "records"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def source_dir():
    configured = current_app.config.get("GYMDAY_EXPORT_DIR")
    if not configured:
        raise ValueError("Configure LIFE_GYMDAY_EXPORT_DIR first")
    return Path(str(configured).strip().strip('"'))


def archive_candidates(folder):
    if not folder.is_dir():
        raise ValueError("Gym Day export directory is unavailable")
    def rank(p):
        match = re.search(r"daily_strength_(\d{4})_(\d{2})_(\d{2})", p.name, re.I)
        try:
            d = date(*map(int, match.groups())).toordinal() if match else 0
        except ValueError:
            d = 0
        return (d, p.stat().st_mtime_ns, p.name.lower())
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".zip"), key=rank, reverse=True)


def latest_archive():
    candidates = archive_candidates(source_dir())
    if not candidates:
        raise ValueError("No Gym Day ZIP exports found")
    errors = []
    for candidate in candidates:
        try:
            with zipfile.ZipFile(candidate) as z:
                files = {PurePosixPath(n).name for n in z.namelist()}
                if not {"WorkoutSession.json", "Exercise.json"}.issubset(files):
                    raise ValueError("required entities are missing")
                if z.testzip() is not None:
                    raise ValueError("ZIP CRC validation failed")
            return candidate, errors
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            errors.append(candidate.name + ": " + str(exc))
    raise ValueError("No valid Gym Day ZIP: " + "; ".join(errors))


def member_data(z, suffix, required=False):
    names = [n for n in z.namelist() if PurePosixPath(n).name == suffix]
    if not names:
        if required:
            raise ValueError("Missing " + suffix)
        return []
    if len(names) != 1:
        raise ValueError("Duplicate archive member " + suffix)
    name = names[0]
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe archive member path")
    info = z.getinfo(name)
    if info.file_size > 80_000_000 or (info.file_size > 1_000_000 and info.file_size / max(info.compress_size, 1) > 250):
        raise ValueError("Excessive archive member expansion")
    return as_rows(json.loads(z.read(name)))


def timestamp(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


def entity_id(value):
    if isinstance(value, dict):
        return value.get("id")
    return value


def muscles(row):
    return [str(v.get("name") or v.get("id")) if isinstance(v, dict) else str(v)
            for v in (row or []) if v is not None]


def numeric(value):
    try:
        n = float(value)
        return n if abs(n) < 1e9 and n == n else None
    except (ValueError, TypeError):
        return None


def kg(value, unit):
    v = numeric(value)
    if v is None:
        return None
    u = str(unit or "").lower()
    if u in ("", "kg", "kilogram", "kilograms", "metric", "0"):
        return v if u else None
    if u in ("lb", "lbs", "pound", "pounds", "imperial", "1"):
        return v * 0.45359237
    return None


def load_zip(path):
    """Parse all relationships into dictionaries before changing persisted data."""
    with zipfile.ZipFile(path) as z:
        exercises = member_data(z, "Exercise.json", required=True)
        sessions = member_data(z, "WorkoutSession.json", required=True)
        flat_exercises = member_data(z, "WorkoutSessionExercise.json")
        flat_sets = member_data(z, "WorkoutSessionSet.json")
    dictionary = {str(e["id"]): e for e in exercises if isinstance(e, dict) and e.get("id")}
    se_by_id = {str(e["id"]): e for e in flat_exercises if isinstance(e, dict) and e.get("id")}
    sets_by_parent = defaultdict(list)
    for s in flat_sets:
        if not isinstance(s, dict):
            continue
        parent = entity_id(s.get("workoutSessionExercise") or s.get("workoutSessionExerciseId"))
        if parent:
            sets_by_parent[str(parent)].append(s)
    result = []
    seen = set()
    for session in sessions:
        if not isinstance(session, dict) or not session.get("id"):
            continue
        sid = str(session["id"])
        if sid in seen:
            raise ValueError("Duplicate session ID " + sid)
        seen.add(sid)
        linked = session.get("workoutSessionExercises")
        if linked is None:
            linked = [s for s in flat_exercises if str(entity_id(s.get("workoutSession") or s.get("workoutSessionId"))) == sid]
        children = []
        for se in as_rows(linked):
            se = se_by_id.get(str(entity_id(se)), se) if not isinstance(se, dict) else se
            if not isinstance(se, dict) or not se.get("id"):
                continue
            eid = entity_id(se.get("exercise") or se.get("exerciseId"))
            if not eid:
                continue
            eid = str(eid)
            exercise = se.get("exercise") if isinstance(se.get("exercise"), dict) else dictionary.get(eid, {"id": eid, "name": "Unknown exercise"})
            if eid not in dictionary or not dictionary[eid].get("name"):
                dictionary[eid] = exercise
            sets = se.get("workoutSessionSets")
            if sets is None:
                sets = sets_by_parent.get(str(se["id"]), [])
            children.append((se, sets or [], eid))
        result.append((session, children))
    return dictionary, result, {"source_sessions": len(sessions), "source_session_exercises": len(flat_exercises), "source_sets": len(flat_sets)}


def import_latest(force=False):
    path, warnings = latest_archive()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    previous = GymImport.query.filter_by(digest=digest, version=IMPORT_VERSION, status="success").first()
    if previous and not force:
        return {"status": "unchanged", "filename": path.name, "counts": previous.counts, "warnings": warnings}
    dictionary, sessions, counts = load_zip(path)
    run = GymImport(filename=path.name, digest=digest, version=IMPORT_VERSION,
                    status="success", warnings=warnings, counts=counts)
    try:
        for eid, e in dictionary.items():
            obj = db.session.get(GymExercise, eid) or GymExercise(id=eid)
            obj.name = e.get("name") or "Unknown exercise"
            obj.category = str(e.get("category") or "")
            equipment = e.get("equipmentRequired")
            obj.equipment = ", ".join(str(x.get("name", "")) for x in equipment if isinstance(x, dict))[:150] if isinstance(equipment, list) else (str(equipment)[:150] if equipment else None)
            obj.primary_muscles = muscles(e.get("primaryMuscleGroups"))
            obj.secondary_muscles = muscles(e.get("secondaryMuscleGroups"))
            db.session.add(obj)
        session_ids = set()
        se_ids = set()
        set_ids = set()
        for raw, children in sessions:
            sid = str(raw["id"])
            session_ids.add(sid)
            started, ended = timestamp(raw.get("startDate")), timestamp(raw.get("endDate"))
            obj = db.session.get(GymSession, sid) or GymSession(id=sid)
            obj.name, obj.started, obj.ended = raw.get("name"), started, ended
            obj.local_date = started.astimezone(SYDNEY).date() if started else None
            obj.duration = int((ended - started).total_seconds()) if started and ended and ended >= started else None
            obj.active = True
            db.session.add(obj)
            for se, raw_sets, eid in children:
                se_id = str(se["id"])
                se_ids.add(se_id)
                ses = db.session.get(GymSessionExercise, se_id) or GymSessionExercise(id=se_id)
                ses.session_id, ses.exercise_id = sid, eid
                ses.position = se.get("position")
                ses.type = str(se.get("type") or "")
                db.session.add(ses)
                for ordinal, raw_set in enumerate(as_rows(raw_sets), 1):
                    if not isinstance(raw_set, dict) or not raw_set.get("id"):
                        continue
                    set_id = str(raw_set["id"])
                    if set_id in set_ids:
                        raise ValueError("Duplicate set ID " + set_id)
                    set_ids.add(set_id)
                    item = db.session.get(GymSet, set_id) or GymSet(id=set_id)
                    item.session_exercise_id = se_id
                    item.ordinal = raw_set.get("set") if isinstance(raw_set.get("set"), int) else ordinal
                    item.weight, item.reps = numeric(raw_set.get("weight")), numeric(raw_set.get("reps"))
                    item.unit = str(raw_set.get("measurementUnit") or "")
                    item.weight_kg = kg(item.weight, item.unit)
                    item.source_onerm = numeric(raw_set.get("oneRepMax"))
                    item.rest = numeric(raw_set.get("restTime"))
                    item.complete = raw_set.get("isComplete") is True
                    item.warmup = raw_set.get("warmUp") is True
                    item.drop_set = raw_set.get("dropSet") is True
                    item.failure = raw_set.get("untilFailure") is True
                    db.session.add(item)
        # Full valid snapshots can remove records; preserve missing sessions as inactive.
        if session_ids and len(session_ids) == counts["source_sessions"] and len(se_ids) == counts["source_session_exercises"] and len(set_ids) == counts["source_sets"]:
            GymSession.query.filter(~GymSession.id.in_(session_ids)).update({"active": False}, synchronize_session=False)
        # Remove replaced exercise/sets attached to present sessions only after complete parse.
        if se_ids:
            for old in GymSessionExercise.query.filter(GymSessionExercise.session_id.in_(session_ids), ~GymSessionExercise.id.in_(se_ids)).all():
                GymSet.query.filter_by(session_exercise_id=old.id).delete()
                db.session.delete(old)
        if set_ids:
            GymSet.query.filter(GymSet.session_exercise_id.in_(se_ids), ~GymSet.id.in_(set_ids)).delete(synchronize_session=False)
        counts.update(imported_sessions=len(session_ids), imported_session_exercises=len(se_ids), imported_sets=len(set_ids))
        if (len(session_ids), len(se_ids), len(set_ids)) != (counts["source_sessions"], counts["source_session_exercises"], counts["source_sets"]):
            raise ValueError("Nested Gym Day records do not reconcile with flat export entity counts; import rolled back")
        db.session.add(run)
        db.session.commit()
        return {"status": "success", "filename": path.name, "counts": counts, "warnings": warnings}
    except Exception:
        db.session.rollback()
        raise


def bounds():
    args = request.args
    try:
        year = int(args["year"]) if args.get("year") else None
        month = int(args["month"]) if args.get("month") and args["month"] != "all" else None
        start = date.fromisoformat(args["from"]) if args.get("from") else None
        end = date.fromisoformat(args["to"]) if args.get("to") else None
    except (ValueError, OverflowError):
        raise ValueError("Invalid year, month or date (YYYY-MM-DD)")
    if year is not None and not 1900 <= year <= 2200:
        raise ValueError("Year out of range")
    if month is not None and not 1 <= month <= 12:
        raise ValueError("Month must be between 1 and 12")
    if month and year is None:
        raise ValueError("Month requires year")
    if year:
        start = max(filter(None, [start, date(year, month or 1, 1)]))
        upper = date(year + 1, 1, 1) - timedelta(days=1) if month is None else (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
        end = min(filter(None, [end, upper]))
    if start and end and start > end:
        raise ValueError("Invalid date range")
    return start, end


def base_sessions():
    start, end = bounds()
    q = GymSession.query.filter_by(active=True)
    if start:
        q = q.filter(GymSession.local_date >= start)
    if end:
        q = q.filter(GymSession.local_date <= end)
    name = request.args.get("workout")
    if name:
        q = q.filter(GymSession.name.ilike("%" + name + "%"))
    return q


def joined_rows():
    q = db.session.query(GymSession, GymSessionExercise, GymExercise, GymSet).join(
        GymSessionExercise, GymSession.id == GymSessionExercise.session_id).join(
        GymExercise, GymExercise.id == GymSessionExercise.exercise_id).join(
        GymSet, GymSet.session_exercise_id == GymSessionExercise.id).filter(GymSession.active.is_(True))
    start, end = bounds()
    if start:
        q = q.filter(GymSession.local_date >= start)
    if end:
        q = q.filter(GymSession.local_date <= end)
    if request.args.get("exercise"):
        q = q.filter(GymExercise.id == request.args["exercise"])
    if request.args.get("muscle"):
        # Exact relationship membership checked after retrieval; avoids substring match.
        muscle = request.args["muscle"]
        q = q.filter(or_(GymExercise.primary_muscles.contains(muscle),
                            GymExercise.secondary_muscles.contains(muscle)))
    return q.all()


def e1rm(s):
    if s.weight_kg is None or s.weight_kg <= 0 or s.reps is None or not 1 <= s.reps <= 10:
        return None
    return s.weight_kg if s.reps == 1 else s.weight_kg * (1 + s.reps / 30)


def set_volume(s):
    if not s.complete or s.warmup or s.weight_kg is None or s.reps is None or s.weight_kg < 0 or s.reps < 0:
        return 0
    return s.weight_kg * s.reps


def overview_data():
    sessions = base_sessions().all()
    rows = joined_rows()
    working = [(s, e, x) for s, _, e, x in rows if x.complete and not x.warmup]
    days = {s.local_date for s in sessions if s.local_date}
    duration = [s.duration for s in sessions if s.duration is not None]
    freq = Counter(str(s.local_date.isocalendar().year) + "-W" + str(s.local_date.isocalendar().week).zfill(2)
                   for s in sessions if s.local_date)
    muscles = Counter()
    exercise_counts = Counter()
    for _, e, x in working:
        exercise_counts[e.name] += 1
        for m in e.primary_muscles or []:
            muscles[m] += 1
    return dict(kpis=dict(sessions=len(sessions), training_days=len(days),
                          hours=round(sum(duration)/3600, 1),
                          avg_minutes=round(sum(duration)/len(duration)/60, 1) if duration else None,
                          working_sets=len(working), reps=sum(x.reps or 0 for _, _, x in working),
                          volume_kg=round(sum(set_volume(x) for _, _, x in working), 1),
                          exercises=len({e.id for _, e, _ in working})),
                weekly=[{"week": k, "count": v} for k, v in sorted(freq.items())],
                muscles=[{"name": k, "sets": v} for k, v in muscles.most_common()],
                top_exercises=[{"name": k, "sets": v} for k, v in exercise_counts.most_common(20)],
                calendar=[{"date": d.isoformat(), "sessions": sum(s.local_date == d for s in sessions)} for d in sorted(days)])


def serial_session(s):
    return dict(id=s.id, name=s.name, date=s.local_date.isoformat() if s.local_date else None,
                duration_seconds=s.duration, started=s.started.isoformat() if s.started else None)


def serial_set(s):
    return dict(id=s.id, ordinal=s.ordinal, weight=s.weight, unit=s.unit,
                weight_kg=s.weight_kg, reps=s.reps, e1rm=e1rm(s), complete=s.complete,
                warmup=s.warmup, drop_set=s.drop_set, failure=s.failure)


@gym_api.errorhandler(ValueError)
def invalid(exc):
    return jsonify(error={"code": "validation_error", "message": str(exc)}), 400


@gym_api.get("/overview")
def api_overview():
    return jsonify(data=overview_data(), meta={"timezone": "Australia/Sydney"})


@gym_api.get("/weekly-frequency")
def api_frequency():
    return jsonify(data=overview_data()["weekly"])


@gym_api.get("/muscles")
def api_muscles():
    role = request.args.get("role", "primary")
    if role not in ("primary", "secondary"):
        raise ValueError("role must be primary or secondary")
    tally = Counter()
    for _, _, e, s in joined_rows():
        if s.complete and not s.warmup:
            for name in (e.primary_muscles if role == "primary" else e.secondary_muscles) or []:
                tally[name] += 1
    return jsonify(data=[{"name": k, "sets": v} for k, v in tally.most_common()])


@gym_api.get("/volume")
def api_volume():
    group = request.args.get("group_by", "week")
    if group not in ("week", "month"):
        raise ValueError("group_by must be week or month")
    buckets = defaultdict(float)
    for session, _, _, s in joined_rows():
        if session.local_date:
            d = session.local_date
            key = d.strftime("%Y-%m") if group == "month" else f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
            buckets[key] += set_volume(s)
    return jsonify(data=[{"period": k, "volume_kg": round(v, 1)} for k, v in sorted(buckets.items())])


@gym_api.get("/calendar")
def api_calendar():
    """One requested Sydney-local month, with complete sessions and measured tonnage."""
    try:
        year = int(request.args["year"])
        month = int(request.args["month"])
        first = date(year, month, 1)
        last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    except (KeyError, ValueError, OverflowError):
        raise ValueError("Calendar requires valid year and month")
    if not 1900 <= year <= 2200:
        raise ValueError("Year out of range")
    sessions = GymSession.query.filter(
        GymSession.active.is_(True),
        GymSession.local_date >= first,
        GymSession.local_date <= last,
    ).order_by(GymSession.started, GymSession.id).all()
    ids = [s.id for s in sessions]
    volumes = defaultdict(float)
    if ids:
        rows = db.session.query(GymSessionExercise.session_id, GymSet).join(
            GymSet, GymSet.session_exercise_id == GymSessionExercise.id
        ).filter(GymSessionExercise.session_id.in_(ids)).all()
        for sid, row in rows:
            volumes[sid] += set_volume(row)
    days = defaultdict(list)
    for session in sessions:
        days[session.local_date.isoformat()].append({
            "id": session.id,
            "name": session.name or "Workout",
            "volume_kg": round(volumes[session.id], 1),
        })
    return jsonify(data={
        "year": year, "month": month,
        "days": [{"date": day, "sessions": entries,
                  "total_volume_kg": round(sum(s["volume_kg"] for s in entries), 1)}
                 for day, entries in sorted(days.items())],
    }, meta={"timezone": "Australia/Sydney", "volume_definition": "completed non-warmup external kg x reps"})


@gym_api.get("/sessions")
def api_sessions():
    page, size = pagination()
    q = base_sessions().order_by(GymSession.started.desc())
    total = q.count()
    return jsonify(data=[serial_session(s) for s in q.offset((page-1)*size).limit(size)],
                   meta=dict(page=page, page_size=size, total=total))


@gym_api.get("/sessions/<session_id>")
def api_session(session_id):
    s = db.session.get(GymSession, session_id)
    if s is None or not s.active:
        return jsonify(error={"message": "Session not found"}), 404
    children = []
    for se in GymSessionExercise.query.filter_by(session_id=s.id).order_by(GymSessionExercise.position):
        e = db.session.get(GymExercise, se.exercise_id)
        children.append(dict(id=se.id, exercise_id=se.exercise_id, name=e.name if e else "Unknown",
                             sets=[serial_set(x) for x in GymSet.query.filter_by(session_exercise_id=se.id).order_by(GymSet.ordinal)]))
    return jsonify(data=dict(**serial_session(s), exercises=children))


def pagination():
    try:
        page, size = int(request.args.get("page", 1)), int(request.args.get("page_size", 25))
    except ValueError:
        raise ValueError("Invalid pagination")
    if page < 1 or size < 1 or size > 200:
        raise ValueError("page >= 1 and 1 <= page_size <= 200 required")
    return page, size


@gym_api.get("/exercises")
def api_exercises():
    page, size = pagination()
    q = GymExercise.query
    if request.args.get("q"):
        q = q.filter(GymExercise.name.ilike("%" + request.args["q"] + "%"))
    sort = request.args.get("sort", "name")
    if sort not in ("name", "category"):
        raise ValueError("Unsupported sort field")
    column = getattr(GymExercise, sort)
    q = q.order_by(column.desc() if request.args.get("order") == "desc" else column.asc())
    total = q.count()
    return jsonify(data=[dict(id=e.id, name=e.name, category=e.category,
                              primary_muscles=e.primary_muscles, equipment=e.equipment)
                         for e in q.offset((page-1)*size).limit(size)],
                   meta=dict(page=page, page_size=size, total=total))


@gym_api.get("/exercises/<exercise_id>/progress")
def api_progress(exercise_id):
    e = db.session.get(GymExercise, exercise_id)
    if e is None:
        return jsonify(error={"message": "Exercise not found"}), 404
    metric = request.args.get("metric", "e1rm")
    if metric not in ("e1rm", "weight", "reps", "volume", "sets"):
        raise ValueError("Unsupported metric")
    data = defaultdict(list)
    for session, se, _, s in joined_rows():
        if se.exercise_id == exercise_id and s.complete and not s.warmup and session.local_date:
            data[session.id].append((session, s))
    out = []
    for group in data.values():
        day = group[0][0].local_date.isoformat()
        sets = [s for _, s in group]
        vals = {"e1rm": [e1rm(x) for x in sets], "weight": [x.weight_kg for x in sets],
                "reps": [x.reps for x in sets],
                "volume": [sum(set_volume(x) for x in sets)],
                "sets": [len(sets)]}[metric]
        vals = [x for x in vals if x is not None]
        if vals:
            out.append(dict(date=day, session_id=group[0][0].id,
                            value=round(max(vals), 2)))
    return jsonify(data=sorted(out, key=lambda x: (x["date"], x["session_id"])),
                   meta=dict(exercise=e.name, metric=metric))


@gym_api.get("/exercises/<exercise_id>/sets")
def api_exercise_sets(exercise_id):
    if db.session.get(GymExercise, exercise_id) is None:
        return jsonify(error={"message": "Exercise not found"}), 404
    page, size = pagination()
    q = db.session.query(GymSession, GymSet).join(GymSessionExercise, GymSession.id == GymSessionExercise.session_id).join(GymSet, GymSet.session_exercise_id == GymSessionExercise.id).filter(
        GymSessionExercise.exercise_id == exercise_id, GymSession.active.is_(True))
    start, end = bounds()
    if start:
        q = q.filter(GymSession.local_date >= start)
    if end:
        q = q.filter(GymSession.local_date <= end)
    total = q.count()
    entries = q.order_by(GymSession.started.desc(), GymSet.ordinal).offset((page-1)*size).limit(size).all()
    return jsonify(data=[dict(date=s.local_date.isoformat() if s.local_date else None, session_id=s.id, **serial_set(x)) for s, x in entries],
                   meta=dict(page=page, page_size=size, total=total))


@gym_api.get("/records")
def api_records():
    # Chronological improvements only, excluding ties. A single session can yield one PR.
    best = {}
    prs = []
    rows = sorted(joined_rows(), key=lambda row: (row[0].started.replace(tzinfo=None) if row[0].started else datetime.min, row[3].ordinal or 0))
    for session, _, e, s in rows:
        value = e1rm(s) if s.complete and not s.warmup else None
        if value is not None and value > best.get(e.id, 0):
            improvement = value - best[e.id] if e.id in best else None
            best[e.id] = value
            prs.append(dict(exercise_id=e.id, exercise=e.name, date=session.local_date.isoformat() if session.local_date else None,
                            weight_kg=s.weight_kg, reps=s.reps, e1rm=round(value, 2),
                            improvement=round(improvement, 2) if improvement is not None else None))
    return jsonify(data=prs[-500:][::-1], meta={"metric": "estimated_1rm", "limited": len(prs) > 500})


@gym_api.get("/imports/status")
def api_status():
    latest = GymImport.query.order_by(GymImport.id.desc()).first()
    try:
        archive, warnings = latest_archive()
        discovery = dict(filename=archive.name, warnings=warnings)
    except (OSError, ValueError) as exc:
        discovery = dict(error=str(exc))
    return jsonify(data=dict(latest=dict(filename=latest.filename, status=latest.status,
                                        counts=latest.counts, warnings=latest.warnings)
                             if latest else None, discovery=discovery))


@gym_api.post("/imports/refresh")
def api_refresh():
    # Same-origin CSRF is enforced globally; never accept client-supplied paths.
    if not request.is_json and request.content_length:
        return jsonify(error={"message": "JSON request expected"}), 400
    try:
        return jsonify(data=import_latest())
    except (ValueError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        return jsonify(error={"message": str(exc)}), 400


@gym_pages.get("/fitness/strength")
@gym_pages.get("/fitness/strength/exercises")
@gym_pages.get("/fitness/strength/exercises/<exercise_id>")
@gym_pages.get("/fitness/strength/history")
@gym_pages.get("/fitness/strength/sessions/<session_id>")
@gym_pages.get("/fitness/strength/records")
@gym_pages.get("/fitness/strength/data")
def strength_page(exercise_id=None, session_id=None):
    return render_template("strength.html", title="Strength training", section="strength")
