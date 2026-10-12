import filecmp
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import athlete_folder as af  # noqa: E402
import demo_athlete  # noqa: E402
import program_build  # noqa: E402

COMMITTED = HERE.parent.parent / "examples" / "demo-athlete"


def files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file())


class DemoAthleteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name) / "demo"
        demo_athlete.write(cls.dir, demo_athlete.SEED)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_committed_example_matches_the_generator(self):
        self.assertEqual(files(COMMITTED), files(self.dir), "run plugin/scripts/demo_athlete.py")
        for f in files(self.dir):
            self.assertTrue(filecmp.cmp(COMMITTED / f, self.dir / f, shallow=False), f"{f} is stale")

    def test_rerun_replaces_the_demo_byte_for_byte(self):
        before = {f: (self.dir / f).read_bytes() for f in files(self.dir)}
        demo_athlete.write(self.dir, demo_athlete.SEED)
        self.assertEqual(before, {f: (self.dir / f).read_bytes() for f in files(self.dir)})

    def test_refuses_a_folder_that_is_not_the_demo(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "coaich.md").write_text("real athlete")
            with self.assertRaises(SystemExit):
                demo_athlete.write(t, demo_athlete.SEED)
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

    def test_the_program_comes_from_the_tree(self):
        self.assertEqual(json.loads((self.dir / "plan/program.json").read_text())["level"], "intermediate")
        with tempfile.TemporaryDirectory() as t:
            for f in ("coaich.md", "profile.md"):
                shutil.copyfile(self.dir / f, Path(t) / f)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(program_build.main(["--dir", t, "--today", demo_athlete.START.isoformat()]), 0)
            self.assertEqual((Path(t) / "plan/program.json").read_bytes(), (self.dir / "plan/program.json").read_bytes())

    def test_twelve_weeks_run_by_the_engine(self):
        sessions = af.read_rows(self.dir, "data/sessions.csv")
        self.assertEqual(len(sessions), 4 * demo_athlete.WEEKS - len(demo_athlete.SKIPPED))
        self.assertEqual({s["session_id"] for s in sessions}, {s["session_id"] for s in af.read_rows(self.dir, "data/sets.csv")})
        docs = [json.loads(p.read_text()) for p in sorted((self.dir / "plan/targets").glob("targets_*.json"))]
        self.assertEqual([d["status"] for d in docs], ["graded"] * (demo_athlete.WEEKS - 1) + ["applied"])
        self.assertEqual([d["microcycle_type"] for d in docs].count("recovery"), 1)  # one easy week
        reasons = {r["reason"]["code"] for d in docs for r in d["rows"] if r.get("reason")}
        self.assertTrue({"calibrated", "step", "reduce", "not_done", "easy_week", "after_easy_week"} <= reasons, reasons)
        # Hit rate: every rolling 4 weeks inside the engine's healthy band (70-85 %).
        weeks = []
        for d in docs[:-1]:
            g = d["summary"]["grades"]
            n = g.get("hit", 0) + g.get("partial", 0) + g.get("miss", 0)
            if n:
                weeks.append((g.get("hit", 0), n))
        for i in range(3, len(weeks)):
            hit = sum(h for h, _ in weeks[i - 3:i + 1]) / sum(n for _, n in weeks[i - 3:i + 1])
            self.assertTrue(0.70 <= hit <= 0.85, (i, hit))
        self.assertEqual(len(list((self.dir / "check-ins").glob("*-weekly.md"))), demo_athlete.WEEKS - 1)

    def test_log_lines_follow_the_contract(self):
        lines = [x for x in (self.dir / "log.md").read_text(encoding="utf-8").splitlines() if x.startswith("- ")]
        self.assertTrue(all(re.fullmatch(r"- 2030-\d\d-\d\d · [a-z-]+ · \S.*", x) for x in lines), lines)
        self.assertEqual(lines[-1].split(" · ")[1], "import")  # week 12 is in, not reviewed yet

if __name__ == "__main__":
    unittest.main()
