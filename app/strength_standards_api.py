"""Read-only Strength Standards API, using the existing Gym Day data model."""
from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, jsonify, request

from app import db
from app.gymday import GymExercise
from app.services import strength_standards as standards
from app.services.strength_bodyweight import histories

api = Blueprint("strength_standards_api", __name__,
                url_prefix="/api/v1/fitness/strength/standards")


@api.errorhandler(ValueError)
def invalid(exc):
    return jsonify(error={"code": "validation_error", "message": str(exc)}), 400


def _exercise(exercise_id):
    if not exercise_id or len(exercise_id) > 80:
        raise ValueError("Invalid exercise_id")
    return db.session.get(GymExercise, exercise_id)


def _context():
    period, lower, upper, _ = standards.selection_period()
    approved, mapping_error = standards.mappings()
    source = standards.benchmarks()
    return period, lower, upper, approved, mapping_error, source


def _catalog(approved, source, records):
    lookup = source[0][1] if source[0] else {}
    sex = standards.sex_category()
    result = []
    for exercise in GymExercise.query.order_by(GymExercise.name, GymExercise.id).all():
        movement = approved.get(exercise.id)
        if not records.get(exercise.id) and not movement:
            continue
        rated = bool(movement and movement in lookup and sex and records.get(exercise.id))
        result.append({"id": exercise.id, "name": exercise.name, "equipment": exercise.equipment,
                       "movement": movement, "rated": rated,
                       "group": "Rated exercises" if rated else "Unrated exercises",
                       "eligible_sessions": len(records.get(exercise.id, [])),
                       "coverage": ("rated" if rated else
                                    "no_valid_sets" if not records.get(exercise.id) else
                                    "configuration_required" if movement and not sex else
                                    "benchmark_unavailable" if movement and movement not in lookup else
                                    "unrated_exercise")})
    result.sort(key=lambda r: (not r["rated"], not bool(r["eligible_sessions"]), r["name"].casefold(), r["id"]))
    return result


@api.get("/metadata")
def metadata():
    source, _ = standards.benchmarks()
    mapped, map_error = standards.mappings()
    info = standards.meta()
    history = histories()
    weight_source_status = {"mfp": "available" if history["mfp"] else "unavailable",
                            "manual": "available" if history["manual"] else "unavailable",
                            "diagnostics": history["diagnostics"]}
    return jsonify(data={**info, "weight_sources": weight_source_status, "supported_movements": (
        [{"id": k, "name": v["name"]} for k, v in source[1].items()] if source else []),
        "mapping_count": len(mapped), "mapping_error": map_error,
        "license": "MIT — Copyright (c) 2026 OpenProgression",
        "source_url": "https://github.com/OpenProgression/openprogression",
        "mapping_instruction": ("Exact barbell names from the approved name_mappings list "
                                "are recognised, unless overridden by an explicit ID. "
                                "Other exercises require verified immutable IDs in "
                                "config/strength-exercise-mapping.yaml.")})


@api.get("/exercises")
def exercises():
    period, start, end, approved, map_error, source = _context()
    # Eligible sessions must match the selected range; older sessions should not
    # make an empty current-period exercise look populated.
    rows = standards.session_records(start, end)
    query = request.args.get("q", "").strip().casefold()
    if len(query) > 100:
        raise ValueError("Search query too long")
    result = _catalog(approved, source, rows)
    if query:
        result = [r for r in result if query in r["name"].casefold()]
    return jsonify(data=result, meta={**standards.meta(period), "mapping_error": map_error})


@api.get("/summary")
def summary():
    ident = request.args.get("exercise_id", "")
    exercise = _exercise(ident)
    if exercise is None:
        return jsonify(error={"message": "Exercise not found"}), 404
    period, start, end, approved, _, source = _context()
    rows = standards.session_records(start, end, exercise.id)
    result = standards.summary_for(exercise, rows.get(exercise.id, []),
                                   histories(), period, approved, source)
    return jsonify(data=result, meta=standards.meta(period))


