import os
import unittest

from support import fixture, make_folder, rows, run, text
import athlete_folder as af  # noqa: E402  (support puts the scripts on the path)

A, B = fixture("hae_export_a.json"), fixture("hae_export_b.json")


def health(folder):
    return {(r["date"], r["metric"]): r["value"] for r in rows(folder, "health.csv")}


class OverlappingExports(unittest.TestCase):
    def setUp(self):
        self.d = make_folder(self)
        run("import_apple_health.py", "--dir", self.d, A)
        self.out = run("import_apple_health.py", "--dir", self.d, B).stdout
        self.h = health(self.d)

    def test_overlap_replaces_never_adds(self):
        self.assertEqual(self.h[("2030-03-02", "steps")], "10500")  # in both files; not 21000
        self.assertEqual(self.h[("2030-03-01", "steps")], "8000")
        self.assertEqual(self.h[("2030-03-03", "steps")], "12000")
        self.assertEqual(self.h[("2030-03-02", "active_kcal")], "500")  # 2092 kJ

    def test_metrics_units_and_hygiene(self):
        self.assertEqual(self.h[("2030-03-02", "hrv_ms")], "55")
        self.assertEqual(self.h[("2030-03-02", "sleep_h")], "7.25")
        self.assertEqual(self.h[("2030-03-03", "vo2max")], "45.2")
        self.assertEqual(self.h[("2030-03-03", "weight_kg")], "80.01")  # 176.4 lb
        self.assertNotIn(("2030-03-03", "resting_hr_bpm"), self.h)  # 200 bpm dropped
        self.assertIn("2030-03-03 resting_hr_bpm = 200", self.out)
        self.assertFalse(any(m == "body_fat_pct" for _, m in self.h))
        units = {r["metric"]: r["unit"] for r in rows(self.d, "health.csv")}
        self.assertEqual((units["steps"], units["sleep_h"], units["active_kcal"]), ("count", "h", "kcal"))

    def test_body_csv(self):
        body = {r["date"]: r for r in rows(self.d, "body.csv")}
        self.assertEqual(sorted(body), ["2030-03-01", "2030-03-02", "2030-03-03"])
        self.assertEqual((body["2030-03-02"]["weight_kg"], body["2030-03-02"]["body_fat_pct"]), ("80.2", "18.5"))
        self.assertEqual(body["2030-03-03"]["source"], "apple-health")

    def test_reimport_and_single_call_match(self):
        before = text(self.d, "health.csv"), text(self.d, "body.csv")
        run("import_apple_health.py", "--dir", self.d, A, B)
        self.assertEqual(before, (text(self.d, "health.csv"), text(self.d, "body.csv")))
        d2 = make_folder(self)
        run("import_apple_health.py", "--dir", d2, A, B)
        self.assertEqual(before, (text(d2, "health.csv"), text(d2, "body.csv")))


class ManualValuesSurvive(unittest.TestCase):
    def test_hand_typed_row_kept_beside_the_apple_health_row(self):
        d = make_folder(self)
        os.makedirs(os.path.join(d, "data"))
        with open(os.path.join(d, "data", "body.csv"), "w", encoding="utf-8") as fh:
            fh.write("date,weight_kg,waist_cm,body_fat_pct,source\n2030-03-02,,81.5,,manual\n")
        run("import_apple_health.py", "--dir", d, A)
        day = {r["source"]: r for r in rows(d, "body.csv") if r["date"] == "2030-03-02"}
        self.assertEqual((day["manual"]["weight_kg"], day["manual"]["waist_cm"]), ("", "81.5"))
        self.assertEqual(day["apple-health"]["weight_kg"], "80.2")
        self.assertEqual(af.body_series(d, "weight_kg")[1], ("2030-03-02", 80.2))  # one value per date
        self.assertIn(("2030-03-02", 81.5), af.body_series(d, "waist_cm"))

    def test_not_a_hae_file(self):
        d = make_folder(self)
        r = run("import_apple_health.py", "--dir", d, fixture("hevy_mcp_page2.json"), ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a Health Auto Export", r.stderr)


if __name__ == "__main__":
    unittest.main()
