#!/usr/bin/env python3
"""Generate the fictional demo athlete: 12 weeks of training, body weight and health data, all in 2030.

Usage: demo_athlete.py [--out examples/demo-athlete] [--seed 2030]
Deterministic: the same seed writes byte-identical files. Re-running replaces a previous demo folder
(one whose coaich.md says `demo: true`) and refuses to touch any other non-empty folder.
"""
import argparse
import datetime as dt
import json
import random
import shutil
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import athlete_folder as af  # noqa: E402

START = dt.date(2030, 1, 7)  # a Monday
WEEKS = 12
EASY_WEEK = 7  # intermediate: an easy week every 7th week
TODAY = START + dt.timedelta(weeks=WEEKS) - dt.timedelta(days=1)

# routine -> [(name as logged, free-exercise-db id, sets, rep_lo, rep_hi, load_step_kg, start e1RM kg, weekly growth)]
# Growth near zero makes a realistic stall: bench and overhead press flatten, the deadlift late.
PROGRAM = {
    "Upper A": [
        ("Bench Press (Barbell)", "Barbell_Bench_Press_-_Medium_Grip", 4, 6, 8, 2.5, 92, 0.003),
        ("Bent Over Row (Barbell)", "Bent_Over_Barbell_Row", 4, 8, 10, 2.5, 86, 0.017),
        ("Overhead Press (Barbell)", "Standing_Military_Press", 3, 6, 8, 2.5, 56, 0.001),
        ("Lat Pulldown (Cable)", "Wide-Grip_Lat_Pulldown", 3, 10, 12, 2.5, 78, 0.014),
        ("Lateral Raise (Dumbbell)", "Side_Lateral_Raise", 3, 12, 15, 1.0, 15, 0.010),
        ("Triceps Pushdown (Cable)", "Triceps_Pushdown", 3, 10, 12, 2.5, 42, 0.014),
    ],
    "Lower A": [
        ("Squat (Barbell)", "Barbell_Full_Squat", 4, 5, 7, 2.5, 122, 0.017),
        ("Romanian Deadlift (Barbell)", "Romanian_Deadlift", 3, 8, 10, 2.5, 112, 0.015),
        ("Leg Press", "Leg_Press", 3, 10, 12, 10.0, 230, 0.020),
        ("Lying Leg Curl (Machine)", "Lying_Leg_Curls", 3, 10, 12, 2.5, 56, 0.014),
        ("Standing Calf Raise (Machine)", "Standing_Calf_Raises", 3, 10, 15, 5.0, 105, 0.010),
    ],
    "Upper B": [
        ("Incline Bench Press (Dumbbell)", "Incline_Dumbbell_Press", 3, 8, 10, 2.0, 35, 0.012),
        ("Seated Cable Row", "Seated_Cable_Rows", 3, 10, 12, 2.5, 82, 0.017),
        ("Lat Pulldown (Cable)", "Wide-Grip_Lat_Pulldown", 3, 10, 12, 2.5, 78, 0.014),
        ("Lateral Raise (Dumbbell)", "Side_Lateral_Raise", 3, 12, 15, 1.0, 15, 0.010),
        ("Bicep Curl (Dumbbell)", "Dumbbell_Bicep_Curl", 3, 10, 12, 1.0, 19, 0.012),
    ],
    "Lower B": [
        ("Deadlift (Barbell)", "Barbell_Deadlift", 3, 4, 6, 5.0, 152, 0.014),
        ("Leg Press", "Leg_Press", 3, 12, 15, 10.0, 230, 0.020),
        ("Leg Extension (Machine)", "Leg_Extensions", 3, 12, 15, 2.5, 70, 0.015),
        ("Lying Leg Curl (Machine)", "Lying_Leg_Curls", 3, 10, 12, 2.5, 56, 0.014),
        ("Standing Calf Raise (Machine)", "Standing_Calf_Raises", 3, 10, 15, 5.0, 105, 0.010),
    ],
}
DAYS = {"Upper A": 0, "Lower A": 1, "Upper B": 3, "Lower B": 4}  # Mon, Tue, Thu, Fri
SHIFT = {"Lower A": 1, "Lower B": 1}  # sometimes a day late (Wed, Sat), never onto another session
STALL_FROM_WEEK = {"Barbell_Deadlift": 8}  # growth stops from this week on
NOTES = ["slept badly", "short on time", "felt strong", "gym busy, waited for the rack", "left knee a bit stiff"]


def step_round(x, step):
    return round(round(x / step) * step, 2)


def reps_to_failure(e1rm, w):
    return 30 * (e1rm / w - 1)  # Epley, inverted


