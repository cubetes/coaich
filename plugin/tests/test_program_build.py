"""program_build.py and program_audit.py: grid coverage, time budget, gates, low back, the folder I/O. Synthetic data."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import program_audit as pa  # noqa: E402
import program_build as pb  # noqa: E402

LEVEL_ANSWERS = {
    "beginner": {"history": "under_6_months"},
    "intermediate": {"history": "6_months_to_2_years", "last_trained": "last_3_months"},
    "advanced": {"history": "over_2_years", "last_trained": "last_3_months", "known_loads": True},
}


def read(*path):
    with open(os.path.join(*path), encoding="utf-8") as f:
        return f.read()


def answers(level, days, minutes, **kw):
    a = {"acknowledged": True, "age": "adult", "health": set(), "injuries": [], "days": days, "minutes": minutes,
         **LEVEL_ANSWERS[level]}
    a.update(kw)
    return a


def program(a, week=9):
    r = pb.decide(a, week)
    assert r["outcome"] == "program", r
    return r["program"]


CELLS = [answers(l, d, m) for l in pb.LEVELS for d in range(2, 7) for m in (30, 45, 60, 75)]
MODIFIERS = [{}, {"goal": "strength"}, {"goal": "muscle"}, {"age": "16_17"}, {"age": "60_plus", "chair_stand": False},
             {"age": "60_plus", "chair_stand": True}, {"health": {"urine_leak"}}, {"bench_safeties": True},
             {"goal": "strength", "priority": "back"}] + [{"priority": r} for r in pb.REGIONS]
PAIN_SETS = [[{"area": a, "red_flag": rf, "checked": ck}] for a in pb.AREAS
             for rf, ck in ((False, False), (True, False), (True, True))] + \
            [[{"area": pb.AREAS[i], "red_flag": False, "checked": False},
              {"area": pb.AREAS[j], "red_flag": j % 2 == 0, "checked": False}]
             for i in range(len(pb.AREAS)) for j in range(i + 1, len(pb.AREAS))]


def grid():
    for cell in CELLS:
        for mod in MODIFIERS:
            for week in (1, 5, 9):
                yield {**cell, **mod}, week


class Grid(unittest.TestCase):
    def test_no_answer_combination_is_a_gap(self):
        n = 0
        for h in pb.HISTORY:
            for last in [None] + pb.LAST_TRAINED:
                for known in (False, True):
                    for age in pb.AGES:
                        for d in range(1, 8):
                            for m in (20, 30, 45, 60, 75, 90):
                                a = {"acknowledged": True, "age": age, "history": h, "last_trained": last,
                                     "known_loads": known, "days": d, "minutes": m, "chair_stand": False}
                                r = pb.decide(a)
                                n += 1
                                if age == "under_16":
                                    self.assertEqual(r["outcome"], "under_age")
                                    continue
                                p = r["program"]
                                self.assertTrue(p["routines"] and all(x["exercises"] for x in p["routines"]))
                                for x in p["routines"]:
                                    self.assertLessEqual(pa.routine_minutes(x["exercises"]), min(max(m, 30), 75))
        self.assertEqual(n, 3 * 4 * 2 * 4 * 7 * 6)

    def test_the_60_cells_reach_all_8_layouts(self):
        self.assertEqual(len(CELLS), 60)
        self.assertEqual({program(c)["layout"] for c in CELLS}, {"fb2b", "fb3b", "ul4b", "fb2i", "fb3i", "ul4i",
                                                                  "ulf5i", "ppl6i"})
        self.assertEqual(program(answers("beginner", 6, 60))["layout"], "ul4b")  # beginners capped at 4 days
        self.assertEqual(program(answers("intermediate", 6, 60, age="60_plus"))["layout"], "ul4i")

    def test_time_budget_holds_for_every_output(self):
        for a, week in grid():
            for r in program(a, week)["routines"]:
                self.assertLessEqual(pa.routine_minutes(r["exercises"]), a["minutes"], (a, week, r["title"]))
        # Worked examples of the formula (8 + 3.25 per compound set + 2 per isolation or paired set).
        self.assertEqual([pa.routine_minutes(r["exercises"]) for r in program(answers("beginner", 3, 60))["routines"]],
                         [51.75, 54.25])
        self.assertEqual([pa.routine_minutes(r["exercises"]) for r in program(answers("beginner", 3, 30))["routines"]],
                         [28, 28])

    def test_every_program_passes_the_gates_or_misses_only_a_known_miss(self):
        for a, week in grid():
            p = program(a, week)
            self.assertEqual(pa.unexpected_failures(p), [], (pa.program_name(p), week))
        for cell in CELLS:
            for pain in PAIN_SETS:
                p = program({**cell, "injuries": pain})
                self.assertEqual(pa.unexpected_failures(p), [], (pa.program_name(p), pain))

    def test_every_exact_known_miss_is_still_a_miss(self):
        seen = set()
        for cell in CELLS:
            p = program(cell)
            for c in pa.audit(p):
                if c["gate"] in (1, 2, 3):
                    seen |= {(pa.program_name(p), c["gate"], m, round(v, 2)) for m, v in c["misses"]}
        exact = {(prog, g, m, v) for prog, g, m, v, _ in pa.KNOWN_MISSES if prog.split("·")[1].isdigit()}
        self.assertEqual(seen, exact)


class Gates(unittest.TestCase):
    def setUp(self):
        self.base = program(answers("intermediate", 4, 60))
        self.assertEqual(pa.unexpected_failures(self.base), [])

    def failing(self, change, p=None):
        p = copy.deepcopy(p or self.base)
        change(p)
        return [c["gate"] for c in pa.audit(p) if not c["passed"]]

    def test_the_audit_catches_a_program_that_breaks_the_rules(self):
        def no_chest(p):
            for r in p["routines"]:
                r["exercises"] = [s for s in r["exercises"] if s["pattern"] not in ("HP", "FL")]
        self.assertIn(1, self.failing(no_chest))

        def calves_20(p):
            for s in (s for r in p["routines"] for s in r["exercises"] if s["pattern"] == "CA"):
                s["sets"] = 20
        self.assertIn(2, self.failing(calves_20))
        self.assertIn(3, self.failing(lambda p: p["routines"][2].__setitem__(
            "exercises", [s for s in p["routines"][2]["exercises"] if s["pattern"] not in ("HP", "FL")])))

        def long_day(p):
            p["routines"][0]["exercises"][1]["sets"], p["routines"][0]["exercises"][0]["sets"] = 4, 6
        self.assertIn(4, self.failing(long_day))
        self.assertEqual(self.failing(lambda p: p["routines"][1]["exercises"][0].__setitem__("rir", [0, 2])), [5])
        self.assertEqual(self.failing(lambda p: p["routines"][0]["exercises"][1].__setitem__("sets", 5)), [4, 8])
        self.assertEqual(self.failing(lambda p: p["routines"][0]["exercises"][1].__setitem__(
            "exercise_id", p["routines"][0]["exercises"][0]["exercise_id"])), [7])
        self.assertEqual(self.failing(lambda p: p["routines"][0]["exercises"][0].__setitem__(
            "alternatives", ["Not_An_Exercise"])), [7])
        low_back = program(answers("intermediate", 4, 60, injuries=[{"area": "low_back"}]))
        self.assertEqual(self.failing(lambda p: p["routines"][1]["exercises"][0].__setitem__(
            "exercise_id", "Leg_Press"), low_back), [6])

    def test_g9_warns_and_never_fails(self):
        p = program(answers("intermediate", 2, 75))
        g9 = pa.audit(p)[8]
        self.assertTrue(g9["warn_only"] and not g9["passed"])
        self.assertEqual(pa.unexpected_failures(p), [])

    def test_a_hand_written_program_is_audited_with_inferred_slots(self):
        own = {"level": "intermediate", "days": 2, "minutes": 60, "routines": [
            {"title": "Day A", "exercises": [
                {"exercise_id": "Barbell_Squat", "sets": 3, "rep_range": [5, 5]},
                {"exercise_id": "Triceps_Pushdown", "sets": 3, "rep_range": [10, 15]}]},
            {"title": "Day B", "exercises": [{"exercise_id": "Barbell_Deadlift", "sets": 1, "rep_range": [5, 5]}]}]}
        p = pa.normalise(own)
        self.assertEqual(p["routines"][0]["exercises"][1]["pattern"], "TE")
        report = pa.report(p)
        self.assertIn("FAILS", report)
        self.assertIn("G1: chest 0", report)
        self.assertIn("| G9 | Overhead triceps preferred | note |", report)


class Pain(unittest.TestCase):
    def test_low_back_never_gets_spine_loading(self):
        n = 0
        for cell in CELLS:
            for back in ({"area": "low_back"}, {"area": "low_back", "red_flag": True},
                         {"area": "low_back", "red_flag": True, "checked": True}):
                for other in (None, {"area": "knee"}, {"area": "hip", "red_flag": True}, {"area": "shoulder"}):
                    for mod in ({}, {"goal": "strength", "priority": "quads"}, {"age": "60_plus", "chair_stand": False}):
                        p = program({**cell, **mod, "injuries": [back] + ([other] if other else [])})
                        every = [x for r in p["routines"] for s in r["exercises"]
                                 for x in [s["exercise_id"]] + s["alternatives"]]
                        self.assertFalse(set(every) & pa.SPINE, pa.program_name(p))
                        self.assertTrue(pa.audit(p)[5]["passed"])
                        n += 1
        self.assertEqual(n, 60 * 3 * 4 * 3)

    def test_a_red_flag_leaves_out_the_area_until_checked(self):
        for area in [a for a in pb.AREAS if a != "other"]:
            red = pb.decide(answers("intermediate", 4, 75, injuries=[{"area": area, "red_flag": True}]))
            slots = [s for r in red["program"]["routines"] for s in r["exercises"]]
            self.assertFalse([s for s in slots if s["pattern"] in pa.AREA_PATTERNS[area]], area)
            self.assertTrue(any("physiotherapist or doctor" in w for w in red["warnings"]))
            ok = program(answers("intermediate", 4, 75, injuries=[{"area": area, "red_flag": True, "checked": True}]))
            self.assertTrue([s for r in ok["routines"] for s in r["exercises"] if s["pattern"] in pa.AREA_PATTERNS[area]])


PROFILE = """---
profile: 0.1
updated: 2030-01-06
age_band: 18-59
health_items: [joint]
pain:
  - area: knee
    red_flag: false
    checked:
