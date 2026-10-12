#!/usr/bin/env python3
"""Tests for progression.py. Synthetic athlete folders in temp dirs, dates in 2030.

Run:  python3 -m unittest discover -s plugin/tests
"""
import contextlib
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import progression as pg  # noqa: E402

SET_COLS = ["date", "datetime", "session_id", "workout_name", "exercise", "exercise_id", "set_index",
            "set_type", "weight_kg", "reps", "rir", "rpe", "seconds", "distance_m", "source", "note"]
W10 = date.fromisocalendar(2030, 10, 1)

SQUAT, DEADLIFT, BENCH = "Barbell_Squat", "Barbell_Deadlift", "Barbell_Incline_Bench_Press_-_Medium_Grip"
RAISE, FACE_PULL, DIP, PUSHUP = "Side_Lateral_Raise", "Face_Pull", "Dips_-_Chest_Version", "Pushups"


def wk(n):
    """Monday of 2030-W(10+n)."""
    return W10 + timedelta(days=7 * n)


def lab(n):
    return pg.week_label(wk(n))


def ex(ex_id, sets, **kw):
    d = {"exercise_id": ex_id, "sets": [{"weight_kg": k, "reps": r} for k, r in sets]}
    d.update(kw)
    return d


def S(pairs, **kw):
    return [dict({"kg": k, "reps": r, "type": "normal"}, **kw) for k, r in pairs]


