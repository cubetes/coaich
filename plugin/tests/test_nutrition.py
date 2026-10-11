"""nutrition.py: the safeguards, the targets maths, the weight-trend maintenance, the meal plan, the food table and
the onboard nutrition keys. Synthetic athletes, 2030 dates."""
import csv
import datetime
import os
import re
import unittest

from support import SCRIPTS, make_folder, run

import nutrition as nu

PLUGIN = os.path.dirname(SCRIPTS)
TODAY = "2030-02-01"
D0 = datetime.date(2030, 1, 4)

SETTINGS = """---
coaich: 0.1
language: en
units: kg
safety_acknowledged: 2030-01-01
safety_status: go
---
"""
PROFILE = {"age_band": "18-59", "health_items": "[]", "age_years": "30", "sex": "male", "height": "180 cm",
           "weight": "82 kg", "activity": "moderate", "eating_disorder_history": "no", "nutrition_phase": "lose",
           "diet": "omnivore", "allergies": "[]", "weight_tracking": "yes", "wellbeing_pause": ""}
NUTRITION_KEYS = ["age_years", "sex", "height", "weight", "activity", "eating_disorder_history", "wellbeing_pause",
                  "nutrition_phase", "rate_pct_week", "body_fat_pct", "diet", "allergies", "foods_avoid",
                  "weight_tracking"]


def athlete(test, settings=SETTINGS, **answers):
    d = make_folder(test, settings=None)
    with open(os.path.join(d, "coaich.md"), "w", encoding="utf-8") as f:
        f.write(settings)
    write_profile(d, **answers)
    return d


def write_profile(d, **answers):
    prof = dict(PROFILE, **answers)
    with open(os.path.join(d, "profile.md"), "w", encoding="utf-8") as f:
        f.write("---\n" + "".join(f"{k}: {v}\n" for k, v in prof.items() if v is not None) + "---\n# Profile\n")


