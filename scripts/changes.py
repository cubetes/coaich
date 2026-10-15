#!/usr/bin/env python3
"""changes.py: plan/changes.md (every applied plan change with its success band) and the measurements that grade it.

    add   --dir D --title T --change C --why W --metric M --band LO..HI --check YYYY-MM-DD [--by SKILL] [--today D]
    list  --dir D                          the open changes
    grade --dir D [--today D] [--write]    grade every open change whose check date has come; --write records it

A band is `lo..hi` in the metric's unit; either side may be blank (`5..` = at least 5). Metrics:

    hit_rate              % of graded targets met (weekly targets files in the window)
    sessions_per_week     program sessions logged a week
    e1rm:<exercise_id>    % change of the best estimated 1-rep max (Epley, working sets of 1–12 reps):
                          the 4 weeks before the window (else its first 2 weeks) against its last 2 weeks
    sets:<muscle|group>   effective sets a week (direct ×1, secondary ×0.5), full weeks, easy weeks left out
    weight_rate           body weight change, % a week (least squares over the window)
    ask                   no number: the check-in asks the athlete

Verdicts: in band → keep · below band / above band → adjust or revert (the athlete decides) · too early (check date
not reached; the value so far is shown) · no data (not measurable: say so, never invent a number).
Python 3.9+ stdlib; reads the folder through athlete_folder.py.
"""
import argparse
import datetime as dt
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402
import program_audit as pa  # noqa: E402
import progression as pg  # noqa: E402

UNITS = {"hit_rate": "%", "sessions_per_week": "sessions/week", "e1rm": "%", "sets": "sets/week",
         "weight_rate": "%/week", "ask": ""}
WORKING = ("normal", "failure")
E1RM_MAX_REPS = 12
HEADER = ("# Plan changes\n\nEvery applied change, with the band that says it worked. The monthly check-in grades "
          "each one once its check date has come.\n")


# ------------------------------------------------------------------ bands
def parse_band(text):
    """`lo..hi` → (lo, hi) floats or None. ValueError on anything else."""
    m = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)?\s*\.\.\s*([+-]?\d+(?:\.\d+)?)?\s*", text or "")
    if not m or (m.group(1) is None and m.group(2) is None):
        raise ValueError(f"band {text!r}: expected lo..hi, e.g. 70..85, 5.. or ..-0.25")
    lo, hi = (None if g is None else float(g) for g in m.groups())
    if lo is not None and hi is not None and lo > hi:
        raise ValueError(f"band {text!r}: lo is above hi")
    return lo, hi


def check_metric(metric):
    kind = metric.split(":", 1)[0]
    if kind not in UNITS or (kind in ("e1rm", "sets")) != (":" in metric):
        raise ValueError(f"metric {metric!r}: one of hit_rate, sessions_per_week, e1rm:<exercise_id>, "
                         "sets:<muscle or group>, weight_rate, ask")
    if kind == "sets" and metric[5:] not in pa.MRV and metric[5:] not in dict(pa.GROUPS):
        raise ValueError(f"metric {metric!r}: muscle or group one of {', '.join(list(pa.MRV) + list(dict(pa.GROUPS)))}")
    return kind


def verdict(value, band):
    if value is None:
        return "no data"
    lo, hi = band
    if lo is not None and value < lo:
        return "below band"
    if hi is not None and value > hi:
        return "above band"
    return "in band"


CALL = {"in band": "keep", "below band": "adjust or revert", "above band": "adjust or revert",
        "no data": "not measurable", "too early": "wait"}


# ------------------------------------------------------------------ the folder's data
def d(s):
    return dt.date.fromisoformat(str(s)[:10])


def working_sets(folder):
    """data/sets.csv working sets: [{date, session_id, workout_name, exercise_id, kg, reps}]."""
    out = []
    for r in af.read_rows(folder, "data/sets.csv"):
        if (r.get("set_type") or "normal") not in WORKING:
            continue
        try:
            out.append({"date": d(r["date"]), "session_id": r.get("session_id") or f"{r['date']}-{r.get('workout_name')}",
                        "workout_name": r.get("workout_name", ""), "exercise_id": r.get("exercise_id", ""),
                        "kg": float(r.get("weight_kg") or 0), "reps": int(float(r.get("reps") or 0))})
        except ValueError:
            continue
    return out


def easy_mondays(folder):
    """Mondays of the ISO weeks that ran as easy weeks (their targets file says recovery)."""
    out = set()
    for label, path in pg.list_target_files(folder):
        doc = pg.load_json(path)
        if (doc.get("graded_week_type") or doc.get("microcycle_type")) == "recovery":
            out.add(pg.parse_week(label))
    return out


def full_weeks(start, end):
    """Mondays of the ISO weeks wholly inside [start, end]."""
    m = pg.week_of(start) + (dt.timedelta(0) if start.weekday() == 0 else dt.timedelta(days=7))
    out = []
    while m + dt.timedelta(days=6) <= end:
        out.append(m)
        m += dt.timedelta(days=7)
    return out


