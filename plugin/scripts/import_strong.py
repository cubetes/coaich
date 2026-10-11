#!/usr/bin/env python3
"""Import a Strong app CSV export into the athlete folder (data/sets.csv, data/sessions.csv).

    python3 import_strong.py --dir <athlete folder> <strong export.csv> [--unit kg|lb]

Reads both Strong layouts (checked 2026-10 against public parsers of real exports):
  older (iOS, comma):   Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,
                        Notes,Workout Notes,RPE        (no unit in the file: --unit, else coaich.md `units`)
  newer (semicolon):    Workout #;Date;Workout Name;Duration (sec);Exercise Name;Set Order;Weight (kg);Reps;
                        RPE;Distance (meters);Seconds;Notes;Workout Notes    (unit in the header)
Set Order: a number = normal set, W = warm-up, D = drop set, F = failure; "Rest Timer" rows are skipped
and "Note" rows become the note of that exercise's sets. lb -> kg on import; RPE -> RIR (10 - RPE).
Safe to run again on a newer export: each session (start time + workout name) is replaced, never doubled.
The export is copied untouched to data/raw/strong/.
"""
import argparse
import csv
import io
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exercise_map  # noqa: E402
import import_common as ic  # noqa: E402

SET_ORDER = {"w": "warmup", "d": "dropset", "f": "failure"}
DIST_TO_M = {"meters": 1, "m": 1, "km": 1000, "miles": 1609.344, "mi": 1609.344}


def parse_duration(s):
    """'1h 36m' / '45m' / '3367' (seconds, newer layout) -> minutes, or None."""
    s = (s or "").strip().lower()
    if not s:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s) / 60
    parts = dict((u, float(v)) for v, u in re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", s))
    mins = parts.get("h", 0) * 60 + parts.get("m", 0) + parts.get("s", 0) / 60
    return mins or None


def read_export(path):
    """(header -> column map, rows). Detects the delimiter from the header line."""
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    fields = [f.strip() for f in reader.fieldnames or []]
    if "Exercise Name" not in fields or "Set Order" not in fields:
        sys.exit(f"{path}: not a Strong export (no 'Exercise Name' / 'Set Order' columns). Header: {first[:120]}")
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    return fields, rows


def column(fields, base):
    """('Weight (kg)', 'kg') for base 'Weight'; ('Weight', None) for the unit-less older layout."""
    for f in fields:
        m = re.fullmatch(re.escape(base) + r"(?:\s*\(([^)]+)\))?", f)
        if m:
            return f, (m.group(1) or "").lower() or None
    return None, None


def convert(path, unit=None):
    """Strong export -> (sets, sessions, drops). `unit` is the weight unit for the older layout."""
    fields, rows = read_export(path)
    wcol, wunit = column(fields, "Weight")
    dcol, dunit = column(fields, "Distance")
    tcol = column(fields, "Duration")[0]
    wunit = wunit or unit
    if wunit is None:
        sys.exit("This Strong export does not say kg or lb. Re-run with --unit kg or --unit lb "
                 "(the unit Strong was set to), or set `units:` in coaich.md.")
    to_kg = ic.LB_TO_KG if wunit.startswith("lb") else 1.0
    to_m = DIST_TO_M.get(dunit or ("km" if to_kg == 1.0 else "miles"), 1)  # lean: older layout unit assumed

    sets, bases, drops, ex_notes = [], {}, [], {}
    for r in rows:
        try:
            start = datetime.strptime(r.get("Date", "")[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                start = datetime.strptime(r.get("Date", "")[:16], "%Y-%m-%d %H:%M")
            except ValueError:
                drops.append(f"bad date {r.get('Date', '')!r}")
                continue
        name, ex = r.get("Workout Name", ""), r.get("Exercise Name", "")
        order = r.get("Set Order", "")
        if not ex or order.lower() == "rest timer":
            continue
        sid = "strong:" + ic.session_hash(start.isoformat(), name)
        if order.lower() == "note":
            ex_notes[(sid, ex)] = r.get("Notes", "")
            continue
        weight, reps = ic.num(r.get(wcol)), ic.num(r.get("Reps"))
        secs, dist = ic.num(r.get("Seconds")) or None, ic.num(r.get(dcol)) or None
        if weight is None and reps is None and secs is None and dist is None:
            continue
        kg = (weight or 0) * to_kg
        if kg > ic.MAX_WEIGHT_KG or (reps or 0) > ic.MAX_REPS:
            drops.append(f"{start:%Y-%m-%d} {ex}: {weight} {wunit} x {reps}")
            continue
        rpe = ic.num(r.get("RPE")) or None
        bases.setdefault(sid, {
            "date": f"{start:%Y-%m-%d}", "datetime": f"{start:%Y-%m-%dT%H:%M}", "session_id": sid,
            "workout_name": name, "duration_min": parse_duration(r.get(tcol)), "source": "strong",
            "note": r.get("Workout Notes", "")})
        sets.append({
            "date": f"{start:%Y-%m-%d}", "datetime": f"{start:%Y-%m-%dT%H:%M}", "session_id": sid,
            "workout_name": name, "exercise": ex, "exercise_id": "",
            "set_type": SET_ORDER.get(order.lower(), "normal"), "weight_kg": ic.fmt(kg),
            "reps": ic.fmt(reps, 0), "rir": ic.rir_from_rpe(rpe), "rpe": ic.fmt(rpe, 1),
            "seconds": ic.fmt(secs, 0), "distance_m": ic.fmt(dist * to_m if dist else None, 1),
            "source": "strong", "note": r.get("Notes", "")})
    for s in sets:
        s["note"] = s["note"] or ex_notes.get((s["session_id"], s["exercise"]), "")
    ic.index_sets(sets)
    sessions = [ic.rollup([s for s in sets if s["session_id"] == sid], b) for sid, b in bases.items()]
    return sets, sessions, drops


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", help="Strong CSV export")
    ap.add_argument("--dir", default=".", help="athlete folder (default: current directory)")
    ap.add_argument("--unit", choices=["kg", "lb"], help="weight unit of an older export without one")
    args = ap.parse_args()
    folder = ic.athlete_dir(args.dir)
    unit = args.unit or {"kg": "kg", "lb": "lb", "lbs": "lb"}.get(ic.setting(folder, "units") or "")
    sets, sessions, drops = convert(args.export, unit)
    ic.keep_raw(folder, args.export, "strong")
    added, replaced = ic.merge_sessions(folder, sets, sessions)
    res = exercise_map.sync(folder)
    summary = (f"strong: {len(sessions)} sessions, {len(sets)} sets in the export "
               f"({added} new sessions, {replaced} updated), {len(drops)} rows dropped, "
               f"{len(res['unmapped'])} exercises to map")
    through = max((x["date"] for x in sessions), default="none")
    ic.append_log(folder, f"strong: {len(sessions)} sessions, {len(sets)} sets through {through}")
    print(summary)
    for d in drops:
        print("  dropped:", d)
    if res["unmapped"] or res["bad_ids"]:
        print(exercise_map.report(res))


if __name__ == "__main__":
    main()
