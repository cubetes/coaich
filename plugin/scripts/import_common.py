"""Shared helpers for the importers: athlete-folder paths, CSV read/write, merge, session rollup.

Column lists follow plugin/docs/athlete-folder.md (data contract v0.1).
lean: local helper; fold into athlete_folder.py when the foundation lane lands.
"""
import csv
import datetime as dt
import hashlib
import os
import shutil
import sys

SETS_COLS = ["date", "datetime", "session_id", "workout_name", "exercise", "exercise_id", "set_index",
             "set_type", "weight_kg", "reps", "rir", "rpe", "seconds", "distance_m", "source", "note"]
SESSIONS_COLS = ["date", "datetime", "session_id", "workout_name", "duration_min", "n_exercises",
                 "n_working_sets", "total_volume_kg", "gym", "source", "note"]
BODY_COLS = ["date", "weight_kg", "waist_cm", "body_fat_pct", "source"]
HEALTH_COLS = ["date", "metric", "value", "unit", "source"]

SET_TYPES = ("warmup", "normal", "failure", "dropset")
LB_TO_KG = 0.45359237
MAX_WEIGHT_KG = 600.0  # hygiene: larger values are typing errors
MAX_REPS = 100


def athlete_dir(start):
    """The nearest folder at or above `start` holding coaich.md (as athlete_folder.find). Exits if none."""
    here = os.path.abspath(start)
    for d in _parents(here):
        if os.path.isfile(os.path.join(d, "coaich.md")):
            os.makedirs(os.path.join(d, "data", "raw"), exist_ok=True)
            return d
    sys.exit(f"no coaich.md in {here} or above: run /onboard to set up an athlete folder, or pass --dir")


def _parents(path):
    while True:
        yield path
        up = os.path.dirname(path)
        if up == path:
            return
        path = up


def setting(folder, key):
    """A `key: value` line from coaich.md, or None."""
    with open(os.path.join(folder, "coaich.md"), encoding="utf-8") as fh:
        for line in fh:
            k, sep, v = line.strip().lstrip("-* ").partition(":")
            if sep and k.strip().lower() == key:
                return v.strip().strip("`\"'").lower() or None
    return None


def keep_raw(folder, src, sub):
    """Copy an export into data/raw/<sub>/ untouched (skipped when it already lives there)."""
    raw = os.path.join(folder, "data", "raw", sub)
    src = os.path.abspath(src)
    if src.startswith(os.path.join(folder, "data", "raw") + os.sep):
        return src
    os.makedirs(raw, exist_ok=True)
    dest = os.path.join(raw, os.path.basename(src))
    shutil.copyfile(src, dest)
    return dest


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_rows(path, cols, rows):
    """Atomic write (temp file + rename) so a crash never leaves a half-written CSV."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def num(s):
    """'82.5' -> 82.5, '' / junk -> None."""
    try:
        v = float(str(s).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def fmt(v, nd=2):
    """Number -> compact CSV text ('82.5', '80', ''). Ints stay ints."""
    if v is None or v == "":
        return ""
    v = round(float(v), nd)
    return str(int(v)) if v == int(v) else str(v)


def rir_from_rpe(rpe):
    """rir = 10 - rpe, rounded half up, clamped to 0-5 (contract). Blank when RPE is blank."""
    if rpe is None:
        return ""
    return str(max(0, min(5, int(10 - rpe + 0.5))))


def session_hash(*parts):
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def merge_sessions(folder, new_sets, new_sessions):
    """Upsert whole sessions into sets.csv + sessions.csv. A session in the import replaces any stored
    session with the same session_id, or with the same start minute + workout name (the same workout
    seen through another export, e.g. Hevy CSV then Hevy MCP). Re-importing is safe and never duplicates.
    Keeps a hand-filled `gym` on a replaced session. Returns (n_new, n_replaced)."""
    sets_path = os.path.join(folder, "data", "sets.csv")
    sess_path = os.path.join(folder, "data", "sessions.csv")
    old_sets, old_sess = read_rows(sets_path), read_rows(sess_path)

    def same(r):
        return (r["datetime"][:16], r["workout_name"].strip().lower())

    new_ids = {s["session_id"] for s in new_sessions}
    new_keys = {same(s) for s in new_sessions}
    gone = {s["session_id"] for s in old_sess if s["session_id"] in new_ids or same(s) in new_keys}
    gyms = {}
    for s in old_sess:
        if s["session_id"] in gone and s.get("gym"):
            gyms[s["session_id"]] = gyms[same(s)] = s["gym"]
    for s in new_sessions:
        s["gym"] = s.get("gym") or gyms.get(s["session_id"]) or gyms.get(same(s), "")

    sets = [r for r in old_sets if r["session_id"] not in gone] + new_sets
    sess = [s for s in old_sess if s["session_id"] not in gone] + new_sessions
    sets.sort(key=lambda r: (r["datetime"], r["session_id"]))  # stable: keeps set order within a session
    sess.sort(key=lambda s: (s["datetime"], s["session_id"]))
    write_rows(sets_path, SETS_COLS, sets)
    write_rows(sess_path, SESSIONS_COLS, sess)
    old_ids, old_keys = {s["session_id"] for s in old_sess}, {same(s) for s in old_sess}
    replaced = sum(1 for s in new_sessions if s["session_id"] in old_ids or same(s) in old_keys)
    return len(new_sessions) - replaced, replaced


def rollup(sets, base):
    """One sessions.csv row from a session's set rows plus `base` (date, datetime, session_id,
    workout_name, duration_min, source, note). Working = every set that is not a warm-up."""
    work = [r for r in sets if r["set_type"] != "warmup"]
    vol = sum((num(r["weight_kg"]) or 0) * (num(r["reps"]) or 0) for r in work)
    row = dict(base)
    row.update(n_exercises=len({r["exercise"] for r in sets}), n_working_sets=len(work),
               total_volume_kg=fmt(vol, 1), gym="")
    row["duration_min"] = fmt(row.get("duration_min"), 1)
    return row


def index_sets(rows):
    """Fill set_index: 0-based per exercise name within the session, in logged order."""
    seen = {}
    for r in rows:
        k = (r["session_id"], r["exercise"])
        r["set_index"] = seen.get(k, 0)
        seen[k] = r["set_index"] + 1
    return rows


def append_log(folder, result, skill="import"):
    """`- YYYY-MM-DD · skill · result` in log.md (same line as athlete_folder.append_log)."""
    path = os.path.join(folder, "log.md")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# Log\n\nOne line per skill run.\n\n")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"- {dt.date.today().isoformat()} · {skill} · {' '.join(str(result).split())}\n")
