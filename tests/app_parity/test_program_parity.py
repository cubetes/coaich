"""Parity with the Release 1 Swift core: every answer cell gives the same program.

swift_parity.json.gz (kept outside plugin/: the directory scan refuses binary files) was exported from AthleteCore (Onboarding.decide + StarterProgram.audit) by a temporary
test in the r1-core worktree (commit d7b7ea0; no source change): 60 cells × 16 modifiers × weeks 1/5/9, every cell
with 33 pain sets, the low-back grid, the 4032-answer gap grid and the medical gates. Routine titles are Spanish
there; slot keys are compared by their exercise half.
"""
import gzip
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "plugin", "scripts"))
import program_audit as pa  # noqa: E402
import program_build as pb  # noqa: E402

AGE = {"under16": "under_16", "sixteenSeventeen": "16_17", "adult": "adult", "sixtyPlus": "60_plus"}
HISTORY = {"underSixMonths": "under_6_months", "sixMonthsToTwoYears": "6_months_to_2_years", "overTwoYears": "over_2_years"}
LAST = {"lastThreeMonths": "last_3_months", "threeToTwelveMonths": "3_to_12_months", "overAYear": "over_a_year"}
OUTCOME = {"needsAcknowledgement": "needs_acknowledgement", "underAge": "under_age", "needsClearance": "needs_clearance",
           "program": "program"}
TITLES = {"Cuerpo completo A": {"Full body A"}, "Cuerpo completo B": {"Full body B"}, "Torso A": {"Upper A"},
          "Torso B": {"Upper B"}, "Pierna A": {"Lower A", "Legs A"}, "Pierna B": {"Lower B", "Legs B"},
          "Día 1": {"Day 1"}, "Día 2": {"Day 2"}, "Día 3": {"Day 3"}, "Cuerpo completo": {"Full body"},
          "Empuje A": {"Push A"}, "Empuje B": {"Push B"}, "Tirón A": {"Pull A"}, "Tirón B": {"Pull B"},
          "Prioridad": {"Priority"}}


def snake(s):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def answers(i):
    return {"acknowledged": i["acknowledged"], "age": AGE[i["age"]], "health": {snake(h) for h in i["health"]},
            "clearance": i.get("clearance"), "history": HISTORY[i["history"]],
            "last_trained": LAST.get(i.get("last_trained")), "known_loads": i.get("known_loads", False),
            "days": i["days"], "minutes": i["minutes"], "chair_stand": i.get("chair_stand"), "goal": i.get("goal"),
            "priority": snake(i["priority"]) if i.get("priority") else None, "bench_safeties": i["bench_safeties"],
            "injuries": [{"area": snake(x["area"]), "red_flag": x["red_flag"], "checked": x["checked"]}
                         for x in i["injuries"]]}


def swift_text(s):
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)  # es_ES decimals
    return re.sub(r"\b(lowBack|elbowWrist|glutesHamstrings)\b", lambda m: snake(m.group(1)), s)


def mine(case):
    r = pb.decide(answers(case["input"]), case["input"]["week"])
    if r["outcome"] != "program":
        return {"outcome": r["outcome"], **({"items": r["items"]} if "items" in r else {})}
    p = r["program"]
    checks = pa.audit(p)
    _, groups, sessions = pa.volume(p)
    return {
        "outcome": "program", "name": pa.program_name(p),
        "minutes_per_routine": [pa.routine_minutes(x["exercises"]) for x in p["routines"]],
        "layout": p["layout"], "level": p["level"], "days": p["days"], "variant": p["variant"], "goal": p["goal"],
        "titles": [x["title"] for x in p["routines"]],
        "slots": [[[s["key"].split("/", 1)[1], s["pattern"], s["exercise_id"], s["sets"], s["rep_range"], s["rir"],
                    s["rest_seconds"], s["alternatives"], s["warmup"], s["pair"], s["main"], s["top_set"]]
                   for s in x["exercises"]] for x in p["routines"]],
        "left_out": p["left_out"], "notes": r["notes"], "warnings": r["warnings"], "fired": r["fired"],
        "placement": r["placement"],
        "audit": [[c["gate"], c["passed"], c["warn_only"], [[m, round(v, 6)] for m, v in c["misses"]]] for c in checks],
        "unexpected": pa.unexpected_failures(p, checks),
        "groups": {k: round(v, 6) for k, v in groups.items()}, "sessions": {k: round(v, 6) for k, v in sessions.items()},
        "easy_week_every": pb.EASY_WEEK_EVERY[p["level"]],
        "easy_weeks": [n for n in range(p["days"] * 14) if pb.is_easy_week(p, n)],
    }


