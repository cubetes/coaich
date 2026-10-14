#!/usr/bin/env python3
"""Map logged exercise names to free-exercise-db ids, and keep data/exercise_map.csv (the fix-up list).

    python3 exercise_map.py --dir <athlete folder>

Every exercise name in data/sets.csv gets one row in data/exercise_map.csv: `exercise,exercise_id`.
Order of resolution for a name:
    1. the map row, when its exercise_id is a catalogue id or a custom id the user chose (a fix)
    2. the bundled alias table (data/exercise_aliases.csv: common Strong/Hevy names)
    3. the catalogue name itself, also "Bench Press (Dumbbell)" read as "Dumbbell Bench Press"
    4. otherwise `custom:<slug of the name>`: unmapped, for the user to fix
To fix a row, put a catalogue id in exercise_id and run this again: every set (old and new) gets it.
Catalogue: data/exercises.json, trimmed from free-exercise-db (The Unlicense).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402
import import_common as ic  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CUSTOM = "custom:"


def norm(name):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower().replace("&", " and ")).split())


def slug(name):
    return norm(name).replace(" ", "-") or "unnamed"


def load_catalog():
    with open(os.path.join(DATA, "exercises.json"), encoding="utf-8") as fh:
        return {e["id"]: e for e in json.load(fh)}


def load_aliases():
    return {norm(r["exercise"]): r["exercise_id"] for r in af.read_rows(DATA, "exercise_aliases.csv")}


def guess(name, by_name, aliases):
    """(exercise_id, how) from the alias table and the catalogue, else a custom slug."""
    n = norm(name)
    if n in aliases:
        return aliases[n], "alias"
    if n in by_name:
        return by_name[n], "catalog"
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", name)  # Strong/Hevy style "Name (Equipment)"
    if m and norm(f"{m.group(2)} {m.group(1)}") in by_name:
        return by_name[norm(f"{m.group(2)} {m.group(1)}")], "catalog"
    return CUSTOM + slug(name), "unmapped"


def sync(folder):
    """Update exercise_map.csv from sets.csv, then rewrite every set's exercise_id from the map.
    Returns {"unmapped": [names], "new_unmapped": [names], "bad_ids": [(name, id)]}."""
    catalog = load_catalog()
    by_name = {norm(e["name"]): i for i, e in catalog.items()}
    aliases = load_aliases()
    rows = {norm(r["exercise"]): r for r in af.read_rows(folder, "data/exercise_map.csv")}
    sets = af.read_rows(folder, "data/sets.csv")
    new = set()
    for r in sets:
        n = norm(r["exercise"])
        if n not in rows:
            rows[n] = {"exercise": r["exercise"].strip(), "exercise_id": ""}
            new.add(n)

    bad, new_unmapped, effective = [], [], {}
    for n, row in rows.items():
        eid, default = row["exercise_id"].strip(), CUSTOM + slug(row["exercise"])
        if eid in catalog or (eid.startswith(CUSTOM) and eid != default):
            effective[n] = eid  # a match or a user fix (a custom id the user chose stays too)
        elif eid and not eid.startswith(CUSTOM):
            bad.append((row["exercise"], eid))  # keep the user's text so they can correct it
            effective[n] = default
        else:  # new, or still unmapped: try again, the alias table may have grown
            row["exercise_id"] = effective[n] = guess(row["exercise"], by_name, aliases)[0]
            if effective[n] == default and n in new:
                new_unmapped.append(row["exercise"])

    for r in sets:
        r["exercise_id"] = effective[norm(r["exercise"])]
    af.write_rows(folder, "data/exercise_map.csv", sorted(rows.values(), key=lambda r: norm(r["exercise"])))
    if sets:
        af.write_rows(folder, "data/sets.csv", sets)
    unmapped = sorted(r["exercise"] for n, r in rows.items() if effective[n] == CUSTOM + slug(r["exercise"]))
    return {"unmapped": unmapped, "new_unmapped": sorted(new_unmapped), "bad_ids": bad}


def report(res):
    lines = []
    if res["bad_ids"]:
        lines.append("Not in the catalogue (fix these ids in data/exercise_map.csv):")
        lines += [f"  - {name}: {eid}" for name, eid in res["bad_ids"]]
    if res["unmapped"]:
        lines.append(f"Exercises to map: {len(res['unmapped'])} (data/exercise_map.csv rows still on custom:<slug>)")
        lines += [f"  - {n}" for n in res["unmapped"]]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="athlete folder (default: current directory)")
    args = ap.parse_args()
    res = sync(ic.athlete_dir(args.dir))
    print(report(res) or "All exercises mapped.")


if __name__ == "__main__":
    main()