history: over-2y          # only periods of 2+ sessions a week
last_trained: last-3m
known_loads: []
days_per_week: 4
minutes_per_session: 60
goal: strength
priority: none
---
# Profile
"""
SETTINGS = """---
coaich: 0.1
safety_acknowledged: 2030-01-06
safety_clearance_sentence:
---
"""


class Folder(unittest.TestCase):
    def folder(self, profile=PROFILE, settings=SETTINGS, current=None):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        for name, text in (("profile.md", profile), ("coaich.md", settings)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(text)
        if current:
            os.makedirs(os.path.join(d, "plan"))
            with open(os.path.join(d, "plan", "CURRENT.md"), "w", encoding="utf-8") as f:
                f.write(current)
        return d

    def run_build(self, d, *args):
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = pb.main(["--dir", d, "--today", "2030-01-07", *args])
        return code, err.getvalue()

    def test_the_yaml_header_parser(self):
        h = pb.front_matter(PROFILE)
        self.assertEqual(h["pain"], [{"area": "knee", "red_flag": False, "checked": None}])
        self.assertEqual(h["health_items"], ["joint"])
        self.assertEqual(h["history"], "over-2y")
        self.assertEqual(pb.front_matter("---\nknown_loads: [{exercise: squat, kg: 80, reps: 8}]\n---\n")["known_loads"],
                         [{"exercise": "squat", "kg": 80, "reps": 8}])

    def test_profile_keys_map_to_the_tree(self):
        a = pb.read_answers(self.folder())
        self.assertEqual((a["age"], a["history"], a["last_trained"], a["days"], a["minutes"], a["goal"], a["priority"]),
                         ("adult", "over_2_years", "last_3_months", 4, 60, "strength", None))
        self.assertEqual(a["health"], {"bone_or_joint_problem"})
        self.assertEqual(a["injuries"], [{"area": "knee", "red_flag": False, "checked": False}])
        self.assertFalse(a["known_loads"])

    def test_writes_program_current_and_log_and_is_safe_to_rerun(self):
        d = self.folder(current="# What is in force today\n\n- **Nutrition:** kept as is.\n")
        self.assertEqual(self.run_build(d)[0], 0)
        self.assertEqual(self.run_build(d)[0], 0)
        doc = json.loads(read(d, "plan", "program.json"))
        self.assertEqual(doc["name"], "ul4i·60·strength·pain")
        self.assertEqual(doc["easy_weeks"][:3], [7, 14, 21])
        first = doc["routines"][0]["exercises"][0]
        self.assertEqual((first["tool"], first["load_step_kg"], first["category"], first["reps_left"]),
                         ("barbell_upper", 2.5, "compound", [2, 2]))
        self.assertEqual(doc["start"], "2030-01-07")
        self.assertNotIn("Barbell_Squat", [s["exercise_id"] for r in doc["routines"] for s in r["exercises"]])  # knee
        current = read(d, "plan", "CURRENT.md")
        self.assertEqual(current.count("<!-- coaich:program -->"), 1)
        self.assertIn("- **Nutrition:** kept as is.", current)
        self.assertIn("(knee pain)", current)
        self.assertIn(pb.DISCLAIMER, current)
        log = read(d, "log.md")
        self.assertEqual(log.count("· program-build · ul4i·60·strength·pain"), 2)

    def test_the_template_placeholder_is_replaced_by_the_program(self):
        template = os.path.join(os.path.dirname(__file__), "..", "templates", "athlete", "plan", "CURRENT.md")
        with open(template, encoding="utf-8") as f:
            d = self.folder(current=f.read())
        self.assertEqual(self.run_build(d)[0], 0)
        current = read(d, "plan", "CURRENT.md")
        self.assertNotIn("none yet", current)
        self.assertEqual(current.count("<!-- coaich:program -->"), 1)

    def test_the_medical_gate_stops_and_writes_nothing(self):
        stops = [
            (PROFILE, SETTINGS.replace("safety_acknowledged: 2030-01-06", "safety_acknowledged:"), "needs_acknowledgement"),
            (PROFILE.replace("age_band: 18-59", "age_band: under-16"), SETTINGS, "under_age"),
            (PROFILE.replace("[joint]", "[joint, heart]"), SETTINGS, "needs_clearance"),
            (PROFILE.replace("[joint]", "[heart, surgery]"), SETTINGS.replace(
                "safety_clearance_sentence:", "safety_clearance_sentence: my doctor said it's fine"), "needs_clearance"),
        ]
        for profile, settings, why in stops:
            d = self.folder(profile, settings)
            code, err = self.run_build(d)
            self.assertEqual(code, 2, why)
            self.assertIn(why, err)
            self.assertFalse(os.path.exists(os.path.join(d, "plan", "program.json")))
        # One clearance lifts every stop item answered in the onboarding (as in the app); Spanish too.
        for sentence in ("I confirm a doctor has cleared me to do strength training.",
                         "Confirmo que un médico me ha autorizado a entrenar fuerza."):
            cleared = SETTINGS.replace("safety_clearance_sentence:", f"safety_clearance_sentence: {sentence}")
            self.assertEqual(self.run_build(self.folder(PROFILE.replace("[joint]", "[heart, surgery]"), cleared))[0], 0)

    def test_diabetes_is_not_a_health_item(self):
        code, err = self.run_build(self.folder(PROFILE.replace("[joint]", "[diabetes]")))
        self.assertEqual(code, 2)
        self.assertIn("'health_items: diabetes' is not one of", err)

    def test_place_prints_the_placement_only(self):
        d = self.folder()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(pb.main(["--dir", d, "--place"]), 0)
        pl = json.loads(out.getvalue())
        self.assertEqual((pl["level"], pl["advanced_check_week"], pl["row"]), ("intermediate", 6, 6))
        self.assertTrue(pl["line"].startswith("We've put you in Intermediate"))
        self.assertEqual(sorted(os.listdir(d)), ["coaich.md", "profile.md"])  # nothing written

    def test_bad_answers_stop_with_the_key_named(self):
        code, err = self.run_build(self.folder(PROFILE.replace("history: over-2y", "history: lots")))
        self.assertEqual(code, 2)
        self.assertIn("'history: lots'", err)


if __name__ == "__main__":
    unittest.main()
