#!/usr/bin/env python3
"""Import an openGym backup into the athlete folder (data/sets.csv, data/sessions.csv, data/body.csv).

    python3 import_opengym.py --dir <athlete folder> <opengym-backup-YYYY-MM-DD.json>
                              [--catalogue <openGym checkout> | --fetch-names]

The file is openGym's Settings > Data & backup > Export backup (JSON): the whole app state, the same shape as a
self-hosted server's data/state-<user>.json (checked 2026-10 against openGym's api/openapi.yaml `State`):
  unit                        "kg" | "lb": every weight in the file (sets, drops, weigh-ins) is in this unit
  workouts[]                  id, d (local day), start / end (ms since epoch), name, note,
    entries[]                 id (catalogue number like "0025", or a customEx id), note,
      sets[]                  w, r, done, rir | rpe, phase "warmup" (older: warmup: true), failure: true,
                              type "dropset" + drops[{w, r}], sec (timed), min + speed (cardio, speed in km/h),
                              sides {L, R} (one-sided sets, each side its own w, r, done)
  customEx[]                  id, n (name) of the user's own exercises
  bodyweight[]                d, w (in `unit`)
Only sets ticked done are kept. A drop-set's drops become extra `dropset` rows after their main set. Catalogue
exercises have no name in the file, only their number. Their English name comes from openGym's catalogue
(AGPL-3.0; `name` field only): --catalogue reads <checkout>/catalogue/exercises/<id>.json (or a folder of those
files); --fetch-names downloads just the numbers used from openGym's GitHub, once, cached in
data/opengym_names.json. Without either, or for a number not found, the name is "openGym <id>". RPE -> RIR (10 - RPE)
when no RIR was logged. lb -> kg on import. Weigh-ins go to body.csv with source `opengym`.
Safe to run again: each session (openGym workout id) and weigh-in (date) is replaced, never doubled.
The export is copied untouched to data/raw/opengym/.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402
import exercise_map  # noqa: E402
import import_common as ic  # noqa: E402

BODY_KG = (30, 250)  # same bounds as the Apple Health import
CATALOGUE_ID = re.compile(r"\d{1,6}")  # openGym catalogue numbers ("0025"); also keeps paths and URLs plain
NAME_URL = "https://raw.githubusercontent.com/DuarteSantos8/openGym/main/catalogue/exercises/{}.json"
MAX_FILE, MAX_NAME = 64 * 1024, 80


def clean_name(raw):
    """The `name` of one catalogue file (bytes, untrusted), or None: JSON object, short single-line text."""
    if len(raw) > MAX_FILE:
        return None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    name = doc.get("name") if isinstance(doc, dict) else None
    if not isinstance(name, str):
        return None
    name = " ".join(name.split())
    return name if 0 < len(name) <= MAX_NAME and name.isprintable() else None


def catalogue_ids(doc):
    """Catalogue numbers used by the export's workouts (custom exercises carry their own name)."""
    return sorted({e.get("id") for w in doc.get("workouts") or [] for e in w.get("entries") or []
                   if isinstance(e, dict) and isinstance(e.get("id"), str) and CATALOGUE_ID.fullmatch(e["id"])})


def names_from_catalogue(directory, ids):
    """{id: name} from a local openGym checkout (or its catalogue/exercises folder). Missing ids are left out."""
    sub = os.path.join(directory, "catalogue", "exercises")
    base = sub if os.path.isdir(sub) else directory
    if not os.path.isdir(base):
        sys.exit(f"{directory}: not a folder. Pass the openGym checkout (it has catalogue/exercises/).")
    out = {}
    for i in ids:
        try:
            with open(os.path.join(base, i + ".json"), "rb") as fh:
                name = clean_name(fh.read(MAX_FILE + 1))
        except OSError:
            continue
        if name:
            out[i] = name
    return out


def names_from_github(folder, ids):
    """{id: name}: cached ones from data/opengym_names.json, the rest fetched once and added to the cache.
    Sends only the exercise numbers. A number GitHub does not have (or answers badly) is left out."""
    cache = os.path.join(folder, "data", "opengym_names.json")
    try:
        with open(cache, encoding="utf-8") as fh:
            names = {k: v for k, v in json.load(fh).items() if isinstance(v, str)}
    except (OSError, ValueError, AttributeError):
        names = {}
    new = False
    for i in ids:
        if i in names:
            continue
        try:
            with urllib.request.urlopen(NAME_URL.format(i), timeout=10) as resp:
                name = clean_name(resp.read(MAX_FILE + 1))
        except urllib.error.HTTPError:
            continue
        except (urllib.error.URLError, OSError) as e:
            sys.exit(f"Could not reach GitHub for openGym exercise names ({e}). Nothing was written. Check the "
                     "connection, or use --catalogue <openGym checkout>, or import without names.")
        if name:
            names[i] = new = name
    if new:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(names, fh, indent=1, sort_keys=True, ensure_ascii=False)
    return {i: names[i] for i in ids if i in names}


