"""Strength scoring and bodyweight matching: synthetic data only."""
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.gymday import GymSet, SYDNEY, timestamp
from app.services.strength_bodyweight import highest_weight, match_weight, normalize, valid_weight, weight_state
from app.services.strength_standards import (
    SOURCE, TIERS, eligible, read_benchmarks, score,
)


def git_blob_sha(data: bytes) -> str:
    """Git stores LF blobs; Windows checkout may convert those bytes to CRLF.

    Normalize only line endings, not JSON semantics or arbitrary whitespace,
    so changing a benchmark threshold still fails the pinned-content test.
    """
    canonical = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(canonical)).encode("ascii")
                        + b"\x00" + canonical).hexdigest()


def test_blob_verification_is_checkout_newline_independent():
    content = b'{\n  "example": 1\n}\n'
    assert git_blob_sha(content) == git_blob_sha(content.replace(b"\n", b"\r\n"))
    assert git_blob_sha(content) != git_blob_sha(content.replace(b"1", b"2"))


@pytest.fixture(scope="module")
def source():
    return read_benchmarks(str(SOURCE))[1]


def test_source_is_pinned_and_complete(source):
    doc, movements = read_benchmarks(str(SOURCE))
    raw = Path(SOURCE).read_bytes()
    assert git_blob_sha(raw) == "666475c049f989700409fa3863fbd1074dd7193a"
    assert doc["version"] == "1.0.0"
    assert doc["source_commit"] == "1e9ead0019bd064e263fa0e42e583c66d9f06c6e"
    assert {r["movement"] for r in doc["movements"]} == set(movements)
    assert set(movements) == {
        "back_squat", "front_squat", "overhead_squat",
        "bench_press", "strict_press", "deadlift"}
    assert len(doc["source_files"]) == 3
    assert all(len(f["git_blob_sha1"]) == 40 for f in doc["source_files"])
    assert (movements["back_squat"]["bwMultiplier"]["advanced"]["male"]) == 1.63
    for row in movements.values():
        for sex in ("male", "female"):
            values = [row["bwMultiplier"][tier][sex] for tier in TIERS]
            assert all(v > 0 for v in values)
            assert values == sorted(set(values))


@pytest.mark.parametrize("field", ["weight_kg", "reps", "complete", "warmup"])
def test_invalid_working_sets_rejected(field):
    row = GymSet(id="set-a", weight_kg=150, reps=5, complete=True, warmup=False)
    bad = {"weight_kg": 0, "reps": 11, "complete": False, "warmup": True}
    setattr(row, field, bad[field])
    assert eligible(row) is None


@pytest.mark.parametrize("weight,reps", [
    (-1, 5), (float("nan"), 5), (float("inf"), 5), (10, 0), (10, 11),
    (150, 5.5), (150, float("nan")), (150, float("inf"))
])
def test_unusable_loads_and_reps(weight, reps):
    row = GymSet(id="bad", weight_kg=weight, reps=reps, complete=True, warmup=False)
    assert eligible(row) is None


def test_observed_and_epley_estimated_sets():
    one = GymSet(id="one", weight_kg=150, reps=1, complete=True, warmup=False)
    five = GymSet(id="five", weight_kg=150, reps=5, complete=True, warmup=False)
    assert eligible(one) == 150
    assert eligible(five) == 175


def test_threshold_inclusive_and_elite_cap(source):
    assert score(86.999, 87, "back_squat", "male", source)["classification"]["label"] == "Developing"
    assert score(87, 87, "back_squat", "male", source)["classification"]["label"] == "Good"
    assert score(141.81, 87, "back_squat", "male", source)["classification"]["label"] == "Excellent"
    assert score(195.75, 87, "back_squat", "male", source)["classification"]["label"] == "Elite"
    assert score(260, 87, "back_squat", "male", source)["next_milestone"] is None
    assert score(175, 87, "back_squat", "male", source)["next_milestone"]["gap_kg"] == 20.75
    assert score(175, 87, "back_squat", "male", source)["relative_strength"] == 175 / 87


def test_precision_not_rounded_for_classification(source):
    below = 87 * 1.63 - 0.00001
    assert score(below, 87, "back_squat", "male", source)["classification"]["label"] == "Good"
    above = 87 * 1.63
    assert score(above, 87, "back_squat", "male", source)["classification"]["label"] == "Excellent"