def simulate(rng):
    """Yields (date, start, routine, [(exercise row, [set dicts])])."""
    state = {}
    for routine, slots in PROGRAM.items():
        for name, ex_id, sets, lo, hi, step, e1rm, growth in slots:
            w = step_round(e1rm / (1 + (lo + 4) / 30), step)  # about lo+2 reps with 2 in reserve
            state[(routine, ex_id)] = {"w": w, "e1rm": e1rm, "misses": 0}
    for week in range(1, WEEKS + 1):
        easy = week == EASY_WEEK
        for routine, slots in PROGRAM.items():
            if rng.random() < 0.06:
                continue  # missed session
            day = START + dt.timedelta(weeks=week - 1, days=DAYS[routine] + (SHIFT.get(routine, 0) if rng.random() < 0.1 else 0))
            start = dt.datetime.combine(day, dt.time(18, 0)) + dt.timedelta(minutes=rng.randrange(0, 75, 5))
            form = rng.gauss(1.0, 0.025)  # day-to-day readiness
            exercises = []
            for i, (name, ex_id, n_sets, lo, hi, step, _, growth) in enumerate(slots):
                s = state[(routine, ex_id)]
                w = step_round(s["w"] * 0.9, step) if easy else s["w"]
                aim_rir = 4 if easy else 2
                rows = []
                if i == 0:
                    for frac, reps in ((0.5, 8), (0.75, 4)):
                        rows.append({"set_type": "warmup", "weight_kg": step_round(w * frac, step), "reps": reps})
                done = []
                for k in range(n_sets - 1 if easy else n_sets):
                    cap = reps_to_failure(s["e1rm"] * form, w) - 0.5 * k
                    reps = max(1, min(hi, int(cap - aim_rir + rng.gauss(0, 0.6))))
                    rir = max(0, min(5, round(cap - reps)))
                    done.append(reps)
                    rows.append({"set_type": "normal", "weight_kg": w, "reps": reps,
                                 "rir": "" if rng.random() < 0.08 else rir})
                exercises.append((name, ex_id, rows))
                if not easy:  # double progression; two sessions under the range cut the load 5 %
                    if all(r >= hi for r in done):
                        s["w"] = round(w + step, 2)
                        s["misses"] = 0
                    elif done[0] < lo:
                        s["misses"] += 1
                        if s["misses"] == 2:
                            s["w"] = step_round(w * 0.95, step)
                            s["misses"] = 0
                    else:
                        s["misses"] = 0
            yield day, start, routine, exercises
        for (routine, ex_id), s in state.items():
            g = next(sl[7] for sl in PROGRAM[routine] if sl[1] == ex_id)
            if week >= STALL_FROM_WEEK.get(ex_id, 99):
                g = 0.0
            s["e1rm"] *= 1 + max(0.0, rng.gauss(g, 0.003))


def training_rows(rng):
    sets, sessions = [], []
    for day, start, routine, exercises in sorted(simulate(rng), key=lambda x: x[1]):
        sid = "manual:" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"coaich-demo/{start.isoformat()}/{routine}"))
        note = rng.choice(NOTES) if rng.random() < 0.1 else ""
        base = {"date": day.isoformat(), "datetime": start.strftime("%Y-%m-%dT%H:%M"), "session_id": sid,
                "workout_name": routine, "source": "manual"}
        n_work = 0
        volume = 0.0
        for name, ex_id, rows in exercises:
            for idx, r in enumerate(rows):
                sets.append(dict(base, exercise=name, exercise_id=ex_id, set_index=idx, **r))
                if r["set_type"] != "warmup":
                    n_work += 1
                    volume += r["weight_kg"] * r["reps"]
        sessions.append(dict(base, duration_min=round(n_work * 2.7 + rng.uniform(4, 12)),
                             n_exercises=len(exercises), n_working_sets=n_work,
                             total_volume_kg=round(volume, 1), note=note))
    return sets, sessions


def body_rows(rng):
    rows = []
    for d in range((TODAY - START).days + 1):
        day = START + dt.timedelta(days=d)
        if rng.random() < 0.2:
            continue  # no weigh-in that day
        trend = 78.0 + 0.03 * d  # slow lean gain, about 0.2 kg a week
        waist = round(83.0 + 0.012 * d + rng.gauss(0, 0.3), 1) if day.weekday() == 0 else ""
        rows.append({"date": day.isoformat(), "weight_kg": round(trend + rng.gauss(0, 0.4), 1),
                     "waist_cm": waist, "source": "scale"})
    return rows


def health_rows(rng):
    rows = []
    hrv = 55.0
    for d in range((TODAY - START).days + 1):
        day = START + dt.timedelta(days=d)
        weekend = day.weekday() >= 5
        sleep = max(4.5, rng.gauss(7.6 if weekend else 7.0, 0.6))
        hrv = 0.7 * hrv + 0.3 * (55 + 6 * (sleep - 7.2) + rng.gauss(0, 6))
        values = {
            "steps": (max(1500, round(rng.gauss(6500 if weekend else 9000, 2200))), "count"),
            "sleep_h": (round(sleep, 2), "h"),
            "hrv_ms": (round(hrv), "ms"),
            "resting_hr_bpm": (round(58 - 0.8 * (sleep - 7.2) + rng.gauss(0, 1.8)), "bpm"),
        }
        for metric, (value, unit) in values.items():
            rows.append({"date": day.isoformat(), "metric": metric, "value": value, "unit": unit,
                         "source": "apple-health"})
    return rows


