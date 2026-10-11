#!/usr/bin/env python3
"""roadmap.py: the long-term plan in plan/roadmap.md: macrocycle › phases (with gates) › mesocycles › microcycles.

    make   --dir D [--start YYYY-MM-DD] [--phases maintenance:12,bulk:20] [--today D]
    show   --dir D [--today D]                    where the athlete is now (also refreshes the file's tables)
    check  --dir D [--today D]                    grade the current phase's gates (due in its last 2 weeks)
    replan --dir D --outcome passed|missed|move-on [--extend-weeks 4] [--today D]

Vocabulary (fixed): references/periodization-system.md. A phase is the energy-balance direction (cut, bulk,
maintenance); a mesocycle is one program block, ending on its easy week (intermediate every 7th program week,
advanced every 6th; beginners: no planned easy week, blocks of 6 after the 4-week ramp); a microcycle is one week.
Program weeks are counted in sessions done (program_build.program_week), so microcycle dates are a projection: every
missed session moves the later weeks. Gates use the metrics and bands of changes.py and are coaching bands (our
rule), not study cut-offs. The header of plan/roadmap.md holds the data; the body is rewritten from it.
Exit 0 ok · 1 refused (no program, or a cut/bulk the athlete cannot have) · 2 stop (safety) or bad input.
"""
import argparse
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402
import changes as ch  # noqa: E402
import program_build as pb  # noqa: E402
import progression as pg  # noqa: E402

PHASES = ("cut", "bulk", "maintenance")
DEFAULT_WEEKS = 52
GATE_WINDOW_DAYS = 14                      # the gate review opens this long before a phase ends
# Strength gate per 12 weeks of a bulk or maintenance phase, % e1RM on the main lifts (our rule, coaching band).
LIFT_GAIN_12W = {"beginner": 10.0, "intermediate": 5.0, "advanced": 2.5}
WEIGHT_BAND = {"cut": "-1..-0.25", "bulk": "0.1..0.5"}   # % body weight a week (nutrition sets the calories)
MAX_LIFT_GATES = 3


def d(s):
    return dt.date.fromisoformat(str(s)[:10])


def monday(day):
    return day - dt.timedelta(days=day.weekday())


def view_monday(day):
    """The week a plan made on `day` starts with: this ISO week, or next week when `day` is a Sunday."""
    return monday(day + dt.timedelta(days=1))


# ------------------------------------------------------------------ inputs
def load(folder):
    folder = Path(folder)
    path = folder / "plan" / "program.json"
    if not path.exists():
        raise SystemExit("REFUSED: no plan/program.json; build a program first (program-build skill).")
    prog = pg.load_json(path)
    settings = pb.front_matter((folder / "coaich.md").read_text(encoding="utf-8"))
    profile = pb.front_matter((folder / "profile.md").read_text(encoding="utf-8")) if (folder / "profile.md").exists() else {}
    if str(settings.get("safety_status") or "").lower() == "stop":
        print("stop: safety status is stop; no plan is made or changed (safety skill).", file=sys.stderr)
        raise SystemExit(2)
    return prog, profile


def nutrition_on(profile):
    """The nutrition skill may set calories: the shared wellbeing gate (athlete_folder.gate) is open."""
    return not af.gate(profile, "nutrition")


def main_lifts(prog):
    """The main lift of each day (intermediate and up), else each day's first exercise; at most 3, no repeats."""
    mains = [s["exercise_id"] for r in prog["routines"] for s in r["exercises"] if s.get("main")]
    firsts = [r["exercises"][0]["exercise_id"] for r in prog["routines"]
              if r["exercises"] and not any(s.get("main") for s in r["exercises"])]
    return list(dict.fromkeys(mains + firsts))[:MAX_LIFT_GATES]


def default_gates(name, weeks, prog):
    gates = [f"sessions_per_week {max(1, prog['days'] - 1)}..", "hit_rate 70..85"]
    gain = 0.0 if name == "cut" else round(2 * LIFT_GAIN_12W[prog["level"]] * weeks / 12) / 2
    gates += [f"e1rm:{x} {gain:g}.." for x in main_lifts(prog)]
    if name in WEIGHT_BAND:
        gates.append(f"weight_rate {WEIGHT_BAND[name]}")
    return gates