def strength_rir(o, s):
    """Since 0.6 the plugin's strength-goal main lifts aim at 2-3 reps left; the Swift core still has 1-2 / 2-2."""
    if o["goal"] == "strength" and o["level"] != "beginner" and s[10] and s[5] in ([1, 2], [2, 2]):
        return [2, 3]
    return s[5]


def theirs(o):
    if o["outcome"] != "program":
        return {"outcome": OUTCOME[o["outcome"]], **({"items": [snake(x) for x in o["items"]]} if "items" in o else {})}
    if "routines" not in o:
        return {"outcome": "program", "name": swift_text(o["name"]), "minutes_per_routine": o["minutes_per_routine"]}
    return {
        "outcome": "program", "name": swift_text(o["name"]), "minutes_per_routine": o["minutes_per_routine"],
        "layout": o["layout"], "level": o["level"], "days": o["days"], "variant": o["variant"], "goal": o["goal"],
        "titles": [x["title"] for x in o["routines"]],
        "slots": [[[s[0].split("/", 1)[1]] + s[1:5] + [strength_rir(o, s)] + s[6:] for s in x["slots"]]
                  for x in o["routines"]],
        "left_out": o["left_out"], "notes": o["notes"], "warnings": [swift_text(w) for w in o["warnings"]],
        "fired": [swift_text(f) for f in o["fired"]], "placement": o["placement"],
        # G2 is a note in the plugin since 0.6 (no study supports a volume cap); the Swift core still gates it
        "audit": [[g, ok, w or g == 2, [[m, round(v, 6)] for m, v in miss]] for g, ok, w, miss in o["audit"]],
        "unexpected": [swift_text(u) for u in o["unexpected"]],
        "groups": {k: round(v, 6) for k, v in o["groups"].items()},
        "sessions": {k: round(v, 6) for k, v in o["sessions"].items()},
        "easy_week_every": o["easy_week_every"], "easy_weeks": o["easy_weeks"],
    }


def load():
    with gzip.open(os.path.join(HERE, "swift_parity.json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


class SwiftParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load()

    def test_fixture_covers_the_full_grid(self):
        groups = {}
        for c in self.doc["cases"]:
            groups[c["group"]] = groups.get(c["group"], 0) + 1
        self.assertEqual(groups, {"grid": 60 * 16 * 3, "injured": 60 * 33, "low_back": 60 * 3 * 4 * 3,
                                  "gap": 3 * 4 * 2 * 4 * 7 * 6, "gate": 34})

    def test_same_rule_tables(self):
        self.assertEqual(sorted(pa.SPINE), self.doc["spine"])
        self.assertEqual([(p, g, m, v) for p, g, m, v, _ in pa.KNOWN_MISSES],
                         [(k["program"], k["gate"], k["muscle"], k["value"]) for k in self.doc["known_misses"]])

    def test_every_case_gives_the_same_program(self):
        diffs = []
        for c in self.doc["cases"]:
            want = theirs(c["output"])
            got = mine(c)
            if "layout" not in want:
                got = {k: got[k] for k in want if k in got}
            if "titles" in want:
                bad = [t for t, e in zip(want["titles"], got["titles"]) if e not in TITLES[t]]
                if bad or len(want["titles"]) != len(got["titles"]):
                    diffs.append((c["input"], "titles", want["titles"], got["titles"]))
                want.pop("titles"), got.pop("titles")
            for k in want:
                if want[k] != got.get(k):
                    diffs.append((c["input"], k, want[k], got.get(k)))
        self.assertEqual(diffs[:3], [], f"{len(diffs)} differences")


if __name__ == "__main__":
    unittest.main()