def program_json():
    routines = []
    for routine, slots in PROGRAM.items():
        routines.append({"title": routine, "day": ["Mon", "Tue", "Wed", "Thu", "Fri"][DAYS[routine]],
                         "exercises": [{"exercise_id": ex_id, "name": name, "sets": n, "rep_range": [lo, hi],
                                        "load_step_kg": step}
                                       for name, ex_id, n, lo, hi, step, _, _ in slots]})
    return {"title": "Upper/Lower, 4 days", "level": "intermediate", "goal": "both", "priority": "back",
            "start": START.isoformat(), "weeks": WEEKS, "easy_weeks": [EASY_WEEK], "routines": routines}


COAICH_MD = f"""---
coaich: 0.1
demo: true               # fictional athlete generated by plugin/scripts/demo_athlete.py
language: en
units: kg
data_sources: []
safety_acknowledged: {START - dt.timedelta(days=1)}
safety_acknowledgement: "CoAIch does not replace a doctor. If you have a condition, an injury or any doubt about your health, see one before you train."
safety_status: go
safety_reasons: []
safety_clearance_date:
safety_clearance_sentence:
safety_clearance_covers: []
---
# CoAIch settings

Demo folder for a fictional lifter. Every date is in 2030 and every number is generated.
"""

PROFILE_MD = f"""---
profile: 0.1
updated: {START - dt.timedelta(days=1)}
age_band: 18-59
health_items: []
pain: []
history: over-2y
last_trained: last-3m
known_loads: []
chair_stand:
level: intermediate
returning: false
check_week: 6
days_per_week: 4
minutes_per_session: 60
equipment: gym
goal: both
priority: back
---
# Profile

Fictional lifter "Sam". Has lifted on and off for about three years, trained steadily in the last three months,
does not know their 8-rep loads, so placed in Intermediate with an advanced check at week 6.
Wants strength and muscle about equally; back is the priority area. Trains in a commercial gym after work.
"""

CURRENT_MD = f"""# What is in force today

*As of {TODAY}. This file wins over every other plan file.*

- **Program:** Upper/Lower, 4 days (`plan/program.json`): Upper A Mon, Lower A Tue, Upper B Thu, Lower B Fri.
- **Phase / week:** first mesocycle, week {WEEKS} of {WEEKS} (week {EASY_WEEK} was the easy week).
- **Progression:** double progression in each rep range; add the load step when every set reaches the top.
- **Priority:** back.
- **Safety:** status go, no health items, no pain areas.
- **Next review:** the weekly review after the next session.
"""


def write(out, seed):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        marker = out / "coaich.md"
        if not (marker.exists() and "demo: true" in marker.read_text(encoding="utf-8")):
            sys.exit(f"refusing to overwrite {out}: not a demo folder")
        shutil.rmtree(out)
    (out / "plan").mkdir(parents=True)
    rng = random.Random(seed)
    sets, sessions = training_rows(rng)
    af.upsert_rows(out, "data/sets.csv", sets)
    af.upsert_rows(out, "data/sessions.csv", sessions)
    af.upsert_rows(out, "data/body.csv", body_rows(rng))
    af.upsert_rows(out, "data/health.csv", health_rows(rng))
    (out / "coaich.md").write_text(COAICH_MD, encoding="utf-8")
    (out / "profile.md").write_text(PROFILE_MD, encoding="utf-8")
    (out / "plan/CURRENT.md").write_text(CURRENT_MD, encoding="utf-8")
    (out / "plan/program.json").write_text(json.dumps(program_json(), indent=2) + "\n", encoding="utf-8")
    ids = sorted({(r["exercise"], r["exercise_id"]) for r in sets})
    (out / "data/exercise_map.csv").write_text(
        "exercise,exercise_id\n" + "".join(f"{n},{i}\n" for n, i in ids), encoding="utf-8")
    first = START - dt.timedelta(days=1)
    log = [(first, "onboard", "profile written: intermediate, 4 days, 60 min, goal both, priority back"),
           (first, "safety", "acknowledged; status go"),
           (first, "program-build", "Upper/Lower 4 days issued")]
    for d, skill, result in log:
        af.append_log(out, skill, result, date=d.isoformat())
    return len(sets), len(sessions)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    root = Path(__file__).resolve().parents[2]
    p.add_argument("--out", default=str(root / "examples" / "demo-athlete"))
    p.add_argument("--seed", type=int, default=2030)
    a = p.parse_args(argv)
    n_sets, n_sessions = write(a.out, a.seed)
    print(f"{a.out}: {n_sessions} sessions, {n_sets} sets, {START} to {TODAY}")


if __name__ == "__main__":
    main()
