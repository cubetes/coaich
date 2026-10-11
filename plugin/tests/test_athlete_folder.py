import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import athlete_folder as af  # noqa: E402

SET = {"date": "2030-01-07", "datetime": "2030-01-07T18:30", "session_id": "manual:a", "workout_name": "Upper A",
       "exercise": "Bench Press (Barbell)", "exercise_id": "Barbell_Bench_Press_-_Medium_Grip", "set_index": 0,
       "set_type": "normal", "weight_kg": 60.0, "reps": 8, "rir": 2, "source": "manual"}


class AthleteFolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_walks_up_to_the_folder_with_coaich_md(self):
        (self.dir / "coaich.md").write_text("x")
        deep = self.dir / "check-ins" / "deeper"
        deep.mkdir(parents=True)
        self.assertEqual(af.find(deep), self.dir.resolve())

    def test_find_without_coaich_md_says_to_onboard(self):
        with self.assertRaisesRegex(FileNotFoundError, "onboard"):
            af.find(self.dir)

    def test_init_creates_template_and_never_overwrites(self):
        made = af.init(self.dir)
        for f in ("coaich.md", "profile.md", "plan/CURRENT.md", "log.md", ".gitignore"):
            self.assertIn(f, made)
        (self.dir / "profile.md").write_text("mine")
        self.assertEqual(af.init(self.dir), [])
        self.assertEqual((self.dir / "profile.md").read_text(), "mine")
        self.assertEqual(af.find(self.dir), self.dir.resolve())

    def test_upsert_is_idempotent(self):
        rows = [SET, dict(SET, set_index=1, reps=7)]
        self.assertEqual(af.upsert_rows(self.dir, "data/sets.csv", rows), (2, 0))
        first = (self.dir / "data/sets.csv").read_text()
        self.assertEqual(af.upsert_rows(self.dir, "data/sets.csv", rows), (0, 0))
        self.assertEqual((self.dir / "data/sets.csv").read_text(), first)
        self.assertIn(",60,8,2,,,,manual,", first)  # 60.0 written as 60, blanks for missing columns

    def test_same_set_index_on_another_exercise_is_a_new_row(self):
        af.upsert_rows(self.dir, "data/sets.csv", [SET, dict(SET, exercise="Row (Barbell)")])
        self.assertEqual(len(af.read_rows(self.dir, "data/sets.csv")), 2)

    def test_upsert_replaces_in_place(self):
        af.upsert_rows(self.dir, "data/health.csv", [
            {"date": "2030-01-07", "metric": "steps", "value": 8000, "unit": "count", "source": "apple-health"},
            {"date": "2030-01-07", "metric": "sleep_h", "value": 7.1, "unit": "h", "source": "apple-health"}])
        n = af.upsert_rows(self.dir, "data/health.csv", [
            {"date": "2030-01-07", "metric": "steps", "value": 9000, "unit": "count", "source": "apple-health"}])
        self.assertEqual(n, (0, 1))
        rows = af.read_rows(self.dir, "data/health.csv")
        self.assertEqual([r["value"] for r in rows], ["9000", "7.1"])

    def test_rejects_unknown_columns_blank_keys_and_files(self):
        with self.assertRaises(ValueError):
            af.upsert_rows(self.dir, "data/body.csv", [{"date": "2030-01-07", "weight": 80}])
        with self.assertRaises(ValueError):
            af.upsert_rows(self.dir, "data/body.csv", [{"weight_kg": 80}])
        with self.assertRaises(ValueError):
            af.upsert_rows(self.dir, "data/other.csv", [])
        self.assertFalse((self.dir / "data/body.csv").exists())

    def test_setting_reads_the_template_with_its_comments(self):
        af.init(self.dir)
        self.assertEqual(af.setting(self.dir, "units"), "kg")
        self.assertIsNone(af.setting(self.dir, "safety_clearance_sentence"))

    def test_replace_sessions_drops_sets_gone_at_the_source(self):
        sess = {"date": "2030-01-07", "datetime": "2030-01-07T18:30", "session_id": "manual:a",
                "workout_name": "Upper A", "source": "manual"}
        af.replace_sessions(self.dir, [SET, dict(SET, set_index=1)], [dict(sess, gym="home")])
        self.assertEqual(af.replace_sessions(self.dir, [SET], [dict(sess)]), (0, 1))
        self.assertEqual(len(af.read_rows(self.dir, "data/sets.csv")), 1)
        self.assertEqual(af.read_rows(self.dir, "data/sessions.csv")[0]["gym"], "home")  # hand-filled gym kept

    def test_log_appends_one_line(self):
        (self.dir / "coaich.md").write_text("x")
        af.append_log(self.dir, "onboard", "profile written,\nlevel intermediate", date="2030-01-06")
        with redirect_stdout(io.StringIO()):
            cwd = os.getcwd()
            os.chdir(self.dir)
            try:
                self.assertEqual(af.main(["log", "safety", "status go"]), 0)
            finally:
                os.chdir(cwd)
        lines = (self.dir / "log.md").read_text().splitlines()
        self.assertEqual(lines[-2], "- 2030-01-06 · onboard · profile written, level intermediate")
        self.assertTrue(lines[-1].endswith(" · safety · status go"))


if __name__ == "__main__":
    unittest.main()