def program_titles(folder):
    path = Path(folder) / "plan" / "program.json"
    return [r.get("title", "") for r in pg.load_json(path).get("routines", [])] if path.exists() else []


# ------------------------------------------------------------------ measurements
def hit_rate(folder, start, end):
    c, weeks = defaultdict(int), 0
    for label, path in pg.list_target_files(folder):
        doc = pg.load_json(path)
        mon = pg.parse_week(label)
        if doc.get("status") != "graded" or mon < pg.week_of(start) or mon + dt.timedelta(days=6) > end:
            continue
        for k, v in (doc.get("summary", {}).get("grades") or {}).items():
            c[k] += v
        weeks += 1
    n = c["hit"] + c["partial"] + c["miss"]
    return (round(100 * c["hit"] / n, 1) if n else None), f"n={n} targets, {weeks} graded weeks"


def sessions_per_week(folder, start, end):
    days = (end - start).days + 1
    if days < 7:
        return None, "under a week of data"
    titles = program_titles(folder)
    ids = {s["session_id"] for s in working_sets(folder) if start <= s["date"] <= end
           and (not titles or any(pg.session_matches(s["workout_name"], t) for t in titles))}
    return round(len(ids) * 7 / days, 2), f"{len(ids)} sessions in {days} days"


def weekly_best_e1rm(folder, exercise_id):
    """{monday: best Epley e1RM} over non-easy weeks for one exercise."""
    easy = easy_mondays(folder)
    best = {}
    for s in working_sets(folder):
        if s["exercise_id"] != exercise_id or s["kg"] <= 0 or not 1 <= s["reps"] <= E1RM_MAX_REPS:
            continue
        mon = pg.week_of(s["date"])
        if mon in easy:
            continue
        best[mon] = max(best.get(mon, 0.0), pg.epley(s["kg"], s["reps"]))
    return best


def e1rm_change(folder, exercise_id, start, end):
    weeks = weekly_best_e1rm(folder, exercise_id)
    before = [m for m in weeks if pg.week_of(start) - dt.timedelta(days=28) <= m < pg.week_of(start)]
    inside = sorted(m for m in weeks if pg.week_of(start) <= m <= end)
    base = before or inside[:2]
    recent = [m for m in inside if m not in base][-2:]
    if not base or not recent:
        return None, "not enough weeks with this lift"
    b, r = max(weeks[m] for m in base), max(weeks[m] for m in recent)
    return round(100 * (r / b - 1), 1), f"best e1RM {b:.1f} kg → {r:.1f} kg"


def weekly_sets(folder, start, end):
    """[(monday, {muscle: (direct, effective)})] for full, non-easy ISO weeks in [start, end] with a session."""
    easy = easy_mondays(folder)
    weeks = [m for m in full_weeks(start, end) if m not in easy]
    per = {m: defaultdict(lambda: [0.0, 0.0]) for m in weeks}
    trained = set()
    for s in working_sets(folder):
        mon = pg.week_of(s["date"])
        ex = pa.CATALOGUE.get(s["exercise_id"])
        if mon not in per or not ex:
            continue
        trained.add(mon)
        for m, w in pa.muscles(ex):
            per[mon][m][1] += w
            if w == 1.0:
                per[mon][m][0] += 1
    return [(m, {k: tuple(v) for k, v in per[m].items()}) for m in weeks if m in trained]


def effective_sets(folder, name, start, end):
    weeks = weekly_sets(folder, start, end)
    if not weeks:
        return None, "no full training week"
    members = dict(pa.GROUPS).get(name, [name])
    avg = sum(sum(w.get(m, (0, 0))[1] for m in members) for _, w in weeks) / len(weeks)
    return round(avg, 1), f"{len(weeks)} full weeks, easy weeks left out"


def weight_rate(folder, start, end):
    pts = [((d(day) - start).days, kg) for day, kg in af.body_series(folder, "weight_kg")
           if start <= d(day) <= end]
    if len(pts) < 6 or pts[-1][0] - pts[0][0] < 14:
        return None, f"{len(pts)} weigh-ins; need 6 over 2 weeks"
    n = len(pts)
    mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
    slope = sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts)
    return round(100 * slope * 7 / my, 2), f"{slope * 7:+.2f} kg/week from {n} weigh-ins, mean {my:.1f} kg"


def measure(folder, metric, start, end):
    """(value or None, detail) for a metric over [start, end] (dates)."""
    kind = check_metric(metric)
    if kind == "ask":
        return None, "ask the athlete"
    arg = metric.split(":", 1)[1] if ":" in metric else None
    return {"hit_rate": lambda: hit_rate(folder, start, end),
            "sessions_per_week": lambda: sessions_per_week(folder, start, end),
            "e1rm": lambda: e1rm_change(folder, arg, start, end),
            "sets": lambda: effective_sets(folder, arg, start, end),
            "weight_rate": lambda: weight_rate(folder, start, end)}[kind]()


def fmt_value(metric, value):
    if value is None:
        return "—"
    unit = UNITS[metric.split(":", 1)[0]]
    sign = "+" if metric.split(":")[0] in ("e1rm", "weight_rate") and value > 0 else ""
    return f"{sign}{value:g} {unit}".strip()