def parse_phases(text, total):
    if not text:
        return [("maintenance", total)]
    out = []
    for part in text.split(","):
        name, _, weeks = part.strip().partition(":")
        if name not in PHASES or not weeks.isdigit() or not 2 <= int(weeks) <= 104:
            raise ValueError(f"--phases {part!r}: name:weeks with name one of {', '.join(PHASES)}, 2–104 weeks")
        out.append((name, int(weeks)))
    return out


# ------------------------------------------------------------------ plan/roadmap.md
def header_text(rm):
    lines = ["---", "roadmap: 0.1", f"made: {rm['made']}", f"start: {rm['start']}", f"end: {rm['end']}",
             f"goal: {rm.get('goal') or 'none'}", f"level: {rm['level']}", "phases:"]
    for p in rm["phases"]:
        lines += [f"  - name: {p['name']}", f"    start: {p['start']}", f"    end: {p['end']}",
                  f"    status: {p['status']}",
                  "    gates: [" + ", ".join(f'"{g}"' for g in p["gates"]) + "]",
                  f"    result: {p.get('result') or ''}".rstrip()]
    return "\n".join(lines + ["---"]) + "\n"


def read(folder):
    path = Path(folder) / "plan" / "roadmap.md"
    if not path.exists():
        raise SystemExit("No plan/roadmap.md yet: run `roadmap.py make` first.")
    rm = pb.front_matter(path.read_text(encoding="utf-8"))
    for k in ("made", "start", "end"):
        rm[k] = str(rm[k])
    for p in rm["phases"]:
        p["start"], p["end"] = str(p["start"]), str(p["end"])
        p["gates"] = list(p.get("gates") or [])
        p["result"] = p.get("result") or ""
    return rm


def phase_weeks(p):
    return ((d(p["end"]) - d(p["start"])).days + 1) // 7


def current_phase(rm):
    return next((p for p in rm["phases"] if p["status"] == "current"), None)


def position(folder, prog, today):
    """(program week of the week in view, sessions done before it)."""
    done = pg.sessions_done(folder, prog, view_monday(today))
    return pb.program_week(prog, done), done


def easy_week(prog, n):
    """Program week n is an easy week: program.json's list, then its interval past the list's end."""
    if prog.get("easy_weeks") and n <= max(prog["easy_weeks"]):
        return n in prog["easy_weeks"]
    return pb.easy_week(prog, n)


def block_ends(prog, upto):
    """Program weeks that end a mesocycle: each easy week; beginners: the ramp's last week, then every 6."""
    if prog["level"] != "beginner":
        return [n for n in range(1, upto + 1) if easy_week(prog, n)]
    first = (prog.get("rebuild_at_week") or 1) - 1
    return [n for n in range(1, upto + 1) if n == first or (n > first and (n - first) % 6 == 0)]


def projection(rm, prog, now_week, today):
    """Microcycles from this ISO week to the macrocycle's end: [(monday, iso label, program week, type, phase)]."""
    out, m, n = [], view_monday(today), now_week
    end = d(rm["end"])
    while m <= end:
        phase = next((p["name"] for p in rm["phases"] if d(p["start"]) <= m <= d(p["end"])), "")
        out.append((m, pg.week_label(m), n, "easy" if easy_week(prog, n) else "full", phase))
        m, n = m + dt.timedelta(days=7), n + 1
    return out


