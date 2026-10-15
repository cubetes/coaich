#!/usr/bin/env python3
"""How well each Claude model rates progress photos: a benchmark you run on your own computer.

Usage: python3 tools/photo_bench.py --dir <athlete folder> [--models haiku,sonnet,opus] [--repeats 3]
                                    [--dates YYYY-MM-DD,...] [--run]

Without --run it only lists what it would send. It sends nothing but the copies photos.py already filed
(photos/YYYY-MM-DD/<pose>.jpg, face and metadata removed), to your own Claude session, through the `claude` command;
every other path is refused. Results stay in the athlete folder, in bench/ (never in this repository):
  bench/reference.csv  your own rating, filled in blind before you look at any model's answer (a template is written)
  bench/runs.csv       every model answer with its cost and time
  bench/report.md      agreement with your rating (exact, within one tier, quadratic-weighted kappa), repeat
                       agreement, change between dates, the body-fat range against data/body.csv, cost and time
Standard library only. It never writes ratings or plans: the physique skill does that, with your OK.
"""
import argparse
import csv
import itertools
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import photo_guard  # noqa: E402
from photos import GROUPS, RATINGS  # noqa: E402

NOT_VISIBLE = "not-visible"
RUN_COLS = ["model", "date", "repeat", "ok", "group", "tier", "body_fat_lo", "body_fat_hi", "cost_usd", "seconds"]
PROMPT = """Rate the progress photos of one person, taken on {date}: {files}.
Read each file. They are already anonymised. Rate how developed each muscle group looks compared with the rest of
this person's own body, never against other people and never how attractive anyone looks, with the CoAIch rubric
(references/muscle-rubric.md): strong, adequate, lagging, severely-lagging, or not-visible when the photos do not
show it. Also give a body-fat range in percent. Reply with JSON only, no other text:
{{"ratings": {{{groups}}}, "confidence": "high|medium|low", "body_fat_range": [low, high]}}"""


# ---------------------------------------------------------------- inputs
def photo_sets(folder, dates=None):
    """{date: [filed copy paths]}, sorted. Only files photo_guard accepts as filed copies; anything else refused."""
    out = {}
    for path in sorted(Path(folder, "photos").glob("*/*.jpg")):
        real = path.resolve()
        if not photo_guard.filed_copy(real):
            raise SystemExit(f"refused: {path} is not a filed copy (photos/YYYY-MM-DD/<pose>.jpg written by photos.py)")
        if dates and path.parent.name not in dates:
            continue
        out.setdefault(path.parent.name, []).append(str(path.relative_to(folder)))
    return out


def prompt_for(date, files):
    return PROMPT.format(date=date, files=", ".join(files), groups=", ".join(f'"{g}": "..."' for g in GROUPS))


def read_reference(folder):
    """{(date, group): tier} from bench/reference.csv; blank or unknown tiers are skipped."""
    path = Path(folder, "bench", "reference.csv")
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        return {(r["date"], r["group"]): r["tier"].strip() for r in csv.DictReader(fh)
                if r.get("tier", "").strip() in RATINGS}


def write_reference_template(folder, dates):
    path = Path(folder, "bench", "reference.csv")
    if path.exists():
        return False
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "group", "tier"])
        for d in dates:
            for g in GROUPS:
                w.writerow([d, g, ""])
    return True


def measured_body_fat(folder):
    """{date: body_fat_pct} from data/body.csv rows not estimated from photos (tape, DEXA, a scale)."""
    path = Path(folder, "data", "body.csv")
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["date"]: float(r["body_fat_pct"]) for r in csv.DictReader(fh)
                if (r.get("body_fat_pct") or "").strip() and "photo" not in (r.get("source") or "")}