class Athlete:
    """A synthetic athlete folder: plan/program.json, data/sets.csv, log.md, optional CURRENT.md."""

    def __init__(self, routines, level="intermediate"):
        self.dir = tempfile.mkdtemp(prefix="coaich-test-")
        os.makedirs(os.path.join(self.dir, "plan"))
        os.makedirs(os.path.join(self.dir, "data"))
        with open(os.path.join(self.dir, "coaich.md"), "w") as fh:
            fh.write("language: en\nunits: kg\n")
        self.program = {"level": level, "routines": routines}
        self.save_program()
        self.rows = []

    def save_program(self):
        with open(os.path.join(self.dir, "plan", "program.json"), "w") as fh:
            json.dump(self.program, fh)

    def session(self, day, title, exercises):
        """exercises: [(exercise_id, [(kg, reps[, type[, rir[, note]]]), ...]), ...]"""
        sid = f"manual:{title}-{day}"
        for ex_id, sets in exercises:
            for i, s in enumerate(sets):
                self.rows.append({
                    "date": str(day), "datetime": f"{day}T10:00", "session_id": sid, "workout_name": title,
                    "exercise": ex_id.replace("_", " "), "exercise_id": ex_id, "set_index": i,
                    "set_type": s[2] if len(s) > 2 else "normal", "weight_kg": s[0], "reps": s[1],
                    "rir": s[3] if len(s) > 3 else "", "rpe": "", "seconds": "", "distance_m": "",
                    "source": "manual", "note": s[4] if len(s) > 4 else ""})
        return self

    def write(self, imported):
        with open(os.path.join(self.dir, "data", "sets.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=SET_COLS)
            w.writeheader()
            w.writerows(self.rows)
        with open(os.path.join(self.dir, "log.md"), "w") as fh:
            fh.write(f"# Log\n\n- {imported} · import · Strong CSV, 3 sessions\n")
        return self

    def current(self, text):
        with open(os.path.join(self.dir, "plan", "CURRENT.md"), "w") as fh:
            fh.write(text)

    def run(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pg.main(list(argv) + ["--dir", self.dir])
        return buf.getvalue()

    def propose(self, n, *extra):
        return self.run("propose", "--week", lab(n), *extra)

    def targets(self, n):
        with open(pg.targets_path(self.dir, lab(n))) as fh:
            return json.load(fh)

    def row(self, n, rid):
        return next(r for r in self.targets(n)["rows"] if r["id"] == rid)


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class Base(unittest.TestCase):
    def tearDown(self):
        for a in getattr(self, "_a", []):
            shutil.rmtree(a.dir, ignore_errors=True)

    def athlete(self, routines, **kw):
        a = Athlete(routines, **kw)
        self._a = getattr(self, "_a", []) + [a]
        return a

    def one(self, ex_id, sets, logged, *, title="Day A", rir_note=None, **kw):
        """One routine, one exercise, one logged week (W9), next week proposed (W10)."""
        a = self.athlete([{"title": title, "exercises": [ex(ex_id, sets, **kw)]}])
        a.session(wk(-1), title, [(ex_id, logged)]).write(wk(-1) + timedelta(days=6))
        a.propose(0)
        return a, a.row(0, f"{pg.slug(title)}-1")


# ------------------------------------------------------------------ ported engine behaviours
class TestRules(Base):
    def test_increase_at_top_of_range(self):
        a, r = self.one(RAISE, [(8, 15)] * 3, [(8, 15)] * 3, rep_range=[12, 15], load_step_kg=1.0,
                        category="isolation", tool="dumbbell")
        self.assertEqual(r["decision"], "increase")
        self.assertEqual(r["target_sets"], S([(9.0, 12)] * 3))
        self.assertFalse(r["needs_approval"])
        self.assertEqual(a.targets(-1)["rows"][0]["grade"], "hit")

    def test_hold_adds_one_rep(self):
        a, r = self.one(BENCH, [(60, 10)] * 3, [(60, 10)] * 3, rep_range=[8, 12], category="compound",
                        tool="barbell_upper")
        self.assertEqual(r["decision"], "hold")
        self.assertEqual([s["reps"] for s in r["target_sets"]], [11, 10, 10])
        self.assertEqual(r["reason"], {"code": "add_rep", "set": 1, "frm": 10, "to": 11})
        self.assertIn("exact_copy", a.targets(-1)["rows"][0]["grade_flags"])

    def test_one_miss_holds_two_misses_reduce_e1rm_matched(self):
        a = self.athlete([{"title": "Day A", "exercises": [
            ex(BENCH, [(100, 10)] * 3, rep_range=[8, 12], category="compound", tool="barbell_upper")]}])
        a.session(wk(-1), "Day A", [(BENCH, [(100, 7)] * 3)])
        a.session(wk(0), "Day A", [(BENCH, [(100, 6)] * 3)])
        a.write(wk(-1) + timedelta(days=6))
        a.propose(0)
        self.assertEqual(a.targets(-1)["rows"][0]["grade"], "miss")
        r = a.row(0, "day-a-1")
        self.assertEqual((r["decision"], r["reason"]["code"], r["needs_approval"]), ("hold", "miss_hold", False))
        a.run("apply", "--week", lab(0), "--accept-all")
        a.write(wk(0) + timedelta(days=6))
        out = a.propose(1)
        r2 = a.row(1, "day-a-1")
        self.assertEqual((r2["decision"], r2["reason"]["code"]), ("reduce", "reduce"))
        self.assertTrue(r2["needs_approval"])
        self.assertIn("coach_review", r2["flags"])
        # best logged 100×6 (e1RM 120) -> 85×9 (e1RM 110.5 = 92 %), every set the same
        self.assertEqual(r2["target_sets"], S([(85.0, 9)] * 3))
        self.assertEqual(r2["reason"]["pct"], 92)
        self.assertIn("about 92 % of what you lifted", out)
        self.assertIn("| ask |", out)

    def test_rep_pr_miss_saves_one_week_only(self):
        a = self.athlete([{"title": "Day A", "exercises": [
            ex(RAISE, [(16, 15)] * 4, rep_range=[12, 15], load_step_kg=2.0, category="isolation")]}])
        a.session(wk(-1), "Day A", [(RAISE, [(16, 15), (16, 13), (16, 12), (16, 11)])])
        a.session(wk(0), "Day A", [(RAISE, [(16, 15), (16, 14), (16, 13), (16, 12)])])   # +3 total
        a.session(wk(1), "Day A", [(RAISE, [(16, 15), (16, 14), (16, 13), (16, 12)])])   # same
        a.write(wk(-1) + timedelta(days=6))
        a.propose(0)
        a.run("apply", "--week", lab(0), "--accept-all")
        a.write(wk(0) + timedelta(days=6))
        a.propose(1)
        self.assertIn("rep_pr", a.row(0, "day-a-1")["grade_flags"])
        self.assertEqual(a.row(1, "day-a-1")["reason"]["code"], "rep_pr_hold")
        a.run("apply", "--week", lab(1), "--accept-all")
        a.write(wk(1) + timedelta(days=6))
        a.propose(2)
        self.assertNotIn("rep_pr", a.row(1, "day-a-1")["grade_flags"])
        self.assertEqual(a.row(2, "day-a-1")["decision"], "reduce")          # the PR miss counted once

    def test_easy_week_then_restore(self):
        a = self.athlete([{"title": "Day A", "exercises": [
            ex(BENCH, [(100, 10)] * 3, rep_range=[8, 12], category="compound", tool="barbell_upper")]}])
        a.current("| Microcycle | Type | Dates | Status |\n|---|---|---|---|\n"
                  f"| W5 | Full | {wk(-1)} → x | done |\n"
                  f"| W6 | **Recovery (easy week)** | {wk(0)} → x | planned |\n"
                  f"| W7 | Full | {wk(1)} → x | planned |\n")
        a.session(wk(-1), "Day A", [(BENCH, [(100, 10)] * 3)])
        a.session(wk(0), "Day A", [(BENCH, [(90, 10)] * 2)])
        a.write(wk(-1) + timedelta(days=6))
        a.propose(0)
        r = a.row(0, "day-a-1")
        self.assertEqual(r["decision"], "easy_week")
        self.assertEqual(len(r["target_sets"]), 2)                       # 3 sets -> -1/3
        self.assertEqual(r["target_kg"], 90.0)                            # -10 %
        self.assertEqual([s["kg"] for s in r["pre_easy_sets"]], [100.0] * 3)
        a.run("apply", "--week", lab(0), "--accept-all")
        a.write(wk(0) + timedelta(days=6))
        a.propose(1)
        self.assertEqual(a.row(0, "day-a-1")["grade"], "excluded")        # easy week is not graded
        r1 = a.row(1, "day-a-1")
        self.assertEqual(r1["reason"]["code"], "after_easy_week")
        self.assertEqual(r1["target_sets"], S([(100.0, 10)] * 3))

    def test_not_done_holds(self):
        a = self.athlete([{"title": "Day A", "exercises": [ex(BENCH, [(100, 10)] * 3, rep_range=[8, 12])]},
                          {"title": "Day B", "exercises": [ex(FACE_PULL, [(25, 15)] * 2, rep_range=[12, 15])]}])
        a.session(wk(-1), "Day B", [(FACE_PULL, [(25, 15)] * 2)]).write(wk(-1) + timedelta(days=6))
        a.propose(0)
        g = a.targets(-1)["rows"][0]
        self.assertEqual((g["id"], g["grade"]), ("day-a-1", "not_done"))
        r = a.row(0, "day-a-1")
        self.assertEqual((r["decision"], r["reason"]["code"]), ("hold", "not_done"))
        self.assertEqual(r["target_sets"], r["prev_target_sets"])

    def test_warmup_logged_as_normal_is_ignored(self):
        a = self.athlete([{"title": "Day A", "exercises": [ex(BENCH, [(100, 8)] * 3, rep_range=[6, 10])]}])
        a.session(wk(-1), "Day A", [(BENCH, [(60, 10), (80, 5), (100, 8), (100, 8), (100, 8)])])
        a.write(wk(-1) + timedelta(days=6))
        a.run("grade", "--week", lab(-1))
        g = a.targets(-1)["rows"][0]
        self.assertEqual(g["grade"], "hit")
        self.assertEqual([s["kg"] for s in g["source_sets"]], [100.0] * 3)

    def test_assisted_runs_inverted(self):
        tgt = S([(10, 10)] * 2)
        easier = [dict(s, kg=15, idx=i) for i, s in enumerate(tgt)]
        harder = [dict(s, kg=5, idx=i) for i, s in enumerate(tgt)]
        self.assertNotEqual(pg.grade_exposure(tgt, easier, [8, 12], 5.0, True)["grade"], "hit")
        self.assertEqual(pg.grade_exposure(tgt, harder, [8, 12], 5.0, True)["grade"], "hit")
        a, r = self.one(DIP, [(10, 12)] * 2, [(10, 12)] * 2, rep_range=[8, 12], load_step_kg=5.0,
                        assisted=True, tool="machine")
        self.assertEqual((r["decision"], r["reason"]["code"]), ("increase", "step_assisted"))
        self.assertEqual(r["target_sets"], S([(5.0, 8)] * 2))

    def test_spine_lift_needs_ok_and_reps_left_gate(self):
        a, r = self.one(DEADLIFT, [(140, 8)] * 3, [(140, 8)] * 3, rep_range=[4, 8], load_step_kg=2.5,
                        category="spine", tool="barbell_lower")
        self.assertEqual(r["decision"], "increase")
        self.assertTrue(r["needs_approval"])
        self.assertIn("reps_left_missing", r["flags"])
        self.assertIn("Needs your OK: load goes up on a spine-loaded lift.", pg.row_text(r))
        # 1 rep left on the last set, target 2 -> same weight
        a, r = self.one(DEADLIFT, [(140, 8)] * 3, [(140, 8, "normal", 2), (140, 8, "normal", 2),
                                                   (140, 8, "normal", 1)],
                        rep_range=[4, 8], load_step_kg=2.5, category="spine", tool="barbell_lower")
        self.assertEqual((r["decision"], r["reason"]["code"]), ("hold", "top_too_hard"))
        self.assertNotIn("reps_left_missing", r["flags"])
        self.assertEqual(r["target_kg"], 140.0)

    def test_stale_data_refuses(self):
        a = self.athlete([{"title": "Day A", "exercises": [ex(BENCH, [(100, 10)] * 3)]}])
        a.session(wk(-1), "Day A", [(BENCH, [(100, 10)] * 3)]).write(wk(-1) + timedelta(days=3))
        with self.assertRaises(SystemExit) as cm:
            a.propose(0)
        self.assertIn("REFUSED", str(cm.exception))
        self.assertFalse(os.path.exists(pg.targets_path(a.dir, lab(0))))
        with self.assertRaises(SystemExit):
            a.run("grade", "--week", lab(-1))
        a.propose(0, "--data-through", str(wk(-1) + timedelta(days=6)))   # the athlete says it's complete
        self.assertEqual(a.targets(0)["status"], "proposed")

    def test_per_routine_separation(self):
        a = self.athlete([
            {"title": "Day A", "exercises": [ex(FACE_PULL, [(25, 15)] * 2, rep_range=[12, 15], load_step_kg=1.25)]},
            {"title": "Day B", "exercises": [ex(FACE_PULL, [(25, 13)] * 3, rep_range=[12, 15], load_step_kg=1.25)]}])
        a.session(wk(-1), "Day A", [(FACE_PULL, [(25, 15)] * 2)])
        a.session(wk(-1) + timedelta(days=1), "Day B", [(FACE_PULL, [(25, 12)] * 3)])
        a.write(wk(-1) + timedelta(days=6))
        a.propose(0)
        x, y = a.row(0, "day-a-1"), a.row(0, "day-b-1")
        self.assertEqual((x["decision"], x["target_kg"]), ("increase", 26.25))
        self.assertEqual((y["decision"], y["target_kg"], y["reason"]["code"]), ("hold", 25.0, "miss_hold"))
        self.assertEqual({r["id"]: r["grade"] for r in a.targets(-1)["rows"]},
                         {"day-a-1": "hit", "day-b-1": "miss"})

    def test_auto_isolation_only(self):
        a = self.athlete([{"title": "Day A", "exercises": [
            ex(DEADLIFT, [(140, 8)] * 3, rep_range=[4, 8], category="spine", tool="barbell_lower"),
            ex(RAISE, [(20, 12)] * 3, rep_range=[10, 12], load_step_kg=2.0, category="isolation"),
            ex(BENCH, [(100, 12)] * 3, rep_range=[8, 12], category="compound", tool="barbell_upper")]}])
        a.session(wk(-1), "Day A", [(DEADLIFT, [(140, 8)] * 3), (RAISE, [(20, 12)] * 3),
                                    (BENCH, [(100, 12)] * 3)]).write(wk(-1) + timedelta(days=6))
        a.propose(0)
        program = sha(os.path.join(a.dir, "plan", "program.json"))
        with self.assertRaises(SystemExit):                  # the athlete is absent: no approvals
            a.run("apply", "--week", lab(0), "--auto-isolation-only", "--approve", "day-a-1")
        a.run("apply", "--week", lab(0), "--auto-isolation-only")
        doc = a.targets(0)
        rows = {r["id"]: r for r in doc["rows"]}
        self.assertEqual((doc["status"], doc["apply_mode"]), ("applied", "auto-isolation-only"))
        self.assertTrue(rows["day-a-2"]["accepted"])
        self.assertEqual(rows["day-a-2"]["live_target_sets"][0], {"kg": 22.0, "reps": 10, "type": "normal"})
        self.assertFalse(rows["day-a-1"]["accepted"])         # spine: held
        self.assertFalse(rows["day-a-3"]["accepted"])         # compound: held
        self.assertEqual(rows["day-a-1"]["live_target_sets"][0]["kg"], 140.0)
        self.assertEqual(program, sha(os.path.join(a.dir, "plan", "program.json")))   # never written

    def test_two_level_shifts_in_a_row_reanchor(self):
        a = self.athlete([{"title": "Day A", "exercises": [
            ex("Leg_Press", [(130, 12)] * 3, rep_range=[10, 15], load_step_kg=5.0, category="compound",
               tool="machine")]}])
        a.session(wk(-1), "Day A", [("Leg_Press", [(60, 15)] * 3)])
        a.session(wk(0), "Day A", [("Leg_Press", [(60, 15)] * 3)])
        a.write(wk(-1) + timedelta(days=6))
        a.propose(0)
        self.assertIn("level_shift", a.row(-1, "day-a-1")["grade_flags"])
        r = a.row(0, "day-a-1")
        self.assertEqual((r["reason"]["code"], r["target_kg"]), ("excluded_hold", 130.0))
        self.assertIn("coach_review", r["flags"])
        a.run("apply", "--week", lab(0), "--accept-all")
        a.write(wk(0) + timedelta(days=6))
        a.propose(1)
        r = a.row(1, "day-a-1")
        self.assertEqual((r["reason"]["code"], r["needs_approval"]), ("reanchor", True))
        self.assertEqual(r["target_sets"], S([(60.0, 15)] * 3))

    def test_first_session_sets_the_weight(self):
        a, r = self.one(SQUAT, [(None, 8)] * 3, [(40, 5, "warmup"), (60, 8), (60, 8), (60, 7)],
                        rep_range=[6, 10], tool="barbell_lower", category="spine")
        g = a.row(-1, "day-a-1")
        self.assertEqual((g["grade"], g["grade_flags"]), ("excluded", ["calibration"]))
        self.assertEqual((r["reason"]["code"], r["needs_approval"]), ("calibrated", False))
        self.assertEqual(r["target_sets"], S([(60.0, 8), (60.0, 8), (60.0, 7)]))
        self.assertIn("60×8·8·7", pg.row_text(r))


class TestProgramShapes(Base):
    def test_set_count_with_id_key_finds_weights_then_easy_week_from_program(self):
        a = self.athlete([{"title": "Day A", "exercises": [{"id": SQUAT, "sets": 3, "rep_range": [6, 8],
                                                            "load_step_kg": 2.5}]}])
        a.program.update(start=str(wk(-1)), easy_weeks=[2])
        a.save_program()
        a.session(wk(-1), "Day A", [(SQUAT, [(80, 8), (80, 8), (80, 7)])]).write(wk(-1) + timedelta(days=6))
        a.propose(0)
        r = a.row(0, "day-a-1")
        self.assertEqual((r["category"], r["tool"]), ("spine", "barbell_lower"))       # inferred, flagged
        self.assertIn("inferred:category", r["flags"])
        self.assertEqual(a.targets(0)["microcycle_type"], "recovery")                  # program week 2
        self.assertEqual((r["decision"], r["pre_easy_sets"]), ("easy_week", S([(80.0, 8), (80.0, 8), (80.0, 7)])))


class TestEasyWeeksCountedInSessions(Base):
    """Easy weeks are counted in sessions done, not calendar weeks: the engine and program_build agree."""

    def test_a_missed_session_moves_the_easy_week(self):
        a = self.athlete([{"title": "Day A", "exercises": [ex(SQUAT, [(100, 8)] * 3, rep_range=[6, 8])]},
                          {"title": "Day B", "exercises": [ex(BENCH, [(60, 8)] * 3, rep_range=[6, 8])]}])
        a.program.update(start=str(wk(-2)), days=2, easy_weeks=[2, 4])
        a.save_program()
        a.session(wk(-2), "Day A", [(SQUAT, [(100, 8)] * 3)])                    # Day B missed: 1 of 2
        a.session(wk(-1), "Day B", [(BENCH, [(60, 8)] * 3)])
        a.session(wk(-1) + timedelta(days=2), "Day A", [(SQUAT, [(100, 8)] * 3)])
        a.session(wk(-1) + timedelta(days=3), "Other", [(SQUAT, [(100, 8)] * 3)])  # not a program session
        a.write(wk(-1) + timedelta(days=6))
        self.assertEqual(pg.week_type_of(a.dir, wk(-1)), "full")       # calendar week 2, program week 1
        self.assertEqual(pg.week_type_of(a.dir, wk(0)), "recovery")    # 3 sessions done: program week 2
        a.propose(0)
        self.assertEqual(a.targets(0)["microcycle_type"], "recovery")

    def test_program_build_and_the_engine_agree(self):
        import program_build as pb
        for level, days in (("intermediate", 4), ("advanced", 5), ("beginner", 3)):
            prog = {"level": level, "days": days, "routines": [{}] * days}
            every = pb.EASY_WEEK_EVERY[level]
            easy = list(range(every, 53, every)) if every else []
            for n in range(days * 30):
                self.assertEqual(pb.is_easy_week(prog, n), pb.program_week(prog, n) in easy, (level, n))


class TestApply(Base):
    def two_rows(self):
        a = self.athlete([{"title": "Day A", "exercises": [
            ex(DEADLIFT, [(140, 8)] * 3, rep_range=[4, 8], category="spine", tool="barbell_lower"),
            ex(RAISE, [(20, 12)] * 3, rep_range=[10, 12], load_step_kg=2.0, category="isolation")]}])
        a.session(wk(-1), "Day A", [(DEADLIFT, [(140, 8)] * 3), (RAISE, [(20, 12)] * 3)])
        a.write(wk(-1) + timedelta(days=6))
        a.propose(0)
        return a

    def test_needs_ok_requires_explicit_approve(self):
        a = self.two_rows()
        with self.assertRaises(SystemExit):
            a.run("apply", "--week", lab(0))                          # nothing confirmed
        a.run("apply", "--week", lab(0), "--accept-all")
        self.assertFalse(a.row(0, "day-a-1")["accepted"])
        self.assertEqual(a.row(0, "day-a-1")["live_target_sets"][0]["kg"], 140.0)
        self.assertTrue(a.row(0, "day-a-2")["accepted"])
        with self.assertRaises(SystemExit):                           # frozen once applied
            a.run("apply", "--week", lab(0), "--accept-all")

    def test_approve_and_override(self):
        a = self.two_rows()
        a.run("apply", "--week", lab(0), "--accept-all", "--approve", "day-a-1",
              "--override", "day-a-2=21x11·11·10:new dumbbells")
        x, y = a.row(0, "day-a-1"), a.row(0, "day-a-2")
        self.assertTrue(x["accepted"])
        self.assertEqual(x["live_target_sets"][0]["kg"], 142.5)       # no reps left logged: one step
        self.assertEqual((y["source"], y["override_reason"], y["decision"]), ("coach", "new dumbbells", "increase"))
        self.assertEqual([s["reps"] for s in y["live_target_sets"]], [11, 11, 10])

    def override_error(self, ov, *extra):
        a = self.two_rows()
        with self.assertRaises(SystemExit) as cm:
            a.run("apply", "--week", lab(0), "--accept-all", "--override", ov, *extra)
        self.assertEqual(a.targets(0)["status"], "proposed")          # nothing applied
        return str(cm.exception)

    def test_override_spine_increase_needs_approve(self):
        self.assertIn("--approve", self.override_error("day-a-1=145x8·8·8:felt strong"))
        a = self.two_rows()
        a.run("apply", "--week", lab(0), "--accept-all", "--approve", "day-a-1",
              "--override", "day-a-1=145x8·8·8:felt strong")
        self.assertEqual(a.row(0, "day-a-1")["live_target_sets"][0]["kg"], 145)

    def test_override_spine_decrease_needs_no_approve(self):
        a = self.two_rows()
        a.run("apply", "--week", lab(0), "--accept-all", "--override", "day-a-1=130x8·8·8:sore back")
        self.assertEqual(a.row(0, "day-a-1")["live_target_sets"][0]["kg"], 130)

    def test_override_requires_reason(self):
        self.assertIn("reason", self.override_error("day-a-2=21x11·11·10"))
        self.assertIn("reason", self.override_error("day-a-2=21x11·11·10:  "))

    def test_override_rejects_impossible_values(self):
        for ov in ("day-a-2=1875x12:typo", "day-a-2=21x0·12:typo", "day-a-2=21x12·45:typo",
                   "day-a-2=21x" + "·".join(["12"] * 12) + ":typo"):
            self.assertIn("override", self.override_error(ov).lower(), ov)

    def test_at_most_six_coach_changes(self):
        a = self.athlete([{"title": "Day A", "exercises": [
            ex(RAISE, [(10, 12)] * 2, rep_range=[10, 15], load_step_kg=1.0, category="isolation")] * 7}])
        a.session(wk(-1), "Day A", [(RAISE, [(10, 12)] * 2)]).write(wk(-1) + timedelta(days=6))
        a.propose(0)
        ovs = [x for i in range(1, 8) for x in ("--override", f"day-a-{i}=10x12·12:coach")]
        with self.assertRaises(SystemExit) as cm:
            a.run("apply", "--week", lab(0), "--accept-all", *ovs)
        self.assertIn("At most 6", str(cm.exception))
        a.run("apply", "--week", lab(0), "--accept-all", *ovs[:12])
        self.assertEqual(a.targets(0)["status"], "applied")

    def test_unapplied_week_grades_against_previous_target(self):
        a = self.two_rows()                                           # W10 proposed, never applied
        a.session(wk(0), "Day A", [(DEADLIFT, [(140, 8)] * 3), (RAISE, [(20, 12)] * 3)])
        a.write(wk(0) + timedelta(days=6))
        a.run("grade", "--week", lab(0))
        self.assertEqual(a.row(0, "day-a-2")["grade"], "hit")         # vs 20×12, still in force
        self.assertIn("never applied", a.targets(0)["note"])

    def test_regrade_guard(self):
        a = self.two_rows()
        with self.assertRaises(SystemExit):
            a.run("grade", "--week", lab(-1))                         # graded: needs --force
        a.run("grade", "--week", lab(-1), "--force")                 # next week only proposed
        a.run("apply", "--week", lab(0), "--accept-all")
        applied = sha(pg.targets_path(a.dir, lab(0)))
        with self.assertRaises(SystemExit):
            a.run("grade", "--week", lab(-1), "--force")             # next week applied
        self.assertEqual(sha(pg.targets_path(a.dir, lab(0))), applied)

    def test_propose_refuses_frozen_week(self):
        a = self.two_rows()
        a.run("apply", "--week", lab(0), "--accept-all")
        with self.assertRaises(SystemExit) as cm:
            a.propose(0)
        self.assertIn("frozen", str(cm.exception))

    def test_no_changes_is_a_valid_outcome(self):
        a = self.athlete([{"title": "Day A", "exercises": [ex(BENCH, [(100, 10)] * 3, rep_range=[8, 12])]}])
        a.session(wk(-2), "Day A", [(BENCH, [(100, 10)] * 3)])
        a.write(wk(-1) + timedelta(days=6))
        out = a.propose(0)                                            # W9 not done -> hold, same target
        self.assertIn("No changes this week", out)
        self.assertIn("0 change (0 go up in weight) · 1 stay the same", out)

    def test_athlete_note_rides_beside_the_grade_only(self):
        plain, r1 = self.one(BENCH, [(60, 10)] * 3, [(60, 10)] * 3, rep_range=[8, 12])
        noted, r2 = self.one(BENCH, [(60, 10)] * 3, [(60, 10), (60, 10), (60, 10, "normal", "", "elbow ached")],
                             rep_range=[8, 12])
        g = noted.row(-1, "day-a-1")
        self.assertEqual(g["athlete_note"], "elbow ached")
        self.assertIn("athlete_note", g["grade_flags"])
        for k in ("decision", "target_sets", "reason", "needs_approval"):
            self.assertEqual(r1[k], r2[k], k)
        self.assertEqual(r2["last_week"]["athlete_note"], "elbow ached")


class TestUnits(unittest.TestCase):
    def test_level_shift_excluded(self):
        g = pg.grade_exposure(S([(130, 15)] * 3), [dict(s, idx=i) for i, s in enumerate(S([(60, 15)] * 3))],
                              [12, 15], 2.5, False)
        self.assertEqual(g["grade"], "excluded")
        self.assertIn("level_shift", g["flags"])

    def test_heavier_fewer_reps_counts_as_met(self):
        act = [{"kg": 109, "reps": 10, "type": "normal", "idx": 0}, {"kg": 109, "reps": 12, "type": "normal", "idx": 1}]
        self.assertEqual(pg.grade_exposure(S([(95, 12)] * 2), act, [8, 12], 2.5, False)["grade"], "hit")

    def test_close_and_missed(self):
        tgt = S([(100, 10)] * 3)
        close = [dict(s, idx=i) for i, s in enumerate(S([(100, 10), (100, 9), (100, 9)]))]
        self.assertEqual(pg.grade_exposure(tgt, close, [8, 12], 2.5, False)["grade"], "partial")
        short = [dict(s, idx=i) for i, s in enumerate(S([(100, 10), (100, 8), (100, 7)]))]
        g = pg.grade_exposure(tgt, short, [8, 12], 2.5, False)
        self.assertEqual((g["grade"], g["reason"]["short"]), ("miss", 5))

    def test_reduce_picks_closest_to_92_under_95_cap(self):
        sets, pct = pg.reduce_sets(S([(115, 10)] * 3), S([(115, 8), (115, 7), (115, 6)]), 8, 12, 5.0)
        self.assertAlmostEqual(pg.epley(sets[0]["kg"], sets[0]["reps"]) / pg.epley(115, 8), pct)
        self.assertLessEqual(pct, 0.95)
        self.assertEqual(len(sets), 3)
        anchor = pg.epley(115, 8)
        for kg in (110, 105, 100, 95):
            for reps in range(8, 13):
                r = pg.epley(kg, reps) / anchor
                if r <= 0.95:
                    self.assertGreaterEqual(abs(r - 0.92) + 1e-9, abs(pct - 0.92))

    def test_reduce_coarse_grid_takes_one_step(self):
        sets, pct = pg.reduce_sets(S([(10, 12)] * 3), S([(10, 10)] * 3), 10, 15, 2.5)
        self.assertEqual(sets[0]["kg"], 7.5)
        self.assertLess(pct, pg.REDUCE_COARSE)

    def test_reduce_keeps_load_offsets(self):
        sets, _ = pg.reduce_sets(S([(107.5, 8), (105, 8)]), S([(107.5, 6), (105, 6)]), 6, 10, 2.5)
        self.assertAlmostEqual(sets[0]["kg"] - sets[1]["kg"], 2.5)
        self.assertEqual(sets[0]["reps"], sets[1]["reps"])

    def test_rep_pr_thresholds(self):
        prev = S([(16, 15), (16, 13), (16, 12), (16, 11)])                    # total 51
        self.assertTrue(pg.rep_pr(S([(16, 15), (16, 14), (16, 13), (16, 12)]), prev, False))
        self.assertFalse(pg.rep_pr(S([(16, 15), (16, 14), (16, 12), (16, 11)]), prev, False))
        self.assertTrue(pg.rep_pr(S([(16, 17), (16, 13), (16, 12), (16, 10)]), prev, False))
        self.assertFalse(pg.rep_pr(S([(16, 14), (16, 14), (16, 14), (16, 13)]), prev, False))  # best set dropped
        self.assertFalse(pg.rep_pr(S([(14, 17)] * 4), prev, False))          # lighter load
        big = S([(50, 20)] * 4)                                              # total 80 -> +4
        self.assertFalse(pg.rep_pr(S([(50, 21), (50, 21), (50, 21), (50, 20)]), big, False))
        self.assertTrue(pg.rep_pr(S([(50, 21)] * 4), big, False))
        self.assertFalse(pg.rep_pr(prev, None, False))

    def test_miss_streak_rep_pr_counts_once(self):
        h = [{"grade": "miss"}, {"grade": "miss", "rep_pr": True}, {"grade": "miss"}]
        self.assertEqual(pg.miss_streak(h)[0], 2)
        self.assertEqual(pg.miss_streak(h[1:])[0], 1)

    def test_rir_falls_back_to_rpe(self):
        d = tempfile.mkdtemp(prefix="coaich-test-")
        try:
            os.makedirs(os.path.join(d, "data"))
            with open(os.path.join(d, "data", "sets.csv"), "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=SET_COLS)
                w.writeheader()
                base = {c: "" for c in SET_COLS}
                w.writerow(dict(base, date=str(W10), session_id="s", workout_name="Day A", exercise_id=BENCH,
                                set_type="normal", weight_kg=60, reps=8, rpe=8.5))
                w.writerow(dict(base, date=str(W10), session_id="s", workout_name="Day A", exercise_id=BENCH,
                                set_index=1, set_type="normal", weight_kg=60, reps=8, rir=3, rpe=9))
            sets = pg.load_sessions(d)[0]["sets"][BENCH]
            self.assertEqual([s["rir"] for s in sets], [2, 3])               # rir column wins over rpe
        finally:
            shutil.rmtree(d)


# ------------------------------------------------------------------ G119 jump table
ROW = {"rep_range": [8, 12], "load_step": 2.5, "assisted": False, "category": "compound",
       "tool": "barbell_lower", "reps_left": [1, 2]}


def at_top(left, row=ROW, n=3, kg=100.0, prev_code=None, level="intermediate"):
    base = S([(kg, row["rep_range"][1])] * n)
    logged = [dict(s, idx=i, rir=left) for i, s in enumerate(base)]
    g = pg.grade_exposure(base, logged, row["rep_range"], row["load_step"], row["assisted"])
    return pg.decide(row, base, g, {"grade": g["grade"]}, [], "full", level=level, prev_code=prev_code)


class TestJumpTable(unittest.TestCase):
    def test_effort_classes(self):
        cases = [(0, True, "failure"), (0, False, "below_target"), (1, True, "at_target"), (2, True, "at_target"),
                 (3, True, "one_over"), (4, True, "two_plus_over"), (5, True, "two_plus_over"), (None, True, None)]
        for left, compound, want in cases:
            self.assertEqual(pg.effort(left, [1, 2], compound), want, (left, compound))
        self.assertEqual(pg.effort(0, [0, 2], False), "at_target")         # isolation may end at 0 left

    def test_steps_by_reps_left(self):
        for left, add in ((None, 2.5), (1, 2.5), (2, 2.5), (3, 5.0), (4, 5.0)):  # intermediate cap: 2 steps
            r = at_top(left)
            self.assertEqual((r["decision"], r["reason"]["kg_add"]), ("increase", add), left)
            self.assertEqual(r["target_sets"][0], {"kg": 100 + add, "reps": 8, "type": "normal"})

    def test_beginner_takes_three_steps_capped_by_equipment(self):
        self.assertEqual(at_top(4, level="beginner")["reason"]["kg_add"], 7.5)
        big = dict(ROW, load_step=5.0)
        self.assertEqual(at_top(4, row=big, level="beginner")["reason"]["kg_add"], 10.0)   # lower barbell cap 10
        upper = dict(ROW, tool="barbell_upper")
        self.assertEqual(at_top(4, row=upper, level="beginner")["reason"]["kg_add"], 5.0)  # upper barbell cap 5
        db = dict(ROW, tool="dumbbell", load_step=2.0)
        self.assertEqual(at_top(4, row=db, level="beginner")["reason"]["kg_add"], 4.0)     # others: 2 steps

    def test_table_is_the_single_source(self):
        old = dict(pg.JUMP_STEPS)
        try:
            pg.JUMP_STEPS.update(one_over=1, two_plus_over=1)                 # classic one-step progression
            self.assertEqual(at_top(4)["reason"]["kg_add"], 2.5)
        finally:
            pg.JUMP_STEPS.clear()
            pg.JUMP_STEPS.update(old)

    def test_below_target_holds_then_steps_the_second_time(self):
        r = at_top(0, row=dict(ROW, category="isolation", reps_left=[1, 2]))
        self.assertEqual((r["decision"], r["reason"]["code"]), ("hold", "top_too_hard"))
        r = at_top(0, row=dict(ROW, category="isolation", reps_left=[1, 2]), prev_code="top_too_hard")
        self.assertEqual((r["decision"], r["reason"]["code"], r["reason"]["kg_add"]),
                         ("increase", "step_despite_hard", 2.5))

    def test_failure_on_a_compound_holds(self):
        r = at_top(0)
        self.assertEqual((r["decision"], r["reason"]["code"]), ("hold", "failure_hold"))
        self.assertEqual(r["target_sets"][0]["kg"], 100.0)

    def test_spine_jump_still_needs_ok(self):
        r = at_top(4, row=dict(ROW, category="spine", reps_left=[2, 2]))
        self.assertEqual((r["decision"], r["needs_approval"], r["reason"]["kg_add"]), ("increase", True, 5.0))


# ------------------------------------------------------------------ every reason code renders
class TestReasonCodes(unittest.TestCase):
    BANNED = ("rir", "rpe", "deload", "e1rm", "calibrat")

    def decide(self, grade, row=ROW, base=None, history=(), next_type="full", restore=None, **gf):
        base = base or S([(100.0, 10)] * 3)
        return pg.decide(row, base, None, dict(gf, grade=grade), list(history), next_type, restore)

    def produced(self):
        """One scenario per decision code (grade codes come from TestUnits and the folder tests)."""
        miss2 = [{"grade": "miss"}, {"grade": "miss"}]
        logged = S([(100.0, 7)] * 3)
        bw = dict(ROW, load_step=0.0, tool="bodyweight")
        return {
            "easy_week": self.decide("hit", next_type="recovery"),
            "travel_week": self.decide("hit", next_type="travel"),
            "after_easy_week": self.decide("excluded", restore=S([(100.0, 10)] * 3)),
            "not_done": self.decide("not_done"),
            "not_done_x2": self.decide("not_done", history=[{"grade": "not_done"}] * 2),
            "excluded_hold": self.decide("excluded", grade_reason={"code": "out_of_loop"}),
            "calibrated": self.decide("excluded", base=S([(None, 8)] * 3), grade_flags=["calibration"],
                                      source_sets=logged),
            "reanchor": self.decide("excluded", grade_flags=["level_shift"], source_sets=logged,
                                    history=[{"grade": "excluded", "flags": ["level_shift"]}] * 2),
            "close_hold": self.decide("partial", grade_reason={"code": "close", "met": 2, "n": 3, "short": 1}),
            "miss_hold": self.decide("miss", history=miss2[:1]),
            "rep_pr_hold": self.decide("miss", history=miss2[:1], grade_flags=["rep_pr"]),
            "reduce": self.decide("miss", history=miss2, source_sets=logged),
            "reduce_assisted": self.decide("miss", row=dict(ROW, assisted=True), history=miss2, source_sets=logged),
            "fewer_reps": self.decide("miss", row=bw, history=miss2, source_sets=logged),
            "swap_after_reduce": self.decide("miss", history=[{"grade": "miss", "decision": "reduce",
                                                               "accepted": True}] * 3),
            "swap_no_assistance": at_top(None, row=dict(ROW, assisted=True, load_step=5.0), kg=0.0),
            "step": at_top(2),
            "step_despite_hard": at_top(0, row=dict(ROW, category="isolation"), prev_code="top_too_hard"),
            "step_assisted": at_top(None, row=dict(ROW, assisted=True, load_step=5.0), kg=10.0),
            "top_too_hard": at_top(0, row=dict(ROW, category="isolation")),
            "failure_hold": at_top(0),
            "top_no_load": at_top(None, row=bw, kg=0.0),
            "add_rep": self.hit(S([(100.0, 10)] * 3)),
            "reps_to_done": self.hit(S([(100.0, 11)] * 3)),
            "reanchored": self.hit(S([(105.0, 10)] * 3)),
        }

    def hit(self, logged):
        base = S([(100.0, 10)] * 3)
        g = pg.grade_exposure(base, [dict(s, idx=i) for i, s in enumerate(logged)], [8, 12], 2.5, False)
        return pg.decide(ROW, base, g, {"grade": g["grade"]}, [], "full")

    def test_each_decision_code_is_produced_and_renders(self):
        for code, res in self.produced().items():
            with self.subTest(code=code):
                self.assertEqual(res["reason"]["code"], code)
                text = pg.row_text(dict(res, category=ROW["category"]))
                self.assertTrue(text and "{" not in text, text)
                for w in self.BANNED:
                    self.assertNotIn(w, text.lower())

    def test_every_text_code_is_covered(self):
        grade_codes = {"met", "close", "missed", "rep_pr", "easy_week_graded", "travel_week_graded", "reentry",
                       "out_of_loop", "session_not_done", "exercise_not_logged", "level_shift", "calibration"}
        suffixes = {"needs_ok_spine", "needs_ok", "reps_left_missing", "new_row"}
        self.assertEqual(set(pg.TEXT["en"]), set(self.produced()) | grade_codes | suffixes)
        samples = {"met": {"n": 3}, "close": {"met": 2, "n": 3, "short": 1},
                   "missed": {"met": 1, "n": 3, "missing": 1, "under_load": True, "short": 4},
                   "reentry": {"days": 14}, "level_shift": {"kg": 60.0, "target_kg": 130.0}}
        for code in grade_codes | suffixes:
            text = pg.render(dict(samples.get(code, {}), code=code))
            self.assertTrue(text and "{" not in text, code)
            for w in self.BANNED:
                self.assertNotIn(w, text.lower(), code)

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(pg.render({"code": "miss_hold"}, "es"), pg.render({"code": "miss_hold"}))


if __name__ == "__main__":
    unittest.main()
