import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from support import fixture, make_folder, rows, run, text

import import_opengym


def backup(d, name, **changes):
    """The fixture backup with top-level keys replaced, saved in the test folder."""
    with open(fixture("opengym_backup.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    doc.update(changes)
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path


class OpenGymBackup(unittest.TestCase):
    def setUp(self):
        self.d = make_folder(self)
        self.out = run("import_opengym.py", "--dir", self.d, fixture("opengym_backup.json")).stdout
        self.sets, self.sessions = rows(self.d, "sets.csv"), rows(self.d, "sessions.csv")

    def test_sessions(self):
        self.assertEqual([s["workout_name"] for s in self.sessions], ["Upper A", "Legs"])  # nothing ticked: left out
        upper = self.sessions[0]
        self.assertEqual((upper["session_id"], upper["datetime"], upper["duration_min"], upper["note"]),
                         ("opengym:wk-test-0001", "2030-02-04T18:00", "62", "Felt fresh"))
        self.assertEqual((upper["n_working_sets"], upper["total_volume_kg"]), ("5", "1552"))  # 80*8 + 80*7 + 20*12 + 14*8
        self.assertIn("2 sessions, 10 sets", self.out)

    def test_set_types_effort_and_undone_sets(self):
        bench = [r for r in self.sets if r["exercise"] == "openGym 0025"]
        self.assertEqual([r["set_type"] for r in bench], ["warmup", "normal", "failure"])  # the undone set is out
        self.assertEqual([(r["rir"], r["rpe"]) for r in bench], [("", ""), ("2", ""), ("1", "9.5")])
        self.assertTrue(all(r["note"] == "Pause on the chest" for r in bench))
        squat = [r for r in self.sets if r["exercise"] == "openGym 0043"]
        self.assertEqual([(r["set_type"], r["rir"]) for r in squat], [("warmup", ""), ("normal", "2")])  # warmup: true

    def test_drops_sides_timed_and_cardio(self):
        fly = [(r["set_type"], r["weight_kg"], r["reps"]) for r in self.sets if r["exercise"] == "cable fly machine"]
        self.assertEqual(fly, [("normal", "20", "12"), ("dropset", "14", "8")])
        lunge = next(r for r in self.sets if r["exercise"] == "openGym 1001")
        self.assertEqual((lunge["weight_kg"], lunge["reps"]), ("16", "20"))  # both sides added up
        plank = next(r for r in self.sets if r["exercise"] == "openGym 0464")
        self.assertEqual((plank["weight_kg"], plank["reps"], plank["seconds"]), ("0", "", "60"))
        bike = next(r for r in self.sets if r["exercise"] == "openGym 0685")
        self.assertEqual((bike["seconds"], bike["distance_m"]), ("1200", "3000"))  # 20 min at 9 km/h

    def test_unknown_exercises_land_in_the_map(self):
        ids = {r["exercise"]: r["exercise_id"] for r in self.sets}
        self.assertEqual(ids["openGym 0025"], "custom:opengym-0025")
        self.assertEqual(ids["cable fly machine"], "custom:cable-fly-machine")  # a custom exercise keeps its name
        self.assertIn("openGym 0025", self.out)

    def test_weigh_ins(self):
        body = rows(self.d, "body.csv")
        self.assertEqual([(b["date"], b["weight_kg"], b["source"]) for b in body],
                         [("2030-02-04", "80.4", "opengym"), ("2030-02-06", "80.1", "opengym")])

    def test_reimport_is_idempotent(self):
        before = [text(self.d, f) for f in ("sets.csv", "sessions.csv", "body.csv", "exercise_map.csv")]
        out = run("import_opengym.py", "--dir", self.d, fixture("opengym_backup.json")).stdout
        self.assertIn("0 new sessions, 2 updated", out)
        self.assertEqual(before, [text(self.d, f) for f in ("sets.csv", "sessions.csv", "body.csv", "exercise_map.csv")])

    def test_log_line_and_raw_copy(self):
        with open(os.path.join(self.d, "log.md"), encoding="utf-8") as fh:
            last = fh.read().splitlines()[-1]
        self.assertRegex(last, r"^- \d{4}-\d{2}-\d{2} · import · opengym: 2 sessions, 10 sets through 2030-02-06$")
        self.assertTrue(os.path.exists(os.path.join(self.d, "data", "raw", "opengym", "opengym_backup.json")))


class OpenGymEdgeCases(unittest.TestCase):
    def test_lb_profile_to_kg(self):
        d = make_folder(self)
        run("import_opengym.py", "--dir", d, backup(d, "lb.json", unit="lb"))
        bench = [r for r in rows(d, "sets.csv") if r["exercise"] == "openGym 0025"]
        self.assertEqual(bench[1]["weight_kg"], "36.29")  # 80 lb
        self.assertEqual(rows(d, "body.csv")[0]["weight_kg"], "36.47")  # 80.4 lb
        bike = next(r for r in rows(d, "sets.csv") if r["exercise"] == "openGym 0685")
        self.assertEqual(bike["distance_m"], "3000")  # speed is km/h whatever the weight unit

    def test_empty_export(self):
        d = make_folder(self)
        out = run("import_opengym.py", "--dir", d, backup(d, "empty.json", workouts=[], bodyweight=[])).stdout
        self.assertIn("opengym: 0 sessions, 0 sets", out)
        self.assertEqual((rows(d, "sets.csv"), rows(d, "body.csv")), ([], []))

    def test_malformed_files_are_refused(self):
        d = make_folder(self)
        bad = os.path.join(d, "broken.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write('{"workouts": [')
        cases = [(bad, "not readable JSON"), (fixture("hevy_mcp_page1.json"), "not an openGym backup"),
                 (backup(d, "unit.json", unit="stone"), "unknown weight unit")]
        zipped = os.path.join(d, "opengym-backup.zip")
        with open(zipped, "wb") as fh:
            fh.write(b"PK\x03\x04")
        cases.append((zipped, "Export backup (JSON)"))
        for path, msg in cases:
            r = run("import_opengym.py", "--dir", d, path, ok=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(msg, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, "data", "sets.csv")))  # nothing written


def write_catalogue(d, names):
    """A synthetic openGym checkout: catalogue/exercises/<id>.json with raw file contents."""
    base = os.path.join(d, "og", "catalogue", "exercises")
    os.makedirs(base)
    for i, raw in names.items():
        with open(os.path.join(base, i + ".json"), "wb") as fh:
            fh.write(raw)
    return os.path.join(d, "og")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class OpenGymNames(unittest.TestCase):
    def test_catalogue_names_then_exercise_map(self):
        d = make_folder(self)
        og = write_catalogue(d, {"0043": b'{"id": "0043", "name": "barbell squat", "bodyPart": "upper legs"}',
                                 "0464": b'{"name": "plank"}', "0025": b"not json",
                                 "0685": json.dumps({"name": "x" * 81}).encode()})
        out = run("import_opengym.py", "--dir", d, "--catalogue", og, fixture("opengym_backup.json")).stdout
        ids = {r["exercise"]: r["exercise_id"] for r in rows(d, "sets.csv")}
        self.assertEqual((ids["barbell squat"], ids["plank"]), ("Barbell_Squat", "Plank"))
        # bad JSON, an oversized name and a missing file (1001) fall back to the number
        self.assertTrue({"openGym 0025", "openGym 0685", "openGym 1001"} <= set(ids))
        self.assertIn("3 openGym exercises have no name yet", out)

    def test_no_flag_says_how_to_get_names(self):
        d = make_folder(self)
        out = run("import_opengym.py", "--dir", d, fixture("opengym_backup.json")).stdout
        self.assertIn("--catalogue <openGym checkout> or --fetch-names", out)

    def test_fetch_uses_and_fills_the_cache(self):
        d = make_folder(self)
        answers = {"0025": b'{"name": "barbell bench press"}', "0043": b'{"name": "barbell squat"}',
                   "0464": b'["plank"]', "0685": b'{"name": "line\\nbreak"}'}
        calls = []

        def fake(url, timeout):
            calls.append(url)
            i = url.rsplit("/", 1)[1][:-5]
            if i not in answers:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return FakeResponse(answers[i])

        ids = ["0025", "0043", "0464", "0685", "1001"]
        with mock.patch("urllib.request.urlopen", fake):
            got = import_opengym.names_from_github(d, ids)
            self.assertEqual(got, {"0025": "barbell bench press", "0043": "barbell squat", "0685": "line break"})
            self.assertEqual(len(calls), 5)
            self.assertTrue(calls[0].startswith("https://raw.githubusercontent.com/DuarteSantos8/openGym/main/"))
            self.assertEqual(import_opengym.names_from_github(d, ids), got)
            self.assertEqual(len(calls), 7)  # cached names are not fetched again; only the two unknown ones
        with open(os.path.join(d, "data", "opengym_names.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), got)

    def test_fetch_refuses_oversized_files_and_stops_without_network(self):
        d = make_folder(self)
        with mock.patch("urllib.request.urlopen", lambda url, timeout: FakeResponse(b" " * (70 * 1024))):
            self.assertEqual(import_opengym.names_from_github(d, ["0025"]), {})

        def offline(url, timeout):
            raise urllib.error.URLError("no network")

        with mock.patch("urllib.request.urlopen", offline), self.assertRaises(SystemExit) as e:
            import_opengym.names_from_github(d, ["0025"])
        self.assertIn("Could not reach GitHub", str(e.exception))


if __name__ == "__main__":
    unittest.main()