# ---------------------------------------------------------------- one model call
def parse_answer(text):
    """The model's JSON → ({group: tier}, (lo, hi) or None); None when it is not valid JSON in the asked shape."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else None
        ratings = {g: str(t).strip().lower() for g, t in data["ratings"].items() if g in GROUPS}
        if not ratings or any(t not in RATINGS + (NOT_VISIBLE,) for t in ratings.values()):
            return None
        bf = data.get("body_fat_range")
        bf = (float(bf[0]), float(bf[1])) if isinstance(bf, list) and len(bf) == 2 else None
        return ratings, bf
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def ask(model, date, files, folder, claude="claude"):
    """One rating from one model → (answer or None, cost_usd, seconds)."""
    start = time.monotonic()
    r = subprocess.run([claude, "-p", prompt_for(date, files), "--model", model, "--output-format", "json",
                        "--allowedTools", "Read"], cwd=folder, capture_output=True, text=True)
    seconds = round(time.monotonic() - start, 1)
    try:
        out = json.loads(r.stdout)
    except ValueError:
        return None, 0.0, seconds
    return parse_answer(out.get("result", "")), float(out.get("total_cost_usd") or 0.0), seconds


# ---------------------------------------------------------------- scores
def kappa_qw(pairs):
    """Quadratic-weighted Cohen's kappa over (tier, tier) pairs on the 4-tier scale; None without variance."""
    pairs = [(RATINGS.index(a), RATINGS.index(b)) for a, b in pairs if a in RATINGS and b in RATINGS]
    n, k = len(pairs), len(RATINGS)
    if not n:
        return None
    w = [[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)]
    obs = [[0.0] * k for _ in range(k)]
    for a, b in pairs:
        obs[a][b] += 1 / n
    ra = [sum(row) for row in obs]
    rb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    expected = sum(w[i][j] * ra[i] * rb[j] for i in range(k) for j in range(k))
    if expected == 0:
        return None  # both raters used one tier only: kappa is undefined
    return 1 - sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k)) / expected


def agreement(pairs):
    """(exact share, within-one-tier share) over pairs both rated on the scale; (None, None) if none."""
    pairs = [(RATINGS.index(a), RATINGS.index(b)) for a, b in pairs if a in RATINGS and b in RATINGS]
    if not pairs:
        return None, None
    return (sum(a == b for a, b in pairs) / len(pairs), sum(abs(a - b) <= 1 for a, b in pairs) / len(pairs))


def direction(before, after):
    """-1 worse, 0 same, 1 better (a lower index is stronger); None if either is not on the scale."""
    if before not in RATINGS or after not in RATINGS:
        return None
    d = RATINGS.index(before) - RATINGS.index(after)
    return (d > 0) - (d < 0)


def body_fat_hit(rng, measured):
    """(inside the range?, midpoint error in points) or None."""
    if rng is None or measured is None:
        return None
    lo, hi = sorted(rng)
    return lo <= measured <= hi, abs((lo + hi) / 2 - measured)


def score(runs, reference, measured, dates):
    """{model: metrics} from run rows ({model, date, repeat, ratings, body_fat, cost, seconds}); None ratings = failed."""
    out = {}
    for model in sorted({r["model"] for r in runs}):
        mine = [r for r in runs if r["model"] == model]
        ok = [r for r in mine if r["ratings"] is not None]
        vs_ref = [(r["ratings"].get(g), reference[(r["date"], g)]) for r in ok for g in GROUPS
                  if (r["date"], g) in reference]
        repeat_pairs = []
        for _, rs in itertools.groupby(sorted(ok, key=lambda r: (r["date"], r["repeat"])), key=lambda r: r["date"]):
            for a, b in itertools.combinations(list(rs), 2):
                repeat_pairs += [(a["ratings"].get(g), b["ratings"].get(g)) for g in GROUPS]
        change = []
        for d1, d2 in zip(dates, dates[1:]):
            first = [r for r in ok if r["date"] == d1]
            second = [r for r in ok if r["date"] == d2]
            for g in GROUPS:
                want = direction(reference.get((d1, g)), reference.get((d2, g)))
                if want is None or not first or not second:
                    continue
                got = direction(first[0]["ratings"].get(g), second[0]["ratings"].get(g))
                change.append(got == want)
        bf = [body_fat_hit(r["body_fat"], measured.get(r["date"])) for r in ok]
        bf = [x for x in bf if x]
        all_tiers = [t for r in ok for t in r["ratings"].values()]
        exact, within = agreement(vs_ref)
        rep_exact, _ = agreement(repeat_pairs)
        out[model] = {
            "answers": f"{len(ok)}/{len(mine)}",
            "exact": exact, "within_one": within, "kappa": kappa_qw(vs_ref),
            "repeat_exact": rep_exact, "repeat_kappa": kappa_qw(repeat_pairs),
            "not_visible": (all_tiers.count(NOT_VISIBLE) / len(all_tiers)) if all_tiers else None,
            "change_right": (sum(change) / len(change)) if change else None,
            "body_fat_inside": (sum(x[0] for x in bf) / len(bf)) if bf else None,
            "body_fat_error": (sum(x[1] for x in bf) / len(bf)) if bf else None,
            "cost_per_set": sum(r["cost"] for r in mine) / len(mine) if mine else 0.0,
            "seconds_per_set": sum(r["seconds"] for r in mine) / len(mine) if mine else 0.0,
        }
    return out