@api.get("/exercises/<exercise_id>/progress")
def progress(exercise_id):
    exercise = _exercise(exercise_id)
    if exercise is None:
        return jsonify(error={"message": "Exercise not found"}), 404
    period, start, end, approved, _, source = _context()
    grouped = standards.session_records(start, end, exercise.id)
    points = standards.progress_for(exercise.id, grouped.get(exercise.id, []),
                                    histories(), approved, source)
    return jsonify(data=points, meta={**standards.meta(period), "period": period,
                                      "exercise_id": exercise.id})


def _comparison_rows():
    period, start, end, approved, _, source = _context()
    grouped = standards.session_records(start, end)
    history = histories()
    catalog = _catalog(approved, source, grouped)
    # Already one bounded join for all sessions and one MFP/manual pass.
    by_id = {exercise.id: exercise for exercise in GymExercise.query.all()}
    rows = []
    for entry in catalog:
        exercise = by_id[entry["id"]]
        item = standards.summary_for(exercise, grouped.get(exercise.id, []),
                                     history, period, approved, source)
        rows.append({
            "exercise_id": exercise.id, "exercise": exercise.name,
            "movement": entry["movement"], "rated": item["status"] == "rated",
            "best_set": item["best_set"], "one_rm_kg": (
                item["best_set"]["one_rm_kg"] if item["best_set"] else None),
            "bodyweight_kg": (item["bodyweight"] or {}).get("weight_kg"),
            "bodyweight_source": (item["bodyweight"] or {}).get("source"),
            "bodyweight_date": (item["bodyweight"] or {}).get("date"),
            "ratio": item["relative_strength"],
            "classification": (item["classification"] or {}).get("label"),
            "next_target_kg": (item["next_milestone"] or {}).get("target_kg"),
            "gap_kg": (item["next_milestone"] or {}).get("gap_kg"),
            "last_record": max((r["date"] for r in grouped.get(exercise.id, [])), default=None),
            "status": item["status"], "reason": item["reason"],
        })
    rows.sort(key=lambda r: (not r["rated"], r["exercise"].casefold(), r["exercise_id"]))
    return rows, period


@api.get("/comparison")
def comparison():
    try:
        page = int(request.args.get("page", "1"))
        size = int(request.args.get("page_size", "100"))
    except ValueError:
        raise ValueError("Invalid pagination values")
    if page < 1 or not 1 <= size <= 200:
        raise ValueError("page >= 1 and page_size between 1 and 200 required")
    rows, period = _comparison_rows()
    return jsonify(data=rows[(page-1)*size:page*size],
                   meta={**standards.meta(period), "total": len(rows), "page": page,
                         "page_size": size, "period": period})


def _csv_safe(value):
    text = str(value if value is not None else "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text


@api.get("/comparison.csv")
def comparison_csv():
    rows, period = _comparison_rows()
    provenance = standards.meta(period)
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    fields = ["exercise_id", "exercise", "movement", "best_set", "one_rm_kg",
              "bodyweight_kg", "bodyweight_source", "bodyweight_date", "ratio",
              "classification", "next_target_kg", "gap_kg", "last_record", "status",
              "reason", "provider", "provider_version", "source_dataset_date",
              "source_commit", "as_of"]
    writer.writerow(fields)
    for row in rows:
        record = row["best_set"] or {}
        values = {**row, "best_set": (
            f"{record.get('weight_kg')} kg x {record.get('reps')}" if record else ""),
            "provider": provenance["provider"], "provider_version": provenance["provider_version"],
            "source_dataset_date": provenance["source_dataset_date"],
            "source_commit": provenance["source_commit"],
            "as_of": period["as_of"]}
        writer.writerow([_csv_safe(values.get(key)) for key in fields])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="strength-standards.csv"',
                             "Cache-Control": "no-store"})
