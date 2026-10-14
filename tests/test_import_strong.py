import csv
import os
import unittest

from support import fixture, make_folder, rows, run, text

import import_strong


class SemicolonKgExport(unittest.TestCase):
    def setUp(self):
        self.d = make_folder(self)
        self.out = run("import_strong.py", "--dir", self.d, fixture("strong_semicolon_kg.csv")).stdout
        self.sets = rows(self.d, "sets.csv")
        self.sessions = rows(self.d, "sessions.csv")

    def test_counts_and_hygiene_drop(self):
        self.assertEqual(len(self.sessions), 2)
        self.assertEqual(len(self.sets), 12)  # rest timers and note rows are not sets; 9999 kg is dropped
        self.assertIn("1 row dropped", self.out)

    def test_set_types_from_set_order(self):
        bench = [r for r in self.sets if r["exercise"] == "Bench Press (Barbell)"]
        self.assertEqual([r["set_type"] for r in bench], ["warmup", "normal", "normal", "dropset"])
        self.assertEqual([r["set_index"] for r in bench], ["0", "1", "2", "3"])
        pull = [r["set_type"] for r in self.sets if r["exercise"] == "Pull Up"]
        self.assertEqual(pull, ["normal", "failure"])

    def test_rpe_to_rir(self):
        got = {(r["exercise"], r["rpe"]): r["rir"] for r in self.sets if r["rpe"]}
        self.assertEqual(got[("Bench Press (Barbell)", "8")], "2")
        self.assertEqual(got[("Bench Press (Barbell)", "9")], "1")
        self.assertEqual(got[("Squat (Barbell)", "7.5")], "3")  # 2.5 rounds half up
        self.assertEqual(got[("Deadlift (Barbell)", "8.5")], "2")
        self.assertTrue(all(r["rir"] == "" for r in self.sets if not r["rpe"]))

    def test_session_rollup(self):
        a = next(s for s in self.sessions if s["workout_name"] == "Full body A")
        self.assertEqual(a["duration_min"], "60")
        self.assertEqual(a["n_working_sets"], "7")
        self.assertEqual(a["total_volume_kg"], "2410")  # 60*8*2 + 45*10 + 100*5*2, warm-ups excluded
        self.assertEqual(a["note"], "Felt fresh")
        self.assertTrue(a["session_id"].startswith("strong:"))
        self.assertEqual(a["datetime"], "2030-01-07T18:00")

    def test_notes_timed_and_bodyweight_sets(self):
        bench = [r for r in self.sets if r["exercise"] == "Bench Press (Barbell)"]
        self.assertTrue(all(r["note"] == "Pause on the chest" for r in bench))
        plank = next(r for r in self.sets if r["exercise"] == "Plank")
        self.assertEqual((plank["weight_kg"], plank["reps"], plank["seconds"]), ("0", "", "60"))
        carry = next(r for r in self.sets if r["exercise"] == "Sandbag Zercher Carry")
        self.assertEqual((carry["distance_m"], carry["seconds"]), ("20", "40"))

    def test_exercise_ids(self):
        ids = {r["exercise"]: r["exercise_id"] for r in self.sets}
        self.assertEqual(ids["Bench Press (Barbell)"], "Barbell_Bench_Press_-_Medium_Grip")
        self.assertEqual(ids["Pull Up"], "Pullups")
        self.assertEqual(ids["Sandbag Zercher Carry"], "custom:sandbag-zercher-carry")
        self.assertIn("Sandbag Zercher Carry", self.out)

    def test_reimport_is_idempotent(self):
        before = (text(self.d, "sets.csv"), text(self.d, "sessions.csv"), text(self.d, "exercise_map.csv"))
        out = run("import_strong.py", "--dir", self.d, fixture("strong_semicolon_kg.csv")).stdout
        self.assertIn("0 new sessions, 2 updated", out)
        self.assertEqual(before, (text(self.d, "sets.csv"), text(self.d, "sessions.csv"),
                                  text(self.d, "exercise_map.csv")))
        with open(os.path.join(self.d, "log.md"), encoding="utf-8") as fh:
            self.assertEqual(sum(line.startswith("- ") for line in fh), 2)

    def test_log_line_for_the_stale_data_guard(self):
        with open(os.path.join(self.d, "log.md"), encoding="utf-8") as fh:
            last = fh.read().splitlines()[-1]
        self.assertRegex(last, r"^- \d{4}-\d{2}-\d{2} · import · strong: 2 sessions, 12 sets through 2030-01-09$")

    def test_raw_export_kept(self):
        self.assertTrue(os.path.exists(os.path.join(self.d, "data", "raw", "strong", "strong_semicolon_kg.csv")))

    def test_kept_gym_survives_reimport(self):
        path = os.path.join(self.d, "data", "sessions.csv")
        sess = rows(self.d, "sessions.csv")
        sess[0]["gym"] = "home"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(sess[0]))
            w.writeheader()
            w.writerows(sess)
        run("import_strong.py", "--dir", self.d, fixture("strong_semicolon_kg.csv"))
        self.assertEqual(rows(self.d, "sessions.csv")[0]["gym"], "home")


class CommaPoundExport(unittest.TestCase):
    def test_lb_to_kg_and_older_layout(self):
        d = make_folder(self)
        run("import_strong.py", "--dir", d, "--unit", "lb", fixture("strong_comma_lb.csv"))
        sets = rows(d, "sets.csv")
        bench = [r for r in sets if r["exercise"] == "Bench Press (Dumbbell)"]
        self.assertEqual(bench[0]["weight_kg"], "22.68")  # 50 lb
        self.assertEqual(bench[1]["rir"], "2")
        run_row = next(r for r in sets if r["exercise"] == "Running")
        self.assertEqual((run_row["distance_m"], run_row["seconds"]), ("3218.7", "900"))  # 2 miles
        sess = rows(d, "sessions.csv")[0]
        self.assertEqual(sess["duration_min"], "65")
        self.assertEqual(next(r for r in sets if r["exercise"] == "Lat Pulldown (Cable)")["note"], "Wide grip")

    def test_unit_from_settings(self):
        d = make_folder(self)
        with open(os.path.join(d, "coaich.md"), "w", encoding="utf-8") as fh:
            fh.write("language: en\nunits: lb\n")
        run("import_strong.py", "--dir", d, fixture("strong_comma_lb.csv"))
        self.assertEqual(rows(d, "sets.csv")[0]["weight_kg"], "22.68")

    def test_unknown_unit_stops(self):
        d = make_folder(self)
        with open(os.path.join(d, "coaich.md"), "w", encoding="utf-8") as fh:
            fh.write("language: en\n")
        r = run("import_strong.py", "--dir", d, fixture("strong_comma_lb.csv"), ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--unit", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, "data", "sets.csv")))

    def test_not_an_athlete_folder(self):
        d = make_folder(self, settings=None)
        r = run("import_strong.py", "--dir", d, fixture("strong_comma_lb.csv"), ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("coaich.md", r.stderr)


class Durations(unittest.TestCase):
    def test_parse_duration(self):
        self.assertEqual(import_strong.parse_duration("1h 36m"), 96)
        self.assertEqual(import_strong.parse_duration("45m"), 45)
        self.assertEqual(import_strong.parse_duration("3600"), 60)
        self.assertIsNone(import_strong.parse_duration(""))


if __name__ == "__main__":
    unittest.main()
