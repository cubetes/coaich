#!/usr/bin/env python3
"""adapt.py: fit the plan around pain or a temporary constraint, and back to normal. Every program change goes
through program_build.issue (the audit gates it) and is written to plan/changes.md with its success band.

    injury     --dir D --area A (--red-flag | --no-red-flag)   pain: red flag → its exercises are left out;
                                                                otherwise safer exercises in the same slots
    checked    --dir D --area A        a physiotherapist or doctor checked a red-flag area: its slots come back
    clear      --dir D --area A        the pain is gone: the area leaves profile.md, the full program returns
    constraint --dir D --from D --to D [--days N] [--minutes M] [--no-gym]
                                       up to 14 days: those weeks run as moderated (one set fewer; sessions not
                                       done hold their targets) or travel (no gym: targets frozen) in CURRENT.md;
                                       longer: the program is rebuilt for N days × M minutes until --to
    restore    --dir D                 end a long constraint: rebuild from profile.md
    status     --dir D                 what is adapted now, and whether its end date has passed

All take --today YYYY-MM-DD and --dry-run (the change on a copy, nothing written). Areas: knee, lower-back, shoulder, elbow-wrist, hip, other. CoAIch never classifies
an injury: a red flag (strong, sharp, recent, swollen or spreading) means "see a professional and leave the area
out"; anything else means "train around it, stop what hurts". Gym only (Release 1): no home or hotel programs.
Exit 0 done · 1 the audit refused the program (nothing written) · 2 stop (safety) or bad input.
"""
import argparse
import datetime as dt
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402
import changes as ch  # noqa: E402
import program_build as pb  # noqa: E402
import progression as pg  # noqa: E402

AREAS = {"knee": "knee", "lower-back": "low_back", "shoulder": "shoulder", "elbow-wrist": "elbow_wrist", "hip": "hip",
         "other": "other"}
SHORT_DAYS = 14                     # up to this long, a constraint changes week types, not the program
CHECK_DAYS = 28                     # when an injury change is graded
BLOCK = re.compile(r"<!-- coaich:adapt(?P<meta>[^>]*)-->.*?<!-- /coaich:adapt -->\n?", re.S)

# Copy (lawyer review pending) — same wording as skills/safety/SKILL.md.
RED_FLAG = ("That pain should be checked by a physiotherapist or doctor before you load the area. Until then we leave "
            "out the exercises that load it. Once it's been checked, tell me and I'll add them back.")
NO_RED_FLAG = ("We'll train around it and pick exercises that don't hurt. If an exercise hurts, stop it and tell me. "
               "If the pain gets worse, see a physiotherapist or doctor.")
COMING_BACK = ("First session back for each exercise that returns: pick a weight you could lift for the top of its rep "
               "range with 3–4 reps left. That session sets its starting weight; the weekly review builds from there.")


def d(s):
    return dt.date.fromisoformat(str(s)[:10])


# ------------------------------------------------------------------ folder state
def header(folder, name):
    p = Path(folder) / name
    return pb.front_matter(p.read_text(encoding="utf-8")) if p.exists() else {}


def gate(folder):
    af.safety_stop(folder)


def program(folder):
    path = Path(folder) / "plan" / "program.json"
    if not path.exists():
        raise SystemExit("REFUSED: no plan/program.json; build a program first (program-build skill).")
    return pg.load_json(path)


def pain_list(folder):
    out = []
    for p in header(folder, "profile.md").get("pain") or []:
        p = {"area": p} if isinstance(p, str) else dict(p)
        area = next((k for k, v in AREAS.items() if v == pb.PROFILE_AREA.get(str(p.get("area")))), None)
        if area:
            out.append({"area": area, "red_flag": bool(p.get("red_flag")), "checked": p.get("checked") or ""})
    return out


def write_pain(folder, pain):
    items = [f"{{area: {p['area']}, red_flag: {str(p['red_flag']).lower()}, checked: {p['checked'] or ''}}}"
             for p in pain]
    af.set_header(folder, "profile.md", "pain", "[" + ", ".join(items) + "]")
    # The safety record follows the pain list (skills/safety/SKILL.md › Record).
    s = header(folder, "coaich.md")
    reasons = [r for r in (s.get("safety_reasons") or []) if not str(r).startswith("red-flag:")]
    reasons += [f"red-flag:{p['area']}" for p in pain if p["red_flag"] and not p["checked"]]
    af.set_header(folder, "coaich.md", "safety_reasons", "[" + ", ".join(reasons) + "]")
    af.set_header(folder, "coaich.md", "safety_status", "warn" if reasons or pain else "go")


