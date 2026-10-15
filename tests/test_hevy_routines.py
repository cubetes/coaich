"""hevy_routines.py: routines built from applied targets, template ids, and the read-back check. Demo data only."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import support  # noqa: F401  (puts scripts/ on sys.path)
import athlete_folder as af  # noqa: E402
import hevy_routines as hr  # noqa: E402
import progression as pg  # noqa: E402

DEMO = os.path.join(os.path.dirname(__file__), "..", "examples", "demo-athlete")


class HevyRoutinesTest(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(tempfile.mkdtemp(prefix="coaich-test-"), "demo")
        self.addCleanup(shutil.rmtree, os.path.dirname(self.dir))
        shutil.copytree(DEMO, self.dir)
        self.week = hr.newest_applied(self.dir)
        self.ids = sorted({r["exercise_id"] for r in pg.load_json(pg.targets_path(self.dir, self.week))["rows"]})

    def run_main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = hr.main(list(argv) + ["--dir", self.dir] if argv[0] != "verify" else list(argv))
        return code, buf.getvalue()

    def all_templates(self):
        for i, eid in enumerate(self.ids):
            self.run_main("template", eid, f"T{i:03d}")

    def test_missing_templates_are_listed_once_and_nothing_is_written(self):
        code, out = self.run_main("build")
        self.assertEqual(code, 2)
        self.assertEqual(out.count("(Romanian_Deadlift)"), 1)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data", "hevy")))

    def test_safety_stop_sends_nothing_to_hevy(self):
        self.all_templates()
        af.set_header(self.dir, "coaich.md", "safety_status", "stop")
        with self.assertRaises(SystemExit) as e:
            self.run_main("build")
        self.assertEqual(e.exception.code, 2)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data", "hevy")))

    def test_build_uses_the_applied_targets_in_program_order(self):
        self.all_templates()
        code, _ = self.run_main("build")
        self.assertEqual(code, 0)
        with open(os.path.join(self.dir, "data", "hevy", f"routines_{self.week}.json")) as fh:
            built = json.load(fh)["routines"]
        doc = pg.load_json(pg.targets_path(self.dir, self.week))
        first = doc["rows"][0]
        rt = built[0]
        self.assertEqual(rt["title"], first["routine"] + " · CoAIch")
        ex = rt["exercises"][0]
        want = pg.effective_target(first, doc["status"])
        self.assertEqual([(s["weight_kg"], s["reps"]) for s in ex["sets"]], [(s["kg"], s["reps"]) for s in want])
        self.assertEqual(ex["sets"][0]["rep_range"], {"start": first["rep_range"][0], "end": first["rep_range"][1]})
        self.assertEqual(ex["notes"], pg.render(first["reason"]))
        self.assertTrue(ex["rest_seconds"] > 0)
        self.assertEqual(len(built), len({r["routine"] for r in doc["rows"]}))

    def test_only_applied_targets_go_to_hevy(self):
        self.all_templates()
        doc = pg.load_json(pg.targets_path(self.dir, self.week))
        doc["status"] = "proposed"
        with open(pg.targets_path(self.dir, self.week), "w") as fh:
            json.dump(doc, fh)
        with self.assertRaises(SystemExit) as e:
            hr.build(self.dir, self.week)
        self.assertIn("not applied", str(e.exception))

    def test_program_push_has_no_weights_and_no_notes(self):
        self.all_templates()
        _, routines, missing = hr.build(self.dir, program_only=True)
        self.assertEqual(missing, [])
        ex = routines[0]["exercises"][0]
        self.assertNotIn("notes", ex)
        self.assertTrue(all("weight_kg" not in s for s in ex["sets"]))

    def test_templates_are_learned_from_imported_hevy_workouts(self):
        raw = os.path.join(self.dir, "data", "raw", "hevy")
        os.makedirs(raw)
        with open(os.path.join(self.dir, "data", "exercise_map.csv"), "a") as fh:
            fh.write("Squat (Barbell),Barbell_Squat\n")
        with open(os.path.join(raw, "w.json"), "w") as fh:
            json.dump({"workout": {"start_time": "2030-03-01T10:00:00Z", "exercises": [
                {"title": "Squat (Barbell)", "exercise_template_id": "tpl-squat", "sets": []}]}}, fh)
        self.assertEqual(hr.templates(self.dir).get("Barbell_Squat"), "tpl-squat")

    def readback(self, routine):
        """A get-routine answer as Hevy shapes it: index fields, no rep_range."""
        r = {"routine": {"id": "x", "title": routine["title"], "exercises": [
            {"index": i, "title": "t", "exercise_template_id": e["exercise_template_id"],
             "sets": [{"index": j, "type": s["type"], "weight_kg": s.get("weight_kg"), "reps": s["reps"]}
                      for j, s in enumerate(e["sets"])]} for i, e in enumerate(routine["exercises"])]}}
        path = os.path.join(self.dir, f"rb-{len(os.listdir(self.dir))}.json")
        with open(path, "w") as fh:
            json.dump(r, fh)
        return path, r

    def test_verify_passes_on_a_match_and_names_a_difference(self):
        self.all_templates()
        self.run_main("build")
        _, routines, _ = hr.build(self.dir, self.week)
        files = [self.readback(rt)[0] for rt in routines]
        code, out = self.run_main("verify", "--dir", self.dir, "--week", self.week, *files)
        self.assertEqual(code, 0, out)
        path, r = self.readback(routines[0])
        r["routine"]["exercises"][0]["sets"][0]["weight_kg"] += 2.5
        with open(path, "w") as fh:
            json.dump(r, fh)
        code, out = self.run_main("verify", "--dir", self.dir, "--week", self.week, path, *files[1:])
        self.assertEqual(code, 1)
        self.assertIn("different " + routines[0]["title"], out)
        self.assertIn("set 1", out)

    def test_verify_fails_when_a_routine_was_not_read_back(self):
        self.all_templates()
        self.run_main("build")
        _, routines, _ = hr.build(self.dir, self.week)
        code, out = self.run_main("verify", "--dir", self.dir, "--week", self.week, self.readback(routines[0])[0])
        self.assertEqual(code, 1)
        self.assertIn("missing " + routines[1]["title"], out)


if __name__ == "__main__":
    unittest.main()
