#!/usr/bin/env python3
"""monthly_check_in.py: the numbers of the monthly check-in, and the program re-issue it may lead to.

    report  --dir D [--today D] [--weeks 4] [--write] [--decision TEXT]… [--note TEXT]…
            the last 4 ISO weeks: hit rate, volume per muscle against the coaching bands, main lifts, flagged rows,
            body-weight trend, a health glance, past plan changes graded against their bands, the roadmap
            position, and the signals for next month. --write saves check-ins/{today}-monthly.md (with the
            decisions and the athlete's notes, verbatim), records the due grades in plan/changes.md and logs.
    reissue --dir D [--today D] [--swap FROM=TO]… [--promote] [--why TEXT] [--dry-run]
            the next mesocycle: program_build at the current program week (week 1's date kept), with the
            athlete's swaps (written to profile.md `exercise_swaps`, same slot only) or, with --promote, Advanced
            (their squat and bench loads from the log go to `known_loads`). Each change goes to plan/changes.md
            with its band. The audit gates it: a refusal writes nothing.

Weeks run Monday–Sunday; "the month" = the 4 ISO weeks before the week in view (next week when run on a
Sunday). Python 3.9+ stdlib.
"""
import argparse
import datetime as dt
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapt  # noqa: E402
import athlete_folder as af  # noqa: E402
import changes as ch  # noqa: E402
import program_audit as pa  # noqa: E402
import program_build as pb  # noqa: E402
import progression as pg  # noqa: E402
import roadmap as rmp  # noqa: E402

# Coaching bands (RP, practitioner; references/volume-landmarks.md): MEV, MAV low–high, MRV, cut keep low–high.
BANDS = {
    "chest": (8, 12, 20, 22, 8, 14), "delts_side": (8, 16, 22, 26, 10, 16), "delts_rear": (6, 12, 18, 25, 10, 16),
    "delts_front": (0, 6, 8, 12, 0, 8), "lats": (10, 14, 20, 25, 10, 16), "upper_back": (10, 14, 22, 25, 10, 16),
    "traps": (4, 12, 20, 26, 4, 12), "biceps": (8, 14, 20, 26, 8, 14), "triceps": (6, 10, 14, 18, 6, 12),
    "quadriceps": (8, 12, 18, 20, 8, 14), "hamstrings": (6, 10, 16, 20, 6, 12), "glutes": (0, 4, 12, 16, 0, 8),
    "calves": (8, 12, 16, 20, 12, 20), "abdominals": (0, 6, 16, 25, 0, 10),
}
assert {m: b[3] for m, b in BANDS.items()} == pa.MRV, "BANDS MRV must match program_audit.MRV"
HEALTH = (("sleep_h", "Sleep", "h"), ("steps", "Steps", ""), ("resting_hr_bpm", "Resting heart rate", "bpm"),
          ("hrv_ms", "HRV", "ms"))
FLAG_DECISIONS = ("reduce", "swap")
FLAG_FLAGS = ("coach_review", "not_done_x2")
LOAD_LIFTS = {"squat": "Barbell_Squat", "bench": "Barbell_Bench_Press_-_Medium_Grip"}


def d(s):
    return dt.date.fromisoformat(str(s)[:10])


