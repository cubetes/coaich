#!/usr/bin/env python3
"""The athlete folder (plugin/docs/athlete-folder.md): find it, read and upsert its CSVs, append log.md.

Usage:
  athlete_folder.py find [--dir D]              print the athlete folder (the one holding coaich.md)
  athlete_folder.py init DIR                    create the folder from the template; never overwrites
  athlete_folder.py log SKILL RESULT [--dir D]  append "date · skill · result" to log.md

Library: find(), setting(), read_rows(), upsert_rows(), write_rows(), replace_sessions(), set_header(),
append_log().
Python stdlib only.
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
    "data/exercise_map.csv": (["exercise", "exercise_id"], ("exercise",)),
}


def find(start=None):
    """The nearest folder at or above `start` (default: cwd) that holds coaich.md. FileNotFoundError if none."""
    here = Path(start or os.getcwd()).resolve()
    for d in (here, *here.parents):
        if (d / MARKER).is_file():
            return d
    raise FileNotFoundError(f"no {MARKER} in {here} or above: run /onboard to set up an athlete folder")


def setting(folder, key):
    """A `key: value` line from coaich.md, lower-cased, or None."""
    with open(Path(folder) / MARKER, encoding="utf-8") as f:
        for line in f:
            k, sep, v = line.split("#")[0].strip().lstrip("-* ").partition(":")
            if sep and k.strip().lower() == key:
                return v.strip().strip("`\"'").lower() or None
    return None


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


def write_rows(folder, name, rows):
    """Replace the whole file with `rows` (the file's columns, in that order). Atomic: temp file + rename."""
    columns, _ = _schema(name)
    path = Path(folder) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows({c: _cell(r.get(c)) for c in columns} for r in rows)
    os.replace(tmp, path)


def upsert_rows(folder, name, rows):
    """Insert or replace rows by the file's key. Existing order is kept; new rows are appended in order.
    Returns (added, replaced). Writes atomically. Unknown columns or a blank key raise ValueError."""
    columns, key = _schema(name)
    existing = read_rows(folder, name)
    index = {tuple(r.get(k, "") for k in key): i for i, r in enumerate(existing)}
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
    write_rows(folder, name, existing)
    return added, replaced


def replace_sessions(folder, sets, sessions):
    """Write whole sessions into sets.csv + sessions.csv. A session replaces every stored session with the same
    session_id, or with the same start minute + workout name (the same workout seen through another export, e.g.
    Hevy CSV then Hevy MCP), sets included: a set deleted at the source disappears here too. Safe to run again.
    Keeps a hand-filled `gym` on a replaced session. Returns (n_new, n_replaced)."""
    old_sets, old_sess = read_rows(folder, "data/sets.csv"), read_rows(folder, "data/sessions.csv")

    def same(r):
        return (r["datetime"][:16], r["workout_name"].strip().lower())

    new_ids = {s["session_id"] for s in sessions}
    new_keys = {same(s) for s in sessions}
    gone = {s["session_id"] for s in old_sess if s["session_id"] in new_ids or same(s) in new_keys}
    gyms = {}
    for s in old_sess:
        if s["session_id"] in gone and s.get("gym"):
            gyms[s["session_id"]] = gyms[same(s)] = s["gym"]
    for s in sessions:
        s["gym"] = s.get("gym") or gyms.get(s["session_id"]) or gyms.get(same(s), "")

    all_sets = [r for r in old_sets if r["session_id"] not in gone] + list(sets)
    all_sess = [s for s in old_sess if s["session_id"] not in gone] + list(sessions)
    all_sets.sort(key=lambda r: (r["datetime"], r["session_id"]))  # stable: keeps set order within a session
    all_sess.sort(key=lambda s: (s["datetime"], s["session_id"]))
    write_rows(folder, "data/sets.csv", all_sets)
    write_rows(folder, "data/sessions.csv", all_sess)
    old_ids, old_keys = {s["session_id"] for s in old_sess}, {same(s) for s in old_sess}
    replaced = sum(1 for s in sessions if s["session_id"] in old_ids or same(s) in old_keys)
    return len(sessions) - replaced, replaced


def set_header(folder, name, key, value):
    """Set one top-level key in a Markdown file's YAML header (profile.md, coaich.md) to `value`, YAML text written
    as given (`[]`, `[{area: knee, red_flag: true}]`, `2030-04-01`). Replaces the key's line and any indented lines
    under it, keeps its trailing comment, or adds the key before the closing `---`. Atomic."""
    path = Path(folder) / name
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{name} has no YAML header")
    end = next((i for i, x in enumerate(lines[1:], 1) if x.strip() == "---"), None)
    if end is None:
        raise ValueError(f"{name}: the YAML header has no closing ---")
    i = next((i for i in range(1, end) if lines[i].split(":", 1)[0] == key), None)
    if i is None:
        lines.insert(end, f"{key}: {value}")
    else:
        j = i + 1
        while j < end and lines[j].startswith((" ", "-")) and lines[j].strip():
            j += 1
        rest = lines[i].split(":", 1)[1]
        comment = rest[rest.index(" #"):].strip() if " #" in rest else ""
        lines[i:j] = [f"{key}: {value}" + (f"  {comment}" if comment else "")]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


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
