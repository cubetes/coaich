#!/usr/bin/env python3
"""The athlete folder (plugin/docs/athlete-folder.md): find it, read and upsert its CSVs, append log.md.

Usage:
  athlete_folder.py find [--dir D]              print the athlete folder (the one holding coaich.md)
  athlete_folder.py init DIR                    create the folder from the template; never overwrites
  athlete_folder.py log SKILL RESULT [--dir D]  append "date · skill · result" to log.md

Library: find(), read_rows(), upsert_rows(), append_log(). Python stdlib only.
"""
import argparse
import csv
import datetime
import os
import shutil
import sys
from pathlib import Path

MARKER = "coaich.md"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "athlete"

# file -> (columns, key). The key makes every write idempotent: a row with an existing key replaces it.
SCHEMAS = {
    "data/sets.csv": (
        ["date", "datetime", "session_id", "workout_name", "exercise", "exercise_id", "set_index", "set_type",
         "weight_kg", "reps", "rir", "rpe", "seconds", "distance_m", "source", "note"],
        # set_index restarts at 0 for each exercise, so the exercise (name as logged) is part of the key.
        ("session_id", "exercise", "set_index"),
    ),
    "data/sessions.csv": (
        ["date", "datetime", "session_id", "workout_name", "duration_min", "n_exercises", "n_working_sets",
         "total_volume_kg", "gym", "source", "note"],
        ("session_id",),
    ),
    "data/body.csv": (["date", "weight_kg", "waist_cm", "body_fat_pct", "source"], ("date",)),
    "data/health.csv": (["date", "metric", "value", "unit", "source"], ("date", "metric")),
}


def find(start=None):
    """The nearest folder at or above `start` (default: cwd) that holds coaich.md. FileNotFoundError if none."""
    here = Path(start or os.getcwd()).resolve()
    for d in (here, *here.parents):
        if (d / MARKER).is_file():
            return d
    raise FileNotFoundError(f"no {MARKER} in {here} or above: run /onboard to set up an athlete folder")


def init(folder):
    """Copy the template into `folder`. Existing files are kept. Returns the list of files created."""
    folder = Path(folder)
    created = []
    for src in sorted(TEMPLATE.rglob("*")):
        dst = folder / src.relative_to(TEMPLATE)
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            created.append(str(dst.relative_to(folder)))
    return created


def _schema(name):
    if name not in SCHEMAS:
        raise ValueError(f"unknown file {name!r}; known: {', '.join(SCHEMAS)}")
    return SCHEMAS[name]


def read_rows(folder, name):
    """Rows of a contract CSV as dicts of strings. A missing file is an empty list."""
    path = Path(folder) / name
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:g}" if abs(v) < 1e15 else repr(v)
    return str(v)


def upsert_rows(folder, name, rows):
    """Insert or replace rows by the file's key. Existing order is kept; new rows are appended in order.
    Returns (added, replaced). Writes atomically. Unknown columns or a blank key raise ValueError."""
    columns, key = _schema(name)
    path = Path(folder) / name
    existing = read_rows(folder, name)
    index = {tuple(r[k] for k in key): i for i, r in enumerate(existing)}
    added = replaced = 0
    for row in rows:
        extra = set(row) - set(columns)
        if extra:
            raise ValueError(f"{name}: unknown column(s) {sorted(extra)}")
        clean = {c: _cell(row.get(c)) for c in columns}
        k = tuple(clean[c] for c in key)
        if not all(k):
            raise ValueError(f"{name}: blank key {dict(zip(key, k))}")
        if k in index:
            if existing[index[k]] != clean:
                existing[index[k]] = clean
                replaced += 1
        else:
            index[k] = len(existing)
            existing.append(clean)
            added += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in columns} for r in existing)
    os.replace(tmp, path)
    return added, replaced


def append_log(folder, skill, result, date=None):
    """Append one line to log.md: `- YYYY-MM-DD · skill · result`."""
    date = date or datetime.date.today().isoformat()
    line = f"- {date} · {skill} · {' '.join(str(result).split())}\n"
    path = Path(folder) / "log.md"
    if not path.exists():
        path.write_text("# Log\n\nOne line per skill run.\n\n", encoding="utf-8")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
    return line


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find")
    f.add_argument("--dir")
    i = sub.add_parser("init")
    i.add_argument("dir")
    lg = sub.add_parser("log")
    lg.add_argument("skill")
    lg.add_argument("result")
    lg.add_argument("--dir")
    a = p.parse_args(argv)
    try:
        if a.cmd == "find":
            print(find(a.dir))
        elif a.cmd == "init":
            made = init(a.dir)
            print("\n".join(made) if made else "nothing to create: the folder is already set up")
        else:
            print(append_log(find(a.dir), a.skill, a.result), end="")
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