def write_body(d, weights, start=D0, bf=""):
    os.makedirs(os.path.join(d, "data"), exist_ok=True)
    with open(os.path.join(d, "data", "body.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "weight_kg", "waist_cm", "body_fat_pct", "source"])
        for i, kg in enumerate(weights):
            w.writerow([(start + datetime.timedelta(days=i)).isoformat(), kg, "", bf, "scale"])


def read(d, *path):
    with open(os.path.join(d, *path), encoding="utf-8") as f:
        return f.read()


def plan(d, *args, ok=True):
    return run("nutrition.py", "plan", "--dir", d, "--today", TODAY, *args, ok=ok)


def nutrition_md(d):
    return nu.front_matter(read(d, "plan", "nutrition.md"))


class Maths(unittest.TestCase):
    def test_mifflin(self):
        self.assertEqual(nu.mifflin(80, 180, 30, "male"), 800 + 1125 - 150 + 5)
        self.assertEqual(nu.mifflin(60, 165, 40, "female"), 600 + 1031.25 - 200 - 161)
        self.assertEqual(nu.mifflin(70, 170, 30, "unspecified"),
                         (nu.mifflin(70, 170, 30, "male") + nu.mifflin(70, 170, 30, "female")) / 2)

    def test_units(self):
        self.assertAlmostEqual(nu.parse_height("5 ft 10 in"), 177.8)
        self.assertAlmostEqual(nu.parse_height("5'10\""), 177.8)
        self.assertEqual(nu.parse_height("178 cm"), 178)
        self.assertAlmostEqual(nu.parse_height("70 in"), 177.8)
        self.assertAlmostEqual(nu.parse_weight("176 lb"), 79.83, places=2)
        self.assertEqual(nu.parse_weight("80"), 80)
        with self.assertRaises(nu.Missing):
            nu.parse_height("tall")

    def test_maintain_targets_add_up(self):
        t = nu.targets(80, 180, 30, "male", "moderate", "maintain")
        rest = nu.mifflin(80, 180, 30, "male")
        self.assertEqual(t["kcal"], nu.round10(rest * 1.55))
        self.assertEqual(t["protein_g"], round(1.8 * 80))
        self.assertEqual(t["fat_g"], round(0.25 * t["kcal"] / 9))
        self.assertAlmostEqual(4 * t["protein_g"] + 4 * t["carbs_g"] + 9 * t["fat_g"], t["kcal"], delta=10)
        self.assertEqual(t["maintenance_source"], "formula")

    def test_lose_and_gain_use_the_rate(self):
        maint = nu.mifflin(80, 180, 30, "male") * 1.55
        lose = nu.targets(80, 180, 30, "male", "moderate", "lose")
        self.assertEqual(lose["rate_pct_week"], 0.5)
        self.assertEqual(lose["kcal"], -(-(maint - 0.005 * 80 * 7700 / 7) // 10) * 10)  # rounded up
        self.assertEqual(lose["protein_g"], 160)  # 2.0 g/kg, body fat unknown
        gain = nu.targets(80, 180, 30, "male", "moderate", "gain")
        self.assertEqual(gain["kcal"], nu.round10(maint + 0.0025 * 80 * 7700 / 7))
        capped = nu.targets(80, 180, 30, "male", "moderate", "gain", rate=1.0)
        self.assertEqual(capped["rate_pct_week"], 0.5)

    def test_lose_protein_from_lean_mass_when_body_fat_known(self):
        t = nu.targets(90, 180, 30, "male", "moderate", "lose", bf=20)
        self.assertEqual(t["protein_g"], round(2.3 * 72))

    def test_protein_basis_capped_at_bmi_30(self):
        t = nu.targets(130, 175, 40, "male", "light", "maintain")
        self.assertEqual(t["protein_g"], round(1.8 * 30 * 1.75 ** 2))

    def test_measured_maintenance_replaces_the_formula(self):
        t = nu.targets(80, 180, 30, "male", "moderate", "maintain", maintenance=3005)
        self.assertEqual((t["kcal"], t["maintenance_source"]), (3010, "weight-trend"))


class LossRateCap(unittest.TestCase):
    def test_bands_by_body_fat_and_sex(self):
        cases = [("male", 10, 0.7), ("male", 14.9, 0.7), ("male", 15, 1.0), ("male", 24.9, 1.0), ("male", 25, 1.5),
                 ("male", 35, 1.5), ("female", 20, 0.7), ("female", 23, 1.0), ("female", 33, 1.5),
                 ("unspecified", 30, 1.0), ("unspecified", 33, 1.5), ("male", None, 0.7), ("female", None, 0.7)]
        for sex, bf, cap in cases:
            self.assertEqual(nu.loss_cap(bf, sex)[0], cap, (sex, bf))

    def test_requested_rate_is_capped(self):
        for bf, cap in ((12, 0.7), (20, 1.0), (30, 1.5), (None, 0.7)):
            t = nu.targets(100, 180, 30, "male", "extra", "lose", bf=bf, rate=2.0)
            floored = any("resting needs" in n for n in t["notes"])
            self.assertEqual(t["rate_pct_week"] if not floored else cap, cap, bf)
            self.assertLessEqual(t["rate_pct_week"], cap, bf)
            self.assertTrue(any("cap" in n for n in t["notes"]))
            maint = nu.mifflin(100, 180, 30, "male") * 1.9
            implied = (maint - t["kcal"]) * 7 / 7700 / 100 * 100
            self.assertLessEqual(implied, cap + 0.01, bf)

    def test_slower_request_is_kept(self):
        self.assertEqual(nu.targets(100, 180, 30, "male", "very", "lose", bf=30, rate=0.3)["rate_pct_week"], 0.3)


class RestingFloor(unittest.TestCase):
    def test_calories_never_below_resting_needs(self):
        # Small, sedentary, higher body fat, fastest rate: the deficit would cut under resting energy.
        for sex, w, h, age, bf in (("female", 70, 155, 60, 40), ("male", 95, 165, 70, 35), ("female", 60, 150, 25, 36)):
            t = nu.targets(w, h, age, sex, "sedentary", "lose", bf=bf, rate=1.5)
            rest = nu.mifflin(w, h, age, sex)
            self.assertGreaterEqual(t["kcal"], rest, sex)
            self.assertTrue(any("resting needs" in n for n in t["notes"]))
            self.assertLess(t["rate_pct_week"], 1.5)

    def test_floor_holds_against_a_low_measured_maintenance(self):
        t = nu.targets(70, 170, 30, "female", "light", "lose", maintenance=1200)
        self.assertGreaterEqual(t["kcal"], nu.mifflin(70, 170, 30, "female"))


class BMI(unittest.TestCase):
    def test_no_fat_loss_below_bmi_18_5(self):
        with self.assertRaises(nu.Safeguard) as c:
            nu.targets(55, 175, 25, "male", "moderate", "lose")  # BMI 17.96
        self.assertEqual((c.exception.code, c.exception.off), ("bmi", False))
        self.assertEqual(nu.targets(55, 175, 25, "male", "moderate", "maintain")["phase"], "maintain")
        self.assertEqual(nu.targets(57, 175, 25, "male", "moderate", "lose")["phase"], "lose")  # BMI 18.6

    def test_refusal_keeps_the_plan_in_force(self):
        d = athlete(self, weight="80 kg")
        plan(d)
        before = read(d, "plan", "nutrition.md")
        write_profile(d, weight="54 kg")
        r = plan(d, ok=False)
        self.assertEqual(r.returncode, 3)
        self.assertIn("below 18.5", r.stdout)
        self.assertEqual(read(d, "plan", "nutrition.md"), before)
        self.assertIn("safeguard bmi: refused", read(d, "log.md"))


class Gate(unittest.TestCase):
    def assert_off(self, code, **answers):
        d = athlete(self)
        plan(d)  # targets in force first: an "off" safeguard must replace them
        write_profile(d, **answers)
        r = plan(d, ok=False)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout.strip(), nu.WORDING[code])
        fm = nutrition_md(d)
        self.assertEqual((fm["status"], fm["reason"]), ("off", code))
        text = read(d, "plan", "nutrition.md")
        self.assertNotIn("kcal", text)
        self.assertIn("lawyer review pending", text)
        self.assertIn(f"Off ({code})", read(d, "plan", "CURRENT.md"))
        self.assertEqual(read(d, "plan", "CURRENT.md").count("<!-- coaich:nutrition -->"), 1)

    def test_under_18(self):
        self.assert_off("age", age_band="16-17")
        self.assert_off("age", age_band="under-16")
        self.assert_off("age", age_years="17")

    def test_eating_disorder_answer_only_no_opens_targets(self):
        for answer in ("yes", "prefer-not-to-say", "maybe", "not sure"):
            self.assert_off("eating-disorder", eating_disorder_history=answer)

    def test_eating_disorder_question_must_be_answered(self):
        d = athlete(self, eating_disorder_history="")
        r = plan(d, ok=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("eating_disorder_history", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, "plan", "nutrition.md")))

    def test_wellbeing_pause(self):
        self.assert_off("wellbeing-pause", wellbeing_pause="2030-01-20")
        d = athlete(self, wellbeing_pause="")  # cleared (blank) → targets again
        self.assertEqual(plan(d).returncode, 0)

    def test_pregnancy(self):
        self.assert_off("pregnancy", health_items="[pregnancy]")

    def test_safety_intake_first(self):
        d = athlete(self, settings="---\ncoaich: 0.1\n---\n")
        r = plan(d, ok=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("safety", r.stderr)

    def test_trend_is_gated_too(self):
        d = athlete(self, eating_disorder_history="yes")
        self.assertEqual(run("nutrition.py", "trend", "--dir", d, "--today", TODAY, ok=False).returncode, 3)
        d = athlete(self, weight_tracking="no")
        r = run("nutrition.py", "trend", "--dir", d, "--today", TODAY, ok=False)
        self.assertEqual(r.returncode, 3)
        self.assertIn("Weight tracking is off", r.stdout)


class Trend(unittest.TestCase):
    def points(self, kg_per_day, days, start=80.0, noise=()):
        return [(D0 + datetime.timedelta(days=i), start + kg_per_day * i + (noise[i % len(noise)] if noise else 0),
                 None) for i in range(days)]

    def test_maintenance_from_a_clean_trend(self):
        pts = self.points(-0.5 / 7, 28)
        tr = nu.trend(pts, D0, D0 + datetime.timedelta(days=27), intake=2300)
        self.assertTrue(tr["usable"], tr)
        self.assertAlmostEqual(tr["kg_per_week"], -0.5)
        self.assertAlmostEqual(tr["maintenance_kcal"], 2300 + 0.5 / 7 * 7700)

    def test_too_short_too_few_or_no_intake(self):
        self.assertIn("14+ days", nu.trend(self.points(-0.05, 10), D0, D0 + datetime.timedelta(days=30), 2300)["why"])
        sparse = self.points(-0.05, 28)[::5]
        self.assertFalse(nu.trend(sparse, D0, D0 + datetime.timedelta(days=30), 2300)["usable"])
        self.assertIn("no intake", nu.trend(self.points(-0.05, 28), D0, D0 + datetime.timedelta(days=30))["why"])

    def test_noisy_trend_is_not_used(self):
        pts = self.points(0, 16, noise=(1.5, -1.5, 2.0, -2.0, 0.5))
        tr = nu.trend(pts, D0, D0 + datetime.timedelta(days=30), 2500)
        self.assertFalse(tr["usable"])
        self.assertIn("noisy", tr["why"])

    def test_plan_uses_the_trend_against_the_plan_in_force(self):
        d = athlete(self, nutrition_phase="maintain")
        os.makedirs(os.path.join(d, "plan"))
        with open(os.path.join(d, "plan", "nutrition.md"), "w", encoding="utf-8") as f:
            f.write("---\nstatus: on\nsince: 2030-01-04\nkcal: 2300\n---\n")
        write_body(d, [80 - 0.5 / 7 * i for i in range(28)])
        plan(d)
        fm = nutrition_md(d)
        self.assertEqual(fm["maintenance_source"], "weight-trend")
        self.assertEqual(fm["maintenance_kcal"], 2850)
        self.assertEqual(fm["kcal"], 2850)
        self.assertEqual(fm["since"], TODAY)  # the next trend window starts here

    def test_losing_faster_than_the_cap_says_eat_more(self):
        d = athlete(self, nutrition_phase="lose")
        os.makedirs(os.path.join(d, "plan"))
        with open(os.path.join(d, "plan", "nutrition.md"), "w", encoding="utf-8") as f:
            f.write("---\nstatus: on\nsince: 2030-01-04\nkcal: 1900\n---\n")
        write_body(d, [80 - 1.0 / 7 * i for i in range(28)])  # ~1.3 %/week, cap 0.7 (body fat unknown)
        out = plan(d).stdout
        self.assertIn("faster than the 0.7 % cap", out)
        fm = nutrition_md(d)
        self.assertGreater(fm["kcal"], 1900)

    def test_weekly_line_against_the_phase_band(self):
        end = D0 + datetime.timedelta(days=27)
        cases = [("lose", 0.5, -0.4, "on track"), ("lose", 0.5, -0.1, "slower than planned"),
                 ("lose", 0.5, -1.2, "losing faster than the safe cap: eat more"), ("gain", 0.25, 0.2, "on track"),
                 ("gain", 0.25, 0.0, "eat more"), ("gain", 0.25, 0.8, "faster than planned"),
                 ("maintain", 0, 0.1, "on track"), ("maintain", 0, -0.6, "eat more"), ("maintain", 0, 0.6, "drifting up")]
        for phase, rate, pct, verdict in cases:
            tr = nu.trend(self.points(80 * pct / 100 / 7, 28), D0, end)
            line = nu.weekly_line(tr, {"phase": phase, "rate_pct_week": rate, "loss_cap_pct_week": 0.7})
            self.assertTrue(line.endswith(f"→ {verdict}."), (phase, pct, line))
            self.assertNotIn("eat less", line)
        few = nu.trend(self.points(-0.05, 28)[::5], D0, end)
        self.assertIn("not enough weigh-ins", nu.weekly_line(few, {"phase": "lose"}))

    def test_trend_line_cli_needs_a_plan_in_force(self):
        d = athlete(self, nutrition_phase="gain")
        write_body(d, [80 + 0.02 * i for i in range(28)])
        r = run("nutrition.py", "trend", "--dir", d, "--today", TODAY, "--line", ok=False)
        self.assertEqual(r.returncode, 3)
        plan(d)
        r = run("nutrition.py", "trend", "--dir", d, "--today", TODAY, "--line")
        self.assertRegex(r.stdout, r"^Weight trend: \+0\.14 kg a week \(\+0\.17 %\), 28 weigh-ins since 2030-01-04; "
                                   r"gain band \+0\.12 to \+0\.50 % → on track\.\n$")

    def test_no_consent_means_no_body_csv(self):
        d = athlete(self, weight_tracking="no", weight="82 kg")
        write_body(d, [70.0] * 28)
        plan(d)
        fm = nutrition_md(d)
        self.assertEqual((fm["weight_kg"], fm["maintenance_source"]), (82.0, "formula"))

    def test_body_fat_range_from_profile(self):
        self.assertEqual(nu.body_fat({"body_fat_pct": "16-20"}, []), 18)
        self.assertEqual(nu.body_fat({"body_fat_pct": "about"}, []), None)
        self.assertEqual(nu.body_fat({"body_fat_pct": 30}, [(D0, 80, 22.0)]), 22.0)  # body.csv wins

    def test_sources_on_the_same_day_are_picked_not_mixed(self):
        import athlete_folder as af
        d = athlete(self, nutrition_phase="maintain")
        write_body(d, [80.0] * 28, bf=20)
        last = (D0 + datetime.timedelta(days=27)).isoformat()
        af.upsert_rows(d, "data/body.csv", [
            {"date": last, "weight_kg": 90.0, "body_fat_pct": 30, "source": "apple-health"},
            {"date": last, "body_fat_pct": 12, "source": "photo-range"},
            {"date": TODAY, "body_fat_pct": 14, "source": "photo-range"}])
        pts = nu.weigh_ins(d, datetime.date.fromisoformat(TODAY))
        self.assertEqual(pts[-2][1:], (80.0, 20.0))  # weight and body fat: the scale over Apple Health and photos
        self.assertEqual(pts[-1][1:], (None, 14.0))  # a photo range alone still counts for body fat
        self.assertEqual(nu.current_weight({}, pts)[0], 80.0)
        self.assertEqual(nu.body_fat({}, pts), 14.0)

    def test_weight_is_the_last_week_of_weigh_ins(self):
        d = athlete(self, nutrition_phase="maintain")
        write_body(d, [80.0] * 21 + [78.0] * 7)
        plan(d)
        self.assertEqual(nutrition_md(d)["weight_kg"], 78.0)


class MealPlan(unittest.TestCase):
    foods = nu.load_foods()

    def day(self, diet="omnivore", avoid=(), meals=4, phase="lose"):
        t = nu.targets(82, 180, 30, "male", "moderate", phase)
        return nu.meal_plan(t, self.foods, nu.allowed(self.foods, diet, list(avoid)), meals), t

    def eaten(self, mp):
        return [self.foods[it["food"]] for m in mp["meals"] for it in m["items"]]

    def test_omnivore_days_are_on_target(self):
        for meals in (3, 4, 5):
            for phase in nu.PHASES:
                mp, t = self.day(meals=meals, phase=phase)
                self.assertTrue(mp["on_target"], (meals, phase, mp["gap"]))
                self.assertEqual(len(mp["meals"]), meals)

    def test_diets_and_allergies_are_respected(self):
        for diet, banned in nu.DIETS.items():
            for avoid in ([], ["gluten", "soy"], ["tree-nut", "peanut", "milk"]):
                mp, _ = self.day(diet, avoid)
                for f in self.eaten(mp):
                    self.assertFalse(f["tags"] & (banned | set(avoid)), (diet, avoid, f["id"]))

    def test_a_disliked_word_removes_foods(self):
        mp, _ = self.day(avoid=["rice", "salmon"])
        names = " ".join(f["name"].lower() for f in self.eaten(mp))
        self.assertNotIn("rice", names)
        self.assertNotIn("salmon", names)

    def test_prefer_goes_first(self):
        t = nu.targets(82, 180, 30, "male", "moderate", "maintain")
        mp = nu.meal_plan(t, self.foods, set(self.foods), 4, prefer=["turkey_breast"])
        self.assertEqual(mp["meals"][1]["items"][0]["food"], "turkey_breast")

    def test_pieces_are_whole(self):
        mp, _ = self.day()
        for m in mp["meals"]:
            for it in m["items"]:
                f = self.foods[it["food"]]
                if f["piece_g"]:
                    self.assertAlmostEqual(it["grams"] / f["piece_g"], round(it["grams"] / f["piece_g"]))
                else:
                    self.assertEqual(it["grams"] % 5, 0)


class FoodTable(unittest.TestCase):
    def test_every_food_is_sourced_and_sane(self):
        foods = nu.load_foods()
        for i, f in foods.items():
            self.assertRegex(f["fdc_id"], r"^\d+$", i)
            self.assertIn(f["fdc_data_type"], ("SR Legacy", "Foundation"), i)
            self.assertIn(f["group"], ("protein", "starch", "fruit", "veg", "fat", "drink"), i)
            self.assertLessEqual(f["tags"], nu.ALLERGY_TAGS | {"meat", "poultry"}, i)
            atwater = 4 * f["protein_100"] + 4 * f["carbs_100"] + 9 * f["fat_100"] + 2 * f["fibre_100"]
            self.assertLess(abs(atwater - f["kcal_100"]), max(12, 0.12 * f["kcal_100"]), i)

    def test_meal_slots_name_real_foods(self):
        foods = nu.load_foods()
        for slots in (nu.BREAKFAST, nu.MAIN, nu.SNACK):
            for order in slots.values():
                self.assertLessEqual(set(order), set(foods))

    def test_source_md_names_usda_and_off(self):
        text = read(PLUGIN, "data", "SOURCE.md")
        self.assertIn("foods.csv", text)
        self.assertIn("FoodData Central", text)
        self.assertIn("Open Food Facts", text)

    def test_foods_lookup(self):
        out = run("nutrition.py", "foods", "chicken").stdout
        self.assertIn("171477", out)
        vegan = run("nutrition.py", "foods", "--diet", "vegan", "--group", "protein").stdout
        self.assertNotIn("Chicken", vegan)
        self.assertIn("Tofu", vegan)


class Writing(unittest.TestCase):
    def test_plan_writes_the_file_the_block_and_the_log(self):
        d = athlete(self)
        out = plan(d).stdout
        fm = nutrition_md(d)
        self.assertEqual((fm["status"], fm["phase"], fm["since"]), ("on", "lose", TODAY))
        self.assertIn("lawyer review pending", out)
        self.assertIn("A day of meals", out)
        plan(d)
        current = read(d, "plan", "CURRENT.md")
        self.assertEqual(current.count("<!-- coaich:nutrition -->"), 1)
        self.assertIn(f"{fm['kcal']:,} kcal", current)
        self.assertEqual(len(re.findall(r"· nutrition · lose 0.5 %/wk", read(d, "log.md"))), 2)

    def test_dry_run_writes_nothing(self):
        d = athlete(self)
        plan(d, "--dry-run")
        self.assertFalse(os.path.exists(os.path.join(d, "plan", "nutrition.md")))

    def test_missing_answers_are_named(self):
        for key in ("sex", "activity", "nutrition_phase", "age_years", "height"):
            d = athlete(self, **{key: None})
            r = plan(d, ok=False)
            self.assertEqual(r.returncode, 2, key)
            self.assertIn(key, r.stderr)


class OnboardHook(unittest.TestCase):
    def test_profile_template_has_every_nutrition_key(self):
        prof = nu.front_matter(read(PLUGIN, "templates", "athlete", "profile.md"))
        for k in NUTRITION_KEYS:
            self.assertIn(k, prof)
        self.assertNotIn(prof.get("eating_disorder_history"), (False, "no"))  # never pre-filled

    def test_onboard_and_contract_name_the_keys(self):
        onboard = read(PLUGIN, "skills", "onboard", "SKILL.md")
        contract = read(PLUGIN, "docs", "athlete-folder.md")
        for k in NUTRITION_KEYS:
            self.assertIn(k, contract, k)
        for k in ("eating_disorder_history", "nutrition_phase", "diet", "allergies", "foods_avoid",
                  "weight_tracking"):
            self.assertIn(f"`{k}", onboard, k)
        self.assertIn("nutrition.py", onboard)

    def test_skill_wording_matches_the_script(self):
        skill = read(PLUGIN, "skills", "nutrition", "SKILL.md")
        self.assertIn("lawyer review pending", skill)
        for code in nu.WORDING:
            self.assertIn(f"`{code}`", skill, code)


if __name__ == "__main__":
    unittest.main()