def body(rm, prog, today):
    now_week, done = position(rm["_folder"], prog, today)
    micro = projection(rm, prog, now_week, today)
    ends = set(block_ends(prog, micro[-1][2] if micro else now_week))
    lines = [f"# Roadmap\n",
             f"*Made {rm['made']}; tables refreshed {today}. The header above holds the data; this body is rewritten "
             "from it. Vocabulary: references/periodization-system.md.*\n",
             f"## Macrocycle\n\n{rm['start']} → {rm['end']} · goal {rm.get('goal') or 'none'} · level {rm['level']}. "
             "Direction only: the program prescribes, this plan does not.\n",
             "## Phases\n", "| # | Phase | From | To | Weeks | Status | Gates (metric band) |", "|---|---|---|---|---|---|---|"]
    for i, p in enumerate(rm["phases"], 1):
        status = p["status"] + (f" ({p['result']})" if p.get("result") else "")
        lines.append(f"| {i} | {p['name']} | {p['start']} | {p['end']} | {phase_weeks(p)} | {status} | "
                     + "; ".join(f"`{g}`" for g in p["gates"]) + " |")
    lines += ["", "A phase's gates are reviewed in its last 2 weeks (monthly check-in). Passed → the next phase starts. "
              "Missed → extend it, or move on with the miss written down. Cut and bulk calories come from the "
              "nutrition skill; with nutrition off, every phase is maintenance.", "",
              "## Mesocycles (program blocks)", "", "| Block | Program weeks | About | Ends with |", "|---|---|---|---|"]
    blocks, cur = [], []
    for row in micro:
        cur.append(row)
        if row[2] in ends or row is micro[-1]:
            blocks, cur = blocks + [cur], []
    for k, b in enumerate(blocks, 1):
        kind = "easy week" if b[-1][3] == "easy" else "macrocycle end" if b[-1] is micro[-1] else "program re-issue"
        lines.append(f"| {k}{' (now)' if k == 1 else ''} | {b[0][2]}–{b[-1][2]} | {b[0][0]} → "
                     f"{b[-1][0] + dt.timedelta(days=6)} | {kind} |")
    lines += ["", f"## Microcycles (projected from program week {now_week}: {done} sessions done since "
              f"{prog['start']})", "",
              "Easy weeks count in sessions done: a missed session moves every later week by its share.", "",
              "| # | ISO week | Monday | Program week | Type | Phase |", "|---|---|---|---|---|---|"]
    lines += [f"| {i} | {lab} | {m} | {n} | {t} | {ph} |" for i, (m, lab, n, t, ph) in enumerate(micro, 1)]
    return "\n".join(lines) + "\n"


def write(folder, rm, prog, today):
    rm["_folder"] = folder
    text = header_text(rm) + "\n" + body(rm, prog, today)
    (Path(folder) / "plan").mkdir(exist_ok=True)
    (Path(folder) / "plan" / "roadmap.md").write_text(text, encoding="utf-8")
    write_current(folder, rm, prog, today)


def summary(rm, prog, today):
    """One paragraph: where the athlete is (CURRENT.md block and `show`)."""
    now_week, _ = position(rm.get("_folder"), prog, today)
    p = current_phase(rm)
    nxt = next((n for n in range(now_week, now_week + 60) if easy_week(prog, n)), None)
    about = view_monday(today) + dt.timedelta(weeks=nxt - now_week) if nxt else None
    review = d(p["end"]) - dt.timedelta(days=GATE_WINDOW_DAYS - 1) if p else None
    return (f"Phase: {p['name']} ({p['start']} → {p['end']})" if p else "Phase: none current (macrocycle complete)") \
        + f" · program week {now_week}" \
        + (f" · next easy week: program week {nxt} (about {about})" if nxt else " · no planned easy week") \
        + (f" · gate review from {review}" if review else "") + " · file `plan/roadmap.md`."


def write_current(folder, rm, prog, today):
    rm["_folder"] = folder
    pb.write_current(folder, f"<!-- coaich:roadmap -->\n## Roadmap\n\n{summary(rm, prog, today)}\n"
                             "<!-- /coaich:roadmap -->\n", tag="roadmap")


# ------------------------------------------------------------------ commands
def make(folder, start, phases_text, today, weeks=DEFAULT_WEEKS):
    prog, profile = load(folder)
    phases = parse_phases(phases_text, weeks)
    if any(n in WEIGHT_BAND for n, _ in phases) and not nutrition_on(profile):
        raise SystemExit("REFUSED: a cut or bulk phase needs the nutrition skill set up and its safeguards passed "
                         "(18 or over, eating-disorder answer \"no\", not paused). Use maintenance.")
    s = view_monday(start)
    rm = {"made": str(today), "start": str(s), "goal": profile.get("goal") or prog.get("goal"), "level": prog["level"],
          "phases": []}
    for i, (name, w) in enumerate(phases):
        e = s + dt.timedelta(weeks=w, days=-1)
        rm["phases"].append({"name": name, "start": str(s), "end": str(e), "status": "current" if i == 0 else "next",
                             "gates": default_gates(name, w, prog), "result": ""})
        s = e + dt.timedelta(days=1)
    rm["end"] = rm["phases"][-1]["end"]
    write(folder, rm, prog, today)
    af.append_log(folder, "roadmap", f"made: {rm['start']} → {rm['end']}, "
                  + ", ".join(f"{n} {w} wk" for n, w in phases), date=str(today))
    return rm


