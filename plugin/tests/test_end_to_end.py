"""End to end on a fresh copy of the demo athlete, the way the skills run the scripts:
onboard files -> program_build.py -> weekly review (progression.py propose/apply) -> a Strong export of the next
week through import_strong.py -> weekly review again -> check-ins and log.md lines.
Then every importer on its fixtures, one after the other, into one folder."""
import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import support
from support import fixture, run

sys.path.insert(0, support.SCRIPTS)
import athlete_folder as af  # noqa: E402
import demo_athlete as da  # noqa: E402
import program_build as pb  # noqa: E402
import progression as pg  # noqa: E402

DEMO = Path(support.HERE).parent.parent / "examples" / "demo-athlete"
LOG_LINE = re.compile(r"^- \d{4}-\d{2}-\d{2} · [a-z-]+ · \S.*$")


def strong_export(path, folder, week_label):
    """A Strong CSV (semicolon, kg) of one week trained to the applied targets: one rep more on the first set of
    the first exercise of each session, one rep short on the last set of the second."""
    doc = pg.load_json(pg.targets_path(folder, week_label))
    monday = pg.parse_week(week_label)
    days = {"Upper A": 0, "Lower A": 1, "Upper B": 3, "Lower B": 4}
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    w.writerow(["Workout #", "Date", "Workout Name", "Duration (sec)", "Exercise Name", "Set Order", "Weight (kg)",
                "Reps", "RPE", "Distance (meters)", "Seconds", "Notes", "Workout Notes"])
    for n, (routine, rows) in enumerate(pg.by_routine(doc["rows"]).items(), 1):
        start = f"{monday + dt.timedelta(days=days[routine])} 18:30:00"
        for slot, r in enumerate(rows):
            sets = [dict(s) for s in r["live_target_sets"]]
            if slot == 0:
                sets[0]["reps"] += 1
            if slot == 1:
                sets[-1]["reps"] -= 1
            for i, s in enumerate(sets, 1):
                w.writerow([n, start, routine, 3600, r["name"], i, f"{s['kg']:.1f}", s["reps"], 8, "", "", "", ""])
    Path(path).write_text(out.getvalue(), encoding="utf-8")


