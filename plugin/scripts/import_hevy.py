#!/usr/bin/env python3
"""Import Hevy workouts into the athlete folder (data/sets.csv, data/sessions.csv). Read-only: it never
writes to Hevy.

    python3 import_hevy.py --dir <athlete folder> <file> [<file> ...]
    python3 import_hevy.py --dir <athlete folder> --cursor     newest Hevy session date on file

Two inputs, told apart by content:
  * JSON saved from the Hevy MCP `get-workouts` / `get-workout` tools: a list of workouts, an object with a
    "workouts" list, or one workout. Fields: id, title, description, start_time, end_time,
    exercises[].title / exercise_template_id / notes, sets[].index / type / weight_kg / reps /
    distance_meters / duration_seconds / rpe (the Hevy API workout shape).
  * Hevy's own CSV export (Settings > Export & Import Data > Export Workouts), one row per set:
    title,start_time,end_time,description,exercise_title,superset_id,exercise_notes,set_index,set_type,
    weight_kg|weight_lbs,reps,distance_km|distance_miles,duration_seconds,rpe   ("28 May 2030, 18:05")
Exercises are matched to free-exercise-db ids by title (exercise_map.py). RPE -> RIR (10 - RPE).
Safe to run again: a session is replaced by id, or by start minute + title (the same workout seen first
through the CSV and then through the MCP), never doubled. Inputs are copied to data/raw/hevy/.
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exercise_map  # noqa: E402
import import_common as ic  # noqa: E402

CSV_DATE = "%d %b %Y, %H:%M"


def local_time(s):
    """Hevy API time (ISO, usually UTC) -> naive local datetime. Naive input is taken as local."""
    t = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


def set_row(start, sid, title, ex, s, drops):
    """One sets.csv row from a Hevy set dict (API field names), or None when dropped/empty."""
    weight, reps = ic.num(s.get("weight_kg")), ic.num(s.get("reps"))
    secs, dist = ic.num(s.get("duration_seconds")) or None, ic.num(s.get("distance_meters")) or None
    if weight is None and reps is None and secs is None and dist is None:
        return None
    if (weight or 0) > ic.MAX_WEIGHT_KG or (reps or 0) > ic.MAX_REPS:
        drops.append(f"{start:%Y-%m-%d} {ex['title']}: {weight} kg x {reps}")
        return None
    rpe = ic.num(s.get("rpe"))
    stype = s.get("type") if s.get("type") in ic.SET_TYPES else "normal"
    return {"date": f"{start:%Y-%m-%d}", "datetime": f"{start:%Y-%m-%dT%H:%M}", "session_id": sid,
            "workout_name": title, "exercise": ex["title"], "exercise_id": "", "set_type": stype,
            "weight_kg": ic.fmt(weight or 0), "reps": ic.fmt(reps, 0), "rir": ic.rir_from_rpe(rpe),
            "rpe": ic.fmt(rpe, 1), "seconds": ic.fmt(secs, 0), "distance_m": ic.fmt(dist, 1),
            "source": "hevy", "note": ex.get("notes") or ""}


def from_workouts(workouts):
    """Hevy API/MCP workout dicts -> (sets, sessions, drops)."""
    sets, sessions, drops = [], [], []
    for w in workouts:
        start, end = local_time(w["start_time"]), w.get("end_time")
        sid, title = w.get("session_id") or f"hevy:{w['id']}", (w.get("title") or "").strip()
        rows = [r for ex in w.get("exercises") or [] for s in ex.get("sets") or []
                if (r := set_row(start, sid, title, ex, s, drops))]
        if not rows:
            continue
        ic.index_sets(rows)
        dur = (local_time(end) - start).total_seconds() / 60 if end else None
        sessions.append(ic.rollup(rows, {
            "date": f"{start:%Y-%m-%d}", "datetime": f"{start:%Y-%m-%dT%H:%M}", "session_id": sid,
            "workout_name": title, "duration_min": dur, "source": "hevy",
            "note": w.get("description") or ""}))
        sets += rows
    return sets, sessions, drops


def csv_workouts(path):
    """Hevy CSV export -> workout dicts in the API shape (grouped by title + start + end)."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        if "exercise_title" not in cols or "start_time" not in cols:
            sys.exit(f"{path}: not a Hevy workouts export (no exercise_title / start_time columns).")
        lb = "weight_lbs" in cols
        miles = "distance_miles" in cols
        workouts = {}
        for r in reader:
            try:
                start = datetime.strptime(r["start_time"].strip(), CSV_DATE)
                end = datetime.strptime(r["end_time"].strip(), CSV_DATE) if r.get("end_time") else None
            except ValueError:
                sys.exit(f"{path}: unexpected date {r['start_time']!r} (expected like '28 May 2030, 18:05').")
            key = (r["title"], r["start_time"], r.get("end_time", ""))
            w = workouts.setdefault(key, {
                "session_id": "hevy:" + ic.session_hash(start.isoformat(), r["title"].strip()),
                "title": r["title"], "description": r.get("description", ""),
                "start_time": start.isoformat(), "end_time": end.isoformat() if end else None,
                "exercises": []})
            if not w["exercises"] or w["exercises"][-1]["title"] != r["exercise_title"]:
                w["exercises"].append({"title": r["exercise_title"], "notes": r.get("exercise_notes", ""),
                                       "sets": []})
            weight = ic.num(r.get("weight_lbs" if lb else "weight_kg"))
            dist = ic.num(r.get("distance_miles" if miles else "distance_km"))
            w["exercises"][-1]["sets"].append({
                "type": r.get("set_type"), "reps": r.get("reps"), "rpe": r.get("rpe"),
                "weight_kg": weight * ic.LB_TO_KG if lb and weight is not None else weight,
                "distance_meters": dist * (1609.344 if miles else 1000) if dist is not None else None,
                "duration_seconds": r.get("duration_seconds")})
    return list(workouts.values())