def adapt_meta(folder):
    """The active long constraint from CURRENT.md's adapt block: {days, minutes, until} or {}."""
    path = Path(folder) / "plan" / "CURRENT.md"
    m = BLOCK.search(path.read_text(encoding="utf-8")) if path.exists() else None
    if not m:
        return {}
    return dict(kv.split("=", 1) for kv in m.group("meta").split() if "=" in kv)


def calendar_rows(folder, today):
    """The adapt block's week-type rows still needed: a week's row stays until it has been graded (one week on)."""
    path = Path(folder) / "plan" / "CURRENT.md"
    m = BLOCK.search(path.read_text(encoding="utf-8")) if path.exists() else None
    return [x for x in (m.group(0).splitlines() if m else []) if re.match(r"\|\s*W\d+\s*\|", x)
            and d(x.split("|")[3].strip()) + dt.timedelta(days=13) >= today]


def write_block(folder, meta, lines, rows):
    """Replace (or remove, when lines is empty) the adapt block of CURRENT.md."""
    path = Path(folder) / "plan" / "CURRENT.md"
    old = path.read_text(encoding="utf-8") if path.exists() else "# In force today\n\n"
    block = ""
    if lines or rows:
        tag = "".join(f" {k}={v}" for k, v in meta.items())
        block = (f"<!-- coaich:adapt{tag} -->\n## Adapted\n\n" + "".join(f"- {x}\n" for x in lines)
                 + ("\n" if lines and rows else "")
                 + ("Week types (read by the progression engine):\n\n| Week | Type | Monday | Why |\n|---|---|---|---|\n"
                    + "\n".join(rows) + "\n" if rows else "") + "<!-- /coaich:adapt -->\n")
    m = BLOCK.search(old)
    new = old[:m.start()] + block + old[m.end():] if m else (old.rstrip("\n") + "\n\n" + block if block else old)
    path.write_text(new, encoding="utf-8")


# ------------------------------------------------------------------ rebuild through program_build
def names(prog):
    return {r["title"]: {s["name"]: s["sets"] for s in r["exercises"]} for r in prog["routines"]}


def diff(old, new):
    """What changed between two programs, in plain words."""
    out = []
    if (old["days"], old["minutes"]) != (new["days"], new["minutes"]):
        out.append(f"{old['days']} days × {old['minutes']} min → {new['days']} days × {new['minutes']} min")
    a, b = names(old), names(new)
    if not set(a) & set(b):
        return "; ".join(out + [f"new sessions {', '.join(b)} ({old.get('name', '?')} → {new.get('name', '?')})"])
    for title in list(dict.fromkeys(list(a) + list(b))):
        x, y = a.get(title, {}), b.get(title, {})
        gone, came = [n for n in x if n not in y], [n for n in y if n not in x]
        sets = [f"{n} {x[n]}→{y[n]}" for n in x if n in y and x[n] != y[n]]
        if gone or came or sets:
            out.append(f"{title}: " + "; ".join(([f"out {', '.join(gone)}"] if gone else [])
                                                 + ([f"in {', '.join(came)}"] if came else [])
                                                 + ([f"sets {', '.join(sets)}"] if sets else [])))
    return "; ".join(out) or "no exercise changed"


def rebuild(folder, today, overrides=None):
    """program_build.issue at the current program week, keeping week 1's date. → (code, message, old, new)."""
    old = program(folder)
    answers = pb.read_answers(folder)
    answers.update(overrides or {})
    week = pb.program_week(old, pg.sessions_done(folder, old, today + dt.timedelta(days=1)))
    code, msg = pb.issue(folder, answers, week, str(today), start=old["start"])
    return code, msg, old, (program(folder) if code == 0 else old)


def overrides_of(meta):
    return {k: int(meta[k]) for k in ("days", "minutes") if k in meta}


