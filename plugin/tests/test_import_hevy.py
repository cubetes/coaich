import os
import unittest

from support import fixture, make_folder, rows, run, text

HEVY_LB_CSV = (
    '"title","start_time","end_time","description","exercise_title","superset_id","exercise_notes",'
    '"set_index","set_type","weight_lbs","reps","distance_miles","duration_seconds","rpe"\n'
    '"Arms","20 Jan 2030, 12:00","20 Jan 2030, 12:40","","Bicep Curl (Dumbbell)",,"",0,"normal",30,12,,,8.5\n'
    '"Arms","20 Jan 2030, 12:00","20 Jan 2030, 12:40","","Treadmill",,"",0,"normal",,,1.5,600,\n')


class HevyCsv(unittest.TestCase):
    def setUp(self):
        self.d = make_folder(self)
        self.out = run("import_hevy.py", "--dir", self.d, fixture("hevy_export_kg.csv")).stdout
        self.sets, self.sessions = rows(self.d, "sets.csv"), rows(self.d, "sessions.csv")

    def test_sessions_sets_durations(self):
        self.assertEqual([s["workout_name"] for s in self.sessions], ["Push", "Legs"])
        self.assertEqual(len(self.sets), 8)
        push = self.sessions[0]
        self.assertEqual((push["duration_min"], push["note"], push["datetime"]), ("65", "Good day", "2030-01-14T18:00"))
        self.assertEqual(push["n_working_sets"], "4")
        self.assertEqual(push["total_volume_kg"], "1182")  # 80*6*2 + 10*15 + 6*12

    def test_set_types_rir_notes(self):
        bench = [r for r in self.sets if r["exercise"] == "Bench Press (Barbell)"]
        self.assertEqual([r["set_type"] for r in bench], ["warmup", "normal", "normal"])
        self.assertEqual([r["rir"] for r in bench], ["", "2", "1"])  # rpe 8 -> 2, 9.5 -> 0.5 rounds up to 1
        lat = [r for r in self.sets if r["exercise"] == "Lateral Raise (Dumbbell)"]
        self.assertEqual((lat[1]["set_type"], lat[1]["note"]), ("dropset", "Slow"))
        self.assertTrue(all(r["source"] == "hevy" for r in self.sets))

    def test_unknown_exercise_lands_in_the_map(self):
        belt = next(r for r in self.sets if r["exercise"] == "Belt Squat (Machine)")
        self.assertEqual(belt["exercise_id"], "custom:belt-squat-machine")
        self.assertIn("Belt Squat (Machine)", self.out)

    def test_reimport_is_idempotent(self):
        before = text(self.d, "sets.csv"), text(self.d, "sessions.csv")
        run("import_hevy.py", "--dir", self.d, fixture("hevy_export_kg.csv"))
        self.assertEqual(before, (text(self.d, "sets.csv"), text(self.d, "sessions.csv")))

    def test_mcp_after_csv_replaces_the_same_workout(self):
        out = run("import_hevy.py", "--dir", self.d, fixture("hevy_mcp_page1.json"), fixture("hevy_mcp_page2.json")).stdout
        self.assertIn("2 sessions", out)  # "Legs" sits on both pages: counted once
        self.assertIn("1 new sessions, 1 updated", out)
        sessions = rows(self.d, "sessions.csv")
        self.assertEqual([s["workout_name"] for s in sessions], ["Push", "Legs", "Pull"])
        legs = sessions[1]
        self.assertEqual(legs["session_id"], "hevy:a1b2c3d4-0000-4000-8000-000000000001")
        squat = next(r for r in rows(self.d, "sets.csv") if r["exercise"] == "Squat (Barbell)")
        self.assertEqual(squat["weight_kg"], "112.5")
        self.assertFalse(any(r["exercise"] == "Belt Squat (Machine)" for r in rows(self.d, "sets.csv")))


class HevyMcp(unittest.TestCase):
    def setUp(self):
        self.d = make_folder(self)
        run("import_hevy.py", "--dir", self.d, fixture("hevy_mcp_page1.json"), fixture("hevy_mcp_page2.json"))

    def test_api_shape(self):
        sets = rows(self.d, "sets.csv")
        pull = next(s for s in rows(self.d, "sessions.csv") if s["workout_name"] == "Pull")
        self.assertEqual((pull["datetime"], pull["duration_min"]), ("2030-01-18T17:00", "60"))
        pu = next(r for r in sets if r["exercise"] == "Pull Up")
        self.assertEqual((pu["weight_kg"], pu["reps"], pu["exercise_id"]), ("0", "8", "Pullups"))
        self.assertEqual(next(r for r in sets if r["exercise"] == "Lat Pulldown (Cable)")["exercise_id"],
                         "Wide-Grip_Lat_Pulldown")

    def test_rerun_is_idempotent_and_cursor(self):
        before = text(self.d, "sets.csv"), text(self.d, "sessions.csv")
        run("import_hevy.py", "--dir", self.d, fixture("hevy_mcp_page2.json"), fixture("hevy_mcp_page1.json"))
        self.assertEqual(before, (text(self.d, "sets.csv"), text(self.d, "sessions.csv")))
        with open(os.path.join(self.d, "log.md"), encoding="utf-8") as fh:
            self.assertIn(" · import · hevy: 2 sessions, 5 sets through 2030-01-18", fh.read().splitlines()[-1])
        self.assertEqual(run("import_hevy.py", "--dir", self.d, "--cursor").stdout.strip(), "2030-01-18")
        self.assertTrue(os.path.exists(os.path.join(self.d, "data", "raw", "hevy", "hevy_mcp_page1.json")))


class HevyPounds(unittest.TestCase):
    def test_lb_and_miles_to_metric(self):
        d = make_folder(self)
        path = os.path.join(d, "hevy_lb.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(HEVY_LB_CSV)
        run("import_hevy.py", "--dir", d, path)
        curl, tread = rows(d, "sets.csv")
        self.assertEqual((curl["weight_kg"], curl["rir"]), ("13.61", "2"))  # 30 lb; rpe 8.5 -> 2
        self.assertEqual((tread["distance_m"], tread["seconds"], tread["reps"]), ("2414", "600", ""))

    def test_rejects_other_files(self):
        d = make_folder(self)
        r = run("import_hevy.py", "--dir", d, fixture("strong_comma_lb.csv"), ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a Hevy workouts export", r.stderr)


if __name__ == "__main__":
    unittest.main()
