"""tools/photo_bench.py: the photo-rating benchmark. Synthetic only: empty stand-in files named like filed copies and
a fake `claude` command; no image and no model is involved.
"""
import csv
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

import support  # noqa: F401  (puts scripts/ on sys.path)

sys.path.insert(0, os.path.join(os.path.dirname(support.SCRIPTS), "tools"))
import photo_bench as pb  # noqa: E402
from photos import GROUPS  # noqa: E402

FAKE = """#!{python}
import json, sys
model = sys.argv[sys.argv.index("--model") + 1]
tiers = {tiers}
if model == "broken":
    print(json.dumps({{"result": "I cannot rate this.", "total_cost_usd": 0.01}}))
else:
    body = {{"ratings": {{g: tiers[model] for g in {groups}}}, "confidence": "medium", "body_fat_range": [14, 18]}}
    print(json.dumps({{"result": json.dumps(body), "total_cost_usd": {cost}[model]}}))
"""


class MetricsTest(unittest.TestCase):
    def test_kappa(self):
        perfect = [("strong", "strong"), ("lagging", "lagging"), ("adequate", "adequate")]
        self.assertAlmostEqual(pb.kappa_qw(perfect), 1.0)
        off = [("strong", "adequate"), ("lagging", "severely-lagging"), ("adequate", "adequate")]
        self.assertLess(pb.kappa_qw(off), 1.0)
        self.assertIsNone(pb.kappa_qw([("strong", "strong")] * 3))          # one tier only: undefined
        self.assertIsNone(pb.kappa_qw([("not-visible", "strong")]))         # off-scale answers are not scored

    def test_agreement_direction_and_body_fat(self):
        self.assertEqual(pb.agreement([("strong", "adequate"), ("strong", "lagging")]), (0.0, 0.5))
        self.assertEqual(pb.direction("lagging", "adequate"), 1)
        self.assertEqual(pb.direction("adequate", "adequate"), 0)
        self.assertIsNone(pb.direction("not-visible", "adequate"))
        self.assertEqual(pb.body_fat_hit((14, 18), 15.0), (True, 1.0))
        self.assertEqual(pb.body_fat_hit((18, 14), 20.0), (False, 4.0))

    def test_malformed_answers_are_failures_not_guesses(self):
        self.assertIsNone(pb.parse_answer("no json here"))
        self.assertIsNone(pb.parse_answer('{"ratings": {"calves": "huge"}}'))
        self.assertIsNone(pb.parse_answer('{"ratings": {"unknown-group": "strong"}}'))
        got = pb.parse_answer('Sure: {"ratings": {"calves": "Lagging"}, "body_fat_range": [12, 15]}')
        self.assertEqual(got, ({"calves": "lagging"}, (12.0, 15.0)))

    def test_recommendation(self):
        base = {"repeat_exact": 0.9, "cost_per_set": 0.0}
        s = {"haiku": dict(base, kappa=0.70, cost_per_set=0.01), "opus": dict(base, kappa=0.75, cost_per_set=0.2)}
        self.assertIn("Use haiku", pb.recommend(s))
        s["haiku"]["repeat_exact"] = 0.5
        self.assertIn("Use opus", pb.recommend(s))
        self.assertIn("No model is reliable", pb.recommend({"haiku": dict(base, kappa=0.2)}))


class BenchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="coaich-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.dir = os.path.join(self.tmp, "athlete")
        for d in ("2030-01-06", "2030-03-03"):
            os.makedirs(os.path.join(self.dir, "photos", d))
            for pose in ("front", "side", "back"):
                open(os.path.join(self.dir, "photos", d, f"{pose}.jpg"), "wb").close()
        os.makedirs(os.path.join(self.dir, "data"))
        with open(os.path.join(self.dir, "coaich.md"), "w") as fh:
            fh.write("language: en\n")
        with open(os.path.join(self.dir, "data", "body.csv"), "w") as fh:
            fh.write("date,weight_kg,waist_cm,body_fat_pct,source\n2030-01-06,80,84,16.0,tape\n"
                     "2030-03-03,80,83,30.0,photos\n")
        self.fake = os.path.join(self.tmp, "claude")
        with open(self.fake, "w") as fh:
            fh.write(FAKE.format(python=sys.executable, groups=list(GROUPS),
                                 tiers={"haiku": "adequate", "opus": "lagging", "broken": "strong"},
                                 cost={"haiku": 0.01, "opus": 0.2, "broken": 0.0}))
        os.chmod(self.fake, os.stat(self.fake).st_mode | stat.S_IXUSR)

    def bench(self, *argv):
        return pb.main(["--dir", self.dir, "--claude", self.fake, *argv])

    def test_dry_run_sends_nothing_and_writes_the_blind_template(self):
        self.assertEqual(self.bench(), 0)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "bench", "runs.csv")))
        with open(os.path.join(self.dir, "bench", "reference.csv")) as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 2 * len(GROUPS))
        self.assertTrue(all(r["tier"] == "" for r in rows))

    def test_a_folder_without_photos_stops(self):
        shutil.rmtree(os.path.join(self.dir, "photos"))
        self.assertEqual(self.bench(), 1)

    def test_anything_but_a_filed_copy_is_refused(self):
        for bad in ("photos/2030-01-06/me.jpg", "photos/originals/front.jpg"):
            path = os.path.join(self.dir, bad)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").close()
            with self.assertRaises(SystemExit):
                self.bench()
            os.remove(path)
        original = os.path.join(self.tmp, "Pictures", "front.jpg")
        os.makedirs(os.path.dirname(original))
        open(original, "wb").close()
        link = os.path.join(self.dir, "photos", "2030-01-06", "front.jpg")
        os.remove(link)
        os.symlink(original, link)
        with self.assertRaises(SystemExit):
            self.bench()

    def test_a_full_run_scores_each_model_against_the_reference(self):
        self.bench()
        ref = os.path.join(self.dir, "bench", "reference.csv")
        with open(ref) as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:  # the athlete's own rating: everything adequate in January, lagging calves in March
            r["tier"] = "lagging" if (r["date"] == "2030-03-03" and r["group"] == "calves") else "adequate"
        with open(ref, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["date", "group", "tier"])
            w.writeheader()
            w.writerows(rows)
        self.assertEqual(self.bench("--models", "haiku,opus,broken", "--repeats", "2", "--run"), 0)
        report = open(os.path.join(self.dir, "bench", "report.md")).read()
        self.assertIn("| haiku | 4/4 | 96 %", report)      # 23 of 24 group ratings match
        self.assertIn("| broken | 0/4 |", report)           # no valid answer is a failure, never a guess
        self.assertIn("| 100 % |", report)                  # identical repeats
        # a model that answers "adequate" for everything matches 96 % here but earns kappa 0: no credit for a constant
        self.assertIn("| haiku | 4/4 | 96 % | 100 % | 0.00 |", report)
        self.assertIn("No model is reliable enough", report)
        runs = list(csv.DictReader(open(os.path.join(self.dir, "bench", "runs.csv"))))
        self.assertEqual({r["model"] for r in runs}, {"haiku", "opus", "broken"})
        # the body-fat check uses only measured values (tape), never the photo estimate in body.csv
        scores = pb.score([{"model": "x", "date": "2030-01-06", "repeat": 1, "ratings": {"calves": "adequate"},
                            "body_fat": (14, 18), "cost": 0, "seconds": 0}], {},
                          pb.measured_body_fat(self.dir), ["2030-01-06"])
        self.assertEqual(scores["x"]["body_fat_inside"], 1.0)
        self.assertEqual(pb.measured_body_fat(self.dir), {"2030-01-06": 16.0})


if __name__ == "__main__":
    unittest.main()
