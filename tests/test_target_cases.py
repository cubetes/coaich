#!/usr/bin/env python3
"""The shared target cases (fixtures/target_cases.json): same inputs, same next targets, in any engine.

Each case is one exercise in one routine ("Day A"), the sets logged week by week, and for each proposed week the
expected grade of the week before, decision, reason code, next sets and whether it needs the athlete's OK. Inputs
use the athlete-folder format 1 (plan/program.json, data/sets.csv, plan/CURRENT.md). The plugin is the reference
(ADR 0006); an app engine passes when it gives the same answers.

Run:   python3 -m unittest discover -s tests
Fill:  python3 tests/test_target_cases.py --write   (only after a deliberate rule change; review the diff)
"""
import json
import os
import shutil
import sys
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_progression import Athlete, ex, lab, wk  # noqa: E402

CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "target_cases.json")
ROW = "day-a-1"


def calendar(types):
    rows = [f"| W{n} | {t} | {wk(int(n))} → x | planned |" for n, t in sorted(types.items(), key=lambda x: int(x[0]))]
    return "| Microcycle | Type | Dates | Status |\n|---|---|---|---|\n" + "\n".join(rows) + "\n"


def run(case):
    """Build the folder, propose each expected week in order (applying the one before, every row OK'd)."""
    e = case["exercise"]
    a = Athlete([{"title": "Day A", "exercises": [ex(e["exercise_id"], [tuple(s) for s in e["sets"]]
                                                     if isinstance(e["sets"], list) else [],
                                                     **{k: v for k, v in e.items() if k not in ("exercise_id", "sets")})]}],
                level=case.get("level", "intermediate"))
    if isinstance(e["sets"], int):
        a.program["routines"][0]["exercises"][0]["sets"] = e["sets"]
        a.save_program()
    if case.get("week_types"):
        a.current(calendar(case["week_types"]))
    for n, sets in case["sessions"].items():
        a.session(wk(int(n)), "Day A", [(e["exercise_id"], [tuple(s) for s in sets])])
    got, prev = {}, None
    try:
        for n in sorted(map(int, case["expect"])):
            if prev is not None:
                a.run("apply", "--week", lab(prev), "--accept-all", "--approve", ROW)
            a.write(wk(n - 1) + timedelta(days=6))
            a.propose(n)
            graded = next((r for r in a.targets(n - 1)["rows"] if r["id"] == ROW), None) \
                if os.path.exists(os.path.join(a.dir, "plan", "targets", f"targets_{lab(n - 1)}.json")) else None
            r = a.row(n, ROW)
            got[str(n)] = {"grade": graded and graded.get("grade"), "decision": r["decision"],
                           "code": r["reason"]["code"], "needs_ok": r["needs_approval"],
                           "sets": [[s["kg"], s["reps"]] for s in r["target_sets"]]}
            prev = n
    finally:
        shutil.rmtree(a.dir, ignore_errors=True)
    return got


def load():
    with open(CASES, encoding="utf-8") as f:
        return json.load(f)


class TargetCases(unittest.TestCase):
    def test_every_case_gives_the_expected_targets(self):
        for case in load()["cases"]:
            with self.subTest(case["id"]):
                self.assertEqual(run(case), case["expect"])

    def test_cases_cover_every_decision(self):
        decisions = {w["decision"] for c in load()["cases"] for w in c["expect"].values()}
        self.assertEqual(decisions, {"increase", "hold", "reduce", "easy_week", "swap"})


if __name__ == "__main__" and sys.argv[1:] == ["--write"]:
    doc = load()
    for c in doc["cases"]:
        c["expect"] = run(c)
    with open(CASES, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
elif __name__ == "__main__":
    unittest.main()