def dry_run(folder, fn):
    """Run fn(copy) on a throwaway copy of the folder: the athlete sees the change before saying yes."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "athlete"
        shutil.copytree(folder, copy, ignore=shutil.ignore_patterns("raw", "photos", ".git"))
        code, msg = fn(copy)
    return code, msg.replace(str(copy), ".") + "\n(dry run: nothing was written)"


def record(folder, today, title, change, why, metric, band, check_days):
    return ch.add(folder, title, change, why, metric, band, str(today + dt.timedelta(days=check_days)), "adapt",
                  str(today))


# ------------------------------------------------------------------ commands
def injury(folder, area, red_flag, today):
    pain = [p for p in pain_list(folder) if p["area"] != area]
    pain.append({"area": area, "red_flag": red_flag, "checked": ""})
    return _pain_change(folder, pain, today, f"{area} pain" + (" (red flag)" if red_flag else ""),
                        "red flag: see a physiotherapist or doctor; the exercises that load the area are left out"
                        if red_flag else "no red flag: safer exercises in the same slots",
                        RED_FLAG if red_flag else NO_RED_FLAG)


def checked(folder, area, today):
    pain = pain_list(folder)
    hit = [p for p in pain if p["area"] == area and p["red_flag"]]
    if not hit:
        raise ValueError(f"no red-flag {area} pain in profile.md")
    hit[0]["checked"] = str(today)
    return _pain_change(folder, pain, today, f"{area} checked by a professional",
                        "checked: its slots come back, still with the safer exercises", COMING_BACK)


def clear(folder, area, today):
    pain = pain_list(folder)
    if not any(p["area"] == area for p in pain):
        raise ValueError(f"no {area} pain in profile.md")
    return _pain_change(folder, [p for p in pain if p["area"] != area], today, f"{area} pain gone",
                        "back to the full program", COMING_BACK)


def _pain_change(folder, pain, today, title, why, say):
    before = pain_list(folder)
    write_pain(folder, pain)
    code, msg, old, new = rebuild(folder, today, overrides_of(adapt_meta(folder)))
    if code:
        write_pain(folder, before)          # the audit refused: put the answers back, nothing changed
        return code, msg
    cid = record(folder, today, title, diff(old, new), why, "sessions_per_week", f"{max(1, new['days'] - 1)}..",
                 CHECK_DAYS)
    af.append_log(folder, "adapt", f"{title}: {diff(old, new)} ({cid})", date=str(today))
    return 0, f"{say}\n\n{msg}\nChange {cid}: {diff(old, new)}"


def constraint(folder, start, end, days, minutes, no_gym, today):
    prog = program(folder)
    if end < start:
        raise ValueError("--to is before --from")
    if days is not None and not 0 <= days <= 6 or minutes is not None and not 30 <= minutes <= 75:
        raise ValueError("--days 0–6 and --minutes 30–75")
    days = 0 if no_gym else days
    long = (end - start).days + 1 > SHORT_DAYS and not no_gym and days != 0
    if long:
        if days is not None and days < 2:
            raise ValueError("a program needs 2 days or more; for fewer, run it as travel weeks (--no-gym)")
        meta = {"days": days or prog["days"], "minutes": minutes or prog["minutes"], "until": str(end)}
        code, msg, old, new = rebuild(folder, today, overrides_of(meta))
        if code:
            return code, msg
        write_block(folder, meta, _current([x for x in _block_lines(folder) if x.startswith("Short constraint")],
                                           today)
                    + [f"Until {end}: {new['days']} days × {new['minutes']} min ({new['name']}, was {old['name']}).",
                                   f"Back to normal from {end + dt.timedelta(days=1)}: `adapt.py restore`. "
                                   + COMING_BACK], calendar_rows(folder, today))
        cid = record(folder, today, f"Temporary program until {end}", diff(old, new), "a temporary schedule",
                     "sessions_per_week", f"{max(1, new['days'] - 1)}..", (end - today).days + 1)
        af.append_log(folder, "adapt", f"temporary {new['days']} days × {new['minutes']} min until {end} ({cid})",
                      date=str(today))
        return 0, f"{msg}\nChange {cid}: {diff(old, new)}"
    kind = "Travel" if no_gym or days == 0 else "Moderated"
    if kind == "Moderated" and (days is None or days >= prog["days"]) and (minutes is None or minutes >= prog["minutes"]):
        return 0, "Nothing to adapt: the program already fits those days and minutes."
    why = ("no gym: targets frozen, nothing graded" if kind == "Travel" else
           f"{days or prog['days']} days × {minutes or prog['minutes']} min: one set fewer per exercise; run the "
           "sessions in order, what is not done holds its target")
    rows = {r.split("|")[3].strip(): r for r in calendar_rows(folder, today)}
    m, hints = pg.week_of(start), []
    while m <= end:
        rows[str(m)] = f"| W{m.isocalendar()[1]} | {kind} | {m} | adapt: {why} |"
        if os.path.exists(pg.targets_path(folder, pg.week_label(m))) and \
                pg.load_json(pg.targets_path(folder, pg.week_label(m))).get("status") in ("applied", "graded"):
            hints.append(f"{pg.week_label(m)} targets are already applied: re-run `progression.py propose --dir . "
                         f"--week {pg.week_label(m)} --week-type {kind.lower()} --force`, then apply, so it is not "
                         "graded as a full week.")
        m += dt.timedelta(days=7)
    lines = _block_lines(folder) + [f"Short constraint {start} → {end}: {kind.lower()} ({why})."]
    write_block(folder, adapt_meta(folder), _current(lines, today), [rows[k] for k in sorted(rows)])
    metric, band = ("ask", "") if kind == "Travel" else ("sessions_per_week", f"{max(1, (days or prog['days']) - 1)}..")
    cid = record(folder, today, f"{kind} weeks {start} → {end}", f"{kind.lower()} week type in CURRENT.md", why,
                 metric, band, (end - today).days + 7)
    af.append_log(folder, "adapt", f"{kind.lower()} {start} → {end} ({cid})", date=str(today))
    return 0, f"{kind} from {start} to {end}: {why}. Change {cid}." + "".join(f"\n{h}" for h in hints)


def _current(lines, today):
    """Drop short-constraint lines that have ended."""
    return [x for x in lines if not (m := re.match(r"Short constraint \S+ → (\S+):", x)) or d(m.group(1)) >= today]


def _block_lines(folder):
    path = Path(folder) / "plan" / "CURRENT.md"
    m = BLOCK.search(path.read_text(encoding="utf-8")) if path.exists() else None
    return [x[2:] for x in (m.group(0).splitlines() if m else []) if x.startswith("- ")]


def restore(folder, today):
    meta = adapt_meta(folder)
    if "until" not in meta:
        return 0, "Nothing to restore: no temporary program in CURRENT.md."
    code, msg, old, new = rebuild(folder, today)
    if code:
        return code, msg
    write_block(folder, {}, _current([x for x in _block_lines(folder) if x.startswith("Short constraint")], today),
                calendar_rows(folder, today))
    cid = record(folder, today, "Back to the normal program", diff(old, new), "the temporary schedule ended",
                 "sessions_per_week", f"{max(1, new['days'] - 1)}..", CHECK_DAYS)
    af.append_log(folder, "adapt", f"restored: {diff(old, new)} ({cid})", date=str(today))
    return 0, f"{COMING_BACK}\n\n{msg}\nChange {cid}: {diff(old, new)}"


def status(folder, today):
    meta, lines = adapt_meta(folder), _block_lines(folder)
    pain = pain_list(folder)
    out = [f"Pain: " + (", ".join(f"{p['area']}" + (" (red flag, checked " + p["checked"] + ")" if p["checked"]
                                                    else " (red flag)" if p["red_flag"] else "") for p in pain)
                        or "none")]
    out += lines or ["No temporary constraint."]
    if "until" in meta and today > d(meta["until"]):
        out.append(f"DUE: the temporary program ended {meta['until']}: run `adapt.py restore`.")
    return 0, "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("injury", "checked", "clear"):
        sp = sub.add_parser(name)
        sp.add_argument("--area", required=True, choices=sorted(AREAS))
    flag = sub.choices["injury"].add_mutually_exclusive_group(required=True)
    flag.add_argument("--red-flag", dest="red_flag", action="store_true")
    flag.add_argument("--no-red-flag", dest="red_flag", action="store_false")
    c = sub.add_parser("constraint")
    c.add_argument("--from", dest="start", required=True)
    c.add_argument("--to", dest="end", required=True)
    c.add_argument("--days", type=int)
    c.add_argument("--minutes", type=int)
    c.add_argument("--no-gym", action="store_true")
    sub.add_parser("restore")
    sub.add_parser("status")
    for sp in sub.choices.values():
        sp.add_argument("--dir")
        sp.add_argument("--today", default=dt.date.today().isoformat())
        sp.add_argument("--dry-run", action="store_true", help="show the change on a copy; write nothing")
    a = ap.parse_args(argv)
    try:
        folder, today = af.find(a.dir), d(a.today)
        if a.cmd != "status":
            gate(folder)
        run = {
            "injury": lambda f: injury(f, a.area, a.red_flag, today),
            "checked": lambda f: checked(f, a.area, today),
            "clear": lambda f: clear(f, a.area, today),
            "constraint": lambda f: constraint(f, d(a.start), d(a.end), a.days, a.minutes, a.no_gym, today),
            "restore": lambda f: restore(f, today),
            "status": lambda f: status(f, today),
        }[a.cmd]
        code, msg = dry_run(folder, run) if a.dry_run else run(folder)
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