def f1(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------------ sections
def month(folder, today, weeks):
    view = rmp.view_monday(today)
    mondays = [view - dt.timedelta(weeks=k) for k in range(weeks, 0, -1)]
    return mondays, mondays[0], view - dt.timedelta(days=1)


def where(eff, band, cut):
    mev, mav_lo, mav_hi, mrv, keep_lo, keep_hi = band
    if eff > mrv:
        return "over MRV"
    if cut:
        return ("below the cut keep band" if eff < keep_lo else "above the cut keep band" if eff > keep_hi
                else "in the cut keep band")
    if eff < mev:
        return "below the usual coaching band"
    if eff < mav_lo:
        return "between MEV and MAV"
    return "in MAV" if eff <= mav_hi else "above MAV"


def the_month(folder, prog, mondays):
    planned = len(prog["routines"])
    titles = [r["title"] for r in prog["routines"]]
    sessions = Counter()
    for s in ch.working_sets(folder):
        m = pg.week_of(s["date"])
        if m in mondays and any(pg.session_matches(s["workout_name"], t) for t in titles):
            sessions[(m, s["session_id"])] += 1
    lines = ["| Week | Type | Sessions | Targets met | Hit rate |", "|---|---|---|---|---|"]
    total = Counter()
    for m in mondays:
        label = pg.week_label(m)
        path = pg.targets_path(folder, label)
        doc = pg.load_json(path) if os.path.exists(path) else {}
        g = Counter((doc.get("summary") or {}).get("grades") or {}) if doc.get("status") == "graded" else Counter()
        hr, n = pg.hit_rate(g)
        total.update(g)
        wtype = doc.get("graded_week_type") or doc.get("microcycle_type") or "—"
        done = sum(1 for (mm, _) in sessions if mm == m)
        lines.append(f"| {label} | {'easy' if wtype == 'recovery' else wtype} | {done}/{planned} | "
                     + (f"{g['hit']}/{n} | {hr * 100:.0f} %" if n else "— | —") + " |")
    hr, n = pg.hit_rate(total)
    lines += ["", f"Targets met in these weeks: " + (f"{total['hit']}/{n} ({hr * 100:.0f} %)." if n else "nothing graded."),
              pg.band_text(folder, pg.week_label(mondays[-1]))]
    return "\n".join(lines), (hr, n)


def volume(folder, start, end, cut):
    weeks = ch.weekly_sets(folder, start, end)
    if not weeks:
        return "No full training week in the month.", []
    lines = [f"Effective sets a week (direct ×1, secondary ×0.5), average of {len(weeks)} full weeks, easy weeks "
             "left out. The bands are coaching practice (RP), not study cut-offs; only MRV is a gate.", "",
             "| Muscle | Direct | Effective | MEV | MAV | MRV | Where |", "|---|---|---|---|---|---|---|"]
    effs, below = {}, []
    for m, band in BANDS.items():
        direct = sum(w.get(m, (0, 0))[0] for _, w in weeks) / len(weeks)
        effs[m] = eff = sum(w.get(m, (0, 0))[1] for _, w in weeks) / len(weeks)
        at = where(eff, band, cut)
        lines.append(f"| {m} | {f1(direct)} | {f1(eff)} | {band[0]} | {band[1]}–{band[2]} | {band[3]} | {at} |")
        if at.startswith("below"):
            below.append(m)
    flags = [f"below the usual coaching band: {', '.join(below)} (the program meets the evidence floors; these "
             "bands are practitioner ones: more sets there need Advanced with a priority, or longer sessions)"] \
        if below else []
    # MRV as the audit gates it: per group at the group's largest head, per muscle for the rest.
    grouped = {m for _, ms in pa.GROUPS for m in ms}
    over = [(g, sum(effs[m] for m in ms), max(BANDS[m][3] for m in ms)) for g, ms in pa.GROUPS]
    over += [(m, effs[m], BANDS[m][3]) for m in BANDS if m not in grouped]
    flags += [f"{g} {f1(v)} sets/week is over its MRV band ({cap})" for g, v, cap in over if v > cap]
    return "\n".join(lines), flags


def lifts(folder, prog, start, end):
    rows = ["| Exercise | 4 weeks before | Last 2 weeks | Change |", "|---|---|---|---|"]
    for ex in rmp.main_lifts(prog):
        v, detail = ch.e1rm_change(folder, ex, start, end)
        name = pa.CATALOGUE.get(ex, {}).get("name", ex)
        rows.append(f"| {name} | " + (" | ".join(detail.replace("best e1RM ", "").split(" → ")) + f" | {v:+.1f} % |"
                                       if v is not None else "— | — | not enough weeks |"))
    return "Best estimated 1-rep max (Epley, sets of 1–12 reps; easy weeks left out).\n\n" + "\n".join(rows)


def flagged(folder, mondays):
    """Rows the weekly loop flagged in the month: reduces, swaps, two weeks not done, coach review."""
    seen = {}
    for m in mondays + [mondays[-1] + dt.timedelta(days=7)]:
        path = pg.targets_path(folder, pg.week_label(m))
        if not os.path.exists(path):
            continue
        for r in pg.load_json(path)["rows"]:
            if r.get("decision") in FLAG_DECISIONS or set(r.get("flags") or []) & set(FLAG_FLAGS):
                seen[r["id"]] = (pg.week_label(m), r)
    if not seen:
        return "None: no reduce, swap or two-weeks-not-done rows this month.", []
    lines, out = [], []
    for rid, (label, r) in seen.items():
        alts = [pa.CATALOGUE[x]["name"] for x in _alternatives(folder, r["exercise_id"])]
        lines.append(f"- {label} · {r['name']} ({rid}): {pg.row_text(r)}"
                     + (f" Same-slot alternatives: {', '.join(alts)}." if alts else ""))
        out.append(r)
    return "\n".join(lines), out


def _alternatives(folder, ex_id):
    prog = pg.load_json(Path(folder) / "plan" / "program.json")
    for r in prog["routines"]:
        for s in r["exercises"]:
            if s["exercise_id"] == ex_id:
                return s.get("alternatives") or []
    return []


def body(folder, start, end):
    v, detail = ch.weight_rate(folder, start, end)
    waist = [(day, cm) for day, cm in af.body_series(folder, "waist_cm") if start <= d(day) <= end]
    out = [f"Body weight: {ch.fmt_value('weight_rate', v)}" + (f" ({detail})." if v is not None else f": {detail}.")]
    if len(waist) >= 2:
        out.append(f"Waist: {f1(waist[0][1])} cm ({waist[0][0]}) → {f1(waist[-1][1])} cm ({waist[-1][0]}).")
    return " ".join(out)


def health(folder, start, end):
    days = (end - start).days + 1
    prev = (start - dt.timedelta(days=days), start - dt.timedelta(days=1))
    vals = {}
    for r in af.read_rows(folder, "data/health.csv"):
        try:
            day, v = d(r["date"]), float(r["value"])
        except ValueError:
            continue
        key = "now" if start <= day <= end else "before" if prev[0] <= day <= prev[1] else None
        if key:
            vals.setdefault((r["metric"], key), []).append(v)
    lines = []
    for metric, label, unit in HEALTH:
        now, before = vals.get((metric, "now")), vals.get((metric, "before"))
        if not now:
            continue
        mean = lambda xs: sum(xs) / len(xs)
        fmt = (lambda x: f"{x:,.0f}") if metric == "steps" else f1
        lines.append(f"- {label}: {fmt(mean(now))} {unit}".rstrip() + f" a day (n={len(now)})"
                     + (f", the 4 weeks before {fmt(mean(before))}" if before else ""))
    if not lines:
        return "No health data in the month."
    return ("Context only. Never call fatigue on fewer than two signals that agree.\n\n" + "\n".join(lines))


def signals(folder, prog, today, hit, vol_flags, rows, graded, rm_state):
    """What next month could change. Each is a question for the athlete, never a decision."""
    out = []
    now_week = pb.program_week(prog, pg.sessions_done(folder, prog, rmp.view_monday(today)))
    ends = rmp.block_ends(prog, now_week + 8)
    nxt = next((e for e in ends if e >= now_week), None)
    if nxt is not None and nxt - now_week <= 4:
        out.append(f"The block ends with program week {nxt}{' (an easy week)' if rmp.easy_week(prog, nxt) else ''}: "
                   f"re-issue the program for week {nxt + 1} (`reissue`), with any swaps the athlete wants.")
    if prog.get("rebuild_at_week") and now_week >= prog["rebuild_at_week"] - 1:
        out.append(f"The program asks to be rebuilt at week {prog['rebuild_at_week']} (its sets or effort change).")
    adv = (prog.get("placement") or {}).get("advanced_check_week")
    if prog["level"] == "intermediate" and adv and now_week >= adv:
        out.append(f"Placement promised an Advanced offer from week {adv}: offer it (`reissue --promote`; it needs "
                   "squat and bench sets in the log).")
    hr, n = hit
    if n and hr is not None and not 0.70 <= hr <= 0.85:
        out.append(f"Hit rate {hr * 100:.0f} %: " + ("targets look easy: ask how hard the sets felt."
                                                     if hr > 0.85 else "targets look hard: ask about sleep, stress "
                                                     "and food before changing the program."))
    for r in rows:
        if r.get("decision") == "swap":
            out.append(f"{r['name']}: the weekly loop asks for another exercise (swap within its slot).")
    out += [f"Volume: {f}." for f in vol_flags]
    out += [f"Change {g['id']} ({g['title']}) is {g['verdict']}: {g['call']}." for g in graded
            if g["verdict"] in ("below band", "above band")]
    if rm_state and rm_state[1]:
        out.append(f"Roadmap: the {rm_state[0]['name']} phase's gates are due ({rm_state[2]}): "
                   "replan passed, missed (extend) or move on.")
    meta = adapt.adapt_meta(folder)
    if "until" in meta and today > d(meta["until"]):
        out.append(f"The temporary program ended {meta['until']}: `adapt.py restore`.")
    return out or ["Nothing asks for a change. \"No changes this month\" is a valid outcome."]


def enabled(folder):
    prof = adapt.header(folder, "profile.md")
    return bool(prof.get("nutrition_phase")) and not af.gate(prof, "nutrition"), not af.gate(prof, "photos")


def report(folder, today, weeks=4):
    prog = adapt.program(folder)
    mondays, start, end = month(folder, today, weeks)
    rm_state = None
    try:
        rm = rmp.read(folder)
        p, due, rows, outcome = rmp.check(folder, today)
        rm["_folder"] = folder
        rm_text = rmp.summary(rm, prog, today) + (
            f"\n\nGates of the {p['name']} phase, due now:\n\n{rmp.gate_table(rows)}\n\nSo far: {outcome}."
            if p and due else "")
        rm_state = (p, due, outcome) if p else None
    except SystemExit:
        rm_text = "No roadmap yet: the `roadmap` skill makes one (macrocycle, phases with gates)."
    cut = bool(rm_state and rm_state[0]["name"] == "cut")
    month_text, hit = the_month(folder, prog, mondays)
    vol_text, vol_flags = volume(folder, start, end, cut)
    flag_text, flag_rows = flagged(folder, mondays)
    graded = ch.grade(folder, end)
    nutrition, physique = enabled(folder)
    sections = [
        ("The month", month_text),
        ("Volume per muscle", vol_text),
        ("Main lifts", lifts(folder, prog, start, end)),
        ("Flagged by the weekly loop", flag_text),
        ("Body", body(folder, start, end)),
        ("Health", health(folder, start, end)),
        ("Past changes", ch.table(graded)),
        ("Roadmap", rm_text),
        ("Nutrition and physique", f"Nutrition skill: {'on' if nutrition else 'off'} · physique skill: "
                                   f"{'on' if physique else 'off'}."),
        ("Signals for next month", "\n".join(f"- {s}" for s in signals(folder, prog, today, hit, vol_flags,
                                                                       flag_rows, graded, rm_state))),
    ]
    title = f"# Monthly check-in · {today} · {pg.week_label(mondays[0])} to {pg.week_label(mondays[-1])}"
    text = title + "\n\n" + "\n\n".join(f"## {h}\n\n{b}" for h, b in sections) + "\n"
    return text, {"hit": hit, "graded": graded, "weeks": [pg.week_label(m) for m in mondays], "end": end}


def write(folder, today, text, info, decisions, notes):
    ch.grade(folder, info["end"], write=True)
    extra = "\n## Athlete's notes\n\n" + "\n".join(f"- “{n}”" for n in notes) + "\n" if notes else ""
    extra += "\n## Decisions\n\n" + ("\n".join(f"- {x}" for x in decisions) if decisions else
                                     "No changes this month.") + "\n"
    path = Path(folder) / "check-ins" / f"{today}-monthly.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text + extra, encoding="utf-8")
    hr, n = info["hit"]
    due = sum(1 for g in info["graded"] if g["due"])
    result = (f"{info['weeks'][0]} to {info['weeks'][-1]}: hit rate " + (f"{hr * 100:.0f} % (n={n})" if n else "—")
              + f", {due} change(s) graded, {len(decisions)} decision(s)")
    af.append_log(folder, "monthly-check-in", result, date=str(today))
    return path


# ------------------------------------------------------------------ re-issue
def best_set(folder, ex_id, since):
    sets = [s for s in ch.working_sets(folder) if s["exercise_id"] == ex_id and s["date"] >= since
            and s["kg"] > 0 and 1 <= s["reps"] <= ch.E1RM_MAX_REPS]
    return max(sets, key=lambda s: pg.epley(s["kg"], s["reps"])) if sets else None


def reissue(folder, today, swaps, promote, why=""):
    old_prof = (Path(folder) / "profile.md").read_text(encoding="utf-8")
    prof = adapt.header(folder, "profile.md")
    if swaps:
        merged = {x["from"]: x["to"] for x in prof.get("exercise_swaps") or [] if isinstance(x, dict)}
        merged.update(swaps)
        af.set_header(folder, "profile.md", "exercise_swaps",
                      "[" + ", ".join(f"{{from: {a}, to: {b}}}" for a, b in merged.items()) + "]")
    if promote:
        loads = []
        for name, ex in LOAD_LIFTS.items():
            s = best_set(folder, ex, today - dt.timedelta(days=28))
            if s is None:
                (Path(folder) / "profile.md").write_text(old_prof, encoding="utf-8")
                raise ValueError(f"--promote needs {pa.CATALOGUE[ex]['name']} sets in the last 4 weeks")
            loads.append(f"{{exercise: {name}, kg: {s['kg']:g}, reps: {s['reps']}}}")
        af.set_header(folder, "profile.md", "known_loads", "[" + ", ".join(loads) + "]")
    try:
        code, msg, old, new = adapt.rebuild(folder, today, adapt.overrides_of(adapt.adapt_meta(folder)))
    except ValueError:
        (Path(folder) / "profile.md").write_text(old_prof, encoding="utf-8")
        raise
    if code:
        (Path(folder) / "profile.md").write_text(old_prof, encoding="utf-8")
        return code, msg
    check = str(today + dt.timedelta(days=28))
    ids = []
    for a, b in swaps.items():
        ids.append(ch.add(folder, f"Swap {pa.CATALOGUE[a]['name']} → {pa.CATALOGUE[b]['name']}",
                          f"{pa.CATALOGUE[a]['name']} → {pa.CATALOGUE[b]['name']} wherever it ran",
                          why or "the athlete's choice at the monthly check-in", f"e1rm:{b}", "0..", check,
                          "monthly-check-in", str(today)))
    if promote:
        ids.append(ch.add(folder, "Advanced level", adapt.diff(old, new), why or "placement's Advanced offer accepted",
                          "hit_rate", "70..85", check, "monthly-check-in", str(today)))
    changed = adapt.diff(old, new)
    if not ids and changed != "no exercise changed":
        ids.append(ch.add(folder, f"Program re-issued at week {new['week']}", changed,
                          why or "new mesocycle", "hit_rate", "70..85", check, "monthly-check-in", str(today)))
    af.append_log(folder, "monthly-check-in", f"re-issued at week {new['week']}: {changed}"
                  + (f" ({', '.join(ids)})" if ids else ""), date=str(today))
    return 0, f"{msg}\nWhat changed: {changed}." + (f" Recorded: {', '.join(ids)}." if ids else " Nothing recorded.")


def parse_swap(text):
    a, sep, b = text.partition("=")
    if not sep or not a.strip() or not b.strip():
        raise ValueError(f"--swap {text!r}: FROM=TO with exercise ids")
    return a.strip(), b.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("--weeks", type=int, default=4)
    r.add_argument("--write", action="store_true")
    r.add_argument("--decision", action="append", default=[])
    r.add_argument("--note", action="append", default=[])
    ri = sub.add_parser("reissue")
    ri.add_argument("--swap", action="append", default=[])
    ri.add_argument("--promote", action="store_true")
    ri.add_argument("--why", default="")
    ri.add_argument("--dry-run", action="store_true", help="show the change on a copy; write nothing")
    for sp in sub.choices.values():
        sp.add_argument("--dir")
        sp.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    try:
        folder, today = af.find(a.dir), d(a.today)
        if a.cmd == "report":
            text, info = report(folder, today, a.weeks)
            if a.write:
                print(f"wrote {write(folder, today, text, info, a.decision, a.note)}")
            else:
                print(text, end="")
            return 0
        adapt.gate(folder)
        swaps = dict(parse_swap(x) for x in a.swap)
        run = lambda f: reissue(f, today, swaps, a.promote, a.why)
        code, msg = adapt.dry_run(folder, run) if a.dry_run else run(folder)
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 1
        return e.code
    print(msg, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
