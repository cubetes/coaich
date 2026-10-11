import filecmp
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import athlete_folder as af  # noqa: E402
import demo_athlete  # noqa: E402

COMMITTED = HERE.parent.parent / "examples" / "demo-athlete"


def files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file())


class DemoAthleteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name) / "demo"
        demo_athlete.write(cls.dir, 2030)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_committed_example_matches_the_generator(self):
        self.assertEqual(files(COMMITTED), files(self.dir), "run plugin/scripts/demo_athlete.py")
        for f in files(self.dir):
            self.assertTrue(filecmp.cmp(COMMITTED / f, self.dir / f, shallow=False), f"{f} is stale")

    def test_rerun_replaces_the_demo_byte_for_byte(self):
        before = {f: (self.dir / f).read_bytes() for f in files(self.dir)}
        demo_athlete.write(self.dir, 2030)
        self.assertEqual(before, {f: (self.dir / f).read_bytes() for f in files(self.dir)})

    def test_refuses_a_folder_that_is_not_the_demo(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "coaich.md").write_text("real athlete")
            with self.assertRaises(SystemExit):
                demo_athlete.write(t, 2030)
            self.assertEqual((Path(t) / "coaich.md").read_text(), "real athlete")

    def test_data_follows_the_contract(self):
        self.assertEqual(af.find(self.dir / "plan"), self.dir.resolve())
        for name, (columns, key) in af.SCHEMAS.items():
            header = (self.dir / name).read_text().splitlines()[0]
            self.assertEqual(header, ",".join(columns), name)
            rows = af.read_rows(self.dir, name)
            self.assertTrue(rows, name)
            self.assertEqual(len({tuple(r[k] for k in key) for r in rows}), len(rows), f"{name}: duplicate keys")
            for r in rows:
                if "date" in r:
                    self.assertTrue(r["date"].startswith("2030-"), r)

    def test_training_looks_like_twelve_weeks_with_progress_and_stalls(self):
        sets = af.read_rows(self.dir, "data/sets.csv")
        sessions = af.read_rows(self.dir, "data/sessions.csv")
        self.assertTrue(40 <= len(sessions) <= 48)
        self.assertEqual({s["session_id"] for s in sessions}, {s["session_id"] for s in sets})
        for r in sets:
            if r["set_type"] == "warmup":
                self.assertEqual(r["rir"], "")
            elif r["rir"]:
                self.assertIn(int(r["rir"]), range(6))

        def top(exercise, routine):
            ws = [float(r["weight_kg"]) for r in sets if r["exercise"] == exercise and r["workout_name"] == routine]
            return ws[0], max(ws)

        squat = top("Squat (Barbell)", "Lower A")
        self.assertGreaterEqual(squat[1] - squat[0], 10)  # progresses
        ohp = top("Overhead Press (Barbell)", "Upper A")
        self.assertLessEqual(ohp[1] - ohp[0], 2.5)  # stalls


if __name__ == "__main__":
    unittest.main()
