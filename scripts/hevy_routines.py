#!/usr/bin/env python3
"""Hevy routines from the athlete's applied targets (or the program), and a read-back check.

This script never talks to Hevy. Claude sends what it builds through the Hevy MCP server (create-routine /
update-routine) and saves what get-routine returns; `verify` compares the two.

    python3 hevy_routines.py build  --dir . [--week 2030-W13 | --program]
    python3 hevy_routines.py template --dir . EXERCISE_ID TEMPLATE_ID [HEVY_TITLE]
    python3 hevy_routines.py verify --dir . --week 2030-W13 <get-routine.json> [...]

build: one routine per program routine, titled "<routine> · CoAIch", exercises in program order, the week's
targets as sets (reps and kg; no kg while a weight is still unknown), the program's rest and rep range, and the
reason for the target as the exercise note. Default week: the newest applied targets file. --program: the
program's sets (first push, no weights yet). Writes data/hevy/routines_<week>.json only when every exercise
has a Hevy template id; otherwise it lists the missing ones and exits 2.

Template ids come from data/hevy_templates.csv, which `build` first fills from imported Hevy workouts
(data/raw/hevy/*.json, matched through data/exercise_map.csv). `template` saves one the user chose.

verify: every built routine must come back with the same exercises (template ids, in order) and sets (type,
kg, reps). Exit 1 on any difference or a routine with no read-back file.
"""
import argparse
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402
import exercise_map  # noqa: E402
import progression as pg  # noqa: E402

TEMPLATES = "data/hevy_templates.csv"   # optional, so not in athlete_folder.SCHEMAS
COLUMNS = ["exercise_id", "template_id", "hevy_title"]
SUFFIX = " · CoAIch"


def save_templates(folder, rows):
    path = os.path.join(folder, TEMPLATES)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["exercise_id"]))
    os.replace(path + ".tmp", path)