def recommend(scores):
    """The cheapest model whose kappa is within 0.1 of the best and whose repeats agree at least 0.8 of the time."""
    rated = {m: s for m, s in scores.items() if s["kappa"] is not None}
    if not rated:
        return "No reference rating yet: fill in bench/reference.csv to get a recommendation."
    best = max(s["kappa"] for s in rated.values())
    if best < 0.4:
        return f"No model is reliable enough: the best kappa against your rating is {best:.2f} (below 0.40)."
    fit = [m for m, s in rated.items() if s["kappa"] >= best - 0.1 and (s["repeat_exact"] or 0) >= 0.8]
    if not fit:
        return "No model is both close to the best and consistent between repeats (repeat agreement 0.80 or more)."
    pick = min(fit, key=lambda m: rated[m]["cost_per_set"])
    return f"Use {pick}: kappa {rated[pick]['kappa']:.2f}, the cheapest within 0.10 of the best ({best:.2f})."


# ---------------------------------------------------------------- report
def fmt(v, pct=False):
    if v is None:
        return "–"
    return f"{v * 100:.0f} %" if pct else (f"{v:.2f}" if isinstance(v, float) else str(v))


def report(scores, dates):
    lines = ["# Photo rating benchmark", "", f"Photo sets: {', '.join(dates)}.", "",
             "| Model | Answers | Exact | Within 1 | Kappa | Repeat exact | Repeat kappa | Not visible | Change right |"
             " Body fat inside | Body fat error | Cost / set | Time / set |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m, s in scores.items():
        lines.append(f"| {m} | {s['answers']} | {fmt(s['exact'], True)} | {fmt(s['within_one'], True)} | "
                     f"{fmt(s['kappa'])} | {fmt(s['repeat_exact'], True)} | {fmt(s['repeat_kappa'])} | "
                     f"{fmt(s['not_visible'], True)} | {fmt(s['change_right'], True)} | "
                     f"{fmt(s['body_fat_inside'], True)} | {fmt(s['body_fat_error'])} | "
                     f"${s['cost_per_set']:.3f} | {s['seconds_per_set']:.0f} s |")
    lines += ["", recommend(scores), "",
              "Kappa is quadratic-weighted on the 4 tiers: 1 = full agreement, 0 = chance. Your rating is the "
              "reference; groups you left blank are not scored."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", required=True, help="the athlete folder")
    ap.add_argument("--models", default="haiku,sonnet,opus")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--dates", help="comma-separated photo dates; default all")
    ap.add_argument("--run", action="store_true", help="send the photos to the models (default: only list)")
    ap.add_argument("--claude", default="claude", help=argparse.SUPPRESS)  # tests pass a fake
    a = ap.parse_args(argv)
    folder = Path(a.dir).resolve()
    if not (folder / photo_guard.MARKER).is_file():
        print(f"{folder} is not an athlete folder (no coaich.md)", file=sys.stderr)
        return 1
    sets = photo_sets(folder, set(a.dates.split(",")) if a.dates else None)
    if not sets:
        print("no filed photo sets: file some first with the physique skill (photos.py file)", file=sys.stderr)
        return 1
    dates, models = sorted(sets), [m.strip() for m in a.models.split(",") if m.strip()]
    if write_reference_template(folder, dates):
        print("wrote bench/reference.csv: fill in your own tier per group before you look at any model's answer")
    calls = len(models) * len(dates) * a.repeats
    print(f"{len(dates)} photo set(s), {sum(map(len, sets.values()))} files, {len(models)} model(s) × "
          f"{a.repeats} repeat(s) = {calls} call(s)")
    if not a.run:
        for d in dates:
            print(f"  {d}: {', '.join(sets[d])}")
        print("dry run: nothing sent. Add --run to send these filed copies to your own Claude session.")
        return 0
    runs = []
    for model, d, rep in itertools.product(models, dates, range(1, a.repeats + 1)):
        answer, cost, secs = ask(model, d, sets[d], folder, a.claude)
        runs.append({"model": model, "date": d, "repeat": rep, "ratings": answer[0] if answer else None,
                     "body_fat": answer[1] if answer else None, "cost": cost, "seconds": secs})
        print(f"  {model} {d} #{rep}: {'ok' if answer else 'no valid answer'} (${cost:.3f}, {secs:.0f} s)")
    bench = folder / "bench"
    bench.mkdir(exist_ok=True)
    with open(bench / "runs.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(RUN_COLS)
        for r in runs:
            bf = r["body_fat"] or ("", "")
            for g in (GROUPS if r["ratings"] else [""]):
                w.writerow([r["model"], r["date"], r["repeat"], int(r["ratings"] is not None), g,
                            (r["ratings"] or {}).get(g, ""), bf[0], bf[1], r["cost"], r["seconds"]])
    text = report(score(runs, read_reference(folder), measured_body_fat(folder), dates), dates)
    (bench / "report.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