def test_simplified_source_tier_mapping(source):
    item = score(90, 87, "back_squat", "male", source)
    assert item["classification"]["label"] == "Good"
    assert item["classification"]["source_tier"] == "intermediate"
    plus = score(115, 87, "back_squat", "male", source)
    assert plus["classification"]["label"] == "Good"
    assert plus["classification"]["source_tier"] == "intermediate_plus"
    assert score(100, 87, "machine_hip_thrust", "male", source) is None


def test_invalid_benchmark_file_fails_closed(tmp_path):
    orig = Path(SOURCE).read_text()
    changed = orig.replace('"rx": {', '"wrong-tier": {')
    path = tmp_path / "bad.json"
    path.write_text(changed)
    with pytest.raises((ValueError, KeyError)):
        read_benchmarks(str(path))


def test_mfp_precedence_and_deterministic_duplicates():
    mfp = normalize([
        {"date": "2026-10-02", "weight_kg": 87},
        {"date": "2026-10-02", "weight_kg": "nan"},
        {"date": "2026-10-02", "weight_kg": 86},
    ], "mfp")
    manual = normalize([{"date": "2026-10-02", "Weight": 88}], "manual", weight_key="Weight")
    got = match_weight({"mfp": mfp, "manual": manual}, date(2026, 10, 2))
    assert got == {"date":"2026-10-02", "source":"mfp","weight_kg":86,"age_days":0}


def test_stale_mfp_manual_fallback_and_future_not_used():
    history = {"mfp": normalize([{"date":"2026-09-01","weight_kg":87},
                                  {"date":"2026-10-20","weight_kg":80}],"mfp"),
               "manual": normalize([{"date":"2026-10-01","Weight":89}],
                                   "manual",weight_key="Weight")}
    assert match_weight(history,date(2026,10,3))["source"] == "manual"
    assert match_weight(history,date(2026,9,20)) is None
    assert weight_state(history,date(2026,9,20)) == "available"
    assert match_weight({"mfp": history["mfp"],"manual":{}},date(2026,8,1)) is None


@pytest.mark.parametrize("value",[None,0,12,900,float("inf"),float("nan"),"unknown",True])
def test_reject_implausible_weight(value):
    assert valid_weight(value) is None


def test_sydney_local_day_at_utc_boundary():
    moment = datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc)
    ms = int(moment.timestamp() * 1000)
    assert timestamp(ms).astimezone(SYDNEY).date() == date(2026, 10, 2)


def test_complete_drop_set_qualifies():
    row = GymSet(id="drop", weight_kg=90, reps=10,
                 complete=True, warmup=False, drop_set=True, failure=True)
    assert eligible(row) == 120


def test_highest_90_day_bodyweight_not_latest_or_future():
    history = {
        "mfp": normalize([
            {"date": "2026-07-01", "weight_kg": 115},  # outside 90 days
            {"date": "2026-08-01", "weight_kg": 97},
            {"date": "2026-10-02", "weight_kg": 86},  # newest is NOT the maximum
            {"date": "2026-10-04", "weight_kg": 105}, # future is ignored
        ], "mfp"),
        "manual": normalize([
            {"date": "2026-09-01", "Weight": 101},
            {"date": "2026-10-02", "Weight": 104},  # duplicate date; MFP wins
        ], "manual", weight_key="Weight"),
    }
    item = highest_weight(history, date(2026, 10, 3))
    assert item["weight_kg"] == 101
    assert item["source"] == "manual"
    assert item["date"] == "2026-09-01"
    assert item["method"] == "highest_90d"
    assert item["period_end"] == "2026-10-03"
    assert highest_weight(history, date(2026, 7, 30))["weight_kg"] == 115
    assert highest_weight(history, date(2026, 6, 30)) is None


def test_peak_weight_ties_choose_newest_observation_and_mfp():
    history = {"mfp": normalize([{"date": "2026-10-02", "weight_kg": 95}], "mfp"),
               "manual": normalize([{"date": "2026-09-01", "Weight": 95},
                                    {"date": "2026-10-02", "Weight": 100}],
                                   "manual", weight_key="Weight")}
    item = highest_weight(history, date(2026, 10, 3))
    assert item["source"] == "mfp" and item["date"] == "2026-10-02"
    assert item["weight_kg"] == 95
