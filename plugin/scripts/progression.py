#!/usr/bin/env python3
"""progression.py: the weekly progression engine (grade -> propose -> apply) on one athlete folder.

Rules: plugin/skills/progression/rules.md. Data contract: plugin/docs/athlete-folder.md.

    grade   --dir D --week YYYY-Www   grade that week's frozen targets against data/sets.csv and
                                      write the grades into plan/targets/targets_YYYY-Www.json
                                      (a week with no targets file is graded against program.json
                                      or the last targets: an "implicit" file).
    propose --dir D --week YYYY-Www   grade the week before (safe to repeat), then write next
                                      week's DRAFT targets (status "proposed") and print the
                                      grade table + proposals as Markdown.
    apply   --dir D --week YYYY-Www   after the athlete's OK: mark accepted rows; the targets file
                                      becomes "applied" and frozen. Writes nothing else.

Targets are per routine x exercise (row id = routine slug + slot). Reasons are stored as codes plus
values ({"code": "step", "kg_add": 5.0, ...}) and rendered to sentences by `render` (English now; the
TEXT table has a slot per language). User-facing text says "reps left" and "easy week".
Deterministic, Python 3.9+ stdlib, no network.
"""
import argparse
import csv
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from itertools import permutations

# ------------------------------------------------------------------ the jump table (G119), in one place
# Every set reached the top of the rep range: how many load steps the next target adds, by the reps
# left on the hardest graded set against the row's target reps left. Setting every value to 1 gives
# the classic one-step double progression. Caps: steps by level, then kg by equipment.
JUMP_STEPS = {"failure": 0, "below_target": 0, "at_target": 1, "one_over": 2, "two_plus_over": 3}
MAX_STEPS = {"beginner": 3, "intermediate": 2, "advanced": 2}
JUMP_CAP_KG = {"barbell_lower": 10.0, "barbell_upper": 5.0}      # other tools: 2 load steps

# ------------------------------------------------------------------ other rule constants
DEFAULT_STEP_KG = {"barbell_lower": 2.5, "barbell_upper": 2.5, "dumbbell": 2.0, "machine": 5.0,
                   "bodyweight": 0.0}
DEFAULT_REPS_LEFT = {"spine": [2, 2], "compound": [1, 2], "isolation": [0, 2]}
ISOLATION_WORDS = ("curl", "raise", "fly", "flye", "extension", "pec deck", "butterfly", "face pull",
                   "kickback", "shrug", "calf", "crunch", "pushdown")
LOWER_WORDS = ("squat", "deadlift", "lunge", "hip thrust", "good morning", "split squat")
MACHINE_WORDS = ("machine", "cable", "lever", "smith", "leg press", "pulldown", "sled")
WORKING_TYPES = ("normal", "failure")        # warm-ups and drop-set tails are never graded
PARTIAL_MAX_SHORTFALL = 2                    # reps short in total that still count as "close"
REDUCE_E1RM = (0.92, 0.95)                   # 2-miss reduce: aim at 92 % of the best logged e1RM, cap 95 %
REDUCE_COARSE = 0.88                         # below this the load step was too coarse (said in the reason)
REDUCE_MAX_CUT = 0.20                        # grid floor for the reduce (one step down always allowed)
REDUCE_ASSISTED_PCT = 0.05                   # assisted rows: +5 % assistance (Epley means nothing there)
REP_PR_TOTAL_PCT = 0.05                      # rep PR: total reps +max(2, 5 %) with the best set not lower
EASY_WEEK_PCT = 0.10                         # easy week: -10 % load, -1/3 sets
LEVEL_SHIFT_PCT = 0.25                       # logged top load this far off target = other machine/variant
REENTRY_GAP_DAYS = 14
BAND = (0.70, 0.85)                          # healthy rolling 4-week hit rate
BAND_MIN_WEEKS = 4
MAX_COACH_CHANGES = 6                        # overrides per review (the rule's own decisions don't count)
OVERRIDE_MAX_KG = 400.0
OVERRIDE_MAX_SETS = 10
SCHEMA = "coaich/targets/0.1"
EPS = 1e-6
DECISIONS = ("increase", "hold", "reduce", "easy_week", "swap")
GRADE_WORD = {"hit": "met", "partial": "close", "miss": "missed", "not_done": "not done",
              "excluded": "skipped", None: ""}


# ------------------------------------------------------------------ small helpers
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def r2(x):
    return round(float(x) + 0.0, 2)