# ------------------------------------------------------------------ plan/changes.md
ENTRY = re.compile(r"^## (c\d+) · (\d{4}-\d{2}-\d{2}) · (.+)$")


def read(folder):
    """plan/changes.md → [{id, applied, title, change, why, by, metric, band, check, graded: [lines]}]."""
    path = Path(folder) / "plan" / "changes.md"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ENTRY.match(line)
        if m:
            out.append({"id": m.group(1), "applied": m.group(2), "title": m.group(3), "graded": []})
            continue
        if not out or not line.startswith("- "):
            continue
        k, _, v = line[2:].partition(":")
        if k.startswith("graded "):
            out[-1]["graded"].append(line[2:])
        elif k.strip() in ("change", "why", "by", "metric", "band", "check"):
            out[-1][k.strip()] = v.strip()
    return out


def add(folder, title, change, why, metric, band, check, by="", today=None):
    """Append one change. Validates the metric, band and dates first. Returns its id."""
    if check_metric(metric) != "ask":
        parse_band(band)
    today = today or dt.date.today().isoformat()
    if d(check) <= d(today):
        raise ValueError(f"check date {check} must be after {today}")
    path = Path(folder) / "plan" / "changes.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else HEADER
    cid = f"c{max([int(c['id'][1:]) for c in read(folder)] or [0]) + 1}"
    one = lambda s: " ".join(str(s).split())
    lines = [f"## {cid} · {today} · {one(title)}", f"- change: {one(change)}", f"- why: {one(why)}"]
    lines += [f"- by: {one(by)}"] if by else []
    lines += [f"- metric: {metric}", f"- band: {band if metric != 'ask' else '—'}", f"- check: {check}"]
    path.write_text(text.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return cid


def open_changes(folder):
    return [c for c in read(folder) if not c["graded"]]


def grade(folder, today, write=False):
    """Grade every open change. Due ones (check date reached) get a verdict; with write, a `graded` line each.
    Returns [{…change, value, detail, verdict, call, due}]."""
    out = []
    for c in open_changes(folder):
        metric = c.get("metric", "ask")
        value, detail = measure(folder, metric, d(c["applied"]), today)
        due = today >= d(c.get("check") or c["applied"])
        band = parse_band(c["band"]) if metric != "ask" else (None, None)
        v = verdict(value, band) if due and metric != "ask" else "too early" if not due else "no data"
        if metric == "ask" and due:
            detail = "ask the athlete"
        out.append(dict(c, value=value, detail=detail, verdict=v, call=CALL[v], due=due))
    if write:
        path = Path(folder) / "plan" / "changes.md"
        text = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        for g in reversed([g for g in out if g["due"]]):
            i = next(k for k, line in enumerate(text) if line.startswith(f"## {g['id']} · "))
            j = i + 1
            while j < len(text) and text[j].startswith("- "):
                j += 1
            text.insert(j, f"- graded {today}: {g['verdict']} ({fmt_value(g.get('metric', 'ask'), g['value'])}; "
                           f"{g['detail']}) · {g['call']}")
        if out:
            path.write_text("\n".join(text) + "\n", encoding="utf-8")
    return out


def table(graded):
    """Markdown table of graded changes (the monthly check-in's 'Past changes' section)."""
    if not graded:
        return "No open plan changes."
    lines = ["| Change | Applied | Metric | Band | Now | Verdict | Call |", "|---|---|---|---|---|---|---|"]
    for g in graded:
        metric = g.get("metric", "ask")
        band = g.get("band", "—")
        now = fmt_value(metric, g["value"]) + (f" ({g['detail']})" if g["detail"] else "")
        when = f" (check {g.get('check')})" if g["verdict"] == "too early" else ""
        lines.append(f"| {g['id']} {g['title']} | {g['applied']} | {metric} | {band} | {now} | "
                     f"{g['verdict']}{when} | {g['call']} |")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    for k in ("title", "change", "why", "metric", "check"):
        a.add_argument(f"--{k}", required=True)
    a.add_argument("--band", default="", help="lo..hi in the metric's unit (not for metric ask)")
    a.add_argument("--by", default="")
    for name in ("list", "grade"):
        sub.add_parser(name)
    for sp in sub.choices.values():
        sp.add_argument("--dir", default=None)
        sp.add_argument("--today", default=dt.date.today().isoformat())
    sub.choices["grade"].add_argument("--write", action="store_true")
    args = p.parse_args(argv)
    try:
        folder = af.find(args.dir)
        if args.cmd == "add":
            cid = add(folder, args.title, args.change, args.why, args.metric, args.band, args.check, args.by,
                      args.today)
            print(f"{cid} added to plan/changes.md")
        elif args.cmd == "list":
            for c in open_changes(folder):
                print(f"{c['id']} · {c['applied']} · {c['title']} · {c.get('metric')} {c.get('band')} · check {c.get('check')}")
        else:
            print(table(grade(folder, d(args.today), args.write)))
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
