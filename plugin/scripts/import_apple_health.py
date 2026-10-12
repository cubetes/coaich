#!/usr/bin/env python3
"""Import Apple Health data exported by the Health Auto Export app (JSON, export version 2) into the
athlete folder: data/health.csv (one row per date + metric) and body weight / waist / body fat in
data/body.csv.

    python3 import_apple_health.py --dir <athlete folder> <export.json> [<export.json> ...]

Input shape (Health Auto Export JSON): {"data": {"metrics": [{"name", "units", "data": [{"date":
"yyyy-MM-dd HH:mm:ss Z", "qty": n}, ...]}, ...]}}. Sleep comes from `sleep_analysis` with "Aggregate"
on (one entry per night, `totalSleep` in hours). Samples are summed (steps, energy) or averaged per day
inside one file. Overlapping exports are normal: across files and against what is stored, the newest
value REPLACES the old one per (date, metric) and is never added to it, so steps cannot double. Give
files oldest first; the last one wins. Values outside the trust-layer bounds are dropped and listed.
Exports are copied to data/raw/apple-health/.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402
import import_common as ic  # noqa: E402

KJ_PER_KCAL = 4.184
# HAE metric -> (our metric, per-day aggregation, unit)
METRICS = {
    "step_count": ("steps", "sum", "count"),
    "heart_rate_variability": ("hrv_ms", "mean", "ms"),
    "resting_heart_rate": ("resting_hr_bpm", "mean", "bpm"),
    "active_energy": ("active_kcal", "sum", "kcal"),
    "vo2_max": ("vo2max", "last", "mL/kg/min"),
    "weight_body_mass": ("weight_kg", "mean", "kg"),
    "body_fat_percentage": ("body_fat_pct", "mean", "%"),
    "waist_circumference": ("waist_cm", "last", "cm"),
    "sleep_analysis": ("sleep_h", "last", "h"),
}
METRICS_BY_METRIC = {v[0]: v for v in METRICS.values()}
BODY_ONLY = {"body_fat_pct", "waist_cm"}  # these go to body.csv, not health.csv (contract metric list)
# Physiologically impossible daily values are dropped (references: trust tiers in the import skill).
BOUNDS = {"steps": (0, 60000), "hrv_ms": (5, 250), "resting_hr_bpm": (30, 120), "sleep_h": (1, 14),
          "vo2max": (10, 90), "weight_kg": (30, 250), "body_fat_pct": (3, 60), "active_kcal": (0, 10000),
          "waist_cm": (40, 200)}


def to_unit(metric, value, units):
    """Convert one sample into our unit from the export's `units` string."""
    u = (units or "").lower()
    if metric == "active_kcal" and u == "kj":
        return value / KJ_PER_KCAL
    if metric == "weight_kg" and u in ("lb", "lbs"):
        return value * ic.LB_TO_KG
    if metric == "waist_cm" and u in ("in", "inch", "inches"):
        return value * 2.54
    if metric == "sleep_h" and u == "min":
        return value / 60
    if metric == "body_fat_pct" and value <= 1:  # some exports give a fraction
        return value * 100
    return value


def parse_file(path):
    """{(date, metric): value} for one export, plus a count of sleep entries without totalSleep."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    try:
        metrics = doc["data"]["metrics"]
    except (KeyError, TypeError):
        sys.exit(f"{path}: not a Health Auto Export JSON file (no data.metrics).")
    samples, skipped = defaultdict(list), 0
    for m in metrics:
        spec = METRICS.get(m.get("name"))
        if not spec:
            continue
        metric = spec[0]
        for e in m.get("data") or []:
            q = e.get("totalSleep", e.get("asleep")) if metric == "sleep_h" else e.get("qty")
            day = (e.get("date") or "")[:10]
            if ic.num(q) is None or len(day) != 10:
                skipped += metric == "sleep_h"
                continue
            samples[(day, metric)].append(to_unit(metric, ic.num(q), m.get("units")))
    agg = {"sum": sum, "mean": lambda v: sum(v) / len(v), "last": lambda v: v[-1]}
    out = {k: agg[METRICS_BY_METRIC[k[1]][1]](v) for k, v in samples.items()}
    return out, skipped



def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exports", nargs="+", help="Health Auto Export JSON files, oldest first")
    ap.add_argument("--dir", default=".", help="athlete folder (default: current directory)")
    args = ap.parse_args()
    folder = ic.athlete_dir(args.dir)

    values, skipped_sleep = {}, 0
    for p in args.exports:
        vals, sk = parse_file(p)
        values.update(vals)  # later file replaces earlier per (date, metric), never adds
        skipped_sleep += sk
    dropped = []
    for (day, metric), v in list(values.items()):
        lo, hi = BOUNDS[metric]
        if not lo <= v <= hi:
            dropped.append(f"{day} {metric} = {round(v, 1)}")
            del values[(day, metric)]
    for p in args.exports:
        ic.keep_raw(folder, p, "apple-health")

    af.upsert_rows(folder, "data/health.csv", [
        {"date": day, "metric": metric, "value": ic.fmt(v, 2), "unit": METRICS_BY_METRIC[metric][2],
         "source": "apple-health"}
        for (day, metric), v in sorted(values.items()) if metric not in BODY_ONLY])

    # body.csv is keyed by date + source: Apple Health fills its own row, rows from other sources stay as they are.
    body = {r["date"]: r for r in af.read_rows(folder, "data/body.csv") if r["source"] == "apple-health"}
    changed = set()
    for (day, metric), v in values.items():
        if metric in ("weight_kg", "waist_cm", "body_fat_pct"):
            row = body.setdefault(day, {"date": day, "weight_kg": "", "waist_cm": "", "body_fat_pct": "",
                                        "source": "apple-health"})
            row[metric] = ic.fmt(v, 2)
            changed.add(day)
    af.upsert_rows(folder, "data/body.csv", [body[d] for d in sorted(changed)])

    days = sorted({d for d, _ in values})
    weights = [(d, ic.num(r["weight_kg"])) for d, r in sorted(body.items()) if ic.num(r["weight_kg"])]
    jumps = [f"{b[0]}: {a[1]:.1f} -> {b[1]:.1f} kg" for a, b in zip(weights, weights[1:])
             if abs(b[1] - a[1]) > 3]
    span = f"{days[0]} to {days[-1]}" if days else "no days"
    summary = (f"apple-health: {len(days)} days ({span}), {len(values)} values, "
               f"{len(dropped)} out-of-range dropped")
    af.append_log(folder, "import", f"apple-health: {len(days)} days through {days[-1] if days else 'none'}")
    print(summary)
    for d in dropped:
        print("  dropped:", d)
    for j in jumps:
        print("  check weight (moved more than 3 kg in a day, scale or water?):", j)
    if skipped_sleep:
        print(f"  {skipped_sleep} sleep entries had no totalSleep: export with 'Aggregate data' on.")


if __name__ == "__main__":
    main()