def load(path):
    """The backup's state dict, or exit with what to do."""
    with open(path, "rb") as fh:
        head = fh.read(2)
    if head == b"PK":
        sys.exit(f"{path}: this is the openGym backup with photos (.zip). Export the plain one instead: "
                 "Settings > Data & backup > Export backup (JSON).")
    try:
        with open(path, encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        sys.exit(f"{path}: not readable JSON ({e}). Export it again from openGym: "
                 "Settings > Data & backup > Export backup (JSON).")
    if not isinstance(doc, dict) or not isinstance(doc.get("workouts", []), list) or \
            not isinstance(doc.get("bodyweight", []), list) or not ("workouts" in doc or "bodyweight" in doc) or \
            not all(isinstance(w, dict) and "entries" in w for w in doc.get("workouts", [])):
        sys.exit(f"{path}: not an openGym backup (no `workouts` with `entries`, no `bodyweight`). Use the file from "
                 "Settings > Data & backup > Export backup (JSON).")
    if doc.get("unit", "kg") not in ("kg", "lb"):
        sys.exit(f"{path}: unknown weight unit {doc.get('unit')!r} (expected kg or lb).")
    return doc


def local_time(ms):
    return datetime.fromtimestamp(ms / 1000)


def completed(s):
    """The logged set as one row's fields, or None when it was not ticked done. A per-side set (sides L/R)
    counts its done sides: reps added up, the heavier weight."""
    sides = [v for v in (s.get("sides") or {}).values() if isinstance(v, dict) and v.get("done") is True] \
        if isinstance(s.get("sides"), dict) else None
    if sides is None:
        return s if s.get("done") is True else None
    if not sides:
        return None
    return dict(s, w=max(ic.num(v.get("w")) or 0 for v in sides), r=sum(ic.num(v.get("r")) or 0 for v in sides),
                drops=[d for v in sides for d in v.get("drops") or []])


def set_type(s):
    """openGym's phase wins over the older `warmup: true`; failure is its own flag on a work set."""
    phase = str(s.get("phase") or "").lower()
    if phase in ("warmup", "warm-up", "warm_up") or (not phase and s.get("warmup") is True):
        return "warmup"
    return "failure" if s.get("failure") is True else "normal"


def convert(doc, catalogue=None):
    """openGym state -> (sets, sessions, body rows, drops). `catalogue`: {catalogue number: name}."""
    to_kg = ic.LB_TO_KG if doc.get("unit") == "lb" else 1.0
    names = dict(catalogue or {})
    names.update({c["id"]: (c.get("n") or "").strip() for c in doc.get("customEx") or [] if isinstance(c, dict)
                  and c.get("id")})
    sets, sessions, drops = [], [], []
    for w in doc.get("workouts") or []:
        try:
            day = datetime.strptime(w["d"], "%Y-%m-%d")
            start = local_time(w["start"])
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            drops.append(f"workout {w.get('id') if isinstance(w, dict) else w!r}: no valid d / start")
            continue
        # `d` is the day the athlete gave the workout (it can be moved); the clock time comes from `start`.
        dt = f"{day:%Y-%m-%d}T{start:%H:%M}"
        sid, title = f"opengym:{w.get('id')}", (w.get("name") or "").strip()
        rows = []
        for e in w.get("entries") or []:
            ex = names.get(e.get("id")) or f"openGym {e.get('id')}"
            for s in e.get("sets") or []:
                s = completed(s) if isinstance(s, dict) else None
                if s is None:
                    continue
                parts = [(s, set_type(s))]
                if parts[0][1] != "warmup":
                    parts += [(d, "dropset") for d in s.get("drops") or [] if isinstance(d, dict)]
                for p, stype in parts:
                    weight, reps = ic.num(p.get("w")), ic.num(p.get("r")) or None
                    mins = ic.num(s.get("min")) if p is s else None
                    secs = ic.num(p.get("sec")) or (mins * 60 if mins else None)
                    speed = ic.num(s.get("speed")) if p is s else None
                    dist = speed * mins / 60 * 1000 if speed and mins else None  # speed is always km/h
                    if not (weight or reps or secs or dist):
                        continue
                    kg = (weight or 0) * to_kg
                    if kg > ic.MAX_WEIGHT_KG or (reps or 0) > ic.MAX_REPS:
                        drops.append(f"{day:%Y-%m-%d} {ex}: {weight} {doc.get('unit', 'kg')} x {reps}")
                        continue
                    rir, rpe = ic.num(p.get("rir")), ic.num(p.get("rpe"))
                    rows.append({
                        "date": f"{day:%Y-%m-%d}", "datetime": dt, "session_id": sid, "workout_name": title,
                        "exercise": ex, "exercise_id": "", "set_type": stype, "weight_kg": ic.fmt(kg),
                        "reps": ic.fmt(reps, 0),
                        "rir": str(max(0, min(5, int(rir + 0.5)))) if rir is not None else ic.rir_from_rpe(rpe),
                        "rpe": ic.fmt(rpe, 1), "seconds": ic.fmt(secs, 0), "distance_m": ic.fmt(dist, 1),
                        "source": "opengym", "note": e.get("note") or ""})
        if not rows:
            continue
        ic.index_sets(rows)
        end = ic.num(w.get("end"))
        sessions.append(ic.rollup(rows, {
            "date": f"{day:%Y-%m-%d}", "datetime": dt, "session_id": sid, "workout_name": title,
            "duration_min": (end - w["start"]) / 60000 if end and end > w["start"] else None,
            "source": "opengym", "note": w.get("note") or ""}))
        sets += rows

    body = {}
    for b in doc.get("bodyweight") or []:
        v = ic.num(b.get("w")) if isinstance(b, dict) else None
        try:
            day = f"{datetime.strptime(b['d'], '%Y-%m-%d'):%Y-%m-%d}"
        except (KeyError, TypeError, ValueError):
            drops.append(f"weigh-in {b!r}: no valid date")
            continue
        if v is None or not BODY_KG[0] <= v * to_kg <= BODY_KG[1]:
            drops.append(f"weigh-in {day}: {b.get('w')} {doc.get('unit', 'kg')}")
            continue
        body[day] = {"date": day, "weight_kg": ic.fmt(v * to_kg), "waist_cm": "", "body_fat_pct": "",
                     "source": "opengym"}  # openGym keeps one weigh-in per day; a repeat keeps the last
    return sets, sessions, [body[d] for d in sorted(body)], drops


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", help="openGym backup JSON")
    ap.add_argument("--dir", default=".", help="athlete folder (default: current directory)")
    how = ap.add_mutually_exclusive_group()
    how.add_argument("--catalogue", metavar="DIR", help="local openGym checkout, for exercise names")
    how.add_argument("--fetch-names", action="store_true",
                     help="download the names of the exercises used from openGym's GitHub (numbers only sent)")
    args = ap.parse_args()
    folder = ic.athlete_dir(args.dir)
    doc = load(args.export)
    ids = catalogue_ids(doc)
    catalogue = names_from_catalogue(args.catalogue, ids) if args.catalogue else \
        names_from_github(folder, ids) if args.fetch_names and ids else {}
    sets, sessions, body, drops = convert(doc, catalogue)
    ic.keep_raw(folder, args.export, "opengym")
    added, replaced = af.replace_sessions(folder, sets, sessions)
    af.upsert_rows(folder, "data/body.csv", body)
    res = exercise_map.sync(folder)
    summary = (f"opengym: {len(sessions)} sessions, {len(sets)} sets in the export "
               f"({added} new sessions, {replaced} updated), {len(body)} weigh-ins, {len(drops)} row{'s' * (len(drops) != 1)} dropped, "
               f"{len(res['unmapped'])} exercises to map")
    through = max((x["date"] for x in sessions), default="none")
    af.append_log(folder, "import", f"opengym: {len(sessions)} sessions, {len(sets)} sets through {through}")
    print(summary)
    for d in drops:
        print("  dropped:", d)
    if res["unmapped"] or res["bad_ids"]:
        print(exercise_map.report(res))
    unnamed = [i for i in ids if i not in catalogue]
    if unnamed:
        print(f"{len(unnamed)} openGym exercises have no name yet (stored as \"openGym <id>\"): re-run with "
              "--catalogue <openGym checkout> or --fetch-names.")


if __name__ == "__main__":
    main()