def fnum(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def norm_title(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def words(s):
    return " " + norm_title((s or "").replace("_", " ")) + " "


def parse_week(w):
    m = re.fullmatch(r"(\d{4})-?W(\d{1,2})", (w or "").strip().upper())
    if not m:
        raise SystemExit(f"Bad --week '{w}' (expected YYYY-Www, e.g. 2030-W10)")
    return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)


def week_label(monday):
    y, wk, _ = monday.isocalendar()
    return f"{y}-W{wk:02d}"


def week_of(d):
    return d - timedelta(days=d.weekday())


def fmt_kg(kg):
    if kg is None:
        return "?"
    return f"{float(kg):.2f}".rstrip("0").rstrip(".")


def fmt_sets(sets):
    """60×10·10·9  |  62.5×8 + 60×8·8  (consecutive equal loads grouped; ? = weight still to find)."""
    if not sets:
        return "—"
    groups = []
    for s in sets:
        k = None if s.get("kg") is None else float(s["kg"])
        if groups and groups[-1][0] == k:
            groups[-1][1].append(int(s["reps"]))
        else:
            groups.append([k, [int(s["reps"])]])
    return " + ".join(f"{fmt_kg(k)}×{'·'.join(str(r) for r in reps)}" for k, reps in groups)


def summarise(sets, assisted=False):
    loads = [float(s["kg"]) for s in sets or [] if s.get("kg") is not None]
    if not loads:
        return None, [int(s["reps"]) for s in sets or []]
    return (min(loads) if assisted else max(loads)), [int(s["reps"]) for s in sets]


def eff(kg, assisted):
    """Effective difficulty: assisted exercises run inverted (more assistance = easier)."""
    return -float(kg) if assisted else float(kg)


def step_round(x, step):
    return r2(round(x / step) * step) if step else r2(x)


def load_down(kg, step, pct, assisted):
    delta = max(step, step_round(abs(float(kg)) * pct, step))
    return r2(kg + delta) if assisted else r2(max(0.0, kg - delta))


def epley(kg, reps):
    return float(kg) * (1 + reps / 30.0)


def left_of(s):
    """Reps left on a logged set: a failure set is 0; else the rir column; else 10 - rpe (0-5)."""
    if s.get("type") == "failure":
        return 0
    return s.get("rir")


# ------------------------------------------------------------------ sentences (codes -> text)
def _left(v):
    n = v.get("left")
    return "" if n is None else f" with {n} rep{'s' if n != 1 else ''} left"


def _reps(n):
    return f"{n} rep{'s' if n != 1 else ''}"


def _missed(v):
    bits = [f"{v['met']}/{v['n']} sets met"]
    if v.get("missing"):
        bits.append(f"{v['missing']} set(s) not done")
    if v.get("under_load"):
        bits.append("load under target")
    if v.get("short"):
        bits.append(f"{_reps(v['short'])} short")
    return "; ".join(bits) + "."


# One table per language; a missing language or code falls back to English.
TEXT = {"en": {
    # grades
    "met": "{n}/{n} sets at or above target.",
    "close": lambda v: f"{v['met']}/{v['n']} sets; {_reps(v['short'])} short in total.",
    "missed": _missed,
    "rep_pr": "Still a rep record against last time.",
    "easy_week_graded": "Easy week: not graded.",
    "travel_week_graded": "Travel week: not graded.",
    "reentry": "First week back after {days}+ days off: not graded.",
    "out_of_loop": "Not in the progression loop (program.json).",
    "session_not_done": "Session not logged this week.",
    "exercise_not_logged": "Exercise not logged in the session (swapped?).",
    "level_shift": "Logged {kg} kg against a {target_kg} kg target: a different machine or variant?",
    "calibration": "First logged session: this sets your starting weight.",
    # decisions
    "easy_week": "Easy week to recover: about 10 % lighter and a third fewer sets. "
                 "Your targets come back next week.",
    "travel_week": "Travel week: targets frozen.",
    "after_easy_week": "Back from the easy week: your previous target returns.",
    "not_done": "Not done last week: same target.",
    "not_done_x2": "Not done two weeks in a row: same target. Worth a talk about this exercise.",
    "excluded_hold": "Skipped last week ({why}): same target.",
    "calibrated": "Starting weight set from what you logged: {target}.",
    "reanchor": "Two weeks in a row far from the target: re-anchor to what you lifted ({target}).",
    "close_hold": "Nearly there ({why}): repeat the target.",
    "miss_hold": "First miss: repeat the target.",
    "rep_pr_hold": "Missed, but a rep record against last time: repeat the target.",
    "reduce": "{streak} misses in a row: about {pct} % of what you lifted, to build back up{coarse}. "
              "Alternatives: hold, one set fewer, or another exercise.",
    "reduce_assisted": "{streak} misses in a row: more assistance ({kg_add} kg), reps to {reps}.",
    "fewer_reps": "{streak} misses in a row: back to {reps} reps.",
    "swap_after_reduce": "Still stuck after a lighter block: time to pick another exercise.",
    "swap_no_assistance": "No assistance left to remove: move to the unassisted version.",
    "step": lambda v: f"{v['reps']} reps on every set{_left(v)}: +{fmt_kg(v['kg_add'])} kg, "
                      f"reps back to {v['lo']}.",
    "step_despite_hard": "Second week in a row at the top with little left: +{kg_add} kg anyway. "
                         "Keep 2 reps in the tank.",
    "step_assisted": "{reps} reps on every set: {kg_add} kg less assistance, reps back to {lo}.",
    "top_too_hard": "You reached the top of the range, but with only {left} left: same weight.",
    "failure_hold": "You had nothing left on a compound lift: same weight; stop one rep earlier.",
    "top_no_load": "{reps} reps on every set of a bodyweight exercise: time for a harder variation.",
    "add_rep": "Target met: same weight, one more rep on set {set} ({frm} → {to}).",
    "reps_to_done": "Target met: same weight, reps up to what you did.",
    "reanchored": "Target met at a heavier weight: the target moves to what you lifted.",
    "new_row": "New in the program: start with the planned target.",
    # suffixes
    "needs_ok_spine": "Needs your OK: load goes up on a spine-loaded lift.",
    "needs_ok": "Needs your OK.",
    "reps_left_missing": "Log reps left on this lift: it decides the size of the next jump.",
}}


def render(reason, lang="en"):
    """{"code": ..., values} -> sentence. Nested reasons render first; floats ending in _kg/kg print as kg."""
    if not reason:
        return ""
    table = TEXT.get(lang) or TEXT["en"]
    tpl = table.get(reason["code"], TEXT["en"].get(reason["code"], reason["code"]))
    vals = {}
    for k, v in reason.items():
        if isinstance(v, dict) and "code" in v:
            v = render(v, lang).rstrip(".")
        elif isinstance(v, float) and "kg" in k:
            v = fmt_kg(v)
        vals[k] = v
    return tpl(reason) if callable(tpl) else tpl.format(**vals)


def row_text(row, lang="en"):
    """The decision sentence plus the OK / logging suffixes."""
    out = [render(row.get("reason"), lang)]
    if row.get("needs_approval"):
        spine_up = row.get("category") == "spine" and row.get("decision") in ("increase", "hold")
        out.append(render({"code": "needs_ok_spine" if spine_up else "needs_ok"}, lang))
    if "reps_left_missing" in (row.get("flags") or []):
        out.append(render({"code": "reps_left_missing"}, lang))
    return " ".join(x for x in out if x)


# ------------------------------------------------------------------ athlete folder I/O
def path_in(folder, *parts):
    return os.path.join(folder, *parts)


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def load_sessions(folder):
    """data/sets.csv -> sessions sorted by time: {id, date, title, sets: {exercise_id: [set, ...]}}."""
    path = path_in(folder, "data", "sets.csv")
    if not os.path.exists(path):
        raise SystemExit(f"data/sets.csv missing in {folder}: import the training history first.")
    sess = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                d = date.fromisoformat((r.get("date") or "").strip())
            except ValueError:
                continue
            sid = r.get("session_id") or f"{d}-{r.get('workout_name', '')}"
            s = sess.setdefault(sid, {"id": sid, "date": d, "datetime": r.get("datetime", ""),
                                      "title": r.get("workout_name", ""), "sets": defaultdict(list)})
            rir = fnum(r.get("rir"))
            rpe = fnum(r.get("rpe"))
            if rir is None and rpe is not None:
                rir = min(5, max(0, round(10 - rpe)))
            s["sets"][r.get("exercise_id", "")].append({
                "date": str(d), "idx": int(fnum(r.get("set_index"), 0) or 0),
                "type": r.get("set_type") or "normal",
                "kg": fnum(r.get("weight_kg"), 0.0) or 0.0,
                "reps": int(fnum(r.get("reps"), 0) or 0),
                "rir": None if rir is None else int(rir),
                "note": (r.get("note") or "").strip()})
    out = sorted(sess.values(), key=lambda s: (s["date"], s["datetime"]))
    for s in out:
        for sets in s["sets"].values():
            sets.sort(key=lambda x: x["idx"])
    return out


IMPORT_LINE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*·\s*import\b")


def data_through(folder, sessions, explicit=None):
    """How far the training data is complete: --data-through > the latest `import` line in log.md
    > the newest set date."""
    if explicit:
        return date.fromisoformat(explicit)
    best = None
    log = path_in(folder, "log.md")
    if os.path.exists(log):
        with open(log, encoding="utf-8") as fh:
            for line in fh:
                m = IMPORT_LINE.search(line)
                if m:
                    d = date.fromisoformat(m.group(1))
                    best = d if best is None or d > best else best
    newest = max((s["date"] for s in sessions), default=None)
    if newest and (best is None or newest > best):
        best = newest
    return best


def stale_guard(folder, sessions, graded_monday, what, explicit=None):
    dt = data_through(folder, sessions, explicit)
    sunday = graded_monday + timedelta(days=6)
    if dt is None or dt < sunday:
        raise SystemExit(
            f"REFUSED ({what}): the training data runs only to {dt or 'nothing yet'}, before the end of "
            f"{week_label(graded_monday)} ({sunday}). Import the latest sessions first, or pass "
            "--data-through YYYY-MM-DD if that week is complete as it is.")
    return dt


def targets_path(folder, label):
    return path_in(folder, "plan", "targets", f"targets_{label}.json")


def list_target_files(folder):
    d = path_in(folder, "plan", "targets")
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        m = re.fullmatch(r"targets_(\d{4}-W\d{2})\.json", fn)
        if m:
            out.append((m.group(1), os.path.join(d, fn)))
    return out


def latest_before(folder, label):
    files = [(lb, p) for lb, p in list_target_files(folder) if lb < label]
    return (files[-1][0], load_json(files[-1][1])) if files else (None, None)


def load_program(folder):
    path = path_in(folder, "plan", "program.json")
    if not os.path.exists(path):
        raise SystemExit(f"plan/program.json missing in {folder}: build a program first.")
    return load_json(path)


# ------------------------------------------------------------------ week types (CURRENT.md calendar)
def type_from_text(text):
    t = (text or "").lower()
    if any(w in t for w in ("recovery", "easy", "deload", "descarga", "recuperación", "suave")):
        return "recovery"
    if any(w in t for w in ("travel", "viaje")):
        return "travel"
    if "moderated" in t or "moderada" in t:
        return "moderated"
    return "full"


def week_type_from_current(folder, monday):
    """Microcycle type of the ISO week from a CURRENT.md calendar table row: | W<n> | type | start date | ..."""
    path = path_in(folder, "plan", "CURRENT.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3 or not re.fullmatch(r"\**W\d+\**", cells[0]):
                continue
            m = re.search(r"(\d{4}-\d{2}-\d{2})", cells[2])
            if m and week_of(date.fromisoformat(m.group(1))) == monday:
                return type_from_text(cells[1])
    return None


def week_type_from_program(folder, monday):
    """program.json `start` (date) + `easy_weeks` (1-based program week numbers) -> "recovery"."""
    path = path_in(folder, "plan", "program.json")
    prog = load_json(path) if os.path.exists(path) else {}
    try:
        n = (monday - week_of(date.fromisoformat(prog["start"]))).days // 7 + 1
    except (KeyError, TypeError, ValueError):
        return None
    return "recovery" if n in (prog.get("easy_weeks") or []) else None


def week_type_of(folder, monday):
    """CURRENT.md calendar > program.json easy weeks > full."""
    return week_type_from_current(folder, monday) or week_type_from_program(folder, monday) or "full"


def is_reentry(sessions, monday):
    """The week's first session comes after >= REENTRY_GAP_DAYS without training."""
    wk = [s for s in sessions if monday <= s["date"] <= monday + timedelta(days=6)]
    prev = [s["date"] for s in sessions if wk and s["date"] < wk[0]["date"]]
    return bool(prev) and (wk[0]["date"] - max(prev)).days >= REENTRY_GAP_DAYS


# ------------------------------------------------------------------ program rows
def infer_tool(ex_id, name):
    w = words(ex_id) + words(name)
    if " dumbbell " in w or " kettlebell " in w:
        return "dumbbell"
    if any(f" {m} " in w for m in MACHINE_WORDS):
        return "machine"
    if " barbell " in w or " ez " in w:
        return "barbell_lower" if any(f" {x} " in w for x in LOWER_WORDS) else "barbell_upper"
    return None


def program_rows(program):
    """Flatten program.json into per routine x exercise rows."""
    rows = []
    for rt in program.get("routines", []):
        for i, ex in enumerate(rt.get("exercises", []), 1):
            ex_id = ex.get("exercise_id") or ex.get("id") or ""
            name = ex.get("name") or ex_id.replace("_", " ")
            sets = ex.get("sets") or []
            if isinstance(sets, int):     # a set count with no weights yet: the first session finds them
                lo = int((ex.get("rep_range") or [ex.get("reps") or 10])[0])
                sets = [{"weight_kg": None, "reps": lo}] * sets
            work = [{"kg": None if s.get("weight_kg", s.get("kg")) is None else r2(s.get("weight_kg", s.get("kg"))),
                     "reps": int(s.get("reps") or 0), "type": s.get("type", "normal")}
                    for s in sets if s.get("type", "normal") in WORKING_TYPES]
            inferred = []
            tool = ex.get("tool")
            if not tool:
                tool = infer_tool(ex_id, name)
                inferred.append("tool")
            cat = ex.get("category")
            if not cat:
                cat = ("spine" if tool == "barbell_lower" else
                       "isolation" if any(f" {x} " in words(ex_id) + words(name) for x in ISOLATION_WORDS)
                       else "compound")
                inferred.append("category")
            rr = ex.get("rep_range")
            if not rr:
                reps = [s["reps"] for s in work] or [10]
                rr = [max(1, min(reps) - (2 if min(reps) == max(reps) else 0)), max(reps)]
                inferred.append("rep_range")
            step = ex.get("load_step_kg")
            if step is None:
                step = DEFAULT_STEP_KG.get(tool, 2.5)
                inferred.append("load_step_kg")
            rows.append({
                "id": f"{slug(rt['title'])}-{i}", "routine": rt["title"], "slot": i,
                "exercise_id": ex_id, "history_ids": list(ex.get("history_ids") or []), "name": name,
                "category": cat, "tool": tool, "assisted": bool(ex.get("assisted", False)),
                "overload": ex.get("overload", True) is not False,
                "rep_range": [int(rr[0]), int(rr[1])],
                "reps_left": list(ex.get("reps_left") or DEFAULT_REPS_LEFT[cat]),
                "load_step": float(step), "spec_sets": work, "inferred": inferred})
    return rows


def row_ids(row):
    return [row["exercise_id"]] + [x for x in row.get("history_ids", []) if x]


def same_row(a, b):
    """Same routine AND same exercise (id or a declared history alias)."""
    return a["routine"] == b["routine"] and bool(set(row_ids(a)) & set(row_ids(b)))


def session_matches(title, routine):
    t, r = norm_title(title), norm_title(routine)
    return t == r or re.search(r"(^| )" + re.escape(r) + r"( |$)", t) is not None


def routine_session(sessions, routine, monday):
    """The routine's session in the ISO week; done twice -> the last one."""
    sunday = monday + timedelta(days=6)
    cands = [s for s in sessions if monday <= s["date"] <= sunday and session_matches(s["title"], routine)]
    return cands[-1] if cands else None


# ------------------------------------------------------------------ grading
def set_meets(t, a, lo, assisted):
    """A logged set meets a target set: >= load and >= reps; or (not assisted) a heavier load at
    >= rep_lo whose Epley e1RM is at least the target's (the athlete went heavier)."""
    if eff(a["kg"], assisted) >= eff(t["kg"], assisted) - EPS and a["reps"] >= t["reps"]:
        return True
    return (not assisted and a["kg"] > t["kg"] + EPS and a["reps"] >= lo
            and epley(a["kg"], a["reps"]) >= epley(t["kg"], t["reps"]) - EPS)


def best_pairing(target, chosen, lo, assisted):
    """Assign logged sets to target sets maximising (sets met, -reps short); exhaustive for <= 7."""
    n, m = len(target), len(chosen)
    k = min(n, m)
    key = lambda s: (eff(s["kg"], assisted), s["reps"])
    if n > 7 or m > 7:
        tidx = sorted(range(n), key=lambda i: key(target[i]), reverse=True)
        return [(tidx[j], chosen[j]) for j in range(k)]

    def score(assign):
        met = sum(1 for i, a in assign if set_meets(target[i], a, lo, assisted))
        short = sum(max(0, target[i]["reps"] - a["reps"]) for i, a in assign
                    if not set_meets(target[i], a, lo, assisted))
        return (met, -short)

    best, best_s = None, None
    for tsub in permutations(range(n), k):
        assign = [(tsub[j], chosen[j]) for j in range(k)]
        sc = score(assign)
        if best_s is None or sc > best_s:
            best, best_s = assign, sc
    return best


def source_view(sets):
    return [{k: s.get(k) for k in ("date", "kg", "reps", "type", "rir")} for s in sets]


def grade_exposure(target, actual, rep_range, step, assisted, check_level=True):
    """Grade one exposure: only the HEAVIEST N working sets count (N = target sets), so ramp sets
    logged as normal sets fall out. Returns None when nothing was logged."""
    lo = rep_range[0]
    work = [s for s in actual if s.get("type", "normal") in WORKING_TYPES]
    if not work:
        return None
    n = len(target)
    chosen = sorted(work, key=lambda s: (eff(s["kg"], assisted), s["reps"]), reverse=True)[:n]
    source = sorted(chosen, key=lambda s: s.get("idx", 0))
    assign = best_pairing(target, chosen, lo, assisted) if n else []
    used = {i for i, _ in assign}
    missing = [target[i] for i in range(n) if i not in used]
    pairs = [(target[i], a) for i, a in assign]
    out = {"source_sets": source_view(source), "flags": [], "pairs": pairs,
           "pair_index": {i: a for i, a in assign}}
    top_t = max(eff(t["kg"], assisted) for t in target) if n else 0.0
    top_a = eff(chosen[0]["kg"], assisted)
    thr = max(LEVEL_SHIFT_PCT * abs(top_t), 3 * step)
    if check_level and n and abs(top_a - top_t) > thr + EPS:
        out.update(grade="excluded", reason={"code": "level_shift", "kg": abs(top_a), "target_kg": abs(top_t)})
        out["flags"].append("level_shift")
        return out
    met = sum(1 for t, a in pairs if set_meets(t, a, lo, assisted))
    near = all(eff(a["kg"], assisted) >= eff(t["kg"], assisted) - step - EPS for t, a in pairs)
    short = (sum(max(0, t["reps"] - a["reps"]) for t, a in pairs if not set_meets(t, a, lo, assisted))
             + sum(t["reps"] for t in missing))
    if not missing and met == n:
        out.update(grade="hit", reason={"code": "met", "n": n})
        if all(abs(t["kg"] - a["kg"]) < EPS and t["reps"] == a["reps"] for t, a in pairs):
            out["flags"].append("exact_copy")      # possibly a pre-filled value saved untouched
        elif any(eff(a["kg"], assisted) > eff(t["kg"], assisted) + EPS or a["reps"] > t["reps"]
                 for t, a in pairs):
            out["flags"].append("overshoot")
    elif not missing and near and short <= PARTIAL_MAX_SHORTFALL:
        out.update(grade="partial", reason={"code": "close", "met": met, "n": n, "short": short})
    else:
        out.update(grade="miss", reason={"code": "missed", "met": met, "n": n, "missing": len(missing),
                                         "under_load": not near, "short": short})
    if any(a.get("type") == "failure" and t.get("type") != "failure" for t, a in pairs):
        out["flags"].append("failure_used")
    return out


def grade_row(row, target, sessions, monday, week_type):
    """Grade one row for the ISO week starting `monday` -> (grade fields, grade_exposure output)."""
    base = {"grade": None, "grade_reason": None, "grade_flags": [], "source_sets": []}
    if week_type in ("recovery", "travel", "reentry"):
        code = {"recovery": "easy_week_graded", "travel": "travel_week_graded", "reentry": "reentry"}[week_type]
        base.update(grade="excluded", grade_reason={"code": code, "days": REENTRY_GAP_DAYS})
        return base, None
    if not row.get("overload", True):
        base.update(grade="excluded", grade_reason={"code": "out_of_loop"})
        return base, None
    s = routine_session(sessions, row["routine"], monday)
    if s is None:
        base.update(grade="not_done", grade_reason={"code": "session_not_done"})
        return base, None
    actual = [x for i in row_ids(row) for x in s["sets"].get(i, [])]
    notes = sorted({x["note"] for x in actual if x.get("note")})
    if notes:
        base["athlete_note"] = " / ".join(notes)    # rides beside the grade; never moves a decision
    work = [x for x in actual if x.get("type", "normal") in WORKING_TYPES]
    if not work:
        base.update(grade="not_done", grade_reason={"code": "exercise_not_logged"})
        return base, None
    if not target or any(t.get("kg") is None for t in target):     # no weight yet: this session sets it
        n = len(target) or len(work)
        heaviest = sorted(work, key=lambda x: (eff(x["kg"], row["assisted"]), x["reps"]), reverse=True)[:n]
        base.update(grade="excluded", grade_flags=["calibration"],
                    source_sets=source_view(sorted(heaviest, key=lambda x: x["idx"])),
                    grade_reason={"code": "calibration"})
        return base, None
    g = grade_exposure(target, work, row["rep_range"], row["load_step"], row["assisted"])
    base.update(grade=g["grade"], grade_reason=g["reason"], grade_flags=list(g["flags"]),
                source_sets=g["source_sets"])
    if "athlete_note" in base:
        base["grade_flags"].append("athlete_note")
    return base, g


# ------------------------------------------------------------------ decisions
def easy_sets(sets, step, assisted):
    n = len(sets)
    keep = max(1, n - int(round(n / 3.0)))
    return [{"kg": None if s["kg"] is None else load_down(s["kg"], step, EASY_WEEK_PCT, assisted),
             "reps": s["reps"], "type": "normal"} for s in sets[:keep]]


def rep_pr(cur, prev, assisted):
    """A miss that still beat the previous exposure: load >= previous and the best set +2 reps, or
    total reps +max(2, 5 %) with the best set not lower. Margins sit above day-to-day rep noise."""
    if not cur or not prev:
        return False
    ck, creps = summarise(cur, assisted)
    pk, preps = summarise(prev, assisted)
    if ck is None or pk is None or eff(ck, assisted) < eff(pk, assisted) - EPS:
        return False
    best = lambda sets, k: max(int(x["reps"]) for x in sets if abs(float(x["kg"]) - k) < EPS)
    cb, pb = best(cur, ck), best(prev, pk)
    gain = max(2, math.ceil(REP_PR_TOTAL_PCT * sum(preps)))
    return cb >= pb + 2 or (sum(creps) >= sum(preps) + gain and cb >= pb)


def miss_streak(history):
    """history newest-first -> (streak, reduced). not_done / excluded / moderated weeks neither break
    nor extend it; a rep-PR miss counts once and ends the look-back (it saves one week)."""
    streak, reduced = 0, False
    for h in history:
        if h.get("grade") in (None, "not_done", "excluded") or h.get("week_type") == "moderated":
            continue
        if h["grade"] != "miss":
            break
        streak += 1
        if h.get("decision") == "reduce" and h.get("accepted"):
            reduced = True
        if h.get("rep_pr"):
            break
    return streak, reduced


def reduce_sets(base, logged, lo, hi, step):
    """2-miss reduce anchored on what was lifted: the (load, reps) pair on the row's grid (one step
    below the top target load down to -20 %, reps in range) whose Epley e1RM is closest to 92 % of
    the best logged set, never above 95 %; tie -> heavier. Every set moves down the same steps.
    Returns (sets, fraction of the logged e1RM) or None."""
    if not base or not logged or not step:
        return None
    anchor = max(epley(x["kg"], int(x["reps"])) for x in logged)
    top = max(float(x["kg"]) for x in base)
    goal, cap = (anchor * f for f in REDUCE_E1RM)
    best = None
    for k in range(1, int(top / step) + 1):
        kg = r2(top - k * step)
        if kg <= 0 or (k > 1 and kg < top * (1 - REDUCE_MAX_CUT) - EPS):
            break
        for reps in range(lo, hi + 1):
            e = epley(kg, reps)
            if e > cap + EPS:
                continue
            cand = (abs(e - goal), -kg, k, reps, e)
            if best is None or cand < best:
                best = cand
    if best is None:
        return None
    _, _, k, reps, e = best
    return ([{"kg": r2(max(0.0, float(x["kg"]) - k * step)), "reps": reps, "type": x.get("type", "normal")}
             for x in base], e / anchor)


def not_done_streak(history):
    n = 0
    for h in history:
        if h.get("grade") == "not_done":
            n += 1
        elif h.get("grade") == "excluded" and h.get("week_type") in ("travel", "recovery"):
            continue
        else:
            break
    return n


def calibrated_sets(logged, base, lo, hi):
    """Calibration / re-anchor: the heaviest N sets as logged, reps capped at rep_hi, one rep fewer
    on a set logged as failure (not below rep_lo); load never raised."""
    out = []
    for i, s in enumerate(logged or []):
        reps = min(hi, int(s["reps"]))
        if s.get("type") == "failure":
            reps = max(min(reps, lo), reps - 1)
        out.append({"kg": r2(s["kg"]), "reps": reps,
                    "type": base[i].get("type", "normal") if i < len(base) else "normal"})
    return out


def prev_level_shift(history):
    """The exposure before the graded one (history[0]) was also a level shift."""
    for h in history[1:]:
        if "level_shift" in (h.get("flags") or []):
            return True
        if h.get("grade") in ("hit", "partial", "miss"):
            return False
    return False


def effort(left, target, compound):
    """Reps left on the hardest graded set vs the row's target [lo, hi] -> a JUMP_STEPS key (None = not logged)."""
    if left is None:
        return None
    if compound and left == 0:
        return "failure"
    if left < target[0]:
        return "below_target"
    over = left - target[1]
    return "at_target" if over <= 0 else "one_over" if over == 1 else "two_plus_over"


def jump_kg(row, effort_key, level):
    """G119: steps by effort, capped by level, then the kg by equipment."""
    n = min(JUMP_STEPS[effort_key or "at_target"], MAX_STEPS.get(level, MAX_STEPS["intermediate"]))
    step = row["load_step"]
    return r2(min(n * step, JUMP_CAP_KG.get(row.get("tool"), 2 * step)))


def decide(row, base, g, gf, history, next_type, restore=None, level="intermediate", prev_code=None):
    """Next week's target for one row.

    base: the target the athlete had last week · g: grade_exposure() output (hit rows) · gf: the
    graded row (grade, grade_reason, grade_flags, source_sets) · history: newest-first, incl. the
    graded week · next_type: microcycle type of the proposed week · restore: the pre-easy-week
    target · prev_code: the reason code that set last week's target."""
    lo, hi = row["rep_range"]
    step, assisted = row["load_step"], row["assisted"]
    spine = row["category"] == "spine"
    flags = []
    if "calibration" in (gf.get("grade_flags") or []) and gf.get("source_sets"):
        base = calibrated_sets(gf["source_sets"], base, lo, hi)   # found weights survive an easy/travel week

    def out(sets, dec, code, appr=False, pre=None, **vals):
        return {"target_sets": sets, "decision": dec, "reason": {"code": code, **vals},
                "needs_approval": appr, "flags": flags, "pre_easy_sets": pre}

    same = lambda: [dict(s) for s in base]
    if next_type == "recovery":
        src = restore or base
        return out(easy_sets(src, step, assisted), "easy_week", "easy_week", pre=src)
    if next_type == "travel":
        return out(same(), "hold", "travel_week")
    if restore:
        return out([dict(s) for s in restore], "hold", "after_easy_week")

    grade = gf.get("grade")
    if grade in (None, "not_done"):
        if not_done_streak(history) >= 2:
            flags.append("not_done_x2")
            return out(same(), "hold", "not_done_x2")
        return out(same(), "hold", "not_done")
    if grade == "excluded":
        gflags = gf.get("grade_flags") or []
        calib = "calibration" in gflags
        if calib or ("level_shift" in gflags and prev_level_shift(history)):
            new = calibrated_sets(gf.get("source_sets"), base, lo, hi)
            if new:
                if calib:
                    flags.append("calibration")
                    return out(new, "hold", "calibrated", target=fmt_sets(new))
                flags.extend(["coach_review", "reanchor"])
                return out(new, "hold", "reanchor", True, target=fmt_sets(new))
        if "level_shift" in gflags:
            flags.append("coach_review")
        return out(same(), "hold", "excluded_hold", why=gf.get("grade_reason"))
    if grade == "partial":
        return out(same(), "hold", "close_hold", why=gf.get("grade_reason"))
    if grade == "miss":
        streak, reduced = miss_streak(history)
        streak = max(streak, 1)
        if streak == 1:
            if "rep_pr" in (gf.get("grade_flags") or []):
                return out(same(), "hold", "rep_pr_hold")
            return out(same(), "hold", "miss_hold")
        flags.append("coach_review")
        if reduced and streak >= 3:
            return out(same(), "swap", "swap_after_reduce", True)
        if not step:
            return out([dict(s, reps=lo) for s in base], "reduce", "fewer_reps", True, streak=streak, reps=lo)
        red = None if assisted else reduce_sets(base, gf.get("source_sets"), lo, hi, step)
        if red:
            new, pct = red
            return out(new, "reduce", "reduce", True, streak=streak, pct=round(pct * 100),
                       coarse=" (the load step is too big to go finer)" if pct < REDUCE_COARSE else "")
        new = [{"kg": load_down(s["kg"], step, REDUCE_ASSISTED_PCT, assisted), "reps": min(hi, lo + 2),
                "type": s.get("type", "normal")} for s in base]
        return out(new, "reduce", "reduce_assisted", True, streak=streak,
                   kg_add=r2(abs(new[0]["kg"] - base[0]["kg"])), reps=min(hi, lo + 2))

    # grade == hit -------------------------------------------------------------------
    paired = {i: a for i, a in (g["pair_index"] if g else {}).items() if i < len(base)}
    # a set logged at least one step above its target moves to the load lifted (already progressed)
    up = {i for i in paired if step and eff(paired[i]["kg"], assisted) >= eff(base[i]["kg"], assisted) + step - EPS}
    loads = [r2(paired[i]["kg"]) if i in up else base[i]["kg"] for i in range(len(base))]
    at_top = bool(paired) and all(paired[i]["reps"] >= hi for i in paired)
    lefts = [left_of(a) for a in paired.values() if left_of(a) is not None]
    left = min(lefts) if lefts else None
    eff_key = effort(left, row["reps_left"], compound=row["category"] != "isolation")
    if left is None and spine:
        flags.append("reps_left_missing")
    if up:
        flags.append("reanchor")
    if eff_key == "failure":
        return out(same(), "hold", "failure_hold")
    kept = []
    for i, s in enumerate(base):
        a = paired.get(i)
        reps = min(hi, a["reps"]) if i in up else min(hi, max(s["reps"], a["reps"] if a else s["reps"]))
        kept.append({"kg": loads[i], "reps": reps, "type": s.get("type", "normal")})
    load_went_up = (max(eff(s["kg"], assisted) for s in kept)
                    > max(eff(s["kg"], assisted) for s in base) + EPS)

    if at_top and not step:
        flags.append("coach_review")
        return out(kept, "hold", "top_no_load", reps=hi)
    if at_top and eff_key == "below_target":
        if prev_code != "top_too_hard":
            return out(kept, "hold", "top_too_hard", spine and load_went_up, left=left)
        add, code = step, "step_despite_hard"           # second time in a row: the step anyway
    elif at_top:
        # lean: assisted rows move one step of assistance at a time; G119 jumps are for loads.
        add, code = (step, "step_assisted") if assisted else (jump_kg(row, eff_key, level), "step")
    else:
        add = None
    if add is not None:
        new_loads = [r2(k - add) if assisted else r2(k + add) for k in loads]
        if assisted and any(k < -EPS for k in new_loads):
            flags.append("coach_review")
            return out(same(), "swap", "swap_no_assistance", True)
        new = [{"kg": k, "reps": lo, "type": base[i].get("type", "normal")} for i, k in enumerate(new_loads)]
        return out(new, "increase", code, spine, reps=hi, left=left, kg_add=add, lo=lo)

    # met, not all at the top: add reps
    if up:
        return out(kept, "hold", "reanchored", spine and load_went_up)
    if [s["reps"] for s in kept] == [s["reps"] for s in base]:
        for i, s in enumerate(kept):
            if s["reps"] < hi:
                s["reps"] += 1
                return out(kept, "hold", "add_rep", set=i + 1, frm=s["reps"] - 1, to=s["reps"])
    return out(kept, "hold", "reps_to_done")


def fit_sets(sets, spec_sets, week_type):
    """Restore the program's set count after a moderated/easy week; trim one set on moderated weeks."""
    sets = [dict(s) for s in sets]
    if week_type == "recovery":
        return sets
    while sets and len(sets) < len(spec_sets):
        extra = dict(sets[-1])
        extra["type"] = spec_sets[len(sets)].get("type", "normal")
        sets.append(extra)
    if week_type == "moderated" and len(sets) > 1:
        sets = sets[:-1]
    for i, s in enumerate(sets):
        if i < len(spec_sets):
            s["type"] = spec_sets[i].get("type", s.get("type", "normal"))
    return sets


# ------------------------------------------------------------------ targets files
def effective_target(row, status):
    """What the athlete actually had as target during the row's week."""
    if row.get("live_target_sets"):
        return row["live_target_sets"]
    if status == "proposed" and row.get("prev_target_sets"):
        return row["prev_target_sets"]       # never applied -> last week's target stayed in force
    return row.get("target_sets") or row.get("spec_sets") or []


PUBLIC_KEYS = ("id", "routine", "slot", "exercise_id", "history_ids", "name", "category", "tool",
               "assisted", "overload", "rep_range", "reps_left", "load_step")


def row_public(row, target):
    d = {k: row.get(k) for k in PUBLIC_KEYS}
    tk, tr = summarise(target, row["assisted"])
    d.update(target_sets=target, target_kg=tk, target_reps=tr)
    return d


def history_for(row, folder, before_label):
    hist = []
    for label, path in reversed(list_target_files(folder)):
        if label >= before_label:
            continue
        doc = load_json(path)
        for r in doc.get("rows", []):
            if same_row(r, row):
                hist.append({"week": label, "grade": r.get("grade"), "decision": r.get("decision"),
                             "accepted": r.get("accepted"),
                             "rep_pr": "rep_pr" in (r.get("grade_flags") or []),
                             "flags": r.get("grade_flags") or [], "row": r,
                             "week_type": doc.get("graded_week_type") or doc.get("microcycle_type")})
                break
    return hist


def grade_week(folder, sessions, monday, write=True, week_type=None):
    """Grade the targets of ISO week `monday` (an implicit file when none exists). Returns the doc."""
    label = week_label(monday)
    path = targets_path(folder, label)
    if os.path.exists(path):
        doc = load_json(path)
    else:
        prev_label, prev = latest_before(folder, label)
        out_rows = []
        for row in program_rows(load_program(folder)):
            tgt = row["spec_sets"]
            for pr in (prev or {}).get("rows", []):
                if same_row(pr, row):
                    tgt = effective_target(pr, prev.get("status"))
                    if pr.get("decision") == "easy_week" and pr.get("pre_easy_sets"):
                        tgt = pr["pre_easy_sets"]
                    break
            r = row_public(row, tgt)
            r.update(prev_target_sets=None, decision="hold", reason=None, needs_approval=False, flags=[],
                     pre_easy_sets=None, accepted=True, source="implicit", override_reason=None,
                     live_target_sets=tgt)
            out_rows.append(r)
        doc = {"schema": SCHEMA, "iso_week": label, "week_start": str(monday),
               "week_end": str(monday + timedelta(days=6)),
               "microcycle_type": week_type or week_type_of(folder, monday),
               "status": "implicit", "generated_at": now(), "based_on_week": prev_label,
               "applied_at": None, "apply_mode": None, "graded_at": None, "summary": {}, "rows": out_rows,
               "note": "No frozen targets this week: graded against the program / the last targets."}
    wt = week_type or doc.get("microcycle_type") or "full"
    if wt == "full" and is_reentry(sessions, monday):
        wt = "reentry"
    st0 = doc.get("status_before_grade") or doc.get("status")
    counts = Counter()
    for r in doc["rows"]:
        r.pop("athlete_note", None)
        hist = history_for(r, folder, label)
        gf, _ = grade_row(r, effective_target(r, st0), sessions, monday, wt)
        if gf["grade"] == "miss":
            prev = next((h["row"].get("source_sets") for h in hist if h["grade"] in ("hit", "partial", "miss")), None)
            if rep_pr(gf["source_sets"], prev, r.get("assisted", False)):
                gf["grade_flags"].append("rep_pr")
        r.update(gf)
        counts[gf["grade"]] += 1
    if st0 == "proposed":
        doc["note"] = "Targets never applied: graded against last week's target (prev_target_sets)."
    doc.update(graded_at=now(), graded_week_type=wt, status_before_grade=st0, status="graded")
    doc.setdefault("summary", {})["grades"] = dict(counts)
    if write:
        save_json(path, doc)
    return doc


def hit_rate(counts):
    n = counts.get("hit", 0) + counts.get("partial", 0) + counts.get("miss", 0)
    return (counts.get("hit", 0) / n if n else None), n


def band_text(folder, upto_label=None):
    weeks = [load_json(p) for lb, p in list_target_files(folder) if upto_label is None or lb <= upto_label]
    counted = [d for d in weeks if d.get("status") == "graded"
               and hit_rate(Counter(d["summary"].get("grades") or {}))[1] > 0]
    if len(counted) < BAND_MIN_WEEKS:
        return (f"Hit rate band: still learning ({len(counted)}/{BAND_MIN_WEEKS} graded weeks); "
                "no verdict yet.")
    c = Counter()
    for d in counted[-BAND_MIN_WEEKS:]:
        c.update(d["summary"].get("grades") or {})
    hr, n = hit_rate(c)
    verdict = ("healthy" if BAND[0] <= hr <= BAND[1] else
               "too easy (over 85 %)" if hr > BAND[1] else "too demanding (under 70 %)")
    return f"Hit rate, last 4 weeks: {hr * 100:.0f} % (n={n}); healthy band 70–85 % → {verdict}."


def regrade_pairs(grow, base, sessions, monday, gdoc):
    """Rebuild the set pairing of a graded hit row (decide needs it)."""
    if grow.get("grade") != "hit":
        return None
    wt = gdoc.get("graded_week_type") or gdoc.get("microcycle_type") or "full"
    return grade_row(grow, base, sessions, monday, wt)[1]


def changed(r):
    return r["decision"] != "hold" or r["target_sets"] != r["prev_target_sets"]


# ------------------------------------------------------------------ commands
def cmd_grade(args):
    folder, monday = args.dir, parse_week(args.week)
    sessions = load_sessions(folder)
    stale_guard(folder, sessions, monday, "grade", args.data_through)
    path = targets_path(folder, week_label(monday))
    if os.path.exists(path) and load_json(path).get("status") == "graded":
        nxt = targets_path(folder, week_label(monday + timedelta(days=7)))
        if os.path.exists(nxt) and load_json(nxt).get("status") in ("applied", "graded"):
            raise SystemExit(f"REFUSED: {week_label(monday)} is graded and the next week is already applied. "
                             "An applied week is never regraded; write the correction in the check-in.")
        if not args.force:
            raise SystemExit(f"REFUSED: {week_label(monday)} is already graded. Use --force to regrade "
                             "(e.g. a session was deleted after grading).")
    doc = grade_week(folder, sessions, monday, week_type=args.week_type)
    print_grades(doc)
    print(f"\n-> {path}")


def cmd_propose(args):
    folder, monday = args.dir, parse_week(args.week)
    label, gmon = week_label(monday), monday - timedelta(days=7)
    sessions = load_sessions(folder)
    dt = stale_guard(folder, sessions, gmon, "propose", args.data_through)
    out_path = targets_path(folder, label)
    if os.path.exists(out_path) and not args.force:
        st = load_json(out_path).get("status")
        if st in ("applied", "graded"):
            raise SystemExit(f"REFUSED: {label} targets are already {st} (frozen). Use --force to redo.")
    gdoc = grade_week(folder, sessions, gmon)
    program = load_program(folder)
    level = program.get("level") or "intermediate"
    next_type = args.week_type or week_type_of(folder, monday)
    out_rows = []
    for row in program_rows(program):
        grow = next((r for r in gdoc["rows"] if same_row(r, row)), None)
        if grow is None:
            base = row["spec_sets"]
            res = {"target_sets": base, "decision": "hold", "reason": {"code": "new_row"},
                   "needs_approval": False, "flags": ["new_row"], "pre_easy_sets": None}
        else:
            base = effective_target(grow, gdoc.get("status_before_grade"))
            restore = grow.get("pre_easy_sets") if grow.get("decision") == "easy_week" else None
            g = regrade_pairs(grow, base, sessions, gmon, gdoc)
            res = decide(row, base, g, grow, history_for(row, folder, label), next_type, restore, level,
                         (grow.get("reason") or {}).get("code"))
        res["target_sets"] = fit_sets(res["target_sets"], row["spec_sets"], next_type)
        r = row_public(row, res["target_sets"])
        r.update(prev_target_sets=base, decision=res["decision"], reason=res["reason"],
                 needs_approval=res["needs_approval"],
                 flags=res["flags"] + ["inferred:" + f for f in row["inferred"]],
                 pre_easy_sets=res["pre_easy_sets"], accepted=None, source="rule", override_reason=None,
                 live_target_sets=None,
                 last_week={k: (grow or {}).get(k) for k in ("grade", "grade_reason", "source_sets", "athlete_note")},
                 grade=None, grade_reason=None, grade_flags=[], source_sets=[])
        r["last_week"]["target_sets"] = base
        out_rows.append(r)
    dec = Counter(r["decision"] for r in out_rows)
    doc = {"schema": SCHEMA, "iso_week": label, "week_start": str(monday),
           "week_end": str(monday + timedelta(days=6)), "microcycle_type": next_type, "status": "proposed",
           "generated_at": now(), "data_through": str(dt), "based_on_week": week_label(gmon), "level": level,
           "applied_at": None, "apply_mode": None, "graded_at": None,
           "summary": {"rows": len(out_rows), **{k: dec.get(k, 0) for k in DECISIONS},
                       "needs_approval": sum(1 for r in out_rows if r["needs_approval"]), "grades": None},
           "rows": out_rows}
    save_json(out_path, doc)
    print_proposal(doc, gdoc, folder)
    print(f"\nDRAFT -> {out_path}")
    print(f"Nothing is final until the athlete confirms. Then: progression.py apply --dir … --week {label} "
          "--accept-all [--approve ID,…] [--override ID=KGxR·R·R:reason] [--reject ID,…]")


def parse_ids(s):
    return {x.strip() for x in (s or "").split(",") if x.strip()}


def parse_override(s):
    """ID=KGxR·R·R:reason  or  ID=KGxR,R,R:reason (one load for every set)."""
    m = re.fullmatch(r"\s*([a-z0-9-]+)\s*=\s*([\d.]+)\s*[x×]\s*([\d·,\s]+?)\s*(?::(.*))?", s)
    if not m:
        raise SystemExit(f"Bad --override '{s}' (expected id=KGxR·R·R:reason)")
    kg = float(m.group(2))
    reps = [int(x) for x in re.split(r"[·,\s]+", m.group(3)) if x]
    why = (m.group(4) or "").strip()
    if not why:
        raise SystemExit(f"--override '{s}': the reason is mandatory (id=KGxR·R·R:reason)")
    if not 0 <= kg <= OVERRIDE_MAX_KG:
        raise SystemExit(f"--override '{s}': {kg:g} kg is out of range (0–{OVERRIDE_MAX_KG:g} kg). Typo?")
    if not 1 <= len(reps) <= OVERRIDE_MAX_SETS or any(not 1 <= x <= 30 for x in reps):
        raise SystemExit(f"--override '{s}': reps out of range (1–30 reps, 1–{OVERRIDE_MAX_SETS} sets). Typo?")
    return m.group(1), kg, reps, why


def cmd_apply(args):
    folder, monday = args.dir, parse_week(args.week)
    label = week_label(monday)
    path = targets_path(folder, label)
    if not os.path.exists(path):
        raise SystemExit(f"No targets file for {label}: run propose first.")
    doc = load_json(path)
    if doc.get("status") != "proposed" and not args.force:
        raise SystemExit(f"REFUSED: {label} targets are '{doc.get('status')}', not 'proposed'.")
    approve, reject = parse_ids(args.approve), parse_ids(args.reject)
    overrides = {}
    for o in args.override or []:
        rid, kg, reps, why = parse_override(o)
        overrides[rid] = (kg, reps, why)
    unknown = (approve | reject | set(overrides)) - {r["id"] for r in doc["rows"]}
    if unknown:
        raise SystemExit(f"Unknown row id(s): {', '.join(sorted(unknown))}")
    if len(overrides) > MAX_COACH_CHANGES:
        raise SystemExit(f"REFUSED: {len(overrides)} overrides. At most {MAX_COACH_CHANGES} coach changes per "
                         "review: rank them by evidence and hold the rest.")
    if not (args.accept_all or args.auto_isolation_only or approve or overrides or reject):
        raise SystemExit("Nothing confirmed. Pass --accept-all (plus --approve for rows that need an OK), "
                         "--override/--reject, or --auto-isolation-only when the check-in was skipped.")
    if args.auto_isolation_only and (approve or overrides):
        raise SystemExit("--auto-isolation-only cannot approve or override rows (the athlete is absent).")
    for r in doc["rows"]:                       # validate every override before anything changes
        if r["id"] in overrides and r["category"] == "spine" and r["id"] not in approve:
            prev = r.get("prev_target_sets") or r["target_sets"]
            if overrides[r["id"]][0] > max((s["kg"] or 0) for s in prev) + EPS:
                raise SystemExit(f"--override {r['id']}: raises the load on a spine-loaded lift; it needs "
                                 f"--approve {r['id']} (the athlete's explicit OK).")
    counts = Counter()
    for r in doc["rows"]:
        prev = r.get("prev_target_sets") or r["target_sets"]
        if r["id"] in overrides:
            kg, reps, why = overrides[r["id"]]
            types = [s.get("type", "normal") for s in r["target_sets"]] + ["normal"] * len(reps)
            live = [{"kg": r2(kg), "reps": rp, "type": types[i]} for i, rp in enumerate(reps)]
            r.update(accepted=True, source="coach", override_reason=why)
            size = lambda ss: (max((s["kg"] or 0) for s in ss), sum(s["reps"] for s in ss)) if ss else (0, 0)
            if size(live) != size(prev):
                r["decision"] = "increase" if size(live) > size(prev) else "reduce"
        elif r["id"] in reject:
            live = prev
            r.update(accepted=False, source="coach", override_reason="rejected at the check-in")
        elif args.auto_isolation_only:
            if r["decision"] == "easy_week" or (r["category"] == "isolation" and not r["needs_approval"]
                                                 and r["decision"] != "swap"):
                live = r["target_sets"]
                r.update(accepted=True, source="auto")
            else:
                live = prev
                r.update(accepted=False, source="auto-hold",
                         override_reason="check-in skipped: compound and spine lifts hold")
        elif r["needs_approval"] and r["id"] not in approve:
            live = prev
            r.update(accepted=False, source="rule", override_reason="waiting for the athlete's OK")
        else:
            live = r["target_sets"]
            r.update(accepted=True, source="rule")
        if r["decision"] == "swap" and r.get("accepted"):
            r["flags"] = list(r.get("flags", [])) + ["swap_pending"]     # the exercise change is manual
        r["live_target_sets"] = live
        counts["accepted" if r["accepted"] else "held"] += 1
    doc.update(status="applied", applied_at=now(),
               apply_mode="auto-isolation-only" if args.auto_isolation_only else "confirmed")
    save_json(path, doc)
    print(f"Applied {label}: {counts['accepted']} accepted · {counts['held']} held at last week's target.")
    for r in doc["rows"]:
        if not r["accepted"]:
            print(f"- held {r['id']} ({r['name']}): {r.get('override_reason')}")
    print_live(doc)
    print(f"\n-> {path}")


# ------------------------------------------------------------------ Markdown output
def by_routine(rows):
    out = defaultdict(list)
    for r in rows:
        out[r["routine"]].append(r)
    return out


def print_grades(doc):
    c = Counter(doc["summary"].get("grades") or {})
    hr, n = hit_rate(c)
    print(f"## Grades {doc['iso_week']} ({doc.get('graded_week_type')} week)\n")
    for routine, rows in by_routine(doc["rows"]).items():
        print(f"### {routine}\n\n| # | Exercise | Target | Done | Grade | Why |\n|---|---|---|---|---|---|")
        for r in rows:
            why = render(r.get("grade_reason")) + (" " + render({"code": "rep_pr"}) if "rep_pr" in r["grade_flags"] else "")
            print(f"| {r['id']} | {r['name']} | {fmt_sets(effective_target(r, doc.get('status_before_grade')))} | "
                  f"{fmt_sets(r.get('source_sets'))} | {GRADE_WORD[r.get('grade')]} | {why} |")
            if r.get("athlete_note"):
                print(f"|  | ✎ athlete's note: “{r['athlete_note']}” |  |  |  |  |")
        print()
    print("Grades: " + " · ".join(f"{GRADE_WORD[k]} {c[k]}" for k in ("hit", "partial", "miss", "not_done", "excluded") if c[k])
          + (f" · hit rate {hr * 100:.0f} % (n={n})" if hr is not None else ""))


def print_proposal(doc, gdoc, folder):
    print(f"## Targets {doc['iso_week']} ({doc['status']}) · {doc['microcycle_type']} week · "
          f"graded {doc['based_on_week']} · data through {doc['data_through']}\n")
    for routine, rows in by_routine(doc["rows"]).items():
        print(f"### {routine}\n\n| # | Exercise | Last target | Done | Grade | Next target | Why | OK? |\n"
              "|---|---|---|---|---|---|---|---|")
        for r in rows:
            lw = r["last_week"]
            print(f"| {r['id']} | {r['name']} | {fmt_sets(lw.get('target_sets'))} | {fmt_sets(lw.get('source_sets'))} | "
                  f"{GRADE_WORD[lw.get('grade')]} | {fmt_sets(r['target_sets'])} | {row_text(r)} | "
                  f"{'ask' if r['needs_approval'] else ''} |")
            if lw.get("athlete_note"):
                print(f"|  | ✎ athlete's note: “{lw['athlete_note']}” |  |  |  |  |  |  |")
        print()
    g = Counter(gdoc["summary"].get("grades") or {})
    hr, n = hit_rate(g)
    s, moved = doc["summary"], sum(1 for r in doc["rows"] if changed(r))
    print("Summary: " + (f"targets met {g['hit']}/{n} ({hr * 100:.0f} %)" if hr is not None else "nothing graded")
          + f" · {s['increase']} go up · {moved} change · {len(doc['rows']) - moved} stay the same"
          + f" · {s['needs_approval']} need your OK"
          + (f" · {g['not_done']} not done" if g.get("not_done") else ""))
    if not moved:
        print("No changes this week. That is a valid outcome: keep the same targets.")
    print(band_text(folder, gdoc["iso_week"]))


def print_live(doc):
    print(f"\n## Next week's targets ({doc['iso_week']})\n")
    for routine, rows in by_routine(doc["rows"]).items():
        print(f"### {routine}\n")
        for r in rows:
            print(f"- {r['name']}: {fmt_sets(r['live_target_sets'])}")
        print()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("grade", "propose", "apply"):
        sp = sub.add_parser(name)
        sp.add_argument("--dir", required=True, help="the athlete folder (holds coaich.md)")
        sp.add_argument("--week", required=True, help="ISO week, e.g. 2030-W10")
        sp.add_argument("--force", action="store_true")
        if name in ("grade", "propose"):
            sp.add_argument("--week-type", choices=("full", "moderated", "recovery", "travel"))
            sp.add_argument("--data-through", help="YYYY-MM-DD: the athlete says the data is complete to here")
        if name == "apply":
            sp.add_argument("--accept-all", action="store_true")
            sp.add_argument("--approve", help="comma-separated row ids the athlete OK'd")
            sp.add_argument("--reject", help="comma-separated row ids to hold")
            sp.add_argument("--override", action="append", help="ID=KGxR·R·R:reason")
            sp.add_argument("--auto-isolation-only", action="store_true")
    args = p.parse_args(argv)
    {"grade": cmd_grade, "propose": cmd_propose, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
