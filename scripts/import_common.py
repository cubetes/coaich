"""Importer helpers: number parsing, RPE -> RIR, session ids and rollups, raw-export copies.

Folder I/O (find, read, write, replace whole sessions, log) is athlete_folder.py.
"""
import hashlib
import os
import shutil
import sys

import athlete_folder as af

SET_TYPES = ("warmup", "normal", "failure", "dropset")
LB_TO_KG = 0.45359237
MAX_WEIGHT_KG = 600.0  # hygiene: larger values are typing errors
MAX_REPS = 100


def athlete_dir(start):
    """athlete_folder.find, ending the script with its message when there is no folder."""
    try:
        return str(af.find(start))
    except FileNotFoundError as e:
        sys.exit(f"{e}, or pass --dir")


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