def review(folder, sunday, last, nxt, *extra):
    """The weekly-review skill: propose, apply with every ask row OK'd, check-in, log line."""
    propose_out = da.run(pg.main, ["propose", "--dir", folder, "--week", nxt, *extra])
    asks = [r["id"] for r in pg.load_json(pg.targets_path(folder, nxt))["rows"] if r["needs_approval"]]
    apply_out = da.run(pg.main, ["apply", "--dir", folder, "--week", nxt, "--accept-all"]
                       + (["--approve", ",".join(asks)] if asks else []))
    result = da.checkin(folder, sunday, last, nxt, propose_out, apply_out)
    af.append_log(folder, "weekly-review", result, date=sunday)
    return propose_out, apply_out, result


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="coaich-e2e-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.dir = os.path.join(self.tmp, "athlete")
        shutil.copytree(DEMO, self.dir)

    def test_a_season_continues_from_the_demo(self):
        d = self.dir
        # Onboard-equivalent files: the tree places the athlete (onboard never computes the level).
        place = json.loads(da.run(pb.main, ["--dir", d, "--place"]))
        self.assertEqual(place["level"], "intermediate")
        # program_build.py from profile.md rebuilds the demo's program byte for byte.
        before = Path(d, "plan/program.json").read_bytes()
        self.assertEqual(run("program_build.py", "--dir", d, "--today", da.START.isoformat()).returncode, 0)
        self.assertEqual(Path(d, "plan/program.json").read_bytes(), before)
        program = pg.load_program(d)
        self.assertEqual((program["level"], program["priority"], program["easy_weeks"][:2]), ("intermediate", None, [7, 14]))

        # The demo's own week 12 (2030-W13) is graded live, as /weekly-review would.
        propose_out, apply_out, result = review(d, "2030-03-31", "2030-W13", "2030-W14")
        self.assertIn("## Targets 2030-W14 (proposed)", propose_out)
        self.assertIn("Hit rate, last 4 weeks:", propose_out)
        self.assertIn("healthy band 70–85 % → healthy", propose_out)
        self.assertRegex(result, r"^2030-W13 graded, \d+/\d+ met, \d+ changes, \d+ held$")
        w14 = pg.load_json(pg.targets_path(d, "2030-W14"))
        self.assertEqual(w14["status"], "applied")
        self.assertTrue(all(r["accepted"] for r in w14["rows"]))

        # Next week arrives as a Strong export and goes through the importer.
        export = os.path.join(self.tmp, "strong.csv")
        strong_export(export, d, "2030-W14")
        n_before = len(af.read_rows(d, "data/sessions.csv"))
        out = run("import_strong.py", export, "--dir", d).stdout
        self.assertIn("4 new sessions", out)
        self.assertEqual(len(af.read_rows(d, "data/sessions.csv")), n_before + 4)
        week = [r for r in af.read_rows(d, "data/sets.csv") if r["date"] >= "2030-04-01"]
        self.assertTrue(week and all(r["session_id"].startswith("strong:") for r in week))
        self.assertFalse([r for r in week if r["exercise_id"].startswith("custom:")])  # names mapped by the map
        self.assertEqual({r["rir"] for r in week}, {"2"})  # RPE 8 -> 2 reps left
        run("import_strong.py", export, "--dir", d)  # re-import: nothing duplicates
        self.assertEqual(len(af.read_rows(d, "data/sessions.csv")), n_before + 4)

        # grade -> propose -> apply. The Friday session ends the data: the athlete says the week is complete.
        graded = da.run(pg.main, ["grade", "--dir", d, "--week", "2030-W14", "--data-through", "2030-04-07"])
        self.assertIn("## Grades 2030-W14 (full week)", graded)
        propose_out, apply_out, result = review(d, "2030-04-07", "2030-W14", "2030-W15", "--data-through",
                                                "2030-04-07")
        w14 = pg.load_json(pg.targets_path(d, "2030-W14"))
        grades = {r["id"]: r["grade"] for r in w14["rows"]}
        self.assertTrue(all(grades[f"{k}-1"] == "hit" for k in ("upper-a", "lower-a", "upper-b", "lower-b")))
        self.assertTrue(all(grades[f"{k}-2"] in ("partial", "miss") for k in ("upper-a", "lower-a", "upper-b", "lower-b")))
        w15 = pg.load_json(pg.targets_path(d, "2030-W15"))
        self.assertEqual(w15["microcycle_type"], "recovery")  # program week 14: the easy week
        self.assertEqual({r["decision"] for r in w15["rows"]}, {"easy_week"})
        self.assertIn("## Next week's targets (2030-W15)", apply_out)

        # Check-ins and log lines.
        checkin = Path(d, "check-ins", "2030-04-07-weekly.md").read_text(encoding="utf-8")
        for head in ("# Weekly check-in · 2030-04-07 · 2030-W14", "## The week", "## Grades", "## Next week (2030-W15)",
                     "## Decisions"):
            self.assertIn(head, checkin)
        log = Path(d, "log.md").read_text(encoding="utf-8").splitlines()
        entries = [x for x in log if x.startswith("- ")]
        self.assertTrue(all(LOG_LINE.match(x) for x in entries), [x for x in entries if not LOG_LINE.match(x)])
        self.assertIn(" · import · strong: 4 sessions, ", "\n".join(entries[-3:]))
        self.assertTrue(entries[-1].startswith("- 2030-04-07 · weekly-review · 2030-W14 graded, "))


class EveryImporter(unittest.TestCase):
    def test_every_importer_on_its_fixtures_into_one_folder(self):
        d = support.make_folder(self)
        run("import_strong.py", fixture("strong_semicolon_kg.csv"), "--dir", d)
        run("import_strong.py", fixture("strong_comma_lb.csv"), "--dir", d, "--unit", "lb")
        run("import_hevy.py", fixture("hevy_export_kg.csv"), "--dir", d)
        run("import_hevy.py", fixture("hevy_mcp_page1.json"), fixture("hevy_mcp_page2.json"), "--dir", d)
        run("import_apple_health.py", fixture("hae_export_a.json"), fixture("hae_export_b.json"), "--dir", d)
        for name, (columns, key) in af.SCHEMAS.items():
            rows = af.read_rows(d, name)
            self.assertTrue(rows, name)
            self.assertEqual(Path(d, name).read_text(encoding="utf-8").splitlines()[0], ",".join(columns), name)
            self.assertEqual(len({tuple(r[k] for k in key) for r in rows}), len(rows), f"{name}: duplicate keys")
        self.assertEqual({r["source"] for r in af.read_rows(d, "data/sessions.csv")}, {"strong", "hevy"})
        log = [x for x in Path(d, "log.md").read_text(encoding="utf-8").splitlines() if x.startswith("- ")]
        self.assertEqual(len(log), 5)
        self.assertTrue(all(LOG_LINE.match(x) and " · import · " in x for x in log), log)


if __name__ == "__main__":
    unittest.main()