def json_workouts(path):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if isinstance(doc, dict):
        doc = doc.get("workouts", [doc] if "start_time" in doc else [])
    if not isinstance(doc, list) or not all(isinstance(w, dict) and "start_time" in w for w in doc):
        sys.exit(f"{path}: expected Hevy workouts JSON (a list of workouts with start_time).")
    return doc


def load(path):
    with open(path, encoding="utf-8-sig") as fh:
        head = fh.read(1).strip()
    return json_workouts(path) if head in ("[", "{") else csv_workouts(path)


def cursor(folder):
    dates = [s["date"] for s in ic.read_rows(os.path.join(folder, "data", "sessions.csv")) if s["source"] == "hevy"]
    return max(dates) if dates else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="*", help="Hevy MCP JSON files and/or a Hevy CSV export")
    ap.add_argument("--dir", default=".", help="athlete folder (default: current directory)")
    ap.add_argument("--cursor", action="store_true", help="print the newest Hevy session date on file")
    args = ap.parse_args()
    folder = ic.athlete_dir(args.dir)
    if args.cursor:
        print(cursor(folder) or "none")
        return
    if not args.inputs:
        ap.error("give at least one Hevy JSON or CSV file")
    workouts, seen = [], set()
    for p in args.inputs:
        for w in load(p):
            k = w.get("session_id") or w.get("id")
            if k not in seen:  # the same workout on two MCP pages counts once
                seen.add(k)
                workouts.append(w)
    sets, sessions, drops = from_workouts(workouts)
    for p in args.inputs:
        ic.keep_raw(folder, p, "hevy")
    added, replaced = ic.merge_sessions(folder, sets, sessions)
    res = exercise_map.sync(folder)
    summary = (f"hevy: {len(sessions)} sessions, {len(sets)} sets read ({added} new sessions, "
               f"{replaced} updated), {len(drops)} sets dropped, {len(res['unmapped'])} exercises to map")
    through = max((x["date"] for x in sessions), default="none")
    ic.append_log(folder, f"hevy: {len(sessions)} sessions, {len(sets)} sets through {through}")
    print(summary)
    for d in drops:
        print("  dropped:", d)
    if res["unmapped"] or res["bad_ids"]:
        print(exercise_map.report(res))


if __name__ == "__main__":
    main()
