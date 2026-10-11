"""The monthly lane: plan/changes.md bands, roadmap generation and re-planning, adapt (pain and constraints), the
program re-issue, and an end-to-end monthly run on a copy of the demo athlete. Synthetic data, dates in 2030."""
import contextlib
import datetime as dt
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support

sys.path.insert(0, support.SCRIPTS)
import adapt  # noqa: E402
import athlete_folder as af  # noqa: E402
import changes as ch  # noqa: E402
import monthly_check_in as mc  # noqa: E402
import program_audit as pa  # noqa: E402
import program_build as pb  # noqa: E402
import progression as pg  # noqa: E402
import roadmap as rmp  # noqa: E402

DEMO = Path(support.HERE).parent.parent / "examples" / "demo-athlete"
D = dt.date
RDL, SLDL = "Romanian_Deadlift", "Stiff-Legged_Dumbbell_Deadlift"


def quiet(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        r = fn(*a, **kw)
    return r, out.getvalue()


class DemoCopy(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="coaich-monthly-")
        self.addCleanup(shutil.rmtree, tmp)
        self.dir = Path(tmp) / "athlete"
        shutil.copytree(DEMO, self.dir)

    def program(self):
        return json.loads((self.dir / "plan/program.json").read_text())

    def ids(self, prog=None):
        prog = prog or self.program()
        return [x for r in prog["routines"] for s in r["exercises"] for x in [s["exercise_id"]] + s["alternatives"]]


# ------------------------------------------------------------------ plan/changes.md
class Changes(DemoCopy):
    def test_bands_parse_and_judge(self):
        self.assertEqual(ch.parse_band("70..85"), (70.0, 85.0))
        self.assertEqual(ch.parse_band("5.."), (5.0, None))
        self.assertEqual(ch.parse_band("..-0.25"), (None, -0.25))
        for bad in ("", "..", "85..70", "70-85", "a..b"):
            with self.assertRaises(ValueError):
                ch.parse_band(bad)
        self.assertEqual([ch.verdict(v, (70, 85)) for v in (69.9, 70, 85, 85.1, None)],
                         ["below band", "in band", "in band", "above band", "no data"])

    def test_add_validates_and_reads_back(self):
        with self.assertRaises(ValueError):
            ch.add(self.dir, "x", "x", "x", "e1rm", "0..", "2030-04-28", today="2030-03-31")      # no exercise
        with self.assertRaises(ValueError):
            ch.add(self.dir, "x", "x", "x", "sets:wings", "0..", "2030-04-28", today="2030-03-31")
        with self.assertRaises(ValueError):
            ch.add(self.dir, "x", "x", "x", "hit_rate", "70..85", "2030-03-31", today="2030-03-31")  # not after
        self.assertFalse((self.dir / "plan/changes.md").exists())
        c1 = ch.add(self.dir, "More rows", "Seated row 3 → 4 sets", "back below band", "sets:back", "14..",
                    "2030-04-28", "monthly-check-in", "2030-03-31")
        c2 = ch.add(self.dir, "Pain question", "none", "ask", "ask", "", "2030-04-28", today="2030-03-31")
        self.assertEqual((c1, c2), ("c1", "c2"))
        got = ch.read(self.dir)
        self.assertEqual([(c["id"], c["metric"], c["band"], c["check"]) for c in got],
                         [("c1", "sets:back", "14..", "2030-04-28"), ("c2", "ask", "—", "2030-04-28")])

    def test_grading_against_the_band(self):
        # The demo's last 4 weeks: about 84 % of targets met, 3.75 sessions a week.
        for title, metric, band in (("in", "hit_rate", "70..90"), ("low", "hit_rate", "90.."),
                                    ("high", "sessions_per_week", "..3"), ("ask", "ask", ""),
                                    ("none", "weight_rate", "0..1")):
            ch.add(self.dir, title, "x", "x", metric, band, "2030-03-10", today="2030-03-03")
        ch.add(self.dir, "later", "x", "x", "hit_rate", "70..85", "2030-04-28", today="2030-03-03")
        (self.dir / "data/body.csv").write_text("date,weight_kg,waist_cm,body_fat_pct,source\n")   # no weigh-ins
        graded = {g["title"]: g for g in ch.grade(self.dir, D(2030, 3, 31))}
        self.assertEqual({k: g["verdict"] for k, g in graded.items()},
                         {"in": "in band", "low": "below band", "high": "above band", "ask": "no data",
                          "none": "no data", "later": "too early"})
        self.assertEqual(graded["in"]["call"], "keep")
        self.assertEqual(graded["low"]["call"], "adjust or revert")
        self.assertIsNotNone(graded["later"]["value"])                       # the value so far is still shown
        ch.grade(self.dir, D(2030, 3, 31), write=True)
        text = (self.dir / "plan/changes.md").read_text()
        self.assertEqual(text.count("- graded 2030-03-31: "), 5)
        self.assertEqual([c["title"] for c in ch.open_changes(self.dir)], ["later"])  # graded = closed
        self.assertIn("| c6 later | 2030-03-03 | hit_rate | 70..85 |", ch.table(ch.grade(self.dir, D(2030, 3, 31))))

    def test_measurements_on_the_demo(self):
        start, end = D(2030, 3, 4), D(2030, 3, 31)
        self.assertEqual(ch.measure(self.dir, "sessions_per_week", start, end)[0], 3.75)   # one missed session
        squat, detail = ch.measure(self.dir, "e1rm:Barbell_Squat", start, end)
        self.assertGreater(squat, 0, detail)
        self.assertGreater(ch.measure(self.dir, "weight_rate", start, end)[0], 0)           # the slow lean gain
        quads, detail = ch.measure(self.dir, "sets:quadriceps", start, end)
        self.assertIn("4 full weeks", detail)
        easy = ch.measure(self.dir, "sets:quadriceps", D(2030, 2, 25), D(2030, 3, 10))       # W09 is the easy week
        self.assertIn("1 full weeks", easy[1])


# ------------------------------------------------------------------ roadmap
class Roadmap(DemoCopy):
    def make(self, phases=None, today=D(2030, 3, 31)):
        return quiet(rmp.make, self.dir, today, phases, today)[0]

    def test_a_year_of_phases_blocks_and_weeks(self):
        rm = self.make()
        self.assertEqual((rm["start"], rm["end"]), ("2030-04-01", "2031-03-30"))         # a Sunday → next Monday
        back = rmp.read(self.dir)
        self.assertEqual([(p["name"], p["start"], p["end"], p["status"]) for p in back["phases"]],
                         [("maintenance", "2030-04-01", "2031-03-30", "current")])
        gates = back["phases"][0]["gates"]
        self.assertEqual(gates[:2], ["sessions_per_week 3..", "hit_rate 70..85"])
        self.assertEqual([g.split()[0] for g in gates[2:]], ["e1rm:Barbell_Bench_Press_-_Medium_Grip",
                                                             "e1rm:Barbell_Squat", "e1rm:Romanian_Deadlift"])
        self.assertTrue(all(g.endswith(" 21.5..") for g in gates[2:]), gates)   # intermediate: 5 % per 12 weeks
        text = (self.dir / "plan/roadmap.md").read_text()
        rows = [r for r in text.splitlines() if r.startswith("| ") and "-W" in r]
        self.assertEqual(rows[0], "| 1 | 2030-W14 | 2030-04-01 | 12 | full | maintenance |")   # 46 sessions done
        easy = [int(r.split("|")[4]) for r in rows if "| easy |" in r]
        self.assertTrue(easy and all(n % 7 == 0 for n in easy), easy)
        self.assertIn("| 1 (now) | 12–14 | 2030-04-01 → 2030-04-21 | easy week |", text)
        current = (self.dir / "plan/CURRENT.md").read_text()
        self.assertIn("<!-- coaich:roadmap -->", current)
        self.assertIn("program week 12 · next easy week: program week 14 (about 2030-04-15)", current)
        self.assertIn("<!-- coaich:program -->", current)                                      # untouched
        self.assertIn(" · roadmap · made: 2030-04-01 → 2031-03-30, maintenance 52 wk", (self.dir / "log.md").read_text())

    def test_progression_never_reads_the_projection(self):
        self.make()
        self.assertEqual(pg.week_type_of(self.dir, pg.parse_week("2030-W16")), "full")   # W15 not trained yet

    def test_cut_and_bulk_need_the_nutrition_safeguards(self):
        prof = self.dir / "profile.md"
        af.set_header(self.dir, "profile.md", "wellbeing_pause", "2030-03-30")     # the demo has nutrition on
        with self.assertRaises(SystemExit):
            self.make("cut:12,maintenance:4")
        af.set_header(self.dir, "profile.md", "wellbeing_pause", "")
        rm = self.make("cut:12,maintenance:4,bulk:20")
        cut, _, bulk = rm["phases"]
        self.assertIn("weight_rate -1..-0.25", cut["gates"])
        self.assertTrue(all(g.endswith(" 0..") for g in cut["gates"] if g.startswith("e1rm")))  # keep strength
        self.assertIn("weight_rate 0.1..0.5", bulk["gates"])
        af.set_header(self.dir, "profile.md", "eating_disorder_history", "prefer-not-to-say")
        with self.assertRaises(SystemExit):
            self.make("bulk:12")
        self.assertIn("eating_disorder_history: prefer-not-to-say", prof.read_text())
        with self.assertRaises(ValueError):
            self.make("diet:12")

    def test_gates_then_replan_passed_or_missed(self):
        self.make("maintenance:6,maintenance:10")
        p, due, rows, outcome = rmp.check(self.dir, D(2030, 3, 31))
        self.assertFalse(due)
        p, due, rows, _ = rmp.check(self.dir, D(2030, 5, 3))           # last 2 weeks of the 6-week phase
        self.assertTrue(due)
        self.assertEqual([r[0] for r in rows][:2], ["sessions_per_week", "hit_rate"])
        quiet(rmp.replan, self.dir, "missed", D(2030, 5, 3), 4)
        rm = rmp.read(self.dir)
        self.assertEqual([(p["start"], p["end"]) for p in rm["phases"]],
                         [("2030-04-01", "2030-06-09"), ("2030-06-10", "2030-08-18")])
        self.assertIn("missed 2030-05-03, extended 4 weeks", rm["phases"][0]["result"])
        quiet(rmp.replan, self.dir, "passed", D(2030, 6, 1), 4)          # a Saturday: the phase ends that Sunday
        rm = rmp.read(self.dir)
        self.assertEqual([(p["status"], p["start"], p["end"]) for p in rm["phases"]],
                         [("done", "2030-04-01", "2030-06-02"), ("current", "2030-06-03", "2030-08-11")])
        self.assertEqual(rm["end"], "2030-08-11")
        quiet(rmp.replan, self.dir, "move-on", D(2030, 8, 4), 4)
        self.assertEqual(rmp.check(self.dir, D(2030, 8, 4))[3], "complete")

    def test_beginners_have_no_planned_easy_week(self):
        prog = {"level": "beginner", "days": 3, "routines": [{}] * 3, "easy_weeks": [], "easy_week_every": None,
                "rebuild_at_week": 5}
        self.assertFalse(any(rmp.easy_week(prog, n) for n in range(1, 60)))
        self.assertEqual(rmp.block_ends(prog, 20), [4, 10, 16])

    def test_stop_status_plans_nothing(self):
        af.set_header(self.dir, "coaich.md", "safety_status", "stop")
        r, out = quiet(rmp.main, ["make", "--dir", str(self.dir), "--today", "2030-03-31"])
        self.assertEqual(r, 2)
        self.assertFalse((self.dir / "plan/roadmap.md").exists())


# ------------------------------------------------------------------ adapt
class Adapt(DemoCopy):
    def run_adapt(self, *argv, code=0):
        r, out = quiet(adapt.main, [*argv, "--dir", str(self.dir), "--today", "2030-03-31"])
        self.assertEqual(r, code, out)
        return out

    def test_low_back_never_gets_spine_loading(self):
        for flag in ("--no-red-flag", "--red-flag"):
            out = self.run_adapt("injury", "--area", "lower-back", flag)
            ids = self.ids()
            self.assertFalse([i for i in ids if i in pa.SPINE], (flag, ids))
            self.assertEqual(pa.unexpected_failures(pa.normalise(self.program())), [])
        self.assertIn("checked by a physiotherapist or doctor", out)             # the red-flag wording, first
        self.assertTrue(out.startswith("That pain should be checked"))
        patterns = {s["pattern"] for r in self.program()["routines"] for s in r["exercises"]}
        self.assertFalse(patterns & {"SQ", "SM", "HI", "LU"})                    # red flag: the area's slots out

    def test_a_red_flag_lifecycle_and_its_records(self):
        before = self.program()
        self.run_adapt("injury", "--area", "knee", "--red-flag")
        prof = (self.dir / "profile.md").read_text()
        self.assertIn("pain: [{area: knee, red_flag: true, checked: }]", prof)
        settings = (self.dir / "coaich.md").read_text()
        self.assertIn("safety_status: warn", settings)
        self.assertIn("safety_reasons: [red-flag:knee]", settings)
        self.assertFalse({s["pattern"] for r in self.program()["routines"] for s in r["exercises"]}
                         & {"SQ", "SM", "LU", "KE"})
        self.assertEqual(self.program()["start"], before["start"])               # the easy-week count carries on
        self.assertEqual(self.program()["week"], 12)
        out = self.run_adapt("checked", "--area", "knee")
        self.assertIn("pick a weight you could lift for the top of its rep range with 3–4 reps left", out)
        self.assertIn("safety_reasons: []", (self.dir / "coaich.md").read_text())
        self.assertTrue({s["pattern"] for r in self.program()["routines"] for s in r["exercises"]} & {"SQ", "SM"})
        self.assertNotIn("KE", {s["pattern"] for r in self.program()["routines"] for s in r["exercises"]})
        self.run_adapt("clear", "--area", "knee")
        self.assertIn("pain: []", (self.dir / "profile.md").read_text())
        self.assertIn("safety_status: go", (self.dir / "coaich.md").read_text())
        self.assertEqual(self.ids(), self.ids(before))                           # back to the full program
        log = (self.dir / "plan/changes.md").read_text()
        self.assertEqual([c["title"] for c in ch.read(self.dir)],
                         ["knee pain (red flag)", "knee checked by a professional", "knee pain gone"])
        self.assertTrue(all(c["metric"] == "sessions_per_week" and c["band"] == "3.." and c["check"] == "2030-04-28"
                            for c in ch.read(self.dir)), log)
        self.assertEqual(self.run_adapt("checked", "--area", "knee", code=2).strip(),
                         "error: no red-flag knee pain in profile.md")

    def test_a_refused_program_changes_nothing(self):
        before = {f: (self.dir / f).read_bytes() for f in ("profile.md", "coaich.md", "plan/program.json")}
        with mock.patch.object(pa, "unexpected_failures", return_value=["G6: test"]):
            out = self.run_adapt("injury", "--area", "shoulder", "--no-red-flag", code=1)
        self.assertIn("refused: the program fails the audit: G6: test", out)
        self.assertEqual(before, {f: (self.dir / f).read_bytes() for f in before})
        self.assertFalse((self.dir / "plan/changes.md").exists())

    def test_dry_run_writes_nothing(self):
        before = sorted((p, p.read_bytes()) for p in self.dir.rglob("*") if p.is_file())
        out = self.run_adapt("injury", "--area", "shoulder", "--no-red-flag", "--dry-run")
        self.assertIn("(dry run: nothing was written)", out)
        self.assertEqual(before, sorted((p, p.read_bytes()) for p in self.dir.rglob("*") if p.is_file()))

    def test_short_constraints_set_week_types_the_engine_reads(self):
        self.run_adapt("constraint", "--from", "2030-04-08", "--to", "2030-04-14", "--days", "2")
        self.run_adapt("constraint", "--from", "2030-04-15", "--to", "2030-04-21", "--no-gym")
        self.assertEqual(pg.week_type_of(self.dir, pg.parse_week("2030-W15")), "moderated")
        self.assertEqual(pg.week_type_of(self.dir, pg.parse_week("2030-W16")), "travel")
        self.assertEqual(pg.week_type_of(self.dir, pg.parse_week("2030-W17")), "full")
        self.assertEqual(self.program()["name"], "ul4i·60")                    # no rebuild for a short constraint
        self.assertEqual([c["metric"] for c in ch.read(self.dir)], ["sessions_per_week", "ask"])
        out = self.run_adapt("constraint", "--from", "2030-03-25", "--to", "2030-03-31", "--minutes", "45")
        self.assertIn("2030-W13 targets are already applied: re-run `progression.py propose", out)
        self.assertIn("Nothing to adapt", self.run_adapt("constraint", "--from", "2030-05-01", "--to", "2030-05-03",
                                                         "--days", "4"))

    def test_a_long_constraint_then_back_to_normal(self):
        before = self.program()
        self.run_adapt("constraint", "--from", "2030-04-01", "--to", "2030-05-31", "--days", "3", "--minutes", "45")
        temp = self.program()
        self.assertEqual((temp["days"], temp["minutes"], temp["name"]), (3, 45, "fb3i·45"))
        self.assertEqual(adapt.adapt_meta(self.dir), {"days": "3", "minutes": "45", "until": "2030-05-31"})
        self.run_adapt("injury", "--area", "elbow-wrist", "--no-red-flag")      # pain during it keeps the schedule
        self.assertEqual(self.program()["days"], 3)
        status = quiet(adapt.main, ["status", "--dir", str(self.dir), "--today", "2030-06-02"])[1]
        self.assertIn("DUE: the temporary program ended 2030-05-31", status)
        r, out = quiet(adapt.main, ["restore", "--dir", str(self.dir), "--today", "2030-06-02"])
        self.assertEqual(r, 0, out)
        self.assertEqual((self.program()["days"], self.program()["minutes"]), (before["days"], before["minutes"]))
        self.assertEqual(adapt.adapt_meta(self.dir), {})
        self.assertEqual(self.program()["start"], before["start"])

    def test_gym_only_and_stop(self):
        self.run_adapt("constraint", "--from", "2030-04-01", "--to", "2030-05-31", "--days", "1", code=2)
        af.set_header(self.dir, "coaich.md", "safety_status", "stop")
        self.run_adapt("injury", "--area", "hip", "--no-red-flag", code=2)
        self.assertIn("pain: []", (self.dir / "profile.md").read_text())


# ------------------------------------------------------------------ program_build swaps
class Swaps(DemoCopy):
    def test_swaps_stay_in_their_slot_and_pass_the_audit(self):
        af.set_header(self.dir, "profile.md", "exercise_swaps", f"[{{from: {RDL}, to: {SLDL}}}]")
        a = pb.read_answers(str(self.dir))
        prog = pb.decide(a, 12)["program"]
        ids = [s["exercise_id"] for r in prog["routines"] for s in r["exercises"]]
        self.assertNotIn(RDL, ids)
        self.assertEqual(ids.count(SLDL), 2)
        self.assertTrue(all(s["why"] == "your choice at a check-in" for s in prog["swaps"]), prog["swaps"])
        self.assertEqual(pa.unexpected_failures(prog), [])
        af.set_header(self.dir, "profile.md", "exercise_swaps", f"[{{from: {RDL}, to: Leg_Press}}]")
        with self.assertRaises(ValueError):
            pb.read_answers(str(self.dir))
        a = dict(a, swaps={"Barbell_Squat": "Front_Barbell_Squat"}, history="under_6_months")   # not for beginners
        prog = pb.decide(a, 12)["program"]
        self.assertNotIn("Front_Barbell_Squat", [s["exercise_id"] for r in prog["routines"] for s in r["exercises"]])


class Promotion(DemoCopy):
    def test_promotion_restarts_the_easy_week_count(self):
        old = self.program()
        self.assertEqual((old["level"], old.get("easy_from_week", 1)), ("intermediate", 1))
        r, out = quiet(mc.main, ["reissue", "--dir", str(self.dir), "--today", "2030-03-24", "--promote"])
        self.assertEqual(r, 0, out)
        new = self.program()
        week = new["week"]
        self.assertEqual((new["level"], new["start"], new["easy_from_week"]), ("advanced", old["start"], week))
        self.assertEqual(new["easy_weeks"][0], week + 5)        # every 6th week, counted from the promotion
        self.assertTrue(all(w > week for w in new["easy_weeks"]))
        self.assertFalse(pb.easy_week(new, week + 1))
        self.assertTrue(pb.easy_week(old, 14) and not pb.easy_week(new, 14))
        # Another re-issue at the same level keeps the count.
        r, out = quiet(mc.main, ["reissue", "--dir", str(self.dir), "--today", "2030-03-31", "--swap", f"{RDL}={SLDL}"])
        self.assertEqual(r, 0, out)
        self.assertEqual(self.program()["easy_from_week"], week)


# ------------------------------------------------------------------ the monthly check-in, end to end
def train(folder, label, calibrate_kg=30.0):
    """One week trained to the applied targets (one rep over on each first set), imported as a manual log."""
    doc = pg.load_json(pg.targets_path(folder, label))
    monday = pg.parse_week(label)
    sets, sessions = [], []
    for n, (routine, rows) in enumerate(pg.by_routine(doc["rows"]).items()):
        day = monday + dt.timedelta(days=(0, 1, 3, 4)[n])
        sid = f"manual:{label}-{n}"
        mine = []
        for r in rows:
            for i, s in enumerate(r["live_target_sets"]):
                mine.append({"date": str(day), "datetime": f"{day}T18:00", "session_id": sid, "workout_name": routine,
                             "exercise": r["name"], "exercise_id": r["exercise_id"], "set_index": i,
                             "set_type": "normal", "weight_kg": calibrate_kg if s["kg"] is None else s["kg"],
                             "reps": s["reps"] + (1 if i == 0 else 0), "rir": 2, "source": "manual"})
        sets += mine
        sessions.append({"date": str(day), "datetime": f"{day}T18:00", "session_id": sid, "workout_name": routine,
                         "duration_min": 55, "n_exercises": len(rows), "n_working_sets": len(mine),
                         "total_volume_kg": 0, "source": "manual"})
    af.replace_sessions(folder, sets, sessions)
    af.append_log(folder, "import", f"manual: {len(sessions)} sessions through {monday + dt.timedelta(days=4)}",
                  date=str(monday + dt.timedelta(days=6)))


def weekly(folder, sunday, *extra):
    last = pg.week_label(pg.week_of(sunday))
    nxt = pg.week_label(pg.week_of(sunday) + dt.timedelta(days=7))
    pg.main(["propose", "--dir", str(folder), "--week", nxt, *extra])
    asks = [r["id"] for r in pg.load_json(pg.targets_path(folder, nxt))["rows"] if r["needs_approval"]]
    pg.main(["apply", "--dir", str(folder), "--week", nxt, "--accept-all"] + (["--approve", ",".join(asks)] if asks else []))
    return last, nxt


class MonthlyEndToEnd(DemoCopy):
    def test_two_monthly_check_ins_on_the_demo(self):
        d = str(self.dir)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            weekly(d, D(2030, 3, 31), "--data-through", "2030-03-31")    # the demo's week 12 graded first
            self.assertEqual(rmp.main(["make", "--dir", d, "--today", "2030-03-31", "--phases", "maintenance:12"]), 0)
        text, info = mc.report(d, D(2030, 3, 31))
        for head in ("## The month", "## Volume per muscle", "## Main lifts", "## Flagged by the weekly loop",
                     "## Body", "## Health", "## Past changes", "## Roadmap", "## Nutrition and physique",
                     "## Signals for next month"):
            self.assertIn(head, text)
        self.assertIn("| 2030-W13 | full | 4/4 |", text)
        self.assertIn("| 2030-W11 | full | 3/4 |", text)                         # the missed session
        self.assertIn("Placement promised an Advanced offer from week 6", text)
        self.assertIn("The block ends with program week 14 (an easy week)", text)
        self.assertIn("Nutrition skill: on · physique skill: off.", text)
        self.assertIn("Targets in force since 2030-01-07: phase gain (0.25 % a week)", text)
        self.assertRegex(text, r"Weight trend, 4 weeks to 2030-03-31: \+0\.\d\d kg a week .* → on track\.")
        self.assertIn("For information: below the usual coaching band this month:", text)
        self.assertNotIn("Volume: below", text)                                  # not a signal
        self.assertIn("Phase: maintenance (2030-04-01 → 2030-06-23) · program week 12", text)
        self.assertIn("below the usual coaching band", text)

        # Preview, the athlete says yes, apply; next week's applied targets are re-proposed from the new program.
        before = (self.dir / "plan/program.json").read_bytes()
        r, out = quiet(mc.main, ["reissue", "--dir", d, "--today", "2030-03-31", "--swap", f"{RDL}={SLDL}", "--dry-run"])
        self.assertEqual(r, 0, out)
        self.assertIn("Lower A: out Romanian Deadlift; in Stiff-Legged Dumbbell Deadlift", out)
        self.assertEqual((self.dir / "plan/program.json").read_bytes(), before)
        r, out = quiet(mc.main, ["reissue", "--dir", d, "--today", "2030-03-31", "--swap", f"{RDL}={SLDL}"])
        self.assertEqual(r, 0, out)
        c1 = ch.read(self.dir)[0]
        self.assertEqual((c1["id"], c1["metric"], c1["band"], c1["check"]),
                         ("c1", f"e1rm:{SLDL}", "0..", "2030-04-28"))
        with contextlib.redirect_stdout(io.StringIO()):
            pg.main(["propose", "--dir", d, "--week", "2030-W14", "--force", "--data-through", "2030-03-31"])
            pg.main(["apply", "--dir", d, "--week", "2030-W14", "--accept-all", "--force"])
        w14 = pg.load_json(pg.targets_path(d, "2030-W14"))
        self.assertIn(SLDL, {r["exercise_id"] for r in w14["rows"]})
        r, out = quiet(mc.main, ["report", "--dir", d, "--today", "2030-03-31", "--write",
                                 "--decision", f"Swap Romanian Deadlift → Stiff-Legged Dumbbell Deadlift (c1)",
                                 "--note", "lower back a bit tight on RDLs"])
        self.assertEqual(r, 0, out)
        first = (self.dir / "check-ins/2030-03-31-monthly.md").read_text()
        self.assertTrue(first.startswith("# Monthly check-in · 2030-03-31 · 2030-W10 to 2030-W13"))
        self.assertIn("## Athlete's notes\n\n- “lower back a bit tight on RDLs”", first)
        self.assertIn("## Decisions\n\n- Swap Romanian Deadlift → Stiff-Legged Dumbbell Deadlift (c1)", first)

        # Four weeks trained to the targets; the easy week is counted in sessions (program week 14 = 2030-W16).
        with contextlib.redirect_stdout(io.StringIO()):
            for label, sunday in (("2030-W14", D(2030, 4, 7)), ("2030-W15", D(2030, 4, 14)),
                                  ("2030-W16", D(2030, 4, 21)), ("2030-W17", D(2030, 4, 28))):
                train(d, label)
                weekly(d, sunday, "--data-through", str(sunday))
        self.assertEqual(pg.load_json(pg.targets_path(d, "2030-W16"))["microcycle_type"], "recovery")
        text, info = mc.report(d, D(2030, 4, 28))
        self.assertIn("| 2030-W16 | easy | 4/4 |", text)
        graded = [g for g in info["graded"] if g["id"] == "c1"][0]
        self.assertTrue(graded["due"])
        self.assertIsNotNone(graded["value"], graded)
        self.assertEqual(graded["verdict"], "in band", graded)                  # the new lift went up
        r, out = quiet(mc.main, ["report", "--dir", d, "--today", "2030-04-28", "--write"])
        self.assertEqual(r, 0, out)
        second = (self.dir / "check-ins/2030-04-28-monthly.md").read_text()
        self.assertIn("| c1 Swap Romanian Deadlift → Stiff-Legged Dumbbell Deadlift | 2030-03-31 |", second)
        self.assertIn("## Decisions\n\nNo changes this month.", second)
        self.assertIn("- graded 2030-04-28: in band (", (self.dir / "plan/changes.md").read_text())
        self.assertEqual(ch.open_changes(self.dir), [])
        log = [x for x in (self.dir / "log.md").read_text().splitlines() if " · monthly-check-in · " in x]
        self.assertEqual(len(log), 3)                                       # check-in, re-issue, check-in
        self.assertRegex(log[-1], r"^- 2030-04-28 · monthly-check-in · 2030-W14 to 2030-W17: hit rate \d+ % "
                                  r"\(n=\d+\), 1 change\(s\) graded, 0 decision\(s\)$")


if __name__ == "__main__":
    unittest.main()