def check(folder, today):
    """Grade the current phase's gates over the phase so far. → (phase, due, rows, outcome)."""
    rm = read(folder)
    p = current_phase(rm)
    if p is None:
        return None, False, [], "complete"
    due = today >= d(p["end"]) - dt.timedelta(days=GATE_WINDOW_DAYS - 1)
    rows = []
    for g in p["gates"]:
        metric, _, band = g.partition(" ")
        value, detail = ch.measure(folder, metric, d(p["start"]), min(today, d(p["end"])))
        rows.append((metric, band, value, detail, ch.verdict(value, ch.parse_band(band))))
    outcome = ("passed" if all(r[4] == "in band" for r in rows) else
               "missed" if any(r[4] in ("below band", "above band") for r in rows) else "no data")
    return p, due, rows, outcome


def gate_table(rows):
    lines = ["| Gate | Band | Now | Verdict |", "|---|---|---|---|"]
    lines += [f"| {m} | {b} | {ch.fmt_value(m, v)} ({det}) | {ver} |" for m, b, v, det, ver in rows]
    return "\n".join(lines)


def replan(folder, outcome, today, extend_weeks=4):
    rm = read(folder)
    prog, _ = load(folder)
    p = current_phase(rm)
    if p is None:
        raise SystemExit("REFUSED: no current phase; the macrocycle is complete. Make a new roadmap.")
    i = rm["phases"].index(p)
    if outcome == "missed":
        shift = dt.timedelta(weeks=extend_weeks)
        p["end"] = str(d(p["end"]) + shift)
        p["result"] = f"missed {today}, extended {extend_weeks} weeks"
        for q in rm["phases"][i + 1:]:
            q["start"], q["end"] = str(d(q["start"]) + shift), str(d(q["end"]) + shift)
    else:
        end = monday(today) + dt.timedelta(days=6)              # this week's Sunday: the next phase starts Monday
        shift = end - d(p["end"])
        p.update(end=str(end), status="done", result=f"{'passed' if outcome == 'passed' else 'moved on, gates missed'} {today}")
        for q in rm["phases"][i + 1:]:
            q["start"], q["end"] = str(d(q["start"]) + shift), str(d(q["end"]) + shift)
        if i + 1 < len(rm["phases"]):
            rm["phases"][i + 1]["status"] = "current"
    rm["end"] = rm["phases"][-1]["end"]
    write(folder, rm, prog, today)
    af.append_log(folder, "roadmap", f"{p['name']} {p['result']}; macrocycle ends {rm['end']}", date=str(today))
    return rm


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("--start", help="first day (default today; moved to its Monday)")
    mk.add_argument("--phases", help="name:weeks,… with name cut|bulk|maintenance (default maintenance:52)")
    sub.add_parser("show")
    sub.add_parser("check")
    rp = sub.add_parser("replan")
    rp.add_argument("--outcome", required=True, choices=("passed", "missed", "move-on"))
    rp.add_argument("--extend-weeks", type=int, default=4)
    for sp in sub.choices.values():
        sp.add_argument("--dir")
        sp.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    try:
        folder = af.find(a.dir)
        today = d(a.today)
        if a.cmd == "make":
            rm = make(folder, d(a.start) if a.start else today, a.phases, today)
            print(f"wrote plan/roadmap.md: {rm['start']} → {rm['end']}")
            rm["_folder"] = folder
            print(summary(rm, load(folder)[0], today))
        elif a.cmd == "show":
            rm, prog = read(folder), load(folder)[0]
            write(folder, rm, prog, today)
            print(summary(rm, prog, today))
        elif a.cmd == "check":
            p, due, rows, outcome = check(folder, today)
            if p is None:
                print("Macrocycle complete: no current phase. Make a new roadmap.")
            else:
                print(f"## Gates · {p['name']} ({p['start']} → {p['end']})"
                      + ("" if due else f" · not due yet (review opens {d(p['end']) - dt.timedelta(days=GATE_WINDOW_DAYS - 1)})")
                      + f"\n\n{gate_table(rows)}\n\nSo far: {outcome}.")
        else:
            rm = replan(folder, a.outcome, today, a.extend_weeks)
            print(f"re-planned: macrocycle {rm['start']} → {rm['end']}")
            rm["_folder"] = folder
            print(summary(rm, load(folder)[0], today))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 1
        return e.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