def templates(folder):
    """exercise_id -> template_id, after learning any new pairs from imported Hevy workouts."""
    rows = {r["exercise_id"]: r for r in af.read_rows(folder, TEMPLATES)}
    by_title = {exercise_map.norm(r["exercise"]): r["exercise_id"]
                for r in af.read_rows(folder, "data/exercise_map.csv")}
    learned = False
    for path in sorted(glob.glob(os.path.join(folder, "data", "raw", "hevy", "*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        ws = [doc["workout"]] if isinstance(doc, dict) and isinstance(doc.get("workout"), dict) else \
            doc.get("workouts", []) if isinstance(doc, dict) else doc if isinstance(doc, list) else []
        for w in ws:
            for ex in (w.get("exercises") or []) if isinstance(w, dict) else []:
                eid = by_title.get(exercise_map.norm(ex.get("title", "")))
                if eid and ex.get("exercise_template_id") and eid not in rows:
                    rows[eid] = {"exercise_id": eid, "template_id": ex["exercise_template_id"],
                                 "hevy_title": ex.get("title", "")}
                    learned = True
    if learned:
        save_templates(folder, rows)
    return {k: r["template_id"] for k, r in rows.items() if r.get("template_id")}


def newest_applied(folder):
    files = [(lb, p) for lb, p in pg.list_target_files(folder) if pg.load_json(p).get("status") == "applied"]
    if not files:
        raise SystemExit("No applied targets yet: run the weekly review first, or use --program.")
    return files[-1][0]


def build(folder, week=None, program_only=False):
    """-> (label, routines, missing [(routine, exercise_id, name)])."""
    program = pg.load_program(folder)
    lang = af.setting(folder, "language") or "en"
    if program_only:
        label, status, rows = "program", None, pg.program_rows(program)
    else:
        label = week or newest_applied(folder)
        doc = pg.load_json(pg.targets_path(folder, label))
        if doc.get("status") != "applied":
            raise SystemExit(f"targets_{label}.json is {doc.get('status')}, not applied: only accepted targets go to Hevy.")
        status, rows = doc["status"], doc["rows"]
    tids = templates(folder)
    spec = {(rt["title"], i): ex for rt in program.get("routines", [])
            for i, ex in enumerate(rt.get("exercises", []), 1)}
    routines, missing = {}, []
    for r in rows:
        ex = spec.get((r["routine"], r.get("slot")), {})
        sets = r.get("spec_sets") if program_only else pg.effective_target(r, status)
        rr = r.get("rep_range") or ex.get("rep_range")
        out = []
        for s in sets or []:
            hs = {"type": s.get("type") or "normal", "reps": int(s["reps"])}
            if s.get("kg") is not None:
                hs["weight_kg"] = float(s["kg"])
            if rr:
                hs["rep_range"] = {"start": int(rr[0]), "end": int(rr[1])}
            out.append(hs)
        if not out:
            continue
        tid = tids.get(r["exercise_id"])
        if not tid and r["exercise_id"] not in {m[1] for m in missing}:
            missing.append((r["routine"], r["exercise_id"], r.get("name") or r["exercise_id"]))
        e = {"exercise_template_id": tid or "", "sets": out}
        if ex.get("rest_seconds"):
            e["rest_seconds"] = int(ex["rest_seconds"])
        note = "" if program_only else pg.render(r.get("reason"), lang)
        if note:
            e["notes"] = note       # Hevy refuses an empty note on update, so none at all instead
        routines.setdefault(r["routine"], {"title": r["routine"] + SUFFIX, "exercises": []})["exercises"].append(e)
    return label, list(routines.values()), missing


def compare(built, got):
    """Differences between one built routine and get-routine's routine, as sentences."""
    diffs = []
    b_ex, g_ex = built["exercises"], sorted(got.get("exercises") or [], key=lambda e: e.get("index", 0))
    if len(b_ex) != len(g_ex):
        return [f"{len(g_ex)} exercises in Hevy, {len(b_ex)} sent"]
    for i, (b, g) in enumerate(zip(b_ex, g_ex), 1):
        if b["exercise_template_id"] != g.get("exercise_template_id"):
            diffs.append(f"exercise {i}: template {g.get('exercise_template_id')} in Hevy, {b['exercise_template_id']} sent")
            continue
        gs = sorted(g.get("sets") or [], key=lambda s: s.get("index", 0))
        if len(gs) != len(b["sets"]):
            diffs.append(f"exercise {i} ({g.get('title')}): {len(gs)} sets in Hevy, {len(b['sets'])} sent")
            continue
        for j, (bs, s) in enumerate(zip(b["sets"], gs), 1):
            kg_b, kg_g = bs.get("weight_kg"), s.get("weight_kg")
            same_kg = (kg_b is None and not kg_g) or (kg_b is not None and kg_g is not None
                                                     and abs(float(kg_g) - kg_b) < 0.01)
            if not same_kg or s.get("reps") != bs["reps"] or (s.get("type") or "normal") != bs["type"]:
                diffs.append(f"exercise {i} ({g.get('title')}) set {j}: {kg_g} kg × {s.get('reps')} in Hevy, "
                             f"{kg_b} kg × {bs['reps']} sent")
    return diffs


def verify(folder, label, files):
    path = os.path.join(folder, "data", "hevy", f"routines_{label}.json")
    if not os.path.exists(path):
        raise SystemExit(f"{path} missing: run build first.")
    with open(path, encoding="utf-8") as fh:
        built = json.load(fh)["routines"]
    got = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            doc = json.load(fh)
        rt = doc.get("routine", doc) if isinstance(doc, dict) else {}
        got[rt.get("title")] = rt
    ok = True
    for b in built:
        if b["title"] not in got:
            print(f"missing {b['title']}: no read-back file")
            ok = False
            continue
        diffs = compare(b, got[b["title"]])
        print(f"ok {b['title']}" if not diffs else f"different {b['title']}: " + "; ".join(diffs))
        ok = ok and not diffs
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dir", default=".")
    g = b.add_mutually_exclusive_group()
    g.add_argument("--week")
    g.add_argument("--program", action="store_true")
    t = sub.add_parser("template")
    t.add_argument("--dir", default=".")
    t.add_argument("exercise_id")
    t.add_argument("template_id")
    t.add_argument("hevy_title", nargs="?", default="")
    v = sub.add_parser("verify")
    v.add_argument("--dir", default=".")
    v.add_argument("--week", required=True)
    v.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    folder = a.dir
    if a.cmd == "template":
        rows = {r["exercise_id"]: r for r in af.read_rows(folder, TEMPLATES)}
        rows[a.exercise_id] = {"exercise_id": a.exercise_id, "template_id": a.template_id, "hevy_title": a.hevy_title}
        save_templates(folder, rows)
        print(f"saved {a.exercise_id} → {a.template_id}")
        return 0
    if a.cmd == "verify":
        return 0 if verify(folder, a.week, a.files) else 1
    af.safety_stop(folder, "nothing is sent to Hevy")
    label, routines, missing = build(folder, a.week, a.program)
    if missing:
        print("No Hevy exercise yet for:")
        for rt, eid, name in missing:
            print(f"  {rt}: {name} ({eid})")
        print("Find each with search-exercise-templates, then: hevy_routines.py template --dir . <exercise_id> <template_id> \"<Hevy title>\"")
        return 2
    path = os.path.join(folder, "data", "hevy", f"routines_{label}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"week": label, "routines": routines}, fh, ensure_ascii=False, indent=1)
    for rt in routines:
        print(f"{rt['title']}: {len(rt['exercises'])} exercises, {sum(len(e['sets']) for e in rt['exercises'])} sets")
    print(f"→ {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
