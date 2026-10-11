import csv
import os
import unittest

from support import fixture, make_folder, rows, run

import exercise_map as em


class Matching(unittest.TestCase):
    def setUp(self):
        cat = em.load_catalog()
        self.cat, self.by_name, self.aliases = cat, {em.norm(e["name"]): i for i, e in cat.items()}, em.load_aliases()

    def guess(self, name):
        return em.guess(name, self.by_name, self.aliases)

    def test_every_alias_points_into_the_catalogue(self):
        self.assertGreater(len(self.aliases), 200)
        self.assertEqual([i for i in self.aliases.values() if i not in self.cat], [])

    def test_alias_catalogue_reorder_custom(self):
        self.assertEqual(self.guess("bench press (dumbbell)"), ("Dumbbell_Bench_Press", "alias"))
        self.assertEqual(self.guess("Barbell Hip Thrust"), ("Barbell_Hip_Thrust", "catalog"))
        self.assertEqual(self.guess("Calf Raise (Smith Machine)"), ("Smith_Machine_Calf_Raise", "catalog"))
        self.assertEqual(self.guess("Belt Squat (Machine)"), ("custom:belt-squat-machine", "unmapped"))


class FixUps(unittest.TestCase):
    def setUp(self):
        self.d = make_folder(self)
        run("import_strong.py", "--dir", self.d, fixture("strong_semicolon_kg.csv"))
        self.map_path = os.path.join(self.d, "data", "exercise_map.csv")

    def edit_map(self, name, eid):
        m = rows(self.d, "exercise_map.csv")
        self.assertEqual(list(m[0]), ["exercise", "exercise_id"])
        for r in m:
            if r["exercise"] == name:
                r["exercise_id"] = eid
        with open(self.map_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["exercise", "exercise_id"])
            w.writeheader()
            w.writerows(m)

    def ids(self, name):
        return {r["exercise_id"] for r in rows(self.d, "sets.csv") if r["exercise"] == name}

    def test_user_fix_reaches_every_set_and_survives_reimport(self):
        self.edit_map("Sandbag Zercher Carry", "Farmers_Walk")
        out = run("exercise_map.py", "--dir", self.d).stdout
        self.assertNotIn("Sandbag", out)
        self.assertEqual(self.ids("Sandbag Zercher Carry"), {"Farmers_Walk"})
        run("import_strong.py", "--dir", self.d, fixture("strong_semicolon_kg.csv"))
        self.assertEqual(self.ids("Sandbag Zercher Carry"), {"Farmers_Walk"})

    def test_user_custom_id_kept(self):
        self.edit_map("Sandbag Zercher Carry", "custom:zercher-carry")
        run("exercise_map.py", "--dir", self.d)
        self.assertEqual(self.ids("Sandbag Zercher Carry"), {"custom:zercher-carry"})

    def test_typo_in_fix_is_reported(self):
        self.edit_map("Sandbag Zercher Carry", "Farmer_Walk")
        out = run("exercise_map.py", "--dir", self.d).stdout
        self.assertIn("Farmer_Walk", out)
        self.assertEqual(self.ids("Sandbag Zercher Carry"), {"custom:sandbag-zercher-carry"})
        with open(self.map_path, encoding="utf-8") as fh:
            self.assertIn("Farmer_Walk", fh.read())


if __name__ == "__main__":
    unittest.main()
