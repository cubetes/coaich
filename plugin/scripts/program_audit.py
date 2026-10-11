#!/usr/bin/env python3
"""Audit a training program against the CoAIch gates G1–G9.

Usage: python3 program_audit.py --dir <athlete folder>      reads plan/program.json, prints the report
       python3 program_audit.py --program <file.json> [--json]

A gate fails a program unless the miss is in KNOWN_MISSES (a literal list, each with its reason). G9 and the
preferences P1–P4 never fail: they are reported as notes. Exit 0 = passes, 1 = an unexpected gate failure,
2 = the program file is unusable.

The rules are a faithful port of the Release 1 Swift core (AthleteCore `ProgramAudit.swift`); thresholds may
only change with a written source beside them (references/evidence.md, references/volume-landmarks.md).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOGUE_PATH = os.path.join(HERE, "..", "data", "exercises.json")

# Movement slots (references/starter-programs.md §Slots). Isolation slots have no effort floor.
ISOLATION = {"KE", "KF", "FL", "LR", "RD", "CU", "TE", "CA", "CO", "ISO"}
LOWER_BODY = {"SQ", "SM", "HI", "LU", "KE", "KF", "CA"}

# Per slot: [0] the usual pick, the rest its alternatives and same-day fallbacks (gym column).
COLUMN = {
    "SQ": ["Barbell_Squat", "Goblet_Squat", "Hack_Squat", "Front_Barbell_Squat"],
    "SM": ["Leg_Press", "Hack_Squat"],
    "HI": ["Romanian_Deadlift", "Stiff-Legged_Dumbbell_Deadlift", "Barbell_Hip_Thrust", "Barbell_Deadlift"],
    "LU": ["Split_Squat_with_Dumbbells", "Dumbbell_Step_Ups"],
    "KE": ["Leg_Extensions"],
    "KF": ["Lying_Leg_Curls", "Seated_Leg_Curl"],
    "HP": ["Barbell_Bench_Press_-_Medium_Grip", "Dumbbell_Bench_Press", "Machine_Bench_Press", "Incline_Dumbbell_Press",
           "Barbell_Incline_Bench_Press_-_Medium_Grip"],
    "VP": ["Standing_Military_Press", "Dumbbell_Shoulder_Press", "Machine_Shoulder_Military_Press"],
    "FL": ["Flat_Bench_Cable_Flyes", "Dumbbell_Flyes", "Incline_Dumbbell_Flyes"],
    "HR": ["Seated_Cable_Rows", "Leverage_Iso_Row", "Bent_Over_Barbell_Row"],
    "VR": ["Wide-Grip_Lat_Pulldown", "Close-Grip_Front_Lat_Pulldown", "Pullups", "Weighted_Pull_Ups"],
    "LR": ["Side_Lateral_Raise", "Cable_Seated_Lateral_Raise"],
    "RD": ["Face_Pull", "Reverse_Machine_Flyes", "Cable_Rear_Delt_Fly"],
    "CU": ["Dumbbell_Bicep_Curl", "Standing_Biceps_Cable_Curl", "Hammer_Curls", "EZ-Bar_Curl", "Barbell_Curl"],
    "TE": ["Cable_Rope_Overhead_Triceps_Extension", "Triceps_Pushdown"],  # overhead first (G9)
    "CA": ["Standing_Calf_Raises", "Seated_Calf_Raise"],
    "CO": ["Dead_Bug", "Plank", "Cable_Crunch", "Knee_Hip_Raise_On_Parallel_Bars", "Flat_Bench_Lying_Leg_Raise",
           "Hanging_Leg_Raise"],
}
PATTERN_OF = {}
for _p, _ids in COLUMN.items():
    for _id in _ids:
        PATTERN_OF.setdefault(_id, _p)

# Spine-loading exercises: axial load standing, a loaded hinge, or a loaded lunge. A low back never gets one.
SPINE = {
    "Barbell_Squat", "Front_Barbell_Squat", "Box_Squat", "Hack_Squat", "Leg_Press", "Dumbbell_Squat",
    "Dumbbell_Squat_To_A_Bench", "Barbell_Lunge", "Dumbbell_Lunges", "Split_Squat_with_Dumbbells", "Dumbbell_Step_Ups",
    "Romanian_Deadlift", "Stiff-Legged_Dumbbell_Deadlift", "Kettlebell_One-Legged_Deadlift", "Barbell_Deadlift",
    "Trap_Bar_Deadlift", "Good_Morning", "Standing_Military_Press", "Bent_Over_Barbell_Row",
}

# The slots that load a painful area (left out while its red flag is unchecked).
AREA_PATTERNS = {
    "knee": ["SQ", "SM", "LU", "KE"],
    "low_back": ["SQ", "SM", "HI", "LU"],
    "hip": ["SQ", "SM", "HI", "LU"],
    "shoulder": ["HP", "VP", "FL", "LR", "VR"],
    "elbow_wrist": ["CU", "TE"],
    "other": [],
}

# MRV (effective sets a week): a practitioner coaching band (RP), the only band number that is a gate (G2).
MRV = {
    "chest": 22, "delts_side": 26, "delts_rear": 25, "delts_front": 12, "lats": 25, "upper_back": 25, "traps": 26,
    "biceps": 26, "triceps": 18, "quadriceps": 20, "hamstrings": 20, "glutes": 16, "calves": 20, "abdominals": 25,
}
# Groups for G1 and G3: delt heads are one group, back = lats + upper back.
GROUPS = [
    ("chest", ["chest"]), ("back", ["lats", "upper_back"]), ("quads", ["quadriceps"]), ("hamstrings", ["hamstrings"]),
    ("delts", ["delts_side", "delts_rear", "delts_front"]), ("biceps", ["biceps"]), ("triceps", ["triceps"]),
    ("calves", ["calves"]),
]
OVERHEAD_TRICEPS = {"Cable_Rope_Overhead_Triceps_Extension", "Standing_Dumbbell_Triceps_Extension",
                    "Dumbbell_One-Arm_Triceps_Extension"}
EASY_WEEK_EVERY = {"beginner": None, "intermediate": 7, "advanced": 6}

_TWO_SHORT = "2 days at 30–45 minutes is the minimum dose: one paired press and pull a session; the plan says so."
_TWO_DAYS = "2 days a week cannot reach 10 sets for the big four in two sessions (minimum-dose line)."
_SHORT_B = "Session B's 30/45-minute versions keep the leg press, not a press, so chest is trained in session A only."
_THREE_SHORT = "3 × 30 minutes: quads get one squat pair a session (short-session line)."
_DEADLIFT_HAMS = ("Strength goal: the hinge is the deadlift, which the catalogue counts as lower-back work with "
                  "hamstrings at half.")
_DEADLIFT_BACK = ("Strength goal: the deadlift's lats and upper-back tags add a back set per set on top of a back "
                  "already near the MRV band (practitioner).")
_PRIORITY_BACK = ("Back priority on 5 days: four upper/lower days already reach the back's MRV band; the priority day "
                  "is trimmed to 2 + 2 sets and still adds.")
_PAIN_DELTS = ("Pain swaps (the goblet squat, the neutral-grip pulldown) carry a shoulder tag, adding front-delt work "
               "on the two highest-volume layouts; delts as a group pass the side-delt MRV band (practitioner).")

# (program tokens, gate, group, value, reason). Same tokens as the program's name = that exact program and value;
# fewer tokens (a family) = the value may be no worse (G1/G3 not lower, G2 not higher).
KNOWN_MISSES = [
    ("fb2b·30", 1, "biceps", 2.5, _TWO_SHORT), ("fb2b·30", 1, "chest", 2, _TWO_SHORT),
    ("fb2b·30", 1, "triceps", 2.5, _TWO_SHORT), ("fb2b·30", 3, "chest", 1, _SHORT_B),
    ("fb2b·45", 3, "chest", 1, _SHORT_B),
    ("fb2i·30", 1, "biceps", 2.5, _TWO_SHORT), ("fb2i·30", 1, "chest", 2, _TWO_SHORT),
    ("fb2i·30", 1, "quads", 5, _TWO_SHORT), ("fb2i·30", 1, "triceps", 2.5, _TWO_SHORT),
    ("fb2i·30", 3, "chest", 1, _SHORT_B),
    ("fb2i·45", 1, "biceps", 3, _TWO_SHORT), ("fb2i·45", 1, "chest", 5, _TWO_SHORT),
    ("fb2i·45", 1, "triceps", 2.5, _TWO_SHORT),
    ("fb2i·60", 1, "biceps", 3, _TWO_DAYS), ("fb2i·60", 1, "chest", 7, _TWO_DAYS),
    ("fb2i·60", 1, "hamstrings", 9, _TWO_DAYS), ("fb2i·60", 1, "quads", 6, _TWO_DAYS),
    ("fb2i·75", 1, "chest", 7, _TWO_DAYS), ("fb2i·75", 1, "hamstrings", 9, _TWO_DAYS),
    ("fb2i·75", 1, "quads", 6, _TWO_DAYS),
    ("fb3b·30", 3, "chest", 1.5, _SHORT_B), ("fb3b·45", 3, "chest", 1.5, _SHORT_B),
    ("fb3i·30", 1, "quads", 5, _THREE_SHORT),
    # Modifiers (families): no worse than the value.
    ("fb2i·strength", 1, "hamstrings", 5.5, _DEADLIFT_HAMS),
    ("ppl6i·strength", 2, "back", 28, _DEADLIFT_BACK),
    ("ulf5i·strength", 2, "back", 29.5, _DEADLIFT_BACK),
    ("ulf5i·back", 2, "back", 26.5, _PRIORITY_BACK),
    ("ppl6i·pain", 2, "delts", 28.5, _PAIN_DELTS),
    ("ulf5i·pain", 2, "delts", 26.5, _PAIN_DELTS),
]

GATE_NAMES = {
    1: "Weekly effective sets per group ≥ floor", 2: "No group over the MRV band", 3: "Every group in ≥ 2 sessions",
    4: "Every session within the minutes", 5: "Effort bounds", 6: "Pain rules", 7: "Exercises valid",
    8: "Sets per exercise", 9: "Overhead triceps preferred",
}
GATE_SOURCES = {
    1: "≥ 4 sets: Schoenfeld 2017 (SR/MA); ≥ 10: Currier 2026 (SR/MA); 3 and 6 at 30/45 min: our rule",
    2: "RP coaching bands (practitioner, P)",
    3: "Pelland 2025, Currier 2026 (SR/MA; strength and session length, not size)",
    4: "the athlete's own answer (time formula: our rule)",
    5: "Robinson 2024, Refalo 2023 (SR/MA); spine lifts ≥ 2 left: our rule",
    6: "our rule (injury swaps)",
    7: "our rule (catalogue ids, ≤ 7 exercises, pairs of two)",
    8: "Krieger 2010 (SR/MA); 60+ at 2 sets: Fragala 2019 (position stand)",
    9: "Maeo 2023 (RCT, one study) — preference",
}


def load_catalogue(path=CATALOGUE_PATH):
    with open(path, encoding="utf-8") as f:
        out = {}
        for e in json.load(f):
            out.setdefault(e["id"], e)
        return out


CATALOGUE = load_catalogue()


def fmt(v):
    return f"{v:g}"


def variant(minutes):
    return [m for m in (30, 45, 60, 75) if m <= max(30, minutes)][-1]


def is_isolation(slot):
    return slot["pattern"] in ISOLATION


def routine_minutes(exercises):
    """8 min warm-up + each working set × 3.25 min (compound) or 2.0 min (isolation, or either half of a pair)."""
    return 8 + sum(e["sets"] * (2 if e.get("pair") is not None or e["pattern"] in ISOLATION else 3.25) for e in exercises)


def muscles(ex):
    """Effective sets: primary ×1, each secondary ×0.5; "shoulders" split into heads by name, "middle back" = upper back."""
    name = ex["name"].lower()

    def key(m):
        if m == "shoulders":
            if any(w in name for w in ("rear delt", "face pull")) or ("reverse" in name and "fly" in name):
                return "delts_rear"
            if any(w in name for w in ("lateral raise", "upright row")):
                return "delts_side"
            return "delts_front"
        if m == "middle back":
            return "upper_back"
        return m if m in MRV else None

    return [(k, 1.0) for k in map(key, ex["primaryMuscles"]) if k] + \
           [(k, 0.5) for k in map(key, ex["secondaryMuscles"]) if k]


def program_name(p):
    """Layout · time variant, then the modifiers that change volume (strength goal, priority region, pain)."""
    if not p.get("layout"):
        return "custom"
    return (f"{p['layout']}·{variant(p['minutes'])}" + ("·strength" if p.get("goal") == "strength" else "")
            + (f"·{p['priority']}" if p.get("priority") else "") + ("·pain" if p.get("pain") else ""))


def volume(p, catalogue=CATALOGUE):
    """Effective sets a week per muscle and per group, and sessions a week per group; each routine weighs days ÷ routines."""
    sets, sessions = {}, {}
    weight = p["days"] / len(p["routines"])
    for r in p["routines"]:
        today = set()
        for s in r["exercises"]:
            ex = catalogue.get(s["exercise_id"])
            if not ex:
                continue
            for m, w in muscles(ex):
                sets[m] = sets.get(m, 0) + w * s["sets"] * weight
                today.add(m)
        for g, ms in GROUPS:
            if any(m in today for m in ms):
                sessions[g] = sessions.get(g, 0) + weight
    groups = {g: sum(sets.get(m, 0) for m in ms) for g, ms in GROUPS}
    return sets, groups, sessions


def _beginner_ramp(p):
    return p["level"] == "beginner" and p.get("week", 99) <= 4


def _older_ramp(p):
    return p.get("older", False) and p.get("week", 99) <= 8


def floors(p):
    short = variant(p["minutes"]) <= 45 if p.get("minutes") else False
    if p["level"] == "beginner":
        return {g: (3 if short else 4) for g, _ in GROUPS if g != "calves"}
    big = 6 if short else 10
    return {"chest": big, "back": big, "quads": big, "hamstrings": big, "delts": 4, "biceps": 4, "triceps": 4, "calves": 4}


def floors_apply(p):
    """Not in the ramp weeks (they run 2 sets on purpose) and not with pain (exercises are left out on purpose)."""
    return not _beginner_ramp(p) and not _older_ramp(p) and not p.get("pain")


def max_sets(level):
    return 3 if level == "beginner" else 4


def audit(p, catalogue=CATALOGUE):
    """G1–G9 → list of {gate, passed, warn_only, detail, misses: [(group, value)]}."""
    m_sets, groups, sessions = volume(p, catalogue)
    slots = [s for r in p["routines"] for s in r["exercises"]]
    pain = p.get("pain", [])
    out = []

    def check(gate, passed, detail, misses=(), warn_only=False):
        out.append({"gate": gate, "passed": passed, "warn_only": warn_only, "detail": detail, "misses": list(misses)})

    fa = floors_apply(p)
    under = sorted(((g, groups.get(g, 0)) for g, f in floors(p).items() if groups.get(g, 0) < f)) if fa else []
    check(1, not under, ("under the floor: " + ", ".join(f"{g} {fmt(v)}" for g, v in under)) if fa
          else "floors apply from the steady weeks, without pain", under)

    limits = {g: (groups.get(g, 0), max(MRV[m] for m in ms)) for g, ms in GROUPS}
    for m, cap in MRV.items():
        if not any(m in ms for _, ms in GROUPS):
            limits[m] = (m_sets.get(m, 0), cap)
    over = sorted((k, v) for k, (v, cap) in limits.items() if v > cap)
    check(2, not over, "over MRV: " + ", ".join(f"{g} {fmt(v)}" for g, v in over), over)

    rare = [(g, sessions.get(g, 0)) for g, _ in GROUPS
            if not (p["level"] == "beginner" and g == "calves") and sessions.get(g, 0) < 2] if not pain else []
    check(3, not rare, "under 2 sessions: " + ", ".join(f"{g} {fmt(v)}" for g, v in rare), rare)

    if p.get("minutes"):
        long_ = [(r["title"], routine_minutes(r["exercises"])) for r in p["routines"]
                 if routine_minutes(r["exercises"]) > p["minutes"] + 1e-9]
        check(4, not long_, f"over {p['minutes']} min: " + ", ".join(f"{t} {fmt(v)}" for t, v in long_))
    else:
        check(4, True, "no minutes answer: not checked")

    def effort_floor(s):
        if is_isolation(s):
            return 0
        return 2 if _beginner_ramp(p) or s["exercise_id"] in SPINE else 1
    hard = [s["exercise_id"] for s in slots if s["rir"][0] < effort_floor(s) or s["rir"][0] > s["rir"][1]]
    check(5, not hard, "effort out of bounds: " + ", ".join(hard))

    bad = []
    for i in pain:
        area, active = i["area"], i.get("red_flag", False) and not i.get("checked", False)
        if area == "low_back":
            bad += [x for s in slots for x in [s["exercise_id"]] + s.get("alternatives", []) if x in SPINE]
        if active:
            bad += [s["exercise_id"] for s in slots if s["pattern"] in AREA_PATTERNS[area]]
        if area == "shoulder":
            bad += [s["exercise_id"] for s in slots if s["pattern"] == "FL"]
        if area == "knee":
            bad += [s["exercise_id"] for s in slots if s["pattern"] == "KE"]
    check(6, not bad, "loads a painful area: " + ", ".join(bad))

    g7 = []
    for r in p["routines"]:
        ex = r["exercises"]
        for x in [y for s in ex for y in [s["exercise_id"]] + s.get("alternatives", [])]:
            if x not in catalogue:
                g7.append(f"unknown {x}")
        if len({s["exercise_id"] for s in ex}) < len(ex):
            g7.append(f"{r['title']}: an exercise twice")
        if len(ex) > 7:
            g7.append(f"{r['title']}: {len(ex)} exercises")
        for pair in {s.get("pair") for s in ex} - {None}:
            if sum(1 for s in ex if s.get("pair") == pair) != 2:
                g7.append(f"{r['title']}: pair {pair}")
    check(7, not g7, "; ".join(g7))

    cap = 2 if _older_ramp(p) else max_sets(p["level"])
    many = [s["exercise_id"] for s in slots if s["sets"] > cap]
    check(8, not many, f"over {cap} sets: " + ", ".join(many))

    te = [s for s in slots if s["pattern"] == "TE"]
    has_overhead = any(s["exercise_id"] in OVERHEAD_TRICEPS for s in te)
    check(9, not te or has_overhead, f"overhead triceps: {str(has_overhead).lower()}", warn_only=True)
    return out


def is_known(p, gate, miss):
    mine = program_name(p).split("·")
    group, value = miss
    for prog, g, m, v, _ in KNOWN_MISSES:
        tokens = prog.split("·")
        if g != gate or m != group or not set(tokens) <= set(mine):
            continue
        if len(tokens) == len(mine):
            if abs(v - value) < 0.01:
                return True
        elif (value <= v + 0.01) if gate == 2 else (value >= v - 0.01):
            return True
    return False


def known_reason(p, gate, miss):
    mine = set(program_name(p).split("·"))
    return next((r for prog, g, m, v, r in KNOWN_MISSES if g == gate and m == miss[0] and set(prog.split("·")) <= mine), "")


def unexpected_failures(p, checks=None):
    """The G1–G3 misses not in KNOWN_MISSES, plus any failed G4–G8."""
    out = []
    for c in checks or audit(p):
        if c["passed"] or c["warn_only"]:
            continue
        if c["gate"] in (1, 2, 3):
            out += [f"G{c['gate']}: {m} {fmt(v)}" for m, v in c["misses"] if not is_known(p, c["gate"], (m, v))]
        else:
            out.append(f"G{c['gate']}: {c['detail']}")
    return out


def preferences(p, catalogue=CATALOGUE):
    """P1–P4: never failures. Each → (id, met, text, source)."""
    slots = [s for r in p["routines"] for s in r["exercises"]]
    ids = [s["exercise_id"] for s in slots]
    names = [catalogue.get(i, {}).get("name", i).lower() for i in ids]
    trained = p["level"] != "beginner"
    out = []
    rear = any(s["pattern"] == "RD" for s in slots) or any("rear delt" in n or "face pull" in n for n in names)
    out.append(("P1", rear or not trained, "A direct rear-delt exercise in the week (intermediate and up)",
                "our rule (P); no training study sets a rear-delt dose"))
    calves = [i for i, s in zip(ids, slots) if s["pattern"] == "CA"]
    standing = not calves or any("standing" in catalogue.get(i, {}).get("name", "").lower() for i in calves)
    out.append(("P2", standing, "A standing calf raise when calves are trained",
                "Kinoshita, Maeo 2023 (RCT, small, untrained)"))
    want = EASY_WEEK_EVERY.get(p["level"])
    have = p.get("easy_week_every", want)
    out.append(("P3", have == want, f"Easy week every {want}th week" if want else "No planned easy week (triggered only)",
                "Coleman 2024, Pancar 2026 (RCT) for the shape; the interval is our rule (P)"))
    chain = not trained or p.get("goal") == "muscle" or any(s["rep_range"][0] <= 6 or s.get("main") for s in slots)
    out.append(("P4", chain, "A heavier main lift (strength or both goal, intermediate and up)",
                "Moesgaard 2022 (SR/MA: 1RM in trained lifters only, small)"))
    return out


def normalise(p, catalogue=CATALOGUE):
    """Fill what a hand-written program may lack: patterns (from the slot column, else the catalogue's mechanic)."""
    for k in ("level", "days", "routines"):
        if k not in p:
            raise ValueError(f"program.json needs '{k}'")
    if p["level"] not in EASY_WEEK_EVERY:
        raise ValueError(f"level must be one of {sorted(EASY_WEEK_EVERY)}")
    for r in p["routines"]:
        r.setdefault("title", r.get("key", "?"))
        for s in r["exercises"]:
            if "pattern" not in s:
                ex = catalogue.get(s["exercise_id"], {})
                s["pattern"] = PATTERN_OF.get(s["exercise_id"]) or ("ISO" if ex.get("mechanic") == "isolation" else "CMP")
            s.setdefault("rir", s.get("reps_left") or (
                [0, 2] if s["pattern"] in ISOLATION else [2, 2] if s["exercise_id"] in SPINE else [1, 2]))
            s.setdefault("alternatives", [])
    return p


def report(p, catalogue=CATALOGUE):
    """Markdown: gates with value and source, then notes (preferences and known misses)."""
    checks = audit(p, catalogue)
    unexpected = unexpected_failures(p, checks)
    _, groups, sessions = volume(p, catalogue)
    lines = [f"# Program audit — {program_name(p)}", "",
             f"**Result: {'passes' if not unexpected else 'FAILS'}** "
             f"({len(unexpected)} unexpected gate failure{'s' if len(unexpected) != 1 else ''}).", "",
             "| Gate | Check | Result | Detail | Source |", "|---|---|---|---|---|"]
    for c in checks:
        g = c["gate"]
        if c["warn_only"]:
            res = "note" if not c["passed"] else "met"
        elif c["passed"]:
            res = "pass"
        elif g in (1, 2, 3) and all(is_known(p, g, m) for m in c["misses"]):
            res = "known miss"
        else:
            res = "**FAIL**"
        detail = c["detail"] if not c["passed"] or c["detail"].startswith("no ") else "—"
        lines.append(f"| G{g} | {GATE_NAMES[g]} | {res} | {detail} | {GATE_SOURCES[g]} |")
    lines += ["", "Effective sets a week (direct ×1 + indirect ×0.5) and sessions a week per group:", "",
              "| Group | Sets | Sessions |", "|---|---|---|"]
    lines += [f"| {g} | {fmt(round(groups.get(g, 0), 2))} | {fmt(round(sessions.get(g, 0), 2))} |" for g, _ in GROUPS]
    notes = [f"- {pid} {text}: {'met' if met else 'not met'} — {src}" for pid, met, text, src in preferences(p, catalogue)]
    known = [f"- G{c['gate']} {m} {fmt(v)}: known miss — {known_reason(p, c['gate'], (m, v))}"
             for c in checks if c["gate"] in (1, 2, 3) for m, v in c["misses"] if is_known(p, c["gate"], (m, v))]
    unknown_pattern = [s["exercise_id"] for r in p["routines"] for s in r["exercises"] if s["pattern"] in ("ISO", "CMP")]
    lines += ["", "## Notes (never failures)", ""] + notes + known
    if unknown_pattern:
        lines.append("- Movement slot unknown for " + ", ".join(unknown_pattern)
                     + ": the pain rules (G6) could not check them; check them by hand.")
    if unexpected:
        lines += ["", "## Failures", ""] + [f"- {u}" for u in unexpected]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dir", help="athlete folder (reads plan/program.json)")
    g.add_argument("--program", help="a program.json file")
    ap.add_argument("--json", action="store_true", help="print the checks as JSON")
    a = ap.parse_args(argv)
    path = a.program or os.path.join(a.dir, "plan", "program.json")
    try:
        with open(path, encoding="utf-8") as f:
            p = normalise(json.load(f))
    except (OSError, ValueError, KeyError) as e:
        print(f"cannot audit {path}: {e}", file=sys.stderr)
        return 2
    if a.json:
        checks = audit(p)
        print(json.dumps({"name": program_name(p), "checks": checks, "unexpected": unexpected_failures(p, checks),
                          "preferences": preferences(p)}, ensure_ascii=False, indent=1))
    else:
        print(report(p), end="")
    return 1 if unexpected_failures(p) else 0


if __name__ == "__main__":
    sys.exit(main())
